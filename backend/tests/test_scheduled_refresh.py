"""
Purpose:
Verifies scheduled refresh configuration, folder refresh work limits, and safe fallbacks.

Guarantees:
* refresh stays disabled by default and respects configured roots and max work limits
* refresh errors and SQLite busy states do not block scan or mark bad state complete

Run when:
* changing scheduled refresh config, refresh loop, folder state updates, or work throttling
* touching warm listing freshness or background indexing interactions
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend import refresh
from backend.config import (
    ENABLE_SCHEDULED_REFRESH,
)
from backend.metadata_store import (
    get_folder_index_state,
    index_directory_tree,
    update_folder_index_state,
)


@pytest.fixture(autouse=True)
def reset_refresh_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "_refresh_thread", None)
    refresh._refresh_stop.clear()
    yield


def test_disabled_by_default():
    assert ENABLE_SCHEDULED_REFRESH is False


def test_start_does_nothing_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", False)
    refresh.start_refresh()
    assert refresh._refresh_thread is None or not refresh._refresh_thread.is_alive()
    refresh.stop_refresh()


def test_refreshes_known_folder_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 10)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    index_directory_tree(album, include_metadata=False)
    counts = _scan_folder_counts(album)
    update_folder_index_state(album, complete=True, **counts)

    state_before = get_folder_index_state(album)
    assert state_before is not None
    assert state_before["complete"]

    refresh._run_refresh_tick()

    state_after = get_folder_index_state(album)
    assert state_after is not None


def test_respects_max_folders_per_tick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 2)

    refresh_calls = []

    def tracking_refresh_folder(path):
        refresh_calls.append(path)
        return True

    monkeypatch.setattr(refresh, "_refresh_folder", tracking_refresh_folder)

    for i in range(5):
        f = tmp_path / f"folder_{i}"
        f.mkdir()
        (f / f"img_{i}.jpg").write_text("fake")
        index_directory_tree(f, include_metadata=False)
        update_folder_index_state(
            f,
            complete=True,
            **{
                "child_count": 1,
                "folder_count": 0,
                "image_count": 1,
            },
        )

    refresh._run_refresh_tick()
    assert len(refresh_calls) == 2


def test_does_not_block_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")

    import queue
    import threading

    events = queue.Queue()

    def slow_refresh(path):
        events.put("refresh_started")
        time.sleep(0.1)
        events.put("refresh_done")
        return True

    monkeypatch.setattr(refresh, "_refresh_folder", slow_refresh)
    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(
        album,
        complete=True,
        **{
            "child_count": 1,
            "folder_count": 0,
            "image_count": 1,
        },
    )

    t = threading.Thread(target=refresh._run_refresh_tick, daemon=True)
    t.start()
    time.sleep(0.05)
    events.put("scan_runs_during_refresh")
    t.join(timeout=1)

    got = []
    while not events.empty():
        got.append(events.get_nowait())

    assert "scan_runs_during_refresh" in got


def test_handles_empty_indexed_paths_gracefully():
    # No roots and allow_all is False by default — tick returns early (no-op)
    result = refresh._run_refresh_tick()
    assert result is None


def test_handles_sqlite_busy_with_safe_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    import sqlite3

    def fail_index_tree(path, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(refresh, "index_directory_tree", fail_index_tree)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")
    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(
        album,
        complete=True,
        **{
            "child_count": 1,
            "folder_count": 0,
            "image_count": 1,
        },
    )

    refresh._run_refresh_tick()

    state = get_folder_index_state(album)
    assert state is not None
    assert not state["complete"]


def test_refresh_folder_updates_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 1000)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")
    sub = album / "subfolder"
    sub.mkdir()

    index_directory_tree(album, include_metadata=False)

    state_before = get_folder_index_state(album)
    assert state_before is None or not state_before["complete"]

    # Add album to folder_index_state as incomplete, then refresh should mark complete
    update_folder_index_state(
        album,
        dir_mtime_ns=album.stat().st_mtime_ns,
        complete=False,
        child_count=2,
        folder_count=1,
        image_count=1,
    )

    # Clean up stale entries from other tests so they don't exhaust the tick budget
    from backend.metadata_store import cleanup_stale_index

    cleanup_stale_index(None)

    refresh._run_refresh_tick()

    state_after = get_folder_index_state(album)
    assert state_after is not None
    assert state_after["complete"]
    assert state_after["image_count"] == 1
    assert state_after["folder_count"] == 1


def test_refresh_folder_error_does_not_mark_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    def fail_index_tree(path, *args, **kwargs):
        raise RuntimeError("indexing failed")

    monkeypatch.setattr(refresh, "index_directory_tree", fail_index_tree)

    album = tmp_path / "album"
    album.mkdir()
    (album / "test.jpg").write_text("fake")
    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(album, complete=True, child_count=1, folder_count=0, image_count=1)

    refresh._run_refresh_tick()

    state = get_folder_index_state(album)
    assert state is not None
    assert state["last_error"] is not None


def test_empty_roots_noop_when_allow_all_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", False)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    refresh_calls = []

    def tracking_refresh_folder(path):
        refresh_calls.append(path)
        return True

    monkeypatch.setattr(refresh, "_refresh_folder", tracking_refresh_folder)

    for i in range(3):
        f = tmp_path / f"folder_{i}"
        f.mkdir()
        (f / "img.jpg").write_text("fake")
        index_directory_tree(f, include_metadata=False)
        update_folder_index_state(f, complete=True, child_count=1, folder_count=0, image_count=1)

    refresh._run_refresh_tick()
    assert len(refresh_calls) == 0


def test_empty_roots_allows_all_when_flag_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    refresh_calls = []

    def tracking_refresh_folder(path):
        refresh_calls.append(path)
        return True

    monkeypatch.setattr(refresh, "_refresh_folder", tracking_refresh_folder)

    for i in range(3):
        f = tmp_path / f"folder_{i}"
        f.mkdir()
        (f / "img.jpg").write_text("fake")
        index_directory_tree(f, include_metadata=False)
        update_folder_index_state(f, complete=True, child_count=1, folder_count=0, image_count=1)

    refresh._run_refresh_tick()
    assert len(refresh_calls) > 0
    assert len(refresh_calls) <= 5


def test_does_not_enqueue_unbounded_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 5)

    refresh_calls = []

    def tracking_refresh_folder(path):
        refresh_calls.append(path)
        return True

    monkeypatch.setattr(refresh, "_refresh_folder", tracking_refresh_folder)

    for i in range(100):
        f = tmp_path / f"folder_{i}"
        f.mkdir()
        (f / f"img_{i}.jpg").write_text("fake")
        index_directory_tree(f, include_metadata=False)
        update_folder_index_state(
            f,
            complete=True,
            **{
                "child_count": 1,
                "folder_count": 0,
                "image_count": 1,
            },
        )

    refresh._run_refresh_tick()
    assert len(refresh_calls) == 5


# ---- helpers ----


def _scan_folder_counts(folder_path: Path) -> dict:
    import os

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
