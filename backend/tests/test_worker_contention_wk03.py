"""WK-03 regression: reconcile transactions must not hold the write lock for seconds.

Purpose:
Pin the worker-lifecycle audit finding WK-03. ``_coalesce_reconcile_candidates``
ran the two capacity aggregates (ready bytes and active-job reservations) for
every one of up to 750 coalesces inside a single ``BEGIN IMMEDIATE``, so a
reconcile batch held the SQLite write lock for seconds and starved every other
writer ("database is locked").

Guarantees:
A reconcile batch evaluates each capacity aggregate at most once; the running
totals the batch keeps in memory produce exactly the same per-identity quota,
eviction, and deferred-capacity outcomes as the old per-coalesce query (checked
against an independent oracle across a quota sweep with every derivative state);
and the public reconcile entry point stays within one aggregate pair per batch.

Run when:
Changing derivative capacity accounting, ``_coalesce_derivative_job``, reconcile
batching, or the quota/eviction/deferred-capacity policy.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler
from backend.derivative_scheduler.models import DerivativeReconcileSummary
from tests.worker_contention_support import VARIANTS, capture_sql, seed_assets, seed_library

READY_BYTES = 1_000
GENEROUS_QUOTA = 1024 * 1024 * 1024
# Pattern of pre-existing derivative states, indexed by (asset * variants + variant) % len.
STATE_PATTERN = (
    "ready_with_file",
    "ready_missing_file",
    "evicted_with_file",
    "evicted_with_file_and_job",
    "evicted_missing_file",
    "deferred_capacity",
    "failed",
    "skipped_retriable",
    "skipped_terminal",
    "queued_with_job",
    "running_with_job",
    "queued_without_job",
    "new_identity",
)


def _is_ready_sum(statement: str) -> bool:
    return "sum(byte_size)" in statement and "status = 'ready'" in statement and "asset_derivatives" in statement


def _is_active_job_count(statement: str) -> bool:
    return "FROM derivative_jobs j" in statement and "j.state IN ('queued', 'running')" in statement


def _capacity_aggregates(statements: list[str]) -> tuple[int, int]:
    return (
        sum(1 for statement in statements if _is_ready_sum(statement)),
        sum(1 for statement in statements if _is_active_job_count(statement)),
    )


def _variants() -> list[tuple[str, dict[str, Any]]]:
    return [(kind, variant) for kind, variants in DERIVATIVE_VARIANTS.items() for variant in variants]


def _candidates(assets: list[tuple[int, str, int, int]]) -> list[tuple[int, int, int]]:
    return [(asset_id, mtime_ns, size) for asset_id, _path, mtime_ns, size in assets]


def _seed_existing_state(
    db_path: Path,
    assets: list[tuple[int, str, int, int]],
    cache_dir: Path,
    *,
    pattern_for: Callable[[int, int], str] | None = None,
    size_for: Callable[[int, int], int] | None = None,
) -> None:
    """Seed one derivative identity per asset/variant according to ``STATE_PATTERN`` (or ``pattern_for``)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        for asset_index, (asset_id, _path, mtime_ns, size) in enumerate(assets):
            for variant_index, (kind, variant, max_edge, quality) in enumerate(VARIANTS):
                if pattern_for is not None:
                    pattern = pattern_for(asset_index, variant_index)
                else:
                    pattern = STATE_PATTERN[(asset_index * len(VARIANTS) + variant_index) % len(STATE_PATTERN)]
                if pattern == "new_identity":
                    continue
                byte_size = size_for(asset_index, variant_index) if size_for is not None else READY_BYTES
                cache_path = cache_dir / f"{asset_id}_{variant}.webp"
                has_file = pattern in {"ready_with_file", "evicted_with_file", "evicted_with_file_and_job"}
                if has_file:
                    cache_path.write_bytes(b"x" * byte_size)
                status = {
                    "ready_with_file": "ready",
                    "ready_missing_file": "ready",
                    "evicted_with_file": "evicted",
                    "evicted_with_file_and_job": "evicted",
                    "evicted_missing_file": "evicted",
                    "deferred_capacity": "deferred_capacity",
                    "failed": "failed",
                    "skipped_retriable": "skipped",
                    "skipped_terminal": "skipped",
                    "queued_with_job": "queued",
                    "running_with_job": "running",
                    "queued_without_job": "queued",
                }[pattern]
                holds_bytes = pattern in {
                    "ready_with_file",
                    "ready_missing_file",
                    "evicted_with_file",
                    "evicted_with_file_and_job",
                    "evicted_missing_file",
                }
                derivative_id = int(
                    conn.execute(
                        """
                        INSERT INTO asset_derivatives (
                          asset_id, kind, variant, source_mtime_ns, source_size, format, quality,
                          max_long_edge, status, cache_path, byte_size
                        ) VALUES (?, ?, ?, ?, ?, 'webp', ?, ?, ?, ?, ?)
                        """,
                        (
                            asset_id,
                            kind,
                            variant,
                            mtime_ns,
                            size,
                            quality,
                            max_edge,
                            status,
                            str(cache_path) if holds_bytes else None,
                            byte_size if holds_bytes else None,
                        ),
                    ).lastrowid
                )
                job_state, result_code = {
                    "ready_with_file": ("done", None),
                    "ready_missing_file": ("done", None),
                    "evicted_with_file": ("done", None),
                    "evicted_with_file_and_job": ("queued", None),
                    "evicted_missing_file": ("done", None),
                    "deferred_capacity": (None, None),
                    "failed": ("failed", "render_failed"),
                    "skipped_retriable": ("skipped", "source_missing"),
                    "skipped_terminal": ("skipped", "source_changed"),
                    "queued_with_job": ("queued", None),
                    "running_with_job": ("running", None),
                    "queued_without_job": ("done", None),
                }[pattern]
                if job_state is not None:
                    conn.execute(
                        "INSERT INTO derivative_jobs (derivative_id, priority, state, result_code) VALUES (?, 3, ?, ?)",
                        (derivative_id, job_state, result_code),
                    )


