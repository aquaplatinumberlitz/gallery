"""WK-05 regression: transient storage errors must be retried, not recorded as terminal failures.

Purpose:
Pin the worker-lifecycle audit finding WK-05. ``perf_0028.png`` ended ``failed`` with
``attempts=1`` and ``error='database is locked'`` because ``fail_metadata_job`` treated every
exception as terminal, so one SQLite lock collision permanently lost a metadata job.

Guarantees:
``sqlite3.OperationalError`` locked/busy errors and ``OSError`` with ``EAGAIN``/``EBUSY``/``EINTR``
are classified transient and requeue the job with exponential backoff (the earliest next attempt is
stored and claims ignore rows that are not due yet) until ``MAX_METADATA_JOB_ATTEMPTS``, then fail;
parse and format errors fail immediately after one attempt; and the failure/requeue write itself is
retried a bounded number of times so a locked database cannot orphan the job.

Run when:
Changing metadata job failure handling, the transient-error classification, retry backoff,
``claim_next_metadata_job`` due-time filtering, or the worker's failure-write retry.
"""

from __future__ import annotations

import errno
import sqlite3
from pathlib import Path

import pytest
from PIL import UnidentifiedImageError

from backend import indexer
from backend.indexer import MetadataLifecycleWorker
from backend.metadata_store import _DB_LOCK, MAX_METADATA_JOB_ATTEMPTS, _connect
from tests.worker_contention_support import (
    install_metadata_clock,
    metadata_job_row,
    seed_queued_metadata_jobs,
    set_metadata_job,
)


@pytest.fixture
def one_job(isolated_metadata_db: Path, isolated_gallery_root: Path) -> tuple[Path, Path, Path]:
    """One library with one queued metadata job: ``(db_path, root, image_path)``."""
    root = isolated_gallery_root / "photos"
    _library_id, images = seed_queued_metadata_jobs(root, 1)
    return isolated_metadata_db, root, images[0]


def _worker(**kwargs) -> MetadataLifecycleWorker:
    kwargs.setdefault("lease_seconds", 30)
    kwargs.setdefault("write_retry_delays", ())
    return MetadataLifecycleWorker(worker_count=1, **kwargs)


def _store():
    import backend.metadata_store as metadata_store

    return metadata_store


def _fail_extract_once(monkeypatch: pytest.MonkeyPatch, exc: BaseException, times: int = 1) -> list[int]:
    real = indexer.extract_metadata
    calls: list[int] = []

    def flaky(path: Path):
        calls.append(1)
        if len(calls) <= times:
            raise exc
        return real(path)

    monkeypatch.setattr(indexer, "extract_metadata", flaky)
    return calls


# ---------------------------------------------------------------------------
# Classification and backoff
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database table is locked: metadata_index_jobs"),
        sqlite3.OperationalError("database is busy"),
        sqlite3.OperationalError("DATABASE IS LOCKED"),
        OSError(errno.EAGAIN, "Resource temporarily unavailable"),
        OSError(errno.EBUSY, "Device or resource busy"),
        OSError(errno.EINTR, "Interrupted system call"),
        BlockingIOError(errno.EAGAIN, "would block"),
        InterruptedError(errno.EINTR, "interrupted"),
    ],
)
def test_transient_errors_are_classified_as_transient(exc: BaseException) -> None:
    assert indexer.is_transient_metadata_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        sqlite3.OperationalError("no such table: metadata_index_jobs"),
        sqlite3.OperationalError("disk I/O error"),
        sqlite3.IntegrityError("UNIQUE constraint failed"),
        OSError(errno.ENOENT, "No such file or directory"),
        FileNotFoundError("gone"),
        PermissionError(errno.EACCES, "denied"),
        OSError(errno.EIO, "I/O error"),
        UnidentifiedImageError("cannot identify image file"),
        ValueError("bad metadata"),
        RuntimeError("database is locked"),
    ],
)
def test_parse_and_permanent_errors_are_not_transient(exc: BaseException) -> None:
    assert indexer.is_transient_metadata_error(exc) is False


def test_backoff_grows_exponentially_and_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.config as config

    monkeypatch.setattr(indexer, "METADATA_RETRY_BASE_SECONDS", 2.0)
    monkeypatch.setattr(indexer, "METADATA_RETRY_MAX_SECONDS", 60.0)

    delays = [indexer.metadata_retry_delay_seconds(attempts) for attempts in (1, 2, 3, 4, 5, 6, 20)]

    assert delays == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
    assert config.METADATA_RETRY_BASE_SECONDS >= 0


# ---------------------------------------------------------------------------
# Retry flow
# ---------------------------------------------------------------------------


