"""Library/asset migration, dual-write, listing, and API coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.indexer import rebuild_index_scope
from backend.metadata_store import (
    get_asset_folder_listing,
    get_first_library_root,
    get_library,
    get_library_for_path,
    get_library_progress,
    index_file,
    initialize_database,
    list_libraries,
    register_library,
    repair_library_assets,
    update_library,
    update_library_state,
    upsert_image_dimensions,
)
from tests.conftest import create_test_png


def _register_library(root: Path) -> int:
    return int(register_library(root)["id"])


def test_no_implicit_library_on_fresh_startup(isolated_metadata_db: Path):
    initialize_database()
    assert list_libraries() == []


def test_version_four_migrates_file_index_into_default_library(isolated_metadata_db: Path, tmp_path: Path):
    initialize_database()
    image = tmp_path / "legacy.png"
    create_test_png(image, size=(40, 30))
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("DELETE FROM assets")
        conn.execute("ALTER TABLE assets DROP COLUMN mime_type")
        conn.execute("ALTER TABLE assets DROP COLUMN duration_ms")
        conn.execute("ALTER TABLE assets DROP COLUMN codec")
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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8


def test_version_six_backfills_import_paths_and_converts_library_timestamps(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    initialize_database()
    root = str(isolated_gallery_root.resolve())
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("ALTER TABLE assets DROP COLUMN mime_type")
        conn.execute("ALTER TABLE assets DROP COLUMN duration_ms")
        conn.execute("ALTER TABLE assets DROP COLUMN codec")
        conn.execute("DELETE FROM library_import_paths")
        conn.execute(
            """
            INSERT INTO libraries (
              root_path, name, state, created_at, updated_at, last_scan_at
            ) VALUES (?, 'Legacy', 'ready', 2460000.5, 2460001.5, 2460002.5)
            """,
            (root,),
        )
        conn.execute("PRAGMA user_version = 5")

    import backend.metadata_store as metadata_store

    metadata_store._DB_INITIALIZED = False
    initialize_database()
    library = list_libraries()[0]
    assert library["root_path"] == root
    assert library["import_paths"][0]["path"] == root
    assert library["import_paths"][0]["position"] == 0
    assert 1_000_000_000 < library["created_at"] < 2_000_000_000
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        assert conn.execute("SELECT count(*) FROM library_import_paths").fetchone()[0] == 1


def test_scan_and_metadata_dual_write_assets(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _register_library(isolated_gallery_root)
    image = isolated_gallery_root / "asset.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()

    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, None, None)
    assert upsert_image_dimensions(image, 80, 60)

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert listing["index_source"] == "warm_db"
    assert listing["media"][0].path == str(image.resolve())
    assert (listing["media"][0].width, listing["media"][0].height) == (80, 60)
    assert listing["media"][0].asset_id is not None
    assert listing["media"][0].metadata_state == "done"
    assert listing["media"][0].derivative_ready == {"thumbnail": False, "preview": False}

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, status, max_long_edge
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', 512)
            """,
            (listing["media"][0].asset_id, stat.st_mtime_ns, stat.st_size),
        )

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert listing["media"][0].derivative_ready == {"thumbnail": True, "preview": False}

    library_id = list_libraries()[0]["id"]
    progress = get_library_progress(library_id)
    assert progress["indexed_assets"] == 1
    assert progress["estimated_assets"] == 1


