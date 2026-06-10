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

    _drain_queue(indexer._pending_path_queue)
    _drain_queue(indexer._job_queue)
    with indexer._path_stager_lock:
        indexer._pending_path_keys.clear()
        indexer._path_stager_thread = None
        indexer._staged_path_coalesced = 0
        indexer._staged_path_failed = 0
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


def test_flush_staged_paths_handles_sqlite_busy_without_crashing(monkeypatch: pytest.MonkeyPatch):
    def fake_queue_metadata_index_paths(paths, root_path=None):  # noqa: ANN001
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(indexer, "queue_metadata_index_paths", fake_queue_metadata_index_paths)
    monkeypatch.setattr(indexer.time, "sleep", lambda _seconds: None)

    result = indexer._flush_staged_paths_to_job_queue([("/images/a.jpg", "/images")], start_worker=False)

    assert result == {"queued": 0, "coalesced": 0, "skipped": 0, "failed": 1}
    assert indexer._job_queue.qsize() == 0
    assert indexer.get_indexer_runtime_status()["staged_path_failed"] == 1
