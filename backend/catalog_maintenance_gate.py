"""Shared gate for catalog maintenance and catalog work producers."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_MAINTENANCE_LOCK = threading.RLock()


class MaintenanceGateBusy(Exception):
    """Raised when the shared catalog maintenance gate is already held."""


@contextmanager
def maintenance_gate() -> Iterator[None]:
    """Hold the maintenance gate, failing fast when another holder is active."""
    acquired = _MAINTENANCE_LOCK.acquire(blocking=False)
    if not acquired:
        raise MaintenanceGateBusy()
    try:
        yield
    finally:
        _MAINTENANCE_LOCK.release()


def try_acquire_maintenance_gate() -> bool:
    """Try to hold the maintenance gate without blocking."""
    return _MAINTENANCE_LOCK.acquire(blocking=False)


def release_maintenance_gate() -> None:
    """Release a gate acquired by try_acquire_maintenance_gate."""
    _MAINTENANCE_LOCK.release()
