from __future__ import annotations

import queue
import sqlite3
from pathlib import Path

import pytest

from backend import indexer
from backend.metadata_store import MetadataIndexJob, MetadataQueueResult


def _drain_queue(target: queue.Queue) -> None:
    while True:
        try:
            target.get_nowait()
        except queue.Empty:
            return
        try:
            target.task_done()
        except ValueError:
            pass


@pytest.fixture(autouse=True)
def reset_indexer_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(indexer, "METADATA_INDEXER_ENABLED", True)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_STAGE_SLEEP_SECONDS", 0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_SCAN_YIELD_SECONDS", 0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS", 1.0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_SQLITE_BUSY_RETRIES", 3)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_WORKER_SLEEP_SECONDS", 0)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_BATCH_SIZE", 8)

    _drain_queue(indexer._pending_path_queue)
    _drain_queue(indexer._job_queue)
    with indexer._path_stager_lock:
        indexer._pending_path_keys.clear()
        indexer._path_stager_thread = None
        indexer._staged_path_coalesced = 0
        indexer._staged_path_failed = 0
        indexer._staged_path_flushes_forced = 0
        indexer._last_path_stage_at = 0.0
        indexer._active_scan_requests = 0
    with indexer._worker_lock:
        indexer._queued_keys.clear()
        indexer._worker_thread = None
        indexer._active_jobs = 0
        indexer._coalesced_duplicates = 0

    yield

    _drain_queue(indexer._pending_path_queue)
    _drain_queue(indexer._job_queue)
    with indexer._path_stager_lock:
        indexer._pending_path_keys.clear()
    with indexer._worker_lock:
        indexer._queued_keys.clear()


def _job(path: str, *, mtime: float = 1.0, size: int = 2) -> MetadataIndexJob:
    parent = str(Path(path).parent)
    return MetadataIndexJob(
        path=path,
        name=Path(path).name,
        parent_path=parent,
        mtime=mtime,
        size=size,
        folder_path=parent,
        root_path="/root",
    )


def test_enqueue_metadata_jobs_from_scan_stages_without_sqlite(monkeypatch: pytest.MonkeyPatch):
    def fail_queue_metadata_index_paths(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("scan enqueue must not touch SQLite queue bookkeeping")

    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fail_queue_metadata_index_paths)

    result = indexer.enqueue_metadata_jobs_from_scan(
        [{"path": "/images/a.jpg"}, {"path": "/images/b.png"}],
        "/images",
        start_worker=False,
    )

    assert result == {"staged": 2, "coalesced": 0, "skipped": 0}
    assert indexer._pending_path_queue.qsize() == 2
    assert indexer._job_queue.qsize() == 0


def test_stage_metadata_paths_from_scan_dedupes_in_ram():
    result = indexer.stage_metadata_paths_from_scan(
        ["/images/a.jpg", Path("/images/a.jpg"), "/images/b.png", ""],
        "/images",
        start_worker=False,
    )

    assert result == {"staged": 2, "coalesced": 1, "skipped": 1}
    assert indexer._pending_path_queue.qsize() == 2
    assert indexer._pending_path_keys == {
        ("/images/a.jpg", "/images"),
        ("/images/b.png", "/images"),
    }

    duplicate_result = indexer.stage_metadata_paths_from_scan(["/images/a.jpg"], "/images", start_worker=False)

    assert duplicate_result == {"staged": 0, "coalesced": 1, "skipped": 0}
    assert indexer._pending_path_queue.qsize() == 2


def test_flush_staged_paths_calls_sqlite_queue_and_runtime_coalesces(monkeypatch: pytest.MonkeyPatch):
    job = _job("/images/a.jpg")
    calls: list[tuple[list[str], str | None]] = []

    def fake_queue_metadata_index_paths(paths, root_path=None):  # noqa: ANN001
        calls.append((list(paths), root_path))
        return MetadataQueueResult(enqueued=[job, job], coalesced=1, skipped=2, failed=3)

    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fake_queue_metadata_index_paths)

    result = indexer._flush_staged_paths_to_job_queue(
        [("/images/a.jpg", "/images"), ("/images/b.png", "/images")],
        start_worker=False,
    )

    assert calls == [(["/images/a.jpg", "/images/b.png"], "/images")]
    assert result == {"queued": 1, "coalesced": 2, "skipped": 2, "failed": 3}
    assert indexer._job_queue.qsize() == 1
    assert indexer._queued_keys == {job.key}


def test_wait_for_staged_paths_forces_flush_after_max_wait(monkeypatch: pytest.MonkeyPatch):
    job = _job("/images/a.jpg")
    queued_calls: list[tuple[list[str], str | None]] = []
    now = {"value": 0.0}

    def fake_sleep(seconds: float):
        now["value"] += seconds

    def fake_queue_metadata_index_paths(paths, root_path=None):  # noqa: ANN001
        queued_calls.append((list(paths), root_path))
        return MetadataQueueResult(enqueued=[job])

    monkeypatch.setattr(indexer, "METADATA_INDEXER_STAGE_SLEEP_SECONDS", 0.01)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS", 0.02)
    monkeypatch.setattr(indexer.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(indexer.time, "sleep", fake_sleep)
    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fake_queue_metadata_index_paths)
    monkeypatch.setattr(indexer, "_start_worker_if_needed", lambda: None)

    indexer.stage_metadata_paths_from_scan(["/images/a.jpg"], "/images", start_worker=False)
    with indexer._path_stager_lock:
        indexer._active_scan_requests = 1

    first_path = indexer._pending_path_queue.get_nowait()
    indexer._process_staged_path_batch(first_path)

    assert queued_calls == [(["/images/a.jpg"], "/images")]
    assert indexer._job_queue.qsize() == 1
    assert indexer.get_indexer_runtime_status()["staged_path_flushes_forced"] == 1
    assert indexer._pending_path_queue.qsize() == 0


