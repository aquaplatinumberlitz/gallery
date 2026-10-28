"""Phase 2.2 regression: metadata job writes go through the single database writer.

Purpose:
Pin the metadata half of the Phase 2 write-contention work. Before it, one metadata job cost three
independent write transactions that each queued on the process-wide ``_DB_LOCK`` (claim, then upsert,
then complete), the upsert and the completion could land separately, and a status or catalog thread
holding ``_DB_LOCK`` stalled every metadata write. Now a job's metadata upsert and completion are one
atomic writer op and every other metadata write is a writer op too.

Guarantees:
Upserting ``image_metadata`` and completing the job commit in one transaction (a failing or
un-committable completion leaves neither); the in-op claim fence rejects a stale worker before it
writes anything; batched claims return jobs in exactly the single-claim order (priority, ``queued_at``,
path, only rows whose ``next_attempt_at`` is due) with their own tokens and leases, in one transaction;
claims, lease renewals and every terminal job write use the priority lane and supervisor recovery uses
the normal lane; no metadata writer call is made by a thread holding ``_DB_LOCK``, and a whole job
lifecycle completes while some other thread holds ``_DB_LOCK``; the maintenance producer gate still
quiesces metadata producers (an in-flight writer op blocks maintenance, maintenance blocks new writer
ops, the maintenance owner may still write); a writer that dies mid-queue leaves running jobs that the
Phase 1 leases requeue, with no ``done`` job lacking metadata; the worker claim buffer renews and
releases pending claims; and with the feature flag off every path uses the previous direct
transactions and never starts the writer.

Run when:
Changing metadata job claim/complete/fail/requeue/renew paths, ``upsert_metadata_batch``, the metadata
worker's use of the database writer, the maintenance producer gate, or the writer feature flag.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import backend.config as config
from backend import indexer
from backend.indexer import MetadataLifecycleWorker
from backend.metadata_extract import extract_metadata
from backend.metadata_store import _DB_LOCK
from tests.worker_contention_support import (
    capture_sql,
    install_metadata_clock,
    metadata_job_row,
    run_while_db_lock_held,
    seed_queued_metadata_jobs,
    set_metadata_job,
    wait_until,
)

LEASE_SECONDS = 30
REPO_ROOT = Path(__file__).resolve().parents[2]

# Tests that exercise the writer path without forcing the flag skip themselves in a flag-off run
# (``GALLERY_DB_WRITER_ENABLED=false``); the parametrized ``mode`` tests run in both. ``getattr`` keeps
# the module importable against a tree that predates the setting.
needs_writer = pytest.mark.skipif(
    not getattr(config, "DB_WRITER_ENABLED", True),
    reason="exercises the writer path; GALLERY_DB_WRITER_ENABLED is off for this run",
)


def _store():
    import backend.metadata_store as metadata_store

    return metadata_store


def _writer_module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


def _worker(**kwargs: Any) -> MetadataLifecycleWorker:
    kwargs.setdefault("lease_seconds", LEASE_SECONDS)
    kwargs.setdefault("heartbeat_seconds", LEASE_SECONDS / 3)
    kwargs.setdefault("write_retry_delays", ())
    return MetadataLifecycleWorker(worker_count=1, **kwargs)


def _seed(isolated_metadata_db: Path, isolated_gallery_root: Path, count: int) -> tuple[Path, Path, list[Path]]:
    root = isolated_gallery_root / "photos"
    _library_id, images = seed_queued_metadata_jobs(root, count)
    return isolated_metadata_db, root, images


@pytest.fixture
def seeded(isolated_metadata_db: Path, isolated_gallery_root: Path) -> tuple[Path, Path, list[Path]]:
    """One library with three queued metadata jobs: ``(db_path, root, image_paths)``."""
    return _seed(isolated_metadata_db, isolated_gallery_root, 3)


@pytest.fixture
def quiet_side_effects(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Silence the post-completion side effects that write through other paths.

    Derivative reconciliation and the derived-search backfill schedulers run after a job completes
    and open their own transactions; patching them keeps statement counts about the metadata path.
    Returns the recorded ``(thread name, library id)`` backfill schedule calls.
    """
    import backend.metadata_store.metadata_persist as metadata_persist
    from backend.derivative_scheduler import scheduler

    scheduled: list[tuple[str, int]] = []
    monkeypatch.setattr(scheduler, "reconcile_desired_derivatives", lambda **kwargs: None)
    monkeypatch.setattr(
        metadata_persist,
        "_schedule_derived_search_backfills",
        lambda library_id: scheduled.append((threading.current_thread().name, library_id)),
    )
    return scheduled


