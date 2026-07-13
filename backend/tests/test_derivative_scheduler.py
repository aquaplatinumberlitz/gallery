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
import time
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
    scheduler = DerivativeScheduler(worker_count=99, quota_bytes=1024 * 1024)
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
    assert status["actionable_missing_derivatives"] == 2
    assert status["expected_derivatives"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert status["by_kind"]["thumbnail"]["queued_derivatives"] == 1
    assert status["by_kind"]["preview"]["missing_derivatives"] == 1
    assert status["queued_jobs"] == 1
    assert status["quota_bytes"] == 1024 * 1024
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
    assert status["library_used_bytes"] == current_bytes
    assert status["quota_used_bytes"] == current_bytes + legacy_file.stat().st_size


def test_library_status_reports_library_and_global_quota_usage(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    first_root = isolated_gallery_root / "first"
    second_root = isolated_gallery_root / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_image, first_asset = _catalog_image(first_root)
    second_image, second_asset = _catalog_image(second_root)
    scheduler = DerivativeScheduler(quota_bytes=1_000)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    first_id = scheduler.schedule_derivative(first_asset, "thumbnail", str(thumbnail["name"]))
    second_id = scheduler.schedule_derivative(second_asset, "thumbnail", str(thumbnail["name"]))
    first_cache = tmp_path / "first.webp"
    second_cache = tmp_path / "second.webp"
    first_cache.write_bytes(b"a" * 100)
    second_cache.write_bytes(b"b" * 300)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 100 WHERE id = ?",
            (str(first_cache), first_id),
        )
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 300 WHERE id = ?",
            (str(second_cache), second_id),
        )

    first_library_id = next(
        int(library["id"]) for library in list_libraries() if library["root_path"] == str(first_image.parent)
    )
    status = scheduler.library_status(first_library_id)

    assert second_image.is_file()
    assert status["library_used_bytes"] == 100
    assert status["quota_used_bytes"] == 400
    assert status["quota_bytes"] == 1_000
    assert status["quota_utilization"] == pytest.approx(0.4)


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

    assert first.created_derivative_rows == 3
    assert first.created_jobs == 3
    assert second.created_derivative_rows == 0
    assert second.created_jobs == 0
    assert second.already_active == 3
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM asset_derivatives").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0] == 3


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
    assert summary.created_jobs == 2
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
    assert summary.created_jobs == 2  # The other thumbnail and preview remain absent and are scheduled.
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
    assert warm["actionable_missing_derivatives"] == 2
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


# ---------------------------------------------------------------------------
# Workstream 1 + 2: Rollback-safe eviction and insufficient-capacity rejection
# ---------------------------------------------------------------------------


