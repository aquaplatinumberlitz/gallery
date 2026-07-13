"""Library/asset migration, dual-write, listing, and API coverage.

Purpose:
Cover library registration, catalog asset writes, migration compatibility, and
management API behavior.

Guarantees:
Registered libraries, import paths, file index rows, and asset rows stay
consistent through scans, updates, and listing.

Run when:
Changing library CRUD, asset catalog writes, migrations, or listing helpers.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import scan_worker as catalog_service
from backend.app import app
from backend.indexer import rebuild_index_scope
from backend.metadata_store import (
    _DB_LOCK,
    _connect,
    get_asset_folder_listing,
    get_first_library_root,
    get_job,
    get_library,
    get_library_for_path,
    get_library_progress,
    index_file,
    initialize_database,
    list_libraries,
    register_library,
    update_job_state,
    update_library,
    update_library_state,
    upsert_image_dimensions,
)
from tests.conftest import create_test_png


def _run_scan(library_id: int) -> dict:
    """Queue and execute one manual catalog scan synchronously, returning the finished job."""
    job, _created = catalog_service.queue_scan(library_id, trigger="manual")
    catalog_service.run_once()
    finished = get_job(int(job["id"]))
    assert finished is not None
    return finished


def _register_library(root: Path) -> int:
    return int(register_library(root)["id"])


def test_no_implicit_library_on_fresh_startup(isolated_metadata_db: Path):
    initialize_database()
    assert list_libraries() == []
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" not in columns


def test_library_listing_batches_child_queries(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    from backend.metadata_store import library_store

    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    library_store.create_library([first], exclusion_patterns=["cache/**"])
    library_store.create_library([second], exclusion_patterns=["tmp/**"])

    statements: list[str] = []
    real_connect = library_store._connect

    class RecordingConnection:
        def __init__(self):
            self.connection = real_connect()

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, statement, parameters=()):
            statements.append(" ".join(statement.split()))
            return self.connection.execute(statement, parameters)

    monkeypatch.setattr(library_store, "_connect", RecordingConnection)

    libraries = library_store.list_libraries()

    assert len(libraries) == 2
    assert len(statements) == 4
    assert sum("FROM library_import_paths" in statement for statement in statements) == 1
    assert sum("FROM library_exclusion_patterns" in statement for statement in statements) == 1
    assert sum("GROUP BY library_id" in statement for statement in statements) == 1


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
    assert listing["media"][0].derivative_ready == {"thumbnail": False, "preview": False}

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
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = client.get(f"/api/libraries/{default_library['id']}/progress")
            assert current.status_code == 200
            if current.json()["active_job_id"] is None:
                break
            time.sleep(0.01)
        assert current.json()["active_job_id"] is None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            deleted = client.delete(f"/api/libraries/{default_library['id']}?confirm=true")
            if deleted.status_code == 200:
                break
            assert deleted.status_code == 409
            assert deleted.json()["detail"]["error"] == "maintenance_busy"
            time.sleep(0.01)
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
        update_job_state(library["initial_scan_job_id"], "running")
        update_job_state(library["initial_scan_job_id"], "succeeded")

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


def test_same_library_overlap_is_rejected(
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
        assert validation.json()["is_valid"] is False
        created = client.post("/api/libraries", json=payload)
        assert created.status_code == 409


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
    updated = update_library(int(library["id"]), import_paths=[first, second], warm_enabled=False)
    assert updated is not None
    finished = _run_scan(int(library["id"]))
    assert finished["counters"]["indexed"] >= 5
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE metadata_index_jobs SET state = 'cancelled' WHERE library_id = ? AND state IN ('queued', 'running')",
            (int(library["id"]),),
        )

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


def test_scan_applies_exclusion_patterns_across_import_paths(
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

    _run_scan(int(library["id"]))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(included.resolve()),)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(excluded.resolve()),)).fetchone()[0] == 0
    stored = get_library(int(library["id"]))
    assert stored is not None
    assert stored["asset_count"] == 1


def test_folder_endpoints_apply_library_exclusion_patterns(
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
        folders = client.get("/api/folders", params={"path": str(isolated_gallery_root)})
        assert folders.status_code == 200
        assert [folder["name"] for folder in folders.json()] == ["visible"]

        assert client.get("/api/folders", params={"path": str(excluded)}).status_code == 404
        assert (
            client.get(
                "/api/search",
                params={"q": "hidden", "scope": "current", "path": str(excluded)},
            ).status_code
            == 404
        )


def test_scan_reconciles_assets_without_deleting_derivatives(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    original = isolated_gallery_root / "original.png"
    create_test_png(original)
    first = _run_scan(library_id)
    assert first["counters"]["indexed"] >= 2

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
    second = _run_scan(library_id)
    assert second["counters"]["indexed"] >= 1
    assert second["counters"]["reconciled"] >= 1

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT offline FROM assets WHERE id = ?", (asset_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM asset_derivatives WHERE asset_id = ?", (asset_id,)).fetchone()[0] >= 1


def test_offline_asset_api_finds_and_forgets_only_media_tombstones(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    missing = isolated_gallery_root / "missing image.png"
    restored_before_check = isolated_gallery_root / "present but stale.png"
    active = isolated_gallery_root / "active.png"
    for path in (missing, restored_before_check, active):
        create_test_png(path)
    _run_scan(library_id)

    missing.unlink()
    _run_scan(library_id)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(restored_before_check.resolve()),))
        missing_id = conn.execute("SELECT id FROM assets WHERE path = ?", (str(missing.resolve()),)).fetchone()[0]
        derivative_id = conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, status, max_long_edge
            ) VALUES (?, 'thumbnail', 'thumb_512', 1, 1, 'queued', 512)
            RETURNING id
            """,
            (missing_id,),
        ).fetchone()[0]
        conn.execute("INSERT INTO derivative_jobs (derivative_id) VALUES (?)", (derivative_id,))

    with TestClient(app) as client:
        found = client.get(f"/api/libraries/{library_id}/offline-assets")
        assert found.status_code == 200
        assert found.json()["total"] == 2
        assert [(item["name"], item["path"]) for item in found.json()["items"]] == [
            ("missing image.png", str(missing.resolve())),
            ("present but stale.png", str(restored_before_check.resolve())),
        ]

        unconfirmed = client.delete(f"/api/libraries/{library_id}/offline-assets")
        assert unconfirmed.status_code == 400

        forgotten = client.delete(
            f"/api/libraries/{library_id}/offline-assets",
            params={"confirm": "true"},
        )
        assert forgotten.status_code == 200
        assert forgotten.json()["forgotten"] == 2
        assert client.get(f"/api/libraries/{library_id}/stats").json()["offline_assets"] == 0
        assert client.get(f"/api/libraries/{library_id}/offline-assets").json() == {"items": [], "total": 0}

    assert restored_before_check.exists(), "Forgetting a catalog row must never delete a source file"
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE path = ?", (str(active.resolve()),)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()[0] == 0
        assert (
            conn.execute("SELECT count(*) FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)).fetchone()[0]
            == 0
        )


def test_offline_asset_api_returns_not_found_for_unknown_library(isolated_metadata_db: Path):
    initialize_database()
    with TestClient(app) as client:
        assert client.get("/api/libraries/999/offline-assets").status_code == 404
        assert client.delete("/api/libraries/999/offline-assets", params={"confirm": "true"}).status_code == 404


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
    finished = _run_scan(library_id)
    assert finished["state"] == "succeeded"

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(offline.resolve()),))

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    folder = listing["folders"][0]
    assert folder.image_count == 1
    assert folder.cover_images == [str(visible.resolve())]


