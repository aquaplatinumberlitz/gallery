"""Durable catalog scan coordinator and worker."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .catalog_maintenance_gate import release_maintenance_gate, try_acquire_maintenance_gate
from .config import (
    CATALOG_JOB_LEASE_SECONDS,
    CATALOG_LEASE_HEARTBEAT_SECONDS,
    CATALOG_SHUTDOWN_TIMEOUT_SECONDS,
    DERIVATIVE_RECONCILE_ENABLED,
    GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS,
    GALLERY_CATALOG_SERVICE_ENABLED,
    GALLERY_CATALOG_WORKERS,
)
from .indexer import dispatch_metadata_index_paths, rebuild_index_scope
from .library_events import event_payload, publish
from .metadata_store import (
    CatalogJobClaimLost,
    CatalogMaintenanceBusy,
    activate_rebuild_staging,
    assert_catalog_job_claim,
    catalog_path_contains,
    claim_next_catalog_job,
    create_or_coalesce_catalog_job,
    delete_rebuild_staging,
    delete_rebuild_staging_for_lost_claim,
    enqueue_startup_catalog_scans,
    enumerate_to_rebuild_staging,
    get_job,
    get_library,
    get_library_for_path,
    list_libraries,
    reconcile_library_assets,
    recover_stale_jobs,
    renew_catalog_job_lease,
    update_job_state,
)

LOGGER = logging.getLogger(__name__)

_worker_threads: list[threading.Thread] = []
_supervisor_thread: threading.Thread | None = None
_service_lock = threading.RLock()
_wake_event = threading.Event()
_stop_event = threading.Event()
_shutdown_incomplete = False
_last_supervisor_check_at: float | None = None
_last_supervisor_recovered_jobs = 0
_supervisor_failures = 0
_SUPERVISOR_INTERVAL_SECONDS = 1.0
_active_claims_lock = threading.RLock()
_active_catalog_claims: set[tuple[int, str]] = set()


TRIGGER_PRIORITIES = {
    "initial": 100,
    "manual": 100,
    "watcher": 50,
    "scheduled": 10,
    "startup": 10,
}


def _emit_job(job: dict[str, Any], event_type: str = "job.updated") -> None:
    publish(event_payload(event_type, job))
    if job["library_id"] is not None:
        publish(event_payload("library.progress", job))


def _transition_job(
    job_id: int,
    state: str,
    *,
    claim_token: str | None = None,
    **changes: Any,
) -> dict[str, Any]:
    job = update_job_state(
        job_id,
        state,
        claim_token=claim_token,
        lease_seconds=CATALOG_JOB_LEASE_SECONDS,
        **changes,
    )
    if job is None:
        if claim_token is not None:
            raise CatalogJobClaimLost(f"Catalog job {job_id} claim was lost")
        raise RuntimeError(f"Catalog job {job_id} disappeared")
    event_type = "job.updated"
    if state == "succeeded":
        event_type = "job.completed"
    elif state == "failed":
        event_type = "job.failed"
    elif state == "cancelled":
        event_type = "job.cancelled"
    _emit_job(job, event_type)
    if job.get("type") in {"scan", "rebuild"}:
        from .metadata_store.job_store import list_parent_aggregate_job_ids, update_parent_aggregate_job

        for parent_job_id in list_parent_aggregate_job_ids(int(job["id"])):
            parent = update_parent_aggregate_job(parent_job_id)
            if parent is None:
                continue
            parent_event = (
                "job.completed"
                if parent["state"] == "succeeded"
                else "job.failed"
                if parent["state"] == "failed"
                else "job.updated"
            )
            _emit_job(parent, parent_event)
    return job


def _event_type_for_state(state: str) -> str:
    if state == "succeeded":
        return "job.completed"
    if state == "failed":
        return "job.failed"
    if state == "cancelled":
        return "job.cancelled"
    return "job.updated"


def _emit_recovered_jobs(jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        _emit_job(job, event_type=_event_type_for_state(str(job["state"])))


def _prune_worker_threads_locked() -> tuple[list[threading.Thread], set[str]]:
    alive = [thread for thread in _worker_threads if thread.is_alive()]
    dead_worker_ids = {
        str(thread._gallery_worker_id)  # type: ignore[attr-defined]
        for thread in _worker_threads
        if not thread.is_alive() and getattr(thread, "_gallery_worker_id", None)
    }
    _worker_threads[:] = alive
    return alive, dead_worker_ids


def _spawn_missing_workers_locked() -> None:
    global _shutdown_incomplete
    if _stop_event.is_set() and any(thread.is_alive() for thread in _worker_threads):
        return
    missing = max(0, GALLERY_CATALOG_WORKERS - len(_worker_threads))
    if missing == 0:
        return
    _stop_event.clear()
    _shutdown_incomplete = False
    start_index = len(_worker_threads)
    for offset in range(missing):
        thread = threading.Thread(
            target=_worker_loop,
            name=f"gallery-catalog-worker-{start_index + offset + 1}",
            daemon=True,
        )
        thread._gallery_worker_id = f"catalog-{id(thread):x}-{time.time_ns():x}"  # type: ignore[attr-defined]
        _worker_threads.append(thread)
        thread.start()


def _spawn_supervisor_locked() -> None:
    global _supervisor_thread
    if _supervisor_thread is not None and _supervisor_thread.is_alive():
        return
    _supervisor_thread = threading.Thread(
        target=_supervisor_loop,
        name="gallery-catalog-supervisor",
        daemon=True,
    )
    _supervisor_thread.start()


def notify_workers() -> None:
    """Wake sleeping catalog workers after durable queue changes."""
    _wake_event.set()


def queue_scan(
    library_id: int,
    *,
    trigger: str,
    scope_path: str | Path | None = None,
    parent_job_id: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create/coalesce a durable scan job and wake the worker."""
    if not try_acquire_maintenance_gate():
        raise CatalogMaintenanceBusy()
    try:
        if trigger not in TRIGGER_PRIORITIES:
            raise ValueError(f"Unsupported scan trigger: {trigger}")
        job, created = create_or_coalesce_catalog_job(
            library_id,
            operation="scan",
            trigger=trigger,
            scope_path=scope_path,
            priority=TRIGGER_PRIORITIES[trigger],
            parent_job_id=parent_job_id,
            message=f"{trigger.capitalize()} update queued",
        )
        _emit_job(job)
        notify_workers()
        return job, created
    finally:
        release_maintenance_gate()