def test_rollback_after_eviction_does_not_cause_stale_unlink(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Committed file eviction cannot be resurrected by a later transaction rollback."""
    import backend.derivative_scheduler as scheduler_module

    image, asset_id = _catalog_image(isolated_gallery_root)
    cache_root = tmp_path / "derivative-cache"
    cache_root.mkdir()
    monkeypatch.setattr(scheduler_module, "THUMBNAIL_CACHE_DIR", cache_root)

    scheduler = DerivativeScheduler(quota_bytes=300)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    preview = DERIVATIVE_VARIANTS["preview"][0]
    thumb_variant = str(thumbnail["name"])
    prev_variant = str(preview["name"])

    id1 = scheduler.schedule_derivative(asset_id, "thumbnail", thumb_variant)
    id2 = scheduler.schedule_derivative(asset_id, "preview", prev_variant)
    cf1 = cache_root / "f1.webp"
    cf2 = cache_root / "f2.webp"
    cf1.write_bytes(b"x" * 200)
    cf2.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cf1), id1),
        )
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cf2), id2),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id IN (?, ?)", (id1, id2))

    assert scheduler._reserve_capacity(200), "capacity should be reservable"
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (asset_id,))
        conn.rollback()

    with sqlite3.connect(isolated_metadata_db) as conn:
        ready = conn.execute("SELECT count(*) FROM asset_derivatives WHERE status = 'ready'").fetchone()[0]
        stale_paths = conn.execute(
            "SELECT count(*) FROM asset_derivatives WHERE status = 'evicted' AND cache_path IS NOT NULL"
        ).fetchone()[0]
    assert ready == 0
    assert stale_paths == 0
    assert not cf1.exists()
    assert not cf2.exists()


def test_insufficient_eligible_bytes_returns_not_reservable(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Workstream 2: need 250 bytes, only 100 eligible -> not reservable, no eviction."""
    import backend.derivative_scheduler as scheduler_module

    image, asset_id = _catalog_image(isolated_gallery_root)
    cache_root = tmp_path / "derivative-cache"
    cache_root.mkdir()
    monkeypatch.setattr(scheduler_module, "THUMBNAIL_CACHE_DIR", cache_root)

    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    variant = str(thumbnail["name"])

    did = scheduler.schedule_derivative(asset_id, "thumbnail", variant)
    cf = cache_root / "f.webp"
    cf.write_bytes(b"x" * 100)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 100 WHERE id = ?",
            (str(cf), did),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (did,))

    assert not scheduler._reserve_capacity(250), "need 250, only 100 eligible -> not reservable"
    with sqlite3.connect(isolated_metadata_db) as conn:
        ready = conn.execute("SELECT count(*) FROM asset_derivatives WHERE status = 'ready'").fetchone()[0]
    assert ready == 1, "ready row should be preserved"
    assert cf.exists(), "cache file should still exist"


def test_unlink_failure_restores_ready_and_leaves_target_deferred(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed unlink restores the victim and never queues unreserved work."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    cache_file = tmp_path / "ready.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cache_file), did),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (did,))

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:  # noqa: ARG001
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    summary = scheduler.reconcile_desired_derivatives(
        asset_ids=[asset_id],
        kinds=["preview"],
        reason="test",
        respect_warm_policy=False,
    )

    assert summary.created_jobs == 0
    assert summary.deferred_capacity == 1
    assert cache_file.exists()
    with sqlite3.connect(isolated_metadata_db) as conn:
        victim = conn.execute("SELECT status, cache_path FROM asset_derivatives WHERE id = ?", (did,)).fetchone()
        target = conn.execute(
            "SELECT status FROM asset_derivatives WHERE asset_id = ? AND kind = 'preview'", (asset_id,)
        ).fetchone()
    assert victim == ("ready", str(cache_file))
    assert target == ("deferred_capacity",)


def test_served_ready_file_is_not_evicted(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    """Lookup-to-stream acquisition is atomic with eviction candidate selection."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    variant = str(thumbnail["name"])
    did = scheduler.schedule_derivative(asset_id, "thumbnail", variant)
    cache_file = tmp_path / "served.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cache_file), did),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (did,))

    ready = scheduler.acquire_ready_derivative(asset_id, "thumbnail", variant)
    assert ready is not None
    summary = scheduler.reconcile_desired_derivatives(
        asset_ids=[asset_id],
        kinds=["preview"],
        reason="test",
        respect_warm_policy=False,
    )
    scheduler.release_serving(str(cache_file))

    assert summary.created_jobs == 0
    assert summary.deferred_capacity == 1
    assert cache_file.exists()
    with sqlite3.connect(isolated_metadata_db) as conn:
        row = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (did,)).fetchone()
    assert row == ("ready",)


def test_schedule_deferred_identity_stays_non_runnable_when_unlink_fails(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """The interactive retry path cannot publish a job backed by fictional capacity."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    preview = DERIVATIVE_VARIANTS["preview"][0]
    thumbnail_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    preview_id = scheduler.schedule_derivative(asset_id, "preview", str(preview["name"]))
    cache_file = tmp_path / "interactive-victim.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cache_file), thumbnail_id),
        )
        conn.execute(
            "UPDATE asset_derivatives SET status = 'deferred_capacity' WHERE id = ?",
            (preview_id,),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (thumbnail_id,))
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (preview_id,))

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:  # noqa: ARG001
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    scheduled_id = scheduler.schedule_derivative(asset_id, "preview", str(preview["name"]))

    assert scheduled_id == preview_id
    assert cache_file.exists()
    with sqlite3.connect(isolated_metadata_db) as conn:
        victim = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (thumbnail_id,)).fetchone()
        target = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (preview_id,)).fetchone()
        active_jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ? AND state IN ('queued', 'running')",
            (preview_id,),
        ).fetchone()[0]
    assert victim == ("ready",)
    assert target == ("deferred_capacity",)
    assert active_jobs == 0


