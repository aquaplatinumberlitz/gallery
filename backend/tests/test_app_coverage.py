"""
Purpose:
Exercise uncovered app.py branches for the ENABLE_METRICS instrumentator
wiring and the ENABLE_PROFILER pyinstrument middleware so backend line coverage
stays above the release threshold.

Guarantees:
* Reloading backend.app with ENABLE_METRICS=True registers the /metrics route
  via prometheus_fastapi_instrumentator.
* Reloading backend.app with ENABLE_PROFILER=True registers the pyinstrument
  profile_middleware, which writes HTML reports for profiled endpoints and
  passes through non-profiled endpoints without writing.
* The original app state is restored after each test so subsequent tests see a
  clean FastAPI instance.

Run when:
* changing backend/app.py metrics wiring or profiler middleware
* toggling ENABLE_METRICS / ENABLE_PROFILER config flags
* updating PROFILE_ENDPOINTS or PROFILE_DIR handling
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.errors import APIError, ErrorType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_app_with(**config_overrides) -> object:
    """Reload backend.app with temporary config overrides and return the module."""
    import backend.config as config_module
    import backend.app as app_module

    saved: dict[str, object] = {}
    for key, value in config_overrides.items():
        saved[key] = getattr(config_module, key)
        setattr(config_module, key, value)

    importlib.reload(app_module)
    return app_module, saved


def _restore_app(saved: dict[str, object]) -> None:
    """Restore config values and reload backend.app to the clean state."""
    import backend.config as config_module
    import backend.app as app_module

    for key, value in saved.items():
        setattr(config_module, key, value)
    importlib.reload(app_module)


# ---------------------------------------------------------------------------
# ENABLE_METRICS (lines 49-56)
# ---------------------------------------------------------------------------


def test_metrics_instrumentator_registers_metrics_endpoint():
    import backend.config as config_module

    original = config_module.ENABLE_METRICS
    config_module.ENABLE_METRICS = True
    try:
        import backend.app as app_module

        importlib.reload(app_module)
        paths = {getattr(r, "path", None) for r in app_module.app.routes}
        assert "/metrics" in paths
    finally:
        config_module.ENABLE_METRICS = original
        importlib.reload(app_module)


def test_metrics_disabled_does_not_register_metrics_endpoint():
    import backend.config as config_module

    original = config_module.ENABLE_METRICS
    config_module.ENABLE_METRICS = False
    try:
        import backend.app as app_module

        importlib.reload(app_module)
        paths = {getattr(r, "path", None) for r in app_module.app.routes}
        assert "/metrics" not in paths
    finally:
        config_module.ENABLE_METRICS = original
        importlib.reload(app_module)


# ---------------------------------------------------------------------------
# ENABLE_PROFILER middleware (lines 92-109)
# ---------------------------------------------------------------------------


def test_profiler_middleware_writes_report_for_profiled_endpoint(
    tmp_path: Path,
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
) -> None:
    import backend.config as config_module

    original_profiler = config_module.ENABLE_PROFILER
    original_dir = config_module.PROFILE_DIR
    profile_dir = tmp_path / "profiles"
    config_module.ENABLE_PROFILER = True
    config_module.PROFILE_DIR = profile_dir
    try:
        import backend.app as app_module

        importlib.reload(app_module)
        client = TestClient(app_module.app, raise_server_exceptions=False)

        resp = client.get("/api/scan", params={"path": str(isolated_gallery_root)})
        assert resp.status_code == 200

        html_files = list(profile_dir.glob("*.html"))
        assert len(html_files) == 1, f"Expected 1 profiler HTML report, got {html_files}"
        content = html_files[0].read_text(encoding="utf-8")
        assert "pyinstrument" in content.lower() or "<html" in content.lower()
    finally:
        config_module.ENABLE_PROFILER = original_profiler
        config_module.PROFILE_DIR = original_dir
        importlib.reload(app_module)


def test_profiler_middleware_skips_non_profiled_endpoint(
    tmp_path: Path,
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
) -> None:
    import backend.config as config_module

    original_profiler = config_module.ENABLE_PROFILER
    original_dir = config_module.PROFILE_DIR
    profile_dir = tmp_path / "profiles"
    config_module.ENABLE_PROFILER = True
    config_module.PROFILE_DIR = profile_dir
    try:
        import backend.app as app_module

        importlib.reload(app_module)
        client = TestClient(app_module.app, raise_server_exceptions=False)

        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        html_files = list(profile_dir.glob("*.html"))
        assert len(html_files) == 0, f"Non-profiled endpoint should not write report, got {html_files}"
    finally:
        config_module.ENABLE_PROFILER = original_profiler
        config_module.PROFILE_DIR = original_dir
        importlib.reload(app_module)


def test_profiler_disabled_does_not_register_middleware(
    tmp_path: Path,
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
) -> None:
    import backend.config as config_module

    original_profiler = config_module.ENABLE_PROFILER
    profile_dir = tmp_path / "profiles"
    config_module.ENABLE_PROFILER = False
    try:
        import backend.app as app_module

        importlib.reload(app_module)
        client = TestClient(app_module.app, raise_server_exceptions=False)

        resp = client.get("/api/health")
        assert resp.status_code == 200

        assert not profile_dir.exists() or len(list(profile_dir.glob("*.html"))) == 0
    finally:
        config_module.ENABLE_PROFILER = original_profiler
        importlib.reload(app_module)


# ---------------------------------------------------------------------------
# _get_cors_origins combined branch (FRONTEND_ORIGIN + FRONTEND_PORT both set)
# ---------------------------------------------------------------------------


def test_get_cors_origins_both_origin_and_port_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://gallery.example.com/")
    monkeypatch.setenv("FRONTEND_PORT", "3000")

    from backend.app import _get_cors_origins

    origins = _get_cors_origins()
    assert "https://gallery.example.com" in origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
