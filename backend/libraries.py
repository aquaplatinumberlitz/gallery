"""Registered library management and progressive discovery endpoints."""

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from wcmatch import glob

from .derivative_scheduler import scheduler
from .errors import APIError, ErrorType
from .indexer import rebuild_index_scope
from .metadata_store import (
    LibraryOverlapError,
    create_library,
    get_library,
    get_library_progress,
    list_libraries,
    repair_library_assets,
    unregister_library,
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


def _discover_library(library_id: int, import_paths: list[str]) -> None:
    try:
        update_library_state(library_id, "indexing")
        for import_path in import_paths:
            rebuild_index_scope(import_path)
        update_library_state(library_id, "ready", scan_completed=True)
    except Exception as exc:  # noqa: BLE001
        update_library_state(library_id, "error", last_error=str(exc), scan_completed=True)


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
    await run_in_threadpool(update_library_state, library_id, "discovering")
    background_tasks.add_task(_discover_library, library_id, import_paths)
    return {"library_id": library_id, "state": "discovering"}


@router.post("/api/libraries/{library_id}/repair")
async def api_repair_library(library_id: int):
    """Reconcile a registered library's asset catalog with its filesystem."""
    library = await run_in_threadpool(get_library, library_id)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    if any(not Path(item["path"]).is_dir() for item in library["import_paths"]):
        await run_in_threadpool(update_library_state, library_id, "offline", last_error="Root path is offline")
        raise APIError(409, "library_offline", "One or more library import paths are offline")
    counts = await run_in_threadpool(repair_library_assets, library_id)
    return {"library_id": library_id, **counts}


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
