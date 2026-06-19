"""
Purpose:
Verify static frontend serving behaviour in development and production modes,
including the root endpoint, landing-page listing, and catch-all asset serving.

Guarantees:
* read_root returns the development API marker JSON when PRODUCTION=False and
  FileResponse for index.html when PRODUCTION=True.
* get_landing_pages returns a sorted list of public URL paths for nested .html
  files and returns [] when the landpage directory is missing.
* catch_all in development returns 404 in all cases.
* catch_all in production rejects api/*, openapi*, and docs* prefixes.
* catch_all in production serves existing static assets with a guessed media
  type and falls back to index.html for missing paths.

Run when:
* modifying static_files.py, catch_all routing, or frontend asset layout
* changing PRODUCTION detection or FRONTEND_DIST resolution
* touching landpage discovery or SPA fallback logic
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.static_files import router


@pytest.fixture
def static_app():
    from fastapi import FastAPI

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.include_router(router)
    return app


@pytest.fixture
def static_client(static_app):
    from fastapi.testclient import TestClient

    return TestClient(static_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# read_root
# ---------------------------------------------------------------------------


class TestReadRoot:
    def test_development_returns_api_marker_json(self, static_client: TestClient):
        resp = static_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Museum Art Gallery API"

    def test_production_returns_index_html(
        self, static_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        index_html = tmp_path / "index.html"
        index_html.write_text("<html><body>Hello</body></html>")

        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", tmp_path)

        resp = static_client.get("/")
        assert resp.status_code == 200
        assert "Hello" in resp.text


# ---------------------------------------------------------------------------
# get_landing_pages
# ---------------------------------------------------------------------------


class TestGetLandingPages:
    def test_missing_landpage_dir_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import backend.static_files as sf

        monkeypatch.setattr(sf, "__file__", str(tmp_path / "backend" / "static_files.py"))
        pages = sf.get_landing_pages()
        assert pages == []

    def test_nested_html_files_produce_public_url_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "backend").mkdir()
        public_dir = tmp_path / "frontend" / "public"
        landpage_dir = public_dir / "landpage"
        (landpage_dir / "sub").mkdir(parents=True)
        (landpage_dir / "index.html").write_text("landing")
        (landpage_dir / "sub" / "about.html").write_text("about")

        import backend.static_files as sf

        monkeypatch.setattr(sf, "__file__", str(tmp_path / "backend" / "static_files.py"))

        pages = sf.get_landing_pages()
        assert len(pages) >= 2
        assert any(p.endswith("index.html") for p in pages)
        assert any("about.html" in p for p in pages)

    def test_ignores_non_html_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "backend").mkdir()
        public_dir = tmp_path / "frontend" / "public"
        landpage_dir = public_dir / "landpage"
        landpage_dir.mkdir(parents=True)
        (landpage_dir / "index.html").write_text("landing")
        (landpage_dir / "style.css").write_text("css")
        (landpage_dir / "script.js").write_text("js")

        import backend.static_files as sf

        monkeypatch.setattr(sf, "__file__", str(tmp_path / "backend" / "static_files.py"))

        pages = sf.get_landing_pages()
        assert len(pages) == 1
        assert pages[0].endswith(".html")


# ---------------------------------------------------------------------------
# catch_all
# ---------------------------------------------------------------------------


class TestCatchAll:
    def test_development_returns_404(self, static_client: TestClient):
        resp = static_client.get("/anything")
        assert resp.status_code == 404

    def test_production_rejects_api_prefix(self, static_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        resp = static_client.get("/api/something")
        assert resp.status_code == 404

    def test_production_rejects_openapi_prefix(self, static_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        resp = static_client.get("/openapi.json")
        assert resp.status_code == 404

    def test_production_rejects_docs_prefix(self, static_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        resp = static_client.get("/docs")
        assert resp.status_code == 404

    def test_production_serves_existing_static_asset(
        self, static_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        asset_path = tmp_path / "assets" / "style.css"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("body { color: red; }")

        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", tmp_path)

        resp = static_client.get("/assets/style.css")
        assert resp.status_code == 200
        assert "color" in resp.text
        assert "text/css" in resp.headers.get("content-type", "")

    def test_production_falls_back_to_index_html(
        self, static_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        index_html = tmp_path / "index.html"
        index_html.write_text("<html>SPA fallback</html>")

        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", tmp_path)

        resp = static_client.get("/some-spa-route")
        assert resp.status_code == 200
        assert "SPA fallback" in resp.text

    def test_production_serves_root_fallback_for_empty_path(
        self, static_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        index_html = tmp_path / "index.html"
        index_html.write_text("<html>Root fallback</html>")

        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", tmp_path)

        resp = static_client.get("/")
        assert resp.status_code == 200
        assert "Root fallback" in resp.text
