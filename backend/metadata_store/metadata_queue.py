"""Metadata indexing job queue helpers."""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..config import GALLERY_CATALOG_WRITE_BATCH_SIZE, METADATA_JOB_LEASE_SECONDS
from ..files import is_image_path, is_index_excluded_path
from ..metadata_extract import metadata_sidecar_identity
from ._db import _DB_LOCK, MAX_METADATA_JOB_ATTEMPTS, METADATA_JOB_STATES, _connect
from .db_writer import LANE_PRIORITY, run_write
from .identity import (
    asset_params_match_sql,
    image_metadata_params_match_sql,
)
from .path_utils import path_scope_sql
from .types import MetadataIndexJob, MetadataQueueResult

_MIN_REASONABLE_MTIME_NS = 1_000_000_000_000
# Cleared on every transition out of ``running`` so a stale worker's token can never match again.
_CLEAR_CLAIM_SQL = "claimed_by=NULL, claim_token=NULL, lease_expires_at=NULL"


def metadata_now() -> float:
    """Return the clock used for metadata job leases, backoff, and recovery (tests replace it)."""
    return time.time()


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _claim_fence(job: MetadataIndexJob) -> tuple[str, list[Any]]:
    """Return the SQL suffix that fences a write to the claim ``job`` was started with.

    A job that carries a claim token (every job from ``claim_next_metadata_job``) may only change a
    row that is still ``running`` under that same token, so a worker that lost its claim to lease
    recovery writes zero rows. Token-less jobs (legacy and the already-current shortcut) keep the
    identity-only behaviour.
    """
    if job.claim_token is None:
        return "", []
    return " AND state = 'running' AND claim_token = ?", [job.claim_token]


def _claim_is_abandoned(row: sqlite3.Row | dict[str, Any], now: float) -> bool:
    """Return whether a ``running`` row has no live claim: no owner token or an expired/missing lease."""
    return row["claim_token"] is None or row["lease_expires_at"] is None or float(row["lease_expires_at"]) <= now


def _image_metadata_exists_for_job(
    conn: sqlite3.Connection,
    path: str,
    mtime: float,
    size: int,
    mtime_ns: int | None = None,
) -> bool:
    """Return whether image_metadata exists for the given job identity.

    Uses the canonical three-branch identity rule:
    - ns match when both sides have mtime_ns,
    - seconds bridge when one side has NULL mtime_ns.
    """
    row = conn.execute(
        f"""
        SELECT source_path, source_mtime_ns, source_size FROM image_metadata
        WHERE path = ?
          AND ({image_metadata_params_match_sql()})
          AND size = ?
        """,
        (path, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime, size),
    ).fetchone()
    if row is None:
        return False
    return tuple(row) == metadata_sidecar_identity(Path(path))


def _current_metadata_is_complete(
    conn: sqlite3.Connection,
    path: str,
    mtime: float,
    size: int,
    mtime_ns: int | None = None,
) -> bool:
    return _image_metadata_exists_for_job(conn, path, mtime, size, mtime_ns)


def _metadata_job_from_path(path_value: str | Path, root_path: str | Path | None = None) -> MetadataIndexJob | None:
    path = Path(path_value)
    if is_index_excluded_path(path) or not is_image_path(path):
        return None
    try:
        stat = path.stat()
        resolved_path = path.resolve()
        parent = resolved_path.parent
    except OSError:
        return None
    resolved_root = str(Path(root_path).resolve()) if root_path is not None else str(parent)
    return MetadataIndexJob(
        path=str(resolved_path),
        name=resolved_path.name,
        parent_path=str(parent),
        folder_path=str(parent),
        root_path=resolved_root,
        mtime=stat.st_mtime,
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
    )


def _mark_current_metadata_done(conn: sqlite3.Connection, job: MetadataIndexJob, now: float) -> None:
    """Mark one metadata job done and materialize assets.metadata_state='done'.

    This is called by the "already current" shortcut in _persist_metadata_index_jobs.
    Makes the job row exist and then delegates to complete_metadata_job so all
    completion verification logic lives in one place.
    """
    # Backfill library_id from matching assets row
    library_row = conn.execute(
        "SELECT library_id FROM assets WHERE path = ?",
        (job.path,),
    ).fetchone()
    library_id = int(library_row["library_id"]) if library_row else None

    # Ensure the job row exists (INSERT/UPDATE for paths without queued jobs)
    conn.execute(
        """
        INSERT INTO metadata_index_jobs (
          path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size, state,
          attempts, error, queued_at, started_at, finished_at, updated_at,
          priority, library_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', 0, NULL, ?, NULL, NULL, ?,
                  3, ?)
        ON CONFLICT(path) DO UPDATE SET
          name=excluded.name,
          parent_path=excluded.parent_path,
          folder_path=excluded.folder_path,
          root_path=excluded.root_path,
          mtime=excluded.mtime,
          mtime_ns=excluded.mtime_ns,
          size=excluded.size,
          state=CASE WHEN metadata_index_jobs.state = 'done' THEN 'done' ELSE 'running' END,
          error=NULL,
          updated_at=excluded.updated_at,
          library_id=COALESCE(metadata_index_jobs.library_id, excluded.library_id)
        """,
        (
            job.path,
            job.name,
            job.parent_path,
            job.folder_path,
            job.root_path,
            job.mtime,
            job.mtime_ns,
            job.size,
            now,
            now,
            library_id,
        ),
    )
    complete_metadata_job(conn, job)


