"""Quota accounting and eviction for persisted derivative files."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..metadata_store import _connect
from ..metadata_store.db_writer import LANE_NORMAL, run_write
from ._common import logger


class CapacityLedger:
    """Running capacity totals for one write transaction (one reconcile batch).

    ``_capacity_available`` needs two full-table aggregates: bytes held by ``ready``
    derivatives and the count of active jobs whose derivative is not ``ready``. Running
    them for every identity of a 750-coalesce batch kept the SQLite write lock for seconds.
    The ledger loads both aggregates once (lazily, on the first capacity check) and then
    follows the only writes that change them: a ``ready`` row leaving ``ready``, an
    ``evicted`` row returning to ``ready``, and a new queued job. Callers report each change
    right after the corresponding SQL; changes that happen before the lazy load are already
    part of the loaded aggregates and are ignored. The decisions are identical to evaluating
    the aggregates after every coalesce because the batch owns the write lock, so nothing
    else can change them.
    """

    def __init__(self) -> None:
        """Create an unloaded ledger."""
        self._ready_used: int | None = None
        self._active_jobs: int | None = None

    def available(self, conn: sqlite3.Connection, estimated_bytes: int, quota_bytes: int) -> bool:
        """Return whether one more derivative of ``estimated_bytes`` fits the quota."""
        if self._ready_used is None or self._active_jobs is None:
            self._ready_used, self._active_jobs = CapacityMixin._capacity_counts(conn)
        return self._ready_used + self._active_jobs * estimated_bytes + estimated_bytes <= quota_bytes

    def ready_row_left(self, byte_size: int | None) -> None:
        """Record that a ``ready`` row stopped being ``ready`` (its bytes no longer count)."""
        if self._ready_used is not None:
            self._ready_used -= int(byte_size or 0)

    def ready_row_restored(self, byte_size: int | None, active_jobs: int) -> None:
        """Record an ``evicted`` row returning to ``ready`` while holding ``active_jobs`` active jobs."""
        if self._ready_used is not None and self._active_jobs is not None:
            self._ready_used += int(byte_size or 0)
            self._active_jobs -= active_jobs

    def job_queued(self) -> None:
        """Record a new queued job for a derivative that is not ``ready``."""
        if self._active_jobs is not None:
            self._active_jobs += 1


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
    def _capacity_counts(conn: sqlite3.Connection) -> tuple[int, int]:
        """Return persisted ready bytes and the number of active jobs of non-ready derivatives."""
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
        return ready_used, active_jobs

    @classmethod
    def _capacity_usage(cls, conn: sqlite3.Connection, estimated_bytes: int) -> tuple[int, int]:
        """Return persisted ready bytes and estimated bytes reserved by active jobs."""
        ready_used, active_jobs = cls._capacity_counts(conn)
        return ready_used, active_jobs * estimated_bytes

    def _capacity_available(
        self,
        conn: sqlite3.Connection,
        estimated_bytes: int,
        ledger: CapacityLedger | None = None,
    ) -> bool:
        """Return whether one more derivative fits; a batch passes its ``ledger`` to skip re-aggregation."""
        if ledger is not None:
            return ledger.available(conn, estimated_bytes, self.quota_bytes)
        ready_used, reserved = self._capacity_usage(conn, estimated_bytes)
        return ready_used + reserved + estimated_bytes <= self.quota_bytes

    def _reserve_capacity(self, estimated_bytes: int, lane: str = LANE_NORMAL) -> bool:
        """Commit eligible evictions, unlink them safely, then verify capacity.

        File deletion never occurs inside a caller-owned scheduling transaction:
        rolling that transaction back could otherwise resurrect ``ready`` catalog
        rows whose files are already gone. Candidate paths remain in the catalog
        until unlink succeeds, allowing failed unlinks to be compensated exactly.

        The two catalog phases are database writer ops on ``lane`` (direct transactions with the flag
        off); the unlink runs between them, after the first op's Future resolved (its commit).
        """

        def select_and_evict(conn: sqlite3.Connection) -> list[tuple[int, str, int]] | bool:
            ready_used, reserved = self._capacity_usage(conn, estimated_bytes)
            if ready_used + reserved + estimated_bytes <= self.quota_bytes:
                return True
            needed = ready_used + reserved + estimated_bytes - self.quota_bytes
            selected: list[tuple[int, str, int]] = []
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
            return selected

        def select_and_evict_directly() -> list[tuple[int, str, int]] | bool:
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                return select_and_evict(conn)

        with self._eviction_lock, self._file_lock:
            evicted = run_write(select_and_evict, lane=lane, fallback=select_and_evict_directly)
            if evicted is True or evicted is False:
                return evicted
            selected = evicted

            removed: list[tuple[int, str, int]] = []
            failed: list[tuple[int, str, int]] = []
            for candidate in selected:
                try:
                    Path(candidate[1]).unlink(missing_ok=True)
                    removed.append(candidate)
                except OSError:
                    failed.append(candidate)

            def finalize(conn: sqlite3.Connection) -> None:
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

            def finalize_directly() -> None:
                with _connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    finalize(conn)

            run_write(finalize, lane=lane, fallback=finalize_directly)

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
