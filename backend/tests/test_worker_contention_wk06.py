"""WK-06 regression: superseded derivatives must leave the ready set.

Purpose:
Pin the worker-lifecycle audit finding WK-06. After seven rescans 27,003 ``ready`` derivative rows
(files still on disk) described old source identities versus 2,136 current ones. They counted
toward quota, inflated the tables behind the WK-01/WK-03 queries, and the integrity check never
retired them.

Guarantees:
When a source identity changes, old-identity ``ready`` rows move to ``skipped`` with job result
code ``source_superseded`` (cache fields cleared), and their files are unlinked only after the
transaction commits; quota accounting counts only current identities, including for decisions
inside the same reconcile batch (the batch ``CapacityLedger`` is told about retired bytes and the
outcomes equal an oracle that retires first and then runs the old algorithm); an integrity pass
repairs pre-existing stale rows without resurrecting them; a file being served (or still referenced
by a row) is never unlinked, only deferred until its serving lease is released; a source that
returns to an earlier identity is regenerated instead of staying terminally skipped; and retiring
never touches current identities or other assets.

Run when:
Changing derivative reconcile, ``_coalesce_derivative_job``, capacity accounting, the integrity
checker's derivative checks, serving protection, or scan-time source-identity handling.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from backend.derivative_scheduler import DerivativeScheduler
from backend.derivative_scheduler.capacity import CapacityLedger
from backend.derivative_scheduler.models import DerivativeReconcileSummary
from backend.indexer import rebuild_index_scope
from backend.metadata_store import _connect
from tests.test_worker_contention_wk03 import (
    OldAlgorithmScheduler,
    _candidates,
    _copy_database,
    _database_fingerprint,
    _use_database,
    _variants,
)
from tests.worker_contention_support import VARIANTS, capture_sql

BYTES = 1_000
GENEROUS_QUOTA = 1024 * 1024 * 1024
TOUCH_NS = 7_000_000_000


class World:
    """A library over real image files with hand-seeded derivative rows and cache files."""

    def __init__(self, db_path: Path, root: Path, cache_dir: Path) -> None:
        self.db_path = db_path
        self.root = root
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.library_id = 0

    def add_images(self, count: int) -> list[Path]:
        from backend.metadata_store import create_library
        from tests.conftest import create_test_png

        self.root.mkdir(parents=True, exist_ok=True)
        self.library_id = int(create_library([self.root], name="Supersede")["id"])
        images = []
        for index in range(count):
            image = self.root / f"photo_{index:02d}.png"
            create_test_png(image, size=(8 + index, 8))
            images.append(image.resolve())
        rebuild_index_scope(self.root)
        return images

    def asset(self, path: Path) -> sqlite3.Row:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT id, mtime_ns, size FROM assets WHERE path = ?", (str(path),)).fetchone()
        assert row is not None
        return row

    def seed_ready(
        self,
        path: Path,
        *,
        mtime_ns: int | None = None,
        size: int | None = None,
        with_file: bool = True,
        byte_size: int = BYTES,
    ) -> list[tuple[int, Path]]:
        """Insert one ``ready`` derivative (and a ``done`` job) per variant for one source identity."""
        asset = self.asset(path)
        mtime_ns = int(asset["mtime_ns"]) if mtime_ns is None else mtime_ns
        size = int(asset["size"]) if size is None else size
        seeded: list[tuple[int, Path]] = []
        with sqlite3.connect(self.db_path) as conn:
            for kind, variant, max_edge, quality in VARIANTS:
                cache_path = self.cache_dir / f"{asset['id']}_{variant}_{mtime_ns}_{size}.webp"
                if with_file:
                    cache_path.write_bytes(b"x" * byte_size)
                derivative_id = int(
                    conn.execute(
                        """
                        INSERT INTO asset_derivatives (
                          asset_id, kind, variant, source_mtime_ns, source_size, format, quality,
                          max_long_edge, status, cache_path, byte_size
                        ) VALUES (?, ?, ?, ?, ?, 'webp', ?, ?, 'ready', ?, ?)
                        """,
                        (asset["id"], kind, variant, mtime_ns, size, quality, max_edge, str(cache_path), byte_size),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'done')",
                    (derivative_id,),
                )
                seeded.append((derivative_id, cache_path))
        return seeded

    @staticmethod
    def touch(path: Path) -> None:
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + TOUCH_NS))

    def rescan(self) -> None:
        rebuild_index_scope(self.root)

    def derivative(self, derivative_id: int) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()
            jobs = conn.execute(
                "SELECT state, result_code FROM derivative_jobs WHERE derivative_id = ? ORDER BY id", (derivative_id,)
            ).fetchall()
        return {**dict(row), "jobs": [tuple(job) for job in jobs]}

    def stale_ready_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return int(
                conn.execute(
                    """
                    SELECT count(*) FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
                    WHERE d.status = 'ready' AND a.deleted_at IS NULL AND a.offline = 0
                      AND (d.source_mtime_ns != a.mtime_ns OR d.source_size != a.size)
                    """
                ).fetchone()[0]
            )

    def ready_bytes(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return int(
                conn.execute(
                    "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
                ).fetchone()[0]
            )


@pytest.fixture
def world(isolated_metadata_db: Path, isolated_gallery_root: Path, tmp_path: Path) -> World:
    return World(isolated_metadata_db, isolated_gallery_root / "photos", tmp_path / "cache")


def _assert_retired(world: World, seeded: list[tuple[int, Path]]) -> None:
    for derivative_id, cache_path in seeded:
        row = world.derivative(derivative_id)
        assert row["status"] == "skipped", row
        assert row["cache_path"] is None and row["byte_size"] is None
        assert ("skipped", "source_superseded") in row["jobs"], row["jobs"]
        assert all(state != "done" for state, _code in row["jobs"]), "a retired row must not keep a done job"
        assert not cache_path.exists(), f"{cache_path} should have been unlinked after commit"


# ---------------------------------------------------------------------------
# Retiring on identity change
# ---------------------------------------------------------------------------


def test_touch_and_rescan_retire_old_identity_rows_and_files(world: World) -> None:
    touched, untouched = world.add_images(2)
    old = world.seed_ready(touched)
    bystander = world.seed_ready(untouched)
    world.touch(touched)
    world.rescan()
    assert world.stale_ready_count() == len(VARIANTS), "the rescan must have produced superseded ready rows"

    summary = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA).reconcile_desired_derivatives(
        library_id=world.library_id, reason="catalog_scan"
    )

    _assert_retired(world, old)
    assert world.stale_ready_count() == 0
    for derivative_id, cache_path in bystander:
        assert world.derivative(derivative_id)["status"] == "ready" and cache_path.is_file()
    new_asset = world.asset(touched)
    with sqlite3.connect(world.db_path) as conn:
        current = conn.execute(
            "SELECT status FROM asset_derivatives WHERE asset_id = ? AND source_mtime_ns = ?",
            (new_asset["id"], new_asset["mtime_ns"]),
        ).fetchall()
    assert [row[0] for row in current] == ["queued"] * len(VARIANTS), "the current identity must be scheduled"
    assert summary.created_jobs == len(VARIANTS)


def test_scan_commit_hook_retires_even_when_warm_policy_is_off(world: World) -> None:
    from backend.scan_worker import _reconcile_derivatives_after_catalog_commit

    (image,) = world.add_images(1)
    old = world.seed_ready(image)
    with sqlite3.connect(world.db_path) as conn:
        conn.execute("UPDATE libraries SET warm_enabled = 0 WHERE id = ?", (world.library_id,))
    world.touch(image)
    world.rescan()

    _reconcile_derivatives_after_catalog_commit({"id": 1, "type": "scan"}, world.library_id)

    _assert_retired(world, old)


def test_retire_ignores_inactive_assets_and_assets_without_a_known_identity(world: World) -> None:
    offline, unknown = world.add_images(2)
    stale_offline = world.seed_ready(offline, mtime_ns=1_000_000_000, size=1)
    stale_unknown = world.seed_ready(unknown, mtime_ns=1_000_000_000, size=1)
    with sqlite3.connect(world.db_path) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(offline),))
        conn.execute("UPDATE assets SET mtime_ns = NULL WHERE path = ?", (str(unknown),))

    retired = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA).retire_superseded_derivatives()

    assert retired == 0
    for derivative_id, cache_path in [*stale_offline, *stale_unknown]:
        assert world.derivative(derivative_id)["status"] == "ready" and cache_path.is_file()


def test_a_source_that_returns_to_an_earlier_identity_is_regenerated(world: World) -> None:
    (image,) = world.add_images(1)
    original = world.asset(image)
    old = world.seed_ready(image)
    world.touch(image)
    world.rescan()
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    scheduler.reconcile_desired_derivatives(library_id=world.library_id, reason="catalog_scan")
    _assert_retired(world, old)

    os.utime(image, ns=(image.stat().st_atime_ns, int(original["mtime_ns"])))
    world.rescan()
    assert int(world.asset(image)["mtime_ns"]) == int(original["mtime_ns"])
    summary = scheduler.reconcile_desired_derivatives(library_id=world.library_id, reason="catalog_scan")

    assert summary.created_jobs == len(VARIANTS)
    assert summary.terminal_skipped == 0
    for derivative_id, _path in old:
        row = world.derivative(derivative_id)
        assert row["status"] == "queued", "a superseded row must be retriable when its identity becomes current again"
        assert row["jobs"][-1] == ("queued", None)


# ---------------------------------------------------------------------------
# Quota accounting
# ---------------------------------------------------------------------------


def test_quota_counts_only_current_identities(world: World) -> None:
    touched, untouched = world.add_images(2)
    world.seed_ready(touched)
    world.seed_ready(untouched, byte_size=BYTES)
    world.touch(touched)
    world.rescan()
    assert world.ready_bytes() == 2 * len(VARIANTS) * BYTES

    DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA).reconcile_desired_derivatives(
        library_id=world.library_id, reason="catalog_scan"
    )

    assert world.ready_bytes() == len(VARIANTS) * BYTES, "only the untouched asset's current rows may count"
    with _connect() as conn:
        ready_used, _active = DerivativeScheduler._capacity_counts(conn)
    assert ready_used == len(VARIANTS) * BYTES


def _quota_world(world: World) -> tuple[list[tuple[int, str, int, int]], list[tuple[int, Path]]]:
    """Asset A is touched (stale ready rows); asset B holds current ready rows. Returns candidates and A's old rows."""
    touched, untouched = world.add_images(2)
    old = world.seed_ready(touched)
    world.seed_ready(untouched)
    world.touch(touched)
    world.rescan()
    candidates = []
    for path in (touched, untouched):
        asset = world.asset(path)
        candidates.append((int(asset["id"]), str(path), int(asset["mtime_ns"]), int(asset["size"])))
    return candidates, old


