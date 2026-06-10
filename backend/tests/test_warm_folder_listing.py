from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import ENABLE_WARM_INDEXED_LISTING
from backend.metadata_store import (
    get_warm_folder_listing,
    update_folder_index_state,
    index_directory_tree,
    index_file,
    initialize_database,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_warm_listing_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.metadata_store.ENABLE_WARM_INDEXED_LISTING", True)
    monkeypatch.setattr("backend.scan.ENABLE_WARM_INDEXED_LISTING", True)
    yield


def test_warm_complete_folder_returns_from_sqlite(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    for i in range(5):
        (album / f"img_{i}.jpg").write_text("fake")
    (album / "subfolder").mkdir()

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is not None
    assert result["total_images"] == 5
    assert len(result["images"]) == 5
    assert len(result["folders"]) == 1
    assert result["index_source"] == "warm_db"


def test_warm_path_does_not_call_scandir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    scandir_calls = []

    def fail_scandir(*args, **kwargs):
        scandir_calls.append(1)
        raise AssertionError("warm path must not call os.scandir")

    monkeypatch.setattr(os, "scandir", fail_scandir)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(album, complete=True, child_count=1, folder_count=0, image_count=1)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is not None
    assert result["total_images"] == 1
    assert len(scandir_calls) == 0


def test_missing_folder_index_state_falls_back(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is None


def test_incomplete_folder_falls_back(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=False, **counts)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is None


def test_stale_dir_mtime_ns_falls_back(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    old = _get_folder_index_state(album)
    old_mtime = old["dir_mtime_ns"]
    update_folder_index_state(
        album,
        complete=True,
        dir_mtime_ns=old_mtime - 1,
        **counts,
    )

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is None


def test_deleted_missing_folder_preserves_error_behavior(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    import shutil
    shutil.rmtree(album)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is None


def test_sort_order_matches_direct_scan(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    for name in ["z.jpg", "a.jpg", "m.jpg"]:
        (album / name).write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is not None
    names = [img.name for img in result["images"]]
    assert names == sorted(names)


def test_response_shape_compatible(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    result = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert result is not None
    assert set(result) == {"folders", "images", "next_cursor", "total_images", "index_source"}

    for img in result["images"]:
        assert set(img.model_dump()) == {
            "name", "path", "type", "has_children", "cover_images", "mtime", "image_count", "width", "height",
        }


def test_cold_path_unchanged_when_warm_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.metadata_store.ENABLE_WARM_INDEXED_LISTING", False)
    monkeypatch.setattr("backend.scan.ENABLE_WARM_INDEXED_LISTING", False)
    monkeypatch.setattr("backend.scan.is_path_safe", lambda _: True)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    response = client.get(
        "/api/scan",
        params={"path": str(album), "image_limit": 10, "image_cursor": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_images"] == 1
    assert data["index_source"] == "direct_scan"


def test_pagination_matches_direct_scan(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()
    for i in range(20):
        (album / f"img_{i:03d}.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    page1 = get_warm_folder_listing(album, offset=0, limit=10, image_limit=10)
    assert page1 is not None
    assert len(page1["images"]) == 10
    assert page1["next_cursor"] == 10

    page2 = get_warm_folder_listing(album, offset=10, limit=10, image_limit=10)
    assert page2 is not None
    assert len(page2["images"]) == 10
    assert page2["next_cursor"] is None


def test_api_scan_uses_warm_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.scan.is_path_safe", lambda _: True)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    scandir_calls = []

    original_scandir = os.scandir
    def tracking_scandir(path):
        scandir_calls.append(path)
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", tracking_scandir)

    response = client.get(
        "/api/scan",
        params={"path": str(album), "image_limit": 10, "image_cursor": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_images"] == 1
    assert data.get("index_source") == "warm_db"


# ---- helpers ----

def _scan_folder_counts(folder_path: Path) -> dict:
    folders = 0
    images = 0
    total = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.name.startswith("."):
                continue
            total += 1
            try:
                if entry.is_dir():
                    folders += 1
                elif entry.is_file():
                    images += 1
            except OSError:
                pass
    except OSError:
        pass
    return {"child_count": total, "folder_count": folders, "image_count": images}


def _get_folder_index_state(folder_path: Path) -> dict | None:
    from backend.metadata_store import get_folder_index_state
    return get_folder_index_state(folder_path)