def test_successful_capacity_finalization_queues_exactly_once(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    """Successful deletion is committed before one target job becomes runnable."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    preview = DERIVATIVE_VARIANTS["preview"][0]
    thumbnail_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    preview_id = scheduler.schedule_derivative(asset_id, "preview", str(preview["name"]))
    cache_file = tmp_path / "successful-victim.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cache_file), thumbnail_id),
        )
        conn.execute("UPDATE asset_derivatives SET status = 'deferred_capacity' WHERE id = ?", (preview_id,))
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (thumbnail_id,))
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (preview_id,))

    assert scheduler.schedule_derivative(asset_id, "preview", str(preview["name"])) == preview_id
    assert scheduler.schedule_derivative(asset_id, "preview", str(preview["name"])) == preview_id

    assert not cache_file.exists()
    with sqlite3.connect(isolated_metadata_db) as conn:
        victim = conn.execute(
            "SELECT status, cache_path, byte_size FROM asset_derivatives WHERE id = ?", (thumbnail_id,)
        ).fetchone()
        target = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (preview_id,)).fetchone()
        active_jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ? AND state IN ('queued', 'running')",
            (preview_id,),
        ).fetchone()[0]
    assert victim == ("evicted", None, None)
    assert target == ("queued",)
    assert active_jobs == 1


def test_periodic_reconcile_does_not_rotate_capacity_deferred_variants(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    """Periodic reconciliation keeps the ready victim until an explicit repair trigger."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=200)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    preview = DERIVATIVE_VARIANTS["preview"][0]
    thumbnail_id = scheduler.schedule_derivative(asset_id, "thumbnail", str(thumbnail["name"]))
    preview_id = scheduler.schedule_derivative(asset_id, "preview", str(preview["name"]))
    cache_file = tmp_path / "stable-ready.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 200 WHERE id = ?",
            (str(cache_file), thumbnail_id),
        )
        conn.execute("UPDATE asset_derivatives SET status = 'deferred_capacity' WHERE id = ?", (preview_id,))
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (thumbnail_id,))
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (preview_id,))

    periodic = scheduler.reconcile_desired_derivatives(
        asset_ids=[asset_id],
        kinds=["preview"],
        reason="periodic",
    )

    assert periodic.created_jobs == 0
    assert periodic.deferred_capacity == 1
    assert cache_file.is_file()
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (thumbnail_id,)).fetchone() == (
            "ready",
        )

    repaired = scheduler.reconcile_desired_derivatives(
        asset_ids=[asset_id],
        kinds=["preview"],
        reason="integrity",
    )

    assert repaired.created_jobs == 1
    assert not cache_file.exists()
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (thumbnail_id,)).fetchone() == (
            "evicted",
        )
        assert conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (preview_id,)).fetchone() == (
            "queued",
        )


