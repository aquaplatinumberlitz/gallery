"""Catalog and lifecycle coverage for the durable derivative scheduler.

Purpose:
Cover derivative job scheduling, coalescing, variant lookup, and catalog status
integration.

Guarantees:
Derivative warm/clear flows update durable rows predictably and report library
coverage without duplicate jobs.

Run when:
Changing derivative scheduler, variant definitions, cache clearing, or status
coverage fields.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler, derivative_variant
from backend.metadata_store import get_asset_folder_listing, index_file, list_libraries, register_library
from tests.conftest import create_test_png


def _catalog_image(root: Path) -> tuple[Path, int]:
    register_library(root)
    image = root / "source.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, 80, 60)
    listing = get_asset_folder_listing(root)
    assert listing is not None
    return image, listing["media"][0].asset_id


def test_schedule_coalesces_jobs_and_reports_library_status(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=99, quota_bytes=1024)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]

    assert scheduler.worker_count == 8
    assert scheduler.find_asset_id(image) == asset_id
    assert scheduler.get_asset_path(asset_id) == image
    assert scheduler.find_asset_id(isolated_gallery_root / "missing.png") is None
    assert scheduler.get_asset_path(999_999) is None
    assert scheduler.get_derivative_status(asset_id, "thumbnail", str(thumbnail["name"])) is None

    derivative_id = scheduler.schedule_derivative(
        asset_id,
        "thumbnail",
        str(thumbnail["name"]),
        priority=3,
    )
    assert scheduler.get_derivative_status(asset_id, "thumbnail", str(thumbnail["name"])) == "queued"
    assert (
        scheduler.schedule_derivative(
            asset_id,
            "thumbnail",
            str(thumbnail["name"]),
            priority=-5,
        )
        == derivative_id
    )

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT priority FROM derivative_jobs").fetchone()[0] == 0

    library_id = list_libraries()[0]["id"]
    status = scheduler.library_status(library_id)
    assert status["library_id"] == library_id
    assert status["policy"] == "warm"
    assert status["converged"] is False
    assert status["actionable_missing_derivatives"] == 1
    assert status["expected_derivatives"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert status["by_kind"]["thumbnail"]["queued_derivatives"] == 1
    assert status["by_kind"]["preview"]["missing_derivatives"] == 1
    assert status["queued_jobs"] == 1
    assert status["quota_bytes"] == 1024
    with pytest.raises(KeyError):
        scheduler.library_status(999_999)
    with pytest.raises(KeyError):
        scheduler.schedule_derivative(999_999, "thumbnail", "thumb_512")
    with pytest.raises(ValueError, match="Unsupported derivative kind"):
        scheduler.schedule_derivative(asset_id, "unknown", "unknown")


def test_ready_derivative_lookup_warming_and_clear(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import backend.derivative_scheduler as scheduler_module

    image, asset_id = _catalog_image(isolated_gallery_root)
    cache_root = tmp_path / "derivative-cache"
    cache_file = cache_root / "files" / "ready.webp"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"ready derivative")
    monkeypatch.setattr(scheduler_module, "THUMBNAIL_CACHE_DIR", cache_root)

    scheduler = DerivativeScheduler(quota_bytes=1024)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    variant = str(thumbnail["name"])
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", variant)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ? WHERE id = ?",
            (str(cache_file), cache_file.stat().st_size, derivative_id),
        )

    ready = scheduler.get_ready_derivative(asset_id, "thumbnail", variant)
    assert ready is not None
    assert ready["id"] == derivative_id
    assert scheduler.get_derivative_status(asset_id, "thumbnail", variant) == "ready"
    assert scheduler.get_ready_derivative(999_999, "thumbnail", variant) is None

    warmed = scheduler.warm_library(list_libraries()[0]["id"])
    assert warmed == {
        "assets": 1,
        "derivatives_considered": sum(len(variants) for variants in DERIVATIVE_VARIANTS.values()),
    }

    scheduler.acquire_serving(str(cache_file))
    cleared = scheduler.clear_all()
    assert cleared["catalog_entries_cleared"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert cleared["files_deleted"] == 0
    assert cache_file.exists()
    scheduler.release_serving(str(cache_file))


def test_library_status_excludes_legacy_variants(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    stat = image.stat()
    cache_dir = tmp_path / "derivatives"
    cache_dir.mkdir()
    scheduler = DerivativeScheduler(quota_bytes=1024 * 1024)

    current_bytes = 0
    current_rows: list[tuple[str, int, int]] = []
    for kind, variants in DERIVATIVE_VARIANTS.items():
        for variant in variants:
            cache_file = cache_dir / f"{kind}-{variant['name']}.webp"
            cache_file.write_bytes(b"current")
            current_bytes += cache_file.stat().st_size
            derivative_id = scheduler.schedule_derivative(asset_id, kind, str(variant["name"]))
            current_rows.append((str(cache_file), cache_file.stat().st_size, derivative_id))

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.executemany(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ? WHERE id = ?",
            current_rows,
        )

        legacy_file = cache_dir / "edge-128-q-78-webp.webp"
        legacy_file.write_bytes(b"legacy")
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format, quality,
              max_long_edge, status, cache_path, byte_size
            ) VALUES (?, 'thumbnail', 'edge-128-q-78-webp', ?, ?, 'webp', 78, 128, 'ready', ?, ?)
            """,
            (asset_id, float(stat.st_mtime_ns), stat.st_size, str(legacy_file), legacy_file.stat().st_size),
        )

    status = scheduler.library_status(list_libraries()[0]["id"])

    assert status["expected_derivatives"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert status["ready_derivatives"] == status["expected_derivatives"]
    assert status["by_kind"]["thumbnail"]["expected_derivatives"] == len(DERIVATIVE_VARIANTS["thumbnail"])
    assert status["by_kind"]["thumbnail"]["ready_derivatives"] == len(DERIVATIVE_VARIANTS["thumbnail"])
    assert status["by_kind"]["preview"]["expected_derivatives"] == len(DERIVATIVE_VARIANTS["preview"])
    assert status["by_kind"]["preview"]["ready_derivatives"] == len(DERIVATIVE_VARIANTS["preview"])
    assert status["quota_used_bytes"] == current_bytes


def test_library_status_excludes_offline_assets(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    library_id = list_libraries()[0]["id"]
    scheduler = DerivativeScheduler(quota_bytes=1024)

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (asset_id,))

    assert scheduler.warm_library(library_id)["assets"] == 0
    status = scheduler.library_status(library_id)
    assert status["total_assets"] == 0
    assert status["ready_derivatives"] == 0
    assert status["expected_derivatives"] == 0
    assert all(kind["expected_derivatives"] == 0 for kind in status["by_kind"].values())


def test_derivative_variant_uses_named_and_custom_variants():
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    assert (
        derivative_variant(
            "thumbnail",
            int(thumbnail["max_long_edge"]),
            int(thumbnail["quality"]),
            "webp",
        )
        == thumbnail["name"]
    )
    assert derivative_variant("thumbnail", 333, 71, "jpeg") == "edge-333-q-71-jpeg"


def test_reconcile_current_variants_is_idempotent(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _image, _asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    library_id = list_libraries()[0]["id"]

    first = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase_1")
    second = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase_1")

    assert first.created_derivative_rows == 2
    assert first.created_jobs == 2
    assert second.created_derivative_rows == 0
    assert second.created_jobs == 0
    assert second.already_active == 2
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM asset_derivatives").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0] == 2


def test_reconcile_repairs_ready_file_and_job_row_gaps(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    _image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    missing_cache = tmp_path / "missing.webp"
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ? WHERE id = ?",
            (str(missing_cache), derivative_id),
        )
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,))

    summary = scheduler.reconcile_desired_derivatives(asset_ids=[asset_id], kinds=["thumbnail"], reason="phase_1")

    assert summary.requeued_without_job == 1
    assert summary.created_jobs == 1
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert (
            conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()[0]
            == "queued"
        )
        assert (
            conn.execute("SELECT count(*) FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)).fetchone()[0]
            == 1
        )


def test_reconcile_keeps_current_terminal_failure_without_explicit_retry(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    library_id = list_libraries()[0]["id"]
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE asset_derivatives SET status = 'failed' WHERE id = ?", (derivative_id,))
        conn.execute("UPDATE derivative_jobs SET state = 'failed' WHERE derivative_id = ?", (derivative_id,))

    summary = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase_1")

    assert summary.terminal_failed == 1
    assert summary.created_jobs == 1  # The preview remains absent and is scheduled.
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert (
            conn.execute("SELECT count(*) FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)).fetchone()[0]
            == 1
        )


def test_automatic_reconcile_respects_warm_enabled_but_manual_warm_overrides_it(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _image, _asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    library_id = list_libraries()[0]["id"]
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE libraries SET warm_enabled = 0 WHERE id = ?", (library_id,))

    automatic = scheduler.reconcile_desired_derivatives(library_id=library_id, reason="phase_2")
    manual = scheduler.warm_library(library_id)

    assert automatic.created_jobs == 0
    assert manual["derivatives_considered"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())


def test_library_status_makes_preview_only_warm_gap_actionable_and_on_demand_informational(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    _image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    library_id = list_libraries()[0]["id"]
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    cache_path = tmp_path / "thumbnail.webp"
    cache_path.write_bytes(b"ready")
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 5 WHERE id = ?",
            (str(cache_path), derivative_id),
        )

    warm = scheduler.library_status(library_id)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE libraries SET warm_enabled = 0 WHERE id = ?", (library_id,))
    on_demand = scheduler.library_status(library_id)

    assert warm["by_kind"]["preview"]["missing_derivatives"] == 1
    assert warm["actionable_missing_derivatives"] == 1
    assert warm["converged"] is False
    assert on_demand["policy"] == "on_demand"
    assert on_demand["desired_derivatives"] == 0
    assert on_demand["actionable_missing_derivatives"] == 0
    assert on_demand["converged"] is True


def test_missing_source_after_claim_is_skipped_without_escaping(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    job = scheduler._claim_job()
    assert job is not None

    image.unlink()
    scheduler._run_job(job)

    with sqlite3.connect(isolated_metadata_db) as conn:
        derivative = conn.execute(
            "SELECT status, last_error FROM asset_derivatives WHERE id = ?",
            (derivative_id,),
        ).fetchone()
        queued_job = conn.execute(
            "SELECT state, result_code FROM derivative_jobs WHERE id = ?",
            (job["job_id"],),
        ).fetchone()
    assert derivative[0] == "skipped"
    assert queued_job == ("skipped", "source_missing")


def test_worker_loop_contains_job_exception_and_processes_next_job(monkeypatch: pytest.MonkeyPatch):
    scheduler = DerivativeScheduler()
    jobs = iter(({"job_id": 1}, {"job_id": 2}, None))
    processed: list[int] = []

    monkeypatch.setattr(scheduler, "_claim_job", lambda _worker_id=None: next(jobs))

    def run_job(job):
        processed.append(job["job_id"])
        if job["job_id"] == 1:
            raise RuntimeError("handler escaped")
        scheduler._stop_event.set()

    monkeypatch.setattr(scheduler, "_run_job", run_job)
    scheduler._worker_loop()

    assert processed == [1, 2]


def test_claim_skips_job_when_asset_becomes_offline(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (asset_id,))

    assert scheduler._claim_job() is None
    with sqlite3.connect(isolated_metadata_db) as conn:
        job = conn.execute(
            "SELECT state, result_code FROM derivative_jobs WHERE derivative_id = ?",
            (derivative_id,),
        ).fetchone()
        derivative = conn.execute(
            "SELECT status FROM asset_derivatives WHERE id = ?",
            (derivative_id,),
        ).fetchone()
    assert job == ("skipped", "asset_inactive")
    assert derivative == ("skipped",)


def test_startup_recovers_current_running_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=1)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            UPDATE derivative_jobs
            SET state = 'running', attempts = 1, claimed_by = 'dead-worker',
                claim_token = 'dead-token', lease_expires_at = julianday('now') - 1
            WHERE derivative_id = ?
            """,
            (derivative_id,),
        )
        conn.execute("UPDATE asset_derivatives SET status = 'running' WHERE id = ?", (derivative_id,))

    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    scheduler.start()
    scheduler.stop()

    with sqlite3.connect(isolated_metadata_db) as conn:
        job = conn.execute(
            "SELECT state, claimed_by, claim_token, lease_expires_at FROM derivative_jobs WHERE derivative_id = ?",
            (derivative_id,),
        ).fetchone()
    assert job == ("queued", None, None, None)


def test_obsolete_claim_token_cannot_overwrite_newer_claim(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    stale_job = scheduler._claim_job("old-worker")
    assert stale_job is not None

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            UPDATE derivative_jobs
            SET state = 'queued', claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL
            WHERE id = ?
            """,
            (stale_job["job_id"],),
        )
        conn.execute("UPDATE asset_derivatives SET status = 'queued' WHERE id = ?", (derivative_id,))
    current_job = scheduler._claim_job("new-worker")
    assert current_job is not None

    scheduler._handle_failure(stale_job, RuntimeError("late failure"))

    with sqlite3.connect(isolated_metadata_db) as conn:
        job = conn.execute(
            "SELECT state, claimed_by, claim_token FROM derivative_jobs WHERE id = ?",
            (stale_job["job_id"],),
        ).fetchone()
        derivative = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()
    assert job == ("running", "new-worker", current_job["claim_token"])
    assert derivative == ("running",)


def test_expired_claim_with_exhausted_attempts_becomes_failed(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            UPDATE derivative_jobs
            SET state = 'running', attempts = 3, claimed_by = 'dead-worker',
                claim_token = 'dead-token', lease_expires_at = julianday('now') - 1
            WHERE derivative_id = ?
            """,
            (derivative_id,),
        )
        conn.execute("UPDATE asset_derivatives SET status = 'running' WHERE id = ?", (derivative_id,))

    assert scheduler._recover_running_jobs(expired_only=True) == 1

    with sqlite3.connect(isolated_metadata_db) as conn:
        job = conn.execute(
            "SELECT state, result_code, claimed_by, claim_token FROM derivative_jobs WHERE derivative_id = ?",
            (derivative_id,),
        ).fetchone()
    assert job == ("failed", "attempts_exhausted", None, None)


def test_claim_does_not_scan_the_whole_queue_before_selecting_valid_work(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))

    def fail_reconcile() -> None:
        raise AssertionError("valid claims must not run full queued-job reconciliation")

    monkeypatch.setattr(scheduler, "_reconcile_queued_jobs", fail_reconcile)

    assert scheduler._claim_job() is not None


def test_transient_failure_uses_exactly_three_attempts_with_backoff(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    delays: list[float] = []
    monkeypatch.setattr(scheduler._stop_event, "wait", lambda delay: delays.append(delay) or False)

    for expected_attempt in (1, 2, 3):
        job = scheduler._claim_job()
        assert job is not None
        assert job["job_attempts"] == expected_attempt
        scheduler._handle_failure(job, OSError("temporary I/O failure"))

    with sqlite3.connect(isolated_metadata_db) as conn:
        job_row = conn.execute(
            "SELECT state, attempts, result_code FROM derivative_jobs WHERE derivative_id = ?",
            (derivative_id,),
        ).fetchone()
    assert job_row == ("failed", 3, "attempts_exhausted")
    assert delays == [1, 2]


def test_recovery_cannot_overwrite_a_claim_that_completed_after_selection(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    job = scheduler._claim_job("worker-that-will-finish")
    assert job is not None

    def complete_selected_claim(_row: sqlite3.Row) -> None:
        with sqlite3.connect(isolated_metadata_db) as conn:
            conn.execute(
                """
                UPDATE derivative_jobs
                SET state = 'done', claim_token = NULL, claimed_by = NULL, lease_expires_at = NULL
                WHERE id = ?
                """,
                (job["job_id"],),
            )
            conn.execute("UPDATE asset_derivatives SET status = 'ready' WHERE id = ?", (derivative_id,))
        return None

    monkeypatch.setattr(scheduler, "_inapplicable_result", complete_selected_claim)

    assert scheduler._recover_running_jobs(claimed_by="worker-that-will-finish") == 0
    with sqlite3.connect(isolated_metadata_db) as conn:
        recovered_job = conn.execute(
            "SELECT state FROM derivative_jobs WHERE id = ?",
            (job["job_id"],),
        ).fetchone()
        derivative = conn.execute(
            "SELECT status FROM asset_derivatives WHERE id = ?",
            (derivative_id,),
        ).fetchone()
    assert recovered_job == ("done",)
    assert derivative == ("ready",)


def test_warm_library_continues_when_asset_becomes_inactive_during_scheduling(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _, first_asset_id = _catalog_image(isolated_gallery_root)
    second_image = isolated_gallery_root / "second.png"
    create_test_png(second_image, size=(80, 60))
    stat = second_image.stat()
    assert index_file(
        second_image,
        second_image.name,
        second_image.parent,
        "photo",
        stat.st_mtime,
        stat.st_size,
        80,
        60,
    )
    scheduler = DerivativeScheduler()
    original_schedule = scheduler.schedule_derivative
    first_call = True

    def schedule_with_inactive_race(*args, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            with sqlite3.connect(isolated_metadata_db) as conn:
                conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (first_asset_id,))
            raise KeyError(first_asset_id)
        return original_schedule(*args, **kwargs)

    monkeypatch.setattr(scheduler, "schedule_derivative", schedule_with_inactive_race)
    result = scheduler.warm_library(list_libraries()[0]["id"])

    expected = sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert result["derivatives_considered"] == expected


def test_library_status_ignores_historical_failed_attempt_after_success(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    failed_job = scheduler._claim_job()
    assert failed_job is not None
    scheduler._handle_failure(failed_job, RuntimeError("first attempt failed"))

    scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    successful_job = scheduler._claim_job()
    assert successful_job is not None
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE derivative_jobs SET state = 'done' WHERE id = ?",
            (successful_job["job_id"],),
        )
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready' WHERE id = ?",
            (derivative_id,),
        )

    status = scheduler.library_status(list_libraries()[0]["id"])
    assert status["failed_jobs"] == 0
    assert status["queued_jobs"] == 0
    assert status["running_jobs"] == 0
