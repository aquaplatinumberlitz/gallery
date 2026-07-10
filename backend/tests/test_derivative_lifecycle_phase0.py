"""Phase 0 characterization for derivative desired-state convergence.

These tests intentionally separate observed baseline behavior from the target
contracts. Strict xfails are removed only by the phase that owns the relevant
production behavior; an XPASS is therefore a review signal, not a silent pass.

Purpose:
Characterizes the current thumbnail-complete / preview-row-missing gap and the
source-change historical-terminalization gap before any reconciler exists.

Guarantees:
* the baseline can report a desired preview with no current row and no job
* a source change leaves historical variants terminal without current work
* target contracts for reconcile/scan/startup/quota/request remain xfailed until implemented

Run when:
* changing derivative lifecycle convergence behavior or the Phase 0 contracts
* touching scan completion, startup catch-up, quota eviction, or HTTP wait lifecycle
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from backend import scan_worker as catalog_service
from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler
from backend.metadata_store import get_asset_folder_listing, index_file, register_library
from tests.conftest import create_test_png


def _indexed_image(root: Path) -> tuple[Path, int, int]:
    library_id = int(register_library(root)["id"])
    image = root / "source.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, 80, 60)
    listing = get_asset_folder_listing(root)
    assert listing is not None
    return image, listing["media"][0].asset_id, library_id


def test_baseline_reports_preview_coverage_gap_with_no_current_preview_row(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Current status can report an expected gap without a corresponding row/job."""
    _image, asset_id, library_id = _indexed_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))

    status = scheduler.library_status(library_id)
    with sqlite3.connect(isolated_metadata_db) as conn:
        preview_rows = conn.execute(
            "SELECT count(*) FROM asset_derivatives WHERE asset_id = ? AND kind = 'preview'",
            (asset_id,),
        ).fetchone()[0]
        preview_jobs = conn.execute(
            """
            SELECT count(*) FROM derivative_jobs j
            JOIN asset_derivatives d ON d.id = j.derivative_id
            WHERE d.asset_id = ? AND d.kind = 'preview'
            """,
            (asset_id,),
        ).fetchone()[0]
    assert status["expected_derivatives"] == 2
    assert status["ready_derivatives"] == 0
    assert preview_rows == 0
    assert preview_jobs == 0


