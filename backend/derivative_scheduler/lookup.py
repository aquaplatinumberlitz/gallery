"""Read-side derivative lookups and serving-protection bookkeeping."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..metadata_store import _connect
from ._common import _ensure_database


class LookupMixin:
    """Status, ready-file, outcome, and asset lookups for ``DerivativeScheduler``."""

    _ACCESS_TOUCH_INTERVAL_SECONDS = 60.0

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
            if last_accessed_at <= now_julian - self._ACCESS_TOUCH_INTERVAL_SECONDS / 86400.0:
                conn.execute(
                    "UPDATE asset_derivatives SET last_accessed_at = ? WHERE id = ?",
                    (now_julian, row["id"]),
                )
            return dict(row)

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
        """Release a derivative file after a response completes."""
        with self._file_lock:
            self._served_paths.discard(cache_path)
