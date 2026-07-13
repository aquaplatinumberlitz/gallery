"""Phase 4 integrity, quota, and request-lifecycle coverage.

Purpose:
Verify the Phase 4 desired-state convergence behaviors: capacity-aware
deferral (``deferred_capacity``), truthful eviction (``evicted`` without a
phantom job), integrity-driven repair of missing current rows and
queued-without-job gaps through the common reconciler, and the ID/outcome-based
derivative read model used by request waiters.

Guarantees:
* Background reconciliation never leaves a false ``queued`` row when quota is
  exceeded; it writes ``deferred_capacity`` (no job) and ``evicted`` (no job).
* A quota increase (or periodic reconciliation) reconsiders deferred work.
* Integrity closes absent current derivative rows and queued-without-job states
  without direct calls to ``warm_library``.
* Request waiters inspect a scheduled derivative by ID and branch on fenced
  outcome states rather than polling by source identity.

Run when:
Changing derivative_scheduler.py quota/reservation logic, integrity_checker.py
desired-state checks, or thumbnails.py derivative wait lifecycle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler
from backend.integrity_checker import IntegrityChecker
from backend.metadata_store import (
    get_asset_folder_listing,
    index_file,
    register_library,
)
from tests.conftest import create_test_png


def _catalog_image(root: Path) -> tuple[Path, int, int]:
    library_id = int(register_library(root)["id"])
    image = root / "source.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, 80, 60)
    listing = get_asset_folder_listing(root)
    assert listing is not None
    return image, listing["media"][0].asset_id, library_id


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _current_rows(conn: sqlite3.Connection, asset_id: int) -> list[tuple[str, str]]:
    return [
        (row["kind"], row["status"])
        for row in conn.execute(
            """
            SELECT d.kind, d.status FROM asset_derivatives d
            JOIN assets a ON a.id = d.asset_id
            WHERE d.asset_id = ? AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
            ORDER BY d.kind
            """,
            (asset_id,),
        ).fetchall()
    ]


def test_background_reconcile_defers_when_quota_exceeded(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Tiny quota forces background work into deferred_capacity without a job."""
    _image, asset_id, library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=100)
    summary = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase4")
    variant_count = sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert summary.deferred_capacity == variant_count
    assert summary.created_jobs == 0
    with _connect(isolated_metadata_db) as conn:
        states = {
            row["status"]
            for row in conn.execute("SELECT status FROM asset_derivatives WHERE asset_id = ?", (asset_id,))
        }
        jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id WHERE d.asset_id = ?",
            (asset_id,),
        ).fetchone()[0]
    assert states == {"deferred_capacity"}
    assert jobs == 0


def test_quota_increase_reconsiders_deferred_work(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Increasing capacity lets the reconciler create the deferred jobs."""
    _image, asset_id, library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=100)
    scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase4")
    scheduler.quota_bytes = 10 * 1024**3
    summary = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase4")
    variant_count = sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert summary.created_jobs == variant_count
    assert summary.deferred_capacity == 0
    with sqlite3.connect(isolated_metadata_db) as conn:
        jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id WHERE d.asset_id = ?",
            (asset_id,),
        ).fetchone()[0]
    assert jobs == variant_count


def test_integrity_closes_missing_current_preview_row(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Integrity creates the absent current preview via the reconciler, not warm_library."""
    _image, asset_id, library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    checker = IntegrityChecker(interval=3600)
    summary = checker.run_and_persist(trigger="manual")
    assert summary["status"] == "ok"
    with _connect(isolated_metadata_db) as conn:
        rows = _current_rows(conn, asset_id)
    assert ("thumbnail", "queued") in [(k, s) for k, s in rows]
    assert ("preview", "queued") in [(k, s) for k, s in rows]
    assert summary["issues"]["generated_image_expected_row_missing"] >= 1


def test_integrity_repairs_queued_without_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Integrity requeues a queued derivative whose job is missing."""
    _image, asset_id, library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    for kind, variants in DERIVATIVE_VARIANTS.items():
        scheduler.schedule_derivative(asset_id, kind, str(variants[0]["name"]))
    with _connect(isolated_metadata_db) as conn:
        thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
        row = conn.execute(
            "SELECT id FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail' AND variant = ?",
            (asset_id, str(thumbnail["name"])),
        ).fetchone()
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (row["id"],))
    checker = IntegrityChecker(interval=3600)
    summary = checker.run_and_persist(trigger="manual")
    with _connect(isolated_metadata_db) as conn:
        job_count = conn.execute(
            "SELECT count(*) FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id WHERE d.asset_id = ? AND j.state IN ('queued', 'running')",
            (asset_id,),
        ).fetchone()[0]
    variant_count = sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert job_count == variant_count
    assert summary["issues"]["generated_image_queued_without_job"] >= 1


def test_get_derivative_outcome_reports_current_and_states(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """The fenced read model exposes derivative state and current identity."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    outcome = scheduler.get_derivative_outcome(derivative_id)
    assert outcome is not None
    assert outcome["derivative_id"] == derivative_id
    assert outcome["derivative_state"] == "queued"
    assert outcome["latest_job_state"] == "queued"
    assert outcome["is_current"] is True
    assert scheduler.get_derivative_outcome(999_999) is None
