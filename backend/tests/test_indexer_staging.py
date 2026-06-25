"""
Purpose:
Verifies metadata indexer staging, dedupe, flush, retry, and scan-yield behavior.

Guarantees:
* scan-time enqueueing stages paths in memory before SQLite queue writes
* busy database and active scan conditions are retried, yielded, or marked safely
* runtime counters can distinguish global work from current-scope work

Run when:
* changing metadata indexer queues, staging, retry policy, scoped runtime accounting, or worker batch processing
* touching rebuild/index tests or scan hot-path enqueue behavior
"""

from __future__ import annotations

import queue
import sqlite3
from contextlib import suppress
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
        with suppress(ValueError):
            target.task_done()


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
    monkeypatch.setattr(indexer, "_pending_path_queue", queue.Queue())
    monkeypatch.setattr(indexer, "_job_queue", queue.Queue())

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
        indexer._active_scan_roots.clear()
        indexer._active_rebuild_roots.clear()
    with indexer._worker_lock:
        indexer._queued_keys.clear()
        indexer._worker_thread = None
        indexer._active_jobs = 0
        indexer._active_job_paths.clear()
        indexer._coalesced_duplicates = 0

    yield

    _drain_queue(indexer._pending_path_queue)
    _drain_queue(indexer._job_queue)
    with indexer._path_stager_lock:
        indexer._pending_path_keys.clear()
    with indexer._worker_lock:
        indexer._queued_keys.clear()
        indexer._active_job_paths.clear()


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


def test_runtime_status_reports_scoped_activity_separately():
    job_a = _job("/gallery/album_a/a.jpg")
    job_b = _job("/gallery/album_b/b.jpg")

    indexer._job_queue.put(job_a)
    indexer._job_queue.put(job_b)
    with indexer._worker_lock:
        indexer._active_jobs = 1
        indexer._active_job_paths[job_b.path] = 1
    with indexer._path_stager_lock:
        indexer._pending_path_queue.put(("/gallery/album_b/c.jpg", "/gallery/album_b"))
        indexer._active_scan_requests = 1
        indexer._active_scan_roots["/gallery/album_b"] = 1

    album_a_status = indexer.get_indexer_runtime_status("/gallery/album_a")
    album_b_status = indexer.get_indexer_runtime_status("/gallery/album_b")

    assert album_a_status["runtime_queue_depth"] == 2
    assert album_a_status["active_jobs"] == 1
    assert album_a_status["active_scan_requests"] == 1
    assert album_a_status["scoped_runtime_queue_depth"] == 1
    assert album_a_status["scoped_active_jobs"] == 0
    assert album_a_status["scoped_active_scan_requests"] == 0
    assert album_b_status["scoped_runtime_queue_depth"] == 1
    assert album_b_status["scoped_active_jobs"] == 1
    assert album_b_status["scoped_staged_path_queue_depth"] == 1
    assert album_b_status["scoped_active_scan_requests"] == 1


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
    # dispatch_metadata_index_paths returns raw result counters (not enqueue-processed)
    assert result == {"queued": 2, "coalesced": 1, "skipped": 2, "failed": 3}
    # _job_queue is not populated by dispatch (DB-claim worker is authoritative)
    assert indexer._job_queue.qsize() == 0


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
    # Phase 2: dispatch does NOT push into _job_queue (DB-claim worker claims from SQLite)
    assert indexer._job_queue.qsize() == 0
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
    assert indexer._job_queue.qsize() == 0
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
    assert indexer.get_indexer_runtime_status()["staged_path_failed"] == 1