def queue_rebuild(
    library_id: int,
    *,
    scope_path: str | Path | None = None,
    parent_job_id: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create a durable rebuild job, cancelling queued scans it covers.

    Raises ``CatalogJobConflict`` when catalog work is already running or
    another rebuild is queued/running for a covering scope.
    """
    if not try_acquire_maintenance_gate():
        raise CatalogMaintenanceBusy()
    try:
        job, created = create_or_coalesce_catalog_job(
            library_id,
            operation="rebuild",
            trigger="manual",
            scope_path=scope_path,
            priority=TRIGGER_PRIORITIES["manual"],
            parent_job_id=parent_job_id,
            message="Rebuild queued",
        )
        _emit_job(job)
        notify_workers()
        return job, created
    finally:
        release_maintenance_gate()


def queue_initial_scan_job(job_id: int) -> None:
    """Wake the worker for an initial scan row created inside another transaction."""
    if not try_acquire_maintenance_gate():
        LOGGER.debug("Maintenance active, deferring initial scan")
        return
    try:
        job = get_job(job_id)
        if job is not None:
            _emit_job(job)
        notify_workers()
    finally:
        release_maintenance_gate()


def queue_startup_scans() -> list[dict[str, Any]]:
    """Queue startup catch-up scans for all registered libraries."""
    if not try_acquire_maintenance_gate():
        LOGGER.debug("Maintenance active, deferring startup scans")
        return []
    try:
        jobs = enqueue_startup_catalog_scans(priority=TRIGGER_PRIORITIES["startup"])
        for job in jobs:
            _emit_job(job)
        notify_workers()
        return jobs
    finally:
        release_maintenance_gate()


def queue_watcher_scan(scope_path: str | Path) -> dict[str, Any] | None:
    """Queue a watcher-triggered scan for the library owning scope_path."""
    library = get_library_for_path(scope_path)
    if library is None:
        return None
    try:
        job, _created = queue_scan(int(library["id"]), trigger="watcher", scope_path=scope_path)
    except CatalogMaintenanceBusy:
        LOGGER.debug("Skipping watcher scan for %s while catalog maintenance is active", scope_path)
        return None
    return job


def queue_scheduled_scans() -> list[dict[str, Any]]:
    """Queue one scheduled whole-library scan per registered library."""
    jobs: list[dict[str, Any]] = []
    for library in list_libraries():
        try:
            job, _created = queue_scan(int(library["id"]), trigger="scheduled")
        except CatalogMaintenanceBusy:
            LOGGER.debug("Skipping scheduled scan for library %s while catalog maintenance is active", library["id"])
            continue
        jobs.append(job)
    return jobs


def _scan_paths_for_job(job: dict[str, Any]) -> tuple[int, list[str]]:
    library_id = int(job["library_id"])
    library = get_library(library_id)
    if library is None:
        raise KeyError(library_id)
    import_paths = [str(item["path"]) for item in library["import_paths"]]
    scope_path = job.get("scope_path")
    if scope_path is None:
        return library_id, import_paths
    if not any(catalog_path_contains(root, scope_path) for root in import_paths):
        raise ValueError("Update scope is outside this library's import paths")
    return library_id, [str(Path(scope_path).resolve())]


def _reconcile_derivatives_after_catalog_commit(job: dict[str, Any], library_id: int) -> None:
    """Apply the scheduler policy only after successful catalog activation."""
    if not DERIVATIVE_RECONCILE_ENABLED:
        return
    from .derivative_scheduler import scheduler

    try:
        scope_path = job.get("scope_path")
        scheduler.reconcile_desired_derivatives(
            **({"scope_path": scope_path} if scope_path else {"library_id": library_id}),
            reason=f"catalog_{job['type']}",
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("Derivative reconciliation failed after catalog job %s", job["id"])


def execute_scan_job(job: dict[str, Any]) -> bool:
    """Run one claimed scan job through the catalog-owned pipeline."""
    job_id = int(job["id"])
    library_id = int(job["library_id"])
    claim_token = str(job["claim_token"]) if job.get("claim_token") else None
    try:
        if claim_token is None:
            raise CatalogJobClaimLost(f"Catalog job {job_id} has no claim token")
        library_id, scan_paths = _scan_paths_for_job(job)
        online_paths = [p for p in scan_paths if Path(p).is_dir()]
        offline_paths = [p for p in scan_paths if not Path(p).is_dir()]
        for offline_path in offline_paths:
            reconcile_library_assets(
                library_id,
                set(),
                scope_path=offline_path,
                claim_job_id=job_id,
                claim_token=claim_token,
                claim_lease_seconds=CATALOG_JOB_LEASE_SECONDS,
            )
        if not online_paths:
            _transition_job(
                job_id,
                "failed",
                claim_token=claim_token,
                message="Update failed",
                error="All update paths are offline",
                library_state="offline",
                library_last_error="All import paths are offline",
            )
            return False
        counters = {
            "indexed": 0,
            "reconciled": 0,
            "queued": 0,
            "coalesced": 0,
            "skipped": 0,
            "failed": 0,
        }
        _transition_job(
            job_id,
            "running",
            claim_token=claim_token,
            progress_current=0,
            progress_total=len(online_paths),
            message="Updating library",
            counters=counters,
            library_state="degraded" if offline_paths else "indexing",
            library_last_error=f"{len(offline_paths)} import path(s) offline" if offline_paths else None,
        )
        for index, scan_path in enumerate(online_paths, start=1):
            result = rebuild_index_scope(
                scan_path,
                claim_job_id=job_id,
                claim_token=claim_token,
                claim_lease_seconds=CATALOG_JOB_LEASE_SECONDS,
            )
            counters["indexed"] += int(result.get("indexed", 0))
            counters["reconciled"] += int(result.get("reconciled", 0))
            for key in ("queued", "coalesced", "skipped", "failed"):
                counters[key] += int(result.get("metadata", {}).get(key, 0))
            _transition_job(
                job_id,
                "running",
                claim_token=claim_token,
                progress_current=index,
                progress_total=len(online_paths),
                message=f"Updated {index} of {len(online_paths)} update scopes",
                counters=counters,
            )
        scan_completed = job.get("scope_path") is None
        if offline_paths:
            success_message = "Update completed with offline paths"
        elif scan_completed:
            success_message = "Update completed"
        else:
            success_message = "Update completed"
        _transition_job(
            job_id,
            "succeeded",
            claim_token=claim_token,
            progress_current=len(online_paths),
            progress_total=len(online_paths),
            message=success_message,
            counters=counters,
            library_state="degraded" if offline_paths else "ready" if scan_completed else "indexing",
            library_last_error=f"{len(offline_paths)} import path(s) offline" if offline_paths else None,
            library_scan_completed=scan_completed,
        )
        _reconcile_derivatives_after_catalog_commit(job, library_id)
        return True
    except CatalogJobClaimLost:
        LOGGER.warning("Catalog scan job %s stopped after losing its claim", job_id)
        return False
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Catalog scan job %s failed: %s", job_id, exc)
        try:
            _transition_job(
                job_id,
                "failed",
                claim_token=claim_token,
                message="Update failed",
                error=str(exc),
                library_state="error",
                library_last_error=str(exc),
                library_scan_completed=job.get("scope_path") is None,
            )
        except CatalogJobClaimLost:
            LOGGER.warning("Catalog scan job %s failure ignored after claim loss", job_id)
            return False
        return False


def execute_rebuild_job(job: dict[str, Any]) -> bool:
    """Run one claimed rebuild job through staging and atomic activation.

    Enumeration writes only to ``catalog_rebuild_entries`` so browse keeps
    serving the canonical generation. On success, one short activation
    transaction merges staged rows, reconciles missing rows, resets affected
    metadata state, and removes staging data. On failure the canonical
    generation is untouched and orphaned staging rows are cleaned up.
    """
    job_id = int(job["id"])
    library_id = int(job["library_id"])
    claim_token = str(job["claim_token"]) if job.get("claim_token") else None
    try:
        if claim_token is None:
            raise CatalogJobClaimLost(f"Catalog job {job_id} has no claim token")
        library_id, scan_paths = _scan_paths_for_job(job)
        online_paths = [p for p in scan_paths if Path(p).is_dir()]
        offline_paths = [p for p in scan_paths if not Path(p).is_dir()]
        if not online_paths:
            _transition_job(
                job_id,
                "failed",
                claim_token=claim_token,
                message="Rebuild failed",
                error="All rebuild paths are offline",
                library_state="offline",
                library_last_error="All import paths are offline",
            )
            return False
        counters = {
            "discovered": 0,
            "folders": 0,
            "assets": 0,
            "created": 0,
            "updated": 0,
            "offline": 0,
            "metadata_reset": 0,
            "metadata_queued": 0,
            "failed": 0,
        }
        _transition_job(
            job_id,
            "running",
            claim_token=claim_token,
            progress_current=0,
            progress_total=len(online_paths),
            message="Rebuild enumerating",
            counters=counters,
            library_state="degraded" if offline_paths else "indexing",
            library_last_error=f"{len(offline_paths)} import path(s) offline" if offline_paths else None,
        )
        discovery, asset_paths = enumerate_to_rebuild_staging(
            job_id,
            library_id,
            online_paths,
            claim_token,
            CATALOG_JOB_LEASE_SECONDS,
        )
        counters["discovered"] = int(discovery["discovered"])
        counters["folders"] = int(discovery["folders"])
        counters["assets"] = int(discovery["assets"])
        _transition_job(
            job_id,
            "running",
            claim_token=claim_token,
            progress_current=len(online_paths),
            progress_total=len(online_paths),
            message="Rebuild activating",
            counters=counters,
        )
        activation = activate_rebuild_staging(
            job_id,
            library_id,
            job.get("scope_path"),
            claim_token,
            CATALOG_JOB_LEASE_SECONDS,
        )
        counters["created"] = int(activation["created"])
        counters["updated"] = int(activation["updated"])
        counters["offline"] = int(activation["offline"])
        counters["metadata_reset"] = int(activation["metadata_reset"])
        enqueued_total = 0
        failed_total = 0
        if online_paths:
            by_root: dict[str, list[str]] = defaultdict(list)
            for asset_path in asset_paths:
                matched_root = next(
                    (root for root in online_paths if catalog_path_contains(root, asset_path)),
                    online_paths[0],
                )
                by_root[matched_root].append(asset_path)
            for root, scoped_paths in by_root.items():
                assert_catalog_job_claim(job_id, claim_token, library_id=library_id)
                result = dispatch_metadata_index_paths(
                    scoped_paths,
                    root,
                    catalog_claim_job_id=job_id,
                    catalog_claim_token=claim_token,
                    catalog_claim_lease_seconds=CATALOG_JOB_LEASE_SECONDS,
                )
                enqueued_total += int(result.get("queued", 0))
                failed_total += int(result.get("failed", 0))
        counters["metadata_queued"] = enqueued_total
        counters["failed"] = failed_total
        scan_completed = job.get("scope_path") is None
        if offline_paths:
            success_message = "Rebuild completed with offline paths"
        elif scan_completed:
            success_message = "Rebuild completed"
        else:
            success_message = "Rebuild completed"
        _transition_job(
            job_id,
            "succeeded",
            claim_token=claim_token,
            progress_current=len(online_paths),
            progress_total=len(online_paths),
            message=success_message,
            counters=counters,
            library_state="degraded" if offline_paths else "ready" if scan_completed else "indexing",
            library_last_error=f"{len(offline_paths)} import path(s) offline" if offline_paths else None,
            library_scan_completed=scan_completed,
        )
        _reconcile_derivatives_after_catalog_commit(job, library_id)
        return True
    except CatalogJobClaimLost:
        LOGGER.warning("Catalog rebuild job %s stopped after losing its claim", job_id)
        try:
            delete_rebuild_staging_for_lost_claim(job_id, claim_token)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to clean stale staging rows for rebuild job %s", job_id)
        return False
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Catalog rebuild job %s failed: %s", job_id, exc)
        try:
            delete_rebuild_staging(job_id, claim_token=claim_token)
        except CatalogJobClaimLost:
            try:
                delete_rebuild_staging_for_lost_claim(job_id, claim_token)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to clean stale staging rows for rebuild job %s", job_id)
            LOGGER.warning("Catalog rebuild job %s failure ignored after claim loss", job_id)
            return False
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to clean staging rows for rebuild job %s", job_id)
        try:
            _transition_job(
                job_id,
                "failed",
                claim_token=claim_token,
                message="Rebuild failed; previous catalog remains active",
                error=str(exc),
                library_state="error",
                library_last_error=str(exc),
                library_scan_completed=job.get("scope_path") is None,
            )
        except CatalogJobClaimLost:
            LOGGER.warning("Catalog rebuild job %s failure ignored after claim loss", job_id)
            return False
        return False


def run_once() -> bool:
    """Claim and execute one queued catalog job. Returns True when work ran."""
    worker_id = str(getattr(threading.current_thread(), "_gallery_worker_id", threading.current_thread().name))
    job = claim_next_catalog_job(
        max_queue_wait_seconds=GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS,
        worker_id=worker_id,
        lease_seconds=CATALOG_JOB_LEASE_SECONDS,
    )
    if job is None:
        return False
    _emit_job(job)
    heartbeat = _CatalogLeaseHeartbeat(int(job["id"]), str(job["claim_token"]))
    heartbeat.start()
    try:
        if job["type"] == "scan":
            execute_scan_job(job)
        elif job["type"] == "rebuild":
            execute_rebuild_job(job)
        else:
            _transition_job(
                int(job["id"]),
                "failed",
                claim_token=str(job["claim_token"]),
                message="Unsupported catalog operation",
                error="Unsupported",
            )
    finally:
        heartbeat.stop()
    return True


class _CatalogLeaseHeartbeat:
    """Renew one catalog claim until the worker reaches a terminal write."""

    def __init__(self, job_id: int, claim_token: str) -> None:
        self._job_id = job_id
        self._claim_token = claim_token
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        claim = (self._job_id, self._claim_token)
        with _active_claims_lock:
            _active_catalog_claims.add(claim)
        try:
            self._thread = threading.Thread(
                target=self._run,
                name=f"gallery-catalog-heartbeat-{self._job_id}",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            with _active_claims_lock:
                _active_catalog_claims.discard(claim)
            raise

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, CATALOG_LEASE_HEARTBEAT_SECONDS + 1.0))
        with _active_claims_lock:
            _active_catalog_claims.discard((self._job_id, self._claim_token))

    def _run(self) -> None:
        while not self._stop.wait(CATALOG_LEASE_HEARTBEAT_SECONDS):
            try:
                if not renew_catalog_job_lease(
                    self._job_id,
                    self._claim_token,
                    lease_seconds=CATALOG_JOB_LEASE_SECONDS,
                ):
                    return
            except Exception:  # noqa: BLE001
                LOGGER.exception("Catalog lease heartbeat failed for job %s", self._job_id)


def _worker_loop() -> None:
    while not _stop_event.is_set():
        ran = False
        try:
            ran = run_once()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog worker iteration failed: %s", exc)
        if ran:
            continue
        _wake_event.wait(0.5)
        _wake_event.clear()


def _supervisor_loop() -> None:
    global _last_supervisor_check_at, _last_supervisor_recovered_jobs, _supervisor_failures
    while not _stop_event.wait(_SUPERVISOR_INTERVAL_SECONDS):
        try:
            result = ensure_running(service_enabled=GALLERY_CATALOG_SERVICE_ENABLED)
            _last_supervisor_check_at = time.time()
            _last_supervisor_recovered_jobs = int(result["recovered_jobs"])
        except Exception:  # noqa: BLE001
            _supervisor_failures += 1
            LOGGER.exception("Catalog supervisor iteration failed")


def start() -> None:
    """Start bounded in-process catalog workers."""
    with _service_lock:
        alive, _dead_worker_ids = _prune_worker_threads_locked()
        if _stop_event.is_set() and alive:
            LOGGER.warning("Catalog worker restart deferred until incomplete shutdown finishes")
            return
        if alive:
            _spawn_missing_workers_locked()
            _spawn_supervisor_locked()
            return
        # Recover orphaned running jobs before spawning workers
        recovered_jobs = recover_stale_jobs()
        for job in recovered_jobs:
            LOGGER.warning("Recovered orphaned catalog job %s after server restart", job["id"])
        _emit_recovered_jobs(recovered_jobs)
        _spawn_missing_workers_locked()
        _spawn_supervisor_locked()
        notify_workers()


def ensure_running(*, service_enabled: bool = GALLERY_CATALOG_SERVICE_ENABLED) -> dict[str, int]:
    """Repair the in-process worker pool and unblock orphaned running jobs.

    Startup recovery handles jobs left running by a prior process. This runtime
    guard covers the same failure shape inside the current process: if no
    catalog worker thread is alive, no thread can finish the durable running
    job, so mark it failed before starting a replacement worker.
    """
    with _service_lock:
        alive, _dead_worker_ids = _prune_worker_threads_locked()
        recovered_count = 0
        if _stop_event.is_set() and alive:
            return {
                "worker_count": GALLERY_CATALOG_WORKERS,
                "alive_workers": len(alive),
                "recovered_jobs": 0,
                "shutdown_incomplete": 1,
            }
        if service_enabled:
            live_worker_ids = {
                str(thread._gallery_worker_id)  # type: ignore[attr-defined]
                for thread in alive
                if getattr(thread, "_gallery_worker_id", None)
            }
            with _active_claims_lock:
                live_claim_tokens = set(_active_catalog_claims)
            recovered_jobs = recover_stale_jobs(
                reason="Catalog worker stopped before completing the job",
                live_worker_ids=live_worker_ids,
                live_claim_tokens=live_claim_tokens,
            )
            recovered_count = len(recovered_jobs)
            for job in recovered_jobs:
                LOGGER.warning("Recovered orphaned catalog job %s after worker stopped", job["id"])
            _emit_recovered_jobs(recovered_jobs)
        if service_enabled and len(alive) < GALLERY_CATALOG_WORKERS:
            _spawn_missing_workers_locked()
            notify_workers()
            alive, _dead_worker_ids = _prune_worker_threads_locked()
        return {
            "worker_count": GALLERY_CATALOG_WORKERS,
            "alive_workers": len(alive),
            "recovered_jobs": recovered_count,
            "shutdown_incomplete": int(_shutdown_incomplete),
        }


def stop() -> None:
    """Signal workers to stop within one shared absolute deadline."""
    global _shutdown_incomplete
    _stop_event.set()
    _wake_event.set()
    deadline = time.monotonic() + CATALOG_SHUTDOWN_TIMEOUT_SECONDS
    with _service_lock:
        threads = [*_worker_threads]
        if _supervisor_thread is not None:
            threads.append(_supervisor_thread)
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(timeout=remaining)
    with _service_lock:
        alive, _dead_worker_ids = _prune_worker_threads_locked()
        supervisor_alive = bool(_supervisor_thread and _supervisor_thread.is_alive())
        _shutdown_incomplete = bool(alive or supervisor_alive)
        if _shutdown_incomplete:
            LOGGER.warning(
                "Catalog shutdown timed out with %s worker(s) and supervisor_alive=%s",
                len(alive),
                supervisor_alive,
            )


def runtime_status() -> dict[str, int]:
    """Return catalog worker runtime counts."""
    with _service_lock:
        return {
            "worker_count": GALLERY_CATALOG_WORKERS,
            "alive_workers": sum(1 for thread in _worker_threads if thread.is_alive()),
            "shutdown_incomplete": int(_shutdown_incomplete),
            "supervisor_alive": int(bool(_supervisor_thread and _supervisor_thread.is_alive())),
            "supervisor_last_check_at": int(_last_supervisor_check_at * 1000)
            if _last_supervisor_check_at is not None
            else 0,
            "supervisor_last_recovered_jobs": _last_supervisor_recovered_jobs,
            "supervisor_failures": _supervisor_failures,
        }