def test_interrupted_eviction_with_original_file_restores_ready(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    """Restart-style coalescing recovers an eviction committed before unlink."""
    _, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(quota_bytes=400)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    variant = str(thumbnail["name"])
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", variant)
    cache_file = tmp_path / "interrupted-eviction.webp"
    cache_file.write_bytes(b"x" * 200)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            UPDATE asset_derivatives
            SET status = 'evicted', cache_path = ?, byte_size = 200,
                last_error = 'evicted: capacity reservation'
            WHERE id = ?
            """,
            (str(cache_file), derivative_id),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (derivative_id,))

    assert scheduler.schedule_derivative(asset_id, "thumbnail", variant) == derivative_id

    with sqlite3.connect(isolated_metadata_db) as conn:
        row = conn.execute(
            "SELECT status, cache_path, byte_size, last_error FROM asset_derivatives WHERE id = ?",
            (derivative_id,),
        ).fetchone()
        active_jobs = conn.execute(
            "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ? AND state IN ('queued', 'running')",
            (derivative_id,),
        ).fetchone()[0]
    assert row == ("ready", str(cache_file), 200, None)
    assert active_jobs == 0
    assert cache_file.exists()


# ---------------------------------------------------------------------------
# Workstream 4: concurrent start/stop linearizability
# ---------------------------------------------------------------------------


class TestStartStopLinearizability:
    def test_overlapping_stops_keep_start_blocked_until_both_finish(self, monkeypatch: pytest.MonkeyPatch):
        import backend.derivative_scheduler as scheduler_module

        scheduler = DerivativeScheduler(worker_count=1)
        release_worker = threading.Event()
        existing = threading.Thread(target=release_worker.wait, name="derivative-worker-1", daemon=True)
        existing.start()
        scheduler._threads = [existing]
        monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 1.0)

        first_stop = threading.Thread(target=scheduler.stop, daemon=True)
        first_stop.start()
        deadline = time.monotonic() + 1
        while scheduler._active_stop_calls != 1 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert scheduler._active_stop_calls == 1

        with scheduler._start_condition:
            scheduler._threads = []
        scheduler.stop()

        assert first_stop.is_alive()
        assert scheduler._stop_in_progress is True
        assert scheduler._active_stop_calls == 1
        scheduler.start()
        assert scheduler.alive_worker_count() == 0

        release_worker.set()
        first_stop.join(timeout=2)
        assert not first_stop.is_alive()
        assert scheduler._stop_in_progress is False
        assert scheduler._active_stop_calls == 0

    def test_stop_during_hung_cold_start_is_bounded_and_unclean(self, monkeypatch: pytest.MonkeyPatch):
        import backend.derivative_scheduler as scheduler_module

        scheduler = DerivativeScheduler(worker_count=2)
        blocker_event = threading.Event()
        recovery_done = threading.Event()
        original_ensure = scheduler_module._ensure_database
        monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 0.05)

        def blocked_ensure():
            recovery_done.set()
            blocker_event.wait()
            original_ensure()

        monkeypatch.setattr(scheduler_module, "_ensure_database", blocked_ensure)

        start_thread = threading.Thread(target=scheduler.start, daemon=True)
        start_thread.start()
        recovery_done.wait(timeout=2)

        started = time.monotonic()
        scheduler.stop()
        assert time.monotonic() - started < 0.25
        assert scheduler.last_shutdown_clean() is False
        assert scheduler.alive_worker_count() == 0

        blocker_event.set()
        start_thread.join(timeout=3)

        assert scheduler.alive_worker_count() == 0

    def test_fresh_start_after_cancelled_generation_works(self, monkeypatch: pytest.MonkeyPatch):
        import backend.derivative_scheduler as scheduler_module

        scheduler = DerivativeScheduler(worker_count=1)
        blocker_event = threading.Event()
        recovery_done = threading.Event()
        original_ensure = scheduler_module._ensure_database
        monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 0.05)

        def blocked_ensure():
            recovery_done.set()
            blocker_event.wait()
            original_ensure()

        monkeypatch.setattr(scheduler_module, "_ensure_database", blocked_ensure)

        start_thread = threading.Thread(target=scheduler.start, daemon=True)
        start_thread.start()
        recovery_done.wait(timeout=2)
        scheduler.stop()
        blocker_event.set()
        start_thread.join(timeout=3)

        assert scheduler.alive_worker_count() == 0

        monkeypatch.undo()
        scheduler.start()
        assert scheduler.alive_worker_count() == 1
        scheduler.stop()

    def test_start_invoked_during_stop_cannot_launch_new_slot(self, monkeypatch: pytest.MonkeyPatch):
        import backend.derivative_scheduler as scheduler_module

        scheduler = DerivativeScheduler(worker_count=1)
        release_worker = threading.Event()
        existing = threading.Thread(
            target=release_worker.wait,
            name="derivative-worker-1",
            daemon=True,
        )
        existing.start()
        scheduler._threads = [existing]
        monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 1.0)

        stop_thread = threading.Thread(target=scheduler.stop, daemon=True)
        stop_thread.start()
        deadline = time.monotonic() + 1
        while not scheduler._stop_in_progress and time.monotonic() < deadline:
            time.sleep(0.001)
        assert scheduler._stop_in_progress

        scheduler.start()
        assert scheduler._threads == [existing]

        release_worker.set()
        stop_thread.join(timeout=2)
        assert not stop_thread.is_alive()
        assert scheduler.last_shutdown_clean() is True
        assert scheduler.alive_worker_count() == 0

    def test_two_pre_stop_start_callers_are_both_cancelled(self, monkeypatch: pytest.MonkeyPatch):
        import backend.derivative_scheduler as scheduler_module

        scheduler = DerivativeScheduler(worker_count=1)
        recovery_entered = threading.Event()
        release_recovery = threading.Event()
        original_ensure = scheduler_module._ensure_database
        monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 0.05)

        def blocked_ensure():
            recovery_entered.set()
            release_recovery.wait()
            original_ensure()

        monkeypatch.setattr(scheduler_module, "_ensure_database", blocked_ensure)
        first = threading.Thread(target=scheduler.start, daemon=True)
        second = threading.Thread(target=scheduler.start, daemon=True)
        first.start()
        assert recovery_entered.wait(timeout=1)
        second.start()

        deadline = time.monotonic() + 1
        while second.ident is None and time.monotonic() < deadline:
            time.sleep(0.001)
        scheduler.stop()
        assert scheduler.last_shutdown_clean() is False

        release_recovery.set()
        first.join(timeout=2)
        second.join(timeout=2)
        assert not first.is_alive()
        assert not second.is_alive()
        assert scheduler.alive_worker_count() == 0


# ---------------------------------------------------------------------------
# repair_derivative_consistency coverage
# ---------------------------------------------------------------------------


def test_repair_consistency_empty_list_returns_zero(
    isolated_metadata_db: Path,
):
    scheduler = DerivativeScheduler()
    assert scheduler.repair_derivative_consistency([]).jobs_created == 0


def test_repair_consistency_skips_nonexistent_derivative(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    # Delete the derivative row so it won't be found
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("DELETE FROM asset_derivatives WHERE id = ?", (did,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0


def test_repair_consistency_skips_non_queued_derivative(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    # Mark the derivative as ready
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("UPDATE asset_derivatives SET status = 'ready' WHERE id = ?", (did,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0


def test_repair_consistency_skips_derivative_with_active_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    # Already has a queued job from schedule_derivative — skip
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0


def test_repair_consistency_terminalizes_inactive_asset(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (did,))
        conn.execute("UPDATE assets SET deleted_at = julianday('now') WHERE id = ?", (asset_id,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status, last_error FROM asset_derivatives WHERE id = ?", (did,)).fetchone()
        assert row["status"] == "skipped"
        assert "inactive" in row["last_error"]


def test_repair_consistency_terminalizes_missing_source(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    image.unlink()  # Remove source file after derivative is scheduled
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (did,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status, last_error FROM asset_derivatives WHERE id = ?", (did,)).fetchone()
        assert row["status"] == "skipped"
        assert "missing" in row["last_error"]


def test_repair_consistency_terminalizes_changed_source(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (did,))
        conn.execute("UPDATE asset_derivatives SET source_mtime_ns = 999999999999 WHERE id = ?", (did,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 0
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status, last_error FROM asset_derivatives WHERE id = ?", (did,)).fetchone()
        assert row["status"] == "skipped"
        assert "changed" in row["last_error"]


def test_repair_consistency_creates_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    did = scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.execute("DELETE FROM derivative_jobs WHERE derivative_id = ?", (did,))
    assert scheduler.repair_derivative_consistency([did]).jobs_created == 1
    with sqlite3.connect(str(isolated_metadata_db)) as conn:
        conn.row_factory = sqlite3.Row
        job = conn.execute(
            "SELECT state FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
            (did,),
        ).fetchone()
        assert job["state"] == "queued"
