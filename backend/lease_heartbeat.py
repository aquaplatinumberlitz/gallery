"""Shared lease-renewal heartbeat for durable job workers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


class LeaseHeartbeat:
    """Run a fenced ``renew`` callable on its own daemon thread at most every ``interval_seconds``.

    The owner of one claimed job creates a heartbeat, ``start()``s it before slow work, and
    ``stop()``s it before persisting the terminal outcome. ``renew`` is expected to update only a
    row that is still ``running`` under the owner's claim token and to swallow storage errors; a
    renewal that raises is logged and never stops the heartbeat or alters the job outcome, because
    fenced recovery arbitrates a genuinely lost lease.
    """

    def __init__(self, renew: Callable[[], object], interval_seconds: float, *, name: str):
        """Prepare (but do not start) the heartbeat thread."""
        self._renew = renew
        self._interval = max(0.05, float(interval_seconds))
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)

    def start(self) -> None:
        """Start renewing."""
        self._thread.start()

    def stop(self) -> None:
        """Stop renewing and wait for an in-flight renewal; safe to call repeatedly or before ``start()``."""
        self._stop_event.set()
        if self._thread.is_alive():
            # Renewal writes are bounded DB operations, but under contention an in-flight
            # renewal can outlast a short join. Wait generously so the caller can safely
            # persist terminal state without a heartbeat race.
            self._thread.join(timeout=max(2.0, self._interval + 2.0))

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._renew()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Lease renewal raised; the heartbeat keeps running")
