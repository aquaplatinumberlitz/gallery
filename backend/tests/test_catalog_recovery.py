"""Recovery of stale catalog jobs after server restart.

Purpose:
Verify that catalog job recovery correctly handles orphaned running jobs
after a server restart, ensuring queued jobs are unblocked and no
non-recoverable state is corrupted.

Guarantees:
- Running scan/rebuild jobs are marked as failed with timestamps and message
- Queued, succeeded, and already-failed jobs are left unchanged
- Non-catalog job types (e.g. maintenance) are not affected
- Recovery is idempotent; a second call does nothing harmful
- After recovery, a queued job for the same library can be claimed
- Worker startup calls recovery before accepting new work

Run when:
Changing recover_stale_jobs, claim_next_catalog_job, or scan_worker.start()
"""

import time
from pathlib import Path

import pytest

from backend.metadata_store import (
    _DB_LOCK,
    _connect,
    claim_next_catalog_job,
    create_job,
    recover_stale_jobs,
    update_job_state,
)
from backend.metadata_store.job_store import _initialize_database


def _insert_library(conn, library_id: int, now: float) -> None:
    conn.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (library_id, "test", now, now),
    )


def test_recover_stale_jobs_marks_running_scan_rebuild_as_failed(
    isolated_metadata_db: Path,
):
    """Running scan/rebuild jobs are transitioned to failed with message."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "rebuild", now, now),
        )
        # Also add a queued job that should NOT be affected
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'queued', ?, ?)""",
            (1, "scan", now, now),
        )

    recovered = recover_stale_jobs()
    assert len(recovered) == 2

    # Check both running jobs became failed
    with _DB_LOCK, _connect() as conn:
        results = conn.execute("SELECT type, state, message FROM library_jobs ORDER BY id").fetchall()
        assert results[0]["type"] == "scan"
        assert results[0]["state"] == "failed"
        assert "Interrupted by server restart" in results[0]["message"]
        assert results[1]["type"] == "rebuild"
        assert results[1]["state"] == "failed"
        assert results[2]["type"] == "scan"
        assert results[2]["state"] == "queued"  # unchanged


def test_recover_stale_jobs_leaves_non_catalog_jobs(
    isolated_metadata_db: Path,
):
    """Non-catalog running jobs (e.g. maintenance) are NOT affected."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "maintenance", now, now),
        )

    recovered = recover_stale_jobs()
    assert len(recovered) == 0

    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT state FROM library_jobs WHERE type = 'maintenance'").fetchone()
        assert row["state"] == "running"  # untouched


def test_recover_stale_scan_all_parent_with_terminal_children(
    isolated_metadata_db: Path,
):
    """A scan_all command parent left running is reconciled from child results."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
    parent = create_job("scan_all", progress_total=1, message="Update all libraries queued")
    child = create_job("scan", library_id=1, parent_job_id=int(parent["id"]))
    update_job_state(int(parent["id"]), "running", progress_total=1)
    update_job_state(int(child["id"]), "running")
    update_job_state(int(child["id"]), "succeeded")

    recovered = recover_stale_jobs()
    recovered_by_id = {job["id"]: job for job in recovered}

    assert recovered_by_id[parent["id"]]["state"] == "succeeded"
    assert recovered_by_id[parent["id"]]["message"] == "Update all libraries completed"


@pytest.mark.parametrize("parent_type", ["scan_all", "rebuild_imported_data"])
def test_recover_stale_parent_without_children_fails(
    isolated_metadata_db: Path,
    parent_type: str,
):
    """Queued/running parent jobs with no children cannot represent active work after restart."""
    _initialize_database()
    parent = create_job(parent_type, progress_total=1, message="Parent queued")
    update_job_state(int(parent["id"]), "running", progress_total=1)

    recovered = recover_stale_jobs()
    recovered_by_id = {job["id"]: job for job in recovered}

    assert recovered_by_id[parent["id"]]["state"] == "failed"
    assert recovered_by_id[parent["id"]]["message"] == "Interrupted by server restart"


