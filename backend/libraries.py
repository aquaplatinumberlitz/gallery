"""Registered library management and progressive discovery endpoints."""

import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse
from wcmatch import glob

from .derivative_scheduler import scheduler
from .errors import APIError, ErrorType
from .indexer import rebuild_index_scope
from .library_events import event_payload, event_stream, publish
from .metadata_store import (
    LibraryOverlapError,
    create_job,
    create_library,
    create_or_get_active_scan_job,
    get_gallery_stats,
    get_job,
    get_library,
    get_library_jobs,
    get_library_progress,
    get_library_stats,
    list_active_jobs,
    list_jobs,
    list_libraries,
    repair_library_assets,
    unregister_library,
    update_job_state,
    update_library,
    update_library_state,
)
from .paths import is_path_safe, resolve_path

router = APIRouter()


class LibraryCreate(BaseModel):
    """Payload for registering one or more managed filesystem roots."""

    model_config = ConfigDict(extra="forbid")

    root_path: str | None = None
    import_paths: list[str] | None = None
    exclusion_patterns: list[str] = Field(default_factory=list)
    name: str | None = None


class LibraryUpdate(BaseModel):
    """Replacement fields for one registered library."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    import_paths: list[str] | None = None
    exclusion_patterns: list[str] | None = None


def _trim_value(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1].strip()
    return trimmed


def _effective_create_paths(payload: LibraryCreate) -> list[str]:
    if payload.root_path is not None and payload.import_paths is not None:
        raise APIError(400, ErrorType.BAD_REQUEST, "Use import_paths or root_path, not both")
    if payload.import_paths is not None:
        return payload.import_paths
    if payload.root_path is not None:
        return [payload.root_path]
    return []


def _validation_item(value: str) -> dict[str, Any]:
    return {
        "value": value,
        "normalized_value": None,
        "is_valid": True,
        "message": None,
        "warnings": [],
    }


def _validate_settings(
    import_paths: list[str],
    exclusion_patterns: list[str],
    *,
    existing_library_id: int | None = None,
) -> dict[str, Any]:
    libraries = list_libraries()
    path_items = [_validation_item(value) for value in import_paths]
    canonical_paths: list[str | None] = []

    for item in path_items:
        value = _trim_value(item["value"])
        if not value:
            item.update(is_valid=False, message="Import path cannot be empty")
            canonical_paths.append(None)
            continue
        path = Path(value)
        if not path.is_absolute():
            item.update(is_valid=False, message="Import path must be absolute")
            canonical_paths.append(None)
            continue
        try:
            resolved = resolve_path(value)
        except (OSError, RuntimeError):
            item.update(is_valid=False, message="Import path could not be resolved")
            canonical_paths.append(None)
            continue
        normalized = str(resolved)
        item["normalized_value"] = normalized
        canonical_paths.append(normalized)
        if not is_path_safe(resolved):
            item.update(is_valid=False, message="Import path is outside the allowed safety root")
        elif not resolved.exists():
            item.update(is_valid=False, message="Import path does not exist")
        elif not resolved.is_dir():
            item.update(is_valid=False, message="Import path is not a directory")
        elif not os.access(resolved, os.R_OK | os.X_OK):
            item.update(is_valid=False, message="Import path is not readable")
        else:
            try:
                with os.scandir(resolved):
                    pass
            except (OSError, PermissionError):
                item.update(is_valid=False, message="Import path is not readable")

    seen_paths: set[str] = set()
    for item, canonical in zip(path_items, canonical_paths, strict=True):
        if canonical is None:
            continue
        if canonical in seen_paths:
            item.update(is_valid=False, message="Duplicate import path")
        seen_paths.add(canonical)

    for index, (item, canonical) in enumerate(zip(path_items, canonical_paths, strict=True)):
        if canonical is None:
            continue
        for other_index, other in enumerate(canonical_paths):
            if index == other_index or other is None or canonical == other:
                continue
            if _path_overlaps(canonical, other):
                item["warnings"].append("This import path overlaps another path in the same library")
                break
        for library in libraries:
            if existing_library_id is not None and int(library["id"]) == existing_library_id:
                continue
            overlap = next(
                (
                    candidate["path"]
                    for candidate in library["import_paths"]
                    if _path_overlaps(canonical, str(candidate["path"]))
                ),
                None,
            )
            if overlap is not None:
                item.update(is_valid=False, message=f"Import path overlaps registered path: {overlap}")
                break

    pattern_items = [_validation_item(value) for value in exclusion_patterns]
    seen_patterns: set[str] = set()
    if len(pattern_items) > 128:
        for item in pattern_items[128:]:
            item.update(is_valid=False, message="At most 128 exclusion patterns are allowed")
    for item in pattern_items:
        pattern = _trim_value(item["value"])
        item["normalized_value"] = pattern or None
        if not pattern:
            item.update(is_valid=False, message="Exclusion pattern cannot be empty")
            continue
        if Path(pattern).is_absolute() or ".." in Path(pattern.replace("\\", "/")).parts:
            item.update(is_valid=False, message="Exclusion patterns must be relative and cannot contain '..'")
            continue
        if pattern in seen_patterns:
            item.update(is_valid=False, message="Duplicate exclusion pattern")
            continue
        seen_patterns.add(pattern)
        try:
            glob.compile(pattern, flags=glob.GLOBSTAR)
        except Exception:  # noqa: BLE001
            item.update(is_valid=False, message="Invalid exclusion pattern")

    return {
        "is_valid": bool(path_items)
        and all(item["is_valid"] for item in path_items)
        and all(item["is_valid"] for item in pattern_items),
        "import_paths": path_items,
        "exclusion_patterns": pattern_items,
    }


def _path_overlaps(left: str, right: str) -> bool:
    left_path = Path(left)
    right_path = Path(right)
    try:
        left_path.relative_to(right_path)
        return True
    except ValueError:
        pass
    try:
        right_path.relative_to(left_path)
        return True
    except ValueError:
        return False


def _normalized_validated_values(result: dict[str, Any], field: str) -> list[str]:
    if not result["is_valid"]:
        overlap = next(
            (
                item["message"]
                for item in result["import_paths"]
                if item["message"] and "overlaps registered path" in item["message"]
            ),
            None,
        )
        if overlap:
            raise APIError(409, "library_overlap", overlap)
        message = next(
            (
                item["message"]
                for key in ("import_paths", "exclusion_patterns")
                for item in result[key]
                if not item["is_valid"] and item["message"]
            ),
            "Invalid library settings",
        )
        if message == "Import path does not exist":
            raise APIError(404, ErrorType.NOT_FOUND, message)
        if message == "Import path is not a directory":
            raise APIError(400, ErrorType.NOT_DIRECTORY, message)
        if message in {
            "Import path is outside the allowed safety root",
            "Import path is not readable",
        }:
            raise APIError(403, ErrorType.PERMISSION_DENIED, message)
        raise APIError(400, ErrorType.BAD_REQUEST, message)
    return [str(item["normalized_value"]) for item in result[field]]


def _emit_job(job: dict[str, Any], event_type: str = "job.updated") -> None:
    publish(event_payload(event_type, job))
    if job["library_id"] is not None:
        publish(event_payload("library.progress", job))


def _set_job_state(job_id: int, state: str, **changes: Any) -> dict[str, Any]:
    job = update_job_state(job_id, state, **changes)
    if job is None:
        raise RuntimeError(f"Library job {job_id} disappeared")
    event_type = "job.updated"
    if state == "succeeded":
        event_type = "job.completed"
    elif state == "failed":
        event_type = "job.failed"
    _emit_job(job, event_type)
    return job


def _active_library_job(library_id: int, *job_types: str) -> dict[str, Any] | None:
    return next((job for job in list_active_jobs(library_id) if job["type"] in job_types), None)


def _queue_scan(library_id: int, *, parent_job_id: int | None = None) -> tuple[dict[str, Any], bool]:
    job, created = create_or_get_active_scan_job(library_id, parent_job_id=parent_job_id)
    if created:
        _emit_job(job)
    return job, created


def _discover_library(job_id: int, library_id: int, import_paths: list[str]) -> bool:
    try:
        _set_job_state(
            job_id,
            "running",
            progress_current=0,
            progress_total=len(import_paths),
            message="Scanning library",
        )
        update_library_state(library_id, "indexing")
        counters = {"indexed": 0, "reconciled": 0, "queued": 0, "coalesced": 0, "skipped": 0, "failed": 0}
        for index, import_path in enumerate(import_paths, start=1):
            result = rebuild_index_scope(import_path)
            counters["indexed"] += int(result.get("indexed", 0))
            counters["reconciled"] += int(result.get("reconciled", 0))
            for key in ("queued", "coalesced", "skipped", "failed"):
                counters[key] += int(result.get("metadata", {}).get(key, 0))
            _set_job_state(
                job_id,
                "running",
                progress_current=index,
                progress_total=len(import_paths),
                message=f"Scanned {index} of {len(import_paths)} import paths",
                counters=counters,
            )
        update_library_state(library_id, "ready", scan_completed=True)
        _set_job_state(
            job_id,
            "succeeded",
            progress_current=len(import_paths),
            progress_total=len(import_paths),
            message="Scan completed",
            counters=counters,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        update_library_state(library_id, "error", last_error=str(exc), scan_completed=True)
        _set_job_state(job_id, "failed", message="Scan failed", error=str(exc))
        return False


def _run_scan_all(parent_job_id: int, children: list[tuple[int, int, list[str], bool]]) -> None:
    total = len(children)
    counters = {"total": total, "succeeded": 0, "failed": 0, "coalesced": 0}
    _set_job_state(
        parent_job_id,
        "running",
        progress_current=0,
        progress_total=total,
        message="Scanning all libraries",
        counters=counters,
    )
    for index, (job_id, library_id, import_paths, created) in enumerate(children, start=1):
        if created:
            _discover_library(job_id, library_id, import_paths)
        else:
            counters["coalesced"] += 1
            while (job := get_job(job_id)) is not None and job["state"] in {"queued", "running"}:
                time.sleep(0.05)
        job = get_job(job_id)
        if job is not None and job["state"] == "succeeded":
            counters["succeeded"] += 1
        else:
            counters["failed"] += 1
        _set_job_state(
            parent_job_id,
            "running",
            progress_current=index,
            progress_total=total,
            message=f"Completed {index} of {total} library scans",
            counters=counters,
        )
    state = "failed" if counters["failed"] else "succeeded"
    _set_job_state(
        parent_job_id,
        state,
        progress_current=total,
        progress_total=total,
        message="Scan all completed" if state == "succeeded" else "One or more library scans failed",
        error="One or more library scans failed" if state == "failed" else None,
        counters=counters,
    )


@router.get("/api/libraries")
async def api_list_libraries():
    """List registered libraries."""
    return await run_in_threadpool(list_libraries)


@router.post("/api/libraries", status_code=201)
async def api_register_library(payload: LibraryCreate):
    """Register one library with ordered import paths and exclusions."""
    import_paths = _effective_create_paths(payload)
    validation = await run_in_threadpool(
        _validate_settings,
        import_paths,
        payload.exclusion_patterns,
    )
    normalized_paths = _normalized_validated_values(validation, "import_paths")
    normalized_patterns = _normalized_validated_values(validation, "exclusion_patterns")
    try:
        return await run_in_threadpool(
            create_library,
            normalized_paths,
            name=_trim_value(payload.name) if payload.name is not None else None,
            exclusion_patterns=normalized_patterns,
        )
    except LibraryOverlapError as exc:
        raise APIError(409, "library_overlap", str(exc)) from exc


@router.post("/api/libraries/validate")
async def api_validate_library_create(payload: LibraryCreate):
    """Validate create settings without writing them."""
    try:
        import_paths = _effective_create_paths(payload)
    except APIError as exc:
        item = _validation_item(payload.root_path or "")
        item.update(is_valid=False, message=exc.detail["message"])
        return {
            "is_valid": False,
            "import_paths": [item],
            "exclusion_patterns": [],
        }
    return await run_in_threadpool(_validate_settings, import_paths, payload.exclusion_patterns)


@router.post("/api/libraries/scan-all", status_code=202)
async def api_scan_all_libraries(background_tasks: BackgroundTasks):
    """Queue a parent scan-all job and one child scan per library."""
    libraries = await run_in_threadpool(list_libraries)
    parent = await run_in_threadpool(
        create_job,
        "scan_all",
        progress_total=len(libraries),
        message="Scan all queued",
    )
    _emit_job(parent)
    children: list[tuple[int, int, list[str], bool]] = []
    for library in libraries:
        library_id = int(library["id"])
        import_paths = [str(item["path"]) for item in library["import_paths"]]
        job, created = await run_in_threadpool(_queue_scan, library_id, parent_job_id=parent["id"])
        children.append((int(job["id"]), library_id, import_paths, created))
    background_tasks.add_task(_run_scan_all, int(parent["id"]), children)
    return {
        "job_id": parent["id"],
        "state": parent["state"],
        "child_job_ids": [child[0] for child in children],
        "count": len(children),
    }


@router.get("/api/stats")
async def api_gallery_stats():
    """Return aggregate statistics across registered libraries."""
    return await run_in_threadpool(get_gallery_stats)


@router.get("/api/jobs")
async def api_list_jobs(limit: int = Query(100, ge=1, le=500)):
    """Return recent library-management jobs."""
    return await run_in_threadpool(list_jobs, limit=limit)


@router.get("/api/jobs/{job_id}")
async def api_get_job(job_id: int):
    """Return one library-management job."""
    job = await run_in_threadpool(get_job, job_id)
    if job is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Job not found")
    return job


@router.get("/api/events")
async def api_events(request: Request):
    """Stream best-effort library job and progress events."""
    return StreamingResponse(
        event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/libraries/{library_id}")
async def api_get_library(library_id: int):
    """Return library details."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return library


