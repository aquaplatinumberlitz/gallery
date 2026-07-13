"""Search indexed gallery files, metadata, and library inspector rows."""

import logging
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
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
from .models import (
    APIErrorResponse,
    MetadataSearchResponse,
    SearchAllScopeV1,
    SearchFolderScopeV1,
    SearchLibraryScopeV1,
    SearchQueryRequestV1,
    SearchResponse,
)
from .paths import InvalidPathError, is_path_safe, resolve_path
from .scan import require_registered_path_allowed
from .search_indexer import require_search_index_mode
from .search_scope import SearchScopeContext, SearchScopeInput, resolve_search_scope, resolve_search_v2_scope

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


_SEARCH_ERROR_RESPONSES = {
    400: {"model": APIErrorResponse, "description": "Malformed or incompatible cursor"},
    404: {"model": APIErrorResponse, "description": "Library or folder scope not found"},
    503: {"model": APIErrorResponse, "description": "Required search index unavailable"},
    500: {"model": APIErrorResponse, "description": "Sanitized internal failure"},
}


@router.get("/api/search-metadata", responses=_SEARCH_ERROR_RESPONSES)
def api_search_metadata(
    q: Annotated[str, Query(description="Prompt, model, sampler, filename, or metadata text to search")] = "",
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum search results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Result offset")] = 0,
) -> MetadataSearchResponse:
    """Search current catalog-owned image metadata without filesystem probes."""
    if not q.strip():
        return MetadataSearchResponse(query=q, total=0, results=[])

    try:
        data = search_metadata(q, limit, offset)
    except sqlite3.OperationalError as exc:
        raise APIError(503, ErrorType.SERVER_ERROR, "Search index temporarily unavailable") from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Metadata search failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    return MetadataSearchResponse.model_validate(data)


@router.get("/api/search", responses=_SEARCH_ERROR_RESPONSES)
def api_search(
    response: Response,
    q: Annotated[str, Query(description="Filename, album name, prompt, or metadata text to search")] = "",
    scope: Annotated[
        SearchScopeInput,
        Query(description="Folder, library, or all-library search scope; current is a legacy folder alias"),
    ] = "current",
    library_id: Annotated[int | None, Query(ge=1, description="Registered library for folder/library scope")] = None,
    path: Annotated[str | None, Query(description="Absolute registered folder path for folder scope")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum media rows per page")] = 50,
    cursor: Annotated[str | None, Query(description="Opaque result cursor; decimal offsets are deprecated")] = None,
) -> SearchResponse:
    """Legacy GET adapter for canonical Search V2 lexical execution."""
    if cursor is not None and cursor.isdecimal():
        response.headers["Deprecation"] = "true"
        response.headers["Warning"] = '299 - "Decimal search cursors are deprecated; use next_cursor"'
    context = resolve_search_scope(scope, library_id=library_id, path=path)
    if context.kind == "folder":
        canonical_scope = SearchFolderScopeV1(
            kind="folder",
            library_id=context.library_id,
            import_path_id=context.import_path_id,
            relative_path=context.relative_path or "",
        )
    elif context.kind == "library":
        canonical_scope = SearchLibraryScopeV1(kind="library", library_id=context.library_id)
    else:
        canonical_scope = SearchAllScopeV1(kind="all")
    # Preserve the legacy GET bounds (including limit up to 200 and unversioned
    # text length) while adapting the already-authorized scope into the shared
    # executor. Only the POST contract is validated as Search V2 input.
    request = SearchQueryRequestV1.model_construct(
        schema_version=1,
        mode="lexical",
        text=q,
        scope=canonical_scope,
        cursor=cursor,
        limit=limit,
    )
    return _execute_search_query(request, context)


def _execute_search_query(request: SearchQueryRequestV1, context: SearchScopeContext) -> SearchResponse:
    """Execute one already-authorized canonical search request."""
    if request.filters.prompt_groups:
        require_search_index_mode("prompt_groups", library_id=context.library_id)
    if request.mode == "workflow" or request.filters.workflow_groups:
        require_search_index_mode("workflow", library_id=context.library_id)
    if request.mode == "raw":
        require_search_index_mode("raw", library_id=context.library_id)
    if request.mode != "lexical" or request.filters.prompt_groups or request.filters.workflow_groups:
        raise APIError(409, ErrorType.FEATURE_DISABLED, f"Search mode '{request.mode}' is not enabled")
    if not request.text.strip():
        return SearchResponse.model_validate(
            {
                "query": request.text,
                "scope": context.kind,
                "root": context.folder_path or "/",
                "albums": [],
                "photos": [],
                "videos": [],
                "prompt": [],
                "media": [],
                "next_cursor": None,
                "has_more": False,
                "returned": 0,
                "limit": request.limit,
            }
        )

    try:
        parsed = parse_fielded_query(request.text)
        if parsed.fields:
            data = search_index_fielded(
                request.text,
                context.kind,
                context.folder_path,
                request.limit,
                request.cursor,
                library_id=context.library_id,
            )
        else:
            data = search_index(
                request.text,
                context.kind,
                context.folder_path,
                request.limit,
                request.cursor,
                library_id=context.library_id,
            )
    except ValueError as exc:
        raise APIError(400, ErrorType.BAD_REQUEST, "Invalid search cursor") from exc
    except sqlite3.OperationalError as exc:
        raise APIError(503, ErrorType.SERVER_ERROR, "Search index temporarily unavailable") from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Search failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    return SearchResponse.model_validate(data)


@router.post("/api/search/query", responses=_SEARCH_ERROR_RESPONSES)
def api_search_query(request: SearchQueryRequestV1) -> SearchResponse:
    """Execute the canonical versioned Search V2 contract."""
    context = resolve_search_v2_scope(request.scope)
    return _execute_search_query(request, context)


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
