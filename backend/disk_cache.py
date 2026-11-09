"""A ``diskcache.Cache`` that closes each thread's SQLite connection when that thread ends."""

from __future__ import annotations

import atexit
import sqlite3
import threading
import weakref
from contextlib import suppress
from typing import Any

from diskcache import Cache


class _ConnectionGuard:
    """Owns a thread's connection and closes it when the thread's local storage is torn down."""

    __slots__ = ("conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __del__(self) -> None:
        # Already closed, or torn down off its own thread (``check_same_thread``): nothing more to do.
        with suppress(sqlite3.Error):
            self.conn.close()


class _GuardedLocal(threading.local):
    """Thread-local storage whose ``con`` attribute (diskcache's per-thread connection) has a guard."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "con" and isinstance(value, sqlite3.Connection):
            super().__setattr__("_con_guard", _ConnectionGuard(value))


_LIVE_CACHES: weakref.WeakSet[ThreadClosingCache] = weakref.WeakSet()


@atexit.register
def _close_live_caches() -> None:
    """Close the exiting (main) thread's connection of every cache still alive, before interpreter teardown."""
    for cache in list(_LIVE_CACHES):
        with suppress(Exception):
            cache.close()


class ThreadClosingCache(Cache):
    """``diskcache.Cache`` opens one SQLite connection per thread and only closes the calling thread's on ``close()``.

    Connections of threads that simply end (the request thread pool, derivative workers) were left to the
    garbage collector: a ``ResourceWarning: unclosed database`` at best, a held descriptor at worst. Here a thread's
    connection is closed by its own thread, the moment the thread's local storage is destroyed.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Open the cache like ``diskcache.Cache`` (same arguments)."""
        super().__init__(*args, **kwargs)
        guarded = _GuardedLocal()
        for name in ("pid", "con"):  # hand the constructing thread's open connection over to the guarded storage
            if hasattr(self._local, name):
                setattr(guarded, name, getattr(self._local, name))
        self._local = guarded
        _LIVE_CACHES.add(self)
