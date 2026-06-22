"""
Purpose:
Verifies health endpoint shape and path safety enforcement across public APIs.

Guarantees:
* /api/health remains JSON and includes expected runtime fields
* image, thumbnail, preview, and metadata endpoints reject unsafe paths

Run when:
* changing health response fields, path safety checks, or gallery root resolution
* touching public endpoint validation behavior
"""

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
    def test_image_rejects_path_outside_gallery_root(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/image", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_thumbnail_rejects_path_outside_gallery_root(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/thumbnail", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_preview_rejects_path_outside_gallery_root(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/preview", params={"path": "/etc/hosts"})
        assert resp.status_code in (403, 404)

    def test_metadata_rejects_path_outside_gallery_root(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/metadata", params={"path": "/etc/hosts"})
        assert resp.status_code in (400, 403)