def test_library_api_lists_progress_and_requires_delete_confirmation(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    with TestClient(app) as client:
        libraries = client.get("/api/libraries")
        assert libraries.status_code == 200
        default_library = next(library for library in libraries.json() if library["id"] == library_id)
        assert default_library["root_path"] == str(isolated_gallery_root.resolve())

        progress = client.get(f"/api/libraries/{default_library['id']}/progress")
        assert progress.status_code == 200
        assert set(progress.json()) == {
            "indexed_assets",
            "estimated_assets",
            "discovery_complete",
            "library_state",
            "active_job_id",
        }

        rejected = client.delete(f"/api/libraries/{default_library['id']}")
        assert rejected.status_code == 400
        deleted = client.delete(f"/api/libraries/{default_library['id']}?confirm=true")
        assert deleted.status_code == 200
    assert deleted.json()["source_files_deleted"] is False


def test_library_api_create_validate_and_update_multiple_import_paths(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    payload = {
        "name": "Managed",
        "import_paths": [str(first), str(second)],
        "exclusion_patterns": ["**/cache/**", "**/*.tmp"],
    }

    with TestClient(app) as client:
        validation = client.post("/api/libraries/validate", json=payload)
        assert validation.status_code == 200
        assert validation.json()["is_valid"] is True
        assert list_libraries() == []

        created = client.post("/api/libraries", json=payload)
        assert created.status_code == 201
        library = created.json()
        assert library["root_path"] == str(first.resolve())
        assert [item["path"] for item in library["import_paths"]] == [
            str(first.resolve()),
            str(second.resolve()),
        ]
        assert [item["position"] for item in library["import_paths"]] == [0, 1]
        assert library["exclusion_patterns"] == ["**/cache/**", "**/*.tmp"]

        updated = client.patch(
            f"/api/libraries/{library['id']}",
            json={
                "name": "Reordered",
                "import_paths": [str(second), str(first)],
                "exclusion_patterns": ["**/ignored/**"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Reordered"
        assert updated.json()["root_path"] == str(second.resolve())
        assert [item["path"] for item in updated.json()["import_paths"]] == [
            str(second.resolve()),
            str(first.resolve()),
        ]
        assert updated.json()["exclusion_patterns"] == ["**/ignored/**"]
        assert client.put(f"/api/libraries/{library['id']}", json={"name": "Alias"}).status_code == 200

    assert get_first_library_root() == second.resolve()
    assert get_library_for_path(first / "nested")["id"] == library["id"]
    assert get_library_for_path(second / "nested")["id"] == library["id"]


def test_library_api_rejects_cross_library_overlap_and_empty_update(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    nested = first / "nested"
    first.mkdir()
    nested.mkdir()
    register_library(first)
    with TestClient(app) as client:
        overlap = client.post("/api/libraries", json={"import_paths": [str(nested)]})
        assert overlap.status_code == 409
        assert overlap.json()["detail"]["error"] == "library_overlap"

        library_id = list_libraries()[0]["id"]
        empty = client.patch(f"/api/libraries/{library_id}", json={"import_paths": []})
        assert empty.status_code == 400
        assert empty.json()["detail"]["error"] == "bad_request"


def test_same_library_overlap_warns_but_is_allowed(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    nested = first / "nested"
    nested.mkdir(parents=True)
    payload = {"import_paths": [str(first), str(nested)]}
    with TestClient(app) as client:
        validation = client.post("/api/libraries/validate", json=payload)
        assert validation.status_code == 200
        assert validation.json()["is_valid"] is True
        assert validation.json()["import_paths"][0]["warnings"]
        created = client.post("/api/libraries", json=payload)
        assert created.status_code == 201


def test_library_update_marks_removed_or_excluded_assets_offline_and_reactivates(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    visible = first / "visible.png"
    excluded = second / "cache" / "excluded.png"
    create_test_png(visible)
    create_test_png(excluded)
    library = register_library(first)
    updated = update_library(int(library["id"]), import_paths=[first, second])
    assert updated is not None
    assert repair_library_assets(int(library["id"]))["added"] == 5

    updated = update_library(
        int(library["id"]),
        import_paths=[second],
        exclusion_patterns=["**/cache/**"],
    )
    assert updated is not None
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT offline FROM assets WHERE path = ?", (str(visible.resolve()),)).fetchone()[0] == 1
        assert conn.execute("SELECT offline FROM assets WHERE path = ?", (str(excluded.resolve()),)).fetchone()[0] == 1

    updated = update_library(
        int(library["id"]),
        import_paths=[first, second],
        exclusion_patterns=[],
    )
    assert updated is not None
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT offline FROM assets WHERE path = ?", (str(visible.resolve()),)).fetchone()[0] == 0
        assert conn.execute("SELECT offline FROM assets WHERE path = ?", (str(excluded.resolve()),)).fetchone()[0] == 0


def test_repair_applies_exclusion_patterns_across_import_paths(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    included = first / "included.png"
    excluded = second / "vendor-cache" / "excluded.png"
    create_test_png(included)
    create_test_png(excluded)
    library = register_library(first)
    update_library(
        int(library["id"]),
        import_paths=[first, second],
        exclusion_patterns=["**/vendor-cache/**"],
    )

    repair_library_assets(int(library["id"]))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(included.resolve()),)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(excluded.resolve()),)).fetchone()[0] == 0
    stored = get_library(int(library["id"]))
    assert stored is not None
    assert stored["asset_count"] == 1


def test_scan_and_folder_endpoints_apply_library_exclusion_patterns(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    visible = isolated_gallery_root / "visible"
    excluded = isolated_gallery_root / "private"
    visible.mkdir()
    excluded.mkdir()
    create_test_png(visible / "visible.png")
    create_test_png(excluded / "hidden.png")
    library = register_library(isolated_gallery_root)
    update_library(int(library["id"]), exclusion_patterns=["private/**"])

    with TestClient(app) as client:
        scan = client.get("/api/scan", params={"path": str(isolated_gallery_root)})
        assert scan.status_code == 200
        assert [folder["name"] for folder in scan.json()["folders"]] == ["visible"]

        folders = client.get("/api/folders", params={"path": str(isolated_gallery_root)})
        assert folders.status_code == 200
        assert [folder["name"] for folder in folders.json()] == ["visible"]

        assert client.get("/api/scan", params={"path": str(excluded)}).status_code == 404
        assert client.get("/api/folders", params={"path": str(excluded)}).status_code == 404
        assert (
            client.get(
                "/api/search",
                params={"q": "hidden", "scope": "current", "path": str(excluded)},
            ).status_code
            == 404
        )


def test_repair_reconciles_assets_without_deleting_derivatives(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    original = isolated_gallery_root / "original.png"
    create_test_png(original)
    assert repair_library_assets(library_id)["added"] == 2

    with sqlite3.connect(isolated_metadata_db) as conn:
        asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (str(original.resolve()),)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, status, max_long_edge
            ) VALUES (?, 'thumbnail', 'thumb_512', 1, 1, 'ready', 512)
            """,
            (asset_id,),
        )

    original.unlink()
    added_image = isolated_gallery_root / "added.png"
    create_test_png(added_image)
    counts = repair_library_assets(library_id)
    assert counts["added"] == 1
    assert counts["removed"] == 1

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT offline FROM assets WHERE id = ?", (asset_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM asset_derivatives WHERE asset_id = ?", (asset_id,)).fetchone()[0] == 1


def test_rebuild_reconciles_deleted_assets(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    update_library_state(library_id, "ready")
    image = isolated_gallery_root / "visible.png"
    create_test_png(image)

    rebuild_index_scope(isolated_gallery_root)
    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert [node.path for node in listing["media"]] == [str(image.resolve())]

    image.unlink()
    rebuild_index_scope(isolated_gallery_root)

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert listing["media"] == []
    with sqlite3.connect(isolated_metadata_db) as conn:
        offline = conn.execute(
            "SELECT offline FROM assets WHERE library_id = ? AND path = ?",
            (library_id, str(image.resolve())),
        ).fetchone()[0]
    assert offline == 1


def test_asset_folder_metadata_excludes_offline_children(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    album = isolated_gallery_root / "album"
    album.mkdir()
    visible = album / "visible.png"
    offline = album / "offline.png"
    create_test_png(visible)
    create_test_png(offline)
    assert repair_library_assets(library_id)["added"] == 4

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(offline.resolve()),))

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    folder = listing["folders"][0]
    assert folder.image_count == 1
    assert folder.cover_images == [str(visible.resolve())]


def test_repair_api_returns_reconciliation_counts(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    create_test_png(isolated_gallery_root / "new.png")
    library_id = _register_library(isolated_gallery_root)
    with TestClient(app) as client:
        response = client.post(f"/api/libraries/{library_id}/repair")
    assert response.status_code == 200
    assert response.json()["library_id"] == library_id
    assert response.json()["added"] == 2
    assert set(response.json()) == {"library_id", "job_id", "added", "removed", "modified"}
