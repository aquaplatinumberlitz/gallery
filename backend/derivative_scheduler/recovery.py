"""Worker loop, supervision, and abandoned-claim recovery."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..catalog_maintenance_gate import maintenance_producer, producer_gate
from ..metadata_store import _connect
from ._common import (
    _MAX_ATTEMPTS,
    _SUPERVISOR_INTERVAL_SECONDS,
    _ensure_database,
    logger,
)


class RecoveryMixin:
    """Worker/supervisor loops and claim recovery for ``DerivativeScheduler``."""

    def _worker_loop(self, worker_id: str | None = None) -> None:
        while not self._stop_event.is_set():
            try:
                with producer_gate():
                    job = self._claim_job(worker_id)
                    if job is not None:
                        self._run_job(job)
            except Exception:  # noqa: BLE001
                logger.exception("Derivative worker could not process a job")
                self._stop_event.wait(0.5)
                continue
            if job is None:
                self._wake_event.wait(timeout=1)
                self._wake_event.clear()
                continue

    def _supervisor_loop(self) -> None:
        """Recover abandoned claims and restore the configured worker count."""
        while not self._stop_event.wait(_SUPERVISOR_INTERVAL_SECONDS):
            try:
                self._supervise_once()
            except Exception:  # noqa: BLE001
                logger.exception("Derivative supervisor iteration failed")

    @maintenance_producer
    def _supervise_once(self) -> None:
        dead_worker_ids: list[str] = []
        replacements: list[threading.Thread] = []
        with self._lifecycle_lock:
            alive: list[threading.Thread] = []
            alive_slots: set[int] = set()
            for thread in self._threads:
                slot = int(thread.name.rsplit("-", 1)[-1])
                if thread.is_alive():
                    alive.append(thread)
                    alive_slots.add(slot)
                else:
                    dead_worker_ids.append(self._worker_id(slot))
            for slot in range(1, self.worker_count + 1):
                if slot not in alive_slots and not self._stop_event.is_set():
                    replacement = self._new_worker(slot)
                    alive.append(replacement)
                    replacements.append(replacement)
            self._threads = alive
        for worker_id in dead_worker_ids:
            self._recover_running_jobs(claimed_by=worker_id)
        self._recover_running_jobs(expired_only=True)
        self._reconcile_queued_jobs()
        for thread in replacements:
            thread.start()
        if replacements:
            logger.warning("Restored %s derivative worker(s)", len(replacements))
            self._wake_event.set()

    def _reconcile_queued_jobs(self) -> None:
        """Terminalize queued work that no longer references an active/current source."""
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT j.id AS job_id, d.id AS derivative_id, d.source_mtime_ns, d.source_size,
                       a.id AS asset_id, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                LEFT JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                  AND (
                    a.id IS NULL OR a.type != 'image' OR a.deleted_at IS NOT NULL OR a.offline != 0
                    OR a.mtime_ns IS NULL OR a.size IS NULL
                    OR d.source_mtime_ns != a.mtime_ns OR d.source_size != a.size
                  )
                """
            ).fetchall()
            for row in rows:
                result_code = (
                    "asset_inactive"
                    if row["asset_id"] is None
                    or row["deleted_at"] is not None
                    or row["offline"]
                    or row["type"] != "image"
                    else "source_changed"
                )
                message = f"queued derivative is no longer applicable: {result_code}"
                transitioned = conn.execute(
                    """
                    UPDATE derivative_jobs SET state = 'skipped', result_code = ?, error = ?,
                      completed_at = julianday('now'), updated_at = julianday('now')
                    WHERE id = ? AND state = 'queued'
                    """,
                    (result_code, message, row["job_id"]),
                )
                if transitioned.rowcount == 1:
                    conn.execute(
                        "UPDATE asset_derivatives SET status = 'skipped', last_error = ?, "
                        "updated_at = julianday('now') WHERE id = ?",
                        (message, row["derivative_id"]),
                    )

    def _recover_running_jobs(self, *, claimed_by: str | None = None, expired_only: bool = False) -> int:
        """Recover abandoned claims using the same policy at startup and runtime."""
        _ensure_database()
        recovered = 0
        with _connect() as conn:
            clauses = ["j.state = 'running'"]
            params: list[Any] = []
            if claimed_by is not None:
                clauses.append("j.claimed_by = ?")
                params.append(claimed_by)
            elif expired_only:
                clauses.append("(j.lease_expires_at IS NULL OR j.lease_expires_at <= julianday('now'))")  # noqa: E501
            rows = conn.execute(
                f"""
                SELECT j.id AS job_id, j.attempts AS job_attempts, j.claim_token,
                       d.id AS derivative_id,
                       d.source_mtime_ns, d.source_size, a.id AS asset_id, a.path, a.type,
                       a.deleted_at, a.offline, a.mtime_ns, a.size
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                LEFT JOIN assets a ON a.id = d.asset_id
                WHERE {" AND ".join(clauses)}
                """,
                params,
            ).fetchall()
            for row in rows:
                result_code = self._inapplicable_result(row)
                if result_code is not None:
                    state = "skipped"
                elif int(row["job_attempts"]) >= _MAX_ATTEMPTS:
                    state, result_code = "failed", "attempts_exhausted"
                else:
                    state = "queued"
                message = f"recovered abandoned derivative claim: {result_code or 'retry'}"
                expiry_guard = (
                    " AND (lease_expires_at IS NULL OR lease_expires_at <= julianday('now'))" if expired_only else ""
                )
                transitioned = conn.execute(
                    f"""
                    UPDATE derivative_jobs SET state = ?, result_code = ?, error = ?,
                      claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                      started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                      completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                      updated_at = julianday('now')
                    WHERE id = ? AND state = 'running' AND claim_token IS ?{expiry_guard}
                    """,
                    (state, result_code, message, state, state, row["job_id"], row["claim_token"]),
                )
                if transitioned.rowcount == 1:
                    conn.execute(
                        "UPDATE asset_derivatives SET status = ?, last_error = ?, "
                        "updated_at = julianday('now') WHERE id = ?",
                        (state, message, row["derivative_id"]),
                    )
                    recovered += 1
        if recovered:
            self._wake_event.set()
        return recovered

    @staticmethod
    def _inapplicable_result(row: sqlite3.Row) -> str | None:
        if row["asset_id"] is None or row["deleted_at"] is not None or row["offline"] or row["type"] != "image":
            return "asset_inactive"
        path = Path(row["path"])
        try:
            stat = path.stat()
        except OSError:
            return "source_missing"
        if (
            stat.st_mtime_ns != int(row["source_mtime_ns"])
            or stat.st_size != int(row["source_size"])
            or row["mtime_ns"] is None
            or row["size"] is None
            or int(row["mtime_ns"]) != int(row["source_mtime_ns"])
            or int(row["size"]) != int(row["source_size"])
        ):
            return "source_changed"
        return None
