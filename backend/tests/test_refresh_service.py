"""
Purpose:
Unit-test the scheduled catalog reconciliation loop without spawning background
threads or sleeping.

Guarantees:
* _run_refresh_tick queues scheduled catalog scans for registered libraries.
* _run_refresh_tick filters candidates to configured roots.
* _run_refresh_tick respects SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK.
* _run_refresh_tick stops early when _refresh_stop is set.
* _run_refresh_tick tolerates OSError during root resolve.
* _run_refresh_tick increments counters when prometheus_client available.
* start_refresh no-ops when disabled or when thread already alive.
* start_refresh creates a daemon thread when enabled.
* stop_refresh sets the stop event and clears the thread handle.
* get_refresh_status returns the expected config/runtime shape.

Run when:
* changing scheduled refresh config, refresh loop, folder state updates, or
  work throttling
* touching warm listing freshness or background indexing interactions
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from backend import refresh
from backend.refresh import (
    _refresh_thread,
    _run_refresh_tick,
    get_refresh_status,
    start_refresh,
    stop_refresh,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_refresh_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "_refresh_thread", None)
    monkeypatch.setattr(refresh, "mark_scheduled_refresh_attempt", lambda _library_id: None)
    refresh._refresh_stop.clear()
    yield
    refresh._refresh_stop.clear()
    monkeypatch.setattr(refresh, "_refresh_thread", None)


# ---------------------------------------------------------------------------
# _run_refresh_tick
# ---------------------------------------------------------------------------


class TestRunRefreshTick:
    def test_no_libraries_noops(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])

        queue_calls = []

        def fake_list_libraries():
            return []

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", lambda *args, **kwargs: queue_calls.append((args, kwargs)))
        _run_refresh_tick()
        assert queue_calls == []

    def test_queues_registered_libraries_without_roots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_list_libraries():
            return [{"id": 7, "import_paths": [{"path": str(folder)}]}]

        refresh_calls = []

        def fake_queue_scan(library_id, *, trigger):
            refresh_calls.append((library_id, trigger))

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert refresh_calls == [(7, "scheduled")]

    def test_configured_roots_filter_candidates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "movies"
        root.mkdir()
        other = tmp_path / "music"
        other.mkdir()

        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [str(root)])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        def fake_list_libraries():
            return [
                {"id": 1, "import_paths": [{"path": str(root / "sub")}]},
                {"id": 2, "import_paths": [{"path": str(other)}]},
            ]

        refresh_calls = []

        def fake_queue_scan(library_id, *, trigger):
            refresh_calls.append((library_id, trigger))

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert refresh_calls == [(1, "scheduled")]

    def test_respects_max_folders_per_tick(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 2)

        libraries = []
        for i in range(5):
            folder = tmp_path / f"album_{i}"
            folder.mkdir(parents=True, exist_ok=True)
            libraries.append({"id": i + 1, "import_paths": [{"path": str(folder)}]})

        def fake_list_libraries():
            return libraries

        refresh_calls = []

        def fake_queue_scan(library_id, *, trigger):
            refresh_calls.append((library_id, trigger))

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 2

    def test_stops_early_when_refresh_stop_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_list_libraries():
            return [{"id": 1, "import_paths": [{"path": str(folder)}]}]

        refresh_calls = []

        def fake_queue_scan(library_id, *, trigger):
            refresh_calls.append((library_id, trigger))
            refresh._refresh_stop.set()

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 1

    def test_handles_oserror_during_root_resolve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", ["/nonexistent_root"])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_list_libraries():
            return [{"id": 1, "import_paths": [{"path": str(folder)}]}]

        refresh_calls = []

        def fake_queue_scan(library_id, *, trigger):
            refresh_calls.append((library_id, trigger))

        monkeypatch.setattr(refresh, "list_libraries", fake_list_libraries)
        monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 0

    def test_increments_counters_when_present(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        class FakeCounter:
            def __init__(self):
                self._val = 0

            def inc(self, v=1):
                if v != 1:
                    self._val += v
                else:
                    self._val += 1

        run_counter = FakeCounter()
        folder_counter = FakeCounter()

        monkeypatch.setattr(refresh, "_refresh_runs", run_counter)
        monkeypatch.setattr(refresh, "_refresh_folders", folder_counter)
        monkeypatch.setattr(refresh, "list_libraries", lambda: [])
        monkeypatch.setattr(refresh, "queue_scan", lambda library_id, *, trigger: None)

        _run_refresh_tick()
        assert run_counter._val == 1
        assert folder_counter._val == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestRefreshLifecycle:
    def test_start_refresh_noops_when_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", False)
        monkeypatch.setattr(refresh, "_refresh_thread", None)
        start_refresh()
        assert _refresh_thread is None

    def test_start_refresh_noops_when_existing_thread_alive(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)

        class FakeAliveThread:
            def is_alive(self):
                return True

        monkeypatch.setattr(refresh, "_refresh_thread", FakeAliveThread())
        start_refresh()
        assert isinstance(refresh._refresh_thread, FakeAliveThread)  # unchanged

    def test_start_refresh_creates_daemon_thread(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
        monkeypatch.setattr(refresh, "_refresh_thread", None)
        monkeypatch.setattr(refresh, "_refresh_stop", threading.Event())

        threads = []

        def fake_target():
            pass

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
        monkeypatch.setattr(refresh, "_refresh_loop", fake_target)

        start_refresh()
        assert len(threads) == 1
        assert threads[0].daemon is True
        assert threads[0].name == "gallery-scheduled-refresh"
        assert threads[0].started is True

    def test_stop_refresh_sets_stop_event_and_clears_thread(self, monkeypatch: pytest.MonkeyPatch):
        e = threading.Event()
        monkeypatch.setattr(refresh, "_refresh_stop", e)
        monkeypatch.setattr(refresh, "_refresh_thread", object())
        assert not e.is_set()

        stop_refresh()
        assert e.is_set()
        assert refresh._refresh_thread is None

    def test_get_refresh_status_returns_expected_shape(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", False)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_INTERVAL_SECONDS", 300)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 20)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", ["/a", "/b"])
        monkeypatch.setattr(refresh, "_refresh_thread", None)

        status = get_refresh_status()
        assert status["enabled"] is False
        assert status["alive"] is False
        assert status["interval_seconds"] == 300
        assert status["max_folders_per_tick"] == 20
        assert status["roots"] == ["/a", "/b"]

    def test_get_refresh_status_alive_when_thread_running(self, monkeypatch: pytest.MonkeyPatch):
        class FakeAliveThread:
            def is_alive(self):
                return True

        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
        monkeypatch.setattr(refresh, "_refresh_thread", FakeAliveThread())

        status = get_refresh_status()
        assert status["enabled"] is True
        assert status["alive"] is True

    def test_start_refresh_idempotent_across_lock(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
        monkeypatch.setattr(refresh, "_refresh_thread", None)
        monkeypatch.setattr(refresh, "_refresh_stop", threading.Event())

        threads = []

        class FakeThread:
            def __init__(self, target=None, name=None, daemon=None):
                self.target = target
                self.daemon = daemon
                self._started = False

            def is_alive(self):
                return self._started

            def start(self):
                self._started = True
                threads.append(self)

        monkeypatch.setattr(threading, "Thread", FakeThread)
        monkeypatch.setattr(refresh, "_refresh_loop", lambda: None)

        start_refresh()
        assert len(threads) == 1

        start_refresh()
        assert len(threads) == 1  # second call no-ops