def _update_asset_done(conn: sqlite3.Connection, job: MetadataIndexJob, now: float) -> None:
    """Update assets.metadata_state='done' for the given job identity.

    Two branches (assets has no ``mtime`` column):
    - ns match when both sides have mtime_ns,
    - seconds bridge when the job has no mtime_ns but assets has mtime_ns.
    """
    conn.execute(
        f"""
        UPDATE assets
        SET metadata_state='done'
        WHERE path=?
          AND ({asset_params_match_sql()})
          AND size=?
        """,
        (job.path, job.mtime_ns, job.mtime_ns, job.mtime_ns, job.mtime, job.size),
    )


_EXISTING_JOB_SQL = """
    SELECT mtime, mtime_ns, size, state, attempts, priority, library_id, claim_token, lease_expires_at
    FROM metadata_index_jobs
    WHERE path = ?
"""


def _persist_metadata_index_job_batch(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    priority: int = 3,
    catalog_claim_job_id: int | None = None,
    catalog_claim_token: str | None = None,
    catalog_claim_lease_seconds: float = 900,
) -> MetadataQueueResult:
    """Persist one bounded metadata-job batch and refresh its catalog claim."""
    if (catalog_claim_job_id is None) != (catalog_claim_token is None):
        raise ValueError("Catalog claim job id and token must be provided together")
    priority = max(0, min(priority, 3))
    jobs = [job for path in paths if (job := _metadata_job_from_path(path, root_path))]
    if not jobs:
        return MetadataQueueResult(enqueued=[])

    _initialize_database()
    enqueued: list[MetadataIndexJob] = []
    coalesced = 0
    skipped = 0
    failed = 0
    now = metadata_now()

    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if catalog_claim_job_id is not None and catalog_claim_token is not None:
            from .job_store import assert_catalog_job_claim_conn

            assert_catalog_job_claim_conn(conn, catalog_claim_job_id, catalog_claim_token)
        for job in jobs:
            if _current_metadata_is_complete(conn, job.path, job.mtime, job.size, job.mtime_ns):
                _mark_current_metadata_done(conn, job, now)
                skipped += 1
                continue

            # Backfill library_id from matching assets row
            library_row = conn.execute(
                "SELECT library_id FROM assets WHERE path = ?",
                (job.path,),
            ).fetchone()
            library_id = int(library_row["library_id"]) if library_row else None

            existing = conn.execute(_EXISTING_JOB_SQL, (job.path,)).fetchone()

            if existing:
                if existing["mtime_ns"] is not None and job.mtime_ns is not None:
                    same_version = existing["mtime_ns"] == job.mtime_ns and existing["size"] == job.size
                else:
                    same_version = existing["mtime"] == job.mtime and existing["size"] == job.size
                if not same_version:
                    existing = None
                else:
                    if existing["state"] == "running" and _claim_is_abandoned(existing, now):
                        # Nobody owns this claim any more: recover it (attempt-aware) instead of
                        # coalescing into a job that will never finish, then continue with its new state.
                        recover_running_metadata_jobs(conn, expired_only=True, now=now, paths=[job.path])
                        existing = conn.execute(_EXISTING_JOB_SQL, (job.path,)).fetchone()
                    state = existing["state"]
                    attempts = int(existing["attempts"] or 0)
                    if state in {"queued", "running"}:
                        # Keep the higher (lower numeric) priority
                        existing_priority = int(existing["priority"] or 3)
                        existing_library_id = existing["library_id"]
                        updates = []
                        upd_params: list = []
                        if priority < existing_priority:
                            updates.append("priority = ?")
                            upd_params.append(priority)
                        if library_id is not None and existing_library_id is None:
                            updates.append("library_id = ?")
                            upd_params.append(library_id)
                        if updates:
                            updates.append("updated_at = ?")
                            upd_params.append(now)
                            upd_params.append(job.path)
                            conn.execute(
                                f"UPDATE metadata_index_jobs SET {', '.join(updates)} WHERE path = ?",
                                upd_params,
                            )
                        coalesced += 1
                        continue
                    if state == "failed" and attempts >= MAX_METADATA_JOB_ATTEMPTS:
                        failed += 1
                        continue
                    if state == "done" and _current_metadata_is_complete(
                        conn, job.path, job.mtime, job.size, job.mtime_ns
                    ):
                        skipped += 1
                        continue

            conn.execute(
                """
                INSERT INTO metadata_index_jobs (
                  path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size,
                  state, attempts, error, queued_at, started_at, finished_at, updated_at,
                  priority, library_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, ?, NULL, NULL, ?,
                          ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  name=excluded.name,
                  parent_path=excluded.parent_path,
                  folder_path=excluded.folder_path,
                  root_path=excluded.root_path,
                  mtime=excluded.mtime,
                  mtime_ns=excluded.mtime_ns,
                  size=excluded.size,
                  state='queued',
                  attempts=CASE
                    WHEN metadata_index_jobs.mtime_ns IS NOT NULL AND excluded.mtime_ns IS NOT NULL
                      AND metadata_index_jobs.mtime_ns = excluded.mtime_ns
                      AND metadata_index_jobs.size = excluded.size
                    THEN metadata_index_jobs.attempts
                    WHEN metadata_index_jobs.mtime_ns IS NULL AND excluded.mtime_ns IS NULL
                      AND metadata_index_jobs.mtime = excluded.mtime
                      AND metadata_index_jobs.size = excluded.size
                    THEN metadata_index_jobs.attempts
                    ELSE 0
                  END,
                  error=NULL,
                  queued_at=excluded.queued_at,
                  started_at=NULL,
                  finished_at=NULL,
                  updated_at=excluded.updated_at,
                  claimed_by=NULL,
                  claim_token=NULL,
                  lease_expires_at=NULL,
                  next_attempt_at=NULL,
                  priority=CASE
                    WHEN COALESCE(metadata_index_jobs.priority, 3) > ?
                    THEN ?
                    ELSE metadata_index_jobs.priority
                  END,
                  library_id=COALESCE(metadata_index_jobs.library_id, excluded.library_id)
                """,
                (
                    job.path,
                    job.name,
                    job.parent_path,
                    job.folder_path,
                    job.root_path,
                    job.mtime,
                    job.mtime_ns,
                    job.size,
                    now,
                    now,
                    priority,
                    library_id,
                    priority,
                    priority,
                ),
            )
            enqueued.append(job)

        if catalog_claim_job_id is not None and catalog_claim_token is not None:
            from .job_store import refresh_catalog_job_claim_before_commit_conn

            refresh_catalog_job_claim_before_commit_conn(
                conn,
                catalog_claim_job_id,
                catalog_claim_token,
                lease_seconds=catalog_claim_lease_seconds,
            )

    return MetadataQueueResult(enqueued=enqueued, coalesced=coalesced, skipped=skipped, failed=failed)


