"""Tests for imported-data maintenance endpoints.

Purpose:
Validate update, clear, rebuild, and reset maintenance APIs for imported
library data and their derivative/catalog side effects.

Guarantees:
Imported-data maintenance preserves registered library records when clearing
derived data, rebuilds catalog state from import paths, and reports job state
for destructive reset operations.

Run when:
Maintenance endpoint behavior, imported library metadata storage, or derivative
cleanup/rebuild flows change.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.derivative_scheduler as derivative_scheduler_module
from backend.metadata_store import _DB_LOCK, _connect, create_job, create_library, initialize_database, update_job_state
from backend.metadata_store.job_store import update_parent_aggregate_job
from tests.conftest import create_test_png


def _seed_imported_data(root: Path, cache_dir: Path, monkeypatch) -> int:
    monkeypatch.setattr(derivative_scheduler_module, "THUMBNAIL_CACHE_DIR", cache_dir)
    library = create_library([root], name="Imported", exclusion_patterns=["*.tmp"])
    image = root / "one.png"
    create_test_png(image)
    cache_file = cache_dir / "files" / "one.webp"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"preview")
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size, indexed_at,
              metadata_state, offline
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 'done', 0)
            """,
            (
                library["id"],
                str(image),
                str(image.parent),
                image.name,
                image.stat().st_mtime_ns,
                image.stat().st_size,
                now,
            ),
        )
        asset_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO file_index (
              path, name, parent_path, type, mtime_ns, size, indexed_at, library_id
            ) VALUES (?, ?, ?, 'image', ?, ?, ?, ?)
            """,
            (
                str(image),
                image.name,
                str(image.parent),
                image.stat().st_mtime_ns,
                image.stat().st_size,
                now,
                library["id"],
            ),
        )
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
            (image.name, str(image), str(image.parent)),
        )
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, indexed_at
            ) VALUES (?, ?, ?, ?, ?, 64, 64, ?)
            """,
            (str(image), image.name, image.stat().st_mtime, image.stat().st_mtime_ns, image.stat().st_size, now),
        )
        conn.execute(
            """
            INSERT INTO image_resources (path, kind, name, updated_at)
            VALUES (?, 'lora', 'test', ?)
            """,
            (str(image), now),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size,
              state, queued_at, updated_at, library_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?, ?)
            """,
            (
                str(image),
                image.name,
                str(image.parent),
                str(image.parent),
                str(root),
                image.stat().st_mtime,
                image.stat().st_mtime_ns,
                image.stat().st_size,
                now,
                now,
                library["id"],
            ),
        )
        scan_job = conn.execute(
            """
            INSERT INTO library_jobs (
              library_id, type, state, trigger, priority, progress_current,
              message, counters, created_at, updated_at, finished_at
            ) VALUES (?, 'scan', 'succeeded', 'manual', 50, 1, 'done', '{}', ?, ?, ?)
            """,
            (library["id"], now, now, now),
        )
        conn.execute(
            """
            INSERT INTO catalog_rebuild_entries (
              job_id, library_id, path, parent_path, name, type, created_at
            ) VALUES (?, ?, ?, ?, ?, 'image', ?)
            """,
            (int(scan_job.lastrowid), library["id"], str(image), str(image.parent), image.name, now),
        )
        conn.execute(
            """
            INSERT INTO folder_index_state (
              path, dir_mtime_ns, indexed_at, complete, updated_at
            ) VALUES (?, ?, ?, 1, ?)
            """,
            (str(root), root.stat().st_mtime_ns, now, now),
        )
        derivative = conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, status,
              cache_path, byte_size, max_long_edge, format, quality
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', ?, ?, 512, 'webp', 85)
            """,
            (
                asset_id,
                float(image.stat().st_mtime_ns),
                image.stat().st_size,
                str(cache_file),
                cache_file.stat().st_size,
            ),
        )
        conn.execute(
            """
            INSERT INTO derivative_jobs (derivative_id, state, created_at, updated_at)
            VALUES (?, 'done', ?, ?)
            """,
            (int(derivative.lastrowid), now, now),
        )
    return int(library["id"])


