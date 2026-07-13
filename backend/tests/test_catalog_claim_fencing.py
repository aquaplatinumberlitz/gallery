"""Durable catalog claim, lease, and migration regressions.

Purpose:
Verify multi-worker catalog ownership, fenced terminal writes, and schema v3.

Guarantees:
Only dead/expired claims recover, live heartbeats win races, stale workers cannot
write catalog data, staging is cleaned, terminal library/job state is atomic,
dependency-linked parents recover, bounded/atomic writes refresh their claim,
healthy parents stay unchanged, and the v2-to-v3 migration rolls back safely.

Run when:
Changing catalog workers, library_jobs claims, supervisor recovery, or schema.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from backend import scan_worker
from backend.indexer import rebuild_index_scope
from backend.metadata_store import (
    _DB_LOCK,
    CatalogJobClaimLost,
    _connect,
    activate_rebuild_staging,
    claim_next_catalog_job,
    create_job,
    create_library,
    create_or_coalesce_catalog_job,
    enumerate_to_rebuild_staging,
    get_job,
    get_library,
    recover_stale_jobs,
    renew_catalog_job_lease,
    update_job_state,
    update_parent_aggregate_job,
)
from backend.metadata_store import _schema as schema_module
from backend.metadata_store import file_index as file_index_module
from backend.metadata_store import job_store as job_store_module
from backend.metadata_store import rebuild_store as rebuild_store_module

from .conftest import create_test_png


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


def test_expired_claim_cannot_be_renewed_or_completed(
    isolated_gallery_root: Path,
) -> None:
    _queued_job(isolated_gallery_root, "expired")
    job = claim_next_catalog_job(worker_id="worker", lease_seconds=60)
    assert job is not None
    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, job["id"]))

    assert not renew_catalog_job_lease(job["id"], job["claim_token"], lease_seconds=60)
    assert update_job_state(job["id"], "succeeded", claim_token=job["claim_token"]) is None


def test_recovery_update_allows_concurrent_heartbeat_to_win(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _queued_job(isolated_gallery_root, "heartbeat-race")
    job = claim_next_catalog_job(worker_id="live-worker", lease_seconds=60)
    assert job is not None
    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, job["id"]))

    original_connect = job_store_module._connect
    calls = 0

    def racing_connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            with sqlite3.connect(isolated_metadata_db) as raw:
                raw.execute(
                    "UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?",
                    (time.time() + 60, job["id"]),
                )
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(job_store_module, "_connect", racing_connect)
    assert recover_stale_jobs(live_worker_ids={"live-worker"}) == []
    assert get_job(job["id"])["state"] == "running"


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


def test_stale_scan_claim_cannot_write_catalog(
    isolated_gallery_root: Path,
) -> None:
    library_id, _queued = _queued_job(isolated_gallery_root, "stale-scan")
    root = isolated_gallery_root / "stale-scan"
    image = root / "late.png"
    create_test_png(image)
    claimed = claim_next_catalog_job(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, claimed["id"]))

    with pytest.raises(CatalogJobClaimLost):
        rebuild_index_scope(
            root,
            claim_job_id=int(claimed["id"]),
            claim_token=str(claimed["claim_token"]),
        )
    with _DB_LOCK, _connect() as conn:
        assert conn.execute("SELECT count(*) FROM file_index WHERE path = ?", (str(image),)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM assets WHERE library_id = ?", (library_id,)).fetchone()[0] == 0


def test_stale_rebuild_activation_is_fenced_and_recovery_cleans_staging(
    isolated_gallery_root: Path,
) -> None:
    root = isolated_gallery_root / "stale-rebuild"
    root.mkdir()
    image = root / "late.png"
    create_test_png(image)
    library_id = int(create_library([root])["id"])
    queued, _created = create_or_coalesce_catalog_job(
        library_id,
        operation="rebuild",
        trigger="manual",
        priority=100,
    )
    claimed = claim_next_catalog_job(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None and claimed["id"] == queued["id"]
    enumerate_to_rebuild_staging(claimed["id"], library_id, [root], claimed["claim_token"])
    with _DB_LOCK, _connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM catalog_rebuild_entries WHERE job_id = ?", (claimed["id"],)).fetchone()[
                0
            ]
            > 0
        )
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, claimed["id"]))

    with pytest.raises(CatalogJobClaimLost):
        activate_rebuild_staging(claimed["id"], library_id, None, claimed["claim_token"])
    with _DB_LOCK, _connect() as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(image),)).fetchone()[0] == 0

    recovered = recover_stale_jobs(live_worker_ids={"worker-a"})
    assert [job["id"] for job in recovered] == [claimed["id"]]
    with _DB_LOCK, _connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM catalog_rebuild_entries WHERE job_id = ?", (claimed["id"],)).fetchone()[
                0
            ]
            == 0
        )


@pytest.mark.parametrize("operation", ["scan", "rebuild"])
def test_terminal_job_and_library_state_commit_atomically(
    isolated_gallery_root: Path,
    operation: str,
) -> None:
    root = isolated_gallery_root / f"atomic-{operation}"
    root.mkdir()
    library_id = int(create_library([root])["id"])
    queued, _created = create_or_coalesce_catalog_job(
        library_id,
        operation=operation,
        trigger="manual",
        priority=100,
    )
    claimed = claim_next_catalog_job(worker_id="worker", lease_seconds=60)
    assert claimed is not None and claimed["id"] == queued["id"]
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_ready_library
            BEFORE UPDATE OF state ON libraries
            WHEN NEW.state = 'ready'
            BEGIN
              SELECT RAISE(ABORT, 'injected library state failure');
            END
            """
        )

    execute = scan_worker.execute_scan_job if operation == "scan" else scan_worker.execute_rebuild_job
    assert execute(claimed) is False
    assert get_job(claimed["id"])["state"] == "failed"
    assert get_library(library_id)["state"] == "error"


