"""Phase 2.5 regression: O(1) runtime counters for the status reads.

Purpose:
Pin the counter half of the Phase 2 work. The status builds counted ``metadata_index_jobs`` states and
summed ``asset_derivatives.byte_size`` with full aggregate queries on every poll. Now a
``runtime_counters`` table, maintained by SQLite triggers on the counted tables (so the writer ops, the
flag-off direct transactions, destructive maintenance and migrations all keep it exact), is read by the
unscoped status builds inside the existing ``_read_snapshot``; scoped reads keep their aggregates.

Guarantees:
Fresh and existing databases have the table, the triggers and exact values (an existing database is
backfilled by the additive ensure, with no catalog version bump); ``schema_check`` reports a missing table
or trigger; after seeded randomized transitions (inserts, upserts, state and byte-size updates, bulk
updates, deletes, rollbacks) the counters equal the aggregate queries; real lifecycle flows through the
writer and through the flag-off direct paths, a rolled-back writer op, and destructive imported-data
maintenance and catalog reset all leave the counters exact; the unscoped status reads come from the
counters (a tampered counter shows up in the status, a scoped read still aggregates) and the status is
identical to the one computed from aggregates; counters and rows are read from one snapshot; the integrity
pass recomputes the counters and repairs drift and missing rows.

Run when:
Changing ``runtime_counters`` or its triggers, the status builds that read it, the integrity counter
repair, or any write path of ``metadata_index_jobs`` or ``asset_derivatives``.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest

import backend.config as config
from tests.worker_contention_support import capture_sql, seed_assets, seed_library

METADATA_STATES = ("queued", "running", "done", "stale", "failed", "skipped")
COUNTER_NAMES = (*(f"metadata_jobs.{state}" for state in METADATA_STATES), "derivative_ready_bytes")


def _writer_module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def stored_counters(db_path: Path) -> dict[str, int]:
    with _connect(db_path) as conn:
        return {str(row["name"]): int(row["value"]) for row in conn.execute("SELECT name, value FROM runtime_counters")}


def aggregate_counters(db_path: Path) -> dict[str, int]:
    """The source of truth: the aggregate queries the status builds ran before the counters existed."""
    with _connect(db_path) as conn:
        counts = dict.fromkeys(METADATA_STATES, 0)
        for row in conn.execute("SELECT state, count(*) AS n FROM metadata_index_jobs GROUP BY state"):
            if row["state"] in counts:
                counts[row["state"]] = int(row["n"])
        ready = conn.execute(
            "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
        ).fetchone()[0]
    return {
        **{f"metadata_jobs.{state}": counts[state] for state in METADATA_STATES},
        "derivative_ready_bytes": int(ready),
    }


def assert_counters_exact(db_path: Path, label: str = "") -> None:
    assert stored_counters(db_path) == aggregate_counters(db_path), f"counters drifted {label}"


@pytest.fixture
def seeded(isolated_metadata_db: Path, isolated_gallery_root: Path) -> tuple[Path, int, Path]:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    return isolated_metadata_db, seed_library(root), root


@pytest.fixture(params=["writer", "direct"])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test once through the writer and once through the direct (flag-off) transactions."""
    monkeypatch.setattr(_writer_module(), "DB_WRITER_ENABLED", request.param == "writer")
    return request.param


# ---------------------------------------------------------------------------
# Schema: fresh, existing, schema_check
# ---------------------------------------------------------------------------


def test_a_fresh_database_has_the_runtime_counters_table_triggers_and_zero_values(isolated_metadata_db: Path) -> None:
    with sqlite3.connect(isolated_metadata_db) as conn:
        table = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runtime_counters'"
        ).fetchone()
        triggers = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trg_runtime_%'"
            )
        }
    assert table is not None, "runtime_counters is missing from a freshly initialized database"
    assert {"name", "value"} <= set(table[0].replace("(", " ").replace(")", " ").replace(",", " ").split())
    assert len(triggers) >= 6, triggers
    assert stored_counters(isolated_metadata_db) == dict.fromkeys(COUNTER_NAMES, 0)


