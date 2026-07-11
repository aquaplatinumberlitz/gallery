"""Shared gate for catalog maintenance and catalog work producers."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar, cast

_STATE_CONDITION = threading.Condition()
_MAINTENANCE_ACTIVE = False
_MAINTENANCE_OWNER: int | None = None
_ACTIVE_PRODUCERS = 0
_ACQUISITIONS = threading.local()
_F = TypeVar("_F", bound=Callable[..., Any])


class MaintenanceGateBusy(Exception):
    """Raised when the shared catalog maintenance gate is already held."""


@contextmanager
def maintenance_gate() -> Iterator[None]:
    """Hold the maintenance gate, failing fast when another holder is active."""
    global _MAINTENANCE_ACTIVE, _MAINTENANCE_OWNER
    with _STATE_CONDITION:
        if _MAINTENANCE_ACTIVE or _ACTIVE_PRODUCERS:
            raise MaintenanceGateBusy()
        _MAINTENANCE_ACTIVE = True
        _MAINTENANCE_OWNER = threading.get_ident()
    try:
        yield
    finally:
        with _STATE_CONDITION:
            _MAINTENANCE_ACTIVE = False
            _MAINTENANCE_OWNER = None
            _STATE_CONDITION.notify_all()


def try_acquire_maintenance_gate() -> bool:
    """Try to hold the maintenance gate without blocking."""
    global _ACTIVE_PRODUCERS
    with _STATE_CONDITION:
        owner_bypass = _MAINTENANCE_ACTIVE and threading.get_ident() == _MAINTENANCE_OWNER
        if _MAINTENANCE_ACTIVE and not owner_bypass:
            return False
        if not owner_bypass:
            _ACTIVE_PRODUCERS += 1
        stack = getattr(_ACQUISITIONS, "stack", [])
        stack.append(owner_bypass)
        _ACQUISITIONS.stack = stack
        return True


def release_maintenance_gate() -> None:
    """Release a gate acquired by try_acquire_maintenance_gate."""
    global _ACTIVE_PRODUCERS
    stack = getattr(_ACQUISITIONS, "stack", [])
    if not stack:
        raise RuntimeError("Maintenance producer gate released without an acquisition")
    owner_bypass = stack.pop()
    with _STATE_CONDITION:
        if not owner_bypass:
            _ACTIVE_PRODUCERS -= 1
            if _ACTIVE_PRODUCERS == 0:
                _STATE_CONDITION.notify_all()


@contextmanager
def producer_gate() -> Iterator[None]:
    """Hold the shared gate for one complete producer operation."""
    global _ACTIVE_PRODUCERS
    with _STATE_CONDITION:
        owner_bypass = _MAINTENANCE_ACTIVE and threading.get_ident() == _MAINTENANCE_OWNER
        while _MAINTENANCE_ACTIVE and not owner_bypass:
            _STATE_CONDITION.wait()
            owner_bypass = _MAINTENANCE_ACTIVE and threading.get_ident() == _MAINTENANCE_OWNER
        if not owner_bypass:
            _ACTIVE_PRODUCERS += 1
    try:
        yield
    finally:
        if not owner_bypass:
            with _STATE_CONDITION:
                _ACTIVE_PRODUCERS -= 1
                if _ACTIVE_PRODUCERS == 0:
                    _STATE_CONDITION.notify_all()


def maintenance_producer(func: _F) -> _F:
    """Serialize a database work producer against destructive maintenance."""

    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with producer_gate():
            return func(*args, **kwargs)

    return cast(_F, wrapped)
