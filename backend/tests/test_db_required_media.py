"""DB_REQUIRED integration coverage for the media-serving endpoints.

These tests run ``require_media_path_allowed`` through its REAL code path
(no monkeypatching) against ``/api/image`` and ``/api/video``. They lock the
policies surfaced by the cross-audit of commit 5aa630b + Phase 4:

* an indexed active image serves (200) under ``GALLERY_DB_REQUIRED=true``;
* an asset row marked ``offline`` is rejected with ``409 asset_offline``;
* an asset row marked ``deleted_at`` is rejected with ``409 asset_deleted``;
* a path inside a registered library that has NOT been indexed still serves
  (``200``) — Option A: the library boundary is the security boundary and an
  indexed ``assets`` row is not required (see status doc section 3.9);
* a legacy ``'photo'``-typed asset still serves under ``expected_type='image'``
  because ``index_file`` normalizes the type before writing to the ``assets``
  table (regression guard for the photo/image dual vocabulary);
* an unregistered path is rejected with ``409 library_not_registered``;
* a path under an offline library is rejected with ``409 library_offline``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.metadata_store import index_file, register_library, update_library_state
from tests.conftest import create_test_png


def _index_image(path: Path, *, asset_type: str = "image") -> None:
    """Index a single image asset row using the same helper the scanner uses."""
    resolved = str(path.resolve())
    index_file(
        path=resolved,
        name=path.name,
        parent_path=str(path.parent.resolve()),
        type=asset_type,
        mtime=time.time(),
        size=path.stat().st_size,
        width=64,
        height=64,
    )


def _index_video(path: Path) -> None:
    """Index a single video asset row without invoking ffprobe."""
    resolved = str(path.resolve())
    index_file(
        path=resolved,
        name=path.name,
        parent_path=str(path.parent.resolve()),
        type="video",
        mtime=time.time(),
        size=path.stat().st_size,
        width=32,
        height=24,
        mime_type="video/mp4",
        duration_ms=2000,
        codec="mpeg4",
    )


def _mark_asset_offline(db_path: Path, asset_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE assets SET offline = 1 WHERE path = ?",
            (str(asset_path.resolve()),),
        )


def _mark_asset_deleted(db_path: Path, asset_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE assets SET deleted_at = ? WHERE path = ?",
            (time.time(), str(asset_path.resolve())),
        )


def test_indexed_active_image_serves_under_db_required(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """A registered, indexed, active image returns 200 from /api/image."""
    image = isolated_gallery_root / "active.png"
    create_test_png(image)
    register_library(isolated_gallery_root)
    _index_image(image)

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 200
    assert response.content == image.read_bytes()
    assert response.headers["content-type"] == "image/png"


def test_offline_asset_returns_409_under_db_required(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """An asset row marked offline is rejected with 409 asset_offline."""
    image = isolated_gallery_root / "offline.png"
    create_test_png(image)
    register_library(isolated_gallery_root)
    _index_image(image)
    _mark_asset_offline(isolated_metadata_db, image)

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "asset_offline"


def test_deleted_asset_returns_409_via_video_endpoint(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """An asset row marked deleted_at is rejected with 409 asset_deleted on /api/video."""
    # A minimal .mp4 file is enough: require_media_path_allowed raises 409
    # before the endpoint's file-existence/format checks run.
    video = isolated_gallery_root / "deleted.mp4"
    video.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00")
    register_library(isolated_gallery_root)
    _index_video(video)
    _mark_asset_deleted(isolated_metadata_db, video)

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/video", params={"path": str(video)})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "asset_deleted"


def test_unindexed_file_inside_registered_library_serves_under_db_required(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Option A: a file inside a registered library with no assets row still serves.

    The library boundary — not the presence of an indexed asset row — is the
    security boundary. This locks the policy documented in status doc section 3.9.
    """
    image = isolated_gallery_root / "freshly_added.png"
    create_test_png(image)
    register_library(isolated_gallery_root)
    # Note: deliberately NOT calling _index_image — the file is on disk, the
    # library is registered, but no assets row exists for this path.

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 200
    assert response.content == image.read_bytes()


def test_legacy_photo_typed_asset_serves_under_expected_image(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """A 'photo'-typed asset still serves under expected_type='image'.

    Regression guard: index_file normalizes 'photo' to 'image' before writing
    to the assets table (metadata_store._normalize_file_type), so the
    asset_state['type'] != expected_type check in require_media_path_allowed
    must NOT fire. If get_asset_state_for_path is ever pointed at a table that
    stores raw 'photo' values, this test will catch the regression.
    """
    image = isolated_gallery_root / "legacy_photo.png"
    create_test_png(image)
    register_library(isolated_gallery_root)
    _index_image(image, asset_type="photo")  # normalized to 'image' in assets

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 200
    assert response.content == image.read_bytes()

    # Pin the contract: the assets row actually stores 'image', not 'photo'.
    with sqlite3.connect(isolated_metadata_db) as conn:
        row = conn.execute(
            "SELECT type FROM assets WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert row is not None
    assert row[0] == "image"


def test_unregistered_path_returns_409_under_db_required(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """A path with no registered library is rejected with 409 library_not_registered."""
    image = isolated_gallery_root / "unregistered.png"
    create_test_png(image)
    # Note: no register_library() call.

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_not_registered"


def test_offline_library_returns_409_under_db_required(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """A path under a library marked offline is rejected with 409 library_offline."""
    image = isolated_gallery_root / "in_offline_lib.png"
    create_test_png(image)
    library = register_library(isolated_gallery_root)
    _index_image(image)
    update_library_state(int(library["id"]), "offline", last_error="Root path is offline")

    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", True)
    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_offline"


def test_default_mode_serves_unregistered_path(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Under DB_REQUIRED=false, /api/image falls back to PATH_SAFETY_ROOT containment."""
    image = isolated_gallery_root / "default_mode.png"
    create_test_png(image)
    monkeypatch.setattr("backend.config.GALLERY_DB_REQUIRED", False)

    with TestClient(app) as client:
        response = client.get("/api/image", params={"path": str(image)})

    assert response.status_code == 200
    assert response.content == image.read_bytes()
