"""Wake-up registry for requests that wait for an on-demand derivative.

A cold thumbnail or preview request awaits its derivative on the event loop instead of parking a thread-pool
thread. The scheduler worker that moves a derivative to a terminal state calls ``notify``; the registry hands
that to each waiting event loop with ``call_soon_threadsafe``. A notification only means "read the catalog
again": the waiter never trusts the signal for the outcome, and keeps a slow fallback poll for terminal
transitions that do not pass through the worker (recovery, eviction, supersede, another process).
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict


class DerivativeWaiters:
    """Thread-safe map of derivative id -> ``(loop, asyncio.Event)`` waiters."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._lock = threading.Lock()
        self._waiters: dict[int, list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = defaultdict(list)

    def register(self, derivative_id: int) -> asyncio.Event:
        """Create an event for the running loop; the caller must ``unregister`` it."""
        event = asyncio.Event()
        with self._lock:
            self._waiters[int(derivative_id)].append((asyncio.get_running_loop(), event))
        return event

    def unregister(self, derivative_id: int, event: asyncio.Event) -> None:
        """Drop one waiter and its map entry once empty. Safe to call twice."""
        with self._lock:
            entries = self._waiters.get(int(derivative_id))
            if entries is None:
                return
            entries[:] = [entry for entry in entries if entry[1] is not event]
            if not entries:
                del self._waiters[int(derivative_id)]

    def notify(self, derivative_id: int) -> None:
        """Wake every waiter of ``derivative_id``. Callable from any thread; never raises."""
        with self._lock:
            entries = list(self._waiters.get(int(derivative_id), ()))
        for loop, event in entries:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # the loop is closed: that waiter is gone
                continue

    def waiting_count(self) -> int:
        """Number of registered waiters (tests and diagnostics)."""
        with self._lock:
            return sum(len(entries) for entries in self._waiters.values())


derivative_waiters = DerivativeWaiters()
