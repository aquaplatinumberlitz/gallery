"""Recovery of stale catalog jobs after server restart."""

import time
from pathlib import Path

import pytest
from backend.metadata_store import (
    _connect,
    _DB_LOCK,
    recover_stale_jobs,
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
        results = conn.execute(
            "SELECT type, state, message FROM library_jobs ORDER BY id"
        ).fetchall()
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
        row = conn.execute(
            "SELECT state FROM library_jobs WHERE type = 'maintenance'"
        ).fetchone()
        assert row["state"] == "running"  # untouched


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

    from backend.scan_worker import start, stop, runtime_status

    start()
    try:
        status = runtime_status()
        assert status["alive_workers"] > 0

        # Running job should now be failed
        with _DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT state, message FROM library_jobs WHERE type = 'scan'"
            ).fetchone()
            assert row["state"] == "failed"
            assert "Interrupted by server restart" in row["message"]
    finally:
        stop()
