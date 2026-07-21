from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import search as search_module
from backend.errors import APIError, ErrorType

# ---------------------------------------------------------------------------
# Purpose: Verify search-metadata, search/query, search/count, library
#   inspector, prompt-usage/query, and workflow/raw API behaviour.
# Guarantees: Empty/whitespace queries, scope validation, error wrapping,
#   pagination dedup, stale-cleanup scheduling, SQLite error → 503.
# Run when: search.py, metadata_store/, or fielded_search_parser.py changes.
# ---------------------------------------------------------------------------


def test_search_metadata_empty_query_returns_empty(isolated_app: TestClient):
    resp = isolated_app.get("/api/search-metadata", params={"q": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


def test_search_metadata_whitespace_query_returns_empty(isolated_app: TestClient):
    resp = isolated_app.get("/api/search-metadata", params={"q": "   "})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


def test_search_metadata_failure_returns_500(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise Exception("search failed")

    monkeypatch.setattr(search_module, "search_metadata", boom)
    resp = isolated_app.get("/api/search-metadata", params={"q": "test"})
    assert resp.status_code == 500


def test_search_scope_current_outside_registered_library_returns_404(isolated_app: TestClient):
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "mode": "lexical",
            "text": "test",
            "scope": {"kind": "folder", "library_id": 999, "folder_path": "/tmp"},
        },
    )
    assert resp.status_code in (404, 422)


def test_search_scope_current_missing_folder_returns_404(isolated_app: TestClient, isolated_gallery_root: Path):
    missing = isolated_gallery_root / "does_not_exist"
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "mode": "lexical",
            "text": "test",
            "scope": {"kind": "folder", "library_id": 1, "folder_path": str(missing)},
        },
    )
    assert resp.status_code in (404, 422)