def test_recover_stale_jobs_leaves_terminal_states(
    isolated_metadata_db: Path,
):
    """Succeeded and already-failed catalog jobs are not affected by recovery."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (1, "scan", "succeeded", now, now),
        )
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (1, "rebuild", "failed", now, now),
        )

    recovered = recover_stale_jobs()
    assert len(recovered) == 0

    with _DB_LOCK, _connect() as conn:
        rows = conn.execute("SELECT type, state FROM library_jobs ORDER BY id").fetchall()
        assert rows[0]["state"] == "succeeded"
        assert rows[1]["state"] == "failed"


def test_recover_stale_jobs_sets_timestamps_and_error(
    isolated_metadata_db: Path,
):
    """Recovery sets finished_at, updated_at, and a clear error/reason message."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )

    recovered = recover_stale_jobs()
    assert len(recovered) == 1
    job = recovered[0]
    assert job["state"] == "failed"
    assert job["error"] == "Interrupted by server restart"
    assert job["message"] == "Interrupted by server restart"
    assert job["finished_at"] is not None
    assert job["updated_at"] is not None
    assert job["finished_at"] > 0


def test_recover_stale_jobs_is_idempotent(
    isolated_metadata_db: Path,
):
    """Running recovery twice recovers jobs the first time and does nothing the second."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )

    first = recover_stale_jobs()
    assert len(first) == 1
    assert first[0]["state"] == "failed"

    second = recover_stale_jobs()
    assert len(second) == 0  # Nothing left to recover

    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT state, message FROM library_jobs WHERE type = 'scan'").fetchone()
        assert row["state"] == "failed"
        assert "Interrupted by server restart" in row["message"]


def test_recover_stale_jobs_unblocks_queued_job(
    isolated_metadata_db: Path,
):
    """After recovery, a queued job for the same library as a stale running job can be claimed."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        # Stale running job - would block claim
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )
        # Queued job for same library
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'queued', ?, ?)""",
            (1, "scan", now, now),
        )

    recover_stale_jobs()

    claimed = claim_next_catalog_job(max_queue_wait_seconds=600)
    assert claimed is not None
    assert claimed["state"] == "running"
    assert claimed["library_id"] == 1


def test_scan_worker_start_calls_recovery_before_worker_claim(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """scan_worker.start() recovers running jobs before spawning workers."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        # Insert running job that would block new claims
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )

    from backend.scan_worker import runtime_status, start, stop

    start()
    try:
        status = runtime_status()
        assert status["alive_workers"] > 0

        # Running job should now be failed
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state, message FROM library_jobs WHERE type = 'scan'").fetchone()
            assert row["state"] == "failed"
            assert "Interrupted by server restart" in row["message"]
    finally:
        stop()


def test_scan_worker_ensure_running_does_not_recover_when_service_disabled(
    isolated_metadata_db: Path,
):
    """Runtime health checks are passive when the catalog service is disabled."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )

    from backend.scan_worker import ensure_running, stop

    stop()
    status = ensure_running(service_enabled=False)

    assert status["alive_workers"] == 0
    assert status["recovered_jobs"] == 0
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT state FROM library_jobs WHERE type = 'scan'").fetchone()
        assert row["state"] == "running"


def test_scan_worker_ensure_running_recovers_running_job_when_workers_dead(
    isolated_metadata_db: Path,
):
    """If no worker is alive, runtime recovery fails orphaned running work and restarts the pool."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        _insert_library(conn, 1, now)
        conn.execute(
            """INSERT INTO library_jobs
               (library_id, type, state, created_at, updated_at)
               VALUES (?, ?, 'running', ?, ?)""",
            (1, "scan", now, now),
        )

    from backend.scan_worker import ensure_running, stop

    stop()
    try:
        status = ensure_running(service_enabled=True)

        assert status["alive_workers"] > 0
        assert status["recovered_jobs"] == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state, message, error FROM library_jobs WHERE type = 'scan'").fetchone()
            assert row["state"] == "failed"
            assert row["message"] == "Catalog worker stopped before completing the job"
            assert row["error"] == "Catalog worker stopped before completing the job"
    finally:
        stop()
