"""Durable derivative identity coalescing, scheduling, and consistency repair."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..catalog_maintenance_gate import maintenance_producer
from ..config import (
    DERIVATIVE_RECONCILE_BATCH_SIZE,
    DERIVATIVE_VARIANTS,
)
from ..metadata_store import _connect
from ._common import _ensure_database
from .models import DerivativeRepairSummary


class SchedulingMixin:
    """Create or repair derivative rows and jobs for ``DerivativeScheduler``."""

    @maintenance_producer
    def repair_derivative_consistency(self, derivative_ids: list[int]) -> DerivativeRepairSummary:
        """Create a queued job for each current ``queued`` derivative without one.

        Unlike ``reconcile_desired_derivatives``, this repair overrides
        ``warm_enabled`` because an already-existing ``queued`` row must have a
        job regardless of library policy.  Historical or source-changed identities
        are terminalized with the appropriate skipped result code.

        Returns a structured ``DerivativeRepairSummary`` with exact outcome
        counters so callers can distinguish requeued from skipped from unchanged.
        """
        summary = DerivativeRepairSummary()
        if not derivative_ids:
            return summary
        summary.issues_considered = len(derivative_ids)
        _ensure_database()
        for offset in range(0, len(derivative_ids), DERIVATIVE_RECONCILE_BATCH_SIZE):
            batch = derivative_ids[offset : offset + DERIVATIVE_RECONCILE_BATCH_SIZE]
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for did in batch:
                    row = conn.execute(
                        """
                        SELECT d.id, d.status, d.asset_id, d.kind, d.variant,
                               d.source_mtime_ns, d.source_size, d.format, d.max_long_edge, d.quality,
                               a.id AS a_id, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
                        FROM asset_derivatives d
                        LEFT JOIN assets a ON a.id = d.asset_id
                        WHERE d.id = ?
                        """,
                        (did,),
                    ).fetchone()
                    if row is None:
                        summary.unchanged += 1
                        continue
                    if row["status"] != "queued":
                        summary.unchanged += 1
                        continue
                    latest_job = conn.execute(
                        "SELECT state FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
                        (did,),
                    ).fetchone()
                    if latest_job is not None and latest_job["state"] in ("queued", "running"):
                        summary.already_active += 1
                        continue
                    if row["a_id"] is None or row["type"] != "image" or row["deleted_at"] is not None or row["offline"]:
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "asset_inactive",
                            "integrity: derivative asset is inactive",
                        )
                        summary.terminal_skipped += 1
                        continue
                    try:
                        stat = Path(
                            conn.execute("SELECT path FROM assets WHERE id = ?", (row["asset_id"],)).fetchone()[0]
                        ).stat()
                    except (OSError, TypeError):
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "source_missing",
                            "integrity: derivative source file is missing",
                        )
                        summary.terminal_skipped += 1
                        continue
                    if (
                        stat.st_mtime_ns != int(row["source_mtime_ns"])
                        or stat.st_size != int(row["source_size"])
                        or int(row["mtime_ns"]) != int(row["source_mtime_ns"])
                        or int(row["size"]) != int(row["source_size"])
                    ):
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "source_changed",
                            "integrity: derivative source identity changed",
                        )
                        summary.terminal_skipped += 1
                        continue
                    conn.execute(
                        "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'queued')",
                        (did,),
                    )
                    summary.jobs_created += 1
            self._wake_event.set()
        return summary

    @staticmethod
    def _terminalize_derivative(
        conn: sqlite3.Connection,
        derivative_id: int,
        row: sqlite3.Row,
        state: str,
        result_code: str,
        message: str,
    ) -> None:
        """Terminalize a derivative row and any active jobs."""
        conn.execute(
            "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
            (state, message, derivative_id),
        )
        conn.execute(
            """
            UPDATE derivative_jobs
            SET state = ?, result_code = ?, error = ?,
                claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                completed_at = julianday('now'), updated_at = julianday('now')
            WHERE derivative_id = ? AND state IN ('queued', 'running')
            """,
            (state, result_code, message, derivative_id),
        )

    def _coalesce_derivative_job(
        self,
        conn: sqlite3.Connection,
        *,
        asset_id: int,
        kind: str,
        variant: str,
        source_mtime_ns: int,
        source_size: int,
        max_long_edge: int,
        quality: int,
        format: str,
        priority: int,
        retry_failed: bool,
        deferrable: bool = False,
        reconsider_deferred_capacity: bool = True,
        estimated_bytes: int | None = None,
    ) -> tuple[int, str]:
        """Create or repair one identity while the caller owns a write transaction.

        When ``deferrable`` is True (automatic background reconciliation), an
        identity that cannot reserve quota capacity is written as ``deferred_capacity``
        without creating a runnable job. Interactive/manual callers pass
        ``deferrable=False`` and rely on post-render eviction instead. Automatic
        periodic, catalog, and metadata-completion reconciliation sets
        ``reconsider_deferred_capacity=False`` so an existing capacity-deferred
        identity does not repeatedly evict a different ready variant; integrity,
        startup, policy, and explicit generation triggers may reconsider it.
        """
        inserted = (
            conn.execute(
                """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format,
              quality, max_long_edge, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
            ON CONFLICT(asset_id, kind, variant, source_mtime_ns, source_size) DO NOTHING
            """,
                (asset_id, kind, variant, source_mtime_ns, source_size, format, quality, max_long_edge),
            ).rowcount
            == 1
        )
        derivative = conn.execute(
            """
            SELECT id, status, cache_path, byte_size FROM asset_derivatives
            WHERE asset_id = ? AND kind = ? AND variant = ?
              AND source_mtime_ns = ? AND source_size = ?
            """,
            (asset_id, kind, variant, source_mtime_ns, source_size),
        ).fetchone()
        if derivative is None:
            raise RuntimeError("Derivative identity was not available after insert")
        derivative_id = int(derivative["id"])
        if derivative["status"] == "ready" and derivative["cache_path"] and Path(derivative["cache_path"]).is_file():
            return derivative_id, "ready"
        if derivative["status"] == "evicted" and derivative["cache_path"] and Path(derivative["cache_path"]).is_file():
            conn.execute(
                """
                UPDATE asset_derivatives
                SET status = 'ready', last_error = NULL, updated_at = julianday('now')
                WHERE id = ? AND status = 'evicted' AND cache_path = ?
                """,
                (derivative_id, derivative["cache_path"]),
            )
            return derivative_id, "ready"
        latest = conn.execute(
            "SELECT result_code FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
            (derivative_id,),
        ).fetchone()
        result_code = latest["result_code"] if latest is not None else None
        if (
            derivative["status"] in {"failed", "skipped"}
            and not retry_failed
            and not (derivative["status"] == "skipped" and result_code in {"source_missing", "asset_inactive"})
        ):
            return derivative_id, str(derivative["status"])
        job = conn.execute(
            """
            SELECT id, priority FROM derivative_jobs
            WHERE derivative_id = ? AND state IN ('queued', 'running')
            ORDER BY id DESC LIMIT 1
            """,
            (derivative_id,),
        ).fetchone()
        if job is not None:
            if priority < int(job["priority"]):
                conn.execute(
                    "UPDATE derivative_jobs SET priority = ?, updated_at = julianday('now') WHERE id = ?",
                    (priority, job["id"]),
                )
            return derivative_id, "active"
        if derivative["status"] in {"deferred_capacity", "evicted"} and deferrable and not reconsider_deferred_capacity:
            return derivative_id, "deferred_capacity"
        if inserted or derivative["status"] in {"deferred_capacity", "evicted"} or deferrable:
            estimated_bytes = estimated_bytes or self._estimate_new_derivative_bytes(conn)
            if not self._capacity_available(conn, estimated_bytes):
                conn.execute(
                    """
                    UPDATE asset_derivatives
                    SET status = 'deferred_capacity', cache_path = NULL, byte_size = NULL,
                        last_error = 'deferred: capacity unavailable', updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (derivative_id,),
                )
                return derivative_id, "capacity_needed_created" if inserted else "capacity_needed"
        conn.execute(
            "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, ?, 'queued')",
            (derivative_id, priority),
        )
        conn.execute(
            """
            UPDATE asset_derivatives
            SET status = 'queued', cache_path = NULL, byte_size = NULL, last_error = NULL,
                updated_at = julianday('now')
            WHERE id = ?
            """,
            (derivative_id,),
        )
        return derivative_id, "created" if inserted else "requeued"

    @maintenance_producer
    def schedule_derivative(
        self,
        asset_id: int,
        kind: str,
        variant: str,
        priority: int = 3,
        *,
        max_long_edge: int | None = None,
        quality: int | None = None,
        format: str = "webp",
    ) -> int:
        """Create or coalesce a derivative job and return its catalog ID."""
        if kind not in DERIVATIVE_VARIANTS:
            raise ValueError(f"Unsupported derivative kind: {kind}")
        priority = max(0, min(priority, 3))
        default_variant = DERIVATIVE_VARIANTS[kind][0]
        max_long_edge = max_long_edge or int(default_variant["max_long_edge"])
        quality = quality or int(default_variant["quality"])
        format = format or "webp"
        _ensure_database()
        with _connect() as conn:
            asset = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
        if asset is None:
            raise KeyError(asset_id)
        stat = Path(asset["path"]).stat()
        coalesce_args = {
            "asset_id": asset_id,
            "kind": kind,
            "variant": variant,
            "source_mtime_ns": stat.st_mtime_ns,
            "source_size": stat.st_size,
            "max_long_edge": max_long_edge,
            "quality": quality,
            "format": format,
            "priority": priority,
            "retry_failed": True,
            "deferrable": False,
        }
        with self._eviction_lock:
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute(
                    "SELECT 1 FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                    (asset_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(asset_id)
                estimated_bytes = self._estimate_new_derivative_bytes(conn)
                derivative_id, outcome = self._coalesce_derivative_job(
                    conn,
                    **coalesce_args,
                    estimated_bytes=estimated_bytes,
                )
            if outcome in {"capacity_needed", "capacity_needed_created"} and self._reserve_capacity(estimated_bytes):
                with _connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    derivative_id, outcome = self._coalesce_derivative_job(
                        conn,
                        **coalesce_args,
                        estimated_bytes=estimated_bytes,
                    )
        if outcome in {"created", "requeued", "active"}:
            self._wake_event.set()
        return derivative_id