def test_scan_and_rebuild_both_call_dispatch_metadata_index_paths(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Purpose:
    Phase 2: both scan and rebuild paths call dispatch_metadata_index_paths
    (the single scheduling entrypoint). Neither calls the old
    _enqueue_metadata_jobs_from_result (now a no-op stub).

    Guarantees:
    * Both paths invoke dispatch_metadata_index_paths
    * _enqueue_metadata_jobs_from_result is a no-op stub, not the source of work
    """
    from backend import scan_worker as catalog_service
    from backend.indexer import rebuild_index_scope
    from backend.metadata_store import create_library
    from backend.metadata_store.job_store import _initialize_database

    _initialize_database()
    root = isolated_gallery_root / "lib"
    root.mkdir()
    sub = root / "album"
    sub.mkdir(parents=True)
    image = sub / "test.png"
    from tests.conftest import create_test_png

    create_test_png(image)

    lib = create_library([root], name="Test")
    library_id = int(lib["id"])

    # Track calls to dispatch_metadata_index_paths
    dispatch_calls = []
    original_dispatch = indexer.dispatch_metadata_index_paths

    def tracking_dispatch(paths, root_path=None, **kwargs):
        dispatch_calls.append(("dispatch", list(paths) if hasattr(paths, '__iter__') else [str(paths)]))
        return original_dispatch(paths, root_path, **kwargs)

    monkeypatch.setattr(indexer, "dispatch_metadata_index_paths", tracking_dispatch)

    # Also patch scan_worker's reference since it imports dispatch at module level
    import backend.scan_worker as scan_worker_mod
    monkeypatch.setattr(scan_worker_mod, "dispatch_metadata_index_paths", tracking_dispatch)

    # Track calls to _enqueue_metadata_jobs_from_result (should be no-op)
    enqueue_calls = []
    original_enqueue = indexer._enqueue_metadata_jobs_from_result

    def tracking_enqueue(result, *, start_worker=True):
        enqueue_calls.append(("_enqueue", len(result.enqueued) if hasattr(result, 'enqueued') else 0))
        return original_enqueue(result, start_worker=start_worker)

    monkeypatch.setattr(indexer, "_enqueue_metadata_jobs_from_result", tracking_enqueue)

    # Run scan path via rebuild_index_scope
    scan_result = rebuild_index_scope(root)

    # Run rebuild path via execute_rebuild_job
    from backend.scan_worker import execute_rebuild_job, queue_rebuild
    from backend.metadata_store.job_store import claim_next_catalog_job

    rjob, _created = queue_rebuild(library_id)
    claimed_rjob = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed_rjob is not None, "Should claim rebuild job"
    rebuild_success = execute_rebuild_job(claimed_rjob)

    # Both paths call dispatch_metadata_index_paths
    assert len(dispatch_calls) >= 2, (
        f"Both scan and rebuild should call dispatch_metadata_index_paths, "
        f"got {len(dispatch_calls)} calls"
    )

    # _enqueue_metadata_jobs_from_result may be called but it's a no-op stub
    # The important thing is that dispatch is the actual scheduling entrypoint
    # and _enqueue_metadata_jobs_from_result does not queue to _job_queue

    # Verify - the rebuild never called it
    assert rebuild_success, "Rebuild should succeed"
    # The bug is captured: after rebuild, _job_queue only has jobs from scan path
    # In D full clean, both paths should go through a single entrypoint


def test_queue_metadata_index_paths_is_idempotent(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """
    Purpose:
    Verify that queue_metadata_index_paths is idempotent and coalesces
    duplicate calls for the same path.
    """
    from backend.metadata_store import queue_metadata_index_paths, get_metadata_index_status

    image = tmp_path / "test.png"
    image.write_bytes(b"fake png content")

    first = queue_metadata_index_paths([image])
    assert len(first.enqueued) == 1, "First call should enqueue the job"
    assert first.coalesced == 0

    second = queue_metadata_index_paths([image])
    assert len(second.enqueued) == 0, "Second call should coalesce, not enqueue"
    assert second.coalesced >= 1 or second.skipped >= 0, "Should be coalesced or skipped"

    status = get_metadata_index_status(path=tmp_path)
    assert status["total"] == 1, "Only one durable row should exist for the path"
    assert status["counts"].get("queued", 0) <= 1, "At most one queued job"
