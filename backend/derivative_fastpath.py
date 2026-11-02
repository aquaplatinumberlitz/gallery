"""Bounded in-process lookup that lets a warm thumbnail/preview request skip the catalog.

A warm request used to cost an authorization read, an asset-id read and a ready-derivative read (each a
fresh SQLite connection) before the first byte. The result of those reads only changes when the source file
changes, the derivative file disappears, or the catalog deactivates the asset, so a small LRU remembers it:

    (requested path or asset id, kind, variant) -> (source path, source identity, asset/derivative ids,
                                                    cache file, ETag)

Validation is done by the caller on every hit, with the ``stat()`` of the source the handler needs anyway:
an entry whose recorded ``(st_mtime_ns, st_size)`` differs from the file on disk is dropped, so a superseded
or rewritten source can never be answered with its old derivative; the caller also checks that the cache
file still exists before it streams it. What a stat cannot see is a catalog-side change that leaves the file
alone (library removed, asset marked offline or deleted). Those are bounded by a short time-to-live: an
entry older than ``ttl_seconds`` is a miss and the full path re-authorizes and refreshes it.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from .config import DERIVATIVE_FASTPATH_ENTRIES, DERIVATIVE_FASTPATH_TTL_SECONDS

FastPathKey = tuple[str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class FastPathEntry:
    """What a validated warm request resolved to."""

    source_path: str
    mtime_ns: int
    size: int
    asset_id: int
    derivative_id: int
    cache_path: str
    etag: str
    created_at: float


def fast_path_key(database: str, path: str | None, asset_id: int | None, kind: str, variant: str) -> FastPathKey | None:
    """Key a request by the catalog database and exactly what the client sent (asset id or path), kind, variant.

    The database path is part of the key so entries resolved against one catalog (an isolated test database,
    a swapped data directory) can never answer for another.
    """
    if asset_id is not None:
        return (database, "asset", str(asset_id), kind, variant)
    if path is not None:
        return (database, "path", path, kind, variant)
    return None


class DerivativeFastPath:
    """Thread-safe LRU of ``FastPathEntry`` with a time-to-live. ``max_entries`` 0 disables it."""

    def __init__(self, max_entries: int, ttl_seconds: float, clock=time.monotonic):  # noqa: ANN001
        """Create an LRU of at most ``max_entries`` entries, each valid for ``ttl_seconds`` on ``clock``."""
        self.max_entries = max(0, int(max_entries))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[FastPathKey, FastPathEntry] = OrderedDict()

    @property
    def enabled(self) -> bool:
        """Whether the fast path remembers anything (a zero capacity or lifetime disables it)."""
        return self.max_entries > 0 and self.ttl_seconds > 0

    def get(self, key: FastPathKey) -> FastPathEntry | None:
        """Return a live entry (and mark it recently used), or None."""
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() - entry.created_at > self.ttl_seconds:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry

    def put(
        self,
        key: FastPathKey,
        *,
        source_path: str,
        mtime_ns: int,
        size: int,
        asset_id: int,
        derivative_id: int,
        cache_path: str,
        etag: str,
    ) -> None:
        """Remember what a fully validated request resolved to, evicting the least recently used entry if full."""
        if not self.enabled:
            return
        entry = FastPathEntry(
            source_path=source_path,
            mtime_ns=mtime_ns,
            size=size,
            asset_id=asset_id,
            derivative_id=derivative_id,
            cache_path=cache_path,
            etag=etag,
            created_at=self._clock(),
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def discard(self, key: FastPathKey, entry: FastPathEntry | None = None) -> None:
        """Drop ``key``; with ``entry`` only if it still holds that exact entry (a refill may have replaced it)."""
        with self._lock:
            current = self._entries.get(key)
            if current is not None and (entry is None or current is entry):
                del self._entries[key]

    def clear(self) -> None:
        """Forget everything."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Return the number of remembered entries."""
        with self._lock:
            return len(self._entries)


derivative_fast_path = DerivativeFastPath(DERIVATIVE_FASTPATH_ENTRIES, DERIVATIVE_FASTPATH_TTL_SECONDS)
