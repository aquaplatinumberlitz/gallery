"""Tests for the maintenance runtime diagnostics API.

Purpose:
Validate GET /api/maintenance/runtime returns global runtime diagnostics and
metadata lifecycle counters without requiring any library to exist.

Guarantees:
Endpoint is read-only, returns 200 with global_runtime and metadata_lifecycle
keys. Global runtime includes catalog/metadata worker counts, queue depths,
watcher fields, and scheduled refresh field.

Run when:
Maintenance runtime response fields or global diagnostic counters change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import create_job, create_library, initialize_database, update_job_state


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path) -> None:
    initialize_database()


class TestGetMaintenanceRuntime:
    def test_returns_200_without_any_library(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        assert resp.status_code == 200

    def test_response_has_global_runtime(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        assert "global_runtime" in data

    def test_response_has_metadata_lifecycle(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        assert "metadata_lifecycle" in data

    def test_global_runtime_includes_expected_fields(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        gr = data["global_runtime"]
        assert "catalog_worker_count" in gr
        assert "catalog_alive_workers" in gr
        assert "catalog_active_jobs" in gr
        assert "catalog_queue_depth" in gr
        assert "watcher_enabled" in gr
        assert "watcher_healthy" in gr
        assert "watcher_issue" in gr
        assert "scheduled_reconciliation_enabled" in gr
        assert "metadata_worker_count" in gr
        assert "metadata_queue_depth" in gr
        assert "metadata_staged_queue_depth" in gr
        assert "derivative_configured_worker_count" in gr
        assert "derivative_worker_count" in gr
        assert "derivative_active_jobs" in gr
        assert "derivative_queue_depth" in gr
        assert "derivative_failed_jobs" in gr
        assert "derivative_skipped_jobs" in gr
        assert "derivative_stale_running_jobs" in gr
        assert "derivative_oldest_running_age_seconds" in gr

    def test_global_runtime_counts_executable_catalog_jobs_only(
        self,
        isolated_app: TestClient,
        isolated_gallery_root: Path,
    ) -> None:
        library = create_library([isolated_gallery_root], name="Runtime")
        parent = create_job("scan_all", progress_total=1)
        update_job_state(int(parent["id"]), "running", progress_total=1)
        create_job("scan", library_id=int(library["id"]))

        resp = isolated_app.get("/api/maintenance/runtime")

        gr = resp.json()["global_runtime"]
        assert gr["catalog_active_jobs"] == 0
        assert gr["catalog_queue_depth"] == 1
