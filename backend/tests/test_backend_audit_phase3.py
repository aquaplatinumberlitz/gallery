"""
Purpose:
Protect watcher, refresh, and catalog-service ownership fixes from backend audit phase 3.

Guarantees:
* watcher debounce is clamped and bounded drains keep deterministic overflow
* durable scheduled-refresh ordering eventually visits every library
* the catalog supervisor restores a dead worker without a status request
* runtime status exposes supervisor health without starting workers or mutating jobs

Run when:
* changing watcher batching, scheduled refresh fairness, catalog workers/supervisor, or runtime status
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend import refresh, scan_worker, watcher
from backend.metadata_store import _DB_LOCK, _connect, create_library
from backend.metadata_store.status_store import build_global_runtime


def test_watcher_debounce_is_clamped_and_drain_order_is_stable(monkeypatch: pytest.MonkeyPatch):
    assert watcher.WATCHER_DEBOUNCE_SECONDS >= 0.1
    monkeypatch.setattr(watcher, "WATCHER_DEBOUNCE_SECONDS", 0.1)
    handler = watcher._DebouncedHandler(["/library"])
    now = time.time()
    handler.affected_folders = {
        "/library/c": now - 1,
        "/library/b": now - 2,
        "/library/a": now - 2,
    }

    assert handler.get_and_clear_debounced(2) == ["/library/a", "/library/b"]
    assert handler.get_and_clear_debounced(2) == ["/library/c"]


def test_scheduled_refresh_fairness_visits_every_library(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    library_ids = []
    for index in range(5):
        root = isolated_gallery_root / f"library-{index}"
        root.mkdir()
        library_ids.append(int(create_library([root], name=root.name)["id"]))

    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_ROOTS", [])
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", 2)
    monkeypatch.setattr(refresh, "_refresh_runs", None)
    monkeypatch.setattr(refresh, "_refresh_folders", None)
    refresh._refresh_stop.clear()

    refresh._run_refresh_tick()
    refresh._run_refresh_tick()
    refresh._run_refresh_tick()

    with _DB_LOCK, _connect() as conn:
        scheduled = {
            int(row["library_id"])
            for row in conn.execute("SELECT library_id FROM library_jobs WHERE trigger = 'scheduled'")
        }
    assert scheduled == set(library_ids)


def test_catalog_supervisor_restores_dead_worker_without_status_request(monkeypatch: pytest.MonkeyPatch):
    scan_worker.stop()
    scan_worker._stop_event.clear()
    monkeypatch.setattr(scan_worker, "GALLERY_CATALOG_WORKERS", 1)
    monkeypatch.setattr(scan_worker, "GALLERY_CATALOG_SERVICE_ENABLED", True)
    monkeypatch.setattr(scan_worker, "_SUPERVISOR_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(scan_worker, "recover_stale_jobs", lambda **_kwargs: [])
    calls = 0

    def worker_loop() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        scan_worker._stop_event.wait()

    monkeypatch.setattr(scan_worker, "_worker_loop", worker_loop)
    try:
        scan_worker.start()
        deadline = time.monotonic() + 1
        while calls < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        status = scan_worker.runtime_status()
        assert calls >= 2
        assert status["alive_workers"] == 1
        assert status["supervisor_alive"] == 1
    finally:
        scan_worker.stop()


def test_global_runtime_is_observational(monkeypatch: pytest.MonkeyPatch):
    worker_count_before = len(scan_worker._worker_threads)
    with _DB_LOCK, _connect() as conn:
        jobs_before = conn.execute("SELECT count(*) FROM library_jobs").fetchone()[0]

    monkeypatch.setattr(
        scan_worker,
        "ensure_running",
        lambda **_kwargs: pytest.fail("status must not invoke catalog recovery"),
    )
    runtime = build_global_runtime()

    with _DB_LOCK, _connect() as conn:
        jobs_after = conn.execute("SELECT count(*) FROM library_jobs").fetchone()[0]
    assert len(scan_worker._worker_threads) == worker_count_before
    assert jobs_after == jobs_before
    assert "catalog_supervisor_alive" in runtime
    assert "catalog_supervisor_failures" in runtime
