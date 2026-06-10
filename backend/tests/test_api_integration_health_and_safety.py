"""Integration tests for health endpoint and path safety enforcement."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestHealth:
    def test_health_returns_200_and_status_ok(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "commit" in data
        assert "features" in data

    def test_health_response_is_json(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/health")
        assert resp.headers["content-type"].startswith("application/json")


class TestPathSafety:
    def test_scan_rejects_path_outside_gallery_root(
        self, isolated_app: TestClient, isolated_gallery_root: Path
    ):
        resp = isolated_app.get("/api/scan", params={"path": "/etc/passwd"})
        assert resp.status_code == 403

    def test_image_rejects_path_outside_gallery_root(
        self, isolated_app: TestClient
    ):
        resp = isolated_app.get("/api/image", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_thumbnail_rejects_path_outside_gallery_root(
        self, isolated_app: TestClient
    ):
        resp = isolated_app.get("/api/thumbnail", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_preview_rejects_path_outside_gallery_root(
        self, isolated_app: TestClient
    ):
        resp = isolated_app.get("/api/preview", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_metadata_rejects_path_outside_gallery_root(
        self, isolated_app: TestClient
    ):
        resp = isolated_app.get("/api/metadata", params={"path": "/etc/hosts"})
        assert resp.status_code in (400, 403)

    def test_scan_accepts_path_inside_gallery_root(
        self, isolated_app: TestClient, temp_gallery: Path
    ):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200

    def test_scan_missing_folder_returns_404(
        self, isolated_app: TestClient, temp_gallery: Path
    ):
        resp = isolated_app.get(
            "/api/scan", params={"path": str(temp_gallery / "nonexistent")}
        )
        assert resp.status_code == 404

    def test_scan_file_path_returns_400(
        self, isolated_app: TestClient, temp_gallery: Path
    ):
        file_path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/scan", params={"path": str(file_path)})
        assert resp.status_code == 400