def _table_count(table: str) -> int:
    with _DB_LOCK, _connect() as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _seed_active_work(kind: str, conn, library_id: int) -> None:
    now = time.time()
    if kind == "catalog":
        create_job("scan", library_id=library_id)
        return
    if kind == "metadata":
        image_path = Path(f"/tmp/maintenance-active-{library_id}.png")
        conn.execute(
            """
            INSERT OR REPLACE INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path, mtime, size,
              state, queued_at, updated_at, library_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (
                str(image_path),
                image_path.name,
                str(image_path.parent),
                str(image_path.parent),
                str(image_path.parent),
                now,
                1,
                now,
                now,
                library_id,
            ),
        )
        return
    if kind == "derivative":
        asset = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size, indexed_at,
              metadata_state, offline
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 'done', 0)
            """,
            (
                library_id,
                f"/tmp/maintenance-active-{library_id}.png",
                "/tmp",
                f"maintenance-active-{library_id}.png",
                int(now * 1_000_000_000),
                1,
                now,
            ),
        )
        derivative = conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, max_long_edge, status
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, 1, 512, 'pending')
            """,
            (int(asset.lastrowid), float(int(now * 1_000_000_000))),
        )
        conn.execute(
            "INSERT INTO derivative_jobs (derivative_id, priority, state, created_at, updated_at) VALUES (?, 3, 'queued', ?, ?)",
            (int(derivative.lastrowid), now, now),
        )
        return
    raise ValueError(f"Unknown active work kind: {kind}")


def test_clear_imported_data_preserves_libraries_import_paths_exclusions_and_clears_derived_rows_files(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    monkeypatch,
) -> None:
    initialize_database()
    library_id = _seed_imported_data(isolated_gallery_root, isolated_thumbnail_cache, monkeypatch)

    response = isolated_app.post("/api/maintenance/imported-data/clear", json={"confirm": True})

    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "cleared"
    assert data["libraries_preserved"] == 1
    assert data["preview_files_deleted"] == 1
    assert _table_count("libraries") == 1
    assert _table_count("library_import_paths") == 1
    assert _table_count("library_exclusion_patterns") == 1
    assert not (isolated_thumbnail_cache / "files" / "one.webp").exists()
    for table in (
        "assets",
        "file_index",
        "file_index_fts",
        "image_metadata",
        "image_resources",
        "metadata_index_jobs",
        "library_jobs",
        "catalog_rebuild_entries",
        "folder_index_state",
        "asset_derivatives",
        "derivative_jobs",
    ):
        assert _table_count(table) == 0, table
    with _DB_LOCK, _connect() as conn:
        library = conn.execute(
            "SELECT state, last_scan_at, last_error FROM libraries WHERE id = ?", (library_id,)
        ).fetchone()
    assert library["state"] == "discovering"
    assert library["last_scan_at"] is None
    assert library["last_error"] is None


def test_clear_imported_data_requires_confirmation(isolated_app: TestClient) -> None:
    response = isolated_app.post("/api/maintenance/imported-data/clear", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_rebuild_imported_data_requires_confirmation(isolated_app: TestClient) -> None:
    response = isolated_app.post("/api/maintenance/imported-data/rebuild", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_clear_imported_data_rejects_active_jobs(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    library = create_library([isolated_gallery_root], name="Busy")
    create_job("scan", library_id=library["id"])

    response = isolated_app.post("/api/maintenance/imported-data/clear", json={"confirm": True})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "maintenance_busy"


def test_rebuild_imported_data_rejects_active_jobs(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    library = create_library([isolated_gallery_root], name="Busy")
    create_job("scan", library_id=library["id"])

    response = isolated_app.post("/api/maintenance/imported-data/rebuild", json={"confirm": True})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "maintenance_busy"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/maintenance/imported-data/clear", {"confirm": True}),
        ("/api/maintenance/imported-data/rebuild", {"confirm": True}),
        ("/api/maintenance/catalog/reset", {"confirm_phrase": "RESET CATALOG DATABASE"}),
    ],
)
@pytest.mark.parametrize(
    ("kind", "count_key"),
    [
        ("catalog", "catalog_jobs"),
        ("metadata", "metadata_jobs"),
        ("derivative", "derivative_jobs"),
    ],
)
def test_maintenance_endpoints_reject_all_active_work_types(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    path: str,
    payload: dict[str, object],
    kind: str,
    count_key: str,
) -> None:
    library = create_library([isolated_gallery_root], name="Busy")
    with _DB_LOCK, _connect() as conn:
        _seed_active_work(kind, conn, int(library["id"]))

    response = isolated_app.post(path, json=payload)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "maintenance_busy"
    assert detail[count_key] == 1


def test_rebuild_imported_data_clears_and_queues_parent_and_child(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    monkeypatch,
) -> None:
    library_id = _seed_imported_data(isolated_gallery_root, isolated_thumbnail_cache, monkeypatch)

    response = isolated_app.post("/api/maintenance/imported-data/rebuild", json={"confirm": True})

    assert response.status_code == 202
    data = response.json()
    assert data["state"] == "running"
    assert data["count"] == 1
    assert len(data["child_job_ids"]) == 1
    assert data["clear"]["assets_cleared"] == 1
    assert data["clear"]["file_index_rows_cleared"] == 1
    assert data["clear"]["image_metadata_rows_cleared"] == 1
    assert data["clear"]["preview_files_deleted"] == 1
    assert _table_count("assets") == 0
    assert _table_count("file_index") == 0
    assert _table_count("image_metadata") == 0
    assert not (isolated_thumbnail_cache / "files" / "one.webp").exists()
    with _DB_LOCK, _connect() as conn:
        parent = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (data["job_id"],)).fetchone()
        child = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (data["child_job_ids"][0],)).fetchone()
    assert parent["type"] == "rebuild_imported_data"
    assert parent["state"] == "running"
    assert child["type"] == "rebuild"
    assert child["library_id"] == library_id
    assert child["parent_job_id"] == parent["id"]


def test_rebuild_imported_data_no_libraries_is_succeeded_noop(isolated_app: TestClient) -> None:
    response = isolated_app.post("/api/maintenance/imported-data/rebuild", json={"confirm": True})

    assert response.status_code == 202
    assert response.json()["state"] == "succeeded"
    assert response.json()["child_job_ids"] == []


def test_rebuild_parent_aggregate_transitions_from_child_results(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
) -> None:
    library = create_library([isolated_gallery_root], name="Aggregate")
    parent = create_job("rebuild_imported_data", progress_total=1)
    child = create_job("rebuild", library_id=library["id"], parent_job_id=parent["id"])
    update_job_state(child["id"], "running")
    update_job_state(child["id"], "succeeded")

    updated = update_parent_aggregate_job(parent["id"])

    assert updated is not None
    assert updated["state"] == "succeeded"
    assert updated["progress_current"] == 1


def test_reset_catalog_database_deletes_libraries(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    monkeypatch,
) -> None:
    _seed_imported_data(isolated_gallery_root, isolated_thumbnail_cache, monkeypatch)

    response = isolated_app.post(
        "/api/maintenance/catalog/reset",
        json={"confirm_phrase": "RESET CATALOG DATABASE"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "reset"
    assert _table_count("libraries") == 0
    assert _table_count("library_import_paths") == 0
    assert _table_count("library_exclusion_patterns") == 0
    assert isolated_app.get("/api/libraries").json() == []


def test_reset_catalog_database_requires_phrase(isolated_app: TestClient) -> None:
    response = isolated_app.post("/api/maintenance/catalog/reset", json={"confirm_phrase": "wrong"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_reset_catalog_database_rejects_active_jobs(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    library = create_library([isolated_gallery_root], name="Busy")
    create_job("scan", library_id=library["id"])

    response = isolated_app.post(
        "/api/maintenance/catalog/reset",
        json={"confirm_phrase": "RESET CATALOG DATABASE"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "maintenance_busy"
    assert _table_count("libraries") == 1
