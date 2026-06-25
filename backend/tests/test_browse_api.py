"""Phase 7 read-only catalog browse API coverage.

Purpose:
Cover `/api/browse` catalog listings for virtual roots, real folders,
pagination, availability, and invalid scopes.

Guarantees:
Browse responses stay catalog-backed, read-only, cursor-compatible, and strict
about library ownership.

Run when:
Changing browse response shape, import-root listing, catalog visibility, or
pagination.
"""

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
    mtime_ns: int | None = None,
    size: int = 128,
    width: int | None = None,
    height: int | None = None,
    metadata_state: str | None = None,
    duration_ms: int | None = None,
    mime_type: str | None = None,
) -> tuple[Any, ...]:
    resolved = str(path.resolve())
    parent = str((parent_path or path.parent).resolve())
    now = time.time()
    asset_mtime_ns = int(now * 1_000_000_000) if mtime_ns is None else mtime_ns
    return (
        library_id,
        resolved,
        parent,
        path.name,
        type,
        asset_mtime_ns,
        0 if type == "folder" else size,
        width,
        height,
        now,
        metadata_state if metadata_state is not None else ("pending" if type == "image" else None),
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


def _insert_image_metadata(
    path: Path,
    *,
    mtime_ns: int,
    size: int,
    width: int,
    height: int,
) -> None:
    resolved = str(path.resolve())
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
            """,
            (resolved, path.name, mtime_ns / 1_000_000_000, mtime_ns, size, width, height, now, now),
        )


def _allow_duplicate_image_metadata_for_test() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            DROP TRIGGER IF EXISTS image_metadata_ai;
            DROP TRIGGER IF EXISTS image_metadata_ad;
            DROP TRIGGER IF EXISTS image_metadata_au;
            DROP TABLE image_metadata;
            CREATE TABLE image_metadata (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL,
              name TEXT NOT NULL,
              mtime REAL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              metadata_json TEXT,
              updated_at REAL,
              indexed_at REAL
            );
            """
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


def test_browse_stale_metadata_not_used(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    root.mkdir()
    image = root / "asset.png"
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=100, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=100, size=100, width=640, height=480)

    current = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(root)})

    assert current.status_code == 200
    assert current.json()["media"][0]["width"] == 640
    assert current.json()["media"][0]["height"] == 480

    with _connect() as conn:
        conn.execute(
            """
            UPDATE image_metadata
            SET mtime_ns = 2100, width = 10, height = 20
            WHERE path = ?
            """,
            (str(image.resolve()),),
        )

    stale = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(root)})

    assert stale.status_code == 200
    assert stale.json()["media"][0]["width"] is None
    assert stale.json()["media"][0]["height"] is None


def test_browse_duplicate_metadata_does_not_duplicate_media(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    root.mkdir()
    image = root / "asset.png"
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    _allow_duplicate_image_metadata_for_test()
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=100, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=100, size=100, width=640, height=480)
    _insert_image_metadata(image, mtime_ns=50, size=100, width=10, height=20)

    response = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(root)})

    assert response.status_code == 200
    media = response.json()["media"]
    assert [item["path"] for item in media] == [str(image.resolve())]
    assert media[0]["width"] == 640
    assert media[0]["height"] == 480


def test_browse_tolerant_mtime_picks_closest_metadata(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "library"
    root.mkdir()
    image = root / "asset.png"
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    _allow_duplicate_image_metadata_for_test()
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="done"),
    )
    # Insert farther row first (gap=500, mtime_ns=500, im.id becomes 1)
    # then closer row second (gap=400, mtime_ns=600, im.id becomes 2).
    # This ensures the test would FAIL if tie-break wrongly used im.id before ABS(diff).
    _insert_image_metadata(image, mtime_ns=500, size=100, width=100, height=100)
    _insert_image_metadata(image, mtime_ns=600, size=100, width=200, height=200)

    response = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(root)})

    assert response.status_code == 200
    media = response.json()["media"]
    assert len(media) == 1
    assert media[0]["path"] == str(image.resolve())
    # Closest match: gap=400 (mtime_ns=600) vs gap=500 (mtime_ns=500)
    assert media[0]["width"] == 200
    assert media[0]["height"] == 200


def test_browse_per_root_availability(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    online = isolated_gallery_root / "online"
    offline = isolated_gallery_root / "offline"
    online.mkdir()
    offline.mkdir()
    library = create_library([online, offline], name="Multi import")
    library_id = int(library["id"])
    offline.rmdir()

    response = isolated_app.get("/api/browse", params={"library_id": library_id})

    assert response.status_code == 200
    availability_by_path = {folder["path"]: folder["availability"] for folder in response.json()["folders"]}
    assert availability_by_path[str(online.resolve())] == "available"
    assert availability_by_path[str(offline.resolve())] == "unavailable"


def test_browse_virtual_root_availability_treats_oserror_as_unavailable(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    online = isolated_gallery_root / "online"
    offline_mount = isolated_gallery_root / "offline_mount"
    online.mkdir()
    offline_mount.mkdir()
    library = create_library([online, offline_mount], name="Multi import")
    library_id = int(library["id"])

    real_is_dir = Path.is_dir

    def fake_is_dir(self: Path) -> bool:
        if str(self) == str(offline_mount.resolve()):
            raise OSError("stale NFS handle")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)

    response = isolated_app.get("/api/browse", params={"library_id": library_id})

    assert response.status_code == 200
    availability_by_path = {folder["path"]: folder["availability"] for folder in response.json()["folders"]}
    assert availability_by_path[str(online.resolve())] == "available"
    assert availability_by_path[str(offline_mount.resolve())] == "unavailable"


def test_browse_case_sensitive_scope(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)
    root = isolated_gallery_root / "Photos"
    upper = root / "A"
    lower = root / "a"
    upper.mkdir(parents=True)
    lower.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    _insert_assets(
        _asset_row(library_id, upper / "upper.png", parent_path=upper, metadata_state="pending"),
        _asset_row(library_id, lower / "lower-1.png", parent_path=lower, metadata_state="pending"),
        _asset_row(library_id, lower / "lower-2.png", parent_path=lower, metadata_state="pending"),
    )

    upper_browse = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(upper)})
    lower_browse = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(lower)})
    upper_status = isolated_app.get(f"/api/libraries/{library_id}/status", params={"scope_path": str(upper)})
    lower_status = isolated_app.get(f"/api/libraries/{library_id}/status", params={"scope_path": str(lower)})

    assert upper_browse.status_code == 200
    assert lower_browse.status_code == 200
    assert [item["name"] for item in upper_browse.json()["media"]] == ["upper.png"]
    assert [item["name"] for item in lower_browse.json()["media"]] == ["lower-1.png", "lower-2.png"]
    assert upper_status.status_code == 200
    assert lower_status.status_code == 200
    assert upper_status.json()["status"]["metadata"]["total_assets"] == 1
    assert lower_status.json()["status"]["metadata"]["total_assets"] == 2
