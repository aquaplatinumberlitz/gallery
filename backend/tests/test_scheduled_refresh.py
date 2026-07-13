"""
Purpose:
Verifies scheduled catalog reconciliation configuration and queue routing.

Guarantees:
* scheduled reconciliation is enabled by default
* refresh ticks queue scheduled catalog scans instead of indexing folders
* configured roots and max-work limits constrain queued library scans

Run when:
* changing scheduled reconciliation config, refresh loop, or catalog trigger routing
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from backend import refresh
from backend.config import ENABLE_SCHEDULED_REFRESH


@pytest.fixture(autouse=True)
def reset_refresh_state(monkeypatch: pytest.MonkeyPatch, isolated_metadata_db: Path):
    monkeypatch.setattr(refresh, "_refresh_thread", None)
    monkeypatch.setattr(refresh, "mark_scheduled_refresh_attempt", lambda _library_id: None)
    refresh._refresh_stop.clear()
    yield
    refresh.stop_refresh()
    refresh._refresh_stop.clear()


def test_enabled_by_default():
    assert ENABLE_SCHEDULED_REFRESH is True


def test_start_does_nothing_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", False)
    refresh.start_refresh()
    assert refresh._refresh_thread is None or not refresh._refresh_thread.is_alive()
    refresh.stop_refresh()


def test_start_refresh_creates_daemon_thread(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "_refresh_thread", None)
    monkeypatch.setattr(refresh, "_refresh_stop", threading.Event())

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
    monkeypatch.setattr(refresh, "_refresh_loop", lambda: None)

    refresh.start_refresh()

    assert len(threads) == 1
    assert threads[0].daemon is True
    assert threads[0].name == "gallery-scheduled-refresh"
    assert threads[0].started is True


def test_refresh_tick_queues_scheduled_scans_for_registered_libraries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    library_root = tmp_path / "library"
    library_root.mkdir()
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 10)
    monkeypatch.setattr(refresh, "list_libraries", lambda: [{"id": 7, "import_paths": [{"path": str(library_root)}]}])

    queued = []

    def fake_queue_scan(library_id, *, trigger):
        queued.append((library_id, trigger))

    monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)

    refresh._run_refresh_tick()

    assert queued == [(7, "scheduled")]


def test_refresh_tick_respects_max_libraries_per_tick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 2)
    libraries = []
    for index in range(5):
        root = tmp_path / f"library_{index}"
        root.mkdir()
        libraries.append({"id": index + 1, "import_paths": [{"path": str(root)}]})
    monkeypatch.setattr(refresh, "list_libraries", lambda: libraries)

    queued = []
    monkeypatch.setattr(refresh, "queue_scan", lambda library_id, *, trigger: queued.append((library_id, trigger)))

    refresh._run_refresh_tick()

    assert queued == [(1, "scheduled"), (2, "scheduled")]


def test_refresh_tick_filters_configured_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    selected = tmp_path / "selected"
    selected.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [str(selected)])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 10)
    monkeypatch.setattr(
        refresh,
        "list_libraries",
        lambda: [
            {"id": 1, "import_paths": [{"path": str(selected / "nested")}]},
            {"id": 2, "import_paths": [{"path": str(other)}]},
        ],
    )

    queued = []
    monkeypatch.setattr(refresh, "queue_scan", lambda library_id, *, trigger: queued.append((library_id, trigger)))

    refresh._run_refresh_tick()

    assert queued == [(1, "scheduled")]


def test_refresh_tick_continues_after_queue_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 10)
    monkeypatch.setattr(
        refresh,
        "list_libraries",
        lambda: [
            {"id": 1, "import_paths": [{"path": str(first)}]},
            {"id": 2, "import_paths": [{"path": str(second)}]},
        ],
    )

    queued = []

    def fake_queue_scan(library_id, *, trigger):
        if library_id == 1:
            raise RuntimeError("queue failed")
        queued.append((library_id, trigger))

    monkeypatch.setattr(refresh, "queue_scan", fake_queue_scan)

    refresh._run_refresh_tick()

    assert queued == [(2, "scheduled")]


def test_busy_coalesced_jobs_do_not_starve_scheduled_refresh(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.metadata_store import _DB_LOCK, _connect, create_library, create_or_coalesce_catalog_job
    from backend.metadata_store.job_store import mark_scheduled_refresh_attempt

    library_ids: list[int] = []
    for index in range(3):
        root = isolated_gallery_root / f"library-{index}"
        root.mkdir()
        library_ids.append(int(create_library([root])["id"]))
    create_or_coalesce_catalog_job(library_ids[0], trigger="initial", priority=100)
    create_or_coalesce_catalog_job(library_ids[1], trigger="manual", priority=100)
    create_or_coalesce_catalog_job(library_ids[2], trigger="initial", priority=100)

    monkeypatch.setattr(refresh, "mark_scheduled_refresh_attempt", mark_scheduled_refresh_attempt)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 1)
    monkeypatch.setattr(refresh, "_refresh_runs", None)
    monkeypatch.setattr(refresh, "_refresh_folders", None)

    refresh._run_refresh_tick()
    refresh._run_refresh_tick()
    refresh._run_refresh_tick()

    with _DB_LOCK, _connect() as conn:
        attempted = {
            int(row["id"])
            for row in conn.execute("SELECT id FROM libraries WHERE last_scheduled_attempt_at IS NOT NULL")
        }
    assert attempted == set(library_ids)


def test_failed_scheduled_attempt_advances_fairness(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.metadata_store import create_library
    from backend.metadata_store.job_store import mark_scheduled_refresh_attempt

    roots = [isolated_gallery_root / "first", isolated_gallery_root / "second"]
    for root in roots:
        root.mkdir()
    libraries = [create_library([root]) for root in roots]
    monkeypatch.setattr(refresh, "mark_scheduled_refresh_attempt", mark_scheduled_refresh_attempt)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 1)
    queued: list[int] = []

    def fail_first(library_id: int, *, trigger: str):
        if library_id == int(libraries[0]["id"]):
            raise RuntimeError("maintenance busy")
        queued.append(library_id)

    monkeypatch.setattr(refresh, "queue_scan", fail_first)
    refresh._run_refresh_tick()
    refresh._run_refresh_tick()
    assert queued == [int(libraries[1]["id"])]