def test_batch_quota_decisions_account_for_the_retired_bytes(world: World) -> None:
    candidates, old = _quota_world(world)
    # Stale 3000 + current 3000 ready bytes. Retired first, the three new identities fit
    # (3000 + 0..2 reservations + 1000 <= 7000); counted, only the first fits.
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=7_000)
    summary = DerivativeReconcileSummary()

    pending = scheduler._coalesce_reconcile_candidates(
        _candidates(candidates), _variants(), priority=3, retry_failed=False, reason="periodic", summary=summary
    )

    assert pending == []
    assert summary.created_jobs == len(VARIANTS)
    assert summary.deferred_capacity == 0
    _assert_retired(world, old)


def test_retire_reports_released_bytes_to_a_loaded_ledger(world: World) -> None:
    candidates, _old = _quota_world(world)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=7_000)
    asset_ids = [asset_id for asset_id, *_rest in candidates]
    ledger = CapacityLedger()

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Load the ledger while the stale rows still count: 6000 ready bytes leave no room under 4000.
        assert ledger.available(conn, 1_000, 4_000) is False
        retired = scheduler._retire_superseded_in_txn(conn, asset_ids, ledger=ledger)
        assert len(retired) == len(VARIANTS)
        # Without ``ready_row_left`` the ledger would still believe 6000 bytes are in use.
        assert ledger.available(conn, 1_000, 4_000) is True
        conn.rollback()


