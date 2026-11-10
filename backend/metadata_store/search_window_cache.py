"""In-process cache of the ranked candidate windows behind keyset search pages (BL-15).

A dense one-to-three character query makes every bounded candidate source rank its whole FTS match set (about
100k rows on the 100k fixture) just to keep the best ``fts_candidate_limit`` rows after the cursor, and a keyset
chain repeats that on every page. The first page already read the best rows of each source; later pages need only
the rows after their cursor, and they are in that list while the cursor lies inside it. ``ranked_search`` keeps the
list of each bounded source here, keyed by the request, the source and the *search generation*.

Never stale: the generation is a database row (``search_generation``) bumped by triggers, in the transaction of
every write that can change a search page (metadata, file index, assets, libraries, import paths and the folded,
trigram and CJK text tables). An entry is used only when its (epoch, generation) equals the one the request read
before it read any data, so a write that commits after that read can only make the entry unreachable, never wrong.

Bounded: at most ``max_entries`` entries and an estimated ``max_bytes`` of row data, least recently used first.
Thread-safe: one lock guards the table; cached rows are immutable ``sqlite3.Row`` objects shared read-only.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Any

# Rough per-value overhead of a cached row (a Python object per column) added to the text length.
_VALUE_OVERHEAD = 56
_ROW_OVERHEAD = 120


@dataclass(frozen=True)
class WindowEntry:
    """The rows one bounded source returned for a search request, and how far they are complete.

    ``bound`` is the cursor key the rows were read after (``None`` for the first page): they hold every row of the
    source after the bound up to ``cover``, and only those when ``cut_short`` (the source returned its full bound).
    """

    generation: int
    bound: tuple[Any, ...] | None
    rows: tuple[sqlite3.Row, ...]
    cut_short: bool
    cover: tuple[Any, ...] | None
    size: int


def estimate_rows_size(rows: Sequence[sqlite3.Row]) -> int:
    """A cheap over-estimate of the memory held by cached rows: the largest of a sample, times the row count.

    Rows of one source have the same shape (paths, a 240-character snippet at most), so sizing eight of them keeps
    the cost of filling an entry out of the first page's latency.
    """
    if not rows:
        return 0
    step = max(1, len(rows) // 8)
    largest = 0
    for row in rows[::step]:
        size = _ROW_OVERHEAD
        for value in tuple(row):
            size += _VALUE_OVERHEAD + (len(value) if isinstance(value, (str, bytes)) else 8)
        largest = max(largest, size)
    return largest * len(rows)


class SearchWindowCache:
    """A bounded, thread-safe LRU of ``WindowEntry`` objects."""

    def __init__(self, max_entries: int, max_bytes: int) -> None:
        """Cap the cache at ``max_entries`` entries and ``max_bytes`` of estimated row memory (0 turns it off)."""
        self.max_entries = max(0, int(max_entries))
        self.max_bytes = max(0, int(max_bytes))
        self._entries: OrderedDict[Hashable, WindowEntry] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @property
    def enabled(self) -> bool:
        """Whether the caps allow any entry."""
        return self.max_entries > 0 and self.max_bytes > 0

    def get(self, key: Hashable, generation: int) -> WindowEntry | None:
        """The entry of ``key`` if it was stored at ``generation``; an entry of another generation is dropped."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            if entry.generation != generation:
                self._remove(key)
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry

    def put(self, key: Hashable, entry: WindowEntry) -> None:
        """Store ``entry`` (replacing the key's older one), then evict least recently used entries to the caps."""
        if not self.enabled or entry.size > self.max_bytes:
            return
        with self._lock:
            if key in self._entries:
                self._remove(key)
            self._entries[key] = entry
            self._bytes += entry.size
            while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                oldest = next(iter(self._entries))
                self._remove(oldest)
                self.evictions += 1

    def clear(self) -> None:
        """Drop every entry (tests, and anything that wants a cold cache)."""
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def stats(self) -> dict[str, int]:
        """Entry count, estimated bytes and the hit, miss and eviction counters."""
        with self._lock:
            return {
                "entries": len(self._entries),
                "bytes": self._bytes,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }

    def _remove(self, key: Hashable) -> None:
        entry = self._entries.pop(key)
        self._bytes -= entry.size


def _configured_cache() -> SearchWindowCache:
    from ..config import SEARCH_WINDOW_CACHE_ENTRIES, SEARCH_WINDOW_CACHE_MB

    return SearchWindowCache(SEARCH_WINDOW_CACHE_ENTRIES, SEARCH_WINDOW_CACHE_MB * 1024 * 1024)


SEARCH_WINDOW_CACHE = _configured_cache()
