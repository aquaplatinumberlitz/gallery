"""Durable catalog claim, lease, and migration regressions.

Purpose:
Verify multi-worker catalog ownership, fenced terminal writes, and schema v3.

Guarantees:
Only dead/expired claims recover, live heartbeats remain owned, stale workers
cannot complete newer claims, and the v2-to-v3 migration backs up and rolls back.

Run when:
Changing catalog workers, library_jobs claims, supervisor recovery, or schema.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from backend import scan_worker
from backend.metadata_store import (
    _DB_LOCK,
    _connect,
    claim_next_catalog_job,
    create_library,
    create_or_coalesce_catalog_job,
    recover_stale_jobs,
    renew_catalog_job_lease,
    update_job_state,
)
from backend.metadata_store import _schema as schema_module


@pytest.fixture(autouse=True)
def _isolated_database(isolated_metadata_db: Path) -> None:
    """Keep every claim test on a fresh schema."""


def _queued_job(root: Path, name: str) -> tuple[int, dict]:
    library_root = root / name
    library_root.mkdir()
    library_id = int(create_library([library_root])["id"])
    job, _created = create_or_coalesce_catalog_job(library_id, trigger="manual", priority=100)
    return library_id, job


def test_partial_worker_death_recovers_only_dead_owner(
    isolated_gallery_root: Path,
) -> None:
    _queued_job(isolated_gallery_root, "one")
    _queued_job(isolated_gallery_root, "two")
    first = claim_next_catalog_job(worker_id="worker-a", lease_seconds=60)
    second = claim_next_catalog_job(worker_id="worker-b", lease_seconds=60)
    assert first is not None and second is not None

    recovered = recover_stale_jobs(
        reason="dead worker",
        live_worker_ids={"worker-b"},
    )
    assert [job["id"] for job in recovered] == [first["id"]]
    with _DB_LOCK, _connect() as conn:
        states = {
            int(row["id"]): row["state"]
            for row in conn.execute(
                "SELECT id, state FROM library_jobs WHERE id IN (?, ?)", (first["id"], second["id"])
            )
        }
    assert states == {first["id"]: "failed", second["id"]: "running"}


def test_heartbeat_renewal_wins_until_lease_truly_expires(
    isolated_gallery_root: Path,
) -> None:
    _queued_job(isolated_gallery_root, "heartbeat")
    job = claim_next_catalog_job(worker_id="live-worker", lease_seconds=1)
    assert job is not None
    assert renew_catalog_job_lease(job["id"], job["claim_token"], lease_seconds=60)
    assert recover_stale_jobs(live_worker_ids={"live-worker"}) == []

    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, job["id"]))
    recovered = recover_stale_jobs(live_worker_ids={"live-worker"})
    assert [item["id"] for item in recovered] == [job["id"]]


def test_stale_completion_cannot_overwrite_newer_claim(
    isolated_gallery_root: Path,
) -> None:
    _queued_job(isolated_gallery_root, "fenced")
    first = claim_next_catalog_job(worker_id="worker-a", lease_seconds=60)
    assert first is not None
    recover_stale_jobs(reason="worker died", live_worker_ids=set())
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE library_jobs SET state = 'queued', finished_at = NULL, error = NULL WHERE id = ?",
            (first["id"],),
        )
    second = claim_next_catalog_job(worker_id="worker-b", lease_seconds=60)
    assert second is not None and second["id"] == first["id"]

    assert update_job_state(first["id"], "succeeded", claim_token=first["claim_token"]) is None
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT state, claim_token FROM library_jobs WHERE id = ?",
            (first["id"],),
        ).fetchone()
    assert tuple(row) == ("running", second["claim_token"])
    assert update_job_state(second["id"], "succeeded", claim_token=second["claim_token"]) is not None


def test_startup_recovery_treats_prior_process_owner_as_dead(
    isolated_gallery_root: Path,
) -> None:
    _queued_job(isolated_gallery_root, "startup")
    job = claim_next_catalog_job(worker_id="prior-process", lease_seconds=3600)
    assert job is not None
    recovered = recover_stale_jobs()
    assert [item["id"] for item in recovered] == [job["id"]]


def test_supervisor_recovery_with_one_live_worker(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _queued_job(isolated_gallery_root, "dead")
    _queued_job(isolated_gallery_root, "live")
    dead_job = claim_next_catalog_job(worker_id="worker-dead", lease_seconds=60)
    live_job = claim_next_catalog_job(worker_id="worker-live", lease_seconds=60)
    assert dead_job is not None and live_job is not None

    class FakeThread:
        def __init__(self, worker_id: str, alive: bool) -> None:
            self._gallery_worker_id = worker_id
            self._alive = alive

        def is_alive(self) -> bool:
            return self._alive

    monkeypatch.setattr(
        scan_worker,
        "_worker_threads",
        [FakeThread("worker-dead", False), FakeThread("worker-live", True)],
    )
    monkeypatch.setattr(scan_worker, "GALLERY_CATALOG_WORKERS", 2)
    monkeypatch.setattr(scan_worker, "_spawn_missing_workers_locked", lambda: None)
    scan_worker._stop_event.clear()

    status = scan_worker.ensure_running(service_enabled=True)
    assert status["recovered_jobs"] == 1
    with _DB_LOCK, _connect() as conn:
        states = {
            int(row["id"]): row["state"]
            for row in conn.execute(
                "SELECT id, state FROM library_jobs WHERE id IN (?, ?)",
                (dead_job["id"], live_job["id"]),
            )
        }
    assert states == {dead_job["id"]: "failed", live_job["id"]: "running"}


def _database_dump(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return "\n".join(conn.iterdump())


def test_v3_migration_failure_rolls_back_and_keeps_v2_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS library_jobs;
            DROP TABLE IF EXISTS libraries;
            CREATE TABLE libraries (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE library_jobs (
              id INTEGER PRIMARY KEY,
              library_id INTEGER REFERENCES libraries(id),
              type TEXT NOT NULL,
              state TEXT NOT NULL
            );
            INSERT INTO libraries(id, name) VALUES (1, 'v2');
            INSERT INTO library_jobs(id, library_id, type, state) VALUES (1, 1, 'scan', 'queued');
            PRAGMA user_version = 2;
            """
        )
    before = _database_dump(isolated_metadata_db)
    original = schema_module._execute_v3_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("v3 injected failure")
        original(conn, statement)

    monkeypatch.setattr(schema_module, "_execute_v3_migration_statement", fail_second)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        with pytest.raises(RuntimeError, match="v3 injected failure"):
            schema_module._migrate_v2_to_v3(conn)

    assert _database_dump(isolated_metadata_db) == before
    backup = isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v2.bak")
    assert backup.exists()
    assert _database_dump(backup) == before