def test_batch_outcomes_equal_retire_first_then_the_old_algorithm_across_a_quota_sweep(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates, _old = _quota_world(world)
    with sqlite3.connect(world.db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    boundary = 0
    for quota in range(0, 12_000, 500):
        outcomes = {}
        for label in ("oracle", "new"):
            run_db = _copy_database(world.db_path, tmp_path / f"{label}_{quota}.db")
            _use_database(monkeypatch, run_db)
            summary = DerivativeReconcileSummary()
            if label == "oracle":
                scheduler: DerivativeScheduler = OldAlgorithmScheduler(worker_count=1, quota_bytes=quota)
                scheduler.retire_superseded_derivatives()
            else:
                scheduler = DerivativeScheduler(worker_count=1, quota_bytes=quota)
            pending = scheduler._coalesce_reconcile_candidates(
                _candidates(candidates), _variants(), priority=3, retry_failed=False, reason="periodic", summary=summary
            )
            outcomes[label] = (summary, pending, _database_fingerprint(run_db))
        assert outcomes["new"][0] == outcomes["oracle"][0], f"summary differs at quota={quota}"
        assert outcomes["new"][1] == outcomes["oracle"][1], f"pending capacity differs at quota={quota}"
        assert outcomes["new"][2] == outcomes["oracle"][2], f"rows differ at quota={quota}"
        boundary += int(bool(outcomes["new"][1]) and outcomes["new"][0].created_jobs > 0)
    assert boundary >= 1, "the sweep never crossed the quota boundary inside a batch"


def test_a_retiring_batch_still_runs_one_capacity_aggregate_pair(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_worker_contention_wk03 import _capacity_aggregates

    candidates, _old = _quota_world(world)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)

    with capture_sql(monkeypatch) as statements:
        scheduler._coalesce_reconcile_candidates(
            _candidates(candidates),
            _variants(),
            priority=3,
            retry_failed=False,
            reason="periodic",
            summary=DerivativeReconcileSummary(),
        )

    assert _capacity_aggregates(statements) == (1, 1)


# ---------------------------------------------------------------------------
# Unlink only after commit, never under serving protection
# ---------------------------------------------------------------------------


def test_a_rolled_back_batch_keeps_its_rows_and_files(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    candidates, old = _quota_world(world)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("batch failed after the rows were retired")

    monkeypatch.setattr(scheduler, "_coalesce_derivative_job", explode)
    with pytest.raises(RuntimeError, match="batch failed"):
        scheduler._coalesce_reconcile_candidates(
            _candidates(candidates),
            _variants(),
            priority=3,
            retry_failed=False,
            reason="periodic",
            summary=DerivativeReconcileSummary(),
        )

    for derivative_id, cache_path in old:
        assert world.derivative(derivative_id)["status"] == "ready"
        assert cache_path.is_file(), "files must not be unlinked unless the retiring transaction committed"


def test_files_are_not_unlinked_while_the_write_transaction_is_open(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates, old = _quota_world(world)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    seen: list[str] = []
    real_unlink = Path.unlink

    def probing_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self in {path for _id, path in old}:
            probe = sqlite3.connect(world.db_path, timeout=0)
            try:
                probe.execute("BEGIN IMMEDIATE")  # raises "database is locked" while the batch still holds the lock
                probe.rollback()
                seen.append("unlinked-after-commit")
            except sqlite3.OperationalError:
                seen.append("unlinked-inside-transaction")
            finally:
                probe.close()
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", probing_unlink)
    scheduler._coalesce_reconcile_candidates(
        _candidates(candidates),
        _variants(),
        priority=3,
        retry_failed=False,
        reason="periodic",
        summary=DerivativeReconcileSummary(),
    )

    assert seen == ["unlinked-after-commit"] * len(old)


def test_a_file_being_served_is_not_unlinked_until_its_lease_is_released(world: World) -> None:
    (image,) = world.add_images(1)
    old = world.seed_ready(image)
    served_id, served_path = old[0]
    world.touch(image)
    world.rescan()
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    scheduler.acquire_serving(str(served_path))

    assert scheduler.retire_superseded_derivatives() == len(old)

    row = world.derivative(served_id)
    assert row["status"] == "skipped" and row["cache_path"] is None, "the row retires immediately"
    assert served_path.is_file(), "the file under a serving lease must survive"
    assert all(not path.exists() for _id, path in old[1:]), "unserved files are removed"

    scheduler.release_serving(str(served_path))
    assert not served_path.exists(), "the deferred unlink runs when the lease is released"


def test_a_deferred_unlink_never_removes_a_file_a_row_references_again(world: World) -> None:
    (image,) = world.add_images(1)
    old = world.seed_ready(image)
    derivative_id, cache_path = old[0]
    world.touch(image)
    world.rescan()
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    scheduler.acquire_serving(str(cache_path))
    scheduler.retire_superseded_derivatives()
    # The identity became current again and the same cache file was republished before the lease ended.
    with sqlite3.connect(world.db_path) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ? WHERE id = ?",
            (str(cache_path), BYTES, derivative_id),
        )

    scheduler.release_serving(str(cache_path))

    assert cache_path.is_file()


# ---------------------------------------------------------------------------
# Integrity repair of pre-existing stale rows
# ---------------------------------------------------------------------------


def test_integrity_pass_repairs_preexisting_superseded_rows(world: World) -> None:
    from backend.integrity_checker import integrity_checker

    first, second, third = world.add_images(3)
    stale_with_files = world.seed_ready(first, mtime_ns=1_500_000_000_000_000_000, size=77)
    stale_without_files = world.seed_ready(second, mtime_ns=1_400_000_000_000_000_000, size=88, with_file=False)
    current = world.seed_ready(third)
    assert world.stale_ready_count() == 2 * len(VARIANTS)

    results = integrity_checker.run_all_checks()

    assert results["derivative_superseded_retired"] == 2 * len(VARIANTS)
    assert world.stale_ready_count() == 0
    _assert_retired(world, stale_with_files)
    for derivative_id, _path in stale_without_files:
        row = world.derivative(derivative_id)
        assert row["status"] == "skipped" and ("skipped", "source_superseded") in row["jobs"]
    for derivative_id, cache_path in current:
        assert world.derivative(derivative_id)["status"] == "ready" and cache_path.is_file()

    again = integrity_checker.run_all_checks()  # idempotent and must not resurrect or fail anything
    assert again["derivative_superseded_retired"] == 0
    _assert_retired(world, stale_with_files)
    assert world.stale_ready_count() == 0


def test_a_file_being_generated_is_not_unlinked(world: World) -> None:
    (image,) = world.add_images(1)
    old = world.seed_ready(image)
    _derivative_id, cache_path = old[0]
    world.touch(image)
    world.rescan()
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    scheduler._generating_paths.add(str(cache_path))

    assert scheduler.retire_superseded_derivatives() == len(old)

    assert cache_path.is_file(), "a path a render is publishing right now belongs to the new row"
    assert all(not path.exists() for _id, path in old[1:])
