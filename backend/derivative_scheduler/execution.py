"""Claiming and rendering of a single durable derivative job."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import UnidentifiedImageError

from ..config import DERIVATIVE_LEASE_HEARTBEAT_SECONDS
from ..errors import APIError
from ..lease_heartbeat import LeaseHeartbeat
from ..metadata_store import _connect
from ..metadata_store.db_writer import LANE_PRIORITY, DatabaseWriterUnavailable, run_write
from ._common import (
    _MAX_ATTEMPTS,
    _ensure_database,
    _lease_days,
    logger,
)

if TYPE_CHECKING:
    from .core import DerivativeScheduler


class JobExecutionMixin:
    """Claim, lease, render, and failure handling for ``DerivativeScheduler``."""

    def run_once(self) -> bool:
        """Claim and execute one durable job for synchronous/test request fallback."""
        job = self._claim_job(f"request-{threading.get_ident()}")
        if job is None:
            return False
        self._run_job(job)
        return True

    def _claim_job(self, worker_id: str | None = None) -> sqlite3.Row | None:
        """Claim the next runnable job in one priority-lane writer op (a direct transaction with the flag off)."""
        _ensure_database()
        worker_id = worker_id or f"{self._instance_id}:{threading.current_thread().name}"

        def claim(conn: sqlite3.Connection) -> sqlite3.Row | None:
            row = conn.execute(
                """
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.*, a.path AS source_path
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                  AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                  AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
                ORDER BY j.priority ASC, j.created_at ASC, j.id ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["job_attempts"]) + 1
            claim_token = uuid.uuid4().hex
            conn.execute(
                """
                UPDATE derivative_jobs SET state = 'running', attempts = ?, started_at = julianday('now'),
                  completed_at = NULL, error = NULL, result_code = NULL, claimed_by = ?,
                  claim_token = ?, lease_expires_at = julianday('now') + ?,
                  updated_at = julianday('now') WHERE id = ? AND state = 'queued'
                """,
                (attempts, worker_id, claim_token, _lease_days(), row["job_id"]),
            )
            conn.execute(
                "UPDATE asset_derivatives SET status = 'running', attempts = ?, updated_at = julianday('now') WHERE id = ?",
                (attempts, row["id"]),
            )
            return conn.execute(
                """
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.*, a.path AS source_path,
                       j.claimed_by, j.claim_token, j.lease_expires_at
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                JOIN assets a ON a.id = d.asset_id
                WHERE j.id = ? AND j.claim_token = ?
                """,
                (row["job_id"], claim_token),
            ).fetchone()

        def claim_directly() -> sqlite3.Row | None:
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                return claim(conn)

        job = run_write(claim, lane=LANE_PRIORITY, fallback=claim_directly)
        if job is None:
            self._reconcile_queued_jobs()
        return job

    def _renew_lease(self, job_id: int, claim_token: str) -> bool:
        """Extend the lease of a still-running, still-owned derivative claim.

        Returns True only when the matching running row with the same claim token
        was found and updated. A claim that already completed, failed, or was
        fenced by recovery is not touched. A database error is recorded as a lease
        renewal failure but never overwrites the worker's render outcome; fenced
        recovery arbitrates instead.
        """
        _ensure_database()

        def renew(conn: sqlite3.Connection) -> bool:
            return (
                conn.execute(
                    """
                    UPDATE derivative_jobs
                    SET lease_expires_at = julianday('now') + ?
                    WHERE id = ? AND state = 'running' AND claim_token = ?
                    """,
                    (_lease_days(), job_id, claim_token),
                ).rowcount
                == 1
            )

        def renew_directly() -> bool:
            with _connect() as conn:  # never takes ``_DB_LOCK``: unrelated readers cannot starve a renewal
                return renew(conn)

        try:
            renewed = run_write(renew, lane=LANE_PRIORITY, fallback=renew_directly)
        except (sqlite3.Error, DatabaseWriterUnavailable):
            logger.warning("Derivative lease renewal failed for job %s", job_id)
            with self._lifecycle_lock:
                self._lease_renewal_failures += 1
                self._reconcile_status["lease_renewal_failures_total"] = self._lease_renewal_failures
            renewed = False
        if not renewed:
            logger.debug("Derivative lease renewal found no matching running claim for job %s", job_id)
        return renewed

    def _run_job(self, job: sqlite3.Row) -> None:
        from ..thumbnails import derivative_cache_path, generate_derivative

        source = Path(job["source_path"])
        cache_path: str | None = None
        succeeded = False
        heartbeat = _LeaseHeartbeat(self, job["job_id"], job["claim_token"], DERIVATIVE_LEASE_HEARTBEAT_SECONDS)
        try:
            self._validate_claimed_source(job, source)
            cache_path = str(
                derivative_cache_path(
                    source,
                    kind=job["kind"],
                    max_long_edge=int(job["max_long_edge"]),
                    quality=int(job["quality"]),
                    format=job["format"],
                )
            )
            with self._file_lock:
                self._generating_paths.add(cache_path)
            heartbeat.start()
            derivative_bytes = generate_derivative(
                source,
                kind=job["kind"],
                max_long_edge=int(job["max_long_edge"]),
                quality=int(job["quality"]),
                format=job["format"],
                no_upscale=True,
            )
            heartbeat.stop()
            self._validate_claimed_source(job, source)

            def complete(conn: sqlite3.Connection) -> bool:
                completed = conn.execute(
                    """
                        UPDATE derivative_jobs SET state = 'done', error = NULL, completed_at = julianday('now'),
                          result_code = NULL, claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                          updated_at = julianday('now') WHERE id = ? AND state = 'running' AND claim_token = ?
                        """,
                    (job["job_id"], job["claim_token"]),
                )
                if completed.rowcount != 1:
                    return False  # stale claim: nothing is written
                conn.execute(
                    """
                        UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ?,
                          last_accessed_at = julianday('now'), last_error = NULL, updated_at = julianday('now')
                        WHERE id = ?
                        """,
                    (cache_path, len(derivative_bytes), job["id"]),
                )
                return True

            def complete_directly() -> bool:
                with _connect() as conn:
                    return complete(conn)

            with self._eviction_lock:
                applied = run_write(complete, lane=LANE_PRIORITY, fallback=complete_directly)
            if not applied:
                logger.info("Ignored stale completion for derivative job %s", job["job_id"])
                return
            succeeded = True
        except Exception as exc:  # noqa: BLE001
            heartbeat.stop()
            self._handle_failure(job, exc)
        finally:
            if cache_path is not None:
                with self._file_lock:
                    self._generating_paths.discard(cache_path)
            if succeeded:
                self._enforce_quota()
                try:
                    from ..visual_fingerprints import notify_derivative_ready

                    notify_derivative_ready(int(job["asset_id"]))
                except Exception:  # noqa: BLE001
                    logger.exception("Could not queue visual fingerprint refresh for asset %s", job["asset_id"])

    def _validate_claimed_source(self, job: sqlite3.Row, source: Path) -> None:
        """Revalidate applicability after claim and before cache/render work."""
        with _connect() as conn:
            asset = conn.execute(
                "SELECT path, mtime_ns, size FROM assets "
                "WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (job["asset_id"],),
            ).fetchone()
        if asset is None:
            raise _DerivativeSkip("asset_inactive", "asset is deleted, offline, or no longer an image")
        try:
            stat = source.stat()
        except FileNotFoundError as exc:
            raise _DerivativeSkip("source_missing", f"source file is missing: {source}") from exc
        if (
            str(asset["path"]) != str(source)
            or stat.st_mtime_ns != int(job["source_mtime_ns"])
            or stat.st_size != int(job["source_size"])
        ):
            raise _DerivativeSkip("source_changed", "source identity changed after derivative was queued")

    def _handle_failure(self, job: sqlite3.Row, exc: Exception) -> None:
        attempts = int(job["job_attempts"])
        if isinstance(exc, _DerivativeSkip):
            state, result_code, retry = "skipped", exc.result_code, False
        elif isinstance(exc, (FileNotFoundError,)):
            state, result_code, retry = "skipped", "source_missing", False
        elif isinstance(exc, UnidentifiedImageError) or (isinstance(exc, APIError) and exc.status_code < 500):
            state, result_code, retry = "failed", "invalid_source", False
        else:
            transient = isinstance(exc, (OSError, sqlite3.OperationalError, DatabaseWriterUnavailable))
            retry = transient and attempts < _MAX_ATTEMPTS and not self._stop_event.is_set()
            state = "queued" if retry else "failed"
            result_code = None if retry else ("attempts_exhausted" if transient else "internal_error")
        if retry:
            self._stop_event.wait(2 ** (attempts - 1))

        def fail(conn: sqlite3.Connection) -> bool:
            transitioned = conn.execute(
                """
                UPDATE derivative_jobs SET state = ?, error = ?, result_code = ?,
                  completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                  started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                  claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                  updated_at = julianday('now')
                WHERE id = ? AND state = 'running' AND claim_token = ?
                """,
                (state, str(exc), result_code, state, state, job["job_id"], job["claim_token"]),
            )
            if transitioned.rowcount != 1:
                return False  # stale claim: nothing is written
            conn.execute(
                "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
                (state, str(exc), job["id"]),
            )
            return True

        def fail_directly() -> bool:
            with _connect() as conn:
                return fail(conn)

        if not run_write(fail, lane=LANE_PRIORITY, fallback=fail_directly):
            logger.info("Ignored stale failure for derivative job %s", job["job_id"])
            return
        if retry:
            self._wake_event.set()
        elif state == "skipped":
            logger.info("Derivative job %s skipped (%s): %s", job["job_id"], result_code, exc)
        else:
            logger.warning("Derivative job %s failed permanently (%s): %s", job["job_id"], result_code, exc)


class _LeaseHeartbeat(LeaseHeartbeat):
    """Lease renewal owned by one claimed derivative job.

    The generic ``LeaseHeartbeat`` (``backend/lease_heartbeat.py``) runs on its own daemon thread
    and renews ``lease_expires_at`` at most every ``interval_seconds``. ``_renew_lease`` only
    updates a row that is still ``running`` with the same claim token, so a long render cannot be
    duplicated by expired-claim recovery while the heartbeat is healthy. The heartbeat stops before
    the worker persists its terminal outcome; a failed renewal is logged, not used to overwrite
    render state.
    """

    def __init__(self, scheduler: DerivativeScheduler, job_id: int, claim_token: str, interval_seconds: float):
        self._scheduler = scheduler
        self._job_id = job_id
        self._claim_token = claim_token
        super().__init__(
            lambda: self._scheduler._renew_lease(self._job_id, self._claim_token),
            interval_seconds,
            name=f"derivative-lease-{job_id}",
        )


class _DerivativeSkip(Exception):
    """Controlled terminal outcome for work that is no longer applicable."""

    def __init__(self, result_code: str, message: str):
        super().__init__(message)
        self.result_code = result_code
