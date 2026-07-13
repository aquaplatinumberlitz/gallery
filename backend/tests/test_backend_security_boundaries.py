"""
Purpose:
Protect the trusted-proxy and catalog-only filesystem boundary introduced by
backend audit remediation phase 1.

Guarantees:
* configured proxy authentication rejects missing/invalid headers
* active catalog ownership and media type are required for file routes
* registered folder scopes reject unregistered and excluded paths
* nested file symlinks are not cataloged
* malformed NUL paths and bounded library settings fail deterministically

Run when:
* changing proxy authentication, path authorization, library validation, or discovery
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.libraries import _validate_settings
from backend.metadata_store import create_library, get_asset_state_for_path, index_directory_tree, index_file
from tests.conftest import create_test_png


def _index_image(path: Path) -> None:
    stat = path.stat()
    assert index_file(
        path,
        path.name,
        path.parent,
        "image",
        stat.st_mtime,
        stat.st_size,
        64,
        64,
        "image/png",
    )


def test_proxy_secret_is_required_when_configured(isolated_app, monkeypatch: pytest.MonkeyPatch):
    import backend.config as config

    secret = "s" * 32
    monkeypatch.setattr(config, "GALLERY_TRUSTED_PROXY_SECRET", secret)
    assert isolated_app.get("/api/health").status_code == 403
    assert isolated_app.get("/api/health", headers={"X-Gallery-Proxy-Secret": "wrong"}).status_code == 403
    assert isolated_app.get("/api/health", headers={"X-Gallery-Proxy-Secret": secret}).status_code == 200


def test_media_routes_require_active_catalog_asset(isolated_app, isolated_gallery_root: Path):
    root = isolated_gallery_root / "library"
    root.mkdir()
    registered = root / "registered.png"
    unregistered = isolated_gallery_root / "unregistered.png"
    create_test_png(registered)
    create_test_png(unregistered)
    create_library([root], name="Boundary")
    _index_image(registered)

    assert isolated_app.get("/api/image", params={"path": registered}).status_code == 200
    assert isolated_app.get("/api/video", params={"path": registered}).status_code == 404
    assert isolated_app.get("/api/image", params={"path": unregistered}).status_code == 404


def test_registered_folder_scope_rejects_excluded_and_unregistered_paths(
    isolated_app,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    excluded = root / "private"
    outside = isolated_gallery_root / "outside"
    excluded.mkdir(parents=True)
    outside.mkdir()
    create_library([root], name="Boundary", exclusion_patterns=["private/**"])

    assert isolated_app.get("/api/folders", params={"path": root}).status_code == 200
    assert isolated_app.get("/api/folders", params={"path": excluded}).status_code == 404
    assert isolated_app.get("/api/folders", params={"path": outside}).status_code == 404


def test_nested_file_symlink_is_not_cataloged(isolated_gallery_root: Path):
    root = isolated_gallery_root / "library"
    outside = isolated_gallery_root / "outside.png"
    root.mkdir()
    create_test_png(outside)
    link = root / "linked.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("File symlinks are unavailable on this platform")
    create_library([root], name="Boundary")

    index_directory_tree(root)

    assert get_asset_state_for_path(link) is None


def test_malformed_paths_and_library_input_bounds(isolated_app, isolated_gallery_root: Path):
    assert isolated_app.get("/api/image", params={"path": "bad\0path"}).status_code == 400

    too_many_paths = [str(isolated_gallery_root / f"path-{index}") for index in range(33)]
    validation = _validate_settings(too_many_paths, ["x" * 513])
    assert validation["import_paths"][32]["message"] == "At most 32 import paths are allowed"
    assert validation["exclusion_patterns"][0]["message"] == "Exclusion patterns cannot exceed 512 characters"


def test_production_configuration_requires_long_secret(monkeypatch: pytest.MonkeyPatch):
    import backend.config as config
    from backend.security import validate_trusted_proxy_configuration

    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "GALLERY_TRUSTED_PROXY_SECRET", "short")
    with pytest.raises(RuntimeError, match="at least 32"):
        validate_trusted_proxy_configuration()
