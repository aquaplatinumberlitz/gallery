"""Read-side derivative lookups and serving-protection bookkeeping."""

from __future__ import annotations

import sqlite3
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..metadata_store import _connect
from ..metadata_store.db_writer import LANE_NORMAL, post_write
from ._common import _ensure_database


class LookupMixin:
    """Status, ready-file, outcome, and asset lookups for ``DerivativeScheduler``."""

    _ACCESS_TOUCH_INTERVAL_SECONDS = 60.0
    # Longest ``release_serving`` waits for a queued ``last_accessed_at`` touch of its file to be applied.
    _TOUCH_FLUSH_TIMEOUT_SECONDS = 2.0

    def get_derivative_status(self, asset_id: int, kind: str, variant: str) -> str | None:
        """Return the current derivative state for the latest source version."""
        _ensure_database()
        with _connect() as conn:
            asset = conn.execute("SELECT path FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if asset is None:
                return None
            try:
                stat = Path(asset["path"]).stat()
            except OSError:
                return None
            row = conn.execute(
                """
                SELECT status FROM asset_derivatives
                WHERE asset_id = ? AND kind = ? AND variant = ?
                  AND source_mtime_ns = ? AND source_size = ?
                ORDER BY id DESC LIMIT 1
                """,
                (asset_id, kind, variant, stat.st_mtime_ns, stat.st_size),
            ).fetchone()
        if row is None:
            return None
        return "generating" if row["status"] == "running" else str(row["status"])

    def get_ready_derivative(
        self,
        asset_id: int,
        kind: str,
        variant: str,
        *,
        source_mtime_ns: int | None = None,
        source_size: int | None = None,
    ) -> dict[str, Any] | None:
        """Return and touch a ready derivative for the current source version."""
        _ensure_database()
        with _connect() as conn:
            if source_mtime_ns is None or source_size is None:
                asset = conn.execute("SELECT path FROM assets WHERE id = ?", (asset_id,)).fetchone()
                if asset is None:
                    return None
                try:
                    stat = Path(asset["path"]).stat()
                except OSError:
                    return None
                source_mtime_ns = stat.st_mtime_ns
                source_size = stat.st_size
            row = conn.execute(
                """
                SELECT * FROM asset_derivatives
                WHERE asset_id = ? AND kind = ? AND variant = ? AND source_mtime_ns = ?
                  AND source_size = ? AND status = 'ready'
                ORDER BY id DESC LIMIT 1
                """,
                (asset_id, kind, variant, source_mtime_ns, source_size),
            ).fetchone()
            if row is None or not row["cache_path"] or not Path(row["cache_path"]).is_file():
                return None
            last_accessed_at = float(row["last_accessed_at"] or 0)
            now_julian = time.time() / 86400.0 + 2440587.5
            touch_id = (
                int(row["id"])
                if last_accessed_at <= now_julian - self._ACCESS_TOUCH_INTERVAL_SECONDS / 86400.0
                else None
            )
            ready = dict(row)
        if touch_id is not None:
            self._touch_derivative(touch_id, now_julian, str(ready["cache_path"]))
        return ready

    def _touch_derivative(self, derivative_id: int, accessed_at: float, cache_path: str) -> None:
        """Record a warm access without making the request wait for the database writer.

        Reads stay on plain connections; the ``last_accessed_at`` update is a best-effort, fire-and-forget
        normal-lane writer op (an HTTP request must never wait for a batch). It only orders the LRU
        eviction, so it may be dropped under maintenance or backpressure. The queued Future is remembered
        so ``release_serving`` can flush it once the response is done. With the writer flag off the update
        is applied inline as before.
        """

        def touch(conn: sqlite3.Connection) -> None:
            conn.execute("UPDATE asset_derivatives SET last_accessed_at = ? WHERE id = ?", (accessed_at, derivative_id))

        def touch_directly() -> None:
            with _connect() as conn:
                touch(conn)

        future = post_write(touch, lane=LANE_NORMAL, fallback=touch_directly)
        if future is not None and not future.done():
            self._pending_touches[cache_path] = future
            future.add_done_callback(
                lambda done: self._pending_touches.pop(cache_path, None)
                if self._pending_touches.get(cache_path) is done
                else None
            )

    def acquire_ready_derivative(
        self,
        asset_id: int,
        kind: str,
        variant: str,
        *,
        source_mtime_ns: int | None = None,
        source_size: int | None = None,
    ) -> dict[str, Any] | None:
        """Atomically look up and protect a ready file for response streaming."""
        ready = self.get_ready_derivative(
            asset_id,
            kind,
            variant,
            source_mtime_ns=source_mtime_ns,
            source_size=source_size,
        )
        if ready is None:
            return None
        cache_path = str(ready["cache_path"])
        with self._file_lock:
            if not Path(cache_path).is_file():
                return None
            self._served_paths.add(cache_path)
        return ready

    def get_derivative_outcome(self, derivative_id: int) -> dict[str, Any] | None:
        """Return a bounded read model for one scheduled derivative by ID.

        The read model exposes the derivative state, latest fenced job outcome,
        result code, error, cache path, and whether the identity is still current.
        Request waiters use this to branch on ready/failed/skipped/deferred outcomes
        without polling by source identity or parsing error strings.
        """
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT d.id, d.status, d.cache_path, d.last_error,
                  (SELECT j.state FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS latest_job_state,
                  (SELECT j.result_code FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS result_code,
                  (SELECT j.error FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS error,
                  a.id AS asset_id, a.mtime_ns, a.size, d.source_mtime_ns, d.source_size
                FROM asset_derivatives d LEFT JOIN assets a ON a.id = d.asset_id
                WHERE d.id = ?
                """,
                (derivative_id,),
            ).fetchone()
        if row is None:
            return None
        is_current = (
            row["asset_id"] is not None
            and row["mtime_ns"] is not None
            and row["size"] is not None
            and int(row["mtime_ns"]) == int(row["source_mtime_ns"])
            and int(row["size"]) == int(row["source_size"])
        )
        return {
            "derivative_id": int(row["id"]),
            "derivative_state": str(row["status"]),
            "latest_job_state": str(row["latest_job_state"]) if row["latest_job_state"] is not None else None,
            "result_code": row["result_code"],
            "error": row["error"],
            "cache_path": row["cache_path"],
            "is_current": bool(is_current),
        }

    def find_asset_id(self, path: Path) -> int | None:
        """Resolve a source path to its active asset ID."""
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                "SELECT id FROM assets WHERE path = ? AND type = 'image' "
                "AND deleted_at IS NULL AND offline = 0 ORDER BY id LIMIT 1",
                (str(path.resolve()),),
            ).fetchone()
        return int(row["id"]) if row else None

    def get_asset_path(self, asset_id: int) -> Path | None:
        """Return the active source path for an asset ID."""
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
        return Path(row["path"]) if row else None

    def acquire_serving(self, cache_path: str) -> None:
        """Protect a derivative file while a response is streaming it."""
        with self._file_lock:
            self._served_paths.add(cache_path)

    def release_serving(self, cache_path: str) -> None:
        """Release a derivative file after a response completes.

        A superseded file whose unlink was deferred while it was being served is removed now.
        """
        with self._file_lock:
            self._served_paths.discard(cache_path)
        pending = self._pending_touches.pop(cache_path, None)
        if pending is not None:
            # The response is complete, so waiting here delays no client; a lost touch only affects LRU order.
            with suppress(Exception):
                pending.result(timeout=self._TOUCH_FLUSH_TIMEOUT_SECONDS)
        self._finish_deferred_unlink(cache_path)