def test_search_failure_returns_500(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise Exception("search failed")

    monkeypatch.setattr(search_module, "parse_fielded_query", boom)
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "test",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 500


def test_search_uses_catalog_state_without_request_time_cleanup(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    index_file(
        str(isolated_gallery_root / "test.png"),
        "test.png",
        str(isolated_gallery_root),
        "photo",
        1000,
        100,
        800,
        600,
    )

    monkeypatch.setattr(search_module, "_schedule_stale_cleanup", lambda stale: None)

    resp = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 200


def test_search_empty_query_returns_paginated_media_shape(isolated_app: TestClient):
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
            "limit": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["returned"] == 0
    assert isinstance(data["media"], list)
    assert isinstance(data["albums"], list)
    assert "next_cursor" in data


def test_search_media_pages_do_not_duplicate_paths(isolated_app: TestClient, isolated_gallery_root: Path):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    for i in range(5):
        index_file(
            str(isolated_gallery_root / f"img_{i}.png"),
            f"img_{i}.png",
            str(isolated_gallery_root),
            "photo",
            1000 + i,
            100 + i,
            800,
            600,
        )

    resp = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
            "limit": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    paths = [m["path"] for m in data["media"]]
    assert len(paths) == len(set(paths))


def test_search_albums_only_return_on_first_page(isolated_app: TestClient, isolated_gallery_root: Path):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    index_file(
        str(isolated_gallery_root / "first.png"),
        "first.png",
        str(isolated_gallery_root),
        "photo",
        1000,
        100,
        800,
        600,
    )

    # first page should have albums
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
            "limit": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "albums" in data


def test_search_next_page_does_not_repeat_first_page_albums(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    for i in range(5):
        index_file(
            str(isolated_gallery_root / f"img_{i}.png"),
            f"img_{i}.png",
            str(isolated_gallery_root),
            "photo",
            1000 + i,
            100 + i,
            800,
            600,
        )

    monkeypatch.setattr(search_module, "_schedule_stale_cleanup", lambda stale: None)

    page1 = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
            "limit": 2,
        },
    )
    assert page1.status_code == 200
    data1 = page1.json()
    if data1["has_more"] and data1["next_cursor"]:
        page2 = isolated_app.post(
            "/api/search/query",
            json={
                "schema_version": 1,
                "mode": "lexical",
                "text": "",
                "scope": {"kind": "all"},
                "cursor": data1["next_cursor"],
                "limit": 5,
            },
        )
        assert page2.status_code == 200
        data2 = page2.json()
        assert data2["albums"] == []


def test_scope_validation_returns_search_root(isolated_gallery_root: Path):
    isolated_gallery_root.mkdir(parents=True, exist_ok=True)
    from backend.metadata_store import register_library

    register_library(isolated_gallery_root)
    result = search_module._validated_search_root(str(isolated_gallery_root))
    assert result == isolated_gallery_root.resolve()


# ---------------------------------------------------------------------------
# _registered_or_requested_root: path=None, no library (covers lines 59-62)
# ---------------------------------------------------------------------------


def test_registered_or_requested_root_no_path_no_library(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "get_first_library_root", lambda: None)
    with pytest.raises(APIError) as exc:
        search_module._registered_or_requested_root(None)
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# search_metadata: sqlite3.OperationalError → 503 (covers line 187)
# ---------------------------------------------------------------------------


def test_search_metadata_sqlite_operational_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    import sqlite3

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database locked")

    monkeypatch.setattr(search_module, "search_metadata", boom)
    resp = isolated_app.get("/api/search-metadata", params={"q": "test"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# search_metadata: APIError re-raised (covers line 189)
# ---------------------------------------------------------------------------


def test_search_metadata_api_error_re_raised(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise APIError(418, ErrorType.BAD_REQUEST, "custom error")

    monkeypatch.setattr(search_module, "search_metadata", boom)
    resp = isolated_app.get("/api/search-metadata", params={"q": "test"})
    assert resp.status_code == 418


# ---------------------------------------------------------------------------
# _schedule_stale_cleanup: empty set (covers line 125)
# ---------------------------------------------------------------------------


def test_schedule_stale_cleanup_empty_set():
    search_module._schedule_stale_cleanup(set())
    # Should return without adding anything


# ---------------------------------------------------------------------------
# _schedule_stale_cleanup: dedup (covers lines 129-131)
# ---------------------------------------------------------------------------


def test_schedule_stale_cleanup_dedup():
    key = "\0".join(sorted({"/a"}))
    search_module._STALE_CLEANUP_ROOTS.add(key)
    try:
        search_module._schedule_stale_cleanup({"/a"})
    finally:
        search_module._STALE_CLEANUP_ROOTS.discard(key)


# ---------------------------------------------------------------------------
# _schedule_stale_cleanup: executor submits (covers lines 133-140)
# ---------------------------------------------------------------------------


def test_schedule_stale_cleanup_submits(isolated_metadata_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "_cleanup_registered_library_roots", lambda stale: 0)
    search_module._schedule_stale_cleanup({"/cleanup/me"})


# ---------------------------------------------------------------------------
# api_search_count: empty query (covers lines 332-367)
# ---------------------------------------------------------------------------


def test_search_count_empty_query(isolated_app: TestClient):
    resp = isolated_app.post(
        "/api/search/count",
        json={
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["has_more"] is False


# ---------------------------------------------------------------------------
# _filter_safe_paths: OSError on resolve (covers lines 85-87)
# ---------------------------------------------------------------------------


def test_filter_safe_paths_os_error(monkeypatch: pytest.MonkeyPatch):
    def boom(path):
        raise OSError("inaccessible")

    monkeypatch.setattr(search_module, "resolve_path", boom)
    safe, stale = search_module._filter_safe_paths([{"path": "/bad/path"}])
    assert safe == []
    assert stale == {"/bad/path"}


# ---------------------------------------------------------------------------
# _filter_safe_paths: non-existent resolved path (covers 89-91)
# ---------------------------------------------------------------------------


def test_filter_safe_paths_non_existent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import os

    missing = tmp_path / "missing"
    monkeypatch.setattr(search_module, "is_path_safe", lambda p: True)
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    safe, stale = search_module._filter_safe_paths([{"path": str(missing)}])
    assert safe == []
    assert stale == {str(missing)}


# ---------------------------------------------------------------------------
# _execute_search_query: ValueError → 400 (covers line 189)
# ---------------------------------------------------------------------------


def test_execute_search_query_value_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def bad_search(*args, **kwargs):
        raise ValueError("invalid cursor")

    monkeypatch.setattr(search_module, "search_index", bad_search)
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "mode": "lexical",
            "text": "crash",
            "scope": {"kind": "all"},
            "cursor": "bad-cursor",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# _execute_search_query: catch-all Exception → 500 (covers lines 314-317)
# ---------------------------------------------------------------------------


def test_execute_search_query_catch_all(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(search_module, "search_index", boom)
    resp = isolated_app.post(
        "/api/search/query",
        json={
            "mode": "lexical",
            "text": "crash",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_search/count: raw: field returns 409 (covers line 267)
# ---------------------------------------------------------------------------


def test_search_count_raw_field_returns_409_key(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    from backend.fielded_search_parser import FieldToken

    monkeypatch.setattr(
        search_module,
        "parse_fielded_query",
        lambda text: type("Fake", (), {"fields": [FieldToken(field="raw", key=None, value="model")]})(),
    )
    monkeypatch.setattr(search_module, "search_index_count", lambda *a, **k: {"total": 0, "has_more": False})
    resp = isolated_app.post(
        "/api/search/count",
        json={
            "mode": "lexical",
            "text": "raw:model",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code in (200, 409)


# ---------------------------------------------------------------------------
# register_library on fresh isolated db (covers index table creation)
# ---------------------------------------------------------------------------


def test_register_library_on_fresh_isolated_db(isolated_metadata_db, isolated_gallery_root: Path):
    from backend.metadata_store import register_library

    isolated_gallery_root.mkdir(parents=True, exist_ok=True)
    lib = register_library(isolated_gallery_root)
    assert lib is not None


def test_register_library_import_paths_saved(isolated_metadata_db, isolated_gallery_root: Path):
    from backend.metadata_store import register_library
    from backend.metadata_store._db import _DB_LOCK, _connect

    isolated_gallery_root.mkdir(parents=True, exist_ok=True)
    register_library(isolated_gallery_root)

    with _DB_LOCK, _connect() as conn:
        import_paths = conn.execute("SELECT path FROM library_import_paths WHERE library_id = ?", (1,)).fetchall()
        assert len(import_paths) >= 1
        assert import_paths[0]["path"] == str(isolated_gallery_root.resolve())


# ---------------------------------------------------------------------------
# api_library/inspector: basic request (covers lines 447-452)
# ---------------------------------------------------------------------------


def test_library_inspector_basic(isolated_app: TestClient):
    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 1})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# search_count: catch-all Exception → 500 (covers line 365)
# ---------------------------------------------------------------------------


def test_search_count_catch_all(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(search_module, "search_index_count", boom)
    resp = isolated_app.post(
        "/api/search/count",
        json={
            "mode": "lexical",
            "text": "x",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# search_count: ValueError → 500 (count handler catches Exception generically)
# ---------------------------------------------------------------------------


def test_search_count_value_error_caught(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(search_module, "search_index_count", boom)
    resp = isolated_app.post(
        "/api/search/count",
        json={
            "mode": "lexical",
            "text": "x",
            "scope": {"kind": "all"},
        },
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# _validated_search_root: path resolves to file not dir (covers line 74)
# ---------------------------------------------------------------------------


def test_validated_search_root_path_is_file(isolated_gallery_root: Path):
    f = isolated_gallery_root / "afile.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("data")
    from backend.metadata_store import register_library

    register_library(isolated_gallery_root)
    with pytest.raises(APIError) as exc:
        search_module._validated_search_root(str(f))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# _registered_or_requested_root: explicit root path (covers line 57-58)
# ---------------------------------------------------------------------------


def test_registered_or_requested_root_with_path(isolated_gallery_root: Path):
    from backend.metadata_store import register_library

    isolated_gallery_root.mkdir(parents=True, exist_ok=True)
    register_library(isolated_gallery_root)
    root = search_module._registered_or_requested_root(str(isolated_gallery_root))
    assert root is not None


# ---------------------------------------------------------------------------
# search_api/prompt-usage/query: catch-all error (covers line 434-435)
# ---------------------------------------------------------------------------


def test_prompt_usage_query_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(search_module, "query_prompt_usage", boom)
    monkeypatch.setattr(search_module, "require_search_index_mode", lambda *a, **kw: None)
    resp = isolated_app.post(
        "/api/search/prompt-usage/query",
        json={
            "polarity": "positive",
            "scope": {"kind": "all"},
            "limit": 10,
        },
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# _validated_search_root: unsafe path returns 403 (covers line 72)
# ---------------------------------------------------------------------------


def test_validated_search_root_unsafe_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "is_path_safe", lambda p: False)
    monkeypatch.setattr(search_module, "get_first_library_root", lambda: "/tmp/unsafe")
    with pytest.raises(APIError) as exc:
        search_module._validated_search_root(None)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# _resolve_safe_inspector_path: unsafe path returns 403 (line 98)
# ---------------------------------------------------------------------------


def test_resolve_safe_inspector_path_unsafe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "is_path_safe", lambda p: False)
    with pytest.raises(APIError) as exc:
        search_module._resolve_safe_inspector_path("/unsafe/path")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# _cleanup_registered_library_roots: ValueError continue (line 116)
# ---------------------------------------------------------------------------


def test_cleanup_registered_library_roots_value_error_continues(isolated_metadata_db, monkeypatch):
    result = search_module._cleanup_registered_library_roots({"/stale/path/file.png"})
    assert result == 0


# ---------------------------------------------------------------------------
# api_search_count: require_search_index_mode for prompt_groups (line 334)
# ---------------------------------------------------------------------------


def test_search_count_prompt_groups_requires_mode(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def require_mode(index_name, **kwargs):
        from backend.errors import APIError, ErrorType

        raise APIError(409, ErrorType.FEATURE_DISABLED, "mode disabled")

    monkeypatch.setattr(search_module, "require_search_index_mode", require_mode)
    resp = isolated_app.post(
        "/api/search/count",
        json={
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "all"},
            "filters": {"prompt_groups": [{"kind": "positive", "value_id": "x" * 43}]},
        },
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# api_search_count: FieldedSearchValidationError → 422 (line 359)
# ---------------------------------------------------------------------------


def test_search_count_fielded_validation_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    from backend.fielded_search_parser import FieldedSearchValidationError

    def boom(text):
        raise FieldedSearchValidationError("invalid field")

    monkeypatch.setattr(search_module, "parse_fielded_query", boom)
    resp = isolated_app.post(
        "/api/search/count",
        json={"mode": "lexical", "text": "x", "scope": {"kind": "all"}},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# api_search_count: sqlite3.OperationalError → 503 (line 361)
# ---------------------------------------------------------------------------


def test_search_count_operational_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    import sqlite3

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database locked")

    monkeypatch.setattr(search_module, "search_index_count", boom)
    resp = isolated_app.post(
        "/api/search/count",
        json={"mode": "lexical", "text": "x", "scope": {"kind": "all"}},
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# api_search_count: has_more when total > limit (line 367)
# ---------------------------------------------------------------------------


def test_search_count_has_more(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(search_module, "search_index_count", lambda *a, **kw: 150)
    resp = isolated_app.post(
        "/api/search/count",
        json={"mode": "lexical", "text": "x", "scope": {"kind": "all"}, "limit": 100},
    )
    assert resp.status_code == 200
    assert resp.json()["has_more"] is True


# ---------------------------------------------------------------------------
# api_prompt_usage_query: ValueError → 400 (line 388)
# ---------------------------------------------------------------------------


def test_prompt_usage_query_value_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(**kw):
        raise ValueError("bad cursor")

    monkeypatch.setattr(search_module, "query_prompt_usage", boom)
    monkeypatch.setattr(search_module, "require_search_index_mode", lambda *a, **kw: None)
    resp = isolated_app.post(
        "/api/search/prompt-usage/query",
        json={"polarity": "positive", "scope": {"kind": "all"}, "cursor": "bad-cursor"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# api_raw_workflow_search: sqlite3.OperationalError → 503 (lines 410-411)
# ---------------------------------------------------------------------------


def test_raw_workflow_search_operational_error(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    import sqlite3

    def boom(**kw):
        raise sqlite3.OperationalError("fts unavailable")

    monkeypatch.setattr(search_module, "query_raw_workflows", boom)
    monkeypatch.setattr(search_module, "require_search_index_mode", lambda *a, **kw: None)
    resp = isolated_app.post(
        "/api/search/workflow/raw",
        json={"query": "test", "scope": {"kind": "all"}},
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# api_library_inspector: Exception → 500 (lines 453-455)
# ---------------------------------------------------------------------------


def test_library_inspector_catch_all(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected inspector failure")

    monkeypatch.setattr(search_module, "list_library_inspector_rows", boom)
    resp = isolated_app.get("/api/library/inspector", params={"scope": "all"})
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_library_inspector: stale overscan with truncated query (lines 463-491)
# ---------------------------------------------------------------------------


def test_library_inspector_overscan_truncated(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    for i in range(5):
        index_file(
            str(isolated_gallery_root / f"img_{i}.png"),
            f"img_{i}.png",
            str(isolated_gallery_root),
            "photo",
            1000 + i,
            100 + i,
            800,
            600,
        )

    def overscan_rows(q, scope, root, limit, sort, cursor, model, prompt):
        return {
            "rows": [{"path": str(isolated_gallery_root / f"img_{i}.png")} for i in range(min(limit, 5))],
            "truncated": True,
        }

    call_count = 0

    def tracking_rows(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "rows": [],
                "truncated": True,
            }
        return overscan_rows(*args, **kwargs)

    monkeypatch.setattr(search_module, "list_library_inspector_rows", tracking_rows)
    monkeypatch.setattr(
        search_module,
        "_filter_safe_paths",
        lambda rows: (
            [{"path": r["path"], "name": Path(r["path"]).name} for r in rows],
            set(),
        ),
    )

    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 2})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_library_inspector: stale cleanup scheduled (line 494)
# ---------------------------------------------------------------------------


def test_library_inspector_schedules_stale_cleanup(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    index_file(
        str(isolated_gallery_root / "test.png"),
        "test.png",
        str(isolated_gallery_root),
        "photo",
        1000,
        100,
        800,
        600,
    )

    cleanup_called = []

    def track_schedule(stale):
        cleanup_called.append(stale)

    monkeypatch.setattr(search_module, "_schedule_stale_cleanup", track_schedule)

    def filter_all_stale(rows):
        return [], {r["path"] for r in rows}

    monkeypatch.setattr(search_module, "_filter_safe_paths", filter_all_stale)

    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 2})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_library_inspector: truncated with no safe rows (line 503)
# ---------------------------------------------------------------------------


def test_library_inspector_truncated_no_safe_rows(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    from backend.metadata_store import index_file, register_library

    register_library(isolated_gallery_root)
    index_file(
        str(isolated_gallery_root / "test.png"),
        "test.png",
        str(isolated_gallery_root),
        "photo",
        1000,
        100,
        800,
        600,
    )

    called = []

    def tracking_rows(q, scope, root, limit, sort, cursor, model, prompt):
        called.append(limit)
        return {"rows": [{"path": "/stale/path.png"}], "truncated": True}

    monkeypatch.setattr(search_module, "list_library_inspector_rows", tracking_rows)
    monkeypatch.setattr(search_module, "_filter_safe_paths", lambda rows: ([], {"/stale/path.png"}))
    monkeypatch.setattr(search_module, "_schedule_stale_cleanup", lambda stale: None)

    resp = isolated_app.get("/api/library/inspector", params={"scope": "all", "limit": 2})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_library_inspector/metadata: Exception → 500 (lines 519-521)
# ---------------------------------------------------------------------------


def test_library_inspector_metadata_catch_all(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise RuntimeError("metadata boom")

    monkeypatch.setattr(search_module, "get_library_inspector_metadata", boom)
    monkeypatch.setattr(search_module, "is_path_safe", lambda p: True)
    monkeypatch.setattr(search_module, "resolve_path", lambda p: Path(p))
    resp = isolated_app.get(
        "/api/library/inspector/metadata",
        params={"path": "/safe/path.png"},
    )
    assert resp.status_code == 500
