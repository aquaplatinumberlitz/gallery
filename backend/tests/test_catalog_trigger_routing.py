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

from pathlib import Path

import pytest

from backend.catalog import service as catalog_service
from backend.metadata_store import (
    create_job,
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


def test_run_once_fails_unsupported_rebuild_job(isolated_metadata_db: Path, isolated_gallery_root: Path):
    library_id = int(register_library(isolated_gallery_root)["id"])
    job = create_job("rebuild", library_id=library_id, trigger="manual", priority=100)

    assert catalog_service.run_once() is True

    finished = get_job(job["id"])
    assert finished is not None
    assert finished["state"] == "failed"
    assert finished["error"] == "Unsupported"


def test_run_once_marks_offline_scan_path_failed(isolated_metadata_db: Path, isolated_gallery_root: Path):
    missing = isolated_gallery_root / "missing"
    library_id = int(register_library(isolated_gallery_root)["id"])
    job, created = catalog_service.queue_scan(library_id, trigger="manual", scope_path=missing)

    assert created is True
    assert catalog_service.run_once() is True

    finished = get_job(job["id"])
    assert finished is not None
    assert finished["state"] == "failed"
    assert finished["error"] == "All scan paths are offline"


def test_runtime_status_and_worker_lifecycle(isolated_metadata_db: Path):
    catalog_service.start()
    try:
        status = catalog_service.runtime_status()
        assert status["worker_count"] >= 1
        assert status["alive_workers"] >= 1
    finally:
        catalog_service.stop()

    assert catalog_service.runtime_status()["alive_workers"] == 0