def test_baseline_source_change_leaves_historical_rows_without_current_work(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Historical rows are terminalized, but baseline creates no new current variants."""
    image, asset_id, library_id = _indexed_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    for kind, variants in DERIVATIVE_VARIANTS.items():
        scheduler.schedule_derivative(asset_id, kind, str(variants[0]["name"]))

    time.sleep(0.01)
    create_test_png(image, size=(96, 72))
    changed = image.stat()
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE assets SET mtime_ns = ?, size = ? WHERE id = ?",
            (changed.st_mtime_ns, changed.st_size, asset_id),
        )
    scheduler._reconcile_queued_jobs()

    with sqlite3.connect(isolated_metadata_db) as conn:
        states = conn.execute(
            "SELECT DISTINCT status FROM asset_derivatives WHERE asset_id = ?",
            (asset_id,),
        ).fetchall()
        current_rows = conn.execute(
            """
            SELECT count(*) FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
            WHERE d.asset_id = ? AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
            """,
            (asset_id,),
        ).fetchone()[0]
    assert states == [("skipped",)]
    assert current_rows == 0
    assert scheduler.library_status(library_id)["ready_derivatives"] == 0


def test_target_reconciler_creates_both_current_configured_variants(
    isolated_gallery_root: Path,
):
    """Target contract: one new image receives one current row/job per default kind."""
    _image, _asset_id, library_id = _indexed_image(isolated_gallery_root)
    summary = DerivativeScheduler().reconcile_desired_derivatives(library_id=library_id, reason="phase_1")
    assert summary.created_derivative_rows == 2
    assert summary.created_jobs == 2


def test_target_successful_scan_queues_thumbnail_and_preview(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Target contract: scan completion closes the absent-row gap without browsing."""
    create_test_png(isolated_gallery_root / "source.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    catalog_service.queue_scan(library_id, trigger="manual")
    assert catalog_service.run_once() is True
    with sqlite3.connect(isolated_metadata_db) as conn:
        rows = conn.execute("SELECT kind, count(*) FROM asset_derivatives GROUP BY kind ORDER BY kind").fetchall()
    assert rows == [("preview", 1), ("thumbnail", 1)]


@pytest.mark.xfail(
    condition=False,
    strict=True,
    reason="Phase 7 owns scan-to-ready derivative convergence acceptance",
)
def test_phase_7_scan_converges_thumbnail_and_preview_files(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
):
    """Phase 7 contract: scanning and one worker materialize both configured files."""
    create_test_png(isolated_gallery_root / "source.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    catalog_service.queue_scan(library_id, trigger="manual")
    assert catalog_service.run_once() is True

    with sqlite3.connect(isolated_metadata_db) as conn:
        rows = conn.execute("SELECT kind, status FROM asset_derivatives ORDER BY kind").fetchall()
    assert rows == [("preview", "queued"), ("thumbnail", "queued")]

    scheduler = DerivativeScheduler(worker_count=1)
    scheduler.start()
    try:
        deadline = time.monotonic() + 5
        ready_rows: list[tuple[str, str, str | None]] = []
        while time.monotonic() < deadline:
            with sqlite3.connect(isolated_metadata_db) as conn:
                ready_rows = conn.execute(
                    "SELECT kind, status, cache_path FROM asset_derivatives ORDER BY kind"
                ).fetchall()
            if len(ready_rows) == 2 and all(
                status == "ready" and cache_path is not None and Path(cache_path).is_file()
                for _kind, status, cache_path in ready_rows
            ):
                break
            time.sleep(0.05)
    finally:
        scheduler.stop()

    assert [(kind, status) for kind, status, _cache_path in ready_rows] == [
        ("preview", "ready"),
        ("thumbnail", "ready"),
    ]
    assert all(cache_path is not None and Path(cache_path).is_file() for _, _, cache_path in ready_rows)
    assert any(isolated_thumbnail_cache.rglob("*"))


def test_target_startup_catchup_repairs_absent_current_preview(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Target contract: startup repairs a seeded preview-only absent-row gap."""
    _image, asset_id, _library_id = _indexed_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    scheduler.start()
    try:
        time.sleep(0.1)
        with sqlite3.connect(isolated_metadata_db) as conn:
            preview_rows = conn.execute(
                "SELECT count(*) FROM asset_derivatives WHERE asset_id = ? AND kind = 'preview'",
                (asset_id,),
            ).fetchone()[0]
        assert preview_rows == 1
    finally:
        scheduler.stop()


def test_target_quota_eviction_never_leaves_queued_derivative_without_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    """Target contract: eviction is visible as evicted, never a false queued row."""
    _image, asset_id, _library_id = _indexed_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=1)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    cache_path = tmp_path / "ready.webp"
    cache_path.write_bytes(b"ready")
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 5 WHERE id = ?",
            (str(cache_path), derivative_id),
        )
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,))
    scheduler._enforce_quota()
    with sqlite3.connect(isolated_metadata_db) as conn:
        state = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()[0]
        jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)
        ).fetchone()[0]
    assert state == "evicted"
    assert jobs == 0


def test_target_scheduler_exposes_fenced_derivative_outcome(
    isolated_gallery_root: Path,
):
    """Target contract: request waiters can inspect a scheduled derivative by ID."""
    _image, asset_id, _library_id = _indexed_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    outcome = scheduler.get_derivative_outcome(derivative_id)
    assert outcome is not None
    assert outcome["derivative_state"] == "queued"
    assert outcome["derivative_id"] == derivative_id
    assert outcome["is_current"] is True
