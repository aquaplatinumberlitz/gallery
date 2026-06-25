"""Metadata indexing job queue helpers."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..files import is_image_path, is_index_excluded_path
from ._db import _DB_LOCK, MAX_METADATA_JOB_ATTEMPTS, METADATA_JOB_STATES, _connect
from .types import MetadataIndexJob, MetadataQueueResult


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _search_like_escape(value: str) -> str:
    from .search_store import _like_escape

    return _like_escape(value)


def _current_metadata_is_complete(conn: sqlite3.Connection, path: str, mtime: float, size: int) -> bool:
    row = conn.execute(
        """
        SELECT mtime, size, metadata_json
        FROM image_metadata
        WHERE path = ?
        """,
        (path,),
    ).fetchone()
    if row is None:
        return False
    return row["mtime"] == mtime and row["size"] == size and bool(row["metadata_json"])


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
        size=stat.st_size,
    )


def _mark_current_metadata_done(conn: sqlite3.Connection, job: MetadataIndexJob, now: float) -> None:
    conn.execute(
        """
        INSERT INTO metadata_index_jobs (
          path, name, parent_path, folder_path, root_path, mtime, size, state,
          attempts, error, queued_at, started_at, finished_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'done', 0, NULL, ?, NULL, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          name=excluded.name,
          parent_path=excluded.parent_path,
          folder_path=excluded.folder_path,
          root_path=excluded.root_path,
          mtime=excluded.mtime,
          size=excluded.size,
          state='done',
          error=NULL,
          finished_at=excluded.finished_at,
          updated_at=excluded.updated_at
        """,
        (
            job.path,
            job.name,
            job.parent_path,
            job.folder_path,
            job.root_path,
            job.mtime,
            job.size,
            now,
            now,
            now,
        ),
    )


def queue_metadata_index_paths(paths: Iterable[str | Path], root_path: str | Path | None = None) -> MetadataQueueResult:
    """Create/coalesce metadata index jobs for image paths without parsing files."""
    jobs = [job for path in paths if (job := _metadata_job_from_path(path, root_path))]
    if not jobs:
        return MetadataQueueResult(enqueued=[])

    _initialize_database()
    enqueued: list[MetadataIndexJob] = []
    coalesced = 0
    skipped = 0
    failed = 0
    now = time.time()

    with _DB_LOCK, _connect() as conn:
        for job in jobs:
            if _current_metadata_is_complete(conn, job.path, job.mtime, job.size):
                _mark_current_metadata_done(conn, job, now)
                skipped += 1
                continue

            existing = conn.execute(
                """
                SELECT mtime, size, state, attempts
                FROM metadata_index_jobs
                WHERE path = ?
                """,
                (job.path,),
            ).fetchone()

            if existing and existing["mtime"] == job.mtime and existing["size"] == job.size:
                state = existing["state"]
                attempts = int(existing["attempts"] or 0)
                if state in {"queued", "running"}:
                    coalesced += 1
                    continue
                if state == "failed" and attempts >= MAX_METADATA_JOB_ATTEMPTS:
                    failed += 1
                    continue
                if state == "done" and _current_metadata_is_complete(conn, job.path, job.mtime, job.size):
                    skipped += 1
                    continue

            conn.execute(
                """
                INSERT INTO metadata_index_jobs (
                  path, name, parent_path, folder_path, root_path, mtime, size,
                  state, attempts, error, queued_at, started_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, ?, NULL, NULL, ?)
                ON CONFLICT(path) DO UPDATE SET
                  name=excluded.name,
                  parent_path=excluded.parent_path,
                  folder_path=excluded.folder_path,
                  root_path=excluded.root_path,
                  mtime=excluded.mtime,
                  size=excluded.size,
                  state='queued',
                  attempts=CASE
                    WHEN metadata_index_jobs.mtime = excluded.mtime
                     AND metadata_index_jobs.size = excluded.size
                    THEN metadata_index_jobs.attempts
                    ELSE 0
                  END,
                  error=NULL,
                  queued_at=excluded.queued_at,
                  started_at=NULL,
                  finished_at=NULL,
                  updated_at=excluded.updated_at
                """,
                (
                    job.path,
                    job.name,
                    job.parent_path,
                    job.folder_path,
                    job.root_path,
                    job.mtime,
                    job.size,
                    now,
                    now,
                ),
            )
            enqueued.append(job)

    return MetadataQueueResult(enqueued=enqueued, coalesced=coalesced, skipped=skipped, failed=failed)


def mark_metadata_jobs_running(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as running and increment their attempt counts."""
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
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
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_done(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as successfully completed."""
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='done',
                error=NULL,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_stale(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs stale when the file version no longer matches."""
    rows = list(jobs)
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='stale',
                error=NULL,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_failed(errors: Iterable[tuple[MetadataIndexJob, str]]) -> None:
    """Mark durable metadata jobs failed with a bounded error message."""
    rows = [(job, error[:1000]) for job, error in errors]
    if not rows:
        return
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='failed',
                error=?,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((error, now, now, job.path, job.mtime, job.size) for job, error in rows),
        )


# ---------------------------------------------------------------------------
# DB-claim worker primitives (Phase 1)
# ---------------------------------------------------------------------------


def claim_next_metadata_job(
    *,
    max_queue_wait_seconds: int = 600,
) -> MetadataIndexJob | None:
    """Claim one queued metadata job from SQLite in a short BEGIN IMMEDIATE transaction.

    Mirrors ``DerivativeScheduler._claim_job`` (derivative_scheduler.py:392-420).
    Returns ``None`` when no queued job is available.
    """
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT path, name, parent_path, folder_path, root_path,
                   mtime, mtime_ns, size, state, attempts,
                   queued_at, started_at, finished_at, updated_at, library_id, priority
            FROM metadata_index_jobs
            WHERE state = 'queued'
            ORDER BY priority ASC, queued_at ASC, path ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        attempts = int(row["attempts"]) + 1
        now = time.time()
        conn.execute(
            """
            UPDATE metadata_index_jobs
            SET state='running',
                attempts=?,
                started_at=?,
                finished_at=NULL,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            (attempts, now, now, row["path"], row["mtime"], row["size"]),
        )
        job = MetadataIndexJob(
            path=row["path"],
            name=row["name"],
            parent_path=row["parent_path"],
            folder_path=row["folder_path"],
            root_path=row["root_path"],
            mtime=row["mtime"],
            size=row["size"],
            library_id=row["library_id"],
        )
        return job


def complete_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    *,
    metadata_is_current: bool = True,
) -> None:
    """Mark one metadata job done and materialize assets.metadata_state='done'.

    Phase 3 adds full stale/race guards. For now this is the basic
    completion transition linking job state and asset state.
    """
    now = time.time()
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
    conn.execute(
        """
        UPDATE assets
        SET metadata_state='done', updated_at=?
        WHERE path=? AND mtime_ns=? AND size=?
        """,
        (now, job.path, job.mtime, job.size),
    )


def fail_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    error: str,
) -> None:
    """Mark one metadata job as failed with a bounded error message."""
    now = time.time()
    conn.execute(
        """
        UPDATE metadata_index_jobs
        SET state='failed',
            error=?,
            finished_at=?,
            updated_at=?
        WHERE path=? AND mtime=? AND size=?
        """,
        (error[:1000], now, now, job.path, job.mtime, job.size),
    )


def mark_metadata_job_stale(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
) -> None:
    """Mark one metadata job stale when the file version no longer matches."""
    now = time.time()
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


def list_recoverable_metadata_jobs(
    conn: sqlite3.Connection,
    states: tuple[str, ...],
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """List metadata_index_jobs rows matching the given states, bounded by limit."""
    placeholders = ",".join("?" for _ in states)
    rows = conn.execute(
        f"""
        SELECT path, name, parent_path, folder_path, root_path,
               mtime, mtime_ns, size, state, attempts,
               queued_at, started_at, finished_at, updated_at, library_id, priority
        FROM metadata_index_jobs
        WHERE state IN ({placeholders})
        ORDER BY updated_at ASC
        LIMIT ?
        """,
        (*states, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def reset_running_jobs_to_queued(
    conn: sqlite3.Connection,
    job_paths: list[tuple[str, float, int]],
) -> None:
    """Atomically reset running metadata jobs to queued (preserves attempts/queued_at).

    Mirrors ``DerivativeScheduler.start()`` recovery pattern at
    derivative_scheduler.py:71-79.
    """
    now = time.time()
    conn.executemany(
        """
        UPDATE metadata_index_jobs
        SET state='queued',
            started_at=NULL,
            finished_at=NULL,
            updated_at=?
        WHERE path=? AND mtime=? AND size=? AND state='running'
        """,
        ((now, path, mtime, size) for path, mtime, size in job_paths),
    )


def get_metadata_index_status(path: str | Path | None = None) -> dict[str, Any]:
    """Return durable metadata job counts, optionally scoped to a path subtree."""
    _initialize_database()
    counts = dict.fromkeys(METADATA_JOB_STATES, 0)
    where = ""
    params: list[Any] = []
    root = ""
    if path:
        resolved = str(Path(path).resolve())
        root = resolved
        prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
        where = "WHERE (path = ? OR path LIKE ? ESCAPE '\\')"
        params = [resolved, f"{_search_like_escape(prefix)}%"]

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
            resolved = str(Path(path).resolve())
            prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
            metadata_scope = "AND (fi.path = ? OR fi.path LIKE ? ESCAPE '\\')"
            metadata_params = [resolved, f"{_search_like_escape(prefix)}%"]
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
