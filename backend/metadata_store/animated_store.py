"""Bounded detection pass that fills ``assets.animated`` (NULL = not detected yet).

The scan worker calls :func:`detect_pending_animated` after each catalog job. Rows are read in id-ordered
chunks, the container headers are sniffed outside the writer, and each chunk is written back in one short
writer op that only touches rows whose ``(mtime_ns, size)`` still match what was detected. A changed file
resets the column to NULL in the scan upsert, so it is re-detected on the next pass.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from ..animated import ANIMATABLE_EXTENSIONS, detect_animated_file
from ._db import _connect_read
from .db_writer import LANE_NORMAL, run_write

logger = logging.getLogger(__name__)

ANIMATED_CHUNK_ROWS = 200
ANIMATED_PASS_BUDGET_SECONDS = 30.0


def _pending_chunk(library_id: int, after_id: int, limit: int) -> list[tuple[int, str, int | None, int | None]]:
    with _connect_read() as conn:
        rows = conn.execute(
            """
            SELECT id, path, mtime_ns, size FROM assets
            WHERE library_id = ? AND id > ? AND type = 'image' AND animated IS NULL
              AND offline = 0 AND deleted_at IS NULL
            ORDER BY id LIMIT ?
            """,
            (library_id, after_id, limit),
        ).fetchall()
    return [(int(row["id"]), str(row["path"]), row["mtime_ns"], row["size"]) for row in rows]


def _detect_row(path: str, mtime_ns: int | None, size: int | None) -> int | None:
    """Return 1 or 0 for a detected row and ``None`` to leave it unknown (missing, changed or unreadable)."""
    if Path(path).suffix.lower() not in ANIMATABLE_EXTENSIONS:
        return 0
    try:
        stat = os.stat(path)
    except OSError:
        return None
    if stat.st_mtime_ns != mtime_ns or stat.st_size != size:
        return None  # the next scan refreshes the row's identity; detect then
    detected = detect_animated_file(path)
    return None if detected is None else int(detected)


def _write_chunk(updates: list[tuple[int, int, int | None, int | None]]) -> int:
    def write(conn) -> int:  # noqa: ANN001 - writer op
        written = 0
        for asset_id, animated, mtime_ns, size in updates:
            cursor = conn.execute(
                "UPDATE assets SET animated = ? WHERE id = ? AND animated IS NULL AND mtime_ns IS ? AND size IS ?",
                (animated, asset_id, mtime_ns, size),
            )
            written += cursor.rowcount
        return written

    return int(run_write(write, lane=LANE_NORMAL))


def detect_pending_animated(
    library_id: int,
    *,
    should_stop: Callable[[], bool] | None = None,
    budget_seconds: float = ANIMATED_PASS_BUDGET_SECONDS,
    chunk_rows: int = ANIMATED_CHUNK_ROWS,
) -> dict[str, int]:
    """Detect ``animated`` for the library's active images that have none; returns counters.

    Bounded by ``budget_seconds`` (the remainder is picked up by the next pass) and stops early when
    ``should_stop`` reports shutdown. Rows that cannot be read stay NULL.
    """
    deadline = time.monotonic() + budget_seconds
    after_id = 0
    counters = {"detected": 0, "animated": 0, "unknown": 0}
    while time.monotonic() < deadline and not (should_stop and should_stop()):
        chunk = _pending_chunk(library_id, after_id, chunk_rows)
        if not chunk:
            break
        after_id = chunk[-1][0]
        updates: list[tuple[int, int, int | None, int | None]] = []
        for asset_id, path, mtime_ns, size in chunk:
            animated = _detect_row(path, mtime_ns, size)
            if animated is None:
                counters["unknown"] += 1
            else:
                updates.append((asset_id, animated, mtime_ns, size))
        if updates:
            counters["detected"] += _write_chunk(updates)
            counters["animated"] += sum(update[1] for update in updates)
    return counters
