"""
Purpose:
Verifies file watcher configuration, debounce handling, and catalog scan queue hooks.

Guarantees:
* watcher is enabled by default and handles missing watchdog dependency safely
* only registered, watch-enabled library roots are monitored
* file events debounce to scoped catalog scan requests

Run when:
* changing watcher config, debounce behavior, image event handling, or catalog trigger routing
* touching future enablement paths for filesystem watching
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from backend import watcher
from backend.config import ENABLE_FILE_WATCHER, WATCHER_DEBOUNCE_SECONDS, WATCHER_ROOTS
from backend.metadata_store import get_folder_index_state, index_file, register_library, update_folder_index_state


@pytest.fixture(autouse=True)
def reset_watcher_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "_watcher_thread", None)
    monkeypatch.setattr(watcher, "_watcher_roots", [])
    watcher._watcher_stop.clear()
    yield


def test_watchdog_dependency_available():
    import importlib.util

    assert importlib.util.find_spec("watchdog") is not None


def test_enabled_by_default():
    assert ENABLE_FILE_WATCHER is True


def test_app_starts_even_if_watchdog_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", False)

    watcher.start_watcher()
    status = watcher.get_watcher_status()
    assert status["enabled"] is True
    assert status["dependency_available"] is False
    watcher.stop_watcher()


def test_configured_roots_filter_registered_libraries(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_ROOTS", ["/images", "/data/photos"])
    monkeypatch.setattr(
        "backend.metadata_store.list_libraries",
        lambda: [
            {"root_path": "/images", "watch_enabled": 1},
            {"root_path": "/data/photos", "watch_enabled": 0},
            {"root_path": "/other", "watch_enabled": 1},
        ],
    )
    status = watcher.get_watcher_status()
    assert status["roots"] == ["/images"]


def test_config_parsing_works():
    assert isinstance(WATCHER_ROOTS, list)
    assert isinstance(WATCHER_DEBOUNCE_SECONDS, (int, float))
    assert WATCHER_DEBOUNCE_SECONDS >= 0


def test_debounce_marks_folder_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    handler = watcher._DebouncedHandler(roots=[str(tmp_path)])

    folder = tmp_path / "album"
    folder.mkdir()
    update_folder_index_state(
        folder,
        complete=True,
        **{
            "child_count": 1,
            "folder_count": 0,
            "image_count": 1,
        },
    )
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


@pytest.mark.parametrize("event_type", ["created", "modified", "deleted"])
def test_uppercase_image_sidecar_events_are_detected_on_case_sensitive_filesystems(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    folder = isolated_gallery_root / "album"
    folder.mkdir()
    register_library(isolated_gallery_root)
    image = folder / "IMAGE.PNG"
    image.write_bytes(b"png")
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 1, 1, "image/png")
    sidecar = folder / "IMAGE.txt"
    if event_type != "deleted":
        sidecar.write_text("Steps: 1", encoding="utf-8")

    event = type(
        "SidecarEvent",
        (),
        {"src_path": str(sidecar), "event_type": event_type, "is_directory": False},
    )()
    handler = watcher._DebouncedHandler(roots=[str(isolated_gallery_root)])
    handler.handle_event(event)
    time.sleep(0.02)
    assert str(folder) in handler.get_and_clear_debounced()


def test_uppercase_image_sidecar_move_detects_source_and_destination(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    folder = isolated_gallery_root / "album"
    folder.mkdir()
    register_library(isolated_gallery_root)
    for stem in ("IMAGE", "MOVED"):
        image = folder / f"{stem}.PNG"
        image.write_bytes(b"png")
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 1, 1, "image/png")

    event = type(
        "SidecarMoveEvent",
        (),
        {
            "src_path": str(folder / "IMAGE.txt"),
            "dest_path": str(folder / "MOVED.txt"),
            "event_type": "moved",
            "is_directory": False,
        },
    )()
    handler = watcher._DebouncedHandler(roots=[str(isolated_gallery_root)])
    handler.handle_event(event)
    time.sleep(0.02)
    assert str(folder) in handler.get_and_clear_debounced()


def test_no_registered_libraries_does_not_start(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.metadata_store.list_libraries", lambda: [])
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


# ---------------------------------------------------------------------------
# _DebouncedHandler.handle_event edge cases
# ---------------------------------------------------------------------------


def test_handle_event_uses_event_type(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeEvent:
        src_path = "/test/file.jpg"
        event_type = "modified"

    handler.handle_event(FakeEvent())
    time.sleep(0.02)
    ready = handler.get_and_clear_debounced()
    assert "/test" in ready


def test_handle_event_falls_back_to_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeEvent:
        path = "/test/file.jpg"
        key = "created"

    handler.handle_event(FakeEvent())
    time.sleep(0.02)
    ready = handler.get_and_clear_debounced()
    assert "/test" in ready


def test_handle_event_properties_raise_exceptions_silently(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class BadEvent:
        @property
        def event_type(self):
            raise RuntimeError("event_type broken")

        @property
        def src_path(self):
            return "/test/folder/file.jpg"

    handler.handle_event(BadEvent())
    time.sleep(0.02)
    ready = handler.get_and_clear_debounced()
    assert "/test/folder" in ready


def test_non_asset_path_is_ignored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeTxtEvent:
        src_path = "/test/readme.txt"
        event_type = "created"

    handler.handle_event(FakeTxtEvent())
    time.sleep(0.02)
    ready_folders = handler.get_and_clear_debounced()
    assert "/test" not in ready_folders


def test_excluded_paths_are_ignored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeCacheEvent:
        src_path = "/test/backend/.cache/thumb.jpg"
        event_type = "created"

    handler.handle_event(FakeCacheEvent())
    time.sleep(0.02)
    assert handler.get_and_clear_debounced() == []


def test_directory_modified_event_is_ignored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeDirModifiedEvent:
        src_path = "/test/album"
        event_type = "modified"
        is_directory = True

    handler.handle_event(FakeDirModifiedEvent())
    time.sleep(0.02)
    assert handler.get_and_clear_debounced() == []


def test_directory_create_event_marks_parent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    handler = watcher._DebouncedHandler(roots=["/test"])

    class FakeDirCreatedEvent:
        src_path = "/test/album"
        event_type = "created"
        is_directory = True

    handler.handle_event(FakeDirCreatedEvent())
    time.sleep(0.02)
    assert "/test" in handler.get_and_clear_debounced()


# ---------------------------------------------------------------------------
# Debounce cleanup
# ---------------------------------------------------------------------------


def test_debounce_returns_ready_folders_after_cutoff(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 2.0)
    handler = watcher._DebouncedHandler(roots=["/test"])

    handler.affected_folders["/test/old"] = time.time() - 10
    handler.affected_folders["/test/new"] = time.time()

    ready = handler.get_and_clear_debounced()
    assert "/test/old" in ready
    assert "/test/new" not in ready


def test_drain_removes_ready_entries(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 2.0)
    handler = watcher._DebouncedHandler(roots=["/test"])

    handler.affected_folders["/test/very_old"] = time.time() - 400
    handler.get_and_clear_debounced()
    assert "/test/very_old" not in handler.affected_folders


def test_recent_entries_remain_pending(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 2.0)
    handler = watcher._DebouncedHandler(roots=["/test"])

    handler.affected_folders["/test/recent"] = time.time()
    handler.get_and_clear_debounced()
    assert "/test/recent" in handler.affected_folders


# ---------------------------------------------------------------------------
# _watcher_loop
# ---------------------------------------------------------------------------


def test_watcher_loop_returns_when_no_watchdog(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", False)
    watcher._watcher_loop()


def test_watcher_loop_schedules_roots_and_queues_catalog_scans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import sys
    from types import ModuleType

    class FakeObserver:
        def __init__(self):
            self.scheduled = []
            self._started = False
            self._stopped = False

        def schedule(self, handler, path, recursive=False):
            self.scheduled.append((path, recursive))

        def start(self):
            self._started = True

        def stop(self):
            self._stopped = True

        def join(self):
            pass

    fake_watchdog = ModuleType("watchdog")
    fake_events = ModuleType("watchdog.events")
    fake_observers = ModuleType("watchdog.observers")

    fake_events.FileSystemEventHandler = type("FileSystemEventHandler", (), {})
    fake_observers.Observer = FakeObserver

    fake_watchdog.events = fake_events
    fake_watchdog.observers = fake_observers

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)

    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "WATCHER_ROOTS", [str(tmp_path)])
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)
    monkeypatch.setattr(watcher, "WATCHER_MAX_EVENTS_PER_TICK", 500)

    queued = []
    monkeypatch.setattr(watcher, "queue_watcher_scan", lambda folder: queued.append(folder))

    def stop_soon():
        watcher._watcher_stop.set()

    t = threading.Timer(0.02, stop_soon)
    t.start()

    watcher._watcher_loop()


def test_watcher_loop_handles_bad_resolve(monkeypatch: pytest.MonkeyPatch):
    import sys
    from types import ModuleType

    class FakeObserver:
        def __init__(self):
            pass

        def schedule(self, handler, path, recursive=False):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

    fake_watchdog = ModuleType("watchdog")
    fake_events = ModuleType("watchdog.events")
    fake_observers = ModuleType("watchdog.observers")

    fake_events.FileSystemEventHandler = type("FileSystemEventHandler", (), {})
    fake_observers.Observer = FakeObserver

    fake_watchdog.events = fake_events
    fake_watchdog.observers = fake_observers

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)

    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "WATCHER_ROOTS", ["/nonexistent_root_xyz"])
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.01)

    def stop():
        watcher._watcher_stop.set()

    t = threading.Timer(0.01, stop)
    t.start()
    watcher._watcher_loop()


# ---------------------------------------------------------------------------
# start_watcher lifecycle
# ---------------------------------------------------------------------------


def test_start_watcher_disabled_noops(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", False)
    monkeypatch.setattr(watcher, "_watcher_thread", None)
    watcher.start_watcher()
    assert watcher._watcher_thread is None


def test_start_watcher_existing_thread_noops(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)

    class FakeAliveThread:
        def is_alive(self):
            return True

    monkeypatch.setattr(watcher, "_watcher_thread", FakeAliveThread())
    watcher.start_watcher()
    assert isinstance(watcher._watcher_thread, FakeAliveThread)


def test_start_watcher_creates_daemon_thread(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)
    monkeypatch.setattr(watcher, "_watcher_thread", None)
    monkeypatch.setattr(watcher, "_watcher_stop", threading.Event())

    from backend import watcher as watcher_mod

    threads = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            threads.append(self)

    monkeypatch.setattr(threading, "Thread", FakeThread)
    monkeypatch.setattr(watcher_mod, "_watcher_loop", lambda: None)
    monkeypatch.setattr(watcher_mod, "_registered_watcher_roots", lambda: ["/registered"])

    watcher_mod.start_watcher()
    assert len(threads) == 1
    assert threads[0].daemon is True
    assert threads[0].name == "gallery-file-watcher"
    assert threads[0].started is True


def test_stop_watcher_sets_stop_and_clears_thread(monkeypatch: pytest.MonkeyPatch):
    e = threading.Event()
    monkeypatch.setattr(watcher, "_watcher_stop", e)
    monkeypatch.setattr(watcher, "_watcher_thread", object())
    assert not e.is_set()

    watcher.stop_watcher()
    assert e.is_set()
    assert watcher._watcher_thread is None


def test_reconcile_watcher_starts_after_roots_appear(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "_registered_watcher_roots", lambda: ["/registered"])

    threads = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            threads.append(self)

        def is_alive(self):
            return self.started

    monkeypatch.setattr(threading, "Thread", FakeThread)

    watcher.reconcile_watcher()

    assert len(threads) == 1
    assert threads[0].name == "gallery-file-watcher"
    assert watcher._watcher_roots == ["/registered"]


def test_reconcile_watcher_restarts_when_roots_change(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(watcher, "ENABLE_FILE_WATCHER", True)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "_registered_watcher_roots", lambda: ["/new"])
    monkeypatch.setattr(watcher, "_watcher_roots", ["/old"])

    class OldThread:
        def __init__(self):
            self.alive = True
            self.joined = False

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.joined = True
            self.alive = False

    old_thread = OldThread()
    monkeypatch.setattr(watcher, "_watcher_thread", old_thread)
    threads = []

    class NewThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            threads.append(self)

        def is_alive(self):
            return self.started

    monkeypatch.setattr(threading, "Thread", NewThread)

    watcher.reconcile_watcher()

    assert old_thread.joined is True
    assert len(threads) == 1
    assert watcher._watcher_roots == ["/new"]


# ---------------------------------------------------------------------------
# Additional edge coverage: handle_event exception, stale cleanup, loop body
# ---------------------------------------------------------------------------


class _StopAfterFirstWait:
    def __init__(self) -> None:
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def wait(self, timeout: float) -> None:
        self._is_set = True

    def set(self) -> None:
        pass


def test_debounce_drain_keeps_overflow_pending(monkeypatch: pytest.MonkeyPatch):
    """A bounded drain removes only selected ready folders."""
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.1)
    handler = watcher._DebouncedHandler(roots=["/test"])
    now = time.time()
    handler.affected_folders = {
        "/test/b": now - 2,
        "/test/a": now - 2,
        "/test/c": now - 1,
    }

    assert handler.get_and_clear_debounced(2) == ["/test/a", "/test/b"]
    assert handler.get_and_clear_debounced(2) == ["/test/c"]


def test_watcher_loop_processes_ready_folders(monkeypatch: pytest.MonkeyPatch):
    """Cover the main loop body ready-folder processing (lines 160-169)."""
    import sys
    from types import ModuleType

    class FakeObserver:
        def __init__(self):
            self._started = False
            self._stopped = False

        def schedule(self, handler, path, recursive=False):
            pass

        def start(self):
            self._started = True

        def stop(self):
            self._stopped = True

        def join(self):
            pass

    fake_watchdog = ModuleType("watchdog")
    fake_events = ModuleType("watchdog.events")
    fake_observers = ModuleType("watchdog.observers")
    fake_events.FileSystemEventHandler = type("FileSystemEventHandler", (), {})
    fake_observers.Observer = FakeObserver
    fake_watchdog.events = fake_events
    fake_watchdog.observers = fake_observers

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.001)
    monkeypatch.setattr(watcher, "WATCHER_MAX_EVENTS_PER_TICK", 5)
    monkeypatch.setattr(watcher, "_registered_watcher_roots", lambda: ["/test"])

    queued = []
    monkeypatch.setattr(watcher, "queue_watcher_scan", lambda folder: queued.append(folder))

    handler = watcher._DebouncedHandler(roots=["/test"])
    handler.affected_folders = {"/test/a": time.time() - 10}
    monkeypatch.setattr(watcher, "_DebouncedHandler", lambda roots: handler)
    monkeypatch.setattr(watcher, "_watcher_stop", _StopAfterFirstWait())

    watcher._watcher_loop()
    assert len(queued) >= 1


def test_watcher_loop_respects_max_events_per_tick(monkeypatch: pytest.MonkeyPatch):
    """Cover the max-events-per-tick break (line 163-164)."""
    import sys
    from types import ModuleType

    class FakeObserver:
        def __init__(self):
            pass

        def schedule(self, handler, path, recursive=False):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

    fake_watchdog = ModuleType("watchdog")
    fake_events = ModuleType("watchdog.events")
    fake_observers = ModuleType("watchdog.observers")
    fake_events.FileSystemEventHandler = type("FileSystemEventHandler", (), {})
    fake_observers.Observer = FakeObserver
    fake_watchdog.events = fake_events
    fake_watchdog.observers = fake_observers

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.001)
    monkeypatch.setattr(watcher, "WATCHER_MAX_EVENTS_PER_TICK", 1)
    monkeypatch.setattr(watcher, "_registered_watcher_roots", lambda: ["/test"])

    queued = []
    monkeypatch.setattr(watcher, "queue_watcher_scan", lambda folder: queued.append(folder))

    handler = watcher._DebouncedHandler(roots=["/test"])
    handler.affected_folders = {"/test/a": time.time() - 10, "/test/b": time.time() - 10}
    monkeypatch.setattr(watcher, "_DebouncedHandler", lambda roots: handler)
    monkeypatch.setattr(watcher, "_watcher_stop", _StopAfterFirstWait())

    watcher._watcher_loop()
    assert len(queued) == 1
    assert "/test/b" in handler.affected_folders


def test_watcher_loop_logs_and_continues_on_exception(monkeypatch: pytest.MonkeyPatch):
    """Cover the exception handler in the loop (line 168-169)."""
    import sys
    from types import ModuleType

    class FakeObserver:
        def __init__(self):
            pass

        def schedule(self, handler, path, recursive=False):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

    fake_watchdog = ModuleType("watchdog")
    fake_events = ModuleType("watchdog.events")
    fake_observers = ModuleType("watchdog.observers")
    fake_events.FileSystemEventHandler = type("FileSystemEventHandler", (), {})
    fake_observers.Observer = FakeObserver
    fake_watchdog.events = fake_events
    fake_watchdog.observers = fake_observers

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)
    monkeypatch.setattr(watcher, "_HAS_WATCHDOG", True)
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.001)
    monkeypatch.setattr(watcher, "WATCHER_MAX_EVENTS_PER_TICK", 5)
    monkeypatch.setattr(watcher, "_registered_watcher_roots", lambda: ["/test"])

    handler = watcher._DebouncedHandler(roots=["/test"])
    handler.affected_folders = {"/test/a": time.time() - 10}
    monkeypatch.setattr(watcher, "_DebouncedHandler", lambda roots: handler)
    monkeypatch.setattr(watcher, "_watcher_stop", _StopAfterFirstWait())
    monkeypatch.setattr(watcher, "queue_watcher_scan", lambda folder: (_ for _ in ()).throw(RuntimeError("boom")))

    watcher._watcher_loop()
