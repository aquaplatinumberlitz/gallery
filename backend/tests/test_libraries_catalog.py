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


def _create_v8_catalog_fixture(db_path: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    image = root / "legacy.png"
    create_test_png(image, size=(40, 30))
    stat = image.stat()
    now = time.time()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE image_metadata (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              mtime REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              metadata_json TEXT,
              updated_at REAL,
              indexed_at REAL
            );
            CREATE TABLE file_index (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              type TEXT NOT NULL,
              mtime REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              indexed_at REAL
            );
            CREATE VIRTUAL TABLE file_index_fts USING fts5(
              name, path UNINDEXED, type UNINDEXED, parent_path UNINDEXED, tokenize='unicode61'
            );
            CREATE TABLE metadata_index_jobs (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              folder_path TEXT NOT NULL,
              root_path TEXT NOT NULL,
              mtime REAL NOT NULL,
              size INTEGER NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              queued_at REAL,
              started_at REAL,
              finished_at REAL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE folder_index_state (
              path TEXT PRIMARY KEY,
              dir_mtime_ns INTEGER NOT NULL,
              indexed_at REAL NOT NULL,
              complete INTEGER NOT NULL DEFAULT 0,
              child_count INTEGER NOT NULL DEFAULT 0,
              folder_count INTEGER NOT NULL DEFAULT 0,
              image_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              updated_at REAL NOT NULL
            );
            CREATE TABLE libraries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              root_path TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'discovering',
              watch_enabled INTEGER NOT NULL DEFAULT 1,
              warm_enabled INTEGER NOT NULL DEFAULT 1,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              last_scan_at REAL,
              last_error TEXT
            );
            CREATE TABLE library_import_paths (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, path),
              UNIQUE(library_id, position)
            );
            CREATE TABLE library_exclusion_patterns (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              pattern TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, pattern),
              UNIQUE(library_id, position)
            );
            CREATE TABLE library_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
              parent_job_id INTEGER REFERENCES library_jobs(id) ON DELETE SET NULL,
              type TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'queued',
              progress_current INTEGER NOT NULL DEFAULT 0,
              progress_total INTEGER,
              message TEXT,
              error TEXT,
              counters TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              started_at REAL,
              finished_at REAL
            );
            CREATE TABLE assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id),
              path TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL DEFAULT 'image',
              mtime_ns REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              orientation INTEGER,
              indexed_at REAL,
              metadata_state TEXT DEFAULT 'pending',
              offline INTEGER NOT NULL DEFAULT 0,
              deleted_at REAL,
              mime_type TEXT,
              duration_ms INTEGER,
              codec TEXT,
              UNIQUE(library_id, path)
            );
            CREATE TABLE asset_derivatives (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id INTEGER NOT NULL REFERENCES assets(id),
              kind TEXT NOT NULL,
              variant TEXT NOT NULL,
              source_mtime_ns REAL NOT NULL,
              source_size INTEGER NOT NULL,
              format TEXT NOT NULL DEFAULT 'webp',
              quality INTEGER NOT NULL DEFAULT 85,
              max_long_edge INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              cache_path TEXT,
              byte_size INTEGER,
              last_accessed_at REAL,
              attempts INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(asset_id, kind, variant, source_mtime_ns, source_size)
            );
            CREATE TABLE derivative_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              derivative_id INTEGER NOT NULL REFERENCES asset_derivatives(id),
              priority INTEGER NOT NULL DEFAULT 3,
              state TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              started_at REAL,
              completed_at REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO libraries (root_path, name, state, created_at, updated_at)
            VALUES (?, 'Legacy', 'ready', ?, ?)
            """,
            (str(root.resolve()), now, now),
        )
        library_id = int(conn.execute("SELECT id FROM libraries").fetchone()[0])
        conn.execute(
            """
            INSERT INTO library_import_paths (library_id, path, position, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (library_id, str(root.resolve()), now, now),
        )
        conn.execute(
            """
            INSERT INTO file_index (path, name, parent_path, type, mtime, size, width, height, indexed_at)
            VALUES (?, ?, ?, 'image', ?, ?, 40, 30, ?)
            """,
            (str(image.resolve()), image.name, str(root.resolve()), stat.st_mtime, stat.st_size, now),
        )
        conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size, width, height, indexed_at, metadata_state
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, 40, 30, ?, 'pending')
            """,
            (library_id, str(image.resolve()), str(root.resolve()), image.name, stat.st_mtime, stat.st_size, now),
        )
        conn.execute(
            """
            INSERT INTO library_jobs (library_id, type, state, counters, created_at, updated_at)
            VALUES (?, 'repair', 'queued', '{}', ?, ?)
            """,
            (library_id, now, now),
        )
        conn.execute("PRAGMA user_version = 8")


def _register_library(root: Path) -> int:
    return int(register_library(root)["id"])


def test_no_implicit_library_on_fresh_startup(isolated_metadata_db: Path):
    initialize_database()
    assert list_libraries() == []
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" not in columns


def test_v8_to_v9_migration_backs_up_removes_root_path_and_adds_catalog_schema(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)

    import backend.metadata_store as metadata_store

    metadata_store._db._DB_INITIALIZED = False
    initialize_database()

    backups = list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    assert len(backups) == 1
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        library_columns = {row["name"] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" not in library_columns
        job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(library_jobs)")}
        assert {"scope_path", "trigger", "priority", "metadata_queued_assets"} <= job_columns
        file_columns = {row["name"] for row in conn.execute("PRAGMA table_info(file_index)")}
        assert {"library_id", "mtime_ns", "last_seen_scan_job_id"} <= file_columns
        asset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(assets)")}
        assert "last_seen_scan_job_id" in asset_columns
        assert conn.execute("SELECT 1 FROM catalog_rebuild_entries").fetchone() is None
        job = conn.execute("SELECT state, error FROM library_jobs WHERE type = 'repair'").fetchone()
        assert job["state"] == "cancelled"
        assert job["error"] == "Closed by catalog v9 migration"
        file_index = conn.execute("SELECT library_id FROM file_index").fetchone()
        assert file_index["library_id"] is not None


def test_v9_migration_preflight_failure_leaves_v8_database_unmutated(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("DELETE FROM library_import_paths")

    import backend.metadata_store as metadata_store

    metadata_store._db._DB_INITIALIZED = False
    try:
        initialize_database()
    except RuntimeError as exc:
        assert "libraries without import paths" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("Expected v9 preflight to fail")

    assert not list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" in columns


def test_v9_migration_rejects_overlapping_import_paths_before_backup(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)
    nested = isolated_gallery_root / "nested"
    nested.mkdir()
    now = time.time()
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            INSERT INTO libraries (root_path, name, state, created_at, updated_at)
            VALUES (?, 'Nested', 'ready', ?, ?)
            """,
            (str(nested.resolve()), now, now),
        )
        nested_library_id = int(conn.execute("SELECT max(id) FROM libraries").fetchone()[0])
        conn.execute(
            """
            INSERT INTO library_import_paths (library_id, path, position, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (nested_library_id, str(nested.resolve()), now, now),
        )

    import backend.metadata_store as metadata_store

    metadata_store._db._DB_INITIALIZED = False
    try:
        initialize_database()
    except RuntimeError as exc:
        assert "overlapping import paths" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("Expected v9 preflight to reject overlapping import paths")

    assert not list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" in columns


def test_v9_migration_rejects_unowned_catalog_rows_before_backup(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)
    outside = tmp_path / "outside.png"
    create_test_png(outside)
    now = time.time()
    stat = outside.stat()
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            """
            INSERT INTO file_index (path, name, parent_path, type, mtime, size, width, height, indexed_at)
            VALUES (?, ?, ?, 'image', ?, ?, 40, 30, ?)
            """,
            (str(outside.resolve()), outside.name, str(outside.parent.resolve()), stat.st_mtime, stat.st_size, now),
        )

    import backend.metadata_store as metadata_store

    metadata_store._db._DB_INITIALIZED = False
    try:
        initialize_database()
    except RuntimeError as exc:
        assert "file_index row" in str(exc)
        assert "maps to 0 libraries" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("Expected v9 preflight to reject unowned catalog rows")

    assert not list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" in columns


def test_v9_migration_backup_failure_leaves_v8_database_unmutated(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)

    import backend.metadata_store as metadata_store

    original = metadata_store._schema._backup_database_before_v9

    def fail_backup(conn):  # noqa: ANN001
        raise RuntimeError("forced backup failure")

    metadata_store._db._DB_INITIALIZED = False
    metadata_store._schema._backup_database_before_v9 = fail_backup
    try:
        try:
            initialize_database()
        except RuntimeError as exc:
            assert "forced backup failure" in str(exc)
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("Expected backup failure")
    finally:
        metadata_store._schema._backup_database_before_v9 = original

    assert not list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" in columns


def test_v9_migration_rolls_back_after_schema_error_and_can_retry(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)

    import backend.metadata_store as metadata_store

    original = metadata_store._schema._rebuild_libraries_without_root_path

    def fail_rebuild(conn):  # noqa: ANN001
        original(conn)
        raise RuntimeError("forced migration failure")

    metadata_store._db._DB_INITIALIZED = False
    metadata_store._schema._rebuild_libraries_without_root_path = fail_rebuild
    try:
        try:
            initialize_database()
        except RuntimeError as exc:
            assert "forced migration failure" in str(exc)
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("Expected forced migration failure")
    finally:
        metadata_store._schema._rebuild_libraries_without_root_path = original

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" in columns

    metadata_store._db._DB_INITIALIZED = False
    initialize_database()
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        columns = {row[1] for row in conn.execute("PRAGMA table_info(libraries)")}
        assert "root_path" not in columns


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


def test_same_library_overlap_migration_preflight_rejects(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    _create_v8_catalog_fixture(isolated_metadata_db, isolated_gallery_root)
    nested = isolated_gallery_root / "nested"
    nested.mkdir()
    now = time.time()
    with sqlite3.connect(isolated_metadata_db) as conn:
        library_id = int(conn.execute("SELECT id FROM libraries").fetchone()[0])
        conn.execute(
            """
            INSERT INTO library_import_paths (library_id, path, position, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (library_id, str(nested.resolve()), now, now),
        )

    import backend.metadata_store as metadata_store

    metadata_store._db._DB_INITIALIZED = False
    try:
        initialize_database()
    except RuntimeError as exc:
        assert "overlapping import paths" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("Expected v9 preflight to reject same-library overlapping import paths")

    assert not list(isolated_metadata_db.parent.glob(f"{isolated_metadata_db.stem}.v8-backup-*"))
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8


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
    finished = _run_scan(int(library["id"]))
    assert finished["counters"]["indexed"] >= 5

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


def test_rebuild_api_returns_job_envelope(
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
    assert response.status_code == 202
    body = response.json()
    assert body["library_id"] == library_id
    assert body["operation"] == "rebuild"
    assert body["trigger"] == "manual"
    assert body["state"] == "queued"
    assert body["coalesced"] is False


def test_rebuild_api_requires_confirmation(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    library_id = _register_library(isolated_gallery_root)
    with TestClient(app) as client:
        response = client.post(
            f"/api/libraries/{library_id}/rebuild",
            json={"confirm": False},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_rebuild_api_rejects_out_of_library_scope(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
):
    outside = tmp_path / "truly_outside"
    outside.mkdir()
    library_id = _register_library(isolated_gallery_root)
    with TestClient(app) as client:
        response = client.post(
            f"/api/libraries/{library_id}/rebuild",
            json={"confirm": True, "scope_path": str(outside)},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "bad_request"


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


def test_rebuild_partial_offline_returns_202(
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
        response = client.post(
            f"/api/libraries/{library_id}/rebuild",
            json={"confirm": True},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["operation"] == "rebuild"
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
    assert finished["message"] == "Scan completed with offline paths"
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
