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
from .identity import (
    asset_params_match_sql,
    image_metadata_params_match_sql,
)
from .types import MetadataIndexJob, MetadataQueueResult

_MIN_REASONABLE_MTIME_NS = 1_000_000_000_000


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _search_like_escape(value: str) -> str:
    from .search_store import _like_escape

    return _like_escape(value)


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
        SELECT 1 FROM image_metadata
        WHERE path = ?
          AND ({image_metadata_params_match_sql()})
          AND size = ?
        """,
        (path, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime, size),
    ).fetchone()
    return row is not None


def _current_metadata_is_complete(
    conn: sqlite3.Connection,
    path: str,
    mtime: float,
    size: int,
    mtime_ns: int | None = None,
) -> bool:
    row = conn.execute(
        f"""
        SELECT metadata_json FROM image_metadata
        WHERE path = ?
          AND ({image_metadata_params_match_sql()})
          AND size = ?
        """,
        (path, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime_ns, mtime, size),
    ).fetchone()
    if row is None:
        return False
    return bool(row["metadata_json"])


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


def _persist_metadata_index_jobs(
    paths: Iterable[str | Path], root_path: str | Path | None = None, *, priority: int = 3
) -> MetadataQueueResult:
    """Create/coalesce metadata index jobs for image paths without parsing files."""
    priority = max(0, min(priority, 3))
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

            existing = conn.execute(
                """
                SELECT mtime, mtime_ns, size, state, attempts, priority, library_id
                FROM metadata_index_jobs
                WHERE path = ?
                """,
                (job.path,),
            ).fetchone()

            if existing:
                if existing["mtime_ns"] is not None and job.mtime_ns is not None:
                    same_version = abs(existing["mtime_ns"] - job.mtime_ns) < 1000 and existing["size"] == job.size
                else:
                    same_version = existing["mtime"] == job.mtime and existing["size"] == job.size
                if not same_version:
                    existing = None
                else:
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
                      AND ABS(metadata_index_jobs.mtime_ns - excluded.mtime_ns) < 1000
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
                        WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
        if row["mtime_ns"] is not None:
            conn.execute(
                """
                UPDATE metadata_index_jobs
                SET state='running',
                    attempts=?,
                    started_at=?,
                    finished_at=NULL,
                    updated_at=?
                WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
                """,
                (attempts, now, now, row["path"], row["mtime_ns"], row["size"]),
            )
        else:
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
            mtime_ns=row["mtime_ns"],
            size=row["size"],
            library_id=row["library_id"],
        )
        return job


def complete_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
) -> None:
    """Mark one metadata job done and materialize assets.metadata_state='done'.

    Enforces the invariant: image_metadata current + job done + asset done.
    If no asset row exists for the path the job is marked skipped.
    If the asset row exists but the version does not match the job is marked stale.
    Verifies that image_metadata exists for the job's identity before marking done.
    """
    if not _image_metadata_exists_for_job(conn, job.path, job.mtime, job.size, job.mtime_ns):
        mark_metadata_job_stale(conn, job)
        return

    now = time.time()

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
            conn.execute(
                f"""
                UPDATE metadata_index_jobs
                SET state='skipped', error=NULL, finished_at=?, updated_at=?
                WHERE path=?
                  AND ({image_metadata_params_match_sql()})
                  AND size=?
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
                ),
            )
        else:
            mark_metadata_job_stale(conn, job)
        return

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
        (now, now, job.path, job.mtime_ns, job.mtime_ns, job.mtime_ns, job.mtime_ns, job.mtime_ns, job.mtime, job.size),
    )

    _update_asset_done(conn, job, now)


def fail_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    error: str,
) -> None:
    """Mark one metadata job as failed with a bounded error message."""
    now = time.time()
    if job.mtime_ns is not None:
        conn.execute(
            """
            UPDATE metadata_index_jobs
            SET state='failed',
                error=?,
                finished_at=?,
                updated_at=?
            WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
            """,
            (error[:1000], now, now, job.path, job.mtime_ns, job.size),
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
            (error[:1000], now, now, job.path, job.mtime, job.size),
        )


def mark_metadata_job_stale(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
) -> None:
    """Mark one metadata job stale when the file version no longer matches."""
    now = time.time()
    if job.mtime_ns is not None:
        conn.execute(
            """
            UPDATE metadata_index_jobs
            SET state='stale',
                error=NULL,
                finished_at=?,
                updated_at=?
            WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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

    Mirrors ``DerivativeScheduler.start()`` recovery pattern at
    derivative_scheduler.py:71-79.
    """
    now = time.time()
    for path, mtime, size, mtime_ns in job_paths:
        if mtime_ns is not None:
            conn.execute(
                """
                UPDATE metadata_index_jobs
                SET state='queued',
                    started_at=NULL,
                    finished_at=NULL,
                    updated_at=?
                WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=? AND state='running'
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
                WHERE path=? AND mtime=? AND size=? AND state='running'
                """,
                (now, path, mtime, size),
            )


def _metadata_scope_filter(alias: str, scope_path: str | Path | None) -> tuple[str, list[Any]]:
    if scope_path is None:
        return "", []
    resolved = str(Path(scope_path).resolve())
    prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
    return f"AND ({alias}.path = ? OR {alias}.path LIKE ? ESCAPE '\\')", [resolved, f"{_search_like_escape(prefix)}%"]


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
        WHERE (
            (mj.state = 'done' AND (a.path IS NULL OR a.metadata_state IS NULL OR a.metadata_state != 'done'))
            OR mj.state = 'stale'
          )
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=? AND state='done'
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
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=?
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
            if state == "stale":
                continue
            # image_metadata missing or stale — demote job to queued
            if mtime_ns is not None:
                conn.execute(
                    """
                    UPDATE metadata_index_jobs
                    SET state='queued',
                        started_at=NULL,
                        finished_at=NULL,
                        updated_at=?
                    WHERE path=? AND ABS(mtime_ns - ?) < 1000 AND size=? AND state='done'
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
                    WHERE path=? AND mtime=? AND size=? AND state='done'
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
