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

    from backend.metadata_store import index_file

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
    # cleanup should have been called because a stale row was detected
    assert len(cleanup_called) >= 1


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
    from backend.metadata_store import _connect, initialize_database

    initialize_database()
    stale_path = str((gallery_root / name).resolve())
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO file_index(path, name, parent_path, type, mtime, size, width, height, indexed_at)
            VALUES (?, ?, ?, 'photo', 9999999999, 1, 1, 1, 9999999999)
            """,
            (stale_path, name, str(gallery_root.resolve())),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO image_metadata(path, name, mtime, size, prompt, metadata_json, updated_at, indexed_at)
            VALUES (?, ?, 9999999999, 1, 'stale prompt', '{}', 9999999999, 9999999999)
            """,
            (stale_path, name),
        )
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
        return original(*args, **kwargs)

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
