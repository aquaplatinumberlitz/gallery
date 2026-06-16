from __future__ import annotations

import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool

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
from .errors import APIError, ErrorType
from .metadata_extract import ExtractedMetadata, extract_metadata
from .metadata_store import (
    MetadataIndexJob,
    clear_index_records,
    get_metadata_index_status,
    index_directory_tree,
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


def _drain_additional_paths(batch: list[tuple[str, str | None]], *, limit: int | None = None) -> None:
    batch_limit = METADATA_INDEXER_STAGE_BATCH_SIZE if limit is None else max(1, min(limit, METADATA_INDEXER_STAGE_BATCH_SIZE))
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

        if failed_jobs:
            if _mark_failed_jobs_safely(failed_jobs):
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
            result = _run_sqlite_write(
                lambda: queue_metadata_index_paths(paths, root_path),
                "queue staged metadata paths",
            )
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


def get_indexer_runtime_status(scope_path: str | Path | None = None) -> dict[str, Any]:
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
            count for path, count in active_job_paths.items()
            if _is_path_in_scope(path, scope_root)
        )
        scoped_runtime_queue_depth = sum(
            1 for job in queued_jobs
            if _is_path_in_scope(getattr(job, "path", ""), scope_root)
        )
        scoped_staged_path_queue_depth = sum(
            1 for path, root_path in staged_paths
            if _is_path_in_scope(path, scope_root) or _is_path_in_scope(root_path, scope_root)
        )
        scoped_active_scan_requests = sum(
            count for root, count in active_scan_roots.items()
            if _is_path_in_scope(root, scope_root) or _is_path_in_scope(scope_root, root)
        )
        scoped_active_rebuilds = sum(
            1 for root in active_rebuild_roots
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
    indexed = index_directory_tree(root_path, include_metadata=False, collected_image_paths=image_paths)
    queued_result = queue_metadata_index_paths(image_paths, root_path)

    if METADATA_INDEXER_ENABLED:
        metadata = _enqueue_metadata_jobs_from_result(queued_result, start_worker=True)
    else:
        metadata = {
            "queued": len(queued_result.enqueued),
            "coalesced": queued_result.coalesced,
            "skipped": queued_result.skipped,
            "failed": queued_result.failed,
        }

    return {
        "path": str(root_path),
        "indexed": indexed,
        "metadata": metadata,
    }


def _mark_rebuild_scope_started(root: str | Path, started_at: float) -> None:
    root_text = _normalized_path_text(root)
    if not root_text:
        return
    with _path_stager_lock:
        _active_rebuild_roots[root_text] = started_at


def _mark_rebuild_scope_finished(root: str | Path) -> None:
    root_text = _normalized_path_text(root)
    if not root_text:
        return
    with _path_stager_lock:
        _active_rebuild_roots.pop(root_text, None)


def _rebuild_index_scope_safely(root: str | Path) -> None:
    try:
        rebuild_index_scope(root)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Index rebuild failed for %s: %s", root, exc)
    finally:
        _mark_rebuild_scope_finished(root)


@router.get("/api/index/status")
async def api_index_status(path: str | None = Query(None, description="Folder/root path to scope index status")):
    target = resolve_path(path) if path else None
    if target is not None and not is_path_safe(target):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")

    status = await run_in_threadpool(get_metadata_index_status, target)
    runtime = get_indexer_runtime_status(target)
    global_runtime_keys = {
        "enabled",
        "worker_count",
        "active_jobs",
        "runtime_queue_depth",
        "coalesced_duplicates",
        "staged_path_queue_depth",
        "staged_path_coalesced",
        "staged_path_failed",
        "staged_path_flushes_forced",
        "staged_path_worker_count",
        "active_scan_requests",
        "batch_size",
        "staged_path_batch_size",
        "stage_max_wait_seconds",
    }
    global_runtime = {key: runtime[key] for key in global_runtime_keys}
    scope = {
        **status,
        "active_jobs": runtime["scoped_active_jobs"],
        "runtime_queue_depth": runtime["scoped_runtime_queue_depth"],
        "staged_path_queue_depth": runtime["scoped_staged_path_queue_depth"],
        "active_scan_requests": runtime["scoped_active_scan_requests"],
        "active_rebuilds": runtime["scoped_active_rebuilds"],
    }
    response = {**status, **global_runtime}
    response["scope"] = scope
    response["global_runtime"] = global_runtime
    return response


@router.post("/api/index/rebuild")
async def api_index_rebuild(
    background_tasks: BackgroundTasks,
    path: str = Query(..., description="Folder/root path to rebuild"),
    confirm: bool = Query(False, description="Must be true because rebuild clears persisted index rows first"),
):
    if not confirm:
        raise APIError(400, "confirmation_required", "Rebuild requires explicit confirmation")

    target = resolve_path(path)
    if not is_path_safe(target):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not target.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Path not found")
    if not target.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")

    cleared = await run_in_threadpool(clear_index_records, target)
    rebuild_started_at = time.time()
    _mark_rebuild_scope_started(target, rebuild_started_at)
    background_tasks.add_task(_rebuild_index_scope_safely, target)

    return {
        "path": str(target),
        "cleared": cleared,
        "rebuild_started": True,
        "rebuild_started_at": rebuild_started_at,
    }
