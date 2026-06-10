from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .config import (
    METADATA_INDEXER_BATCH_SIZE,
    METADATA_INDEXER_ENABLED,
    METADATA_INDEXER_STAGE_BATCH_SIZE,
    METADATA_INDEXER_STAGE_SLEEP_SECONDS,
    METADATA_INDEXER_WORKER_SLEEP_SECONDS,
)
from .errors import APIError, ErrorType
from .metadata_extract import ExtractedMetadata, extract_metadata
from .metadata_store import (
    MetadataIndexJob,
    get_metadata_index_status,
    mark_metadata_jobs_done,
    mark_metadata_jobs_failed,
    mark_metadata_jobs_running,
    mark_metadata_jobs_stale,
    queue_metadata_index_paths,
    upsert_metadata_batch,
)
from .paths import is_path_safe, resolve_path

try:  # prometheus-fastapi-instrumentator depends on prometheus_client.
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - metrics are optional at import time.
    Counter = Gauge = Histogram = None  # type: ignore[assignment]


router = APIRouter()
LOGGER = logging.getLogger(__name__)

_job_queue: queue.Queue[MetadataIndexJob] = queue.Queue()
_worker_lock = threading.RLock()
_worker_thread: threading.Thread | None = None
_queued_keys: set[tuple[str, float, int]] = set()
_active_jobs = 0
_coalesced_duplicates = 0

_pending_path_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
_pending_path_keys: set[tuple[str, str | None]] = set()
_path_stager_thread: threading.Thread | None = None
_path_stager_lock = threading.RLock()
_staged_path_coalesced = 0
_staged_path_failed = 0
_last_path_stage_at = 0.0
_active_scan_requests = 0


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


def _inc(metric: Any, *labels: str, amount: float = 1.0) -> None:
    if metric is None:
        return
    target = metric.labels(*labels) if labels else metric
    target.inc(amount)


def _observe(metric: Any, value: float) -> None:
    if metric is not None:
        metric.observe(value)


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
    global _worker_thread
    if not METADATA_INDEXER_ENABLED:
        return
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="gallery-metadata-indexer",
            daemon=True,
        )
        _worker_thread.start()


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


def _drain_path_batch(first_path: tuple[str, str | None]) -> list[tuple[str, str | None]]:
    batch = [first_path]
    _drain_additional_paths(batch)
    return batch


def _drain_additional_paths(batch: list[tuple[str, str | None]]) -> None:
    while len(batch) < METADATA_INDEXER_STAGE_BATCH_SIZE:
        try:
            batch.append(_pending_path_queue.get_nowait())
        except queue.Empty:
            break


def _worker_loop() -> None:
    while True:
        first_job = _job_queue.get()
        batch = _drain_batch(first_job)
        _process_batch(batch)
        for _ in batch:
            _job_queue.task_done()
        _update_runtime_queue_metrics()


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
    _update_runtime_queue_metrics()

    try:
        mark_metadata_jobs_running(jobs)
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
                upsert_metadata_batch(metadata for _, metadata in successes)
                _observe(_sqlite_write_duration_metric, time.perf_counter() - write_started)
                _observe(_sqlite_batch_size_metric, len(successes))
                mark_metadata_jobs_done(job for job, _ in successes)
                _inc(_jobs_total_metric, "done", amount=len(successes))
            except Exception as exc:  # noqa: BLE001
                failed_jobs.extend((job, f"SQLite write failed: {exc}") for job, _ in successes)

        if stale_jobs:
            mark_metadata_jobs_stale(stale_jobs)
            _inc(_jobs_total_metric, "stale", amount=len(stale_jobs))

        if failed_jobs:
            mark_metadata_jobs_failed(failed_jobs)
            _inc(_jobs_total_metric, "error", amount=len(failed_jobs))

        _observe(_job_duration_metric, time.perf_counter() - started)
    finally:
        with _worker_lock:
            _active_jobs -= len(jobs)
            for job in jobs:
                _queued_keys.discard(job.key)


def _enqueue_metadata_jobs_from_result(result: Any, *, start_worker: bool = True) -> dict[str, int]:
    global _coalesced_duplicates
    queued = 0
    in_memory_coalesced = 0

    with _worker_lock:
        for job in result.enqueued:
            if job.key in _queued_keys:
                in_memory_coalesced += 1
                continue
            _queued_keys.add(job.key)
            _job_queue.put(job)
            queued += 1
        _coalesced_duplicates += result.coalesced + in_memory_coalesced

    if result.coalesced or in_memory_coalesced:
        _inc(_jobs_total_metric, "skipped", amount=result.coalesced + in_memory_coalesced)

    if queued and start_worker:
        _start_worker_if_needed()
    _update_runtime_queue_metrics()
    return {
        "queued": queued,
        "coalesced": result.coalesced + in_memory_coalesced,
        "skipped": result.skipped,
        "failed": result.failed,
    }


