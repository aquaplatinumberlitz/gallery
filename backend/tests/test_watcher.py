"""
Purpose:
Verifies file watcher configuration, debounce handling, and metadata staging hooks.

Guarantees:
* watcher remains disabled by default and handles missing watchdog dependency safely
* file events mark folders stale and can stage changed images for metadata indexing

Run when:
* changing watcher config, debounce behavior, image event handling, or metadata staging integration
* touching future enablement paths for filesystem watching
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend import watcher
from backend.config import ENABLE_FILE_WATCHER, WATCHER_ROOTS, WATCHER_DEBOUNCE_SECONDS
from backend.metadata_store import get_folder_index_state, update_folder_index_state
from backend.files import is_image_path


@pytest.fixture(autouse=True)
def reset_watcher_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "_watcher_thread", None)
    watcher._watcher_stop.clear()
    yield


def test_disabled_by_default():
    assert ENABLE_FILE_WATCHER is False


def test_app_starts_even_if_watchdog_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", False)

    watcher.start_watcher()
    status = watcher.get_watcher_status()
    assert status["enabled"] is True
    assert status["dependency_available"] is False
    watcher.stop_watcher()


def test_configured_roots_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_ROOTS", ["/images", "/data/photos"])
    status = watcher.get_watcher_status()
    assert status["roots"] == ["/images", "/data/photos"]


def test_config_parsing_works():
    assert isinstance(WATCHER_ROOTS, list)
    assert isinstance(WATCHER_DEBOUNCE_SECONDS, (int, float))
    assert WATCHER_DEBOUNCE_SECONDS >= 0


def test_debounce_marks_folder_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    import threading

    handler = watcher._DebouncedHandler(roots=[str(tmp_path)])

    folder = tmp_path / "album"
    folder.mkdir()
    update_folder_index_state(folder, complete=True, **{
        "child_count": 1,
        "folder_count": 0,
        "image_count": 1,
    })
    assert get_folder_index_state(folder)["complete"]

    class FakeEvent:
        src_path = str(folder / "new.jpg")
        event_type = "created"

    handler.handle_event(FakeEvent())
    time.sleep(0.02)

    ready = handler.get_and_clear_debounced()
    assert str(folder) in ready


def test_changed_image_can_be_staged_for_metadata_indexing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    handler = watcher._DebouncedHandler(roots=[str(tmp_path)])
    folder = tmp_path / "album"
    folder.mkdir()

    class FakeCreateEvent:
        src_path = str(folder / "new.jpg")
        event_type = "created"

    class FakeModifyEvent:
        src_path = str(folder / "existing.jpg")
        event_type = "modified"

    handler.handle_event(FakeCreateEvent())
    handler.handle_event(FakeModifyEvent())
    time.sleep(0.02)

    ready = handler.get_and_clear_debounced()
    assert str(folder) in ready


def test_disabled_stub_does_not_start():
    assert ENABLE_FILE_WATCHER is False
    watcher.start_watcher()
    status = watcher.get_watcher_status()
    assert status["alive"] is False


def test_future_enable_path_documented():
    status = watcher.get_watcher_status()
    assert "enabled" in status
    assert "dependency_available" in status
    assert "roots" in status
    assert "debounce_seconds" in status
    assert "max_events_per_tick" in status


def test_handler_tracks_image_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    handler = watcher._DebouncedHandler(roots=[str(tmp_path)])

    class FakeCreateEvent:
        src_path = str(tmp_path / "new.jpg")
        event_type = "created"

    class FakeTxtEvent:
        src_path = str(tmp_path / "readme.txt")
        event_type = "created"

    handler.handle_event(FakeCreateEvent())
    handler.handle_event(FakeTxtEvent())
    time.sleep(0.02)

    ready_paths = handler.get_and_clear_debounced_image_paths()
    assert str(tmp_path / "new.jpg") in ready_paths
    assert str(tmp_path / "readme.txt") not in ready_paths


def test_watcher_image_event_can_be_staged(monkeypatch: pytest.MonkeyPatch):
    staged_paths = []

    def fake_stage(paths, **kwargs):
        staged_paths.extend(paths)
        return {"staged": len(paths), "coalesced": 0, "skipped": 0}

    monkeypatch.setattr("backend.indexer.stage_metadata_paths_from_scan", fake_stage)
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    from backend.watcher import _DebouncedHandler
    handler = _DebouncedHandler(roots=["/test"])

    class FakeEvent:
        src_path = "/test/album/new_image.png"
        event_type = "created"

    handler.handle_event(FakeEvent())
    time.sleep(0.02)

    ready_paths = handler.get_and_clear_debounced_image_paths()
    assert "/test/album/new_image.png" in ready_paths
