"""
Purpose:
Verifies folder count helpers used by refresh and warm listing state.

Guarantees:
* child, folder, and image counts match filesystem contents for warm listing bookkeeping
* warm listing avoids unnecessary folder-count scans on the hot path

Run when:
* changing _scan_folder_counts or warm listing completeness checks
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_refresh_imports_scan_folder_counts():
    from backend.metadata_store import _scan_folder_counts

    assert callable(_scan_folder_counts)


def test_scan_folder_counts_behavior(tmp_path: Path):
    from backend.metadata_store import _scan_folder_counts

    root = tmp_path / "root"
    root.mkdir()
    (root / "image1.png").write_text("fake")
    (root / "image2.jpg").write_text("fake")
    (root / "notes.txt").write_text("not an image")
    (root / "subfolder").mkdir()

    counts = _scan_folder_counts(root)

    assert counts["folder_count"] == 1
    assert counts["image_count"] == 2
    # notes.txt is counted as a child but not as an image
    assert counts["child_count"] == 4


def test_warm_path_does_not_call_scan_folder_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.metadata_store.ENABLE_WARM_INDEXED_LISTING", True)

    from backend.metadata_store import (
        _scan_folder_counts,
        get_warm_folder_listing,
        index_directory_tree,
        update_folder_index_state,
    )

    album = tmp_path / "album"
    album.mkdir()
    (album / "img.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    called = []

    def raiser(*args, **kwargs):
        called.append(1)
        raise RuntimeError("_scan_folder_counts must not be called on warm path")

    monkeypatch.setattr("backend.metadata_store._scan_folder_counts", raiser)

    result = get_warm_folder_listing(album, limit=10, media_cursor=0)
    assert result is not None
    assert result["index_source"] == "warm_db"
    assert len(called) == 0