def _persist_metadata_index_jobs(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    priority: int = 3,
    catalog_claim_job_id: int | None = None,
    catalog_claim_token: str | None = None,
    catalog_claim_lease_seconds: float = 900,
) -> MetadataQueueResult:
    """Create/coalesce metadata jobs in bounded claim-refreshing transactions."""
    path_list = list(paths)
    if not path_list:
        return MetadataQueueResult(enqueued=[])
    enqueued: list[MetadataIndexJob] = []
    coalesced = 0
    skipped = 0
    failed = 0
    batch_size = max(1, GALLERY_CATALOG_WRITE_BATCH_SIZE)
    for start in range(0, len(path_list), batch_size):
        result = _persist_metadata_index_job_batch(
            path_list[start : start + batch_size],
            root_path,
            priority=priority,
            catalog_claim_job_id=catalog_claim_job_id,
            catalog_claim_token=catalog_claim_token,
            catalog_claim_lease_seconds=catalog_claim_lease_seconds,
        )
        enqueued.extend(result.enqueued)
        coalesced += result.coalesced
        skipped += result.skipped
        failed += result.failed
    return MetadataQueueResult(enqueued=enqueued, coalesced=coalesced, skipped=skipped, failed=failed)


def mark_metadata_jobs_running(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as running and increment their attempt counts."""
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        for job in rows:
            if job.mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='running',
                        attempts=attempts + 1,
                        error=NULL,
                        started_at=?,
                        finished_at=NULL,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=?
                    """,
                    (now, now, job.path, job.mtime_ns, job.size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='running',
                        attempts=attempts + 1,
                        error=NULL,
                        started_at=?,
                        finished_at=NULL,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=?
                    """,
                    (now, now, job.path, job.mtime, job.size),
                )


def mark_metadata_jobs_done(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as successfully completed (batch path).

    Verifies image_metadata is current for each job before marking done.
    If image_metadata is not current, marks the job stale instead.
    Also materializes assets.metadata_state='done' per job.
    """
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        for job in rows:
            if not _image_metadata_exists_for_job(conn, job.path, job.mtime, job.size, job.mtime_ns):
                if job.mtime_ns is not None:
                    conn.execute(
                        """
                        UPDATE metadata_index_jobs
                        SET state='stale',
                            error=NULL,
                            finished_at=?,
                            updated_at=?
                        WHERE path=? AND mtime_ns = ? AND size=?
                        """,
                        (now, now, job.path, job.mtime_ns, job.size),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE metadata_index_jobs
                        SET state='stale',
                            error=NULL,
                            finished_at=?,
                            updated_at=?
                        WHERE path=? AND mtime=? AND size=?
                        """,
                        (now, now, job.path, job.mtime, job.size),
                    )
                continue

            if job.mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='done',
                        error=NULL,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=?
                    """,
                    (now, now, job.path, job.mtime_ns, job.size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='done',
                        error=NULL,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=?
                    """,
                    (now, now, job.path, job.mtime, job.size),
                )
            _update_asset_done(conn, job, now)


def mark_metadata_jobs_stale(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs stale when the file version no longer matches."""
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        for job in rows:
            if job.mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='stale',
                        error=NULL,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=?
                    """,
                    (now, now, job.path, job.mtime_ns, job.size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='stale',
                        error=NULL,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=?
                    """,
                    (now, now, job.path, job.mtime, job.size),
                )


def mark_metadata_jobs_failed(errors: Iterable[tuple[MetadataIndexJob, str]]) -> None:
    """Mark durable metadata jobs failed with a bounded error message."""
    rows = [(job, error[:1000]) for job, error in errors]
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        for job, error in rows:
            if job.mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='failed',
                        error=?,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=?
                    """,
                    (error, now, now, job.path, job.mtime_ns, job.size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='failed',
                        error=?,
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=?
                    """,
                    (error, now, now, job.path, job.mtime, job.size),
                )


# ---------------------------------------------------------------------------
# DB-claim worker primitives (Phase 1)
# ---------------------------------------------------------------------------


def _claim_metadata_jobs_conn(
    conn: sqlite3.Connection,
    limit: int,
    *,
    worker_id: str | None,
    lease_seconds: float,
    now: float | None,
) -> list[MetadataIndexJob]:
    """Claim up to ``limit`` due queued jobs inside the caller's write transaction.

    Rows come in the exact order of repeated single claims (``priority``, ``queued_at``, ``path``);
    rows whose ``next_attempt_at`` (retry backoff) lies in the future are not due. Every claimed job
    gets its own claim token and ``lease_seconds`` lease, and its attempt count is incremented.
    """
    claimed_at = metadata_now() if now is None else float(now)
    rows = conn.execute(
        """
        SELECT path, name, parent_path, folder_path, root_path,
               mtime, mtime_ns, size, state, attempts,
               queued_at, started_at, finished_at, updated_at, library_id, priority
        FROM metadata_index_jobs
        WHERE state = 'queued'
          AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        ORDER BY priority ASC, queued_at ASC, path ASC
        LIMIT ?
        """,
        (claimed_at, limit),
    ).fetchall()
    owner = worker_id or "metadata-worker"
    jobs: list[MetadataIndexJob] = []
    for row in rows:
        attempts = int(row["attempts"]) + 1
        claim_token = uuid.uuid4().hex
        identity_sql, identity_params = (
            ("mtime_ns = ? AND size = ?", (row["mtime_ns"], row["size"]))
            if row["mtime_ns"] is not None
            else ("mtime = ? AND size = ?", (row["mtime"], row["size"]))
        )
        conn.execute(
            f"""
            UPDATE metadata_index_jobs
            SET state='running',
                attempts=?,
                started_at=?,
                finished_at=NULL,
                updated_at=?,
                claimed_by=?,
                claim_token=?,
                lease_expires_at=?,
                next_attempt_at=NULL
            WHERE path=? AND {identity_sql} AND state='queued'
            """,
            (
                attempts,
                claimed_at,
                claimed_at,
                owner,
                claim_token,
                claimed_at + lease_seconds,
                row["path"],
                *identity_params,
            ),
        )
        jobs.append(
            MetadataIndexJob(
                path=row["path"],
                name=row["name"],
                parent_path=row["parent_path"],
                folder_path=row["folder_path"],
                root_path=row["root_path"],
                mtime=row["mtime"],
                mtime_ns=row["mtime_ns"],
                size=row["size"],
                library_id=row["library_id"],
                attempts=attempts,
                claim_token=claim_token,
                claimed_by=owner,
            )
        )
    return jobs


def claim_next_metadata_jobs(
    limit: int,
    *,
    worker_id: str | None = None,
    lease_seconds: float | None = None,
    now: float | None = None,
) -> list[MetadataIndexJob]:
    """Claim up to ``limit`` due queued metadata jobs from SQLite in one short write transaction.

    Mirrors ``DerivativeScheduler._claim_job`` (``derivative_scheduler/execution.py``): each claim
    records the owner (``worker_id``), its own claim token, and a lease. The claim is one priority-lane
    database writer op (or, with the writer flag off, one direct ``BEGIN IMMEDIATE`` transaction), so
    claiming K jobs costs one transaction. Returns fewer than ``limit`` jobs when fewer are due.
    """
    if limit < 1:
        return []
    _initialize_database()
    lease = float(METADATA_JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds)

    def claim(conn: sqlite3.Connection) -> list[MetadataIndexJob]:
        return _claim_metadata_jobs_conn(conn, limit, worker_id=worker_id, lease_seconds=lease, now=now)

    def claim_directly() -> list[MetadataIndexJob]:
        with _DB_LOCK, _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return claim(conn)

    return run_write(claim, lane=LANE_PRIORITY, fallback=claim_directly)


def claim_next_metadata_job(
    *,
    max_queue_wait_seconds: int = 600,
    worker_id: str | None = None,
    lease_seconds: float | None = None,
    now: float | None = None,
) -> MetadataIndexJob | None:
    """Claim one due queued metadata job from SQLite in a short write transaction.

    The single-job form of ``claim_next_metadata_jobs``. Returns ``None`` when no job is available.
    """
    jobs = claim_next_metadata_jobs(1, worker_id=worker_id, lease_seconds=lease_seconds, now=now)
    return jobs[0] if jobs else None


def release_metadata_job_claims(jobs: Iterable[MetadataIndexJob]) -> int:
    """Give claimed-but-never-started jobs back to the queue without consuming an attempt.

    Used when a worker that claimed a batch stops before reaching its later jobs. Fenced by each
    job's claim token (a job whose claim was already recovered is left alone); keeps ``queued_at`` so
    the queue order is unchanged. Returns how many jobs were released.
    """
    claimed = [job for job in jobs if job.claim_token is not None]
    if not claimed:
        return 0
    _initialize_database()

    def release(conn: sqlite3.Connection) -> int:
        now = metadata_now()
        released = 0
        for job in claimed:
            result = conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='queued',
                    attempts=MAX(attempts - 1, 0),
                    started_at=NULL,
                    finished_at=NULL,
                    updated_at=?,
                    next_attempt_at=NULL,
                    {_CLEAR_CLAIM_SQL}
                WHERE path=? AND state='running' AND claim_token=?
                """,
                (now, job.path, job.claim_token),
            )
            released += result.rowcount
        return released

    def release_directly() -> int:
        with _DB_LOCK, _connect() as conn:
            return release(conn)

    return run_write(release, lane=LANE_PRIORITY, fallback=release_directly)


def renew_metadata_job_lease(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    *,
    lease_seconds: float | None = None,
    now: float | None = None,
) -> bool:
    """Extend the lease of a still-running, still-owned claim; return whether this claim was renewed."""
    if job.claim_token is None:
        return False
    lease = float(METADATA_JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds)
    renewed_at = metadata_now() if now is None else float(now)
    result = conn.execute(
        """
        UPDATE metadata_index_jobs SET lease_expires_at = ?
        WHERE path = ? AND state = 'running' AND claim_token = ?
        """,
        (renewed_at + lease, job.path, job.claim_token),
    )
    return result.rowcount == 1


def owns_metadata_job_claim(conn: sqlite3.Connection, job: MetadataIndexJob) -> bool:
    """Return whether ``job`` still holds its claim (token-less legacy jobs always do)."""
    if job.claim_token is None:
        return True
    return (
        conn.execute(
            "SELECT 1 FROM metadata_index_jobs WHERE path = ? AND state = 'running' AND claim_token = ?",
            (job.path, job.claim_token),
        ).fetchone()
        is not None
    )


def complete_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
) -> bool:
    """Mark one metadata job done and materialize assets.metadata_state='done'.

    Enforces the invariant: image_metadata current + job done + asset done.
    If no asset row exists for the path the job is marked skipped.
    If the asset row exists but the version does not match the job is marked stale.
    Verifies that image_metadata exists for the job's identity before marking done.

    Every job write is fenced by the claim token, so a worker whose claim was recovered and
    reissued changes nothing (no job transition and no asset stamp). Returns whether the
    transition was applied.
    """
    if not _image_metadata_exists_for_job(conn, job.path, job.mtime, job.size, job.mtime_ns):
        return mark_metadata_job_stale(conn, job)

    now = metadata_now()
    fence_sql, fence_params = _claim_fence(job)

    # Check whether a matching asset row exists
    # Two branches: assets has no ``mtime`` column, so the seconds bridge
    # only goes one direction (job has NULL mtime_ns → convert assets.mtime_ns).
    asset_match = conn.execute(
        f"""
        SELECT 1 FROM assets
        WHERE path=?
          AND ({asset_params_match_sql()})
          AND size=?
        """,
        (job.path, job.mtime_ns, job.mtime_ns, job.mtime_ns, job.mtime, job.size),
    ).fetchone()

    if asset_match is None:
        any_asset = conn.execute(
            "SELECT 1 FROM assets WHERE path = ?",
            (job.path,),
        ).fetchone()
        if any_asset is None:
            skipped = conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='skipped', error=NULL, finished_at=?, updated_at=?, {_CLEAR_CLAIM_SQL}
                WHERE path=?
                  AND ({image_metadata_params_match_sql()})
                  AND size=?{fence_sql}
                """,
                (
                    now,
                    now,
                    job.path,
                    job.mtime_ns,
                    job.mtime_ns,
                    job.mtime_ns,
                    job.mtime_ns,
                    job.mtime_ns,
                    job.mtime,
                    job.size,
                    *fence_params,
                ),
            )
            return skipped.rowcount == 1
        return mark_metadata_job_stale(conn, job)

    completed = conn.execute(
        f"""
        UPDATE metadata_index_jobs
        SET state='done',
            error=NULL,
            finished_at=?,
            updated_at=?,
            next_attempt_at=NULL,
            {_CLEAR_CLAIM_SQL}
        WHERE path=?
          AND ({image_metadata_params_match_sql()})
          AND size=?{fence_sql}
        """,
        (
            now,
            now,
            job.path,
            job.mtime_ns,
            job.mtime_ns,
            job.mtime_ns,
            job.mtime_ns,
            job.mtime_ns,
            job.mtime,
            job.size,
            *fence_params,
        ),
    )
    applied = completed.rowcount == 1
    if applied or job.claim_token is None:
        _update_asset_done(conn, job, now)
    return applied


def fail_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    error: str,
) -> bool:
    """Mark one metadata job as failed with a bounded error message (fenced by the claim token)."""
    now = metadata_now()
    fence_sql, fence_params = _claim_fence(job)
    identity_sql, identity_params = _job_identity_sql(job)
    result = conn.execute(
        f"""
        UPDATE metadata_index_jobs
        SET state='failed',
            error=?,
            finished_at=?,
            updated_at=?,
            next_attempt_at=NULL,
            {_CLEAR_CLAIM_SQL}
        WHERE path=? AND {identity_sql}{fence_sql}
        """,
        (error[:1000], now, now, job.path, *identity_params, *fence_params),
    )
    return result.rowcount == 1


