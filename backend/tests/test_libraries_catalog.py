"""Library/asset migration, dual-write, listing, and API coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.metadata_store import (
    get_asset_folder_listing,
    get_library_progress,
    index_file,
    initialize_database,
    list_libraries,
    upsert_image_dimensions,
)
from tests.conftest import create_test_png


def test_version_four_migrates_file_index_into_default_library(isolated_metadata_db: Path, tmp_path: Path):
    initialize_database()
    image = tmp_path / "legacy.png"
    create_test_png(image, size=(40, 30))
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("DELETE FROM assets")
        conn.execute(
            """
            INSERT INTO file_index (path, name, parent_path, type, mtime, size, width, height, indexed_at)
            VALUES (?, ?, ?, 'photo', 12.5, 99, 40, 30, 13.0)
            """,
            (str(image.resolve()), image.name, str(image.parent.resolve())),
        )
        conn.execute("PRAGMA user_version = 3")

    import backend.metadata_store as metadata_store

    metadata_store._DB_INITIALIZED = False
    initialize_database()

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets WHERE path = ?", (str(image.resolve()),)).fetchone()
        assert row is not None
        assert (row["width"], row["height"], row["type"], row["mtime_ns"]) == (40, 30, "image", 12.5)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5


def test_scan_and_metadata_dual_write_assets(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image = isolated_gallery_root / "asset.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()

    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, None, None)
    assert upsert_image_dimensions(image, 80, 60)

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert listing["index_source"] == "warm_db"
    assert listing["images"][0].path == str(image.resolve())
    assert (listing["images"][0].width, listing["images"][0].height) == (80, 60)
    assert listing["images"][0].asset_id is not None
    assert listing["images"][0].metadata_state == "done"
    assert listing["images"][0].derivative_ready == {"thumbnail": False, "preview": False}

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, status, max_long_edge
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', 512)
            """,
            (listing["images"][0].asset_id, stat.st_mtime_ns, stat.st_size),
        )

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert listing["images"][0].derivative_ready == {"thumbnail": True, "preview": False}

    library_id = list_libraries()[0]["id"]
    progress = get_library_progress(library_id)
    assert progress["indexed_assets"] == 1
    assert progress["estimated_assets"] == 1


def test_library_api_lists_progress_and_requires_delete_confirmation(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    with TestClient(app) as client:
        libraries = client.get("/api/libraries")
        assert libraries.status_code == 200
        default_library = libraries.json()[0]
        assert default_library["root_path"] == str(isolated_gallery_root.resolve())

        progress = client.get(f"/api/libraries/{default_library['id']}/progress")
        assert progress.status_code == 200
        assert set(progress.json()) == {
            "indexed_assets",
            "estimated_assets",
            "discovery_complete",
            "library_state",
        }

        rejected = client.delete(f"/api/libraries/{default_library['id']}")
        assert rejected.status_code == 400
        deleted = client.delete(f"/api/libraries/{default_library['id']}?confirm=true")
        assert deleted.status_code == 200
        assert deleted.json()["source_files_deleted"] is False
