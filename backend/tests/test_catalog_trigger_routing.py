"""
Purpose:
Locks Phase 4 catalog trigger routing through the durable catalog service.

Guarantees:
* library creation queues an initial scan job
* manual, watcher, startup, and scheduled triggers create/coalesce scan jobs
* run_once executes the catalog-owned scan pipeline for a queued job

Run when:
* changing catalog coordinator, worker startup, watcher routing, or scheduled reconciliation
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend import scan_worker as catalog_service
from backend.catalog_maintenance_gate import maintenance_gate
from backend.metadata_store import (
    CatalogJobConflict,
    CatalogMaintenanceBusy,
    create_library,
    get_job,
    list_active_jobs,
    register_library,
    update_job_state,
)
from tests.conftest import create_test_png


@pytest.fixture(autouse=True)
def stop_catalog_service_between_tests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.indexer.METADATA_INDEXER_ENABLED", False)
    monkeypatch.setattr("backend.config.METADATA_INDEXER_ENABLED", False)
    catalog_service.stop()
    yield
    catalog_service.stop()


def test_create_library_can_atomically_queue_initial_scan(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library = create_library([isolated_gallery_root], queue_initial_scan=True)

    job = get_job(library["initial_scan_job_id"])

    assert job is not None
    assert job["library_id"] == library["id"]
    assert job["type"] == "scan"
    assert job["trigger"] == "initial"
    assert job["priority"] == 100
    assert job["scope_path"] is None


def test_manual_scan_queues_durable_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])

    job, created = catalog_service.queue_scan(library_id, trigger="manual")

    assert created is True
    assert job["library_id"] == library_id
    assert job["trigger"] == "manual"
    assert job["priority"] == 100


def test_queue_scan_rejects_while_maintenance_gate_is_held(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])

    with maintenance_gate(), ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(catalog_service.queue_scan, library_id, trigger="manual")
        with pytest.raises(CatalogMaintenanceBusy):
            future.result()


def test_queue_rebuild_rejects_while_maintenance_gate_is_held(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])

    with maintenance_gate(), ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(catalog_service.queue_rebuild, library_id)
        with pytest.raises(CatalogMaintenanceBusy):
            future.result()


def test_initial_scan_wake_defers_while_maintenance_gate_is_held(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    library = create_library([isolated_gallery_root], queue_initial_scan=True)

    def fail_notify() -> None:
        raise AssertionError("initial scan worker wake should be deferred")

    monkeypatch.setattr(catalog_service, "notify_workers", fail_notify)
    with maintenance_gate(), ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(catalog_service.queue_initial_scan_job, int(library["initial_scan_job_id"]))
        assert future.result() is None


def test_startup_scans_defer_while_maintenance_gate_is_held(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    library_id = int(register_library(isolated_gallery_root)["id"])

    def fail_notify() -> None:
        raise AssertionError("startup scan worker wake should be deferred")

    monkeypatch.setattr(catalog_service, "notify_workers", fail_notify)
    with maintenance_gate(), ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(catalog_service.queue_startup_scans)
        assert future.result() == []

    assert list_active_jobs(library_id) == []


def test_watcher_scan_resolves_owning_library_and_scope(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    album = isolated_gallery_root / "album"
    album.mkdir()
    library_id = int(register_library(isolated_gallery_root)["id"])

    job = catalog_service.queue_watcher_scan(album)

    assert job is not None
    assert job["library_id"] == library_id
    assert job["trigger"] == "watcher"
    assert job["scope_path"] == str(album.resolve())


def test_watcher_scan_during_running_scan_queues_followup(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    album = isolated_gallery_root / "album"
    album.mkdir()
    library_id = int(register_library(isolated_gallery_root)["id"])
    running, created = catalog_service.queue_scan(library_id, trigger="manual")
    assert created is True
    running = update_job_state(running["id"], "running")
    assert running is not None

    job = catalog_service.queue_watcher_scan(album)

    assert job is not None
    assert job["id"] != running["id"]
    assert job["state"] == "queued"
    assert job["trigger"] == "watcher"
    assert job["scope_path"] == str(album.resolve())


def test_startup_trigger_queues_all_libraries(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    first_id = int(register_library(first)["id"])
    second_id = int(register_library(second)["id"])

    startup_jobs = catalog_service.queue_startup_scans()

    assert {job["library_id"] for job in startup_jobs} == {first_id, second_id}
    assert {job["trigger"] for job in startup_jobs} == {"startup"}


def test_scheduled_trigger_queues_all_libraries(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    first_id = int(register_library(first)["id"])
    second_id = int(register_library(second)["id"])

    scheduled_jobs = catalog_service.queue_scheduled_scans()

    assert {job["library_id"] for job in scheduled_jobs} == {first_id, second_id}
    assert {job["trigger"] for job in scheduled_jobs} == {"scheduled"}


def test_run_once_executes_queued_scan_through_catalog_pipeline(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    create_test_png(isolated_gallery_root / "image.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    job, created = catalog_service.queue_scan(library_id, trigger="manual")

    assert created is True
    assert catalog_service.run_once() is True

    finished = get_job(job["id"])
    assert finished is not None
    assert finished["state"] == "succeeded"
    assert finished["counters"]["indexed"] >= 1
    assert list_active_jobs(library_id) == []


def test_queue_scan_rejects_unknown_trigger(isolated_metadata_db: Path, isolated_gallery_root: Path):
    library_id = int(register_library(isolated_gallery_root)["id"])

    with pytest.raises(ValueError, match="Unsupported scan trigger"):
        catalog_service.queue_scan(library_id, trigger="repair")


def test_watcher_scan_returns_none_for_unregistered_scope(isolated_metadata_db: Path, isolated_gallery_root: Path):
    outside = isolated_gallery_root / "outside"
    outside.mkdir()

    assert catalog_service.queue_watcher_scan(outside) is None


def test_run_once_returns_false_when_no_catalog_job(isolated_metadata_db: Path):
    assert catalog_service.run_once() is False


def test_run_once_executes_rebuild_job_through_catalog_pipeline(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    create_test_png(isolated_gallery_root / "image.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    scan, _ = catalog_service.queue_scan(library_id, trigger="manual")
    assert catalog_service.run_once() is True
    finished_scan = get_job(scan["id"])
    assert finished_scan["state"] == "succeeded"

    create_test_png(isolated_gallery_root / "added.png")
    rebuild, _ = catalog_service.queue_rebuild(library_id)
    assert catalog_service.run_once() is True

    finished = get_job(rebuild["id"])
    assert finished is not None
    assert finished["state"] == "succeeded"
    assert finished["counters"]["discovered"] >= 2
    assert finished["counters"]["assets"] >= 2


def test_rebuild_writes_to_staging_then_activates(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    import sqlite3

    create_test_png(isolated_gallery_root / "image.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    rebuild, _ = catalog_service.queue_rebuild(library_id)

    assert catalog_service.run_once() is True

    with sqlite3.connect(isolated_metadata_db) as conn:
        staging = conn.execute("SELECT count(*) FROM catalog_rebuild_entries").fetchone()[0]
        assert staging == 0
    finished = get_job(rebuild["id"])
    assert finished["state"] == "succeeded"


def test_rebuild_marks_missing_assets_offline(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    import sqlite3

    image = isolated_gallery_root / "image.png"
    create_test_png(image)
    library_id = int(register_library(isolated_gallery_root)["id"])
    catalog_service.queue_scan(library_id, trigger="manual")
    assert catalog_service.run_once() is True

    image.unlink()
    rebuild, _ = catalog_service.queue_rebuild(library_id)
    assert catalog_service.run_once() is True

    finished = get_job(rebuild["id"])
    assert finished["state"] == "succeeded"
    assert finished["counters"]["offline"] >= 1
    with sqlite3.connect(isolated_metadata_db) as conn:
        offline = conn.execute(
            "SELECT offline FROM assets WHERE library_id = ? AND path = ?",
            (library_id, str(image.resolve())),
        ).fetchone()[0]
    assert offline == 1


def test_rebuild_preserves_canonical_on_failure(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    import sqlite3

    create_test_png(isolated_gallery_root / "image.png")
    library_id = int(register_library(isolated_gallery_root)["id"])
    catalog_service.queue_scan(library_id, trigger="manual")
    assert catalog_service.run_once() is True

    rebuild, _ = catalog_service.queue_rebuild(library_id)
    import backend.scan_worker as svc

    original = svc.enumerate_to_rebuild_staging
    svc.enumerate_to_rebuild_staging = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert catalog_service.run_once() is True
    finally:
        svc.enumerate_to_rebuild_staging = original

    finished = get_job(rebuild["id"])
    assert finished["state"] == "failed"
    with sqlite3.connect(isolated_metadata_db) as conn:
        staging = conn.execute("SELECT count(*) FROM catalog_rebuild_entries").fetchone()[0]
        assert staging == 0
        assets = conn.execute(
            "SELECT count(*) FROM assets WHERE library_id = ? AND offline = 0",
            (library_id,),
        ).fetchone()[0]
    assert assets >= 1


def test_manual_scan_while_rebuild_queued_returns_409(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])
    rebuild, _ = catalog_service.queue_rebuild(library_id)
    assert rebuild["state"] == "queued"

    with pytest.raises(CatalogJobConflict):
        catalog_service.queue_scan(library_id, trigger="manual")


def test_manual_rebuild_cancels_queued_scans(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])
    scan, scan_created = catalog_service.queue_scan(library_id, trigger="manual")
    assert scan_created is True
    assert scan["state"] == "queued"

    rebuild, rebuild_created = catalog_service.queue_rebuild(library_id)
    assert rebuild_created is True

    cancelled_scan = get_job(scan["id"])
    assert cancelled_scan["state"] == "cancelled"
    assert rebuild["state"] == "queued"


def test_manual_rebuild_while_scan_running_returns_409(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = int(register_library(isolated_gallery_root)["id"])
    scan, _ = catalog_service.queue_scan(library_id, trigger="manual")
    scan = update_job_state(scan["id"], "running")
    assert scan["state"] == "running"

    with pytest.raises(CatalogJobConflict):
        catalog_service.queue_rebuild(library_id)


def test_run_once_marks_offline_scan_path_failed(isolated_metadata_db: Path, isolated_gallery_root: Path):
    missing = isolated_gallery_root / "missing"
    library_id = int(register_library(isolated_gallery_root)["id"])
    job, created = catalog_service.queue_scan(library_id, trigger="manual", scope_path=missing)

    assert created is True
    assert catalog_service.run_once() is True

    finished = get_job(job["id"])
    assert finished is not None
    assert finished["state"] == "failed"
    assert finished["error"] == "All update paths are offline"


def test_runtime_status_and_worker_lifecycle(isolated_metadata_db: Path):
    catalog_service.start()
    try:
        status = catalog_service.runtime_status()
        assert status["worker_count"] >= 1
        assert status["alive_workers"] >= 1
    finally:
        catalog_service.stop()

    assert catalog_service.runtime_status()["alive_workers"] == 0


def test_scan_all_zero_libraries_parent_succeeds(isolated_metadata_db: Path):
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as client:
        response = client.post("/api/libraries/scan-all")

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "succeeded"
    assert body["child_job_ids"] == []
    assert body["count"] == 0
    job = get_job(int(body["job_id"]))
    assert job is not None
    assert job["state"] == "succeeded"
    assert job["message"] == "No libraries to update"
