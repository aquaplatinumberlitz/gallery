"""Background metadata indexing queues, workers, and metrics."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .config import (
    METADATA_INDEXER_BATCH_SIZE,
    METADATA_INDEXER_ENABLED,
    METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS,
    METADATA_INDEXER_SCAN_YIELD_SECONDS,
    METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS,
    METADATA_INDEXER_SQLITE_BUSY_RETRIES,
    METADATA_INDEXER_STAGE_BATCH_SIZE,
    METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS,
    METADATA_INDEXER_STAGE_SLEEP_SECONDS,
    METADATA_INDEXER_WORKER_SLEEP_SECONDS,
)
from .metadata_extract import ExtractedMetadata, extract_metadata
from .metadata_store import (
    MetadataIndexJob,
    _DB_LOCK,
    _connect,
    claim_next_metadata_job,
    complete_metadata_job,
    fail_metadata_job,
    get_library_for_path,
    index_directory_tree,
    initialize_database,
    list_recoverable_metadata_jobs,
    mark_metadata_job_stale,
    mark_metadata_jobs_done,
    mark_metadata_jobs_failed,
    mark_metadata_jobs_running,
    mark_metadata_jobs_stale,
    queue_metadata_index_paths,
    reconcile_library_assets,
    repair_inconsistent_asset_states,
    reset_running_jobs_to_queued,
    upsert_metadata_batch,
)

try:  # prometheus-fastapi-instrumentator depends on prometheus_client.
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # noqa: BLE001  # pragma: no cover - metrics are optional at import time.
    Counter = Gauge = Histogram = None  # type: ignore[assignment]


router = APIRouter()
LOGGER = logging.getLogger(__name__)

_job_queue: queue.Queue[MetadataIndexJob] = queue.Queue()
_worker_lock = threading.RLock()
_worker_thread: threading.Thread | None = None
_queued_keys: set[tuple[str, float, int]] = set()
_active_jobs = 0
_active_job_paths: dict[str, int] = {}
_coalesced_duplicates = 0

_pending_path_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
_pending_path_keys: set[tuple[str, str | None]] = set()
_path_stager_thread: threading.Thread | None = None
_path_stager_lock = threading.RLock()
_staged_path_coalesced = 0
_staged_path_failed = 0
_staged_path_flushes_forced = 0
_last_path_stage_at = 0.0
_active_scan_requests = 0
_active_scan_roots: dict[str, int] = {}
_active_rebuild_roots: dict[str, float] = {}


def _metric(factory: Any, name: str, documentation: str, *args: Any, **kwargs: Any) -> Any:
    if factory is None:
        return None
    try:
        return factory(name, documentation, *args, **kwargs)
    except ValueError:
        return None


_queue_depth_metric = _metric(
    Gauge,
    "gallery_index_queue_depth",
    "Metadata index jobs by state",
    ["state"],
)
_jobs_total_metric = _metric(
    Counter,
    "gallery_index_jobs_total",
    "Metadata index jobs by result",
    ["result"],
)
_job_duration_metric = _metric(
    Histogram,
    "gallery_index_job_duration_seconds",
    "Background metadata index job duration",
)
_parse_duration_metric = _metric(
    Histogram,
    "gallery_metadata_parse_duration_seconds",
    "Metadata parse duration",
)
_sqlite_write_duration_metric = _metric(
    Histogram,
    "gallery_sqlite_write_duration_seconds",
    "SQLite metadata batch write duration",
)
_sqlite_batch_size_metric = _metric(
    Histogram,
    "gallery_sqlite_write_batch_size",
    "SQLite metadata write batch size",
)
_staged_path_forced_flush_metric = _metric(
    Counter,
    "gallery_index_staged_path_flushes_forced_total",
    "Forced staged metadata path flushes after max scan wait",
)


def _inc(metric: Any, *labels: str, amount: float = 1.0) -> None:
    if metric is None:
        return
    target = metric.labels(*labels) if labels else metric
    target.inc(amount)


def _observe(metric: Any, value: float) -> None:
    if metric is not None:
        metric.observe(value)


def _normalized_path_text(path: str | Path | None) -> str:
    if not path:
        return ""
    return str(Path(path).resolve())


def _is_path_in_scope(path: str | Path | None, scope_root: str | Path | None) -> bool:
    path_text = _normalized_path_text(path)
    root_text = _normalized_path_text(scope_root)
    if not path_text or not root_text:
        return False
    if path_text == root_text:
        return True
    if root_text == os.sep:
        return path_text.startswith(os.sep)
    return path_text.startswith(f"{root_text.rstrip(os.sep)}{os.sep}")


def _queue_items(target_queue: queue.Queue) -> list[Any]:
    with target_queue.mutex:
        return list(target_queue.queue)


class _SQLiteBusyRetriesExhausted(RuntimeError):
    """Raised after a transient SQLite busy/locked error exhausts retries."""


def _is_sqlite_busy_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text or "locked" in text


def _retry_sqlite_busy(operation: Callable[[], Any], description: str) -> Any:
    retries = METADATA_INDEXER_SQLITE_BUSY_RETRIES
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            if not _is_sqlite_busy_error(exc):
                raise
            if attempt >= retries:
                raise _SQLiteBusyRetriesExhausted(f"{description} SQLite busy after retries: {exc}") from exc
            backoff_seconds = METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS * (attempt + 1)
            if backoff_seconds:
                time.sleep(backoff_seconds)
    raise AssertionError("unreachable SQLite retry loop")


def _yield_to_active_scans(max_wait_seconds: float | None = None) -> None:
    sleep_seconds = METADATA_INDEXER_SCAN_YIELD_SECONDS
    if sleep_seconds <= 0:
        return

    with _path_stager_lock:
        active_scan_requests = _active_scan_requests
    if active_scan_requests <= 0:
        return

    max_wait = METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS if max_wait_seconds is None else max(0.0, max_wait_seconds)
    started_waiting = time.monotonic()
    while True:
        waited_for = time.monotonic() - started_waiting
        if waited_for >= max_wait:
            return
        time.sleep(min(sleep_seconds, max_wait - waited_for))
        with _path_stager_lock:
            active_scan_requests = _active_scan_requests
        if active_scan_requests <= 0:
            return


def _run_sqlite_write(operation: Callable[[], Any], description: str) -> Any:
    def attempt() -> Any:
        _yield_to_active_scans()
        return operation()

    return _retry_sqlite_busy(attempt, description)


def _update_runtime_queue_metrics() -> None:
    if _queue_depth_metric is None:
        return
    with _worker_lock:
        queued = _job_queue.qsize()
        running = _active_jobs
    with _path_stager_lock:
        staged = _pending_path_queue.qsize()
    _queue_depth_metric.labels("queued").set(queued)
    _queue_depth_metric.labels("running").set(running)
    _queue_depth_metric.labels("staged_paths").set(staged)


def _is_job_current(job: MetadataIndexJob) -> bool:
    try:
        stat = Path(job.path).stat()
    except OSError:
        return False
    return stat.st_mtime == job.mtime and stat.st_size == job.size


def _start_worker_if_needed() -> None:
    """No-op compatibility stub. Phase 2: DB-claim worker is authoritative.

    The metadata worker is started at app startup via metadata_worker.start().
    """
    pass


def _start_path_stager_if_needed() -> None:
    global _path_stager_thread
    if not METADATA_INDEXER_ENABLED:
        return
    with _path_stager_lock:
        if _path_stager_thread and _path_stager_thread.is_alive():
            return
        _path_stager_thread = threading.Thread(
            target=_path_stager_loop,
            name="gallery-metadata-path-stager",
            daemon=True,
        )
        _path_stager_thread.start()


def _drain_batch(first_job: MetadataIndexJob) -> list[MetadataIndexJob]:
    batch = [first_job]
    while len(batch) < METADATA_INDEXER_BATCH_SIZE:
        try:
            batch.append(_job_queue.get_nowait())
        except queue.Empty:
            break
    return batch


def _drain_additional_paths(batch: list[tuple[str, str | None]], *, limit: int | None = None) -> None:
    batch_limit = (
        METADATA_INDEXER_STAGE_BATCH_SIZE if limit is None else max(1, min(limit, METADATA_INDEXER_STAGE_BATCH_SIZE))
    )
    while len(batch) < batch_limit:
        try:
            batch.append(_pending_path_queue.get_nowait())
        except queue.Empty:
            break


def _worker_loop() -> None:
    while True:
        first_job = _job_queue.get()
        batch = _drain_batch(first_job)
        try:
            _process_batch(batch)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Unhandled metadata index batch failure: %s", exc)
        finally:
            for _ in batch:
                _job_queue.task_done()
            _update_runtime_queue_metrics()


def _mark_failed_jobs_safely(failed_jobs: list[tuple[MetadataIndexJob, str]]) -> bool:
    if not failed_jobs:
        return True
    try:
        _run_sqlite_write(lambda: mark_metadata_jobs_failed(failed_jobs), "mark metadata jobs failed")
    except _SQLiteBusyRetriesExhausted as exc:
        LOGGER.warning("Unable to mark %s metadata jobs failed after SQLite busy retries: %s", len(failed_jobs), exc)
        return False
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Unable to mark %s metadata jobs failed: %s", len(failed_jobs), exc)
        return False
    return True


def _process_batch(jobs: list[MetadataIndexJob]) -> None:
    global _active_jobs
    if METADATA_INDEXER_WORKER_SLEEP_SECONDS:
        time.sleep(METADATA_INDEXER_WORKER_SLEEP_SECONDS)

    started = time.perf_counter()
    successes: list[tuple[MetadataIndexJob, ExtractedMetadata]] = []
    stale_jobs: list[MetadataIndexJob] = []
    failed_jobs: list[tuple[MetadataIndexJob, str]] = []

    with _worker_lock:
        _active_jobs += len(jobs)
        for job in jobs:
            _active_job_paths[job.path] = _active_job_paths.get(job.path, 0) + 1
    _update_runtime_queue_metrics()

    try:
        try:
            _run_sqlite_write(lambda: mark_metadata_jobs_running(jobs), "mark metadata jobs running")
        except _SQLiteBusyRetriesExhausted as exc:
            failed_jobs.extend((job, str(exc)) for job in jobs)
            if _mark_failed_jobs_safely(failed_jobs):
                _inc(_jobs_total_metric, "error", amount=len(failed_jobs))
            return
        except Exception as exc:  # noqa: BLE001
            failed_jobs.extend((job, f"SQLite running mark failed: {exc}") for job in jobs)
            if _mark_failed_jobs_safely(failed_jobs):
                _inc(_jobs_total_metric, "error", amount=len(failed_jobs))
            return

        for job in jobs:
            parse_started = time.perf_counter()
            if not _is_job_current(job):
                stale_jobs.append(job)
                continue
            try:
                metadata = extract_metadata(Path(job.path))
                _observe(_parse_duration_metric, time.perf_counter() - parse_started)
                if _is_job_current(job):
                    successes.append((job, metadata))
                else:
                    stale_jobs.append(job)
            except Exception as exc:  # noqa: BLE001
                failed_jobs.append((job, str(exc)))

        if successes:
            write_started = time.perf_counter()
            try:
                _run_sqlite_write(
                    lambda: upsert_metadata_batch(metadata for _, metadata in successes),
                    "upsert metadata batch",
                )
                _observe(_sqlite_write_duration_metric, time.perf_counter() - write_started)
                _observe(_sqlite_batch_size_metric, len(successes))
                try:
                    done_jobs = [job for job, _ in successes]
                    _run_sqlite_write(lambda: mark_metadata_jobs_done(done_jobs), "mark metadata jobs done")
                    _inc(_jobs_total_metric, "done", amount=len(successes))
                except Exception as exc:  # noqa: BLE001
                    failed_jobs.extend((job, f"SQLite done mark failed: {exc}") for job, _ in successes)
            except Exception as exc:  # noqa: BLE001
                failed_jobs.extend((job, f"SQLite write failed: {exc}") for job, _ in successes)

        if stale_jobs:
            try:
                _run_sqlite_write(lambda: mark_metadata_jobs_stale(stale_jobs), "mark metadata jobs stale")
                _inc(_jobs_total_metric, "stale", amount=len(stale_jobs))
            except Exception as exc:  # noqa: BLE001
                failed_jobs.extend((job, f"SQLite stale mark failed: {exc}") for job in stale_jobs)

        if failed_jobs and _mark_failed_jobs_safely(failed_jobs):
            _inc(_jobs_total_metric, "error", amount=len(failed_jobs))

        _observe(_job_duration_metric, time.perf_counter() - started)
    finally:
        with _worker_lock:
            _active_jobs -= len(jobs)
            for job in jobs:
                _queued_keys.discard(job.key)
                active_count = _active_job_paths.get(job.path, 0)
                if active_count <= 1:
                    _active_job_paths.pop(job.path, None)
                else:
                    _active_job_paths[job.path] = active_count - 1


def _enqueue_metadata_jobs_from_result(result: Any, *, start_worker: bool = True) -> dict[str, int]:
    """No-op compatibility stub. Phase 2: DB-claim worker is authoritative."""
    if result.coalesced or (hasattr(result, "enqueued") and result.enqueued):
        LOGGER.debug(
            "_enqueue_metadata_jobs_from_result called (no-op): %s enqueued", len(getattr(result, "enqueued", []))
        )
    _update_runtime_queue_metrics()
    return {
        "queued": 0,
        "coalesced": result.coalesced if hasattr(result, "coalesced") else 0,
        "skipped": result.skipped if hasattr(result, "skipped") else 0,
        "failed": result.failed if hasattr(result, "failed") else 0,
    }


def stage_metadata_paths_from_scan(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    """Stage scan-discovered image paths in RAM without touching SQLite or files."""
    global _last_path_stage_at, _staged_path_coalesced
    staged = 0
    coalesced = 0
    skipped = 0
    root_text = str(root_path) if root_path is not None else None
    saw_stage_activity = False

    with _path_stager_lock:
        for raw_path in paths:
            path_text = str(raw_path) if raw_path else ""
            if not path_text or not METADATA_INDEXER_ENABLED:
                skipped += 1
                continue

            saw_stage_activity = True
            key = (path_text, root_text)
            if key in _pending_path_keys:
                coalesced += 1
                continue

            _pending_path_keys.add(key)
            _pending_path_queue.put(key)
            staged += 1

        if saw_stage_activity:
            _last_path_stage_at = time.monotonic()
        _staged_path_coalesced += coalesced

    if staged and start_worker:
        _start_path_stager_if_needed()
    _update_runtime_queue_metrics()
    return {"staged": staged, "coalesced": coalesced, "skipped": skipped}


def note_scan_request_started(root_path: str | Path | None = None) -> None:
    """Record scan hot-path activity so staged DB writes can yield."""
    global _active_scan_requests, _last_path_stage_at
    if not METADATA_INDEXER_ENABLED:
        return
    root_text = _normalized_path_text(root_path)
    with _path_stager_lock:
        _active_scan_requests += 1
        if root_text:
            _active_scan_roots[root_text] = _active_scan_roots.get(root_text, 0) + 1
        _last_path_stage_at = time.monotonic()


def note_scan_request_finished(root_path: str | Path | None = None) -> None:
    """Record scan hot-path completion so staged DB writes can resume later."""
    global _active_scan_requests, _last_path_stage_at
    if not METADATA_INDEXER_ENABLED:
        return
    root_text = _normalized_path_text(root_path)
    with _path_stager_lock:
        _active_scan_requests = max(0, _active_scan_requests - 1)
        if root_text:
            active_count = _active_scan_roots.get(root_text, 0)
            if active_count <= 1:
                _active_scan_roots.pop(root_text, None)
            else:
                _active_scan_roots[root_text] = active_count - 1
        _last_path_stage_at = time.monotonic()


def _path_stager_loop() -> None:
    while True:
        first_path = _pending_path_queue.get()
        _process_staged_path_batch(first_path)


def _process_staged_path_batch(first_path: tuple[str, str | None]) -> None:
    batch = [first_path]
    try:
        forced_flush = _wait_for_staged_paths_to_go_idle()
        if forced_flush:
            _record_forced_staged_path_flush()
            _drain_additional_paths(batch, limit=METADATA_INDEXER_BATCH_SIZE)
        else:
            _drain_additional_paths(batch)
        _flush_staged_paths_to_job_queue(batch)
    except Exception as exc:  # noqa: BLE001
        _record_staged_path_failure(len(batch))
        LOGGER.exception("Unhandled metadata path staging failure: %s", exc)
    finally:
        with _path_stager_lock:
            for key in batch:
                _pending_path_keys.discard(key)
        for _ in batch:
            _pending_path_queue.task_done()
        _update_runtime_queue_metrics()


def _wait_for_staged_paths_to_go_idle() -> bool:
    sleep_seconds = METADATA_INDEXER_STAGE_SLEEP_SECONDS
    if not sleep_seconds:
        return False

    started_waiting = time.monotonic()
    while True:
        time.sleep(sleep_seconds)
        now = time.monotonic()
        with _path_stager_lock:
            active_scan_requests = _active_scan_requests
            idle_for = now - _last_path_stage_at
        waited_for = now - started_waiting
        if active_scan_requests == 0 and idle_for >= sleep_seconds:
            # Extra hold-off: sleep another cycle so the next scan request can
            # start and register note_scan_request_started() before we grab
            # the SQLite write lock.
            time.sleep(sleep_seconds)
            return False
        if waited_for >= METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS:
            return True


def _record_forced_staged_path_flush() -> None:
    global _staged_path_flushes_forced
    with _path_stager_lock:
        _staged_path_flushes_forced += 1
    _inc(_staged_path_forced_flush_metric)


def _record_staged_path_failure(count: int) -> None:
    global _staged_path_failed
    if count <= 0:
        return
    with _path_stager_lock:
        _staged_path_failed += count
    _inc(_jobs_total_metric, "error", amount=count)


def _flush_staged_paths_to_job_queue(
    batch: Iterable[tuple[str, str | None]],
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    """Move staged scan paths into the durable metadata job queue."""
    grouped_paths: dict[str | None, list[str]] = {}
    for path, root_path in batch:
        grouped_paths.setdefault(root_path, []).append(path)

    totals = {"queued": 0, "coalesced": 0, "skipped": 0, "failed": 0}
    for root_path, paths in grouped_paths.items():
        try:
            result = dispatch_metadata_index_paths(paths, root_path)
        except _SQLiteBusyRetriesExhausted as exc:
            failed = len(paths)
            totals["failed"] += failed
            _record_staged_path_failure(failed)
            LOGGER.warning("Failed to flush %s staged metadata paths after SQLite busy retries: %s", failed, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            failed = len(paths)
            totals["failed"] += failed
            _record_staged_path_failure(failed)
            LOGGER.warning("Failed to flush %s staged metadata paths: %s", failed, exc)
            continue

        for key in totals:
            totals[key] += result[key]

    return totals


def enqueue_metadata_jobs_from_scan(
    images: Iterable[Any],
    root_path: str | Path | None = None,
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    """Stage image paths from a scan response for durable metadata indexing."""
    paths: list[str] = []
    for item in images:
        raw_path = item.get("path") if isinstance(item, dict) else getattr(item, "path", None)
        if raw_path:
            paths.append(str(raw_path))
    return stage_metadata_paths_from_scan(paths, root_path, start_worker=start_worker)


def get_indexer_runtime_status(scope_path: str | Path | None = None) -> dict[str, Any]:
    """Return in-memory indexer worker and staging queue status, optionally scoped to a path."""
    scope_root = _normalized_path_text(scope_path)
    with _worker_lock:
        worker_count = 1 if _worker_thread and _worker_thread.is_alive() else 0
        active_jobs = _active_jobs
        runtime_queue_depth = _job_queue.qsize()
        coalesced_duplicates = _coalesced_duplicates
        active_job_paths = dict(_active_job_paths)
        queued_jobs = _queue_items(_job_queue)
    with _path_stager_lock:
        staged_path_queue_depth = _pending_path_queue.qsize()
        staged_path_coalesced = _staged_path_coalesced
        staged_path_failed = _staged_path_failed
        staged_path_flushes_forced = _staged_path_flushes_forced
        staged_path_worker_count = 1 if _path_stager_thread and _path_stager_thread.is_alive() else 0
        active_scan_requests = _active_scan_requests
        active_scan_roots = dict(_active_scan_roots)
        staged_paths = _queue_items(_pending_path_queue)
        active_rebuild_roots = dict(_active_rebuild_roots)

    scoped_active_jobs = 0
    scoped_runtime_queue_depth = 0
    scoped_staged_path_queue_depth = 0
    scoped_active_scan_requests = 0
    scoped_active_rebuilds = 0
    if scope_root:
        scoped_active_jobs = sum(
            count for path, count in active_job_paths.items() if _is_path_in_scope(path, scope_root)
        )
        scoped_runtime_queue_depth = sum(
            1 for job in queued_jobs if _is_path_in_scope(getattr(job, "path", ""), scope_root)
        )
        scoped_staged_path_queue_depth = sum(
            1
            for path, root_path in staged_paths
            if _is_path_in_scope(path, scope_root) or _is_path_in_scope(root_path, scope_root)
        )
        scoped_active_scan_requests = sum(
            count
            for root, count in active_scan_roots.items()
            if _is_path_in_scope(root, scope_root) or _is_path_in_scope(scope_root, root)
        )
        scoped_active_rebuilds = sum(
            1
            for root in active_rebuild_roots
            if _is_path_in_scope(root, scope_root) or _is_path_in_scope(scope_root, root)
        )

    return {
        "enabled": METADATA_INDEXER_ENABLED,
        "worker_count": worker_count,
        "active_jobs": active_jobs,
        "runtime_queue_depth": runtime_queue_depth,
        "coalesced_duplicates": coalesced_duplicates,
        "batch_size": METADATA_INDEXER_BATCH_SIZE,
        "staged_path_queue_depth": staged_path_queue_depth,
        "staged_path_coalesced": staged_path_coalesced,
        "staged_path_failed": staged_path_failed,
        "staged_path_flushes_forced": staged_path_flushes_forced,
        "staged_path_worker_count": staged_path_worker_count,
        "staged_path_batch_size": METADATA_INDEXER_STAGE_BATCH_SIZE,
        "stage_max_wait_seconds": METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS,
        "active_scan_requests": active_scan_requests,
        "scoped_active_jobs": scoped_active_jobs,
        "scoped_runtime_queue_depth": scoped_runtime_queue_depth,
        "scoped_staged_path_queue_depth": scoped_staged_path_queue_depth,
        "scoped_active_scan_requests": scoped_active_scan_requests,
        "scoped_active_rebuilds": scoped_active_rebuilds,
    }


def rebuild_index_scope(root: str | Path) -> dict[str, Any]:
    """Rebuild non-destructively for files: recreate DB index rows for a scoped root."""
    root_path = Path(root).resolve()
    image_paths: list[Path] = []
    asset_paths: set[str] = set()
    indexed = index_directory_tree(
        root_path,
        include_metadata=False,
        collected_image_paths=image_paths,
        collected_asset_paths=asset_paths,
    )
    library = get_library_for_path(root_path)
    reconciled = 0
    if library is not None:
        reconciled = reconcile_library_assets(int(library["id"]), asset_paths, scope_path=root_path)

    metadata = dispatch_metadata_index_paths(image_paths, root_path)

    return {
        "path": str(root_path),
        "indexed": indexed,
        "reconciled": reconciled,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# DB-claim metadata worker (Phase 1)
# ---------------------------------------------------------------------------


def dispatch_metadata_index_paths(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    priority: int = 3,
) -> dict[str, int]:
    """Persist/coalesce metadata_index_jobs in SQLite and wake the DB-claim worker.

    This is the single scheduling entrypoint for all metadata work. It does
    NOT push jobs into the in-memory ``_job_queue``; the DB-claim worker
    claims directly from SQLite.

    Phase 2 replaces all direct calls to ``queue_metadata_index_paths`` +
    ``_enqueue_metadata_jobs_from_result`` with this unified entrypoint.
    """
    result = _run_sqlite_write(
        lambda: queue_metadata_index_paths(list(paths), root_path),
        "persist metadata index paths",
    )
    metadata_worker.wake()
    return {
        "queued": len(result.enqueued),
        "coalesced": result.coalesced,
        "skipped": result.skipped,
        "failed": result.failed,
    }


class MetadataLifecycleWorker:
    """DB-claim metadata worker, modeled on ``DerivativeScheduler``.

    Claims queued metadata jobs from SQLite, processes them, and materializes
    completion state. The worker does NOT use an in-memory ``_job_queue`` as
    the source of work — it claims directly from ``metadata_index_jobs``.
    """

    _logger = logging.getLogger("gallery.metadata")

    def __init__(self, worker_count: int = 1):
        """Initialize metadata worker thread pool."""
        self.worker_count = max(1, min(worker_count, 4))
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lifecycle_lock = threading.RLock()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start DB-claim metadata worker threads. Recovery deferred to Phase 4."""
        with self._lifecycle_lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            self._stop_event.clear()
            self._threads = [
                threading.Thread(
                    target=self._worker_loop,
                    name=f"gallery-metadata-worker-{i + 1}",
                    daemon=True,
                )
                for i in range(self.worker_count)
            ]
            for thread in self._threads:
                thread.start()
            self._wake_event.set()

    def stop(self) -> None:
        """Stop workers and wait briefly for in-flight work to finish."""
        with self._lifecycle_lock:
            threads = self._threads
            self._stop_event.set()
            self._wake_event.set()
        deadline = time.monotonic() + 1
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._lifecycle_lock:
            self._threads = [t for t in threads if t.is_alive()]

    def is_running(self) -> bool:
        """Return whether at least one configured worker is alive."""
        with self._lifecycle_lock:
            return any(thread.is_alive() for thread in self._threads)

    def wake(self) -> None:
        """Wake workers to check for new queued jobs."""
        self._wake_event.set()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._claim_job()
            except Exception:  # noqa: BLE001
                self._logger.exception("DB-claim worker could not read the job queue")
                self._stop_event.wait(0.5)
                continue
            if job is None:
                self._wake_event.clear()
                self._wake_event.wait(timeout=1)
                continue
            self._run_job(job)

    def _claim_job(self) -> MetadataIndexJob | None:
        """Claim one queued metadata job from SQLite.

        Mirrors ``DerivativeScheduler._claim_job`` (derivative_scheduler.py:392-420).
        """
        return claim_next_metadata_job()

    def _run_job(self, job: MetadataIndexJob) -> None:
        """Extract metadata and complete the job in short transactions."""
        from .metadata_extract import extract_metadata
        from .metadata_store import _DB_LOCK, _connect

        try:
            if not self._is_job_current(job):
                with _DB_LOCK, _connect() as conn:
                    mark_metadata_job_stale(conn, job)
                return

            metadata = extract_metadata(Path(job.path))

            if not self._is_job_current(job):
                with _DB_LOCK, _connect() as conn:
                    mark_metadata_job_stale(conn, job)
                return

            # Write image_metadata in its own short transaction
            from .metadata_store import upsert_metadata_batch as _upbatch

            _upbatch([metadata])

            # Complete job + materialize asset state in another short transaction
            with _DB_LOCK, _connect() as conn:
                complete_metadata_job(conn, job)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Metadata job %s failed: %s", job.path, exc)
            try:
                with _DB_LOCK, _connect() as conn:
                    fail_metadata_job(conn, job, str(exc))
            except Exception:  # noqa: BLE001
                self._logger.exception("Could not mark job %s as failed", job.path)

    @staticmethod
    def _is_job_current(job: MetadataIndexJob) -> bool:
        """Return whether the file on disk still matches the job's identity.

        Primary check uses st_mtime_ns (nanoseconds). Falls back to
        st_mtime (seconds) for legacy jobs without mtime_ns.
        """
        try:
            stat = Path(job.path).stat()
        except OSError:
            return False
        if job.mtime_ns is not None:
            return abs(stat.st_mtime_ns - job.mtime_ns) < 1000 and stat.st_size == job.size
        return stat.st_mtime == job.mtime and stat.st_size == job.size


# Singleton instance
metadata_worker = MetadataLifecycleWorker()


def recover_metadata_index_jobs() -> dict[str, int]:
    """Recover interrupted metadata jobs from SQLite.

    Recovery does NOT mean "re-dispatch DB jobs into memory queue." It means
    "make SQLite job state claimable and consistent."

    Mirrors DerivativeScheduler.start() recovery pattern.

    Returns:
        dict with counters: running_reset, done_repaired, done_demoted,
        done_skipped, total
    """
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        running_jobs = list_recoverable_metadata_jobs(conn, ("running",))
        job_paths = [(j["path"], j["mtime"], j["size"], j["mtime_ns"]) for j in running_jobs]
        reset_running_jobs_to_queued(conn, job_paths)
        repair_result = repair_inconsistent_asset_states(conn)

    metadata_worker.wake()

    return {
        "running_reset": len(running_jobs),
        "done_repaired": repair_result["repaired"],
        "done_demoted": repair_result["demoted"],
        "done_skipped": repair_result["skipped"],
        "total": len(running_jobs) + repair_result["repaired"] + repair_result["demoted"] + repair_result["skipped"],
    }
