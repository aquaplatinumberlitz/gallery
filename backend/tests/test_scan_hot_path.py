from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend.metadata_store import CachedDimensions
from backend import indexer, metadata_extract, metadata_store, scan


client = TestClient(app)


def test_api_scan_hot_path_uses_cached_dimensions_without_parsing_or_opening_images(
    tmp_path,
    monkeypatch,
):
    album = tmp_path / "album"
    nested = album / "nested"
    album.mkdir()
    nested.mkdir()
    image_a = album / "a.jpg"
    image_b = album / "b.png"
    image_a.write_bytes(b"not a real jpg")
    image_b.write_bytes(b"not a real png")
    (nested / "cover.jpg").write_bytes(b"not a real nested jpg")

    def fail_extract_metadata(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("scan hot path must not parse image metadata")

    def fail_image_open(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("scan hot path must not open images with PIL")

    background_calls: list[tuple[str, int | None]] = []

    def fake_get_cached_dimensions_for_files(files):
        rows = list(files)
        assert {Path(path).name for path, _mtime, _size in rows} == {"a.jpg", "b.png"}
        return {
            str(Path(path).resolve()): CachedDimensions(width=320, height=240)
            for path, _mtime, _size in rows
        }

    def fake_enqueue_metadata_jobs_from_scan(images, root_path):  # noqa: ANN001
        background_calls.append(("metadata", len(images)))
        return {"staged": len(images), "coalesced": 0, "skipped": 0}

    monkeypatch.setattr(scan, "is_path_safe", lambda _path: True)
    monkeypatch.setattr(scan, "get_cached_dimensions_for_files", fake_get_cached_dimensions_for_files)
    monkeypatch.setattr(scan, "index_file", lambda *args, **kwargs: background_calls.append(("file", None)))
    monkeypatch.setattr(scan, "index_files_from_scan", lambda _folders, images, *args, **kwargs: background_calls.append(("scan", len(images))))
    monkeypatch.setattr(scan, "index_directory_tree", lambda *args, **kwargs: background_calls.append(("tree", None)))
    monkeypatch.setattr(scan, "enqueue_metadata_jobs_from_scan", fake_enqueue_metadata_jobs_from_scan)
    monkeypatch.setattr(metadata_extract, "extract_metadata", fail_extract_metadata)
    monkeypatch.setattr(metadata_store, "extract_metadata", fail_extract_metadata)
    monkeypatch.setattr(Image, "open", fail_image_open)

    response = client.get(
        "/api/scan",
        params={"path": str(album), "image_limit": 1, "image_cursor": 0},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"folders", "images", "next_cursor", "total_images", "index_source"}
    assert data["total_images"] == 2
    assert data["next_cursor"] == 1
    assert len(data["folders"]) == 1
    assert len(data["images"]) == 1
    assert data["images"][0]["name"] == "a.jpg"
    assert data["images"][0]["width"] == 320
    assert data["images"][0]["height"] == 240
    assert ("metadata", 2) in background_calls


def test_api_scan_finishes_active_scan_counter_when_resolve_path_raises(monkeypatch):
    error_client = TestClient(app, raise_server_exceptions=False)

    with indexer._path_stager_lock:
        indexer._active_scan_requests = 0
    monkeypatch.setattr(indexer, "METADATA_INDEXER_ENABLED", True)

    def raise_resolve_error(_path):  # noqa: ANN001
        raise RuntimeError("resolve failed")

    monkeypatch.setattr(scan, "resolve_path", raise_resolve_error)

    response = error_client.get("/api/scan", params={"path": "/boom"})

    assert response.status_code == 500
    assert indexer.get_indexer_runtime_status()["active_scan_requests"] == 0