def test_runtime_recovery_does_not_rewrite_healthy_aggregate_parent(
    isolated_gallery_root: Path,
) -> None:
    root = isolated_gallery_root / "aggregate"
    root.mkdir()
    library_id = int(create_library([root])["id"])
    parent = create_job("scan_all", progress_total=1, message="Updating all libraries")
    child, _created = create_or_coalesce_catalog_job(
        library_id,
        operation="scan",
        trigger="manual",
        priority=100,
        parent_job_id=parent["id"],
    )
    claimed = claim_next_catalog_job(worker_id="live-worker", lease_seconds=60)
    assert claimed is not None and claimed["id"] == child["id"]
    assert update_parent_aggregate_job(parent["id"])["state"] == "running"
    with _DB_LOCK, _connect() as conn:
        before = conn.execute("SELECT updated_at FROM library_jobs WHERE id = ?", (parent["id"],)).fetchone()[0]

    assert recover_stale_jobs(live_worker_ids={"live-worker"}) == []
    assert recover_stale_jobs(live_worker_ids={"live-worker"}) == []
    with _DB_LOCK, _connect() as conn:
        after = conn.execute("SELECT updated_at FROM library_jobs WHERE id = ?", (parent["id"],)).fetchone()[0]
    assert after == before


def test_runtime_recovery_updates_dependency_only_aggregate_parent(
    isolated_gallery_root: Path,
) -> None:
    library_id, _queued = _queued_job(isolated_gallery_root, "dependency-parent")
    child = claim_next_catalog_job(worker_id="dead-worker", lease_seconds=60)
    assert child is not None
    parent = create_job("scan_all", progress_total=1, message="Updating all libraries")
    coalesced, created = create_or_coalesce_catalog_job(
        library_id,
        operation="scan",
        trigger="manual",
        priority=100,
        parent_job_id=parent["id"],
    )
    assert not created and coalesced["id"] == child["id"]
    with _DB_LOCK, _connect() as conn:
        child_row = conn.execute(
            "SELECT parent_job_id FROM library_jobs WHERE id = ?",
            (child["id"],),
        ).fetchone()
        dependency = conn.execute(
            """SELECT 1 FROM catalog_job_dependencies
               WHERE parent_job_id = ? AND child_job_id = ?""",
            (parent["id"], child["id"]),
        ).fetchone()
    assert child_row["parent_job_id"] is None
    assert dependency is not None
    assert update_parent_aggregate_job(parent["id"])["state"] == "running"

    recovered = recover_stale_jobs(live_worker_ids=set())
    assert {job["id"] for job in recovered} == {child["id"], parent["id"]}
    updated_parent = get_job(parent["id"])
    assert updated_parent is not None
    assert updated_parent["state"] == "failed"
    assert updated_parent["progress_current"] == 1
    assert updated_parent["finished_at"] is not None