@pytest.fixture(params=["writer", "direct"])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test once through the writer and once through the direct (flag-off) transactions."""
    monkeypatch.setattr(_writer_module(), "DB_WRITER_ENABLED", request.param == "writer")
    return request.param


@pytest.fixture
def submit_log(monkeypatch: pytest.MonkeyPatch) -> list[SimpleNamespace]:
    """Record every external submission to the shared writer: caller thread, lane, `_DB_LOCK` ownership."""
    db_writer = _writer_module()
    writer = db_writer.database_writer
    writer.start()
    log: list[SimpleNamespace] = []
    real_submit = writer.submit

    def spy(op, *, lane: str = "normal", **kwargs: Any):
        if not writer.in_writer_thread():
            log.append(
                SimpleNamespace(thread=threading.current_thread().name, lane=lane, holds_db_lock=_DB_LOCK.is_owned())
            )
        return real_submit(op, lane=lane, **kwargs)

    monkeypatch.setattr(writer, "submit", spy)
    return log


def _asset_state(db_path: Path, path: Path | str) -> str:
    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (str(path),)).fetchone()[0])


def _has_metadata(db_path: Path, path: Path | str) -> bool:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM image_metadata WHERE path = ?", (str(path),)).fetchone() is not None


def _done_jobs_without_metadata(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [
            row[0]
            for row in conn.execute(
                """
                SELECT j.path FROM metadata_index_jobs j
                LEFT JOIN image_metadata m ON m.path = j.path
                WHERE j.state = 'done' AND m.path IS NULL
                """
            )
        ]


# ---------------------------------------------------------------------------
# One writer op per job
# ---------------------------------------------------------------------------


@needs_writer
def test_persisting_metadata_and_completing_the_job_is_one_write_transaction(
    seeded, quiet_side_effects, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _root, _images = seeded
    worker = _worker()

    with capture_sql(monkeypatch) as statements:
        job = worker._claim_job()
        assert job is not None
        before_run = len(statements)
        worker._run_job(job)
    run_statements = statements[before_run:]

    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "done" and _asset_state(db_path, job.path) == "done"
    commits = [sql for sql in run_statements if sql.strip().upper().startswith("COMMIT")]
    assert len(commits) == 1, (
        f"upsert + completion must be one transaction; saw {len(commits)} commits in:\n" + "\n".join(run_statements)
    )


@needs_writer
def test_upsert_and_completion_are_atomic_when_the_completion_step_fails(
    seeded, quiet_side_effects, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _root, _images = seeded
    worker = _worker()
    job = worker._claim_job()
    assert job is not None

    def failing_completion(_conn, _job):
        raise sqlite3.IntegrityError("injected completion failure")

    monkeypatch.setattr(indexer, "complete_metadata_job", failing_completion)
    worker._run_job(job)

    assert not _has_metadata(db_path, job.path), "an upsert must not survive a failed completion"
    assert _asset_state(db_path, job.path) == "pending"
    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "failed" and "injected completion failure" in row["error"]
    assert _done_jobs_without_metadata(db_path) == []


@needs_writer
def test_a_commit_failure_leaves_neither_the_upsert_nor_the_completion_and_the_retry_completes(
    seeded, quiet_side_effects, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.metadata_store._db import _connect
    from tests.test_db_writer import ScriptedConnection

    db_path, _root, _images = seeded
    clock = install_metadata_clock(monkeypatch)
    failing_commits = {"left": 0}

    def script(sql: str) -> BaseException | None:
        if sql == "COMMIT" and failing_commits["left"] > 0:
            failing_commits["left"] -= 1
            return sqlite3.OperationalError("database is locked")
        return None

    def connect() -> ScriptedConnection:
        conn = _connect()
        conn.isolation_level = None
        return ScriptedConnection(conn, script)

    db_writer = _writer_module()
    writer = db_writer.DatabaseWriter(connect=connect, retry_delays=(0.0,), sleep=lambda _seconds: None)
    writer.start()
    monkeypatch.setattr(db_writer, "database_writer", writer)
    worker = _worker()
    try:
        job = worker._claim_job()
        assert job is not None and job.attempts == 1
        failing_commits["left"] = 2  # the first attempt and its one retry; later commits succeed

        worker._run_job(job)

        assert not _has_metadata(db_path, job.path)
        assert _asset_state(db_path, job.path) == "pending"
        row = metadata_job_row(db_path, job.path)
        assert row["state"] == "queued" and row["attempts"] == 1, "a transient commit failure requeues the job"
        assert "locked" in row["error"]
        assert _done_jobs_without_metadata(db_path) == []

        clock.advance(indexer.metadata_retry_delay_seconds(1) + 0.01)
        retry = worker._claim_job()
        assert retry is not None and retry.path == job.path and retry.attempts == 2
        worker._run_job(retry)
        row = metadata_job_row(db_path, job.path)
        assert row["state"] == "done" and row["attempts"] == 2
        assert _has_metadata(db_path, job.path) and _asset_state(db_path, job.path) == "done"
    finally:
        writer.stop(timeout=5)


def test_a_stale_workers_result_is_fenced_inside_the_op_before_anything_is_written(
    seeded, quiet_side_effects, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db_path, _root, _images = seeded
    clock = install_metadata_clock(monkeypatch)
    store = _store()
    stale_worker = _worker()
    old = stale_worker._claim_job()
    assert old is not None
    clock.advance(LEASE_SECONDS + 1)
    assert indexer.recover_abandoned_metadata_jobs(expired_only=True)["reset"] == 1
    new = None
    while (candidate := store.claim_next_metadata_job(worker_id="new-worker", lease_seconds=LEASE_SECONDS)) is not None:
        if candidate.path == old.path:
            new = candidate
            break
    assert new is not None and new.claim_token != old.claim_token
    # The pre-write ownership check races with the reclaim; only the write itself can arbitrate.
    monkeypatch.setattr(stale_worker, "_owns_claim", lambda _job: True)

    stale_worker._run_job(old)

    row = metadata_job_row(db_path, old.path)
    assert row["state"] == "running" and row["claim_token"] == new.claim_token
    assert _asset_state(db_path, old.path) == "pending"
    if mode == "writer":
        assert not _has_metadata(db_path, old.path), "the fenced op writes nothing at all"
    else:
        assert _has_metadata(db_path, old.path), "the direct path still upserts before the fenced completion"


# ---------------------------------------------------------------------------
# Batched claims
# ---------------------------------------------------------------------------


def _seed_claim_order(db_path: Path, images: list[Path], now: float) -> None:
    plan = [
        (3, 100.0, None),  # job 0: late priority, queued 100
        (1, 300.0, None),  # job 1
        (1, 200.0, None),  # job 2: same priority, queued earlier than job 1
        (0, 500.0, now + 100),  # job 3: best priority but its retry backoff is not due
        (3, 50.0, None),  # job 4: oldest of the priority 3 rows
        (2, 400.0, None),  # job 5
    ]
    for image, (priority, queued_at, next_attempt_at) in zip(images, plan, strict=True):
        set_metadata_job(db_path, image, priority=priority, queued_at=queued_at, next_attempt_at=next_attempt_at)


def test_batched_claims_follow_the_single_claim_order_with_their_own_tokens_and_leases(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 6)
    clock = install_metadata_clock(monkeypatch)
    _seed_claim_order(db_path, images, clock.now)
    store = _store()

    claimed = store.claim_next_metadata_jobs(limit=4, worker_id="batch-worker", lease_seconds=45)

    assert [job.path for job in claimed] == [str(images[n]) for n in (2, 1, 5, 4)]
    assert len({job.claim_token for job in claimed}) == 4 and all(job.claim_token for job in claimed)
    for job in claimed:
        row = metadata_job_row(db_path, job.path)
        assert row["state"] == "running" and row["attempts"] == 1 and job.attempts == 1
        assert row["claimed_by"] == "batch-worker" and job.claimed_by == "batch-worker"
        assert row["claim_token"] == job.claim_token
        assert row["lease_expires_at"] == pytest.approx(clock.now + 45)
        assert row["started_at"] == pytest.approx(clock.now)
    assert metadata_job_row(db_path, images[0])["state"] == "queued"
    not_due = metadata_job_row(db_path, images[3])
    assert not_due["state"] == "queued" and not_due["claim_token"] is None, "a backed-off row is not due"

    rest = store.claim_next_metadata_jobs(limit=4, worker_id="batch-worker", lease_seconds=45)
    assert [job.path for job in rest] == [str(images[0])], "fewer due rows than the limit returns fewer jobs"
    assert store.claim_next_metadata_jobs(limit=4) == []
    assert store.claim_next_metadata_jobs(limit=0) == []

    clock.advance(101)
    late = store.claim_next_metadata_jobs(limit=2)
    assert [job.path for job in late] == [str(images[3])], "the row becomes claimable once it is due"


def test_batched_claims_equal_repeated_single_claims(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 6)
    clock = install_metadata_clock(monkeypatch)
    _seed_claim_order(db_path, images, clock.now)
    store = _store()

    singles = []
    while (job := store.claim_next_metadata_job(worker_id="single", lease_seconds=45)) is not None:
        singles.append(job.path)
    for image in images:  # put everything back for the batched run
        set_metadata_job(
            db_path, image, state="queued", attempts=0, claimed_by=None, claim_token=None, lease_expires_at=None
        )
    batched = store.claim_next_metadata_jobs(limit=50, worker_id="single", lease_seconds=45)

    assert [job.path for job in batched] == singles


@needs_writer
def test_a_claim_batch_is_a_single_writer_transaction(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    _db_path, _root, _images = seeded
    store = _store()

    with capture_sql(monkeypatch) as statements:
        claimed = store.claim_next_metadata_jobs(limit=3)

    assert len(claimed) == 3
    assert [sql for sql in statements if sql.strip().upper().startswith("BEGIN")] == ["BEGIN IMMEDIATE"]
    assert [sql for sql in statements if sql.strip().upper().startswith("COMMIT")] == ["COMMIT"]


def test_the_worker_claims_in_batches_renews_pending_claims_and_releases_them(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 5)
    clock = install_metadata_clock(monkeypatch)
    worker = _worker(claim_batch_size=3)

    first = worker._claim_job()
    second_row_claimed = [metadata_job_row(db_path, image)["state"] for image in images].count("running")
    assert first is not None and second_row_claimed == 3, "one claim call takes the whole batch"
    second, third = worker._claim_job(), worker._claim_job()
    assert second is not None and third is not None
    assert [first.path, second.path, third.path] == [str(image) for image in images[:3]]
    assert [metadata_job_row(db_path, image)["state"] for image in images].count("running") == 3

    # Holding claims longer than one job takes: the running job's heartbeat renews the pending claims too.
    fresh = worker._claim_job()  # opens a second batch (the first one is used up)
    assert fresh is not None and fresh.path == str(images[3])
    pending = worker._pending_claim_paths()
    assert pending == [str(images[4])]
    clock.advance(LEASE_SECONDS / 2)
    assert worker._renew_lease(fresh) is True
    renewed = metadata_job_row(db_path, images[4])
    assert renewed["lease_expires_at"] == pytest.approx(clock.now + LEASE_SECONDS)

    worker._release_pending_claims()
    released = metadata_job_row(db_path, images[4])
    assert released["state"] == "queued" and released["attempts"] == 0, "an unstarted claim costs no attempt"
    assert released["claim_token"] is None and released["lease_expires_at"] is None
    assert worker._pending_claim_paths() == []


@pytest.mark.parametrize("batch_size", [1, 3])
def test_the_worker_drains_every_job_end_to_end(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    quiet_side_effects,
    mode: str,
    batch_size: int,
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 5)
    worker = _worker(claim_batch_size=batch_size) if batch_size > 1 else _worker()
    worker.start()
    try:
        assert wait_until(
            lambda: all(metadata_job_row(db_path, image)["state"] == "done" for image in images), timeout=60
        ), [metadata_job_row(db_path, image)["state"] for image in images]
    finally:
        worker.stop()

    for image in images:
        row = metadata_job_row(db_path, image)
        assert row["attempts"] == 1 and row["claim_token"] is None and row["lease_expires_at"] is None
        assert _has_metadata(db_path, image) and _asset_state(db_path, image) == "done"
    assert indexer.get_indexer_runtime_status()["active_jobs"] == 0


# ---------------------------------------------------------------------------
# Lanes and the `_DB_LOCK` rule
# ---------------------------------------------------------------------------


@needs_writer
def test_claims_renewals_and_terminal_writes_use_the_priority_lane_and_recovery_the_normal_lane(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    quiet_side_effects,
    submit_log,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 5)
    clock = install_metadata_clock(monkeypatch)
    worker = _worker()
    real_extract = indexer.extract_metadata
    outcomes = {
        str(images[1]): ValueError("unreadable"),
        str(images[2]): OSError(errno.EAGAIN, "try again"),
    }

    def scripted_extract(path: Path):
        outcome = outcomes.get(str(path))
        if outcome is not None:
            raise outcome
        return real_extract(path)

    monkeypatch.setattr(indexer, "extract_metadata", scripted_extract)
    lanes: dict[str, list[str]] = {}

    def lanes_of(label: str, action) -> None:
        start = len(submit_log)
        action()
        lanes[label] = [entry.lane for entry in submit_log[start:]]

    jobs = {}
    lanes_of("claim", lambda: jobs.update({n: worker._claim_job() for n in range(4)}))
    lanes_of("renew", lambda: worker._renew_lease(jobs[0]))
    lanes_of("complete", lambda: worker._run_job(jobs[0]))
    lanes_of("fail", lambda: worker._run_job(jobs[1]))
    lanes_of("requeue", lambda: worker._run_job(jobs[2]))
    stat = Path(jobs[3].path).stat()
    os.utime(jobs[3].path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 9_000_000_000))
    lanes_of("stale", lambda: worker._run_job(jobs[3]))
    clock.advance(LEASE_SECONDS + 1)
    set_metadata_job(db_path, images[4], state="running", attempts=1, claim_token=None)
    lanes_of("recover", lambda: worker.supervise_once())

    assert metadata_job_row(db_path, images[0])["state"] == "done"
    assert metadata_job_row(db_path, images[1])["state"] == "failed"
    assert metadata_job_row(db_path, images[2])["state"] == "queued"
    assert metadata_job_row(db_path, images[3])["state"] == "stale"
    assert metadata_job_row(db_path, images[4])["state"] == "queued"
    for label in ("claim", "renew", "complete", "fail", "requeue", "stale"):
        assert lanes[label], f"{label} never reached the writer"
        assert set(lanes[label]) == {"priority"}, f"{label} used lanes {lanes[label]}"
    assert lanes["claim"] == ["priority"] * 1
    assert lanes["recover"] and set(lanes["recover"]) == {"normal"}


@needs_writer
def test_no_metadata_writer_call_is_made_while_holding_the_db_lock(
    isolated_metadata_db: Path, isolated_gallery_root: Path, quiet_side_effects, submit_log, monkeypatch
) -> None:
    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 4)
    real_extract = indexer.extract_metadata

    def flaky_extract(path: Path):
        if path.name == Path(images[0]).name:
            raise ValueError("permanent")
        return real_extract(path)

    monkeypatch.setattr(indexer, "extract_metadata", flaky_extract)
    worker = _worker()
    worker.start()
    try:
        assert wait_until(
            lambda: all(metadata_job_row(db_path, image)["state"] in {"done", "failed"} for image in images),
            timeout=60,
        )
    finally:
        worker.stop()

    assert submit_log, "the worker never used the writer"
    assert not [entry for entry in submit_log if entry.holds_db_lock], "a writer call was made holding _DB_LOCK"


def test_a_whole_job_lifecycle_needs_no_db_lock(seeded, quiet_side_effects, monkeypatch, mode: str) -> None:
    """Claim, extraction, and completion proceed while some other thread holds `_DB_LOCK` (the WK-02 root cause)."""
    db_path, _root, _images = seeded
    worker = _worker()
    handled: list[str] = []

    def lifecycle() -> None:
        job = worker._claim_job()
        assert job is not None
        worker._run_job(job)
        handled.append(job.path)

    finished, _result, error = run_while_db_lock_held(lifecycle, timeout=1.0 if mode == "direct" else 20.0)

    assert error is None
    if mode == "writer":
        assert finished, "the writer path must not queue behind _DB_LOCK"
    else:
        assert not finished, "control: the direct path does queue behind _DB_LOCK"
    # run_while_db_lock_held releases the holder afterwards, so the direct path completes too.
    assert len(handled) == 1
    assert metadata_job_row(db_path, handled[0])["state"] == "done"


def test_a_caller_holding_the_db_lock_uses_the_direct_path_instead_of_waiting_on_the_writer(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_writer = _writer_module()
    monkeypatch.setattr(db_writer, "DB_WRITER_ENABLED", True)
    store = _store()
    db_writer.database_writer.reset()

    with _DB_LOCK:
        job = store.claim_next_metadata_job()

    assert job is not None
    assert db_writer.database_writer.state == "idle", "the writer was never involved"


def test_writer_unavailability_is_a_transient_failure_for_retry_purposes() -> None:
    db_writer = _writer_module()
    for exc in (
        db_writer.DatabaseWriterClosed("closed"),
        db_writer.DatabaseWriterBackpressure("full"),
        db_writer.DatabaseWriterTimeout("slow"),
    ):
        assert indexer.is_transient_metadata_error(exc), type(exc).__name__
    assert not indexer.is_transient_metadata_error(db_writer.DatabaseWriterDeadlock("bug"))


# ---------------------------------------------------------------------------
# upsert_metadata_batch through the writer
# ---------------------------------------------------------------------------


@needs_writer
def test_upsert_metadata_batch_runs_on_the_writer_and_schedules_backfills_after_commit(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store.metadata_persist as metadata_persist

    db_path, _root, images = seeded
    store = _store()
    seen: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        metadata_persist,
        "_schedule_derived_search_backfills",
        lambda _library_id: seen.append((threading.current_thread().name, _has_metadata(db_path, images[0]))),
    )
    writer = _writer_module().database_writer
    writer.start()

    assert store.upsert_metadata_batch([extract_metadata(images[0])]) == 1

    assert seen == [(threading.current_thread().name, True)], "backfills are scheduled by the caller after the commit"
    assert writer.stats()["ops"] >= 1


@needs_writer
def test_upsert_metadata_batch_inside_a_writer_op_joins_the_transaction_and_defers_backfills(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store.metadata_persist as metadata_persist

    db_path, _root, images = seeded
    store = _store()
    scheduled: list[int] = []
    monkeypatch.setattr(metadata_persist, "_schedule_derived_search_backfills", scheduled.append)
    writer = _writer_module().database_writer
    writer.start()
    metadata = extract_metadata(images[0])

    def op(conn: sqlite3.Connection) -> tuple[int, bool]:
        persisted = store.upsert_metadata_batch([metadata])
        in_txn = conn.execute("SELECT 1 FROM image_metadata WHERE path = ?", (str(images[0]),)).fetchone() is not None
        return persisted, in_txn

    assert writer.run(op) == (1, True)
    assert scheduled == [], "the writer thread never schedules backfills (they may take _DB_LOCK)"
    assert _has_metadata(db_path, images[0])


# ---------------------------------------------------------------------------
# Maintenance producer gate
# ---------------------------------------------------------------------------


@needs_writer
def test_an_in_flight_writer_op_keeps_maintenance_from_starting(seeded) -> None:
    from backend.catalog_maintenance_gate import MaintenanceGateBusy, maintenance_gate
    from tests.test_db_writer import Blocker

    db_writer = _writer_module()
    blocker = Blocker()
    outcome: dict[str, Any] = {}

    def producer() -> None:
        outcome["value"] = db_writer.run_write(blocker, lane="priority", fallback=lambda: "direct")

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    try:
        assert blocker.entered.wait(10)
        with pytest.raises(MaintenanceGateBusy), maintenance_gate():
            pass
    finally:
        blocker.release.set()
        thread.join(10)
    assert outcome == {"value": "unblocked"}
    with maintenance_gate():  # quiesced again once the producer's op finished
        pass


@needs_writer
def test_active_maintenance_blocks_new_writer_ops_until_it_is_released(seeded) -> None:
    from backend.catalog_maintenance_gate import maintenance_gate

    _db_path, _root, _images = seeded
    store = _store()
    db_writer = _writer_module()
    db_writer.database_writer.reset()
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def producer() -> None:
        outcome["job"] = store.claim_next_metadata_job()
        done.set()

    with maintenance_gate():
        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        assert not done.wait(0.3), "a producer must wait while maintenance holds the gate"
        assert db_writer.database_writer.stats()["ops"] == 0, "no writer op may bypass the gate"
    assert done.wait(10), "releasing maintenance resumes the paused producer"
    thread.join(10)
    assert outcome["job"] is not None
    assert db_writer.database_writer.stats()["ops"] >= 1


@needs_writer
def test_the_maintenance_owner_may_still_use_metadata_writes(seeded) -> None:
    from backend.catalog_maintenance_gate import maintenance_gate

    store = _store()
    with maintenance_gate():
        job = store.claim_next_metadata_job()
    assert job is not None


# ---------------------------------------------------------------------------
# A dead writer is recovered by the Phase 1 leases
# ---------------------------------------------------------------------------


@needs_writer
def test_a_writer_that_dies_mid_queue_leaves_jobs_the_leases_requeue_and_nothing_done_without_metadata(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    quiet_side_effects,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.metadata_store._db import _connect
    from tests.test_db_writer import ScriptedConnection

    db_path, _root, images = _seed(isolated_metadata_db, isolated_gallery_root, 4)
    clock = install_metadata_clock(monkeypatch)
    dead = threading.Event()

    def script(_sql: str) -> BaseException | None:
        return sqlite3.OperationalError("disk I/O error") if dead.is_set() else None

    def connect() -> ScriptedConnection:
        conn = _connect()
        conn.isolation_level = None
        return ScriptedConnection(conn, script)

    db_writer = _writer_module()
    writer = db_writer.DatabaseWriter(connect=connect, retry_delays=(), sleep=lambda _seconds: None)
    writer.start()
    monkeypatch.setattr(db_writer, "database_writer", writer)
    worker = _worker()
    try:
        first = worker._claim_job()
        assert first is not None
        worker._run_job(first)
        assert metadata_job_row(db_path, first.path)["state"] == "done"

        second = worker._claim_job()
        assert second is not None
        dead.set()  # from here on no write ever commits: the writer is dead
        worker._run_job(second)  # extraction works, the writer op and the failure write both die
        with pytest.raises(sqlite3.OperationalError):
            worker._claim_job()

        states = {Path(row_path).name: metadata_job_row(db_path, row_path)["state"] for row_path in images}
        assert sorted(states.values()) == ["done", "queued", "queued", "running"], states
        assert metadata_job_row(db_path, second.path)["claim_token"] == second.claim_token
        assert not _has_metadata(db_path, second.path), "atomic op: the dead writer left no partial metadata"
        assert _done_jobs_without_metadata(db_path) == []

        # A restarted writer plus the Phase 1 lease recovery bring everything back.
        dead.clear()
        assert worker.supervise_once()["reset"] == 0, "the dead writer's claim is still within its lease"
        clock.advance(LEASE_SECONDS + 1)
        assert worker.supervise_once()["reset"] == 1
        assert metadata_job_row(db_path, second.path)["state"] == "queued"
        assert _done_jobs_without_metadata(db_path) == []

        while (job := worker._claim_job()) is not None:
            worker._run_job(job)
        for image in images:
            assert metadata_job_row(db_path, image)["state"] == "done"
            assert _has_metadata(db_path, image) and _asset_state(db_path, image) == "done"
    finally:
        writer.stop(timeout=5)


# ---------------------------------------------------------------------------
# Feature flag off: exactly the previous behaviour
# ---------------------------------------------------------------------------


def test_with_the_flag_off_the_direct_transactions_are_used_and_the_writer_never_starts(
    seeded, quiet_side_effects, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_writer = _writer_module()
    monkeypatch.setattr(db_writer, "DB_WRITER_ENABLED", False)
    db_writer.database_writer.reset()
    db_path, _root, _images = seeded
    worker = _worker()

    with capture_sql(monkeypatch) as statements:
        job = worker._claim_job()
        assert job is not None
        before_run = len(statements)
        worker._run_job(job)
    run_statements = statements[before_run:]

    assert metadata_job_row(db_path, job.path)["state"] == "done"
    commits = [sql for sql in run_statements if sql.strip().upper().startswith("COMMIT")]
    assert len(commits) == 2, "flag off keeps the previous shape: one commit for the upsert, one for the completion"
    assert db_writer.database_writer.state == "idle"
    assert db_writer.database_writer.stats()["ops"] == 0


# ---------------------------------------------------------------------------
# Static ownership guard
# ---------------------------------------------------------------------------


def test_metadata_lifecycle_ownership_check_passes_and_guards_the_new_helpers() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_metadata_lifecycle_ownership.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import check_metadata_lifecycle_ownership as ownership
    finally:
        sys.path.pop(0)
    assert {"claim_next_metadata_jobs", "release_metadata_job_claims"} <= set(ownership.LIFECYCLE_SYMBOLS)
