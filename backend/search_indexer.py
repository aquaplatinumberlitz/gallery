"""Single-writer durable search-index worker and code-owned index registry."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from .config import (
    GALLERY_RELATED_VISUAL_ENABLED,
    GALLERY_SEARCH_INDEX_BATCH_SIZE,
    GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS,
    GALLERY_SEARCH_INDEX_POLL_SECONDS,
    GALLERY_SEARCH_WORKFLOW_RAW_ENABLED,
)
from .errors import APIError, ErrorType
from .generation_signatures import (
    GENERATION_SIGNATURE_EXTRACTOR_VERSION,
    extract_generation_signature,
    persist_generation_signature,
)
from .metadata_store.library_store import list_libraries
from .metadata_store.search_index_store import (
    SearchIndexClaimLost,
    claim_next_search_index_job,
    finish_search_index_job,
    list_search_index_asset_batch,
    list_search_index_states,
    record_search_index_extraction,
    recover_search_index_jobs,
    renew_search_index_job_lease,
    search_index_job_control_state,
)
from .prompt_discovery import extract_prompt_discovery, persist_prompt_discovery
from .visual_fingerprints import (
    VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    extract_visual_fingerprint,
    persist_visual_fingerprint,
)
from .workflow_discovery import extract_workflow_properties, persist_workflow_properties
from .workflow_raw_search import extract_raw_workflow, persist_raw_workflow

LOGGER = logging.getLogger(__name__)
SearchExtractionStatus = Literal["ready", "not_applicable", "skipped", "failed"]


@dataclass(frozen=True)
class SearchExtractionResult:
    """One extractor result persisted atomically with its extraction record."""

    status: SearchExtractionStatus
    payload: Any = None
    error_code: str | None = None


@dataclass(frozen=True)
class SearchIndexDefinition:
    """Code-owned derived-index implementation and capability metadata."""

    name: str
    schema_version: int
    extractor_version: int
    enabled: bool
    required_mode: Literal["prompt_groups", "workflow", "raw", "related", "visual"]
    extractor: Any = None
    persist: Any = None


def _noop_persist(_conn, _asset, _payload) -> None:  # noqa: ANN001
    return None


_DEFINITIONS: dict[str, SearchIndexDefinition] = {
    "generation_signatures": SearchIndexDefinition(
        name="generation_signatures",
        schema_version=1,
        extractor_version=GENERATION_SIGNATURE_EXTRACTOR_VERSION,
        enabled=True,
        required_mode="related",
        extractor=extract_generation_signature,
        persist=persist_generation_signature,
    ),
    "visual_fingerprints": SearchIndexDefinition(
        name="visual_fingerprints",
        schema_version=1,
        extractor_version=VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
        enabled=GALLERY_RELATED_VISUAL_ENABLED,
        required_mode="visual",
        extractor=extract_visual_fingerprint,
        persist=persist_visual_fingerprint,
    ),
    "prompt_values": SearchIndexDefinition(
        name="prompt_values",
        schema_version=1,
        extractor_version=1,
        enabled=True,
        required_mode="prompt_groups",
        extractor=extract_prompt_discovery,
        persist=persist_prompt_discovery,
    ),
    "workflow_properties": SearchIndexDefinition(
        name="workflow_properties",
        schema_version=1,
        extractor_version=1,
        enabled=True,
        required_mode="workflow",
        extractor=extract_workflow_properties,
        persist=persist_workflow_properties,
    ),
    "workflow_raw": SearchIndexDefinition(
        name="workflow_raw",
        schema_version=1,
        extractor_version=1,
        enabled=GALLERY_SEARCH_WORKFLOW_RAW_ENABLED,
        required_mode="raw",
        extractor=extract_raw_workflow,
        persist=persist_raw_workflow,
    ),
}


def register_search_index_definition(definition: SearchIndexDefinition) -> None:
    """Register or replace one fixed code-owned index implementation."""
    if not definition.name or definition.schema_version < 1 or definition.extractor_version < 1:
        raise ValueError("Invalid search index definition")
    if definition.enabled and (definition.extractor is None or definition.persist is None):
        raise ValueError("Enabled search index definitions require extractor and persist callbacks")
    _DEFINITIONS[definition.name] = definition


def get_search_index_definition(index_name: str) -> SearchIndexDefinition | None:
    """Return one registered definition."""
    return _DEFINITIONS.get(index_name)


def list_search_index_definitions() -> list[SearchIndexDefinition]:
    """Return definitions in stable name order."""
    return [_DEFINITIONS[name] for name in sorted(_DEFINITIONS)]


def require_search_index_mode(required_mode: str, *, library_id: int | None) -> None:
    """Enforce feature enablement and usable state for one canonical request mode."""
    definition = next((item for item in _DEFINITIONS.values() if item.required_mode == required_mode), None)
    if definition is None or not definition.enabled:
        raise APIError(409, ErrorType.FEATURE_DISABLED, "Search feature is disabled")
    library_ids = [library_id] if library_id is not None else [int(item["id"]) for item in list_libraries()]
    states = {
        (int(item["library_id"]), str(item["index_name"])): item
        for item in list_search_index_states(library_id=library_id)
    }
    unusable = []
    for requested_library_id in library_ids:
        state = states.get((requested_library_id, definition.name))
        if (
            state is None
            or not bool(state["usable"])
            or int(state["schema_version"]) != definition.schema_version
            or int(state["extractor_version"]) != definition.extractor_version
        ):
            unusable.append(requested_library_id)
    if unusable:
        raise APIError(
            503,
            ErrorType.SEARCH_INDEX_NOT_READY,
            "Required search index is not ready",
            extra={"index_name": definition.name, "library_ids": unusable},
            headers={"Retry-After": "5"},
        )


def _failed_result(code: str = "extraction_failed") -> SearchExtractionResult:
    return SearchExtractionResult(status="failed", error_code=code)


def run_search_index_once(*, worker_id: str | None = None) -> bool:
    """Claim and fully process at most one durable search-index job."""
    worker = worker_id or f"search-index-{uuid.uuid4().hex[:12]}"
    job = claim_next_search_index_job(worker, lease_seconds=GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS)
    if job is None:
        return False
    job_id = int(job["id"])
    claim_token = str(job["claim_token"])
    definition = get_search_index_definition(str(job["index_name"]))
    if definition is None or not definition.enabled or definition.extractor is None or definition.persist is None:
        finish_search_index_job(
            job_id,
            claim_token,
            "failed",
            error_code="feature_disabled",
            error_summary="Search index feature is disabled",
        )
        return True

    try:
        repair_pass_complete = False
        while True:
            control_state = search_index_job_control_state(job_id, claim_token)
            if control_state is None:
                raise SearchIndexClaimLost(job_id)
            if control_state == "cancel_requested":
                finish_search_index_job(job_id, claim_token, "cancelled")
                return True
            if not renew_search_index_job_lease(
                job_id,
                claim_token,
                lease_seconds=GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS,
            ):
                raise SearchIndexClaimLost(job_id)
            batch = list_search_index_asset_batch(
                job,
                extractor_version=definition.extractor_version,
                limit=GALLERY_SEARCH_INDEX_BATCH_SIZE,
            )
            if not batch:
                if definition.name in {"generation_signatures", "visual_fingerprints"} and not repair_pass_complete:
                    repair_pass_complete = True
                    job["mode"] = "missing"
                    job["cursor_asset_id"] = 0
                    continue
                finish_search_index_job(job_id, claim_token, "succeeded")
                return True

            for asset in batch:
                if search_index_job_control_state(job_id, claim_token) == "cancel_requested":
                    finish_search_index_job(job_id, claim_token, "cancelled")
                    return True
                try:
                    result = definition.extractor(asset)
                    if not isinstance(result, SearchExtractionResult):
                        result = _failed_result("invalid_extractor_result")
                except Exception:  # noqa: BLE001
                    LOGGER.exception(
                        "Search index extraction failed for index=%s asset_id=%s", definition.name, asset["id"]
                    )
                    result = _failed_result()
                try:
                    record_search_index_extraction(
                        job_id,
                        claim_token,
                        asset,
                        index_name=definition.name,
                        extractor_version=definition.extractor_version,
                        status=result.status,
                        error_code=result.error_code,
                        payload=result.payload,
                        persist=definition.persist,
                        lease_seconds=GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS,
                    )
                except SearchIndexClaimLost:
                    raise
                except Exception:  # noqa: BLE001
                    LOGGER.exception(
                        "Search index persistence failed for index=%s asset_id=%s", definition.name, asset["id"]
                    )
                    record_search_index_extraction(
                        job_id,
                        claim_token,
                        asset,
                        index_name=definition.name,
                        extractor_version=definition.extractor_version,
                        status="failed",
                        error_code="persistence_failed",
                        payload=None,
                        persist=_noop_persist,
                        lease_seconds=GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS,
                    )
                job["cursor_asset_id"] = int(asset["id"])
    except SearchIndexClaimLost:
        LOGGER.warning("Search index job %s lost its claim", job_id)
        return True
    except Exception:  # noqa: BLE001
        LOGGER.exception("Search index job %s failed", job_id)
        finish_search_index_job(
            job_id,
            claim_token,
            "failed",
            error_code="worker_failed",
            error_summary="Search index worker failed",
        )
        return True


class SearchIndexWorker:
    """One supervised daemon thread that serializes SQLite index writers."""

    def __init__(self) -> None:
        """Initialize stopped worker state and one stable owner ID."""
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lock = threading.Lock()
        self._worker_id = f"search-index-{uuid.uuid4().hex[:12]}"

    def start(self) -> None:
        """Recover interrupted work and start the single writer if needed."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            recover_search_index_jobs()
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(target=self._run, name="search-index-writer", daemon=True)
            self._thread.start()

    def stop(self) -> bool:
        """Stop and join the writer thread."""
        with self._lock:
            thread = self._thread
            if thread is None:
                return True
            self._stop_event.set()
            self._wake_event.set()
        thread.join(timeout=30)
        with self._lock:
            stopped = not thread.is_alive()
            if stopped:
                self._thread = None
        return stopped

    def wake(self) -> None:
        """Wake the writer after enqueue or cancellation."""
        self._wake_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            worked = run_search_index_once(worker_id=self._worker_id)
            if worked:
                continue
            self._wake_event.wait(GALLERY_SEARCH_INDEX_POLL_SECONDS)
            self._wake_event.clear()


search_index_worker = SearchIndexWorker()