def test_locked_database_during_upsert_requeues_and_the_job_ends_done_with_two_attempts(
    one_job, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _root, image = one_job
    clock = install_metadata_clock(monkeypatch)
    store = _store()
    real_upsert = store.upsert_metadata_batch
    calls: list[int] = []

    def locked_once(batch):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_upsert(batch)

    monkeypatch.setattr(store, "upsert_metadata_batch", locked_once)
    worker = _worker()

    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)

    row = metadata_job_row(db_path, image)
    assert row["state"] == "queued", "a transient failure must requeue, not fail"
    assert row["attempts"] == 1
    assert "database is locked" in (row["error"] or "")
    assert row["next_attempt_at"] == pytest.approx(clock.now + indexer.metadata_retry_delay_seconds(1))
    assert row["claim_token"] is None and row["lease_expires_at"] is None

    assert worker._claim_job() is None, "the retry is not due yet"
    clock.advance(indexer.metadata_retry_delay_seconds(1) + 0.01)
    retry = worker._claim_job()
    assert retry is not None and retry.path == job.path and retry.attempts == 2
    worker._run_job(retry)

    row = metadata_job_row(db_path, image)
    assert row["state"] == "done" and row["attempts"] == 2 and row["error"] is None
    assert row["next_attempt_at"] is None
    assert len(calls) == 2


