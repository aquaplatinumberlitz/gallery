"""Catalog and lifecycle coverage for the durable derivative scheduler."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler, derivative_variant
from backend.metadata_store import get_asset_folder_listing, index_file, list_libraries
from tests.conftest import create_test_png


def _catalog_image(root: Path) -> tuple[Path, int]:
    image = root / "source.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, 80, 60)
    listing = get_asset_folder_listing(root)
    assert listing is not None
    return image, listing["images"][0].asset_id


def test_schedule_coalesces_jobs_and_reports_library_status(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    image, asset_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=99, quota_bytes=1024)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]

    assert scheduler.worker_count == 8
    assert scheduler.find_asset_id(image) == asset_id
    assert scheduler.get_asset_path(asset_id) == image
    assert scheduler.find_asset_id(isolated_gallery_root / "missing.png") is None
    assert scheduler.get_asset_path(999_999) is None
    assert scheduler.get_derivative_status(asset_id, "thumbnail", str(thumbnail["name"])) is None

    derivative_id = scheduler.schedule_derivative(
        asset_id,
        "thumbnail",
        str(thumbnail["name"]),
        priority=3,
    )
    assert scheduler.get_derivative_status(asset_id, "thumbnail", str(thumbnail["name"])) == "queued"
    assert (
        scheduler.schedule_derivative(
            asset_id,
            "thumbnail",
            str(thumbnail["name"]),
            priority=-5,
        )
        == derivative_id
    )

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT priority FROM derivative_jobs").fetchone()[0] == 0

    library_id = list_libraries()[0]["id"]
    status = scheduler.library_status(library_id)
    assert status == {
        "library_id": library_id,
        "total_assets": 1,
        "ready_derivatives": 0,
        "expected_derivatives": sum(len(variants) for variants in DERIVATIVE_VARIANTS.values()),
        "quota_bytes": 1024,
        "quota_used_bytes": 0,
        "quota_utilization": 0.0,
    }
    with pytest.raises(KeyError):
        scheduler.library_status(999_999)
    with pytest.raises(KeyError):
        scheduler.schedule_derivative(999_999, "thumbnail", "thumb_512")
    with pytest.raises(ValueError, match="Unsupported derivative kind"):
        scheduler.schedule_derivative(asset_id, "unknown", "unknown")


def test_ready_derivative_lookup_warming_and_clear(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import backend.derivative_scheduler as scheduler_module

    image, asset_id = _catalog_image(isolated_gallery_root)
    cache_root = tmp_path / "derivative-cache"
    cache_file = cache_root / "files" / "ready.webp"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"ready derivative")
    monkeypatch.setattr(scheduler_module, "THUMBNAIL_CACHE_DIR", cache_root)

    scheduler = DerivativeScheduler(quota_bytes=1024)
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    variant = str(thumbnail["name"])
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", variant)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ? WHERE id = ?",
            (str(cache_file), cache_file.stat().st_size, derivative_id),
        )

    ready = scheduler.get_ready_derivative(asset_id, "thumbnail", variant)
    assert ready is not None
    assert ready["id"] == derivative_id
    assert scheduler.get_derivative_status(asset_id, "thumbnail", variant) == "ready"
    assert scheduler.get_ready_derivative(999_999, "thumbnail", variant) is None

    warmed = scheduler.warm_library(list_libraries()[0]["id"])
    assert warmed == {
        "assets": 1,
        "derivatives_considered": sum(len(variants) for variants in DERIVATIVE_VARIANTS.values()),
    }

    scheduler.acquire_serving(str(cache_file))
    cleared = scheduler.clear_all()
    assert cleared["catalog_entries_cleared"] == sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
    assert cleared["files_deleted"] == 0
    assert cache_file.exists()
    scheduler.release_serving(str(cache_file))


def test_derivative_variant_uses_named_and_custom_variants():
    thumbnail = DERIVATIVE_VARIANTS["thumbnail"][0]
    assert (
        derivative_variant(
            "thumbnail",
            int(thumbnail["max_long_edge"]),
            int(thumbnail["quality"]),
            "webp",
        )
        == thumbnail["name"]
    )
    assert derivative_variant("thumbnail", 333, 71, "jpeg") == "edge-333-q-71-jpeg"
