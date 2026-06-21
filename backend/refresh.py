"""Scheduled background reconciliation for registered catalog libraries."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .catalog.service import queue_scan
from .config import (
    ENABLE_SCHEDULED_REFRESH,
    SCHEDULED_REFRESH_INTERVAL_SECONDS,
    SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK,
    SCHEDULED_REFRESH_ROOTS,
)
from .metadata_store import list_libraries

LOGGER = logging.getLogger(__name__)

_refresh_thread: threading.Thread | None = None
_refresh_lock = threading.RLock()
_refresh_stop = threading.Event()

try:
    from prometheus_client import Counter

    _refresh_runs = Counter("gallery_scheduled_refresh_runs_total", "Scheduled refresh runs")
    _refresh_folders = Counter("gallery_scheduled_refresh_folders_total", "Folders refreshed per tick")
except Exception:  # noqa: BLE001
    _refresh_runs = None
    _refresh_folders = None


def _refresh_loop() -> None:
    while not _refresh_stop.is_set():
        _refresh_stop.wait(SCHEDULED_REFRESH_INTERVAL_SECONDS)
        if _refresh_stop.is_set():
            break

        try:
            _run_refresh_tick()
        except Exception as exc:
            LOGGER.exception("Scheduled refresh tick failed: %s", exc)


def _run_refresh_tick() -> None:
    libraries = list_libraries()
    roots = {str(Path(root).resolve()) for root in SCHEDULED_REFRESH_ROOTS}
    if not libraries:
        tick_count = 0
    else:
        if roots:
            libraries = [
                library
                for library in libraries
                if any(
                    Path(import_path["path"]).resolve() == Path(root)
                    or Path(root) in Path(import_path["path"]).resolve().parents
                    or Path(import_path["path"]).resolve() in Path(root).parents
                    for root in roots
                    for import_path in library["import_paths"]
                )
            ]
        tick_count = 0
        for library in libraries[:SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK]:
            if _refresh_stop.is_set():
                break
            try:
                queue_scan(int(library["id"]), trigger="scheduled")
                tick_count += 1
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Scheduled catalog reconciliation queue failed for library %s: %s", library["id"], exc)

    if _refresh_runs is not None:
        _refresh_runs.inc()
    if _refresh_folders is not None:
        _refresh_folders.inc(tick_count)


def start_refresh() -> None:
    """Start the scheduled refresh worker when enabled and not already running."""
    global _refresh_thread
    if not ENABLE_SCHEDULED_REFRESH:
        return
    with _refresh_lock:
        if _refresh_thread and _refresh_thread.is_alive():
            return
        _refresh_stop.clear()
        _refresh_thread = threading.Thread(
            target=_refresh_loop,
            name="gallery-scheduled-refresh",
            daemon=True,
        )
        _refresh_thread.start()
        LOGGER.info(
            "Scheduled refresh started: interval=%ss, max_folders_per_tick=%s, roots=%s",
            SCHEDULED_REFRESH_INTERVAL_SECONDS,
            SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK,
            SCHEDULED_REFRESH_ROOTS or "(all indexed)",
        )


def stop_refresh() -> None:
    """Signal the scheduled refresh worker to stop and clear its thread handle."""
    global _refresh_thread
    _refresh_stop.set()
    with _refresh_lock:
        _refresh_thread = None


def get_refresh_status() -> dict[str, Any]:
    """Return scheduled refresh configuration and runtime liveness."""
    return {
        "enabled": ENABLE_SCHEDULED_REFRESH,
        "alive": bool(_refresh_thread and _refresh_thread.is_alive()),
        "interval_seconds": SCHEDULED_REFRESH_INTERVAL_SECONDS,
        "max_folders_per_tick": SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK,
        "roots": SCHEDULED_REFRESH_ROOTS or [],
    }
