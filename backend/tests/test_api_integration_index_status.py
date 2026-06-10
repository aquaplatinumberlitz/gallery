"""Integration tests for /api/index/status endpoint."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestIndexStatus:
    def test_index_status_returns_200(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/index/status")
        assert resp.status_code == 200

    def test_index_status_has_expected_shape(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/index/status")
        assert resp.status_code == 200
        data = resp.json()
        # Core keys
        for key in ("path", "total", "queued", "running", "done", "failed"):
            assert key in data
        # Runtime keys
        for key in ("enabled", "active_jobs", "runtime_queue_depth"):
            assert key in data

    def test_index_status_when_indexer_disabled(self, isolated_app: TestClient):
        """Index status should work even when indexer is disabled."""
        resp = isolated_app.get("/api/index/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    def test_index_status_with_path(self, isolated_app: TestClient, temp_gallery: Path):
        resp = isolated_app.get(
            "/api/index/status",
            params={"path": str(temp_gallery / "album_a")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "total" in data

    def test_index_status_with_enabled_indexer(self, isolated_app: TestClient, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch):
        """Index status should work when indexer is enabled with an empty temp gallery."""
        monkeypatch.setattr("backend.indexer.METADATA_INDEXER_ENABLED", True)
        monkeypatch.setattr("backend.config.METADATA_INDEXER_ENABLED", True)

        resp = isolated_app.get("/api/index/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True

    def test_index_status_has_runtime_fields(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/index/status")
        assert resp.status_code == 200
        data = resp.json()
        runtime_keys = {
            "worker_count", "active_jobs", "runtime_queue_depth",
            "coalesced_duplicates", "batch_size",
        }
        for key in runtime_keys:
            assert key in data

    def test_index_status_does_not_crash_with_empty_state(self, isolated_app: TestClient, temp_gallery: Path):
        """After fresh start with no index, the endpoint should not 500."""
        resp = isolated_app.get("/api/index/status", params={"path": str(temp_gallery / "album_a")})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
