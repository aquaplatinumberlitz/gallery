"""A ``diskcache.Cache`` that closes each thread's SQLite connection when that thread ends."""

from __future__ import annotations

import atexit
import os
import sqlite3
import threading
import weakref
from contextlib import suppress
from typing import Any

from diskcache import Cache
from diskcache.core import DBNAME


class _ConnectionGuard:
    """Owns a thread's connection and closes it when the thread's local storage is torn down.

    The storage is torn down by the thread itself when it ends, or by whichever thread drops the last reference to
    the cache while the owning thread is still alive (a pooled request thread outliving a cache). The connection is
    opened with ``check_same_thread=False`` (see ``ThreadClosingCache._con``) so the second case can close it too;
    nothing else can use it by then, because the cache that handed it out is gone.
    """

    __slots__ = ("conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __del__(self) -> None:
        with suppress(sqlite3.Error):  # already closed
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

    @property
    def _con(self) -> sqlite3.Connection:
        """This thread's connection, opened as ``diskcache.Cache._con`` opens it (diskcache 5.6) but closable from any thread.

        diskcache opens it with the default ``check_same_thread=True``: when a cache is dropped while a pooled thread
        that used it is still alive, the dropping thread cannot close that thread's connection, and it is freed with
        ``ResourceWarning: unclosed database``. Only the owning thread ever uses the connection; another thread only
        closes it once the cache is unreachable.
        """
        local = self._local
        pid = os.getpid()
        if getattr(local, "pid", None) != pid:  # a new thread, or a forked process: as diskcache does
            self.close()
            local.pid = pid
        con = getattr(local, "con", None)
        if con is None:
            con = local.con = sqlite3.connect(
                os.path.join(self._directory, DBNAME),
                timeout=self._timeout,
                isolation_level=None,
                check_same_thread=False,
            )
            # Per-connection pragmas live in the Settings table (absent while the cache is being created).
            try:
                settings = con.execute("SELECT key, value FROM Settings").fetchall()
            except sqlite3.OperationalError:
                pass
            else:
                for key, value in settings:
                    if key.startswith("sqlite_"):
                        self.reset(key, value, update=False)
        return con
