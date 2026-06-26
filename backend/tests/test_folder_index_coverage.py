"""
Purpose:
Exercise backend/metadata_store/folder_index.py error and edge-case branches for
warm folder listing, scan result indexing, and folder state helpers so backend
line coverage stays above the release threshold.

Guarantees:
* update_folder_index_state and get_folder_index_state handle DB exceptions.
* get_warm_folder_listing returns None when listing is disabled, the path does
  not resolve, or the folder has not been indexed.
* _scan_folder_counts skips dot-files and handles OSError from scandir.
* index_files_from_scan handles empty paths, SQLite errors, and updates folder
  state when scan_folder_path is provided.

Run when:
* changing folder_index.py exception handling, warm listing guards, or
  index_files_from_scan error paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.metadata_store import folder_index


def test_update_folder_index_state_exception_on_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(folder_index, "_initialize_database", lambda: None)

    def broken_connect(**kwargs):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(folder_index, "_connect", broken_connect)
    result = folder_index.update_folder_index_state("/tmp", dir_mtime_ns=12345)
    assert result is False


def test_get_folder_index_state_exception_on_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(folder_index, "_initialize_database", lambda: None)

    def broken_connect(**kwargs):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(folder_index, "_connect", broken_connect)
    result = folder_index.get_folder_index_state("/tmp")
    assert result is None


def test_get_warm_folder_listing_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(folder_index, "_warm_indexed_listing_enabled", lambda: False)
    result = folder_index.get_warm_folder_listing("/tmp")
    assert result is None


def test_get_warm_folder_listing_oserror_on_resolve():
    result = folder_index.get_warm_folder_listing("/dev/null/../nonexistent_sibling_xyz")
    assert result is None


def test_get_warm_folder_listing_nonexistent_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(folder_index, "_warm_indexed_listing_enabled", lambda: True)
    missing = tmp_path / "missing"
    result = folder_index.get_warm_folder_listing(missing)
    assert result is None


def test_scan_folder_counts_skips_dot_files(tmp_path: Path):
    d = tmp_path / "scan_counts"
    d.mkdir()
    (d / ".hidden").write_text("skip me")
    (d / "visible.txt").write_text("visible")
    result = folder_index._scan_folder_counts(d)
    assert result["child_count"] == 1
    assert result["image_count"] == 0


def test_scan_folder_counts_handles_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import os

    def fail_scandir(_path):
        raise OSError("permission denied")

    monkeypatch.setattr(os, "scandir", fail_scandir)
    result = folder_index._scan_folder_counts(tmp_path)
    assert result == {"child_count": 0, "folder_count": 0, "image_count": 0}


def test_index_files_from_scan_skips_empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(folder_index, "_file_index_index_file", lambda *a, **kw: calls.append(a))
    result = folder_index.index_files_from_scan(
        [{"path": "", "name": "empty"}],
        [],
    )
    assert result == 0
    assert len(calls) == 0


def test_index_files_from_scan_handles_sqlite_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sqlite3

    monkeypatch.setattr(
        folder_index, "_file_index_path_value", lambda item, key, default=None: str(tmp_path / "test.png")
    )
    monkeypatch.setattr(
        folder_index, "_file_index_index_file", lambda *a, **kw: (_ for _ in ()).throw(sqlite3.Error("db locked"))
    )
    result = folder_index.index_files_from_scan(
        [{"path": str(tmp_path / "test.png")}],
        [],
    )
    assert result == 0


def test_index_files_from_scan_updates_folder_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        folder_index, "_file_index_path_value", lambda item, key, default=None: str(tmp_path / "test.png")
    )
    monkeypatch.setattr(folder_index, "_file_index_index_file", lambda *a, **kw: True)
    monkeypatch.setattr(folder_index, "_file_index_normalize_file_type", lambda t: t)

    update_calls = []
    monkeypatch.setattr(folder_index, "update_folder_index_state", lambda *a, **kw: update_calls.append((a, kw)))

    result = folder_index.index_files_from_scan(
        [{"path": str(tmp_path / "test.png"), "name": "test.png", "type": "image"}],
        [],
        scan_folder_path=tmp_path,
    )
    assert result == 1
    assert len(update_calls) == 1