def test_process_batch_yields_to_active_scan_before_sqlite_write(tmp_path, monkeypatch: pytest.MonkeyPatch):
    image_path = tmp_path / "stale.jpg"
    image_path.write_bytes(b"not metadata")
    job = _job(str(image_path), mtime=1.0, size=2)
    now = {"value": 0.0}
    sleep_calls: list[float] = []
    events: list[tuple[str, int]] = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)
        now["value"] += seconds

    def fake_mark_running(jobs):  # noqa: ANN001
        events.append(("running", len(sleep_calls)))

    def fake_mark_stale(jobs):  # noqa: ANN001
        events.append(("stale", len(sleep_calls)))

    monkeypatch.setattr(indexer, "METADATA_INDEXER_SCAN_YIELD_SECONDS", 0.05)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS", 0.1)
    monkeypatch.setattr(indexer.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(indexer.time, "sleep", fake_sleep)
    monkeypatch.setattr(indexer, "mark_metadata_jobs_running", fake_mark_running)
    monkeypatch.setattr(indexer, "mark_metadata_jobs_stale", fake_mark_stale)

    with indexer._path_stager_lock:
        indexer._active_scan_requests = 1

    indexer._process_batch([job])

    assert events[0][0] == "running"
    assert events[0][1] > 0
    assert events[1][0] == "stale"
    assert events[1][1] > events[0][1]


def test_process_batch_returns_on_jobs_running_fail_and_failed_mark_also_fails(monkeypatch: pytest.MonkeyPatch):
    job = _job("/images/a.jpg")
    calls = {"running": 0, "failed": 0}

    def fake_mark_running(jobs):  # noqa: ANN001
        calls["running"] += 1
        raise indexer._SQLiteBusyRetriesExhausted("running mark failed")

    def fake_mark_failed(failed_jobs):  # noqa: ANN001
        calls["failed"] += 1
        raise indexer._SQLiteBusyRetriesExhausted("failed mark failed")

    def should_not_be_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("should not be called")

    monkeypatch.setattr(indexer, "mark_metadata_jobs_running", fake_mark_running)
    monkeypatch.setattr(indexer, "mark_metadata_jobs_failed", fake_mark_failed)
    monkeypatch.setattr(indexer, "extract_metadata", should_not_be_called)
    monkeypatch.setattr(indexer, "upsert_metadata_batch", should_not_be_called)
    monkeypatch.setattr(indexer, "mark_metadata_jobs_done", should_not_be_called)

    with indexer._worker_lock:
        indexer._queued_keys.add(job.key)

    indexer._process_batch([job])

    assert calls == {"running": 1, "failed": 1}
    assert indexer._queued_keys == set()


def test_flush_staged_paths_retries_sqlite_busy_then_queues(monkeypatch: pytest.MonkeyPatch):
    job = _job("/images/a.jpg")
    calls = {"count": 0}

    def fake_queue_metadata_index_paths(paths, root_path=None):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] <= 2:
            raise sqlite3.OperationalError("database is locked")
        return MetadataQueueResult(enqueued=[job])

    monkeypatch.setattr(indexer, "METADATA_INDEXER_SQLITE_BUSY_RETRIES", 3)
    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fake_queue_metadata_index_paths)
    monkeypatch.setattr(indexer.time, "sleep", lambda _seconds: None)

    result = indexer._flush_staged_paths_to_job_queue([("/images/a.jpg", "/images")], start_worker=False)

    assert calls["count"] == 3
    assert result == {"queued": 1, "coalesced": 0, "skipped": 0, "failed": 0}
    assert indexer._job_queue.qsize() == 1
    assert indexer.get_indexer_runtime_status()["staged_path_failed"] == 0


def test_flush_staged_paths_records_failed_after_sqlite_busy_retries(monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}

    def fake_queue_metadata_index_paths(paths, root_path=None):  # noqa: ANN001
        calls["count"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(indexer, "METADATA_INDEXER_SQLITE_BUSY_RETRIES", 2)
    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fake_queue_metadata_index_paths)
    monkeypatch.setattr(indexer.time, "sleep", lambda _seconds: None)

    result = indexer._flush_staged_paths_to_job_queue([("/images/a.jpg", "/images")], start_worker=False)

    assert calls["count"] == 3
    assert result == {"queued": 0, "coalesced": 0, "skipped": 0, "failed": 1}
    assert indexer._job_queue.qsize() == 0
    assert indexer.get_indexer_runtime_status()["staged_path_failed"] == 1
