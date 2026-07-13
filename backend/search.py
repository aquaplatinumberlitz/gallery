"""Search indexed gallery files, metadata, and library inspector rows."""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .errors import APIError, ErrorType
from .fielded_search_parser import parse_fielded_query
from .metadata_store import (
    _encode_inspector_cursor,
    cleanup_stale_index,
    get_first_library_root,
    get_library_inspector_metadata,
    list_library_inspector_rows,
    search_index,
    search_index_fielded,
    search_metadata,
)
from .paths import InvalidPathError, is_path_safe, resolve_path
from .scan import require_registered_path_allowed

router = APIRouter()
LOGGER = logging.getLogger(__name__)
_STALE_CLEANUP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="search-stale-cleanup")
_STALE_CLEANUP_LOCK = threading.Lock()
_STALE_CLEANUP_ROOTS: set[str] = set()


def _registered_or_requested_root(path: str | None) -> Path:
    if path:
        return resolve_path(path)
    root = get_first_library_root()
    if root is None:
        raise APIError(400, ErrorType.BAD_REQUEST, "path required")
    return root


def _require_visible_registered_path(path: Path) -> None:
    require_registered_path_allowed(path)


def _validated_search_root(path: str | None) -> Path:
    root = _registered_or_requested_root(path)
    if not is_path_safe(root):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied: path outside allowed root")
    if not root.exists() or not root.is_dir():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    _require_visible_registered_path(root)
    return root


def _filter_safe_paths(rows: list[dict]) -> tuple[list[dict], set[str]]:
    safe: list[dict] = []
    stale_paths: set[str] = set()
    for row in rows:
        try:
            resolved = resolve_path(row["path"])
        except (OSError, RuntimeError, InvalidPathError):
            stale_paths.add(str(row["path"]))
            continue
        if os.path.exists(resolved) and is_path_safe(resolved):
            safe.append(row)
        else:
            stale_paths.add(str(row["path"]))
    return safe, stale_paths


def _resolve_safe_inspector_path(path: str) -> Path:
    resolved = resolve_path(path)
    if not is_path_safe(resolved):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied: path outside allowed root")
    return resolved


def _cleanup_registered_library_roots(stale_paths: set[str]) -> int:
    from .metadata_store import list_libraries

    affected_roots: set[str] = set()
    for library in list_libraries():
        import_paths = library.get("import_paths") or [{"path": library["root_path"]}]
        for import_path in import_paths:
            root = str(Path(import_path["path"]).resolve())
            for stale_path in stale_paths:
                try:
                    Path(stale_path).resolve().relative_to(root)
                    affected_roots.add(root)
                    break
                except ValueError:
                    continue
    removed = 0
    for root in sorted(affected_roots)[:4]:
        removed += int(cleanup_stale_index(None, root, remove_outside_scope=False, max_candidates=250) or 0)
    return removed


def _schedule_stale_cleanup(stale_paths: set[str]) -> None:
    """Deduplicate affected roots and keep bounded cleanup off request workers."""
    if not stale_paths:
        return
    key = "\0".join(sorted(stale_paths))
    with _STALE_CLEANUP_LOCK:
        if key in _STALE_CLEANUP_ROOTS:
            return
        _STALE_CLEANUP_ROOTS.add(key)

    def run() -> None:
        try:
            _cleanup_registered_library_roots(stale_paths)
        finally:
            with _STALE_CLEANUP_LOCK:
                _STALE_CLEANUP_ROOTS.discard(key)

    _STALE_CLEANUP_EXECUTOR.submit(run)


@router.get("/api/search-metadata")
async def api_search_metadata(
    q: str = Query("", description="Prompt, model, sampler, filename, or metadata text to search"),
    limit: int = Query(100, ge=1, le=200, description="Maximum search results"),
    offset: int = Query(0, ge=0, description="Result offset"),
):
    """Search extracted image metadata and return path-safe results."""
    if not q.strip():
        return {"query": q, "total": 0, "results": []}

    try:
        data = await run_in_threadpool(search_metadata, q, limit, offset)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Metadata search failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    safe_results, stale_paths = await run_in_threadpool(_filter_safe_paths, data["results"])
    if stale_paths:
        _schedule_stale_cleanup(stale_paths)
    return {
        "query": data["query"],
        "total": len(safe_results),
        "results": safe_results,
    }