def test_an_existing_database_gains_the_table_and_triggers_with_backfilled_values(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store as ms

    db_path, library_id, root = seeded
    assets = seed_assets(db_path, library_id, root, 6)
    with sqlite3.connect(db_path) as conn:
        for index, (_asset_id, path, mtime_ns, size) in enumerate(assets):
            conn.execute(
                """
                INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, mtime_ns,
                                                 size, state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0)
                """,
                (path, Path(path).name, str(root), str(root), str(root), mtime_ns / 1e9, mtime_ns, size,
                 METADATA_STATES[index % 3]),
            )  # fmt: skip
        derivative_id = conn.execute(
            """
            INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, max_long_edge,
                                           status, byte_size)
            VALUES (?, 'thumbnail', 'thumb_128', ?, ?, 128, 'ready', 4096)
            """,
            (assets[0][0], assets[0][2], assets[0][3]),
        ).lastrowid
        assert derivative_id
        # An older database: no counters table and none of its triggers.
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trg_runtime_%'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute("DROP TABLE runtime_counters")
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)

    ms.initialize_database()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12, "no catalog version bump"
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trg_runtime_%'"
            ).fetchone()[0]
            >= 6
        )
    counters = stored_counters(db_path)
    assert counters["metadata_jobs.queued"] == 2 and counters["metadata_jobs.running"] == 2
    assert counters["metadata_jobs.done"] == 2 and counters["derivative_ready_bytes"] == 4096
    assert_counters_exact(db_path, "after the backfill")
    with sqlite3.connect(db_path) as conn:  # and the triggers keep it exact afterwards
        conn.execute("UPDATE metadata_index_jobs SET state = 'failed' WHERE path = ?", (assets[0][1],))
        conn.execute("UPDATE asset_derivatives SET byte_size = 100 WHERE id = ?", (derivative_id,))
    assert_counters_exact(db_path, "after post-backfill transitions")


def test_schema_check_reports_a_missing_counters_table_or_trigger(isolated_metadata_db: Path) -> None:
    from backend.metadata_store.schema_check import check_catalog_schema

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert check_catalog_schema(conn) == []
        trigger = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trg_runtime_%' LIMIT 1"
        ).fetchone()[0]
        conn.execute(f"DROP TRIGGER {trigger}")
        assert f"Missing trigger: {trigger}" in check_catalog_schema(conn)
        conn.execute("DROP TABLE runtime_counters")
        assert "Missing table: runtime_counters" in check_catalog_schema(conn)


# ---------------------------------------------------------------------------
# Randomized transitions: counters == aggregates
# ---------------------------------------------------------------------------


