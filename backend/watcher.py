from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from .config import (
    ENABLE_FILE_WATCHER,
    WATCHER_DEBOUNCE_SECONDS,
    WATCHER_MAX_EVENTS_PER_TICK,
    WATCHER_ROOTS,
)
from .files import is_image_path
from .metadata_store import mark_folder_index_incomplete

try:
    from prometheus_client import Counter

    _watcher_events = Counter(
        "gallery_watcher_events_total",
        "File watcher events by kind",
        ["kind"],
    )
except Exception:
    _watcher_events = None

LOGGER = logging.getLogger(__name__)

_watcher_thread: threading.Thread | None = None
_watcher_lock = threading.RLock()
_watcher_stop = threading.Event()

_HAS_WATCHDOG = False
try:
    import watchdog  # noqa: F401

    _HAS_WATCHDOG = True
except ImportError:
    pass


def _record_event(kind: str) -> None:
    if _watcher_events is not None:
        try:
            _watcher_events.labels(kind=kind).inc()
        except Exception:
            pass


class _DebouncedHandler:
    def __init__(self, roots: list[str]) -> None:
        self.affected_folders: dict[str, float] = {}
        self.affected_image_paths: dict[str, float] = {}
        self.lock = threading.Lock()
        self.roots = roots
        self._last_cleanup = 0.0

    def handle_event(self, event: Any) -> None:
        kind = "unknown"
        try:
            if hasattr(event, "event_type"):
                kind = event.event_type
            elif hasattr(event, "key"):
                kind = str(event.key)
        except Exception:
            pass

        path_str = None
        try:
            if hasattr(event, "src_path"):
                path_str = event.src_path
            elif hasattr(event, "path"):
                path_str = str(event.path)
        except Exception:
            pass

        _record_event(kind)

        if path_str:
            folder = str(Path(path_str).parent)
            with self.lock:
                self.affected_folders[folder] = time.time()
                if is_image_path(Path(path_str)):
                    self.affected_image_paths[path_str] = time.time()

    def get_and_clear_debounced(self) -> list[str]:
        now = time.time()
        cutoff = now - WATCHER_DEBOUNCE_SECONDS
        with self.lock:
            ready = [f for f, t in self.affected_folders.items() if t <= cutoff]
            for f in ready:
                del self.affected_folders[f]
            if now - self._last_cleanup > 60:
                for f in list(self.affected_folders):
                    if self.affected_folders[f] < now - 300:
                        del self.affected_folders[f]
                self._last_cleanup = now
        return ready

    def get_and_clear_debounced_image_paths(self) -> list[str]:
        now = time.time()
        cutoff = now - WATCHER_DEBOUNCE_SECONDS
        with self.lock:
            ready = [p for p, t in self.affected_image_paths.items() if t <= cutoff]
            for p in ready:
                del self.affected_image_paths[p]
        return ready


def _watcher_loop() -> None:
    if not _HAS_WATCHDOG:
        LOGGER.warning(
            "watchdog not installed; file watcher disabled. "
            "Install with: pip install watchdog"
        )
        return

    import watchdog.events
    import watchdog.observers

    handler = _DebouncedHandler(WATCHER_ROOTS)
    observer = watchdog.observers.Observer()

    for root in WATCHER_ROOTS:
        root_path = Path(root)
        if root_path.exists() and root_path.is_dir():
            event_handler = watchdog.events.FileSystemEventHandler()
            event_handler.on_created = handler.handle_event
            event_handler.on_deleted = handler.handle_event
            event_handler.on_modified = handler.handle_event
            event_handler.on_moved = handler.handle_event
            observer.schedule(event_handler, str(root_path), recursive=True)
            LOGGER.info("Watcher monitoring: %s", root_path)

    observer.start()
    try:
        while not _watcher_stop.is_set():
            _watcher_stop.wait(WATCHER_DEBOUNCE_SECONDS)
            ready = handler.get_and_clear_debounced()
            tick_count = 0
            for folder in ready:
                if tick_count >= WATCHER_MAX_EVENTS_PER_TICK:
                    break
                try:
                    mark_folder_index_incomplete(folder, last_error="watcher_marked_stale")
                    tick_count += 1
                except Exception as exc:
                    LOGGER.warning("Watcher mark incomplete failed for %s: %s", folder, exc)

            ready_paths = handler.get_and_clear_debounced_image_paths()
            if ready_paths:
                try:
                    from .indexer import stage_metadata_paths_from_scan
                    stage_metadata_paths_from_scan(
                        ready_paths[:WATCHER_MAX_EVENTS_PER_TICK],
                        start_worker=True,
                    )
                except Exception as exc:
                    LOGGER.warning("Watcher metadata staging failed: %s", exc)
    finally:
        observer.stop()
        observer.join()


def start_watcher() -> None:
    global _watcher_thread
    if not ENABLE_FILE_WATCHER:
        return
    with _watcher_lock:
        if _watcher_thread and _watcher_thread.is_alive():
            return
        _watcher_stop.clear()
        _watcher_thread = threading.Thread(
            target=_watcher_loop,
            name="gallery-file-watcher",
            daemon=True,
        )
        _watcher_thread.start()
        LOGGER.info("File watcher started: roots=%s, debounce=%ss", WATCHER_ROOTS, WATCHER_DEBOUNCE_SECONDS)


def stop_watcher() -> None:
    global _watcher_thread
    _watcher_stop.set()
    with _watcher_lock:
        _watcher_thread = None


def get_watcher_status() -> dict[str, Any]:
    return {
        "enabled": ENABLE_FILE_WATCHER,
        "alive": bool(_watcher_thread and _watcher_thread.is_alive()),
        "dependency_available": _HAS_WATCHDOG,
        "roots": WATCHER_ROOTS or [],
        "debounce_seconds": WATCHER_DEBOUNCE_SECONDS,
        "max_events_per_tick": WATCHER_MAX_EVENTS_PER_TICK,
    }