@router.get("/api/search")
async def api_search(
    q: str = Query("", description="Filename, album name, prompt, or metadata text to search"),
    scope: Literal["current", "all"] = Query(
        "current", description="Search current folder recursively or all indexed files"
    ),
    path: str | None = Query(None, description="Current folder path when scope=current"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results per section"),
    cursor: int = Query(0, ge=0, description="Result cursor for the merged media stream"),
):
    """Search albums, photos, and prompts in either current folder or all indexed files."""
    if not q.strip():
        root = await run_in_threadpool(_validated_search_root, path) if scope == "current" else None
        return {
            "query": q,
            "scope": scope,
            "root": str(root) if root is not None else "/",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
            "media": [],
            "next_cursor": None,
            "has_more": False,
            "returned": 0,
            "limit": limit,
        }

    root_path: Path | None = None
    if scope == "current":
        root_path = await run_in_threadpool(_validated_search_root, path)

    try:
        parsed = parse_fielded_query(q)
        if parsed.fields:
            data = await run_in_threadpool(search_index_fielded, q, scope, root_path, limit, cursor)
        else:
            data = await run_in_threadpool(search_index, q, scope, root_path, limit, cursor)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Search failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    stale_paths: set[str] = set()
    albums, stale = await run_in_threadpool(_filter_safe_paths, data["albums"])
    stale_paths.update(stale)
    photos, stale = await run_in_threadpool(_filter_safe_paths, data["photos"])
    stale_paths.update(stale)
    videos, stale = await run_in_threadpool(_filter_safe_paths, data.get("videos", []))
    stale_paths.update(stale)
    prompt, stale = await run_in_threadpool(_filter_safe_paths, data["prompt"])
    stale_paths.update(stale)
    media, stale = await run_in_threadpool(_filter_safe_paths, data.get("media", []))
    stale_paths.update(stale)

    if stale_paths:
        _schedule_stale_cleanup(stale_paths)

    return {
        "query": data["query"],
        "scope": data["scope"],
        "root": data["root"],
        "albums": albums,
        "photos": photos,
        "videos": videos,
        "prompt": prompt,
        "media": media,
        "next_cursor": data.get("next_cursor"),
        "has_more": data.get("next_cursor") is not None,
        "returned": len(media),
        "limit": data.get("limit", limit),
    }


@router.get("/api/library/inspector")
async def api_library_inspector(
    q: str = Query("", description="Free text or fielded metadata query"),
    scope: Literal["current", "all"] = Query(
        "current", description="Inspect current folder recursively or all indexed files"
    ),
    path: str | None = Query(None, description="Current folder path when scope=current"),
    limit: int = Query(200, ge=1, le=200, description="Maximum inspector rows"),
    cursor: str | None = Query(None, description="Opaque pagination cursor from previous response"),
    sort: Literal["name_asc", "name_desc", "date_asc", "date_desc"] = Query(
        "date_desc", description="Inspector row sort"
    ),
    model: str | None = Query(None, description="Exact displayed model/tool filter"),
    prompt: Literal["all", "has_prompt", "no_prompt"] = Query("all", description="Filter rows by prompt availability"),
):
    """Return paginated library inspector rows with stale path filtering."""
    root_path: Path | None = None
    if scope == "current":
        root_path = await run_in_threadpool(_validated_search_root, path)

    try:
        data = await run_in_threadpool(
            list_library_inspector_rows,
            q,
            scope,
            root_path,
            limit,
            sort,
            cursor,
            model,
            prompt,
        )
    except ValueError as exc:
        raise APIError(400, ErrorType.BAD_REQUEST, "Invalid pagination cursor") from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Library inspector failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    query_truncated = bool(data.get("truncated"))
    safe_rows, stale_paths = await run_in_threadpool(_filter_safe_paths, data["rows"])
    stale_detected = bool(stale_paths)
    # Overscan once if stale rows were detected and the current page is not full,
    # or if the query was truncated and may contain stale entries just past the page.
    if stale_detected and (len(safe_rows) < limit or query_truncated):
        overscan_limit = min(max(limit * 2, limit + 25), 1000)
        try:
            overscan_data = await run_in_threadpool(
                list_library_inspector_rows,
                q,
                scope,
                root_path,
                overscan_limit,
                sort,
                cursor,
                model,
                prompt,
            )
        except ValueError as exc:
            raise APIError(400, ErrorType.BAD_REQUEST, "Invalid pagination cursor") from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Library inspector pagination failed")
            raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc
        overscan_safe_rows, overscan_stale_paths = await run_in_threadpool(_filter_safe_paths, overscan_data["rows"])
        overscan_stale_detected = bool(overscan_stale_paths)
        data = overscan_data
        query_truncated = bool(overscan_data.get("truncated")) or len(overscan_safe_rows) > limit
        safe_rows = overscan_safe_rows[:limit]
        stale_detected = stale_detected or overscan_stale_detected
        stale_paths.update(overscan_stale_paths)

    if stale_detected:
        _schedule_stale_cleanup(stale_paths)

    data["rows"] = safe_rows
    data["returned"] = len(safe_rows)
    data["limit"] = limit
    data["truncated"] = query_truncated
    if query_truncated and safe_rows:
        data["next_cursor"] = _encode_inspector_cursor(safe_rows[-1])
    elif query_truncated:
        data["next_cursor"] = data.get("next_cursor")
    else:
        data["next_cursor"] = None
    data["has_more"] = data["next_cursor"] is not None
    return data


@router.get("/api/library/inspector/metadata")
async def api_library_inspector_metadata(
    path: str = Query(..., description="Encoded image path from an indexed library row"),
):
    """Return indexed metadata details for a selected library inspector image."""
    resolved = await run_in_threadpool(_resolve_safe_inspector_path, path)

    try:
        data = await run_in_threadpool(get_library_inspector_metadata, resolved)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Library inspector metadata failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    if data is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Indexed metadata unavailable for this path")

    return data