def test_transient_oserror_during_extraction_is_retried(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, image = one_job
    clock = install_metadata_clock(monkeypatch)
    _fail_extract_once(monkeypatch, OSError(errno.EBUSY, "Device or resource busy"))
    worker = _worker()

    worker._run_job(worker._claim_job())
    assert metadata_job_row(db_path, image)["state"] == "queued"

    clock.advance(indexer.metadata_retry_delay_seconds(1) + 0.01)
    worker._run_job(worker._claim_job())
    row = metadata_job_row(db_path, image)
    assert row["state"] == "done" and row["attempts"] == 2


def test_transient_failures_stop_at_the_attempt_limit(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, image = one_job
    clock = install_metadata_clock(monkeypatch)
    calls = _fail_extract_once(monkeypatch, sqlite3.OperationalError("database is locked"), times=99)
    worker = _worker()

    for attempt in range(1, MAX_METADATA_JOB_ATTEMPTS + 1):
        job = worker._claim_job()
        assert job is not None and job.attempts == attempt
        worker._run_job(job)
        row = metadata_job_row(db_path, image)
        if attempt < MAX_METADATA_JOB_ATTEMPTS:
            assert row["state"] == "queued"
            clock.advance(indexer.metadata_retry_delay_seconds(attempt) + 0.01)

    row = metadata_job_row(db_path, image)
    assert row["state"] == "failed" and row["attempts"] == MAX_METADATA_JOB_ATTEMPTS
    assert "database is locked" in row["error"]
    assert len(calls) == MAX_METADATA_JOB_ATTEMPTS
    assert worker._claim_job() is None


@pytest.mark.parametrize(
    "exc",
    [
        UnidentifiedImageError("cannot identify image file"),
        ValueError("unsupported metadata"),
        FileNotFoundError("source vanished"),
    ],
)
def test_parse_and_format_errors_fail_immediately_after_one_attempt(
    one_job, monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    db_path, _root, image = one_job
    _fail_extract_once(monkeypatch, exc, times=99)
    worker = _worker()

    worker._run_job(worker._claim_job())

    row = metadata_job_row(db_path, image)
    assert row["state"] == "failed" and row["attempts"] == 1
    assert row["next_attempt_at"] is None and row["claim_token"] is None


def test_oversized_sidecar_is_a_permanent_failure(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.metadata_extract as metadata_extract

    db_path, _root, image = one_job
    image.with_suffix(".txt").write_text("x" * 64)
    monkeypatch.setattr(metadata_extract, "METADATA_SIDECAR_MAX_BYTES", 8)
    worker = _worker()

    worker._run_job(worker._claim_job())

    row = metadata_job_row(db_path, image)
    assert row["state"] == "failed" and row["attempts"] == 1


# ---------------------------------------------------------------------------
# The failure/requeue write itself
# ---------------------------------------------------------------------------


def test_failure_write_is_retried_so_a_locked_database_cannot_orphan_the_job(
    one_job, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _root, image = one_job
    _fail_extract_once(monkeypatch, ValueError("boom"), times=99)
    real_fail = indexer.fail_metadata_job
    attempts: list[int] = []

    def locked_twice(conn, job, error):
        attempts.append(1)
        if len(attempts) <= 2:
            raise sqlite3.OperationalError("database is locked")
        return real_fail(conn, job, error)

    monkeypatch.setattr(indexer, "fail_metadata_job", locked_twice)
    worker = _worker(write_retry_delays=(0.0, 0.0, 0.0))

    worker._run_job(worker._claim_job())

    row = metadata_job_row(db_path, image)
    assert row["state"] == "failed", "the failure write must be retried instead of leaving the job running"
    assert len(attempts) == 3


def test_requeue_write_is_retried_too(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, image = one_job
    install_metadata_clock(monkeypatch)
    _fail_extract_once(monkeypatch, sqlite3.OperationalError("database is locked"), times=99)
    real_requeue = indexer.requeue_metadata_job
    attempts: list[int] = []

    def locked_once(conn, job, error, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_requeue(conn, job, error, **kwargs)

    monkeypatch.setattr(indexer, "requeue_metadata_job", locked_once)
    worker = _worker(write_retry_delays=(0.0, 0.0))

    worker._run_job(worker._claim_job())

    assert metadata_job_row(db_path, image)["state"] == "queued"
    assert len(attempts) == 2


def test_failure_write_retries_are_bounded(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, image = one_job
    _fail_extract_once(monkeypatch, ValueError("boom"), times=99)
    attempts: list[int] = []

    def always_locked(_conn, _job, _error):
        attempts.append(1)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(indexer, "fail_metadata_job", always_locked)
    worker = _worker(write_retry_delays=(0.0, 0.0, 0.0))

    worker._run_job(worker._claim_job())  # must return, not loop forever

    assert len(attempts) == 4, "one try plus one per configured retry delay"
    assert metadata_job_row(db_path, image)["state"] == "running", "the lease, not the writer, recovers it from here"


def test_non_transient_write_errors_are_not_retried(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    _db_path, _root, _image = one_job
    _fail_extract_once(monkeypatch, ValueError("boom"), times=99)
    attempts: list[int] = []

    def broken(_conn, _job, _error):
        attempts.append(1)
        raise sqlite3.OperationalError("no such table: metadata_index_jobs")

    monkeypatch.setattr(indexer, "fail_metadata_job", broken)
    worker = _worker(write_retry_delays=(0.0, 0.0, 0.0))

    worker._run_job(worker._claim_job())

    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Claim honours the due time
# ---------------------------------------------------------------------------


def test_claim_ignores_rows_that_are_not_due_and_still_orders_the_due_ones(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = install_metadata_clock(monkeypatch)
    store = _store()
    root = isolated_gallery_root / "photos"
    _library_id, images = seed_queued_metadata_jobs(root, 3)
    backoff, later, earlier = images
    set_metadata_job(isolated_metadata_db, backoff, priority=0, next_attempt_at=clock.now + 60)
    set_metadata_job(isolated_metadata_db, later, priority=3, queued_at=clock.now - 10)
    set_metadata_job(isolated_metadata_db, earlier, priority=3, queued_at=clock.now - 20)

    first = store.claim_next_metadata_job()
    second = store.claim_next_metadata_job()
    assert store.claim_next_metadata_job() is None, "the only remaining row is in backoff"
    assert (Path(first.path), Path(second.path)) == (earlier, later)

    clock.advance(59)
    assert store.claim_next_metadata_job() is None
    clock.advance(2)
    due = store.claim_next_metadata_job()
    assert due is not None and Path(due.path) == backoff and due.attempts == 1


def test_requeue_stores_the_next_attempt_and_clears_the_claim(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, image = one_job
    clock = install_metadata_clock(monkeypatch)
    store = _store()
    job = store.claim_next_metadata_job(worker_id="w", lease_seconds=30)
    assert job is not None

    with _DB_LOCK, _connect() as conn:
        assert store.requeue_metadata_job(conn, job, "database is locked", delay_seconds=12.5) is True

    row = metadata_job_row(db_path, image)
    assert row["state"] == "queued" and row["attempts"] == 1
    assert row["next_attempt_at"] == pytest.approx(clock.now + 12.5)
    assert row["claim_token"] is None and row["claimed_by"] is None and row["lease_expires_at"] is None
    assert row["error"] == "database is locked" and row["started_at"] is None


def test_a_rescan_does_not_reset_the_backoff_of_a_queued_retry(one_job, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, root, image = one_job
    clock = install_metadata_clock(monkeypatch)
    store = _store()
    job = store.claim_next_metadata_job(worker_id="w", lease_seconds=30)
    with _DB_LOCK, _connect() as conn:
        store.requeue_metadata_job(conn, job, "database is locked", delay_seconds=30)
    due_at = metadata_job_row(db_path, image)["next_attempt_at"]

    result = indexer.dispatch_metadata_index_paths([image], root)

    assert result["coalesced"] == 1
    assert metadata_job_row(db_path, image)["next_attempt_at"] == pytest.approx(due_at)
    assert store.claim_next_metadata_job() is None
    assert clock.now < due_at
