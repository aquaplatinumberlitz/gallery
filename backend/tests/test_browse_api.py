"""Phase 7 read-only catalog browse API coverage."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.metadata_store import _connect, create_library


def _asset_row(
    library_id: int,
    path: Path,
    *,
    type: str = "image",
    parent_path: Path | None = None,
    offline: int = 0,
    width: int | None = None,
    height: int | None = None,
    duration_ms: int | None = None,
    mime_type: str | None = None,
) -> tuple[Any, ...]:
    resolved = str(path.resolve())
    parent = str((parent_path or path.parent).resolve())
    now = time.time()
    return (
        library_id,
        resolved,
        parent,
        path.name,
        type,
        int(now * 1_000_000_000),
        0 if type == "folder" else 128,
        width,
        height,
        now,
        "pending" if type == "image" else None,
        offline,
        None,
        mime_type,
        duration_ms,
        None,
    )


def _insert_assets(*rows: tuple[Any, ...]) -> None:
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at,
              mime_type, duration_ms, codec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _table_counts() -> dict[str, int]:
    with _connect() as conn:
        return {
            "assets": int(conn.execute("SELECT count(*) FROM assets").fetchone()[0]),
            "library_jobs": int(conn.execute("SELECT count(*) FROM library_jobs").fetchone()[0]),
            "metadata_index_jobs": int(conn.execute("SELECT count(*) FROM metadata_index_jobs").fetchone()[0]),
        }


def test_browse_virtual_root_returns_ordered_import_roots(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    left = isolated_gallery_root / "left" / "photos"
    right = isolated_gallery_root / "right" / "photos"
    left.mkdir(parents=True)
    right.mkdir(parents=True)
    library = create_library([left, right], name="Multi import")
    library_id = int(library["id"])
    _insert_assets(
        _asset_row(library_id, left / "album", type="folder", parent_path=left),
        _asset_row(library_id, right / "cover.png", type="image", parent_path=right, width=100, height=80),
    )

    response = isolated_app.get("/api/browse", params={"library_id": library_id})

    assert response.status_code == 200
    data = response.json()
    assert data["index_source"] == "catalog"
    assert data["path"] is None
    assert data["media"] == []
    assert [folder["path"] for folder in data["folders"]] == [str(left.resolve()), str(right.resolve())]
    assert [folder["entry_kind"] for folder in data["folders"]] == ["import_root", "import_root"]
    assert [folder["display_label"] for folder in data["folders"]] == [str(left.resolve()), str(right.resolve())]
    assert [folder["availability"] for folder in data["folders"]] == ["available", "available"]
    assert data["folders"][0]["has_children"] is True
    assert data["folders"][1]["image_count"] == 1


def test_browse_real_folder_reads_catalog_rows_and_paginates(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    _insert_assets(
        _asset_row(library_id, root / "album", type="folder", parent_path=root),
        _asset_row(library_id, root / "asset1.png", type="image", parent_path=root, width=640, height=480),
        _asset_row(
            library_id,
            root / "asset2.mp4",
            type="video",
            parent_path=root,
            duration_ms=2500,
            mime_type="video/mp4",
        ),
        _asset_row(library_id, root / "asset3.png", type="image", parent_path=root, width=320, height=240),
        _asset_row(library_id, root / "offline.png", type="image", parent_path=root, offline=1),
        _asset_row(library_id, root / "album" / "nested.png", type="image", parent_path=root / "album"),
        _asset_row(library_id, root / "album_extra" / "leak.png", type="image", parent_path=root / "album_extra"),
    )

    first = isolated_app.get(
        "/api/browse",
        params={"library_id": library_id, "path": str(root), "limit": 2},
    )
    second = isolated_app.get(
        "/api/browse",
        params={"library_id": library_id, "path": str(root), "limit": 2, "cursor": first.json()["next_cursor"]},
    )
    nested = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(root / "album")})

    assert first.status_code == 200
    assert second.status_code == 200
    assert [folder["name"] for folder in first.json()["folders"]] == ["album"]
    assert [item["name"] for item in first.json()["media"]] == ["asset1.png", "asset2.mp4"]
    assert [item["name"] for item in second.json()["media"]] == ["asset3.png"]
    assert first.json()["next_cursor"] == 2
    assert second.json()["next_cursor"] is None
    assert first.json()["total_images"] == 2
    assert first.json()["total_videos"] == 1
    assert first.json()["total_assets"] == 3
    assert [item["name"] for item in nested.json()["media"]] == ["nested.png"]


def test_browse_rejects_cross_library_scope(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    first_root = isolated_gallery_root / "first"
    second_root = isolated_gallery_root / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = create_library([first_root], name="First")
    create_library([second_root], name="Second")

    response = isolated_app.get(
        "/api/browse",
        params={"library_id": int(first["id"]), "path": str(second_root)},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "bad_request"


def test_browse_empty_catalog_does_not_scan_or_write(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    root = isolated_gallery_root / "empty"
    root.mkdir()
    library = create_library([root], name="Empty")
    before = _table_counts()

    def fail_scandir(*_args, **_kwargs):
        raise AssertionError("/api/browse must not scan the filesystem")

    monkeypatch.setattr(os, "scandir", fail_scandir)

    response = isolated_app.get(
        "/api/browse",
        params={"library_id": int(library["id"]), "path": str(root)},
    )

    assert response.status_code == 200
    assert response.json()["folders"] == []
    assert response.json()["media"] == []
    assert response.json()["index_source"] == "catalog"
    assert _table_counts() == before


def test_browse_rejects_unknown_query_params(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")

    response = isolated_app.get(
        "/api/browse",
        params={"library_id": int(library["id"]), "bogus": "1"},
    )

    assert response.status_code == 422
    assert "bogus" in response.text