def test_rebuild_api_route_is_removed(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    create_test_png(isolated_gallery_root / "new.png")
    library_id = _register_library(isolated_gallery_root)
    with TestClient(app) as client:
        response = client.post(
            f"/api/libraries/{library_id}/rebuild",
            json={"confirm": True},
        )
    assert response.status_code in {404, 405}


def test_manual_scan_partial_offline_returns_202(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    offline = isolated_gallery_root / "offline"
    first.mkdir()
    second.mkdir()
    offline.mkdir()
    create_test_png(first / "a.png")
    create_test_png(second / "b.png")
    library_id = _register_library(first)
    update_library(library_id, import_paths=[first, second, offline])
    offline.rmdir()

    with TestClient(app) as client:
        response = client.post(f"/api/libraries/{library_id}/scan")

    assert response.status_code == 202
    body = response.json()
    assert body["operation"] == "scan"
    assert body["state"] == "queued"
    stored = get_library(library_id)
    assert stored is not None
    assert stored["state"] != "offline"


def test_degraded_scan(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """Scanning with some offline import paths transitions to degraded and never scans offline paths."""
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    offline = isolated_gallery_root / "offline"
    first.mkdir()
    second.mkdir()
    offline.mkdir()
    create_test_png(first / "a.png")
    create_test_png(second / "b.png")
    create_test_png(offline / "c.png")
    library_id = _register_library(first)
    update_library(library_id, import_paths=[first, second, offline])
    (offline / "c.png").unlink()
    offline.rmdir()

    finished = _run_scan(library_id)
    assert finished["state"] == "succeeded"
    assert finished["message"] == "Update completed with offline paths"
    assert finished["progress_total"] == 2
    stored = get_library(library_id)
    assert stored is not None
    assert stored["state"] == "degraded"
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM assets WHERE path = ?",
                (str((isolated_gallery_root / "offline" / "c.png").resolve()),),
            ).fetchone()[0]
            == 0
        )


def test_degraded_rebuild(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """Rebuilding with some offline import paths transitions to degraded and never scans offline paths."""
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    offline = isolated_gallery_root / "offline"
    first.mkdir()
    second.mkdir()
    offline.mkdir()
    create_test_png(first / "a.png")
    create_test_png(second / "b.png")
    create_test_png(offline / "c.png")
    library_id = _register_library(first)
    update_library(library_id, import_paths=[first, second, offline])
    (offline / "c.png").unlink()
    offline.rmdir()

    rebuild, _created = catalog_service.queue_rebuild(library_id)
    catalog_service.run_once()
    finished = get_job(int(rebuild["id"]))
    assert finished is not None
    assert finished["state"] == "succeeded"
    assert finished["message"] == "Rebuild completed with offline paths"
    assert finished["progress_total"] == 2
    stored = get_library(library_id)
    assert stored is not None
    assert stored["state"] == "degraded"
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM assets WHERE path = ?",
                (str((isolated_gallery_root / "offline" / "c.png").resolve()),),
            ).fetchone()[0]
            == 0
        )
