"""Tests for the maintenance runtime diagnostics API.

Purpose:
Validate GET /api/maintenance/runtime returns global runtime diagnostics and
metadata lifecycle counters without requiring any library to exist.

Guarantees:
Endpoint is read-only, returns 200 with global_runtime and metadata_lifecycle
keys. Global runtime includes catalog/metadata worker counts, queue depths,
watcher fields, and scheduled refresh field.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import initialize_database


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
        assert "catalog_active_jobs" in gr
        assert "catalog_queue_depth" in gr
        assert "watcher_enabled" in gr
        assert "watcher_healthy" in gr
        assert "watcher_issue" in gr
        assert "scheduled_reconciliation_enabled" in gr
        assert "metadata_worker_count" in gr
        assert "metadata_queue_depth" in gr
        assert "metadata_staged_queue_depth" in gr