@router.post("/api/libraries/{library_id}/validate")
async def api_validate_library_update(library_id: int, payload: LibraryUpdate):
    """Validate replacement settings for an existing library without writing."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    paths = (
        payload.import_paths
        if payload.import_paths is not None
        else [str(item["path"]) for item in library["import_paths"]]
    )
    patterns = (
        payload.exclusion_patterns if payload.exclusion_patterns is not None else list(library["exclusion_patterns"])
    )
    return await run_in_threadpool(
        _validate_settings,
        paths,
        patterns,
        existing_library_id=library_id,
    )


async def _api_update_library(library_id: int, payload: LibraryUpdate):
    if not payload.model_fields_set:
        raise APIError(400, ErrorType.BAD_REQUEST, "At least one update field is required")
    if any(getattr(payload, field) is None for field in payload.model_fields_set):
        raise APIError(400, ErrorType.BAD_REQUEST, "Update fields cannot be null")
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    if {"import_paths", "exclusion_patterns"} & payload.model_fields_set:
        active = await run_in_threadpool(_active_library_job, library_id, "scan", "repair")
        if active is not None:
            raise APIError(409, "library_busy", "Library scan or repair is active")
    normalized_paths: list[str] | None = None
    normalized_patterns: list[str] | None = None
    if payload.import_paths is not None or payload.exclusion_patterns is not None:
        paths = (
            payload.import_paths
            if payload.import_paths is not None
            else [str(item["path"]) for item in library["import_paths"]]
        )
        patterns = (
            payload.exclusion_patterns
            if payload.exclusion_patterns is not None
            else list(library["exclusion_patterns"])
        )
        validation = await run_in_threadpool(
            _validate_settings,
            paths,
            patterns,
            existing_library_id=library_id,
        )
        if payload.import_paths is not None:
            normalized_paths = _normalized_validated_values(validation, "import_paths")
        if payload.exclusion_patterns is not None:
            normalized_patterns = _normalized_validated_values(validation, "exclusion_patterns")
    if payload.name is not None and not _trim_value(payload.name):
        raise APIError(400, ErrorType.BAD_REQUEST, "Library name cannot be empty")
    try:
        updated = await run_in_threadpool(
            update_library,
            library_id,
            name=_trim_value(payload.name) if payload.name is not None else None,
            import_paths=normalized_paths,
            exclusion_patterns=normalized_patterns,
        )
    except LibraryOverlapError as exc:
        raise APIError(409, "library_overlap", str(exc)) from exc
    if updated is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return updated


@router.patch("/api/libraries/{library_id}")
async def api_patch_library(library_id: int, payload: LibraryUpdate):
    """Replace supplied library settings."""
    return await _api_update_library(library_id, payload)


@router.put("/api/libraries/{library_id}")
async def api_put_library(library_id: int, payload: LibraryUpdate):
    """Compatibility alias for PATCH library settings."""
    return await _api_update_library(library_id, payload)


@router.get("/api/libraries/{library_id}/progress")
async def api_library_progress(library_id: int):
    """Return progressive discovery and metadata coverage."""
    try:
        return await run_in_threadpool(get_library_progress, library_id)
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc


@router.get("/api/libraries/{library_id}/stats")
async def api_library_stats(library_id: int):
    """Return aggregate media statistics for one library."""
    try:
        return await run_in_threadpool(get_library_stats, library_id)
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc


@router.get("/api/libraries/{library_id}/jobs")
async def api_library_jobs(library_id: int, limit: int = Query(50, ge=1, le=200)):
    """Return recent jobs for one library."""
    if await run_in_threadpool(get_library, library_id) is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return await run_in_threadpool(get_library_jobs, library_id, limit=limit)


@router.post("/api/libraries/{library_id}/scan", status_code=202)
async def api_scan_library(library_id: int, background_tasks: BackgroundTasks):
    """Trigger background discovery/import for a registered library."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    import_paths = [str(item["path"]) for item in library["import_paths"]]
    if any(not Path(path).is_dir() for path in import_paths):
        await run_in_threadpool(update_library_state, library_id, "offline", last_error="Root path is offline")
        raise APIError(409, "library_offline", "One or more library import paths are offline")
    job, created = await run_in_threadpool(_queue_scan, library_id)
    if created:
        await run_in_threadpool(update_library_state, library_id, "discovering")
        background_tasks.add_task(_discover_library, int(job["id"]), library_id, import_paths)
    return {"library_id": library_id, "job_id": job["id"], "state": job["state"]}