def requeue_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    error: str,
    *,
    delay_seconds: float,
    now: float | None = None,
) -> bool:
    """Return a failed-transiently running job to ``queued`` with a retry backoff.

    Stores the earliest next attempt (``next_attempt_at``) so claims ignore the row until it is
    due, keeps ``attempts`` and ``queued_at`` (priority order), and releases the claim. Fenced by
    the claim token: a worker that lost its claim cannot requeue the newer one.
    """
    ts = metadata_now() if now is None else float(now)
    fence_sql, fence_params = _claim_fence(job)
    identity_sql, identity_params = _job_identity_sql(job)
    result = conn.execute(
        f"""
        UPDATE metadata_index_jobs
        SET state='queued',
            error=?,
            started_at=NULL,
            finished_at=NULL,
            updated_at=?,
            next_attempt_at=?,
            {_CLEAR_CLAIM_SQL}
        WHERE path=? AND {identity_sql} AND state='running'{fence_sql}
        """,
        (error[:1000], ts, ts + max(0.0, float(delay_seconds)), job.path, *identity_params, *fence_params),
    )
    return result.rowcount == 1


def mark_metadata_job_stale(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
) -> bool:
    """Mark one metadata job stale when the file version no longer matches (fenced by the claim token)."""
    now = metadata_now()
    fence_sql, fence_params = _claim_fence(job)
    identity_sql, identity_params = _job_identity_sql(job)
    result = conn.execute(
        f"""
        UPDATE metadata_index_jobs
        SET state='stale',
            error=NULL,
            finished_at=?,
            updated_at=?,
            next_attempt_at=NULL,
            {_CLEAR_CLAIM_SQL}
        WHERE path=? AND {identity_sql}{fence_sql}
        """,
        (now, now, job.path, *identity_params, *fence_params),
    )
    return result.rowcount == 1