def _database_fingerprint(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Return timestamp-free derivative rows keyed by identity, for exact outcome comparison."""
    with sqlite3.connect(db_path) as conn:
        derivatives = conn.execute(
            """
            SELECT asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path,
                   byte_size, last_error
            FROM asset_derivatives ORDER BY asset_id, kind, variant, source_mtime_ns, source_size
            """
        ).fetchall()
        jobs = conn.execute(
            """
            SELECT d.asset_id, d.kind, d.variant, j.state, j.priority, j.result_code
            FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id
            ORDER BY d.asset_id, d.kind, d.variant, j.id
            """
        ).fetchall()
    return {"derivatives": [tuple(row) for row in derivatives], "jobs": [tuple(row) for row in jobs]}


def _use_database(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    import backend.config as config_module
    import backend.metadata_store as ms

    monkeypatch.setattr(config_module, "GALLERY_METADATA_DB", db_path)
    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", db_path)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)
    ms.initialize_database()


def _copy_database(source: Path, target: Path) -> Path:
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target


class OldAlgorithmScheduler(DerivativeScheduler):
    """Oracle: the pre-fix algorithm, i.e. two full-table aggregates for every coalesce.

    ``_capacity_available`` is an independent re-implementation of the old query
    and ``_coalesce_reconcile_candidates`` is the old loop that never passed a
    running ledger, so every identity pays for (and sees) fresh aggregates.
    """

    def _capacity_available(self, conn: sqlite3.Connection, estimated_bytes: int, ledger: Any = None) -> bool:
        # ``ledger`` is accepted for signature compatibility and deliberately ignored.
        ready_used = int(
            conn.execute("SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'").fetchone()[
                0
            ]
        )
        active_jobs = int(
            conn.execute(
                """SELECT count(*) FROM derivative_jobs j
                   JOIN asset_derivatives d ON d.id = j.derivative_id
                   WHERE j.state IN ('queued', 'running') AND d.status != 'ready'"""
            ).fetchone()[0]
        )
        return ready_used + active_jobs * estimated_bytes + estimated_bytes <= self.quota_bytes

    def _coalesce_reconcile_candidates(  # type: ignore[override]
        self,
        candidates,
        variants,
        *,
        priority,
        retry_failed,
        reason,
        summary,
    ):
        from backend.derivative_scheduler._common import _CAPACITY_DEFERRED_AUTOMATIC_REASONS
        from backend.metadata_store import _connect

        pending_capacity = []
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            estimated_bytes = self._estimate_new_derivative_bytes(conn)
            for asset_id, mtime_ns, size in candidates:
                current = conn.execute(
                    """
                    SELECT 1 FROM assets
                    WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0
                      AND mtime_ns = ? AND size = ?
                    """,
                    (asset_id, mtime_ns, size),
                ).fetchone()
                if current is None:
                    summary.source_unavailable += len(variants)
                    continue
                for kind, variant in variants:
                    coalesce_args = {
                        "asset_id": asset_id,
                        "kind": kind,
                        "variant": str(variant["name"]),
                        "source_mtime_ns": mtime_ns,
                        "source_size": size,
                        "max_long_edge": int(variant["max_long_edge"]),
                        "quality": int(variant["quality"]),
                        "format": "webp",
                        "priority": priority,
                        "retry_failed": retry_failed,
                        "deferrable": True,
                        "reconsider_deferred_capacity": reason not in _CAPACITY_DEFERRED_AUTOMATIC_REASONS,
                        "estimated_bytes": estimated_bytes,
                    }
                    _derivative_id, outcome = self._coalesce_derivative_job(conn, **coalesce_args)
                    if outcome in {"capacity_needed", "capacity_needed_created"}:
                        pending_capacity.append((coalesce_args, estimated_bytes, outcome == "capacity_needed_created"))
                    else:
                        self._record_reconcile_outcome(summary, outcome)
        return pending_capacity


@pytest.fixture
def seeded_batch(
    isolated_metadata_db: Path, isolated_gallery_root: Path, tmp_path: Path
) -> tuple[Path, list[tuple[int, str, int, int]], Path]:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    assets = seed_assets(isolated_metadata_db, library_id, root, 36)
    cache_dir = tmp_path / "cache"
    _seed_existing_state(isolated_metadata_db, assets, cache_dir)
    return isolated_metadata_db, assets, cache_dir


def test_reconcile_batch_evaluates_each_capacity_aggregate_at_most_once(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    assets = seed_assets(isolated_metadata_db, library_id, root, 60)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)
    variants = _variants()
    summary = DerivativeReconcileSummary()

    with capture_sql(monkeypatch) as statements:
        pending = scheduler._coalesce_reconcile_candidates(
            _candidates(assets),
            variants,
            priority=3,
            retry_failed=False,
            reason="periodic",
            summary=summary,
        )

    ready_sums, active_counts = _capacity_aggregates(statements)
    assert pending == []
    assert summary.created_jobs == len(assets) * len(variants)
    assert ready_sums <= 1, f"ready-bytes aggregate ran {ready_sums} times in one reconcile batch"
    assert active_counts <= 1, f"active-job aggregate ran {active_counts} times in one reconcile batch"


def test_capacity_aggregates_stay_at_one_pair_when_quota_is_exhausted_midway(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    assets = seed_assets(isolated_metadata_db, library_id, root, 40)
    # 64 KiB fallback estimate per new derivative: room for about 30 of 120 identities.
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=30 * 64 * 1024)
    summary = DerivativeReconcileSummary()

    with capture_sql(monkeypatch) as statements:
        pending = scheduler._coalesce_reconcile_candidates(
            _candidates(assets),
            _variants(),
            priority=3,
            retry_failed=False,
            reason="periodic",
            summary=summary,
        )

    ready_sums, active_counts = _capacity_aggregates(statements)
    assert 0 < summary.created_jobs < len(assets) * len(_variants())
    assert pending, "quota was never exhausted; the boundary was not exercised"
    assert (ready_sums, active_counts) == (1, 1)


def test_public_reconcile_runs_one_capacity_pair_per_batch(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.derivative_scheduler.reconcile as reconcile_module
    from tests.conftest import create_test_png

    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    with sqlite3.connect(isolated_metadata_db) as conn:
        for index in range(75):
            image = root / f"real_{index:03d}.png"
            create_test_png(image, size=(8, 8))
            stat = image.stat()
            conn.execute(
                """
                INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, metadata_state)
                VALUES (?, ?, ?, ?, 'image', ?, ?, 'pending')
                """,
                (library_id, str(image), str(root), image.name, stat.st_mtime_ns, stat.st_size),
            )
    monkeypatch.setattr(reconcile_module, "DERIVATIVE_RECONCILE_BATCH_SIZE", 25)
    monkeypatch.setattr(reconcile_module, "DERIVATIVE_RECONCILE_YIELD_SECONDS", 0)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=GENEROUS_QUOTA)

    with capture_sql(monkeypatch) as statements:
        summary = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="periodic")

    ready_sums, active_counts = _capacity_aggregates(statements)
    assert summary.created_jobs == 75 * len(_variants())
    assert ready_sums <= 3 and active_counts <= 3, (ready_sums, active_counts)


@pytest.mark.parametrize("reason", ["periodic", "integrity"])
@pytest.mark.parametrize("retry_failed", [False, True])
def test_batch_ledger_matches_old_per_coalesce_outcomes_across_a_quota_sweep(
    seeded_batch: tuple[Path, list[tuple[int, str, int, int]], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    retry_failed: bool,
) -> None:
    base_db, assets, _cache_dir = seeded_batch
    with sqlite3.connect(base_db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    variants = _variants()
    outcomes_seen: set[str] = set()
    boundary_hits = 0
    # Ready bytes already on disk plus per-job reservations: sweep from "nothing fits" to "everything fits".
    for quota in range(0, 160_000, 5_000):
        results: dict[str, tuple[dict[str, int], list[Any], dict[str, list[tuple[Any, ...]]]]] = {}
        for label, scheduler_cls in (("old", OldAlgorithmScheduler), ("new", DerivativeScheduler)):
            run_db = _copy_database(base_db, tmp_path / f"{label}_{quota}.db")
            _use_database(monkeypatch, run_db)
            scheduler = scheduler_cls(worker_count=1, quota_bytes=quota)
            summary = DerivativeReconcileSummary()
            pending = scheduler._coalesce_reconcile_candidates(
                _candidates(assets),
                variants,
                priority=2,
                retry_failed=retry_failed,
                reason=reason,
                summary=summary,
            )
            results[label] = (asdict(summary), pending, _database_fingerprint(run_db))
        assert results["new"][0] == results["old"][0], f"summary differs at quota={quota}"
        assert results["new"][1] == results["old"][1], f"pending capacity differs at quota={quota}"
        assert results["new"][2] == results["old"][2], f"derivative/job rows differ at quota={quota}"
        summary_values = results["new"][0]
        pending_count = len(results["new"][1])
        boundary_hits += int(pending_count > 0 and summary_values["created_jobs"] > 0)
        if pending_count or summary_values["deferred_capacity"]:
            outcomes_seen.add("capacity_limited")
        if summary_values["created_jobs"]:
            outcomes_seen.add("created")
    # The sweep must really cross the exhaustion boundary inside single batches.
    assert boundary_hits >= 3
    assert outcomes_seen == {"capacity_limited", "created"}


def test_batch_ledger_matches_old_outcomes_for_seeded_random_states(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seeded random derivative states, byte sizes, quotas, and options: the ledger never disagrees."""
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    assets = seed_assets(isolated_metadata_db, library_id, root, 30)
    rng = random.Random(20261027)
    patterns = {
        (asset_index, variant_index): rng.choice(STATE_PATTERN)
        for asset_index in range(len(assets))
        for variant_index in range(len(VARIANTS))
    }
    sizes = {key: rng.randint(400, 3_000) for key in patterns}
    _seed_existing_state(
        isolated_metadata_db,
        assets,
        tmp_path / "cache",
        pattern_for=lambda a, v: patterns[(a, v)],
        size_for=lambda a, v: sizes[(a, v)],
    )
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    ready_bytes = sum(
        sizes[key] for key, pattern in patterns.items() if pattern in {"ready_with_file", "ready_missing_file"}
    )
    variants = _variants()
    boundary_trials = 0
    for trial in range(24):
        quota = rng.randint(max(0, ready_bytes // 2), ready_bytes + 120_000)
        retry_failed = bool(rng.getrandbits(1))
        reason = rng.choice(["periodic", "catalog_scan", "integrity", "startup"])
        shuffled = _candidates(assets)
        rng.shuffle(shuffled)
        results = {}
        for label, scheduler_cls in (("old", OldAlgorithmScheduler), ("new", DerivativeScheduler)):
            run_db = _copy_database(isolated_metadata_db, tmp_path / f"{label}_{trial}.db")
            _use_database(monkeypatch, run_db)
            scheduler = scheduler_cls(worker_count=1, quota_bytes=quota)
            summary = DerivativeReconcileSummary()
            pending = scheduler._coalesce_reconcile_candidates(
                shuffled, variants, priority=1, retry_failed=retry_failed, reason=reason, summary=summary
            )
            results[label] = (asdict(summary), pending, _database_fingerprint(run_db))
        assert results["new"] == results["old"], f"trial {trial} diverged (quota={quota}, reason={reason})"
        boundary_trials += int(bool(results["new"][1]) and results["new"][0]["created_jobs"] > 0)
    assert boundary_trials >= 5