def enqueue_metadata_jobs(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    """Queue metadata parse jobs. This performs stat/SQLite bookkeeping."""
    result = queue_metadata_index_paths(paths, root_path)
    return _enqueue_metadata_jobs_from_result(result, start_worker=start_worker)


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


def note_scan_request_started() -> None:
    """Record scan hot-path activity so staged DB writes can yield."""
    global _active_scan_requests, _last_path_stage_at
    if not METADATA_INDEXER_ENABLED:
        return
    with _path_stager_lock:
        _active_scan_requests += 1
        _last_path_stage_at = time.monotonic()


def note_scan_request_finished() -> None:
    """Record scan hot-path completion so staged DB writes can resume later."""
    global _active_scan_requests, _last_path_stage_at
    if not METADATA_INDEXER_ENABLED:
        return
    with _path_stager_lock:
        _active_scan_requests = max(0, _active_scan_requests - 1)
        _last_path_stage_at = time.monotonic()


def _path_stager_loop() -> None:
    while True:
        first_path = _pending_path_queue.get()
        batch = _drain_path_batch(first_path)
        try:
            _wait_for_staged_paths_to_go_idle()
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


def _wait_for_staged_paths_to_go_idle() -> None:
    sleep_seconds = METADATA_INDEXER_STAGE_SLEEP_SECONDS
    if not sleep_seconds:
        return

    while True:
        time.sleep(sleep_seconds)
        with _path_stager_lock:
            active_scan_requests = _active_scan_requests
            idle_for = time.monotonic() - _last_path_stage_at
        if active_scan_requests == 0 and idle_for >= sleep_seconds:
            # Extra hold-off: sleep another cycle so the next scan request can
            # start and register note_scan_request_started() before we grab
            # the SQLite write lock.
            time.sleep(sleep_seconds)
            return


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
            result = queue_metadata_index_paths(paths, root_path)
        except Exception as exc:  # noqa: BLE001
            failed = len(paths)
            totals["failed"] += failed
            _record_staged_path_failure(failed)
            LOGGER.warning("Failed to flush %s staged metadata paths: %s", failed, exc)
            time.sleep(max(0.1, METADATA_INDEXER_STAGE_SLEEP_SECONDS))
            continue

        queued = _enqueue_metadata_jobs_from_result(result, start_worker=start_worker)
        for key in totals:
            totals[key] += queued[key]

    return totals


def enqueue_metadata_jobs_from_scan(
    images: Iterable[Any],
    root_path: str | Path | None = None,
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    paths: list[str] = []
    for item in images:
        raw_path = item.get("path") if isinstance(item, dict) else getattr(item, "path", None)
        if raw_path:
            paths.append(str(raw_path))
    return stage_metadata_paths_from_scan(paths, root_path, start_worker=start_worker)


def get_indexer_runtime_status() -> dict[str, Any]:
    with _worker_lock:
        worker_count = 1 if _worker_thread and _worker_thread.is_alive() else 0
        active_jobs = _active_jobs
        runtime_queue_depth = _job_queue.qsize()
        coalesced_duplicates = _coalesced_duplicates
    with _path_stager_lock:
        staged_path_queue_depth = _pending_path_queue.qsize()
        staged_path_coalesced = _staged_path_coalesced
        staged_path_failed = _staged_path_failed
        staged_path_worker_count = 1 if _path_stager_thread and _path_stager_thread.is_alive() else 0
        active_scan_requests = _active_scan_requests
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
        "staged_path_worker_count": staged_path_worker_count,
        "staged_path_batch_size": METADATA_INDEXER_STAGE_BATCH_SIZE,
        "active_scan_requests": active_scan_requests,
    }


@router.get("/api/index/status")
async def api_index_status(path: str | None = Query(None, description="Folder/root path to scope index status")):
    target = resolve_path(path) if path else None
    if target is not None and not is_path_safe(target):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")

    status = await run_in_threadpool(get_metadata_index_status, target)
    status.update(get_indexer_runtime_status())
    return status