def _job_identity_sql(job: MetadataIndexJob) -> tuple[str, tuple[Any, ...]]:
    """Return the ``mtime_ns``/``mtime`` + size identity predicate of a job row."""
    if job.mtime_ns is not None:
        return "mtime_ns = ? AND size = ?", (job.mtime_ns, job.size)
    return "mtime = ? AND size = ?", (job.mtime, job.size)


def recover_running_metadata_jobs(
    conn: sqlite3.Connection,
    *,
    expired_only: bool,
    now: float | None = None,
    paths: Iterable[str] | None = None,
) -> dict[str, int]:
    """Requeue (or fail, when attempts are exhausted) ``running`` jobs nobody owns any more.

    The one recovery policy shared by the metadata supervisor (``expired_only=True``: only rows
    with no claim token or an expired/missing lease, live claims stay protected), dispatch and the
    integrity checker (``expired_only=True``, optionally restricted to ``paths``), and startup
    recovery (``expired_only=False``: after a restart no worker can own any claim). Each row is
    transitioned with a write fenced by the claim token it was read with (and, when
    ``expired_only``, by the expiry condition again), so a heartbeat renewal or a completion that
    lands between the read and the write wins. Returns ``{"reset": n, "failed": n}``.
    """
    ts = metadata_now() if now is None else float(now)
    expiry_sql = "(claim_token IS NULL OR lease_expires_at IS NULL OR lease_expires_at <= ?)"
    clauses = ["state = 'running'"]
    params: list[Any] = []
    if expired_only:
        clauses.append(expiry_sql)
        params.append(ts)
    path_list = None if paths is None else list(paths)
    if path_list is not None:
        if not path_list:
            return {"reset": 0, "failed": 0}
        clauses.append(f"path IN ({','.join('?' for _ in path_list)})")
        params.extend(path_list)
    rows = conn.execute(
        f"SELECT path, attempts, claim_token FROM metadata_index_jobs WHERE {' AND '.join(clauses)}",
        params,
    ).fetchall()
    reset = failed = 0
    guard_sql = f" AND {expiry_sql}" if expired_only else ""
    guard_params: list[Any] = [ts] if expired_only else []
    for row in rows:
        if int(row["attempts"] or 0) >= MAX_METADATA_JOB_ATTEMPTS:
            result = conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='failed', error=?, finished_at=?, updated_at=?, next_attempt_at=NULL, {_CLEAR_CLAIM_SQL}
                WHERE path=? AND state='running' AND claim_token IS ?{guard_sql}
                """,
                ("exhausted recovery attempts", ts, ts, row["path"], row["claim_token"], *guard_params),
            )
            failed += result.rowcount
        else:
            result = conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='queued', started_at=NULL, finished_at=NULL, updated_at=?, next_attempt_at=NULL,
                    {_CLEAR_CLAIM_SQL}
                WHERE path=? AND state='running' AND claim_token IS ?{guard_sql}
                """,
                (ts, row["path"], row["claim_token"], *guard_params),
            )
            reset += result.rowcount
    return {"reset": reset, "failed": failed}