@router.post("/api/libraries/{library_id}/repair")
async def api_repair_library(library_id: int):
    """Reconcile a registered library's asset catalog with its filesystem."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    if any(not Path(item["path"]).is_dir() for item in library["import_paths"]):
        await run_in_threadpool(update_library_state, library_id, "offline", last_error="Root path is offline")
        raise APIError(409, "library_offline", "One or more library import paths are offline")
    active = await run_in_threadpool(_active_library_job, library_id, "scan", "repair")
    if active is not None:
        raise APIError(409, "library_busy", "Library scan or repair is active")
    job = await run_in_threadpool(create_job, "repair", library_id=library_id, message="Repair queued")
    _emit_job(job)
    await run_in_threadpool(_set_job_state, int(job["id"]), "running", message="Repairing library")
    try:
        counts = await run_in_threadpool(repair_library_assets, library_id)
    except Exception as exc:
        await run_in_threadpool(
            _set_job_state,
            int(job["id"]),
            "failed",
            message="Repair failed",
            error=str(exc),
        )
        raise
    await run_in_threadpool(
        _set_job_state,
        int(job["id"]),
        "succeeded",
        progress_current=1,
        progress_total=1,
        message="Repair completed",
        counters=counts,
    )
    return {"library_id": library_id, "job_id": job["id"], **counts}


@router.delete("/api/libraries/{library_id}")
async def api_unregister_library(
    library_id: int,
    confirm: bool = Query(False, description="Must be true; source files are never deleted"),
):
    """Unregister a library and delete only its catalog rows."""
    if not confirm:
        raise APIError(400, "confirmation_required", "Unregister requires explicit confirmation")
    active = await run_in_threadpool(_active_library_job, library_id, "scan", "repair")
    if active is not None:
        raise APIError(409, "library_busy", "Library scan or repair is active")
    if not await run_in_threadpool(unregister_library, library_id):
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return {"library_id": library_id, "unregistered": True, "source_files_deleted": False}


@router.get("/api/derivatives/status")
async def api_derivative_status(library_id: int = Query(..., ge=1)):
    """Return derivative warm coverage and global quota utilization."""
    try:
        return await run_in_threadpool(scheduler.library_status, library_id)
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc


@router.post("/api/derivatives/warm", status_code=202)
async def api_warm_derivatives(library_id: int = Query(..., ge=1)):
    """Queue default thumbnail and preview derivatives for a library."""
    if await run_in_threadpool(get_library, library_id) is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    result = await run_in_threadpool(scheduler.warm_library, library_id)
    return {"library_id": library_id, "state": "queued", **result}


@router.post("/api/derivatives/rebuild", status_code=202)
async def api_rebuild_derivatives(
    confirm: bool = Query(False, description="Must be true"),
):
    """Queue replacements for derivatives with changed source versions."""
    if not confirm:
        raise APIError(400, "confirmation_required", "Rebuild requires explicit confirmation")
    stale = await run_in_threadpool(scheduler.rebuild_stale)
    return {"stale_derivatives": stale, "state": "queued"}


@router.post("/api/derivatives/clear")
async def api_clear_derivatives(
    confirm: bool = Query(False, description="Must be true"),
):
    """Clear the derivative catalog and persisted derivative files."""
    if not confirm:
        raise APIError(400, "confirmation_required", "Clear requires explicit confirmation")
    return await run_in_threadpool(scheduler.clear_all)
