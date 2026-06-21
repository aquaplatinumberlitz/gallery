"""Phase 4 DB-required scan cutover coverage."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.metadata_store import register_library, update_library_state
from tests.conftest import create_test_png


def test_default_mode_allows_unregistered_direct_scan(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    create_test_png(isolated_gallery_root / "direct.png")
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", False)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 200
    assert response.json()["index_source"] == "direct_scan"


def test_required_mode_rejects_unregistered_path(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "library_not_registered",
        "message": "Register this root before browsing it",
    }


def test_required_mode_returns_404_for_missing_path(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    register_library(isolated_gallery_root)
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root / "missing")})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"


def test_required_mode_returns_400_for_file_path(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    image = isolated_gallery_root / "file.png"
    create_test_png(image)
    register_library(isolated_gallery_root)
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(image)})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "not_directory"


def test_required_mode_returns_409_for_offline_library(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    library = register_library(isolated_gallery_root)
    update_library_state(int(library["id"]), "offline", last_error="Root path is offline")
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "library_offline",
        "message": "Root path is offline",
    }


def test_required_mode_returns_last_error_for_error_library(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    library = register_library(isolated_gallery_root)
    update_library_state(int(library["id"]), "error", last_error="scan failed")
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "library_error",
        "message": "scan failed",
    }


def test_required_mode_never_falls_back_to_filesystem(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    register_library(isolated_gallery_root)
    create_test_png(isolated_gallery_root / "not-yet-indexed.png")
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    monkeypatch.setattr(
        "backend.scan.scan_directory",
        lambda *_: (_ for _ in ()).throw(AssertionError("filesystem fallback used")),
    )
    monkeypatch.setattr(
        "backend.scan.get_warm_folder_listing",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy catalog used")),
    )

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 200
    assert response.json() == {
        "folders": [],
        "media": [],
        "next_media_cursor": None,
        "total_images": 0,
        "total_videos": 0,
        "total_assets": 0,
        "index_source": "warm_db",
        "library_state": "discovering",
        "indexed": False,
        "message": "Library is still being scanned",
    }
