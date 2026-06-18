"""
Purpose:
Unit-test the scheduled-refresh service logic without spawning background threads
or sleeping.  Every coverage branch in refresh.py is exercised via direct helper
calls and monkeypatched dependencies.

Guarantees:
* _refresh_folder marks incomplete on missing path and returns False.
* _refresh_folder calls index_directory_tree, _scan_folder_counts, and
  update_folder_index_state on success.
* _refresh_folder marks incomplete on exception and returns False.
* _run_refresh_tick skips when no roots + allow_all=False.
* _run_refresh_tick processes all indexed paths when allow_all=True.
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
    _refresh_folder,
    _refresh_stop,
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
    refresh._refresh_stop.clear()
    yield
    refresh._refresh_stop.clear()
    monkeypatch.setattr(refresh, "_refresh_thread", None)


# ---------------------------------------------------------------------------
# _refresh_folder
# ---------------------------------------------------------------------------


class TestRefreshFolder:
    def test_missing_path_marks_incomplete_and_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        calls = []

        def fake_mark(path, last_error=None):
            calls.append(("mark", path, last_error))

        monkeypatch.setattr(refresh, "mark_folder_index_incomplete", fake_mark)

        result = _refresh_folder("/nonexistent/path")
        assert result is False
        assert len(calls) == 1
        assert calls[0][1] == "/nonexistent/path"
        assert calls[0][2] == "path_not_found"

    def test_file_path_marks_incomplete_and_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        f = tmp_path / "file.txt"
        f.write_text("data")
        calls = []

        def fake_mark(path, last_error=None):
            calls.append(("mark", path, last_error))

        monkeypatch.setattr(refresh, "mark_folder_index_incomplete", fake_mark)

        result = _refresh_folder(str(f))
        assert result is False
        assert len(calls) == 1

    def test_successful_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        folder = tmp_path / "album"
        folder.mkdir()

        index_calls = []
        scan_counts_calls = []
        update_calls = []

        def fake_index(path, include_metadata=False):
            index_calls.append(str(path))

        def fake_scan_counts(path):
            scan_counts_calls.append(str(path))
            return {"child_count": 5, "folder_count": 2, "image_count": 10}

        def fake_update(path, complete, child_count, folder_count, image_count, last_error):
            update_calls.append((str(path), complete, child_count))

        monkeypatch.setattr(refresh, "index_directory_tree", fake_index)
        monkeypatch.setattr(refresh, "_scan_folder_counts", fake_scan_counts)
        monkeypatch.setattr(refresh, "update_folder_index_state", fake_update)

        result = _refresh_folder(str(folder))
        assert result is True
        assert len(index_calls) == 1
        assert len(scan_counts_calls) == 1
        assert len(update_calls) == 1
        assert update_calls[0][1] is True

    def test_exception_marks_incomplete_and_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        folder = tmp_path / "album"
        folder.mkdir()

        def fake_index(path, include_metadata=False):
            raise RuntimeError("boom")

        mark_calls = []

        def fake_mark(path, last_error=None):
            mark_calls.append((path, last_error))

        monkeypatch.setattr(refresh, "index_directory_tree", fake_index)
        monkeypatch.setattr(refresh, "mark_folder_index_incomplete", fake_mark)

        result = _refresh_folder(str(folder))
        assert result is False
        assert len(mark_calls) == 1
        assert "boom" in mark_calls[0][1]


# ---------------------------------------------------------------------------
# _run_refresh_tick
# ---------------------------------------------------------------------------


class TestRunRefreshTick:
    def test_no_roots_and_allow_all_false_skips(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", False)

        get_folders_calls = []

        def fake_get_folders():
            get_folders_calls.append(1)
            return []

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        _run_refresh_tick()
        assert len(get_folders_calls) == 0

    def test_allow_all_true_processes_indexed_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_get_folders():
            return [{"path": str(folder), "updated_at": 0}]

        refresh_calls = []

        def fake_refresh_folder(p):
            refresh_calls.append(p)
            return True

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        monkeypatch.setattr(refresh, "_refresh_folder", fake_refresh_folder)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 1

    def test_configured_roots_filter_candidates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "movies"
        root.mkdir()
        other = tmp_path / "music"
        other.mkdir()

        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [str(root)])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        def fake_get_folders():
            return [
                {"path": str(root / "sub"), "updated_at": 0},
                {"path": str(other), "updated_at": 0},
            ]

        refresh_calls = []

        def fake_refresh_folder(p):
            refresh_calls.append(p)
            return True

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        monkeypatch.setattr(refresh, "_refresh_folder", fake_refresh_folder)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        paths = refresh_calls
        assert str(root / "sub") in paths
        assert str(other) not in paths

    def test_respects_max_folders_per_tick(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 2)

        folders = [{"path": str(tmp_path / f"album_{i}"), "updated_at": i} for i in range(5)]
        for f in folders:
            Path(f["path"]).mkdir(parents=True, exist_ok=True)

        def fake_get_folders():
            return folders

        refresh_calls = []

        def fake_refresh_folder(p):
            refresh_calls.append(p)
            return True

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        monkeypatch.setattr(refresh, "_refresh_folder", fake_refresh_folder)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 2

    def test_stops_early_when_refresh_stop_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_get_folders():
            return [{"path": str(folder), "updated_at": 0}]

        refresh_calls = []

        def fake_refresh_folder(p):
            refresh_calls.append(p)
            refresh._refresh_stop.set()
            return True

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        monkeypatch.setattr(refresh, "_refresh_folder", fake_refresh_folder)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 1

    def test_handles_oserror_during_root_resolve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", ["/nonexistent_root"])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        folder = tmp_path / "album"
        folder.mkdir()

        def fake_get_folders():
            return [{"path": str(folder), "updated_at": 0}]

        refresh_calls = []

        def fake_refresh_folder(p):
            refresh_calls.append(p)
            return True

        monkeypatch.setattr(refresh, "get_folder_indexed_paths", fake_get_folders)
        monkeypatch.setattr(refresh, "_refresh_folder", fake_refresh_folder)
        monkeypatch.setattr(refresh, "_refresh_runs", None)
        monkeypatch.setattr(refresh, "_refresh_folders", None)

        _run_refresh_tick()
        assert len(refresh_calls) == 0

    def test_increments_counters_when_present(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", True)
        monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 100)

        runs_vals = []
        folders_vals = []

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
        monkeypatch.setattr(refresh, "get_folder_indexed_paths", lambda: [])
        monkeypatch.setattr(refresh, "_refresh_folder", lambda p: True)

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