def test_counters_equal_the_aggregate_queries_after_randomized_transitions(seeded) -> None:
    db_path, library_id, root = seeded
    assets = seed_assets(db_path, library_id, root, 24)
    rng = random.Random(20261028)
    job_paths = [asset[1] for asset in assets]
    states = (*METADATA_STATES, "queued", "running")  # weighted towards the active states
    derivative_status = ("queued", "running", "ready", "ready", "failed", "skipped", "evicted", "deferred_capacity")
    derivative_ids: list[int] = []
    variants = [
        (kind, variant, edge)
        for kind, variant, edge in (
            ("thumbnail", "thumb_128", 128),
            ("thumbnail", "thumb_512", 512),
            ("preview", "preview_1440", 1440),
        )
    ]
    seen: set[tuple[int, str]] = set()
    visited_states: set[str] = set()
    peak_ready_bytes = 0
    with _connect(db_path) as conn:
        for step in range(900):
            action = rng.randrange(14)
            path = rng.choice(job_paths)
            if action <= 2:  # insert or upsert-coalesce a metadata job
                state = rng.choice(states)
                visited_states.add(state)
                conn.execute(
                    """
                    INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, mtime_ns,
                                                     size, state, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1.0, 1, 1, ?, 1.0)
                    ON CONFLICT(path) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
                    """,
                    (path, Path(path).name, str(root), str(root), str(root), state),
                )
            elif action <= 4:  # change one job's state (including to the same value)
                conn.execute("UPDATE metadata_index_jobs SET state = ? WHERE path = ?", (rng.choice(states), path))
            elif action == 5:  # an update that does not touch the state
                conn.execute(
                    "UPDATE metadata_index_jobs SET attempts = attempts + 1, error = NULL WHERE path = ?", (path,)
                )
            elif action == 6:  # bulk transitions and deletes
                if rng.random() < 0.5:
                    conn.execute(
                        "UPDATE metadata_index_jobs SET state = ? WHERE state = ?",
                        (rng.choice(states), rng.choice(states)),
                    )
                else:
                    conn.execute(
                        "DELETE FROM metadata_index_jobs WHERE state = ? AND rowid % 2 = 0", (rng.choice(states),)
                    )
            elif action == 7:
                conn.execute("DELETE FROM metadata_index_jobs WHERE path = ?", (path,))
            elif action <= 9:  # insert a derivative
                asset_id, _path, mtime_ns, size = rng.choice(assets)
                kind, variant, edge = rng.choice(variants)
                key = (asset_id, variant)
                if key in seen:
                    continue
                seen.add(key)
                status = rng.choice(derivative_status)
                derivative_ids.append(
                    int(
                        conn.execute(
                            """
                            INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size,
                                                           max_long_edge, status, byte_size)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                asset_id,
                                kind,
                                variant,
                                mtime_ns,
                                size,
                                edge,
                                status,
                                rng.choice([None, 0, 500, 2048, 9000]),
                            ),
                        ).lastrowid
                    )
                )
            elif derivative_ids and action == 10:  # status transition
                conn.execute(
                    "UPDATE asset_derivatives SET status = ? WHERE id = ?",
                    (rng.choice(derivative_status), rng.choice(derivative_ids)),
                )
            elif derivative_ids and action == 11:  # byte size change, and a touch that changes neither
                target = rng.choice(derivative_ids)
                conn.execute(
                    "UPDATE asset_derivatives SET byte_size = ? WHERE id = ?",
                    (rng.choice([None, 1, 777, 4096]), target),
                )
                conn.execute("UPDATE asset_derivatives SET last_accessed_at = 5.0 WHERE id = ?", (target,))
            elif derivative_ids and action == 12:  # bulk transition
                conn.execute(
                    "UPDATE asset_derivatives SET status = ?, byte_size = COALESCE(byte_size, 10) WHERE status = ?",
                    (rng.choice(derivative_status), rng.choice(derivative_status)),
                )
            elif derivative_ids:  # delete a derivative (its jobs first, as the production code does)
                target = derivative_ids.pop(rng.randrange(len(derivative_ids)))
                conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (target,))
                conn.execute("DELETE FROM asset_derivatives WHERE id = ?", (target,))
            if step % 7 == 3:  # a rolled-back unit of work must not move any counter
                conn.commit()
                before = stored_counters(db_path)
                conn.execute("UPDATE metadata_index_jobs SET state = 'done'")
                conn.execute("UPDATE asset_derivatives SET status = 'ready', byte_size = 12345")
                conn.rollback()
                assert stored_counters(db_path) == before
            if step % 20 == 0:
                conn.commit()
                assert_counters_exact(db_path, f"at step {step}")
                peak_ready_bytes = max(peak_ready_bytes, stored_counters(db_path)["derivative_ready_bytes"])
        conn.commit()
    assert_counters_exact(db_path, "at the end")
    final = aggregate_counters(db_path)
    assert sum(final[f"metadata_jobs.{state}"] for state in METADATA_STATES) > 0
    assert peak_ready_bytes > 0, "the walk never held any ready bytes"
    assert visited_states == set(METADATA_STATES), "the walk never visited every job state"


def test_a_rolled_back_writer_op_leaves_the_counters_untouched(seeded) -> None:
    from backend.metadata_store.db_writer import database_writer

    db_path, library_id, root = seeded
    assets = seed_assets(db_path, library_id, root, 3)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, size, state, updated_at)
            VALUES (?, 'a', ?, ?, ?, 1.0, 1, 'queued', 1.0)
            """,
            (assets[0][1], str(root), str(root), str(root)),
        )
    before = stored_counters(db_path)
    assert before["metadata_jobs.queued"] == 1

    def failing_op(conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE metadata_index_jobs SET state = 'done'")
        raise RuntimeError("op fails after changing the state")

    def good_op(conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE metadata_index_jobs SET state = 'running'")

    database_writer.start()
    failed = database_writer.submit(failing_op)
    good = database_writer.submit(good_op)
    with pytest.raises(RuntimeError):
        failed.result(timeout=10)
    good.result(timeout=10)

    after = stored_counters(db_path)
    assert (
        after["metadata_jobs.done"] == 0 and after["metadata_jobs.running"] == 1 and after["metadata_jobs.queued"] == 0
    )
    assert_counters_exact(db_path)


# ---------------------------------------------------------------------------
# Real flows through the writer and through the flag-off direct paths
# ---------------------------------------------------------------------------


def test_counters_stay_exact_through_the_real_scan_metadata_derivative_and_integrity_flows(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    import backend.visual_fingerprints as visual_fingerprints
    from backend import indexer, scan_worker
    from backend.derivative_scheduler import DerivativeScheduler
    from backend.indexer import MetadataLifecycleWorker
    from backend.integrity_checker import IntegrityChecker
    from backend.metadata_store import create_library
    from tests.conftest import create_test_png

    monkeypatch.setattr(visual_fingerprints, "notify_derivative_ready", lambda _asset_id: None)
    root = isolated_gallery_root / "photos"
    root.mkdir()
    for index in range(10):
        create_test_png(root / f"img_{index:02d}.png", size=(32, 24), color=(index * 20, 80, 160))
    library_id = int(create_library([root], name="Counters")["id"])
    db_path = isolated_metadata_db

    scan_worker.queue_scan(library_id, trigger="manual")
    assert scan_worker.run_once() is True
    assert_counters_exact(db_path, "after the scan")
    assert aggregate_counters(db_path)["metadata_jobs.queued"] == 10

    worker = MetadataLifecycleWorker(worker_count=1, lease_seconds=30, heartbeat_seconds=10, write_retry_delays=())
    for _ in range(6):  # complete some jobs, fail one
        job = worker._claim_job()
        assert job is not None
        if job.path.endswith("img_03.png"):
            worker._persist(lambda conn, job=job: indexer.fail_metadata_job(conn, job, "boom"))
        else:
            worker._run_job(job)
        assert_counters_exact(db_path, "during metadata work")
    after_metadata = aggregate_counters(db_path)
    assert after_metadata["metadata_jobs.done"] >= 5 and after_metadata["metadata_jobs.failed"] == 1

    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=1024 * 1024 * 1024)
    summary = scheduler.reconcile_desired_derivatives(
        library_id=library_id, reason="manual_generate", respect_warm_policy=False
    )
    assert summary.desired_derivatives > 0  # the scan's own reconcile already queued them
    for _ in range(8):
        claimed = scheduler._claim_job("worker")
        assert claimed is not None
        scheduler._run_job(claimed)
    assert_counters_exact(db_path, "after derivative work")
    assert aggregate_counters(db_path)["derivative_ready_bytes"] > 0

    for index in range(0, 10, 2):  # change sources: supersede ready derivatives, requeue metadata
        path = root / f"img_{index:02d}.png"
        create_test_png(path, size=(33, 25), color=(200, 10, 10))
    scan_worker.queue_scan(library_id, trigger="manual")
    assert scan_worker.run_once() is True
    assert_counters_exact(db_path, "after the rescan that superseded derivatives")
    IntegrityChecker().run_all_checks()
    assert_counters_exact(db_path, "after the integrity pass")


# ---------------------------------------------------------------------------
# Destructive maintenance
# ---------------------------------------------------------------------------


def _seed_terminal_state(db_path: Path, library_id: int, root: Path) -> None:
    assets = seed_assets(db_path, library_id, root, 8)
    with sqlite3.connect(db_path) as conn:
        for index, (asset_id, path, mtime_ns, size) in enumerate(assets):
            conn.execute(
                """
                INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, mtime_ns,
                                                 size, state, updated_at)
                VALUES (?, ?, ?, ?, ?, 1.0, ?, ?, ?, 1.0)
                """,
                (path, Path(path).name, str(root), str(root), str(root), mtime_ns, size, ("done", "failed", "stale", "skipped")[index % 4]),
            )  # fmt: skip
            conn.execute(
                """
                INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, max_long_edge,
                                               status, byte_size)
                VALUES (?, 'thumbnail', 'thumb_128', ?, ?, 128, 'ready', 1000)
                """,
                (asset_id, mtime_ns, size),
            )


def test_destructive_maintenance_leaves_the_counters_exact(
    seeded, isolated_thumbnail_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.imported_data_maintenance import RESET_CONFIRM_PHRASE, clear_imported_data, reset_catalog_database

    db_path, library_id, root = seeded
    _seed_terminal_state(db_path, library_id, root)
    before = stored_counters(db_path)
    assert before["metadata_jobs.done"] == 2 and before["derivative_ready_bytes"] == 8_000

    clear_imported_data(confirm=True)

    assert stored_counters(db_path) == dict.fromkeys(COUNTER_NAMES, 0)
    assert_counters_exact(db_path, "after clearing imported data")

    _seed_terminal_state(db_path, library_id, root)  # libraries survive a clear; the catalog starts over
    assert stored_counters(db_path)["derivative_ready_bytes"] == 8_000
    reset_catalog_database(confirm_phrase=RESET_CONFIRM_PHRASE)
    assert stored_counters(db_path) == dict.fromkeys(COUNTER_NAMES, 0)
    assert_counters_exact(db_path, "after the catalog reset")


# ---------------------------------------------------------------------------
# Status reads come from the counters
# ---------------------------------------------------------------------------


def _tamper(db_path: Path, **values: int) -> None:
    with sqlite3.connect(db_path) as conn:
        for name, value in values.items():
            conn.execute("UPDATE runtime_counters SET value = ? WHERE name = ?", (value, name.replace("__", ".")))


def test_the_unscoped_status_reads_come_from_the_counters_and_scoped_reads_still_aggregate(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.derivative_scheduler import DerivativeScheduler
    from backend.indexer import get_indexer_runtime_status, get_metadata_lifecycle_status

    db_path, library_id, root = seeded
    _seed_terminal_state(db_path, library_id, root)
    _tamper(
        db_path,
        metadata_jobs__queued=777,
        metadata_jobs__running=555,
        metadata_jobs__done=333,
        derivative_ready_bytes=424_242,
    )

    lifecycle = get_metadata_lifecycle_status()
    runtime = get_indexer_runtime_status()
    library = DerivativeScheduler(worker_count=1, quota_bytes=10_000_000).library_status(library_id)
    scoped = get_metadata_lifecycle_status(scope_path=root)
    scoped_runtime = get_indexer_runtime_status(scope_path=root)

    assert lifecycle["queued_metadata_jobs"] == 777 and lifecycle["running_metadata_jobs"] == 555
    assert lifecycle["done_metadata_jobs"] == 333
    assert runtime["runtime_queue_depth"] == 777 and runtime["active_jobs"] == 555
    assert library["quota_used_bytes"] == 424_242
    assert scoped["queued_metadata_jobs"] == 0 and scoped["done_metadata_jobs"] == 2, "a scoped read must aggregate"
    assert scoped_runtime["runtime_queue_depth"] == 0

    with capture_sql(monkeypatch) as statements:
        get_metadata_lifecycle_status()
        get_indexer_runtime_status()
    aggregates = [
        s
        for s in statements
        if "count(*)" in s.lower()
        and "from metadata_index_jobs" in s.lower()
        and "join" not in s.lower()
        and "state" in s.lower()
    ]
    assert not aggregates, f"unscoped status still aggregates metadata job states: {aggregates[:2]}"
    assert any("runtime_counters" in s for s in statements)


def test_status_is_identical_whether_it_is_read_from_the_counters_or_from_the_aggregates(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_worker_contention_wk01 import build_status_snapshot, seed_status_golden_state

    monkeypatch.setattr(config, "METADATA_INDEXER_ENABLED", True)
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_status_golden_state(isolated_metadata_db, root)
    assert_counters_exact(isolated_metadata_db, "after seeding the golden state")

    from_counters = build_status_snapshot(library_id, root)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("DELETE FROM runtime_counters")  # a missing counter falls back to the aggregate query
    from_aggregates = build_status_snapshot(library_id, root)

    assert from_counters == from_aggregates
    assert from_counters["metadata_lifecycle"]["queued_metadata_jobs"] == 2


def test_counters_and_rows_are_read_from_one_snapshot(seeded) -> None:
    from backend.metadata_store import _read_snapshot

    db_path, library_id, root = seeded
    assets = seed_assets(db_path, library_id, root, 2)
    with _read_snapshot() as snapshot:
        first = snapshot.execute("SELECT value FROM runtime_counters WHERE name = 'metadata_jobs.queued'").fetchone()[0]
        with sqlite3.connect(db_path) as writer:  # a commit lands in the middle of the status build
            writer.execute(
                """
                INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, size, state, updated_at)
                VALUES (?, 'a', ?, ?, ?, 1.0, 1, 'queued', 1.0)
                """,
                (assets[0][1], str(root), str(root), str(root)),
            )
        counted = snapshot.execute("SELECT value FROM runtime_counters WHERE name = 'metadata_jobs.queued'").fetchone()[
            0
        ]
        rows = snapshot.execute("SELECT count(*) FROM metadata_index_jobs WHERE state = 'queued'").fetchone()[0]
    assert first == counted == rows == 0
    assert stored_counters(db_path)["metadata_jobs.queued"] == 1


# ---------------------------------------------------------------------------
# Integrity repair
# ---------------------------------------------------------------------------


def test_the_integrity_pass_recomputes_the_counters_and_repairs_drift(
    seeded, isolated_thumbnail_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.integrity_checker import IntegrityChecker

    db_path, library_id, root = seeded
    _seed_terminal_state(db_path, library_id, root)
    assert_counters_exact(db_path)
    checker = IntegrityChecker()
    clean = checker.run_all_checks()
    assert clean["runtime_counters_repaired"] == 0

    _tamper(db_path, metadata_jobs__done=999, metadata_jobs__failed=-4, derivative_ready_bytes=1)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM runtime_counters WHERE name = 'metadata_jobs.stale'")
    assert stored_counters(db_path) != aggregate_counters(db_path)

    repaired = checker.run_all_checks()

    assert repaired["runtime_counters_repaired"] == 4
    assert_counters_exact(db_path, "after the integrity repair")
    assert checker.run_all_checks()["runtime_counters_repaired"] == 0
