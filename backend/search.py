import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .config import DEFAULT_ROOT, GALLERY_ROOT
from .errors import APIError, ErrorType
from .fielded_search_parser import parse_fielded_query
from .metadata_store import (
    cleanup_stale_index,
    get_library_inspector_metadata,
    list_library_inspector_rows,
    search_index,
    search_index_fielded,
    search_metadata,
)
from .paths import is_path_safe, resolve_path

router = APIRouter()


@router.get("/api/search-metadata")
async def api_search_metadata(
    q: str = Query("", description="Prompt, model, sampler, filename, or metadata text to search"),
    limit: int = Query(100, ge=1, le=200, description="Maximum search results"),
    offset: int = Query(0, ge=0, description="Result offset"),
):
    if not q.strip():
        return {"query": q, "total": 0, "results": []}

    try:
        data = await run_in_threadpool(search_metadata, q, limit, offset)
    except Exception as exc:  # noqa: BLE001
        raise APIError(500, ErrorType.SERVER_ERROR, f"Metadata search failed: {exc}") from exc

    safe_results = [
        result
        for result in data["results"]
        if is_path_safe(resolve_path(result["path"]))
    ]
    return {
        "query": data["query"],
        "total": len(safe_results),
        "results": safe_results,
    }


@router.get("/api/search")
async def api_search(
    q: str = Query("", description="Filename, album name, prompt, or metadata text to search"),
    scope: Literal["current", "all"] = Query("current", description="Search current folder recursively or all indexed files"),
    path: str | None = Query(None, description="Current folder path when scope=current"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results per section"),
):
    if not q.strip():
        root = resolve_path(path) if scope == "current" and path else GALLERY_ROOT
        return {"query": q, "scope": scope, "root": str(root), "albums": [], "photos": [], "prompt": []}

    root_path: Path | None = None
    if scope == "current":
        root_path = resolve_path(path) if path else DEFAULT_ROOT
        if not is_path_safe(root_path):
            raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied: path outside allowed root")
        if not root_path.exists() or not root_path.is_dir():
            raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")

    try:
        parsed = parse_fielded_query(q)
        if parsed.fields:
            data = await run_in_threadpool(search_index_fielded, q, scope, root_path, limit)
        else:
            data = await run_in_threadpool(search_index, q, scope, root_path, limit)
    except Exception as exc:  # noqa: BLE001
        raise APIError(500, ErrorType.SERVER_ERROR, f"Search failed: {exc}") from exc

    stale_detected = False

    def safe_section(section: list[dict]) -> list[dict]:
        nonlocal stale_detected
        safe_results: list[dict] = []
        for result in section:
            try:
                resolved = resolve_path(result["path"])
            except (OSError, RuntimeError):
                stale_detected = True
                continue
            if os.path.exists(resolved) and is_path_safe(resolved):
                safe_results.append(result)
            else:
                stale_detected = True
        return safe_results

    albums = safe_section(data["albums"])
    photos = safe_section(data["photos"])
    prompt = safe_section(data["prompt"])

    if stale_detected:
        await run_in_threadpool(cleanup_stale_index, None, GALLERY_ROOT)

    return {
        "query": data["query"],
        "scope": data["scope"],
        "root": data["root"],
        "albums": albums,
        "photos": photos,
        "prompt": prompt,
    }


@router.get("/api/library/inspector")
async def api_library_inspector(
    q: str = Query("", description="Free text or fielded metadata query"),
    scope: Literal["current", "all"] = Query("current", description="Inspect current folder recursively or all indexed files"),
    path: str | None = Query(None, description="Current folder path when scope=current"),
    limit: int = Query(200, ge=1, le=200, description="Maximum inspector rows"),
    sort: Literal["name_asc", "name_desc", "date_asc", "date_desc"] = Query("date_desc", description="Inspector row sort"),
):
    root_path: Path | None = None
    if scope == "current":
        root_path = resolve_path(path) if path else DEFAULT_ROOT
        if not is_path_safe(root_path):
            raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied: path outside allowed root")
        if not root_path.exists() or not root_path.is_dir():
            raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")

    def _filter_safe_rows(rows: list[dict]) -> tuple[list[dict], bool]:
        stale = False
        safe: list[dict] = []
        for row in rows:
            try:
                resolved = resolve_path(row["path"])
            except (OSError, RuntimeError):
                stale = True
                continue
            if os.path.exists(resolved) and is_path_safe(resolved):
                safe.append(row)
            else:
                stale = True
        return safe, stale

    try:
        data = await run_in_threadpool(list_library_inspector_rows, q, scope, root_path, limit, sort)
    except Exception as exc:  # noqa: BLE001
        raise APIError(500, ErrorType.SERVER_ERROR, f"Library inspector failed: {exc}") from exc

    query_truncated = bool(data.get("truncated"))
    safe_rows, stale_detected = _filter_safe_rows(data["rows"])
    # Overscan once if stale rows were detected and the current page is not full,
    # or if the query was truncated and may contain stale entries just past the page.
    if stale_detected and (len(safe_rows) < limit or query_truncated):
        overscan_limit = min(max(limit * 2, limit + 25), 1000)
        try:
            overscan_data = await run_in_threadpool(list_library_inspector_rows, q, scope, root_path, overscan_limit, sort)
        except Exception as exc:  # noqa: BLE001
            raise APIError(500, ErrorType.SERVER_ERROR, f"Library inspector failed: {exc}") from exc
        overscan_safe_rows, overscan_stale_detected = _filter_safe_rows(overscan_data["rows"])
        data = overscan_data
        query_truncated = bool(overscan_data.get("truncated")) or len(overscan_safe_rows) > limit
        safe_rows = overscan_safe_rows[:limit]
        stale_detected = stale_detected or overscan_stale_detected

    if stale_detected:
        await run_in_threadpool(cleanup_stale_index, None, GALLERY_ROOT)

    data["rows"] = safe_rows
    data["returned"] = len(safe_rows)
    data["limit"] = limit
    data["truncated"] = query_truncated
    return data


@router.get("/api/library/inspector/metadata")
async def api_library_inspector_metadata(
    path: str = Query(..., description="Encoded image path from an indexed library row"),
):
    resolved = resolve_path(path)
    if not is_path_safe(resolved):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied: path outside allowed root")

    try:
        data = await run_in_threadpool(get_library_inspector_metadata, resolved)
    except Exception as exc:  # noqa: BLE001
        raise APIError(500, ErrorType.SERVER_ERROR, f"Library inspector metadata failed: {exc}") from exc

    if data is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Indexed metadata unavailable for this path")

    return data