def list_recoverable_metadata_jobs(
    conn: sqlite3.Connection,
    states: tuple[str, ...],
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """List metadata_index_jobs rows matching the given states, bounded by limit.

    Pass ``limit=0`` to return all matching rows (no LIMIT clause).
    """
    placeholders = ",".join("?" for _ in states)
    limit_clause = "" if limit == 0 else "LIMIT ?"
    params = list(states)
    if limit != 0:
        params.append(limit)
    rows = conn.execute(
        f"""
        SELECT path, name, parent_path, folder_path, root_path,
               mtime, mtime_ns, size, state, attempts,
               queued_at, started_at, finished_at, updated_at, library_id, priority
        FROM metadata_index_jobs
        WHERE state IN ({placeholders})
        ORDER BY updated_at ASC
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def reset_running_jobs_to_queued(
    conn: sqlite3.Connection,
    job_paths: list[tuple[str, float, int, int | None]],
) -> None:
    """Atomically reset running metadata jobs to queued (preserves attempts/queued_at).

    Mirrors the ``DerivativeScheduler`` start/recovery pattern in
    ``derivative_scheduler/lifecycle.py`` and ``derivative_scheduler/recovery.py``.
    """
    now = metadata_now()
    for path, mtime, size, mtime_ns in job_paths:
        if mtime_ns is not None:
            conn.execute(
                """
                UPDATE metadata_index_jobs
                SET state='queued',
                    started_at=NULL,
                    finished_at=NULL,
                    updated_at=?,
                    next_attempt_at=NULL,
                    claimed_by=NULL, claim_token=NULL, lease_expires_at=NULL
                WHERE path=? AND mtime_ns = ? AND size=? AND state='running'
                """,
                (now, path, mtime_ns, size),
            )
        else:
            conn.execute(
                """
                UPDATE metadata_index_jobs
                SET state='queued',
                    started_at=NULL,
                    finished_at=NULL,
                    updated_at=?,
                    next_attempt_at=NULL,
                    claimed_by=NULL, claim_token=NULL, lease_expires_at=NULL
                WHERE path=? AND mtime=? AND size=? AND state='running'
                """,
                (now, path, mtime, size),
            )


def _metadata_scope_filter(alias: str, scope_path: str | Path | None) -> tuple[str, list[Any]]:
    if scope_path is None:
        return "", []
    return path_scope_sql(scope_path, column=f"{alias}.path", leading_and=True)


def repair_legacy_asset_mtime_ns(
    conn: sqlite3.Connection,
    scope_path: str | Path | None = None,
) -> dict[str, int]:
    """Backfill asset mtimes that were accidentally stored as seconds."""
    counters = {"file_index": 0, "filesystem": 0, "skipped": 0}
    scope_where, scope_params = _metadata_scope_filter("a", scope_path)
    now = time.time()
    rows = conn.execute(
        f"""
        SELECT a.id, a.path, a.size, fi.mtime_ns AS file_index_mtime_ns
        FROM assets AS a
        LEFT JOIN file_index AS fi
          ON fi.path = a.path
         AND (fi.size = a.size OR (fi.size IS NULL AND a.size IS NULL))
        WHERE a.mtime_ns IS NOT NULL
          AND a.mtime_ns < ?
          {scope_where}
        ORDER BY a.id
        """,
        [_MIN_REASONABLE_MTIME_NS, *scope_params],
    ).fetchall()

    for row in rows:
        file_index_mtime_ns = row["file_index_mtime_ns"]
        source: str
        if file_index_mtime_ns is not None and int(file_index_mtime_ns) >= _MIN_REASONABLE_MTIME_NS:
            repaired_mtime_ns = int(file_index_mtime_ns)
            source = "file_index"
        else:
            try:
                repaired_mtime_ns = int(Path(row["path"]).stat().st_mtime_ns)
            except OSError:
                counters["skipped"] += 1
                continue
            source = "filesystem"

        conn.execute(
            "UPDATE assets SET mtime_ns = ?, indexed_at = ? WHERE id = ?",
            (repaired_mtime_ns, now, row["id"]),
        )
        counters[source] += 1

    return counters


def repair_inconsistent_asset_states(
    conn: sqlite3.Connection,
    scope_path: str | Path | None = None,
) -> dict[str, int]:
    """Repair done metadata_index_jobs whose assets are not in the done state.

    For each ``done`` job whose ``assets.metadata_state`` is not ``done``:
    - If no asset row exists, marks the job ``skipped``.
    - If ``image_metadata`` is current (matches the job's identity by mtime_ns
      or mtime + size), stamps ``assets.metadata_state = 'done'``.
    - Otherwise, demotes the job back to ``queued`` so the worker re-processes.

    Uses ``scope_path`` to filter by path prefix (or None for all paths).

    Returns counters ``{"repaired": N, "demoted": N, "skipped": N}``.
    """
    counters: dict[str, int] = {"repaired": 0, "demoted": 0, "skipped": 0, "stale_repaired": 0}

    scope_where, scope_params = _metadata_scope_filter("mj", scope_path)

    rows = conn.execute(
        f"""
        SELECT mj.path, mj.mtime, mj.mtime_ns, mj.size, mj.state,
               a.path IS NOT NULL AS has_asset,
               a.metadata_state AS asset_metadata_state
        FROM metadata_index_jobs mj
        LEFT JOIN assets a ON a.path = mj.path
        WHERE mj.state IN ('done', 'stale')
          {scope_where}
        """,
        scope_params,
    ).fetchall()

    now = time.time()
    for row in rows:
        path = row["path"]
        mtime = row["mtime"]
        mtime_ns = row["mtime_ns"]
        size = row["size"]
        state = row["state"]
        has_asset = bool(row["has_asset"])

        if not has_asset:
            # No asset row — mark job skipped
            if mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='skipped',
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=? AND state='done'
                    """,
                    (now, now, path, mtime_ns, size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='skipped',
                        finished_at=?,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=? AND state='done'
                    """,
                    (now, now, path, mtime, size),
                )
            counters["skipped"] += 1
            continue

        # Check whether current image_metadata exists for the job identity
        im_exists = _image_metadata_exists_for_job(conn, path, mtime, size, mtime_ns)

        if im_exists:
            if state == "done" and row["asset_metadata_state"] == "done":
                continue
            # image_metadata is current — repair job and asset state
            conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='done',
                    error=NULL,
                    finished_at=?,
                    updated_at=?
                WHERE path=?
                  AND ({image_metadata_params_match_sql()})
                  AND size=?
                """,
                (now, now, path, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime, size),
            )
            if mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE assets
                    SET metadata_state='done'
                    WHERE path=? AND mtime_ns = ? AND size=?
                    """,
                    (path, mtime_ns, size),
                )
            else:
                conn.execute(
                    """
                    UPDATE assets
                    SET metadata_state='done'
                    WHERE path=? AND mtime=? AND size=?
                    """,
                    (path, mtime, size),
                )
            counters["repaired"] += 1
            if state == "stale":
                counters["stale_repaired"] += 1
        else:
            # image_metadata missing or stale (including sidecar mismatch) — demote to queued
            if mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='queued',
                        started_at=NULL,
                        finished_at=NULL,
                        updated_at=?
                    WHERE path=? AND mtime_ns = ? AND size=? AND state IN ('done', 'stale')
                    """,
                    (now, path, mtime_ns, size),
                )
            else:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='queued',
                        started_at=NULL,
                        finished_at=NULL,
                        updated_at=?
                    WHERE path=? AND mtime=? AND size=? AND state IN ('done', 'stale')
                    """,
                    (now, path, mtime, size),
                )
            counters["demoted"] += 1

    return counters


def get_metadata_index_status(path: str | Path | None = None) -> dict[str, Any]:
    """Return durable metadata job counts, optionally scoped to a path subtree."""
    _initialize_database()
    counts = dict.fromkeys(METADATA_JOB_STATES, 0)
    where = ""
    params: list[Any] = []
    root = ""
    if path:
        root = str(Path(path).resolve())
        scope_predicate, params = path_scope_sql(path)
        where = f"WHERE {scope_predicate}"

    with _DB_LOCK, _connect() as conn:
        for row in conn.execute(
            f"""
            SELECT state, count(*) AS total
            FROM metadata_index_jobs
            {where}
            GROUP BY state
            """,
            params,
        ):
            if row["state"] in counts:
                counts[row["state"]] = int(row["total"])

        last_error_row = conn.execute(
            f"""
            SELECT path, error, updated_at
            FROM metadata_index_jobs
            {where + (" AND" if where else "WHERE")} state = 'failed' AND error IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        oldest_queued_row = conn.execute(
            f"""
            SELECT min(queued_at) AS oldest_queued_at
            FROM metadata_index_jobs
            {where + (" AND" if where else "WHERE")} state = 'queued'
            """,
            params,
        ).fetchone()

        updated_row = conn.execute(
            f"""
            SELECT max(updated_at) AS updated_at
            FROM metadata_index_jobs
            {where}
            """,
            params,
        ).fetchone()

        indexed_photos_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index
            {where + (" AND" if where else "WHERE")} type IN ('image', 'photo')
            """,
            params,
        ).fetchone()

        metadata_scope = ""
        metadata_params: list[Any] = []
        if path:
            metadata_scope, metadata_params = path_scope_sql(path, column="fi.path", leading_and=True)
        metadata_records_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE fi.type IN ('image', 'photo')
            {metadata_scope}
            """,
            metadata_params,
        ).fetchone()

    now = time.time()
    oldest_queued_at = oldest_queued_row["oldest_queued_at"] if oldest_queued_row else None
    indexed_photos = int(indexed_photos_row["total"] if indexed_photos_row else 0)
    metadata_records = int(metadata_records_row["total"] if metadata_records_row else 0)
    return {
        "path": root,
        "total": sum(counts.values()),
        "indexed_photos": indexed_photos,
        "metadata_records": metadata_records,
        "missing_metadata_records": max(0, indexed_photos - metadata_records),
        "counts": counts,
        "queued": counts["queued"],
        "running": counts["running"],
        "done": counts["done"],
        "failed": counts["failed"],
        "stale": counts["stale"],
        "skipped": counts["skipped"],
        "oldest_queued_age_seconds": round(now - oldest_queued_at, 3) if oldest_queued_at else None,
        "last_error": {
            "path": last_error_row["path"],
            "message": last_error_row["error"],
            "updated_at": last_error_row["updated_at"],
        }
        if last_error_row
        else None,
        "updated_at": updated_row["updated_at"] if updated_row else None,
    }
