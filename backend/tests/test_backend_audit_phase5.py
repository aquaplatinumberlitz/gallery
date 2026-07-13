"""Phase 5 HTTP semantics, runtime cleanup, migration, and diagnostics.

Purpose:
Protect the final backend-audit remediation contracts around cache revalidation,
video ranges, lifespan supervision, schema migration, and public errors.

Guarantees:
* derivative responses revalidate and changed sources receive a new validator
* video ranges clamp at EOF and If-Range supports strong ETags and HTTP dates
* startup failures unwind every started service even when one cleanup fails
* the v1-to-v2 migration backs up first and rolls back exact schema and data
* unexpected failures retain details in logs but expose only a generic response

Run when:
Changing HTTP validators/ranges, FastAPI lifespan startup, SQLite migrations,
or unexpected exception handling.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi import Request

from backend import app as app_module
from backend import metadata_store
from backend.metadata_store import _DB_LOCK, _connect, index_file, register_library
from backend.metadata_store import _schema as schema_module
from tests.conftest import create_test_png


def _catalog_file(path: Path, media_type: str) -> None:
    if metadata_store.get_library_for_path(path) is None:
        register_library(path.parent)
    stat = path.stat()
    assert index_file(
        path,
        path.name,
        path.parent,
        media_type,
        stat.st_mtime,
        stat.st_size,
        64 if media_type == "image" else None,
        64 if media_type == "image" else None,
        "image/png" if media_type == "image" else "video/mp4",
    )


def test_derivative_revalidation_observes_source_change(
    isolated_app,
    isolated_gallery_root: Path,
) -> None:
    image = isolated_gallery_root / "changing.png"
    create_test_png(image, color=(10, 20, 30))
    _catalog_file(image, "image")

    first = isolated_app.get("/api/thumbnail", params={"path": image, "max_long_edge": 128})
    assert first.status_code == 200
    assert "must-revalidate" in first.headers["cache-control"]

    create_test_png(image, color=(30, 20, 10))
    _catalog_file(image, "image")
    second = isolated_app.get(
        "/api/thumbnail",
        params={"path": image, "max_long_edge": 128},
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert second.status_code == 200
    assert second.headers["etag"] != first.headers["etag"]


def test_video_range_clamps_and_if_range_validates(
    isolated_app,
    isolated_gallery_root: Path,
) -> None:
    video = isolated_gallery_root / "range.mp4"
    video.write_bytes(b"0123456789")
    _catalog_file(video, "video")
    full = isolated_app.get("/api/video", params={"path": video})

    clamped = isolated_app.get(
        "/api/video",
        params={"path": video},
        headers={"Range": "bytes=4-999", "If-Range": full.headers["etag"]},
    )
    assert clamped.status_code == 206
    assert clamped.content == b"456789"
    assert clamped.headers["content-range"] == "bytes 4-9/10"

    dated = isolated_app.get(
        "/api/video",
        params={"path": video},
        headers={"Range": "bytes=2-3", "If-Range": full.headers["last-modified"]},
    )
    assert dated.status_code == 206
    assert dated.content == b"23"

    mismatched = isolated_app.get(
        "/api/video",
        params={"path": video},
        headers={"Range": "bytes=2-3", "If-Range": '"stale"'},
    )
    assert mismatched.status_code == 200
    assert mismatched.content == video.read_bytes()


def test_startup_failure_unwinds_all_started_services(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(app_module, "GALLERY_CATALOG_SERVICE_ENABLED", True)
    monkeypatch.setattr(app_module, "GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED", False)
    monkeypatch.setattr(app_module, "GALLERY_SEARCH_INDEXER_ENABLED", False)
    monkeypatch.setattr(app_module.metadata_indexer, "METADATA_INDEXER_ENABLED", False)
    monkeypatch.setattr(app_module, "INTEGRITY_CHECK_ENABLED", False)
    monkeypatch.setattr(app_module, "validate_trusted_proxy_configuration", lambda: None)
    monkeypatch.setattr(app_module, "recover_stale_jobs", lambda: None)
    monkeypatch.setattr(app_module, "start", lambda: events.append("catalog:start"))
    monkeypatch.setattr(app_module, "stop", lambda: events.append("catalog:stop"))
    monkeypatch.setattr(app_module.scheduler, "start", lambda: events.append("derivative:start"))

    def stop_derivative() -> None:
        events.append("derivative:stop")
        raise RuntimeError("stop failed")

    monkeypatch.setattr(app_module.scheduler, "stop", stop_derivative)

    def fail_refresh() -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(app_module, "_start_refresh", fail_refresh)
    monkeypatch.setattr(app_module, "_stop_refresh", lambda: events.append("refresh:stop"))

    async def exercise() -> None:
        with pytest.raises(RuntimeError, match="startup failed"):
            async with app_module._lifespan(app_module.app):
                pass

    asyncio.run(exercise())
    assert events == [
        "catalog:start",
        "derivative:start",
        "refresh:stop",
        "derivative:stop",
        "catalog:stop",
    ]


def test_lifecycle_registry_cleans_partial_start_and_every_reverse_cleanup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import threading

    events: list[str] = []
    stop_thread = threading.Event()
    thread = threading.Thread(target=stop_thread.wait, daemon=True)
    registry = app_module._LifecycleRegistry()

    def partial_start() -> None:
        events.append("partial:start")
        thread.start()
        raise RuntimeError("original startup failure")

    def partial_stop() -> bool:
        events.append("partial:stop")
        stop_thread.set()
        thread.join(timeout=1)
        return not thread.is_alive()

    registry.start("first", lambda: events.append("first:start"), lambda: events.append("first:stop"))
    registry.start("raises", lambda: events.append("raises:start"), lambda: (_ for _ in ()).throw(RuntimeError("stop")))
    registry.start("false", lambda: events.append("false:start"), lambda: events.append("false:stop") or False)
    with pytest.raises(RuntimeError, match="original startup failure"):
        try:
            registry.start("partial", partial_start, partial_stop)
        finally:
            with caplog.at_level(logging.WARNING, logger="backend.app"):
                registry.close()

    assert events == [
        "first:start",
        "raises:start",
        "false:start",
        "partial:start",
        "partial:stop",
        "false:stop",
        "first:stop",
    ]
    assert not thread.is_alive()
    assert "Backend service shutdown incomplete: false" in caplog.text
    assert "Backend service shutdown failed: raises" in caplog.text


def _database_dump(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return "\n".join(conn.iterdump())


def _mark_nanosecond_columns_as_real(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute(
            "UPDATE sqlite_master SET sql = replace(sql, 'mtime_ns INTEGER', 'mtime_ns REAL') "
            "WHERE type = 'table' AND name = 'assets'"
        )
        conn.execute(
            "UPDATE sqlite_master SET sql = replace(sql, 'source_mtime_ns INTEGER', 'source_mtime_ns REAL') "
            "WHERE type = 'table' AND name = 'asset_derivatives'"
        )
        conn.execute("PRAGMA writable_schema=OFF")
        conn.execute("PRAGMA user_version=1")


def test_v2_migration_failure_restores_exact_schema_and_data(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_store.initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute("INSERT INTO libraries(name) VALUES ('migration')")
    _mark_nanosecond_columns_as_real(isolated_metadata_db)
    before = _database_dump(isolated_metadata_db)
    original_execute = schema_module._execute_v2_migration_statement
    statements = 0

    def fail_after_rename(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal statements
        statements += 1
        if statements == 2:
            raise RuntimeError("injected migration failure")
        original_execute(conn, statement)

    monkeypatch.setattr(schema_module, "_execute_v2_migration_statement", fail_after_rename)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        with pytest.raises(RuntimeError, match="injected migration failure"):
            schema_module._migrate_v1_to_v2(conn)

    assert _database_dump(isolated_metadata_db) == before
    backup = isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v1.bak")
    assert backup.exists()
    assert _database_dump(backup) == before


def test_unexpected_error_is_logged_not_disclosed(caplog: pytest.LogCaptureFixture) -> None:
    secret = "/private/catalog/gallery_metadata.db"
    request = Request({"type": "http", "method": "GET", "path": "/api/fail", "headers": []})

    async def exercise():
        with caplog.at_level(logging.ERROR, logger="backend.app"):
            return await app_module.unexpected_error_handler(request, RuntimeError(secret))

    response = asyncio.run(exercise())
    assert response.status_code == 500
    assert secret not in response.body.decode()
    assert b"Internal server error" in response.body
    assert secret in caplog.text


def test_metadata_route_unexpected_error_is_generic(
    isolated_app,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from backend import metadata_parse

    image = isolated_gallery_root / "route-error.png"
    create_test_png(image)
    _catalog_file(image, "image")
    secret = f"sqlite failed at {image}"
    with metadata_parse._metadata_cache_lock:
        metadata_parse._metadata_cache.clear()
        metadata_parse._metadata_inflight.clear()
    monkeypatch.setattr(metadata_parse, "extract_metadata", lambda _path: (_ for _ in ()).throw(RuntimeError(secret)))

    with caplog.at_level(logging.ERROR, logger="backend.metadata_parse"):
        response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 500
    assert response.json() == {"detail": {"error": "server_error", "message": "Internal server error"}}
    assert secret not in response.text
    assert secret in caplog.text
