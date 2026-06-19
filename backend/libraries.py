"""Registered library management and progressive discovery endpoints."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .errors import APIError, ErrorType
from .indexer import rebuild_index_scope
from .metadata_store import (
    get_library,
    get_library_progress,
    list_libraries,
    register_library,
    unregister_library,
    update_library_state,
)
from .paths import is_path_safe, resolve_path

router = APIRouter()


class LibraryCreate(BaseModel):
    """Payload for registering a managed filesystem root."""

    root_path: str
    name: str | None = None


def _discover_library(library_id: int, root_path: str) -> None:
    try:
        update_library_state(library_id, "indexing")
        rebuild_index_scope(root_path)
        update_library_state(library_id, "ready", scan_completed=True)
    except Exception as exc:  # noqa: BLE001
        update_library_state(library_id, "error", last_error=str(exc), scan_completed=True)


@router.get("/api/libraries")
async def api_list_libraries():
    """List registered libraries."""
    return await run_in_threadpool(list_libraries)


@router.post("/api/libraries", status_code=201)
async def api_register_library(payload: LibraryCreate):
    """Register an existing, canonical, non-overlapping library root."""
    target = resolve_path(payload.root_path)
    if not is_path_safe(target):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not target.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Path not found")
    if not target.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")
    try:
        return await run_in_threadpool(register_library, target, payload.name)
    except ValueError as exc:
        raise APIError(409, "library_overlap", str(exc)) from exc


@router.get("/api/libraries/{library_id}")
async def api_get_library(library_id: int):
    """Return library details."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return library


@router.get("/api/libraries/{library_id}/progress")
async def api_library_progress(library_id: int):
    """Return progressive discovery and metadata coverage."""
    try:
        return await run_in_threadpool(get_library_progress, library_id)
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc


@router.post("/api/libraries/{library_id}/scan", status_code=202)
async def api_scan_library(library_id: int, background_tasks: BackgroundTasks):
    """Trigger background discovery/import for a registered library."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    root = Path(library["root_path"])
    if not root.exists():
        await run_in_threadpool(update_library_state, library_id, "offline", last_error="Root path is offline")
        raise APIError(409, "library_offline", "Library root is offline")
    await run_in_threadpool(update_library_state, library_id, "discovering")
    background_tasks.add_task(_discover_library, library_id, str(root))
    return {"library_id": library_id, "state": "discovering"}


@router.delete("/api/libraries/{library_id}")
async def api_unregister_library(
    library_id: int,
    confirm: bool = Query(False, description="Must be true; source files are never deleted"),
):
    """Unregister a library and delete only its catalog rows."""
    if not confirm:
        raise APIError(400, "confirmation_required", "Unregister requires explicit confirmation")
    if not await run_in_threadpool(unregister_library, library_id):
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return {"library_id": library_id, "unregistered": True, "source_files_deleted": False}
