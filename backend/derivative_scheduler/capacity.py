"""Quota accounting and eviction for persisted derivative files."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..metadata_store import _connect
from ._common import logger


class CapacityMixin:
    """Capacity estimation, reservation, and quota enforcement for ``DerivativeScheduler``."""

    _ESTIMATED_DERIVATIVE_BYTES_FALLBACK = 64 * 1024

    def _estimate_new_derivative_bytes(self, conn: sqlite3.Connection) -> int:
        """Return a bounded estimate for one new derivative's on-disk size."""
        average = conn.execute(
            "SELECT COALESCE(avg(byte_size), 0) FROM asset_derivatives WHERE status = 'ready' AND byte_size > 0"
        ).fetchone()[0]
        if average and float(average) > 0:
            return int(average)
        return self._ESTIMATED_DERIVATIVE_BYTES_FALLBACK

    @staticmethod
    def _capacity_usage(conn: sqlite3.Connection, estimated_bytes: int) -> tuple[int, int]:
        """Return persisted ready bytes and estimated bytes reserved by active jobs."""
        ready_used = int(
            conn.execute("SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'").fetchone()[
                0
            ]
        )
        active_jobs = int(
            conn.execute(
                """SELECT count(*) FROM derivative_jobs j
                   JOIN asset_derivatives d ON d.id = j.derivative_id
                   WHERE j.state IN ('queued', 'running') AND d.status != 'ready'"""
            ).fetchone()[0]
        )
        return ready_used, active_jobs * estimated_bytes

    def _capacity_available(self, conn: sqlite3.Connection, estimated_bytes: int) -> bool:
        ready_used, reserved = self._capacity_usage(conn, estimated_bytes)
        return ready_used + reserved + estimated_bytes <= self.quota_bytes

    def _reserve_capacity(self, estimated_bytes: int) -> bool:
        """Commit eligible evictions, unlink them safely, then verify capacity.

        File deletion never occurs inside a caller-owned scheduling transaction:
        rolling that transaction back could otherwise resurrect ``ready`` catalog
        rows whose files are already gone. Candidate paths remain in the catalog
        until unlink succeeds, allowing failed unlinks to be compensated exactly.
        """
        with self._eviction_lock, self._file_lock:
            selected: list[tuple[int, str, int]] = []
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                ready_used, reserved = self._capacity_usage(conn, estimated_bytes)
                if ready_used + reserved + estimated_bytes <= self.quota_bytes:
                    return True
                needed = ready_used + reserved + estimated_bytes - self.quota_bytes
                selected_bytes = 0
                candidates = conn.execute(
                    """
                    SELECT id, cache_path, byte_size FROM asset_derivatives
                    WHERE status = 'ready' AND cache_path IS NOT NULL
                    ORDER BY COALESCE(last_accessed_at, created_at) ASC
                    """
                ).fetchall()
                for row in candidates:
                    cache_path = str(row["cache_path"])
                    if cache_path in self._served_paths or cache_path in self._generating_paths:
                        continue
                    byte_size = int(row["byte_size"] or 0)
                    selected.append((int(row["id"]), cache_path, byte_size))
                    selected_bytes += byte_size
                    if selected_bytes >= needed:
                        break
                if selected_bytes < needed:
                    return False
                for derivative_id, cache_path, _byte_size in selected:
                    conn.execute(
                        """
                        UPDATE asset_derivatives
                        SET status = 'evicted', last_error = 'evicted: capacity reservation',
                            updated_at = julianday('now')
                        WHERE id = ? AND status = 'ready' AND cache_path = ?
                        """,
                        (derivative_id, cache_path),
                    )
                conn.commit()

            removed: list[tuple[int, str, int]] = []
            failed: list[tuple[int, str, int]] = []
            for candidate in selected:
                try:
                    Path(candidate[1]).unlink(missing_ok=True)
                    removed.append(candidate)
                except OSError:
                    failed.append(candidate)

            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for derivative_id, cache_path, _byte_size in removed:
                    conn.execute(
                        """
                        UPDATE asset_derivatives
                        SET cache_path = NULL, byte_size = NULL, updated_at = julianday('now')
                        WHERE id = ? AND status = 'evicted' AND cache_path = ?
                        """,
                        (derivative_id, cache_path),
                    )
                for derivative_id, cache_path, byte_size in failed:
                    conn.execute(
                        """
                        UPDATE asset_derivatives
                        SET status = 'ready', cache_path = ?, byte_size = ?, last_error = NULL,
                            updated_at = julianday('now')
                        WHERE id = ? AND status = 'evicted' AND cache_path = ?
                        """,
                        (cache_path, byte_size, derivative_id, cache_path),
                    )
                conn.commit()

            with _connect() as conn:
                return self._capacity_available(conn, estimated_bytes)

    def _enforce_quota(self) -> None:
        if self._reserve_capacity(0):
            return
        with _connect() as conn:
            total = int(
                conn.execute(
                    "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
                ).fetchone()[0]
            )
        logger.warning(
            "Derivative quota still exceeded after eviction (%s > %s bytes); protected files may be in use",
            total,
            self.quota_bytes,
        )
