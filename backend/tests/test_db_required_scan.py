"""Phase 4 DB-required scan cutover coverage."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.metadata_store import list_libraries, unregister_library
from tests.conftest import create_test_png


def test_default_mode_allows_unregistered_direct_scan(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    library_id = list_libraries()[0]["id"]
    assert unregister_library(library_id)
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
    library_id = list_libraries()[0]["id"]
    assert unregister_library(library_id)
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)

    with TestClient(app) as client:
        response = client.get("/api/scan", params={"path": str(isolated_gallery_root)})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "library_not_registered",
        "message": "Register this root before browsing it",
    }


def test_required_mode_never_falls_back_to_filesystem(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    list_libraries()
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
        "images": [],
        "next_cursor": None,
        "total_images": 0,
        "index_source": "warm_db",
    }
