"""WK-04 regression: an orphaned ``running`` metadata job must be recoverable without a restart.

Purpose:
Pin the worker-lifecycle audit finding WK-04. A metadata job whose failure write also hit
``database is locked`` stayed ``running`` forever: the integrity checker and dispatch both
preserved ``running`` rows, nothing ever re-claimed them, and the runtime reported one phantom
active job until the process restarted.

Guarantees:
Claiming a metadata job records owner, claim token, and lease; completion, failure, stale,
requeue, and lease-renewal writes are fenced by the claim token so a stale worker's write after a
reclaim changes zero rows; a heartbeat keeps a slow extraction's lease alive; the supervisor and
startup recovery share one attempt-aware function that requeues expired or ownerless ``running``
rows and leaves live claims alone; the integrity checker and dispatch stop preserving expired
``running`` rows; the supervisor thread starts and stops with the worker; and the runtime
``active_jobs`` counter returns to zero.

Run when:
Changing metadata job claim/lease columns, ``claim_next_metadata_job``, the metadata worker,
its supervisor or heartbeat, metadata startup recovery, or the integrity checker's metadata checks.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from backend import indexer
from backend.indexer import MetadataLifecycleWorker
from backend.metadata_extract import extract_metadata
from backend.metadata_store import _DB_LOCK, MAX_METADATA_JOB_ATTEMPTS, _connect
from tests.worker_contention_support import (
    install_metadata_clock,
    metadata_job_row,
    seed_queued_metadata_jobs,
    set_metadata_job,
)

LEASE_SECONDS = 30


@pytest.fixture
def seeded(isolated_metadata_db: Path, isolated_gallery_root: Path) -> tuple[Path, Path, list[Path]]:
    """One library with three queued metadata jobs: ``(db_path, root, image_paths)``."""
    root = isolated_gallery_root / "photos"
    _library_id, images = seed_queued_metadata_jobs(root, 3)
    return isolated_metadata_db, root, images


def _metadata_store():
    import backend.metadata_store as metadata_store

    return metadata_store


def _upsert_current_metadata(path: Path) -> None:
    _metadata_store().upsert_metadata_batch([extract_metadata(path)])


def _asset_metadata_state(db_path: Path, path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (str(path),)).fetchone()[0])


def _make_worker(**kwargs) -> MetadataLifecycleWorker:
    kwargs.setdefault("lease_seconds", LEASE_SECONDS)
    kwargs.setdefault("heartbeat_seconds", LEASE_SECONDS / 3)
    kwargs.setdefault("write_retry_delays", ())
    return MetadataLifecycleWorker(worker_count=1, **kwargs)


# ---------------------------------------------------------------------------
# Schema and claim
# ---------------------------------------------------------------------------


def test_claim_records_owner_token_and_lease(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    clock = install_metadata_clock(monkeypatch)

    job = _metadata_store().claim_next_metadata_job(worker_id="worker-a", lease_seconds=45)

    assert job is not None and job.claim_token
    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "running" and row["attempts"] == 1 and job.attempts == 1
    assert row["claimed_by"] == "worker-a"
    assert row["claim_token"] == job.claim_token
    assert row["lease_expires_at"] == pytest.approx(clock.now + 45)
    assert job.path in {str(image) for image in images}


def test_every_claim_gets_its_own_token(seeded) -> None:
    store = _metadata_store()
    first = store.claim_next_metadata_job(worker_id="w", lease_seconds=LEASE_SECONDS)
    second = store.claim_next_metadata_job(worker_id="w", lease_seconds=LEASE_SECONDS)
    assert first is not None and second is not None
    assert first.claim_token and second.claim_token and first.claim_token != second.claim_token


def test_default_lease_comes_from_configuration(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.config as config

    clock = install_metadata_clock(monkeypatch)
    job = _metadata_store().claim_next_metadata_job()
    assert job is not None
    row = metadata_job_row(seeded[0], job.path)
    assert row["lease_expires_at"] == pytest.approx(clock.now + config.METADATA_JOB_LEASE_SECONDS)


def test_claim_columns_and_lease_index_exist_on_fresh_and_existing_databases(
    isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store as ms
    from backend.metadata_store.schema_check import check_catalog_schema

    columns = ("claimed_by", "claim_token", "lease_expires_at", "next_attempt_at")
    index_name = "idx_metadata_index_jobs_state_lease"

    def table_columns() -> set[str]:
        with sqlite3.connect(isolated_metadata_db) as conn:
            return {row[1] for row in conn.execute("PRAGMA table_info(metadata_index_jobs)")}

    def has_index() -> bool:
        with sqlite3.connect(isolated_metadata_db) as conn:
            return (
                conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (index_name,)).fetchone()
                is not None
            )

    assert set(columns) <= table_columns(), "fresh DDL/ensure must create the claim columns"
    assert has_index()

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        for column in columns:
            conn.execute(f"ALTER TABLE metadata_index_jobs DROP COLUMN {column}")
    assert not set(columns) & table_columns()
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)

    ms.initialize_database()

    assert set(columns) <= table_columns(), "the additive ensure path must add the columns to an existing database"
    assert has_index()
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        assert check_catalog_schema(conn) == []


# ---------------------------------------------------------------------------
# Fencing: a stale worker cannot overwrite a newer claim
# ---------------------------------------------------------------------------


def test_stale_workers_writes_after_reclaim_change_zero_rows(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, _images = seeded
    store = _metadata_store()
    clock = install_metadata_clock(monkeypatch)

    old = store.claim_next_metadata_job(worker_id="old-worker", lease_seconds=LEASE_SECONDS)
    assert old is not None
    clock.advance(LEASE_SECONDS + 1)
    recovered = indexer.recover_abandoned_metadata_jobs(expired_only=True)
    assert recovered == {"reset": 1, "failed": 0}
    new = None
    while (candidate := store.claim_next_metadata_job(worker_id="new-worker", lease_seconds=LEASE_SECONDS)) is not None:
        if candidate.path == old.path:
            new = candidate
            break
    assert new is not None and new.claim_token != old.claim_token

    # Metadata exists and the asset matches, so an unfenced completion would mark the job done.
    _upsert_current_metadata(Path(old.path))
    with _DB_LOCK, _connect() as conn:
        assert store.complete_metadata_job(conn, old) is False
        assert store.fail_metadata_job(conn, old, "late failure") is False
        assert store.mark_metadata_job_stale(conn, old) is False
        assert store.requeue_metadata_job(conn, old, "late retry", delay_seconds=5) is False
        assert store.renew_metadata_job_lease(conn, old, lease_seconds=LEASE_SECONDS) is False

    row = metadata_job_row(db_path, old.path)
    assert row["state"] == "running"
    assert row["claim_token"] == new.claim_token and row["claimed_by"] == "new-worker"
    assert row["error"] is None
    assert _asset_metadata_state(db_path, Path(old.path)) == "pending", "a stale completion must not stamp the asset"

    with _DB_LOCK, _connect() as conn:
        assert store.complete_metadata_job(conn, new) is True
    row = metadata_job_row(db_path, old.path)
    assert row["state"] == "done"
    assert row["claim_token"] is None and row["claimed_by"] is None and row["lease_expires_at"] is None
    assert _asset_metadata_state(db_path, Path(old.path)) == "done"


def test_dispatch_of_a_changed_file_fences_the_old_claim(seeded) -> None:
    db_path, root, images = seeded
    store = _metadata_store()
    old = store.claim_next_metadata_job(worker_id="old-worker", lease_seconds=LEASE_SECONDS)
    assert old is not None
    path = Path(old.path)
    stat = path.stat()
    import os

    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    indexer.dispatch_metadata_index_paths([path], root)

    row = metadata_job_row(db_path, path)
    assert row["state"] == "queued" and row["attempts"] == 0
    assert row["claim_token"] is None and row["lease_expires_at"] is None
    with _DB_LOCK, _connect() as conn:
        assert store.complete_metadata_job(conn, old) is False
        assert store.fail_metadata_job(conn, old, "late failure") is False
    assert metadata_job_row(db_path, path)["state"] == "queued"
    assert images  # the other seeded jobs are untouched
    assert all(metadata_job_row(db_path, other)["state"] == "queued" for other in images if str(other) != old.path)


# ---------------------------------------------------------------------------
# Recovery policy shared by the supervisor and startup
# ---------------------------------------------------------------------------


def test_recovery_is_attempt_aware_and_leaves_live_claims_alone(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    clock = install_metadata_clock(monkeypatch)
    ownerless, exhausted, live = images
    set_metadata_job(db_path, ownerless, state="running", attempts=1, started_at=clock.now - 5)
    set_metadata_job(
        db_path,
        exhausted,
        state="running",
        attempts=MAX_METADATA_JOB_ATTEMPTS,
        claimed_by="gone",
        claim_token="expired-token",
        lease_expires_at=clock.now - 1,
    )
    set_metadata_job(
        db_path,
        live,
        state="running",
        attempts=1,
        claimed_by="busy",
        claim_token="live-token",
        lease_expires_at=clock.now + 60,
    )

    result = indexer.recover_abandoned_metadata_jobs(expired_only=True)

    assert result == {"reset": 1, "failed": 1}
    row = metadata_job_row(db_path, ownerless)
    assert row["state"] == "queued" and row["attempts"] == 1 and row["claim_token"] is None
    row = metadata_job_row(db_path, exhausted)
    assert row["state"] == "failed" and row["error"] == "exhausted recovery attempts"
    assert row["claim_token"] is None and row["lease_expires_at"] is None
    row = metadata_job_row(db_path, live)
    assert row["state"] == "running" and row["claim_token"] == "live-token"
    assert row["lease_expires_at"] == pytest.approx(clock.now + 60)


def test_startup_recovery_and_supervisor_share_one_function(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    clock = install_metadata_clock(monkeypatch)
    set_metadata_job(
        db_path,
        images[0],
        state="running",
        attempts=1,
        claimed_by="previous-process",
        claim_token="stale-token",
        lease_expires_at=clock.now + 600,
    )
    calls: list[dict] = []
    real = indexer.recover_running_metadata_jobs

    def spy(conn, **kwargs):
        calls.append(kwargs)
        return real(conn, **kwargs)

    monkeypatch.setattr(indexer, "recover_running_metadata_jobs", spy)

    summary = indexer.recover_metadata_index_jobs()
    assert summary["running_reset"] == 1
    assert calls and calls[-1]["expired_only"] is False, (
        "startup recovery ignores leases: nothing owns them after a restart"
    )
    row = metadata_job_row(db_path, images[0])
    assert row["state"] == "queued" and row["claim_token"] is None and row["lease_expires_at"] is None

    _make_worker().supervise_once()
    assert calls[-1]["expired_only"] is True


# ---------------------------------------------------------------------------
# The orphan scenario from the audit
# ---------------------------------------------------------------------------


def test_orphaned_job_is_reclaimed_after_lease_expiry_and_completes(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    clock = install_metadata_clock(monkeypatch)
    store = _metadata_store()
    for extra in images[1:]:
        set_metadata_job(db_path, extra, state="done")  # leave exactly one runnable job
    worker = _make_worker()
    real_extract = indexer.extract_metadata
    extract_calls: list[str] = []

    def flaky_extract(path: Path):
        extract_calls.append(str(path))
        if len(extract_calls) == 1:
            raise ValueError("boom")
        return real_extract(path)

    def locked_failure_write(_conn, _job, _error):
        raise sqlite3.OperationalError("database is locked")

    real_fail = indexer.fail_metadata_job
    monkeypatch.setattr(indexer, "extract_metadata", flaky_extract)
    monkeypatch.setattr(indexer, "fail_metadata_job", locked_failure_write)

    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)  # extraction fails, then the failure write hits "database is locked"

    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "running" and row["claim_token"] == job.claim_token, "the orphan scenario was not reproduced"
    assert indexer.get_indexer_runtime_status()["active_jobs"] == 1

    clock.advance(LEASE_SECONDS / 2)
    assert worker.supervise_once()["reset"] == 0, "a live, unexpired claim must stay protected"
    assert metadata_job_row(db_path, job.path)["state"] == "running"

    clock.advance(LEASE_SECONDS)
    assert worker.supervise_once()["reset"] == 1
    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "queued" and row["attempts"] == 1 and row["claim_token"] is None

    monkeypatch.setattr(indexer, "fail_metadata_job", real_fail)
    second = worker._claim_job()
    assert second is not None and second.path == job.path and second.claim_token != job.claim_token
    worker._run_job(second)

    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "done" and row["attempts"] == 2
    assert row["claim_token"] is None and row["lease_expires_at"] is None
    assert _asset_metadata_state(db_path, Path(job.path)) == "done"
    assert store.claim_next_metadata_job() is None
    assert indexer.get_indexer_runtime_status()["active_jobs"] == 0
    from backend.metadata_store.status_store import build_global_runtime

    assert build_global_runtime()["metadata_active_jobs"] == 0


def test_slow_extraction_with_a_live_heartbeat_is_not_reclaimed(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    for extra in images[1:]:
        set_metadata_job(db_path, extra, state="done")
    worker = _make_worker(lease_seconds=0.6, heartbeat_seconds=0.05)
    entered, release, renewed = threading.Event(), threading.Event(), threading.Event()
    renewals: list[bool] = []
    real_renew = worker._renew_lease
    real_extract = indexer.extract_metadata

    def counting_renew(job):
        result = real_renew(job)
        renewals.append(result)
        if len(renewals) >= 3:
            renewed.set()
        return result

    def blocking_extract(path: Path):
        entered.set()
        assert release.wait(30), "extraction was never released"
        return real_extract(path)

    monkeypatch.setattr(worker, "_renew_lease", counting_renew)
    monkeypatch.setattr(indexer, "extract_metadata", blocking_extract)
    job = worker._claim_job()
    assert job is not None
    first_expiry = metadata_job_row(db_path, job.path)["lease_expires_at"]
    thread = threading.Thread(target=worker._run_job, args=(job,), daemon=True)
    thread.start()
    try:
        assert entered.wait(10)
        assert renewed.wait(10), "the heartbeat never renewed the lease"
        # Three renewals take at least three heartbeat intervals, so the lease now outlives its original expiry.
        assert worker.supervise_once(now=first_expiry + 0.01)["reset"] == 0
        row = metadata_job_row(db_path, job.path)
        assert row["state"] == "running" and row["claim_token"] == job.claim_token
        assert row["lease_expires_at"] > first_expiry
    finally:
        release.set()
        thread.join(30)

    assert all(renewals)
    row = metadata_job_row(db_path, job.path)
    assert row["state"] == "done" and row["attempts"] == 1
    assert row["claim_token"] is None


def test_without_a_heartbeat_the_same_slow_job_would_be_reclaimed(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """Control for the heartbeat test: an unrenewed lease does expire at its original time."""
    db_path, _root, _images = seeded
    store = _metadata_store()
    job = store.claim_next_metadata_job(worker_id="slow", lease_seconds=0.6)
    assert job is not None
    expiry = metadata_job_row(db_path, job.path)["lease_expires_at"]

    assert _make_worker().supervise_once(now=expiry - 0.01)["reset"] == 0
    assert _make_worker().supervise_once(now=expiry + 0.01)["reset"] == 1


# ---------------------------------------------------------------------------
# Integrity checker and dispatch stop preserving expired ``running`` rows
# ---------------------------------------------------------------------------


def test_integrity_pass_recovers_expired_running_but_protects_live_claims(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.integrity_checker import integrity_checker

    db_path, _root, images = seeded
    orphan, live, _queued = images
    now = time.time()
    set_metadata_job(
        db_path, orphan, state="running", attempts=1, claimed_by="gone", claim_token="t1", lease_expires_at=now - 60
    )
    set_metadata_job(
        db_path, live, state="running", attempts=1, claimed_by="busy", claim_token="t2", lease_expires_at=now + 600
    )

    integrity_checker.run_all_checks()

    row = metadata_job_row(db_path, orphan)
    assert row["state"] == "queued", "an expired claim must be recovered by the integrity pass"
    assert row["claim_token"] is None and row["attempts"] == 1
    row = metadata_job_row(db_path, live)
    assert row["state"] == "running" and row["claim_token"] == "t2", "a live claim must stay protected"


def test_integrity_pass_recovers_ownerless_running_rows(seeded) -> None:
    from backend.integrity_checker import integrity_checker

    db_path, _root, images = seeded
    set_metadata_job(db_path, images[0], state="running", attempts=1)

    integrity_checker.run_all_checks()

    assert metadata_job_row(db_path, images[0])["state"] == "queued"


def test_dispatch_requeues_an_expired_running_job_but_coalesces_a_live_one(seeded) -> None:
    db_path, root, images = seeded
    orphan, live, _queued = images
    now = time.time()
    set_metadata_job(
        db_path, orphan, state="running", attempts=1, claimed_by="gone", claim_token="t1", lease_expires_at=now - 60
    )
    set_metadata_job(
        db_path, live, state="running", attempts=1, claimed_by="busy", claim_token="t2", lease_expires_at=now + 600
    )

    indexer.dispatch_metadata_index_paths([orphan, live], root)

    row = metadata_job_row(db_path, orphan)
    assert row["state"] == "queued" and row["claim_token"] is None and row["attempts"] == 1
    row = metadata_job_row(db_path, live)
    assert row["state"] == "running" and row["claim_token"] == "t2"


def test_dispatch_fails_an_expired_running_job_whose_attempts_are_exhausted(seeded) -> None:
    db_path, root, images = seeded
    set_metadata_job(
        db_path,
        images[0],
        state="running",
        attempts=MAX_METADATA_JOB_ATTEMPTS,
        claimed_by="gone",
        claim_token="t1",
        lease_expires_at=time.time() - 60,
    )

    result = indexer.dispatch_metadata_index_paths([images[0]], root)

    assert result["failed"] == 1
    assert metadata_job_row(db_path, images[0])["state"] == "failed"


# ---------------------------------------------------------------------------
# Supervisor thread
# ---------------------------------------------------------------------------


def test_supervisor_thread_reclaims_orphans_and_stops_with_the_worker(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, _root, images = seeded
    for extra in images[1:]:
        set_metadata_job(db_path, extra, state="done")
    set_metadata_job(
        db_path, images[0], state="running", attempts=1, claimed_by="gone", claim_token="t", lease_expires_at=1.0
    )
    worker = _make_worker(supervisor_interval_seconds=0.05)
    results: list[dict[str, int]] = []
    reclaimed = threading.Event()
    real_supervise = worker.supervise_once

    def spy(now=None):
        result = real_supervise(now)
        results.append(result)
        if result["reset"]:
            reclaimed.set()
        return result

    monkeypatch.setattr(worker, "supervise_once", spy)

    worker.start()
    try:
        assert reclaimed.wait(15), "the supervisor never reclaimed the orphaned job"
        names = {thread.name for thread in threading.enumerate()}
        assert "gallery-metadata-supervisor" in names
    finally:
        started = time.monotonic()
        worker.stop()
        elapsed = time.monotonic() - started

    assert elapsed < 2.0, "stop() must stay within the bounded shutdown"
    assert not worker.is_running()
    assert "gallery-metadata-supervisor" not in {thread.name for thread in threading.enumerate()}
    assert sum(result["reset"] for result in results) == 1


def test_supervisor_restores_dead_worker_slots_but_never_starts_an_unstarted_worker(seeded) -> None:
    worker = _make_worker()
    worker.supervise_once()
    assert worker.alive_worker_count() == 0, "supervise_once must not spawn workers before start()"

    worker.start()
    try:
        assert worker.alive_worker_count() == 1
        worker._stop_event.set()  # let the live worker exit without going through stop()
        for thread in list(worker._threads):
            thread.join(5)
        assert worker.alive_worker_count() == 0
        worker._stop_event.clear()
        worker.supervise_once()
        assert worker.alive_worker_count() == 1
    finally:
        worker.stop()


def test_app_lifespan_starts_and_stops_the_supervisor(monkeypatch: pytest.MonkeyPatch, seeded) -> None:
    import asyncio

    import backend.app as app_module

    monkeypatch.setattr(app_module, "GALLERY_CATALOG_SERVICE_ENABLED", False)
    monkeypatch.setattr(app_module, "GALLERY_SEARCH_INDEXER_ENABLED", False)
    monkeypatch.setattr(app_module, "INTEGRITY_CHECK_ENABLED", False)
    monkeypatch.setattr(app_module, "validate_trusted_proxy_configuration", lambda: None)
    monkeypatch.setattr(app_module, "recover_stale_jobs", lambda: None)
    monkeypatch.setattr(app_module.scheduler, "start", lambda: None)
    monkeypatch.setattr(app_module.scheduler, "stop", lambda: None)
    monkeypatch.setattr(app_module, "_start_refresh", lambda: None)
    monkeypatch.setattr(app_module, "_stop_refresh", lambda: None)
    monkeypatch.setattr(app_module, "_start_watcher", lambda: None)
    monkeypatch.setattr(app_module, "_stop_watcher", lambda: None)
    monkeypatch.setattr(app_module.metadata_indexer, "METADATA_INDEXER_ENABLED", True)
    seen: dict[str, bool] = {}

    async def exercise() -> None:
        async with app_module._lifespan(app_module.app):
            names = {thread.name for thread in threading.enumerate()}
            seen["supervisor_running"] = "gallery-metadata-supervisor" in names

    asyncio.run(exercise())

    assert seen == {"supervisor_running": True}
    assert "gallery-metadata-supervisor" not in {thread.name for thread in threading.enumerate()}
    assert not indexer.metadata_worker.is_running()


def test_supervisor_interval_and_lease_defaults() -> None:
    import backend.config as config

    assert config.METADATA_SUPERVISOR_INTERVAL_SECONDS == 30
    assert indexer.metadata_worker.supervisor_interval_seconds == 30
    assert indexer.metadata_worker.lease_seconds == config.METADATA_JOB_LEASE_SECONDS
    assert indexer.metadata_worker.heartbeat_seconds == pytest.approx(config.METADATA_JOB_LEASE_SECONDS / 3)


def test_lease_heartbeat_keeps_renewing_after_a_renewal_raises() -> None:
    from backend.lease_heartbeat import LeaseHeartbeat

    calls: list[int] = []
    enough = threading.Event()

    def renew() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("renewal exploded")
        if len(calls) >= 3:
            enough.set()

    heartbeat = LeaseHeartbeat(renew, 0.05, name="test-lease-heartbeat")
    heartbeat.start()
    try:
        assert enough.wait(10), "the heartbeat died after one failing renewal"
    finally:
        heartbeat.stop()
    assert not heartbeat._thread.is_alive()
    heartbeat.stop()  # idempotent
