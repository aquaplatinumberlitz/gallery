"""Phase 6 ready_assets image_metadata join coverage for the status builder.

Verifies that `ready_assets` only counts assets whose `metadata_state='done'`
has a matching current `image_metadata` row by path + mtime_ns + size. Both the
single-scope and admin batch status endpoints exercise the same SQL shape, so
each scenario asserts the behavior through both surfaces.

Purpose:
Cover ready-asset aggregation for scoped and batch catalog status responses.

Guarantees:
Ready asset counts require current image metadata and stay consistent across
single-library and batch status endpoints.

Run when:
Changing metadata freshness joins, ready/not-ready counts, or status SQL.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.metadata_store import _connect, create_library


def _asset_row(
    library_id: int,
    path: Path,
    *,
    parent_path: Path | None = None,
    mtime_ns: int = 1000,
    size: int = 128,
    metadata_state: str = "done",
) -> tuple[Any, ...]:
    resolved = str(path.resolve())
    parent = str((parent_path or path.parent).resolve())
    now = time.time()
    return (
        library_id,
        resolved,
        parent,
        path.name,
        "image",
        mtime_ns,
        size,
        None,
        None,
        now,
        metadata_state,
        0,
        None,
        None,
        None,
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
    width: int = 640,
    height: int = 480,
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


def _enable_metadata_status(monkeypatch) -> None:
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)


def _single_scope_metadata(isolated_app: TestClient, library_id: int) -> dict[str, Any]:
    response = isolated_app.get(f"/api/libraries/{library_id}/status")
    assert response.status_code == 200, response.text
    return response.json()["status"]["metadata"]


def _batch_metadata(isolated_app: TestClient, library_id: int) -> dict[str, Any]:
    response = isolated_app.get("/api/libraries/status")
    assert response.status_code == 200, response.text
    items = {item["library_id"]: item["status"]["metadata"] for item in response.json()["items"]}
    return items[library_id]


def test_ready_assets_counts_asset_with_current_image_metadata(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=1000, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["total_assets"] == 1
    assert single["ready_assets"] == 1
    assert batch["total_assets"] == 1
    assert batch["ready_assets"] == 1


def test_ready_assets_excludes_asset_when_image_metadata_missing(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="done"),
    )

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["total_assets"] == 1
    assert single["ready_assets"] == 0
    assert batch["total_assets"] == 1
    assert batch["ready_assets"] == 0


def test_ready_assets_excludes_asset_with_stale_image_metadata_mtime(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=2000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=1000, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["total_assets"] == 1
    assert single["ready_assets"] == 0
    assert batch["total_assets"] == 1
    assert batch["ready_assets"] == 0
