"""
Purpose:
Exercise uncovered search.py branches for empty metadata queries, scope-current
path safety, missing folder handling, stale-row detection, inspector overscan
error paths, and inspector metadata error mapping so backend line coverage stays
above the release threshold.

Guarantees:
* /api/search-metadata returns an empty result shape for empty queries without
  touching the search backend.
* /api/search returns 403 for scope=current with an unsafe path and 404 for a
  missing folder, and 500 when the underlying search raises.
* /api/search filters stale rows and triggers cleanup_stale_index when paths
  no longer resolve or are no longer safe.
* /api/library/inspector returns 403 for unsafe paths and 404 for missing
  folders, 400 for an invalid cursor (initial and overscan), and 500 when the
  underlying inspector call raises.
* /api/library/inspector handles truncated pages with no safe rows (next_cursor
  passthrough) and rejects unindexed paths in the metadata detail endpoint.

Run when:
* changing search.py route handlers, scope validation, stale-row cleanup
  integration, or library inspector pagination/overscan behavior
* touching path-safety checks or error mapping for search and inspector routes
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import search as search_module

# ---------------------------------------------------------------------------
# /api/search-metadata empty query
# ---------------------------------------------------------------------------


def test_search_metadata_empty_query_returns_empty(isolated_app: TestClient):
    resp = isolated_app.get("/api/search-metadata", params={"q": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"query": "", "total": 0, "results": []}


def test_search_metadata_whitespace_query_returns_empty(isolated_app: TestClient):
    resp = isolated_app.get("/api/search-metadata", params={"q": "   "})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"query": "   ", "total": 0, "results": []}


def test_search_metadata_failure_returns_500(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("backend down")

    monkeypatch.setattr(search_module, "search_metadata", boom)
    resp = isolated_app.get("/api/search-metadata", params={"q": "anything"})
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /api/search scope=current path safety + missing folder
# ---------------------------------------------------------------------------


def test_search_scope_current_unsafe_path_returns_403(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    # Force is_path_safe to False to trigger the 403 branch
    monkeypatch.setattr(search_module, "is_path_safe", lambda _: False)
    resp = isolated_app.get(
        "/api/search",
        params={"q": "hello", "scope": "current", "path": "/etc"},
    )
    assert resp.status_code == 403


def test_search_scope_current_missing_folder_returns_404(isolated_app: TestClient, isolated_gallery_root: Path):
    missing = isolated_gallery_root / "missing_folder"
    resp = isolated_app.get(
        "/api/search",
        params={"q": "hello", "scope": "current", "path": str(missing)},
    )
    assert resp.status_code == 404


def test_search_failure_returns_500(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("backend down")

    monkeypatch.setattr(search_module, "search_index", boom)
    resp = isolated_app.get("/api/search", params={"q": "hello", "scope": "all"})
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /api/search stale row handling
# ---------------------------------------------------------------------------


def test_search_filters_stale_rows_and_triggers_cleanup(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """When search returns rows for deleted/missing files, the safe_section
    filter should drop them and cleanup_stale_index should be called."""
    image = isolated_gallery_root / "ghost.png"
    image.write_bytes(b"data")

    import time

    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    index_file(str(image), "ghost.png", str(isolated_gallery_root), "photo", time.time(), 4, 1, 1)

    # Delete the file so the index row becomes stale
    image.unlink()

    cleanup_called = []
    monkeypatch.setattr(
        search_module,
        "cleanup_stale_index",
        lambda *args, **kwargs: cleanup_called.append(1),  # noqa: ANN002, ANN003
    )

    resp = isolated_app.get("/api/search", params={"q": "ghost", "scope": "all"})
    assert resp.status_code == 200
    for _ in range(50):
        if cleanup_called:
            break
        time.sleep(0.01)
    assert len(cleanup_called) >= 1


def test_search_empty_query_returns_paginated_media_shape(isolated_app: TestClient):
    resp = isolated_app.get("/api/search", params={"q": "", "scope": "all"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["albums"] == []
    assert data["media"] == []
    assert data["next_cursor"] is None
    assert data["has_more"] is False
    assert data["returned"] == 0


def test_search_media_pages_do_not_duplicate_paths(isolated_app: TestClient, isolated_gallery_root: Path):
    import time

    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    for index in range(5):
        image = isolated_gallery_root / f"page_asset_{index}.png"
        image.write_bytes(b"data")
        index_file(
            str(image),
            image.name,
            str(isolated_gallery_root),
            "photo",
            time.time() + index,
            4,
            1,
            1,
        )

    first = isolated_app.get("/api/search", params={"q": "page_asset", "scope": "all", "limit": 2})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["returned"] == 2
    assert first_data["next_cursor"] == 2

    second = isolated_app.get(
        "/api/search",
        params={"q": "page_asset", "scope": "all", "limit": 2, "cursor": first_data["next_cursor"]},
    )
    assert second.status_code == 200
    second_data = second.json()
    first_paths = {item["path"] for item in first_data["media"]}
    second_paths = {item["path"] for item in second_data["media"]}
    assert first_paths.isdisjoint(second_paths)


def test_search_albums_only_return_on_first_page(isolated_app: TestClient, isolated_gallery_root: Path):
    import time

    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    album = isolated_gallery_root / "page_album"
    album.mkdir()
    index_file(str(album), album.name, str(isolated_gallery_root), "folder", time.time(), 0, None, None)
    for index in range(3):
        image = album / f"page_album_asset_{index}.png"
        image.write_bytes(b"data")
        index_file(str(image), image.name, str(album), "photo", time.time() + index, 4, 1, 1)

    first = isolated_app.get("/api/search", params={"q": "page_album", "scope": "all", "limit": 1})
    assert first.status_code == 200
    assert first.json()["albums"]

    second = isolated_app.get("/api/search", params={"q": "page_album", "scope": "all", "limit": 1, "cursor": 1})
    assert second.status_code == 200
    assert second.json()["albums"] == []


def test_fielded_search_media_excludes_unfiltered_filename_videos(
    isolated_app: TestClient, isolated_gallery_root: Path
):
    import time

    from backend.metadata_store import index_file, register_library, upsert_metadata_result

    register_library(isolated_gallery_root)
    image = isolated_gallery_root / "rain_seed_image.png"
    image.write_bytes(b"image")
    video = isolated_gallery_root / "rain_seed_clip.mp4"
    video.write_bytes(b"video")
    index_file(str(image), image.name, str(isolated_gallery_root), "photo", time.time(), 5, 1, 1)
    index_file(str(video), video.name, str(isolated_gallery_root), "video", time.time(), 5, None, None)
    assert upsert_metadata_result(
        image,
        {
            "prompt": "rain portrait",
            "params": {"Seed": "123"},
            "width": 1,
            "height": 1,
        },
    )

    resp = isolated_app.get("/api/search", params={"q": "rain seed:123", "scope": "all"})
    assert resp.status_code == 200
    names = [item["name"] for item in resp.json()["media"]]
    assert image.name in names
    assert video.name not in names


# ---------------------------------------------------------------------------
# /api/library/inspector error paths
# ---------------------------------------------------------------------------


def test_inspector_scope_current_unsafe_path_returns_403(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "is_path_safe", lambda _: False)
    resp = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "current", "path": "/etc"},
    )
    assert resp.status_code == 403


def test_inspector_scope_current_missing_folder_returns_404(isolated_app: TestClient, isolated_gallery_root: Path):
    missing = isolated_gallery_root / "missing_folder"
    resp = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "current", "path": str(missing)},
    )
    assert resp.status_code == 404


def test_inspector_invalid_cursor_returns_400(isolated_app: TestClient):
    resp = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "all", "cursor": "not-valid-base64-or-json!!"},
    )
    assert resp.status_code == 400


def test_inspector_failure_returns_500(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("inspector backend down")

    monkeypatch.setattr(search_module, "list_library_inspector_rows", boom)
    resp = isolated_app.get("/api/library/inspector", params={"scope": "all"})
    assert resp.status_code == 500


def _seed_stale_row(gallery_root: Path, name: str = "stale_row.png") -> str:
    """Insert a stale (non-existent on disk) row into both file_index and
    image_metadata so /api/library/inspector returns it and marks it stale."""
    from backend.metadata_store import index_file, register_library, upsert_metadata_result

    register_library(gallery_root)
    path = gallery_root / name
    path.write_bytes(b"x")
    stat = path.stat()
    assert index_file(path, name, gallery_root, "image", stat.st_mtime, stat.st_size, 1, 1)
    assert upsert_metadata_result(path, {"prompt": "stale prompt"})
    stale_path = str(path.resolve())
    path.unlink()
    return stale_path


def test_inspector_overscan_invalid_cursor_returns_400(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """When overscan is triggered and the cursor is invalid, a 400 is returned."""
    _seed_stale_row(isolated_gallery_root, "overscan_invalid.png")

    original = search_module.list_library_inspector_rows
    call_count = {"n": 0}

    def fail_on_second(*args, **kwargs):  # noqa: ANN002, ANN003
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise ValueError("invalid cursor during overscan")
        data = original(*args, **kwargs)
        data["rows"] = [{"path": str(isolated_gallery_root / "missing.png")}]
        data["truncated"] = True
        return data

    monkeypatch.setattr(search_module, "list_library_inspector_rows", fail_on_second)

    resp = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "all", "limit": 1},
    )
    assert resp.status_code == 400


def test_inspector_overscan_failure_returns_500(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """When overscan is triggered and the underlying call raises, a 500 is returned."""
    _seed_stale_row(isolated_gallery_root, "overscan_failure.png")

    original = search_module.list_library_inspector_rows
    call_count = {"n": 0}

    def fail_on_second(*args, **kwargs):  # noqa: ANN002, ANN003
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("overscan backend down")
        return original(*args, **kwargs)

    monkeypatch.setattr(search_module, "list_library_inspector_rows", fail_on_second)

    resp = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "all", "limit": 1},
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /api/library/inspector/metadata error paths
# ---------------------------------------------------------------------------


def test_inspector_metadata_unsafe_path_returns_403(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "is_path_safe", lambda _: False)
    resp = isolated_app.get(
        "/api/library/inspector/metadata",
        params={"path": "/etc/passwd"},
    )
    assert resp.status_code == 403


def test_inspector_metadata_unindexed_path_returns_404(isolated_app: TestClient, isolated_gallery_root: Path):
    image = isolated_gallery_root / "unindexed.png"
    image.write_bytes(b"data")
    resp = isolated_app.get(
        "/api/library/inspector/metadata",
        params={"path": str(image)},
    )
    assert resp.status_code == 404


def test_inspector_metadata_failure_returns_500(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "indexed.png"
    image.write_bytes(b"data")

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("metadata backend down")

    monkeypatch.setattr(search_module, "get_library_inspector_metadata", boom)
    resp = isolated_app.get(
        "/api/library/inspector/metadata",
        params={"path": str(image)},
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /api/library/inspector next_cursor branches
# ---------------------------------------------------------------------------


def test_inspector_truncated_with_no_safe_rows_passes_through_cursor(
    isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """When the inspector response is truncated but no safe rows remain after
    filtering, next_cursor passthrough behavior is exercised."""
    fake_data = {
        "rows": [],
        "truncated": True,
        "next_cursor": "opaque-cursor-from-backend",
    }
    monkeypatch.setattr(
        search_module,
        "list_library_inspector_rows",
        lambda *a, **k: fake_data,  # noqa: ANN002, ANN003
    )
    # No stale rows → no overscan
    monkeypatch.setattr(search_module, "cleanup_stale_index", lambda *a, **k: None)  # noqa: ANN002, ANN003

    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 50})
    assert resp.status_code == 200
    data = resp.json()
    assert data["truncated"] is True
    assert data["next_cursor"] == "opaque-cursor-from-backend"
    assert data["has_more"] is True


def test_inspector_not_truncated_clears_cursor(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    """When the inspector response is not truncated, next_cursor is None."""
    fake_data = {
        "rows": [],
        "truncated": False,
        "next_cursor": None,
    }
    monkeypatch.setattr(
        search_module,
        "list_library_inspector_rows",
        lambda *a, **k: fake_data,  # noqa: ANN002, ANN003
    )
    monkeypatch.setattr(search_module, "cleanup_stale_index", lambda *a, **k: None)  # noqa: ANN002, ANN003

    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 50})
    assert resp.status_code == 200
    data = resp.json()
    assert data["truncated"] is False
    assert data["next_cursor"] is None
    assert data["has_more"] is False


# ---------------------------------------------------------------------------
# Regression: register_library on a fresh isolated DB + library_import_paths
# ---------------------------------------------------------------------------


def test_register_library_on_fresh_isolated_db(isolated_metadata_db, isolated_gallery_root):
    """register_library must create a library row and a library_import_paths row
    on a freshly initialised isolated DB — no prior catalog state required."""
    from backend.metadata_store import _connect, register_library

    library = register_library(isolated_gallery_root)

    assert "id" in library
    paths = [ip["path"] for ip in library["import_paths"]]
    assert paths == [str(isolated_gallery_root.resolve())]

    with _connect() as conn:
        lib_row = conn.execute("SELECT id, name FROM libraries WHERE id = ?", (library["id"],)).fetchone()
        assert lib_row is not None, "libraries row must exist"

        import_paths = conn.execute(
            "SELECT path FROM library_import_paths WHERE library_id = ?", (library["id"],)
        ).fetchall()
        assert len(import_paths) >= 1
        assert import_paths[0]["path"] == str(isolated_gallery_root.resolve())
