from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .config import (
    ENABLE_SCHEDULED_REFRESH,
    SCHEDULED_REFRESH_ALLOW_ALL_INDEXED,
    SCHEDULED_REFRESH_INTERVAL_SECONDS,
    SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK,
    SCHEDULED_REFRESH_ROOTS,
)
from .metadata_store import (
    _scan_folder_counts,
    get_folder_indexed_paths,
    index_directory_tree,
    mark_folder_index_incomplete,
    update_folder_index_state,
)

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


def _refresh_folder(folder_path_str: str) -> bool:
    path = Path(folder_path_str)
    if not path.exists() or not path.is_dir():
        mark_folder_index_incomplete(folder_path_str, last_error="path_not_found")
        return False
    try:
        index_directory_tree(path, include_metadata=False)
        counts = _scan_folder_counts(path)
        update_folder_index_state(
            path,
            complete=True,
            child_count=counts["child_count"],
            folder_count=counts["folder_count"],
            image_count=counts["image_count"],
            last_error=None,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        mark_folder_index_incomplete(folder_path_str, last_error=str(exc))
        LOGGER.warning("Scheduled refresh failed for %s: %s", folder_path_str, exc)
        return False


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
    roots = set(SCHEDULED_REFRESH_ROOTS)
    if not roots and not SCHEDULED_REFRESH_ALLOW_ALL_INDEXED:
        LOGGER.warning(
            "Scheduled refresh tick skipped: no roots configured and SCHEDULED_REFRESH_ALLOW_ALL_INDEXED is false"
        )
        return

    folders = get_folder_indexed_paths()
    candidate_folders: list[dict] = []

    for f in folders:
        p = f["path"]
        if not roots:
            candidate_folders.append(f)
        else:
            for root in roots:
                try:
                    rp = Path(root).resolve()
                    fp = Path(p).resolve()
                    if fp == rp or rp in fp.parents:
                        candidate_folders.append(f)
                        break
                except OSError:
                    pass

    candidate_folders.sort(key=lambda x: float(x.get("updated_at", 0) or 0))

    tick_count = 0
    for f in candidate_folders:
        if tick_count >= SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK:
            break
        if _refresh_stop.is_set():
            break
        try:
            if _refresh_folder(f["path"]):
                tick_count += 1
        except Exception:  # noqa: BLE001
            pass

    if _refresh_runs is not None:
        _refresh_runs.inc()
    if _refresh_folders is not None:
        _refresh_folders.inc(tick_count)


def start_refresh() -> None:
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
    global _refresh_thread
    _refresh_stop.set()
    with _refresh_lock:
        _refresh_thread = None


def get_refresh_status() -> dict[str, Any]:
    return {
        "enabled": ENABLE_SCHEDULED_REFRESH,
        "alive": bool(_refresh_thread and _refresh_thread.is_alive()),
        "interval_seconds": SCHEDULED_REFRESH_INTERVAL_SECONDS,
        "max_folders_per_tick": SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK,
        "roots": SCHEDULED_REFRESH_ROOTS or [],
    }