def test_scan_batches_release_lock_and_refresh_claim_before_each_commit(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_id, _queued = _queued_job(isolated_gallery_root, "bounded-scan")
    claimed = claim_next_catalog_job(worker_id="worker", lease_seconds=1)
    assert claimed is not None
    root = isolated_gallery_root / "bounded-scan"
    records = []
    for index in range(2):
        image = root / f"image-{index}.png"
        create_test_png(image)
        stat = image.stat()
        records.append(
            (
                str(image),
                image.name,
                str(root),
                "image",
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                64,
                64,
                time.time(),
                "image/png",
                None,
                None,
            )
        )

    monkeypatch.setattr(file_index_module, "_INDEX_WRITE_BATCH_SIZE", 1)
    original_connect = file_index_module._connect
    connection_count = 0

    def counting_connect(*args, **kwargs):
        nonlocal connection_count
        connection_count += 1
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(file_index_module, "_connect", counting_connect)
    original_refresh = job_store_module.refresh_catalog_job_claim_before_commit_conn

    def slow_refresh(*args, **kwargs):
        time.sleep(0.6)
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(job_store_module, "refresh_catalog_job_claim_before_commit_conn", slow_refresh)
    started = time.monotonic()
    file_index_module._bulk_index_records(
        records,
        library_id,
        claim_job_id=claimed["id"],
        claim_token=claimed["claim_token"],
        claim_lease_seconds=1,
    )

    assert connection_count == 2
    assert time.monotonic() - started >= 1.2
    assert (
        update_job_state(
            claimed["id"],
            "succeeded",
            claim_token=claimed["claim_token"],
            lease_seconds=1,
        )
        is not None
    )


def test_rebuild_activation_refreshes_claim_inside_long_transaction(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = isolated_gallery_root / "long-activation"
    root.mkdir()
    image = root / "image.png"
    create_test_png(image)
    library_id = int(create_library([root])["id"])
    queued, _created = create_or_coalesce_catalog_job(
        library_id,
        operation="rebuild",
        trigger="manual",
        priority=100,
    )
    claimed = claim_next_catalog_job(worker_id="worker", lease_seconds=1)
    assert claimed is not None and claimed["id"] == queued["id"]
    enumerate_to_rebuild_staging(
        claimed["id"],
        library_id,
        [root],
        claimed["claim_token"],
        claim_lease_seconds=1,
    )
    original_scope_sql = rebuild_store_module.path_scope_sql

    def slow_scope_sql(*args, **kwargs):
        time.sleep(1.2)
        return original_scope_sql(*args, **kwargs)

    monkeypatch.setattr(rebuild_store_module, "path_scope_sql", slow_scope_sql)
    activation = activate_rebuild_staging(
        claimed["id"],
        library_id,
        root,
        claimed["claim_token"],
        claim_lease_seconds=1,
    )
    assert activation["created"] >= 1
    assert (
        update_job_state(
            claimed["id"],
            "succeeded",
            claim_token=claimed["claim_token"],
            lease_seconds=1,
        )
        is not None
    )
    with _DB_LOCK, _connect() as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(image),)).fetchone()[0] == 1


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
