"""Public capabilities and durable derived-search-index lifecycle APIs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .errors import APIError, ErrorType
from .metadata_store import (
    SearchIndexJobConflict,
    create_search_index_job,
    get_library,
    get_search_index_job,
    list_libraries,
    list_search_index_states,
    request_search_index_job_cancel,
)
from .search_indexer import get_search_index_definition, list_search_index_definitions, search_index_worker
from .workflow_discovery import workflow_registry_capability

router = APIRouter()


class SearchIndexRebuildRequest(BaseModel):
    """Queue parameters for one derived index and registered library."""

    mode: Literal["missing", "full"] = "missing"
    library_id: int = Field(ge=1)


class SearchIndexCapabilityItem(BaseModel):
    """One code-owned derived-index capability."""

    index_name: str
    enabled: bool
    schema_version: int
    extractor_version: int
    required_mode: str


class SearchCapabilitiesResponse(BaseModel):
    """Canonical search feature and limit advertisement."""

    schema_version: int
    enabled_modes: list[str]
    supported_scopes: list[str]
    field_limits: dict[str, int]
    workflow_registry: dict
    raw_search: dict[str, int | bool]
    index_requirements: dict[str, list[str]]
    indexes: list[SearchIndexCapabilityItem]


class SearchIndexStateResponse(BaseModel):
    """Public state and usability for one library/index pair."""

    index_name: str
    library_id: int
    library_name: str
    state: str
    usable: bool
    enabled: bool
    schema_version: int
    extractor_version: int
    indexed_count: int
    target_count: int
    failed_count: int
    active_job_id: int | None = None
    started_at: float | None = None
    completed_at: float | None = None
    updated_at: float | None = None
    error_code: str | None = None
    error_summary: str | None = None
    warning: str | None = None


class SearchIndexJobResponse(BaseModel):
    """Public durable search-index job without its fencing token."""

    id: int
    index_name: str
    library_id: int
    mode: str
    state: str
    cursor_asset_id: int | None = None
    processed_count: int
    target_count: int
    failed_count: int
    requested_at: float
    started_at: float | None = None
    finished_at: float | None = None
    claimed_by: str | None = None
    lease_expires_at: float | None = None
    error_code: str | None = None
    error_summary: str | None = None


def _capability_index(definition) -> dict:  # noqa: ANN001
    return {
        "index_name": definition.name,
        "enabled": definition.enabled,
        "schema_version": definition.schema_version,
        "extractor_version": definition.extractor_version,
        "required_mode": definition.required_mode,
    }


@router.get("/api/search/capabilities")
def api_search_capabilities() -> SearchCapabilitiesResponse:
    """Advertise canonical modes, limits, fixed registries, and index requirements."""
    definitions = list_search_index_definitions()
    enabled_modes = ["lexical"]
    if any(item.enabled and item.required_mode == "workflow" for item in definitions):
        enabled_modes.append("workflow")
    if any(item.enabled and item.required_mode == "raw" for item in definitions):
        enabled_modes.append("raw")
    return SearchCapabilitiesResponse.model_validate(
        {
            "schema_version": 1,
            "enabled_modes": enabled_modes,
            "supported_scopes": ["folder", "library", "all"],
            "field_limits": {
                "text_max_chars": 512,
                "request_max_bytes": 32 * 1024,
                "limit_min": 1,
                "limit_max": 100,
                "prompt_groups_max": 8,
                "workflow_groups_max": 4,
                "workflow_predicates_per_group_max": 8,
            },
            "workflow_registry": workflow_registry_capability(),
            "raw_search": {
                "enabled": "raw" in enabled_modes,
                "query_min_chars": 3,
                "query_max_chars": 128,
                "limit_max": 50,
            },
            "index_requirements": {
                "lexical": [],
                "prompt_groups": ["prompt_values"],
                "workflow": ["workflow_properties"],
                "raw": ["workflow_raw"],
            },
            "indexes": [_capability_index(item) for item in definitions],
        }
    )


@router.get("/api/search/indexes")
def api_search_indexes(
    library_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[SearchIndexStateResponse]:
    """Return persisted or initial per-library state for every code-owned index."""
    if library_id is not None:
        library = get_library(library_id)
        if library is None:
            raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
        libraries = [library]
    else:
        libraries = list_libraries()
    persisted = {
        (int(item["library_id"]), str(item["index_name"])): item
        for item in list_search_index_states(library_id=library_id)
    }
    result: list[dict] = []
    for library in libraries:
        for definition in list_search_index_definitions():
            key = (int(library["id"]), definition.name)
            state = persisted.get(key)
            if state is None:
                state = {
                    "index_name": definition.name,
                    "library_id": int(library["id"]),
                    "state": "pending" if definition.enabled else "disabled",
                    "schema_version": definition.schema_version,
                    "extractor_version": definition.extractor_version,
                    "indexed_count": 0,
                    "target_count": 0,
                    "failed_count": 0,
                    "active_job_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "updated_at": None,
                    "error_code": None,
                    "error_summary": None,
                    "usable": False,
                }
            else:
                state = dict(state)
                version_mismatch = (
                    int(state["schema_version"]) != definition.schema_version
                    or int(state["extractor_version"]) != definition.extractor_version
                )
                if not definition.enabled:
                    state["state"] = "disabled"
                    state["usable"] = False
                elif version_mismatch:
                    state["state"] = "degraded" if int(state["indexed_count"]) > 0 else "pending"
                    state["usable"] = int(state["indexed_count"]) > 0
                    state["warning"] = "version_mismatch"
                elif state["state"] == "building" and bool(state["usable"]):
                    state["warning"] = "rebuild_in_progress_using_previous_index"
            state["enabled"] = definition.enabled
            state["library_name"] = str(library["name"])
            result.append(state)
    return [SearchIndexStateResponse.model_validate(item) for item in result]


@router.get("/api/search/index-jobs/{job_id}")
def api_search_index_job(job_id: int) -> SearchIndexJobResponse:
    """Return one durable search-index job."""
    job = get_search_index_job(job_id)
    if job is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Search index job not found")
    return SearchIndexJobResponse.model_validate(job)


@router.post("/api/search/indexes/{index_name}/rebuild", status_code=202)
def api_rebuild_search_index(index_name: str, payload: SearchIndexRebuildRequest) -> SearchIndexJobResponse:
    """Queue a missing/full durable rebuild for one enabled fixed index."""
    definition = get_search_index_definition(index_name)
    if definition is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Search index not found")
    if not definition.enabled:
        raise APIError(409, ErrorType.FEATURE_DISABLED, "Search index feature is disabled")
    try:
        job = create_search_index_job(
            index_name,
            payload.library_id,
            mode=payload.mode,
            schema_version=definition.schema_version,
            extractor_version=definition.extractor_version,
        )
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc
    except SearchIndexJobConflict as exc:
        raise APIError(
            409,
            ErrorType.BAD_REQUEST,
            "A rebuild is already active for this library and index",
            extra={"active_job_id": int(exc.args[0])},
        ) from exc
    search_index_worker.wake()
    return SearchIndexJobResponse.model_validate(job)


@router.post("/api/search/index-jobs/{job_id}/cancel")
def api_cancel_search_index_job(job_id: int) -> SearchIndexJobResponse:
    """Idempotently request or complete durable job cancellation."""
    job = request_search_index_job_cancel(job_id)
    if job is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Search index job not found")
    search_index_worker.wake()
    return SearchIndexJobResponse.model_validate(job)
