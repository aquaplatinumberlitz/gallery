"""Integration tests for /api/index/status endpoint."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import get_metadata_index_status, index_directory_tree
from .conftest import create_test_image


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

    def test_index_status_is_json_serializable_with_previous_job_error(
        self,
        isolated_app: TestClient,
        temp_gallery: Path,
    ):
        from backend.metadata_store import mark_metadata_jobs_failed, queue_metadata_index_paths

        image_path = temp_gallery / "album_a" / "binary-error.png"
        create_test_image(image_path)
        queued = queue_metadata_index_paths([image_path], temp_gallery / "album_a")
        assert len(queued.enqueued) == 1
        mark_metadata_jobs_failed(
            [(queued.enqueued[0], "Object of type bytes is not JSON serializable")]
        )

        resp = isolated_app.get("/api/index/status", params={"path": str(temp_gallery / "album_a")})

        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["last_error"]["path"] == str(image_path.resolve())
        assert data["last_error"]["message"] == "Object of type bytes is not JSON serializable"

    def test_rebuild_requires_confirmation(self, isolated_app: TestClient, temp_gallery: Path):
        resp = isolated_app.post(
            "/api/index/rebuild",
            params={"path": str(temp_gallery / "album_a")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "confirmation_required"

    def test_rebuild_clears_scoped_index_and_queues_metadata(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        sibling = temp_gallery / "album_b"

        # Pre-populate file_index, image_metadata and metadata_index_jobs for album_a.
        image_paths: list[Path] = []
        indexed_before = index_directory_tree(album, include_metadata=False, collected_image_paths=image_paths)
        assert indexed_before > 0
        assert len(image_paths) >= 3

        from backend.metadata_store import index_image, queue_metadata_index_paths

        queue_metadata_index_paths(image_paths, album)
        for img_path in image_paths:
            index_image(img_path)

        # Pre-populate sibling folder so we can verify rebuild stays scoped.
        sibling_images: list[Path] = []
        index_directory_tree(sibling, include_metadata=False, collected_image_paths=sibling_images)
        queue_metadata_index_paths(sibling_images, sibling)

        before_album = get_metadata_index_status(album)
        assert before_album["total"] > 0
        before_sibling = get_metadata_index_status(sibling)
        assert before_sibling["total"] > 0

        resp = isolated_app.post(
            "/api/index/rebuild",
            params={"path": str(album), "confirm": "true"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["path"] == str(album.resolve())
        assert data["rebuild_started"] is True
        assert data["cleared"]["file_index"] > 0
        assert data["cleared"]["image_metadata"] > 0
        assert data["cleared"]["metadata_index_jobs"] > 0

        # Sibling folder must remain untouched.
        after_sibling = get_metadata_index_status(sibling)
        assert after_sibling["total"] == before_sibling["total"]

        status = isolated_app.get("/api/index/status", params={"path": str(album)}).json()
        assert status["total"] >= 3
        assert status["queued"] >= 3
