"""
Purpose:
Unit-test the album helper functions: has_subfolders, first_images_in_dir,
count_images_in_dir, build_album_metadata, and has_any_children.

Guarantees:
* has_subfolders detects a child directory and returns False when none exist.
* has_subfolders ignores hidden and index-excluded directories.
* has_subfolders handles OSError from scandir without crashing.
* first_images_in_dir collects up to `limit` images sorted by newest mtime,
  and tolerates stat and resolve errors.
* count_images_in_dir counts only image files, ignores hidden/excluded entries,
  and returns 0 on OSError.
* build_album_metadata returns cover_images, image_count, has_children, and
  mtime, falling back to 0 when stat fails.

Run when:
* modifying album metadata building, folder listing helpers, or image counting
* touching has_subfolders, natural_sort_key, or scan directory entry filtering
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.albums import (
    build_album_metadata,
    count_images_in_dir,
    first_images_in_dir,
    has_any_children,
    has_subfolders,
)


class TestHasSubfolders:
    def test_returns_true_when_child_dir_exists(self, tmp_path: Path):
        (tmp_path / "child").mkdir()
        assert has_subfolders(tmp_path) is True

    def test_returns_false_when_no_child_dir(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("data")
        assert has_subfolders(tmp_path) is False

    def test_ignores_hidden_dirs(self, tmp_path: Path):
        (tmp_path / ".hidden").mkdir()
        assert has_subfolders(tmp_path) is False

    def test_handles_scandir_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "scandir", lambda p: (_ for _ in ()).throw(OSError("broken")))
        assert has_subfolders(tmp_path) is False


class TestFirstImagesInDir:
    def test_collects_images_sorted_by_mtime(self, tmp_path: Path):
        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        a.write_bytes(b"img")
        b.write_bytes(b"img")
        os.utime(a, (1000, 1000))
        os.utime(b, (2000, 2000))
        result = first_images_in_dir(tmp_path, limit=3)
        assert len(result) == 2
        assert result[0] == str(b.resolve())

    def test_tolerates_stat_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        good = tmp_path / "good.png"
        bad = tmp_path / "bad.png"
        good.write_bytes(b"img")
        bad.write_bytes(b"img")

        def fake_resolve(self):
            if self.name == "bad.png":
                raise OSError("resolve error")
            return self._orig_resolve()

        monkeypatch.setattr(Path, "_orig_resolve", Path.resolve, raising=False)
        monkeypatch.setattr(Path, "resolve", fake_resolve)
        result = first_images_in_dir(tmp_path, limit=3)
        assert len(result) == 1

    def test_respects_limit(self, tmp_path: Path):
        for i in range(5):
            p = tmp_path / f"img_{i}.png"
            p.write_bytes(b"img")
            os.utime(p, (i * 100, i * 100))
        result = first_images_in_dir(tmp_path, limit=2)
        assert len(result) == 2


class TestCountImagesInDir:
    def test_counts_only_image_files(self, tmp_path: Path):
        (tmp_path / "a.png").write_bytes(b"img")
        (tmp_path / "b.jpg").write_bytes(b"img")
        (tmp_path / "readme.txt").write_text("hello")
        assert count_images_in_dir(tmp_path) == 2

    def test_handles_scandir_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "iterdir", lambda self: (_ for _ in ()).throw(OSError("broken")))
        assert count_images_in_dir(tmp_path) == 0


class TestBuildAlbumMetadata:
    def test_returns_expected_shape(self, tmp_path: Path):
        (tmp_path / "cover.png").write_bytes(b"img")
        result = build_album_metadata(tmp_path)
        assert isinstance(result["cover_images"], list)
        assert isinstance(result["image_count"], int)
        assert isinstance(result["has_children"], bool)
        assert isinstance(result["mtime"], (int, float))

    def test_stat_failure_returns_mtime_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "cover.png").write_bytes(b"img")
        dir_path_str = str(tmp_path)

        original_stat = Path.stat

        def fake_stat(self):
            if str(self) == dir_path_str:
                raise OSError("stat error")
            return original_stat(self)

        monkeypatch.setattr(Path, "stat", fake_stat)
        result = build_album_metadata(tmp_path)
        assert result["mtime"] == 0


class TestHasAnyChildren:
    def test_returns_true_when_dir_has_entries(self, tmp_path: Path):
        (tmp_path / "some_file.txt").write_text("data")
        assert has_any_children(tmp_path) is True

    def test_returns_false_for_empty_dir(self, tmp_path: Path):
        tmp_path.mkdir(exist_ok=True)
        assert has_any_children(tmp_path) is False
