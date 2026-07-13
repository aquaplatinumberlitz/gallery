"""Catalog-only search, inspector, and facet boundary regressions.

Purpose:
Verify that legacy index/metadata rows cannot bypass active registered assets.

Guarantees:
Search, metadata search, inspector rows/details, folders, facets, and metadata
availability exclude unowned, offline, deleted, wrong-type, and stale identities;
ownership probes use the indexed library/path key rather than scanning assets.

Run when:
Changing search/inspector/facet SQL, file identity matching, or catalog ownership.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.metadata_store import _DB_LOCK, _connect, index_file, register_library, upsert_metadata_result
from backend.metadata_store.identity import active_catalog_file_sql

from .conftest import create_test_png


def _seed_boundary_rows(root: Path) -> dict[str, Path]:
    library_root = root / "registered"
    library_root.mkdir()
    register_library(library_root)
    paths: dict[str, Path] = {}
    for state in ("owned", "offline", "deleted", "wrong_type", "stale"):
        path = library_root / f"auditneedle_{state}.png"
        create_test_png(path)
        stat = path.stat()
        assert index_file(path, path.name, path.parent, "image", stat.st_mtime, stat.st_size, 64, 64, "image/png")
        assert upsert_metadata_result(
            path,
            {
                "prompt": f"auditneedle {state}",
                "params": {"Model": "BoundaryModel", "Seed": state},
                "tool": "A1111",
            },
        )
        paths[state] = path

    unowned = root / "auditneedle_unowned.png"
    create_test_png(unowned)
    assert upsert_metadata_result(
        unowned,
        {
            "prompt": "auditneedle unowned secret",
            "params": {"Model": "BoundaryModel", "Seed": "unowned"},
            "tool": "A1111",
        },
    )
    paths["unowned"] = unowned

    with _DB_LOCK, _connect() as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(paths["offline"].resolve()),))
        conn.execute(
            "UPDATE assets SET deleted_at = ? WHERE path = ?",
            (time.time(), str(paths["deleted"].resolve())),
        )
        conn.execute("UPDATE assets SET type = 'video' WHERE path = ?", (str(paths["wrong_type"].resolve()),))
        conn.execute("UPDATE assets SET mtime_ns = mtime_ns + 1 WHERE path = ?", (str(paths["stale"].resolve()),))
        legacy_folder = root / "LegacyAlbumLeak"
        conn.execute(
            """
            INSERT INTO file_index(path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, library_id)
            VALUES (?, ?, ?, 'folder', ?, ?, NULL, ?, NULL)
            """,
            (
                str(legacy_folder),
                legacy_folder.name,
                str(root),
                time.time(),
                time.time_ns(),
                time.time(),
            ),
        )
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, 'folder', ?)",
            (legacy_folder.name, str(legacy_folder), str(root)),
        )
    return paths


def test_all_metadata_boundaries_require_current_active_assets(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    paths = _seed_boundary_rows(isolated_gallery_root)
    owned_path = str(paths["owned"].resolve())

    search = isolated_app.get("/api/search", params={"q": "auditneedle", "scope": "all", "limit": 50})
    assert search.status_code == 200
    assert {row["path"] for row in search.json()["media"]} == {owned_path}

    metadata_search = isolated_app.get("/api/search-metadata", params={"q": "auditneedle"})
    assert metadata_search.status_code == 200
    assert {row["path"] for row in metadata_search.json()["results"]} == {owned_path}

    inspector = isolated_app.get(
        "/api/library/inspector",
        params={"q": "auditneedle", "scope": "all", "limit": 50},
    )
    assert inspector.status_code == 200
    assert {row["path"] for row in inspector.json()["rows"]} == {owned_path}

    detail = isolated_app.get("/api/library/inspector/metadata", params={"path": owned_path})
    assert detail.status_code == 200
    for state in ("unowned", "offline", "deleted", "wrong_type", "stale"):
        hidden = isolated_app.get(
            "/api/library/inspector/metadata",
            params={"path": str(paths[state].resolve())},
        )
        assert hidden.status_code == 404

    album_search = isolated_app.get("/api/search", params={"q": "LegacyAlbumLeak", "scope": "all"})
    assert album_search.status_code == 200
    assert album_search.json()["albums"] == []

    facets = isolated_app.get("/api/facets")
    assert facets.status_code == 200
    body = facets.json()
    assert body["model"] == [{"value": "BoundaryModel", "count": 1}]
    assert body["folders"] == [{"value": str(paths["owned"].parent.resolve()), "count": 1}]
    assert body["seed_availability"] == [
        {"value": "available", "count": 1},
        {"value": "missing", "count": 0},
    ]
    assert body["metadata_availability"] == [
        {"value": "available", "count": 1},
        {"value": "missing", "count": 0},
    ]


def test_catalog_ownership_predicate_uses_library_path_index(isolated_gallery_root: Path) -> None:
    _seed_boundary_rows(isolated_gallery_root)
    predicate = active_catalog_file_sql(fi_alias="fi")
    with _DB_LOCK, _connect() as conn:
        plan = [
            str(row["detail"])
            for row in conn.execute(f"EXPLAIN QUERY PLAN SELECT count(*) FROM file_index AS fi WHERE {predicate}")
        ]

    catalog_steps = [detail for detail in plan if "catalog_asset" in detail]
    assert catalog_steps
    assert all("SCAN catalog_asset" not in detail for detail in catalog_steps)
    assert any("library_id" in detail and "path" in detail for detail in catalog_steps)
