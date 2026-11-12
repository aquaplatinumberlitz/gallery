"""
Purpose:
Verify static frontend serving behaviour in development and production modes,
including the root endpoint, landing-page listing, and catch-all asset serving.

Guarantees:
* read_root returns the development API marker JSON when neither PRODUCTION nor LOCAL_MODE is set, and
  FileResponse for index.html when PRODUCTION=True or GALLERY_MODE=local (LOCAL_MODE).
* the real frontend/public/landpage folder (copied verbatim into dist) ships only real themes: no
  developer sample page and no archive or other non-page file, and the API lists exactly its
  `<theme>/index.html` pages.
* get_landing_pages returns a sorted list of public URL paths for nested .html
  files and returns [] when the landpage directory is missing.
* catch_all in development returns 404 in all cases.
* catch_all in production rejects api/*, openapi*, and docs* prefixes.
* catch_all in production serves existing static assets with a guessed media
  type and falls back to index.html for missing paths.
* local mode serves the built SPA like production: index at /, assets, SPA fallback, and 404 for api/*.

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

    def test_shipped_landpage_folder_has_only_real_themes(self):
        """`frontend/public` is copied verbatim into `dist`, so whatever is here is served publicly."""
        import backend.static_files as sf

        landpage_dir = Path(sf.__file__).resolve().parent.parent / "frontend" / "public" / "landpage"
        assert landpage_dir.is_dir()

        entries = sorted(p.name for p in landpage_dir.iterdir())
        assert not [n for n in entries if n.lower().endswith(".zip")], entries
        assert "sample_test" not in entries
        # Every entry is a theme folder with its own index page; stray files would ship in dist.
        for entry in landpage_dir.iterdir():
            assert entry.is_dir(), f"stray file in landpage/: {entry.name}"
            assert (entry / "index.html").is_file(), f"theme without index.html: {entry.name}"
        assert not [p for p in landpage_dir.rglob("*") if p.suffix.lower() in {".zip", ".rar", ".7z", ".psd"}]

        pages = sf.get_landing_pages()
        assert sorted(pages) == sorted(f"/landpage/{n}/index.html" for n in entries)
        assert not [p for p in pages if "sample" in p.lower()]


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

    def test_production_does_not_serve_files_outside_frontend_dist(
        self, static_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        frontend = tmp_path / "dist"
        frontend.mkdir()
        (frontend / "index.html").write_text("safe shell")
        (tmp_path / "secret.txt").write_text("outside secret")

        monkeypatch.setattr("backend.static_files.PRODUCTION", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", frontend)

        resp = static_client.get("/%2e%2e%2fsecret.txt")
        assert resp.status_code == 200
        assert resp.text == "safe shell"

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


# ---------------------------------------------------------------------------
# Local mode (GALLERY_MODE=local): the backend serves the built SPA itself
# ---------------------------------------------------------------------------


class TestLocalMode:
    @pytest.fixture
    def local_dist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        (tmp_path / "assets").mkdir()
        (tmp_path / "index.html").write_text("<html><body>Local SPA</body></html>")
        (tmp_path / "assets" / "app.js").write_text("console.log('x')")
        monkeypatch.setattr("backend.static_files.LOCAL_MODE", True)
        monkeypatch.setattr("backend.static_files.FRONTEND_DIST", tmp_path)
        return tmp_path

    def test_root_serves_index_html(self, static_client: TestClient, local_dist: Path):
        resp = static_client.get("/")
        assert resp.status_code == 200
        assert "Local SPA" in resp.text

    def test_serves_assets_and_spa_fallback(self, static_client: TestClient, local_dist: Path):
        asset = static_client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "console.log" in asset.text
        fallback = static_client.get("/admin/libraries")
        assert fallback.status_code == 200
        assert "Local SPA" in fallback.text

    def test_api_prefixes_are_not_served_as_spa(self, static_client: TestClient, local_dist: Path):
        assert static_client.get("/api/unknown").status_code == 404
        assert static_client.get("/openapi.json").status_code == 404

    def test_without_local_mode_catch_all_stays_disabled(
        self, static_client: TestClient, local_dist: Path, monkeypatch
    ):
        monkeypatch.setattr("backend.static_files.LOCAL_MODE", False)
        assert static_client.get("/admin/libraries").status_code == 404
