"""Test that metadata operations do not resurrect offline/deleted assets."""

from __future__ import annotations

import time
from pathlib import Path

from backend.metadata_extract import ExtractedMetadata
from backend.metadata_store import (
    _connect,
    index_file,
    register_library,
    upsert_extracted_metadata,
)
from tests.conftest import create_test_png


def _make_extracted_metadata(path: Path, name: str) -> ExtractedMetadata:
    stat = path.stat()
    return ExtractedMetadata(
        path=str(path.resolve()),
        name=name,
        mtime=stat.st_mtime,
        size=stat.st_size,
        width=80,
        height=60,
        format="PNG",
        mode="RGB",
        has_alpha=0,
        prompt="test prompt",
        negative_prompt="",
        model="",
        sampler="",
        seed="",
        steps=None,
        cfg_scale=None,
        raw_metadata_text="",
        metadata_json="{}",
        indexed_at=stat.st_mtime,
    )


def test_metadata_upsert_does_not_reactivate_offline_asset(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """upsert_extracted_metadata should not resurrect an offline/deleted asset."""
    register_library(isolated_gallery_root)
    asset_path = isolated_gallery_root / "test_offline.png"
    create_test_png(asset_path, size=(80, 60))
    stat = asset_path.stat()

    index_file(asset_path, asset_path.name, asset_path.parent, "photo", stat.st_mtime, stat.st_size, None, None)

    conn = _connect()
    conn.execute(
        "UPDATE assets SET offline = 1, deleted_at = ? WHERE path = ?",
        (time.time(), str(asset_path.resolve())),
    )
    conn.commit()

    meta = _make_extracted_metadata(asset_path, asset_path.name)
    upsert_extracted_metadata(meta)

    row = conn.execute(
        "SELECT offline, deleted_at FROM assets WHERE path = ?",
        (str(asset_path.resolve()),),
    ).fetchone()
    assert row is not None
    assert row["offline"] == 1, "Asset should remain offline after metadata upsert"
    assert row["deleted_at"] is not None, "Asset should remain deleted after metadata upsert"


def test_index_file_reactivates_active_asset(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Normal index operation (reactivate_existing=True default) should reactivate."""
    register_library(isolated_gallery_root)
    asset_path = isolated_gallery_root / "test_active.png"
    create_test_png(asset_path, size=(80, 60))
    stat = asset_path.stat()

    conn = _connect()
    conn.execute(
        "INSERT INTO assets (library_id, path, parent_path, name, type, offline, deleted_at) "
        "VALUES (?, ?, ?, ?, 'image', 1, ?)",
        (
            conn.execute("SELECT id FROM libraries ORDER BY id LIMIT 1").fetchone()[0],
            str(asset_path.resolve()),
            str(asset_path.parent.resolve()),
            asset_path.name,
            time.time(),
        ),
    )
    conn.commit()

    index_file(asset_path, asset_path.name, asset_path.parent, "photo", stat.st_mtime, stat.st_size, None, None)

    row = conn.execute(
        "SELECT offline, deleted_at FROM assets WHERE path = ?",
        (str(asset_path.resolve()),),
    ).fetchone()
    assert row is not None
    assert row["offline"] == 0
    assert row["deleted_at"] is None
