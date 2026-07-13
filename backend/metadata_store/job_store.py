"""Library job queue and lifecycle helpers."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ._db import _DB_LOCK, LIBRARY_JOB_TERMINAL_STATES, _connect
from .library_store import list_libraries
from .path_utils import canonicalize_catalog_path, catalog_path_contains
from .types import CatalogJobConflict

CATALOG_WORK_JOB_TYPES = ("scan", "rebuild")
CATALOG_PARENT_JOB_TYPES = ("scan_all", "rebuild_imported_data")


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _serialize_library_job(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a library job row to the public API shape."""
    try:
        counters = json.loads(row["counters"] or "{}")
    except (TypeError, json.JSONDecodeError):
        counters = {}
    return {
        "id": int(row["id"]),
        "library_id": int(row["library_id"]) if row["library_id"] is not None else None,
        "parent_job_id": int(row["parent_job_id"]) if row["parent_job_id"] is not None else None,
        "config_revision": int(row["config_revision"]) if row["config_revision"] is not None else None,
        "type": str(row["type"]),
        "state": str(row["state"]),
        "scope_path": row["scope_path"],
        "trigger": str(row["trigger"]),
        "priority": int(row["priority"]),
        "progress_current": int(row["progress_current"]),
        "progress_total": int(row["progress_total"]) if row["progress_total"] is not None else None,
        "message": row["message"],
        "error": row["error"],
        "counters": counters if isinstance(counters, dict) else {},
        "discovered_assets": int(row["discovered_assets"]),
        "created_assets": int(row["created_assets"]),
        "updated_assets": int(row["updated_assets"]),
        "offline_assets": int(row["offline_assets"]),
        "metadata_queued_assets": int(row["metadata_queued_assets"]),
        "created_at": int(float(row["created_at"]) * 1000),
        "updated_at": int(float(row["updated_at"]) * 1000),
        "started_at": int(float(row["started_at"]) * 1000) if row["started_at"] is not None else None,
        "finished_at": int(float(row["finished_at"]) * 1000) if row["finished_at"] is not None else None,
    }


def create_job(
    job_type: str,
    *,
    library_id: int | None = None,
    parent_job_id: int | None = None,
    scope_path: str | Path | None = None,
    trigger: str = "manual",
    priority: int = 50,
    progress_total: int | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Create one queued library-management job."""
    now = time.time()
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        config_revision = None
        if library_id is not None and job_type in CATALOG_WORK_JOB_TYPES:
            library = conn.execute("SELECT config_revision FROM libraries WHERE id = ?", (library_id,)).fetchone()
            config_revision = int(library["config_revision"]) if library is not None else None
        cursor = conn.execute(
            """
            INSERT INTO library_jobs (
              library_id, parent_job_id, config_revision, type, state, scope_path, trigger, priority, progress_current,
              progress_total, message, counters, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, 0, ?, ?, '{}', ?, ?)
            """,
            (
                library_id,
                parent_job_id,
                config_revision,
                job_type,
                canonicalize_catalog_path(scope_path) if scope_path is not None else None,
                trigger,
                priority,
                progress_total,
                message,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _serialize_library_job(row)


def _job_scope_covers(existing_scope: str | None, requested_scope: str | None) -> bool:
    """Return whether an active job scope covers a requested scope."""
    if existing_scope is None:
        return True
    if requested_scope is None:
        return False
    return catalog_path_contains(existing_scope, requested_scope)


def _serialize_catalog_enqueue_result(job: sqlite3.Row, created: bool) -> tuple[dict[str, Any], bool]:
    return _serialize_library_job(job), created


def create_or_coalesce_catalog_job(
    library_id: int,
    *,
    operation: str = "scan",
    trigger: str = "manual",
    scope_path: str | Path | None = None,
    priority: int = 50,
    parent_job_id: int | None = None,
    message: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create or coalesce one durable catalog job under the v9 trigger rules.

    Rebuild conflict rules (plan §5.3):
    - manual rebuild returns 409 when any catalog work is already running or
      another rebuild is queued/running for a covering scope;
    - manual rebuild cancels queued non-rebuild scans it covers;
    - manual scan requested while rebuild is queued/running returns 409;
    - automated scans during rebuild defer as a queued follow-up.
    """
    if operation not in {"scan", "rebuild"}:
        raise ValueError(f"Unsupported catalog operation: {operation}")
    requested_scope = canonicalize_catalog_path(scope_path) if scope_path is not None else None
    now = time.time()
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            library = conn.execute("SELECT config_revision FROM libraries WHERE id = ?", (library_id,)).fetchone()
            if library is None:
                raise KeyError(library_id)
            config_revision = int(library["config_revision"])

            def _link_parent(child_job_id: int) -> None:
                if parent_job_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO catalog_job_dependencies "
                        "(parent_job_id, child_job_id, created_at) VALUES (?, ?, ?)",
                        (parent_job_id, child_job_id, now),
                    )

            active_rows = conn.execute(
                """
                SELECT * FROM library_jobs
                WHERE library_id = ? AND type IN ('scan', 'rebuild')
                  AND state IN ('queued', 'running')
                ORDER BY CASE state WHEN 'queued' THEN 0 ELSE 1 END, priority DESC, created_at, id
                """,
                (library_id,),
            ).fetchall()

            def _cancel_job(job_id: int, reason: str = "Superseded by broader catalog job") -> None:
                conn.execute(
                    """
                    UPDATE library_jobs
                    SET state = 'cancelled',
                        message = COALESCE(message, ?),
                        error = ?,
                        updated_at = ?,
                        finished_at = COALESCE(finished_at, ?)
                    WHERE id = ?
                    """,
                    (reason, reason, now, now, job_id),
                )

            def _emit_cancelled(job_id: int) -> None:
                from ..library_events import event_payload, publish

                cancelled = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
                if cancelled is not None:
                    publish(event_payload("job.cancelled", _serialize_library_job(cancelled)))

            if operation == "rebuild":
                for row in active_rows:
                    if row["state"] == "running":
                        raise CatalogJobConflict(_serialize_library_job(row))
                for row in active_rows:
                    if row["type"] == "rebuild" and _job_scope_covers(row["scope_path"], requested_scope):
                        raise CatalogJobConflict(_serialize_library_job(row))
                for row in active_rows:
                    if (
                        row["type"] == "scan"
                        and row["state"] == "queued"
                        and _job_scope_covers(requested_scope, row["scope_path"])
                    ):
                        _cancel_job(int(row["id"]), "Superseded by rebuild")
                        _emit_cancelled(int(row["id"]))
            else:
                active_rebuilds = [row for row in active_rows if row["type"] == "rebuild"]
                if active_rebuilds:
                    if trigger == "manual":
                        raise CatalogJobConflict(_serialize_library_job(active_rebuilds[0]))
                else:
                    scan_rows = [row for row in active_rows if row["type"] == "scan"]
                    for row in scan_rows:
                        if _job_scope_covers(row["scope_path"], requested_scope):
                            if row["state"] == "running" and trigger == "watcher":
                                continue
                            if row["state"] == "queued" and priority > int(row["priority"]):
                                conn.execute(
                                    """
                                    UPDATE library_jobs
                                    SET priority = ?, trigger = ?, updated_at = ?
                                    WHERE id = ?
                                    """,
                                    (priority, trigger, now, int(row["id"])),
                                )
                                row = conn.execute(
                                    "SELECT * FROM library_jobs WHERE id = ?", (int(row["id"]),)
                                ).fetchone()
                            _link_parent(int(row["id"]))
                            conn.execute("COMMIT")
                            return _serialize_catalog_enqueue_result(row, False)

                    for row in scan_rows:
                        if (
                            row["state"] == "queued"
                            and priority >= int(row["priority"])
                            and _job_scope_covers(requested_scope, row["scope_path"])
                        ):
                            _cancel_job(int(row["id"]))
                            _emit_cancelled(int(row["id"]))

            cursor = conn.execute(
                """
                INSERT INTO library_jobs (
                  library_id, parent_job_id, config_revision, type, state, scope_path, trigger, priority,
                  progress_current, progress_total, message, counters, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, 0, NULL, ?, '{}', ?, ?)
                """,
                (
                    library_id,
                    parent_job_id,
                    config_revision,
                    operation,
                    requested_scope,
                    trigger,
                    priority,
                    message or "Catalog update queued",
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
            _link_parent(int(row["id"]))
            conn.execute("COMMIT")
            return _serialize_catalog_enqueue_result(row, True)
        except Exception:
            conn.execute("ROLLBACK")
            raise


def claim_next_catalog_job(*, max_queue_wait_seconds: int = 600) -> dict[str, Any] | None:
    """Mark the next runnable catalog job running and return it."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """UPDATE library_jobs
                   SET state = 'cancelled', error = 'Library configuration changed before activation',
                       message = 'Catalog job cancelled because library configuration changed',
                       updated_at = ?, finished_at = ?
                   WHERE state = 'queued' AND type IN ('scan', 'rebuild')
                     AND library_id IS NOT NULL AND config_revision IS NOT NULL
                     AND config_revision != (
                       SELECT config_revision FROM libraries WHERE id = library_jobs.library_id
                     )""",
                (now, now),
            )
            rows = conn.execute(
                """
                SELECT *
                FROM library_jobs AS queued
                WHERE queued.state = 'queued'
                  AND queued.type IN ('scan', 'rebuild')
                  AND queued.library_id IS NOT NULL
                  AND (
                    queued.config_revision IS NULL OR queued.config_revision = (
                      SELECT config_revision FROM libraries WHERE id = queued.library_id
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM library_jobs AS running
                    WHERE running.library_id = queued.library_id
                      AND running.state = 'running'
                      AND running.type IN ('scan', 'rebuild')
                  )
                ORDER BY
                  CASE
                    WHEN (? - queued.created_at) >= ? THEN 100
                    ELSE queued.priority
                  END DESC,
                  queued.created_at ASC,
                  queued.id ASC
                LIMIT 1
                """,
                (now, max_queue_wait_seconds),
            ).fetchall()
            if not rows:
                conn.execute("COMMIT")
                return None
            job_id = int(rows[0]["id"])
            conn.execute(
                """
                UPDATE library_jobs
                SET state = 'running',
                    config_revision = COALESCE(
                      config_revision, (SELECT config_revision FROM libraries WHERE id = library_jobs.library_id)
                    ),
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    message = COALESCE(message, 'Catalog job running')
                WHERE id = ? AND state = 'queued'
                """,
                (now, now, job_id),
            )
            row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.execute("COMMIT")
            return _serialize_library_job(row)
        except Exception:
            conn.execute("ROLLBACK")
            raise


def enqueue_startup_catalog_scans(*, priority: int = 10) -> list[dict[str, Any]]:
    """Queue or coalesce one low-priority startup scan per registered library."""
    jobs: list[dict[str, Any]] = []
    for library in list_libraries():
        job, _created = create_or_coalesce_catalog_job(
            int(library["id"]),
            trigger="startup",
            priority=priority,
            message="Startup catch-up update queued",
        )
        jobs.append(job)
    return jobs


def order_library_ids_for_scheduled_refresh(library_ids: list[int]) -> list[int]:
    """Order eligible libraries by durable scheduled-job recency and ID."""
    if not library_ids:
        return []
    _initialize_database()
    placeholders = ",".join("?" for _ in library_ids)
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT l.id, max(j.created_at) AS last_scheduled_at
            FROM libraries AS l
            LEFT JOIN library_jobs AS j
              ON j.library_id = l.id
             AND j.type = 'scan'
             AND j.trigger = 'scheduled'
            WHERE l.id IN ({placeholders})
            GROUP BY l.id
            ORDER BY last_scheduled_at IS NOT NULL ASC,
                     last_scheduled_at ASC,
                     l.id ASC
            """,
            library_ids,
        ).fetchall()
    ordered = [int(row["id"]) for row in rows]
    seen = set(ordered)
    ordered.extend(sorted(library_id for library_id in library_ids if library_id not in seen))
    return ordered


def update_job_state(
    job_id: int,
    state: str,
    *,
    progress_current: int | None = None,
    progress_total: int | None = None,
    message: str | None = None,
    error: str | None = None,
    counters: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """Apply a valid lifecycle/progress update and return the updated job."""
    allowed_states = {"queued", "running", *LIBRARY_JOB_TERMINAL_STATES}
    if state not in allowed_states:
        raise ValueError(f"Invalid library job state: {state}")
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        current_state = str(row["state"])
        transitions = {
            "queued": {"queued", "running", "cancelled"},
            "running": {"running", *LIBRARY_JOB_TERMINAL_STATES},
            "succeeded": {"succeeded"},
            "failed": {"failed"},
            "cancelled": {"cancelled"},
        }
        if state not in transitions[current_state]:
            raise ValueError(f"Invalid library job transition: {current_state} -> {state}")
        current = int(row["progress_current"]) if progress_current is None else max(0, progress_current)
        total = row["progress_total"] if progress_total is None else progress_total
        if total is not None:
            total = max(current, int(total))
        now = time.time()
        terminal = state in LIBRARY_JOB_TERMINAL_STATES
        conn.execute(
            """
            UPDATE library_jobs
            SET state = ?, progress_current = ?, progress_total = ?,
                message = ?, error = ?, counters = ?, updated_at = ?,
                started_at = CASE WHEN ? = 'running' THEN COALESCE(started_at, ?) ELSE started_at END,
                finished_at = CASE WHEN ? THEN COALESCE(finished_at, ?) ELSE finished_at END
            WHERE id = ?
            """,
            (
                state,
                current,
                total,
                message,
                error,
                json.dumps(counters if counters is not None else json.loads(row["counters"] or "{}")),
                now,
                state,
                now,
                int(terminal),
                now,
                job_id,
            ),
        )
        updated = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
        return _serialize_library_job(updated)


def get_job(job_id: int) -> dict[str, Any] | None:
    """Return one library-management job."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
        return _serialize_library_job(row) if row else None


def get_library_jobs(library_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent jobs for one library, newest first."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM library_jobs WHERE library_id = ? ORDER BY id DESC LIMIT ?",
            (library_id, limit),
        )
        return [_serialize_library_job(row) for row in rows]


def list_jobs(*, limit: int = 100) -> list[dict[str, Any]]:
    """Return recent library-management jobs, newest first."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        return [
            _serialize_library_job(row)
            for row in conn.execute("SELECT * FROM library_jobs ORDER BY id DESC LIMIT ?", (limit,))
        ]


def list_active_jobs(library_id: int | None = None) -> list[dict[str, Any]]:
    """Return queued/running jobs, optionally scoped to one library."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        query = "SELECT * FROM library_jobs WHERE state IN ('queued', 'running')"
        params: tuple[Any, ...] = ()
        if library_id is not None:
            query += " AND library_id = ?"
            params = (library_id,)
        query += " ORDER BY id"
        return [_serialize_library_job(row) for row in conn.execute(query, params)]


def update_parent_aggregate_job(parent_job_id: int) -> dict[str, Any] | None:
    """Refresh aggregate parent job progress from child terminal states."""
    _initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        parent = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (parent_job_id,)).fetchone()
        if parent is None or parent["type"] not in CATALOG_PARENT_JOB_TYPES:
            return None
        if parent["state"] not in {"queued", "running"}:
            return None
        children = conn.execute(
            """SELECT child.state FROM catalog_job_dependencies dep
               JOIN library_jobs child ON child.id = dep.child_job_id
               WHERE dep.parent_job_id = ?
               UNION ALL
               SELECT state FROM library_jobs
               WHERE parent_job_id = ?
                 AND NOT EXISTS (
                   SELECT 1 FROM catalog_job_dependencies WHERE parent_job_id = ?
                 )""",
            (parent_job_id, parent_job_id, parent_job_id),
        ).fetchall()
        total = len(children)
        succeeded = sum(1 for child in children if child["state"] == "succeeded")
        failed = sum(1 for child in children if child["state"] == "failed")
        cancelled = sum(1 for child in children if child["state"] == "cancelled")
        finished = succeeded + failed + cancelled
        parent_type = str(parent["type"])
        try:
            existing_counters = json.loads(parent["counters"] or "{}")
        except (TypeError, json.JSONDecodeError):
            existing_counters = {}
        if total == 0:
            state = "failed"
            message = "Interrupted by server restart"
            finished_at = now
        elif finished < total:
            state = "running"
            if parent_type == "scan_all":
                message = f"Updated {finished} of {total} libraries"
            else:
                message = f"Rebuilt {finished} of {total} libraries"
            finished_at = None
        elif failed or cancelled:
            state = "failed"
            if parent_type == "scan_all":
                message = "Update all libraries completed with failures"
            else:
                message = "Imported data rebuild completed with failures"
            finished_at = now
        else:
            state = "succeeded"
            if parent_type == "scan_all":
                message = "Update all libraries completed"
            else:
                message = "Imported data rebuild completed"
            finished_at = now
        counters = {"total": total, "succeeded": succeeded, "failed": failed, "cancelled": cancelled}
        if parent_type == "scan_all":
            counters["coalesced"] = int(existing_counters.get("coalesced", 0))
        conn.execute(
            """
            UPDATE library_jobs
            SET state = ?,
                progress_current = ?,
                progress_total = ?,
                message = ?,
                counters = ?,
                updated_at = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = CASE WHEN ? IS NULL THEN NULL ELSE ? END
            WHERE id = ?
            """,
            (
                state,
                finished,
                total,
                message,
                json.dumps(counters),
                now,
                now,
                finished_at,
                finished_at,
                parent_job_id,
            ),
        )
        row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (parent_job_id,)).fetchone()
        return _serialize_library_job(row)


def list_parent_aggregate_job_ids(child_job_id: int) -> list[int]:
    """Return every aggregate parent linked to a catalog child."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            """SELECT parent_job_id FROM catalog_job_dependencies WHERE child_job_id = ?
               UNION SELECT parent_job_id FROM library_jobs
               WHERE id = ? AND parent_job_id IS NOT NULL""",
            (child_job_id, child_job_id),
        )
        return [int(row["parent_job_id"]) for row in rows]


def create_or_get_active_scan_job(
    library_id: int,
    *,
    parent_job_id: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Atomically return an existing active scan job or create a queued one.

    The check for an existing active scan job and the insert of a new queued
    job happen inside a single ``_DB_LOCK`` critical section, eliminating the
    TOCTOU race that existed when ``_queue_scan`` performed the lookup and the
    insert as separate calls. Returns ``(job, created)`` where ``created`` is
    ``True`` when a new job was inserted and ``False`` when an existing active
    scan job was reused.
    """
    return create_or_coalesce_catalog_job(
        library_id,
        operation="scan",
        trigger="manual",
        priority=100,
        parent_job_id=parent_job_id,
        message="Scan queued",
    )


def recover_stale_jobs(*, reason: str = "Interrupted by server restart") -> list[dict[str, Any]]:
    """Fail jobs left running by a previous server process.

    Queued durable jobs remain queued so startup can resume them or coalesce a
    low-priority catch-up scan without losing work.
    """
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        running_rows = [
            (int(row["id"]), int(row["parent_job_id"]) if row["parent_job_id"] is not None else None)
            for row in conn.execute(
                """
                SELECT id, parent_job_id
                FROM library_jobs
                WHERE state = 'running' AND type IN (?, ?)
                """,
                CATALOG_WORK_JOB_TYPES,
            )
        ]
        parent_ids = {
            int(row["id"])
            for row in conn.execute(
                """
                SELECT id
                FROM library_jobs
                WHERE state IN ('queued', 'running')
                  AND type IN (?, ?)
                """,
                CATALOG_PARENT_JOB_TYPES,
            )
        }
    recovered: list[dict[str, Any]] = []
    touched_parent_ids = {parent_id for _job_id, parent_id in running_rows if parent_id is not None}
    for job_id, _parent_job_id in running_rows:
        job = update_job_state(
            job_id,
            "failed",
            message=reason,
            error=reason,
        )
        if job is not None:
            recovered.append(job)
    seen_ids = {int(job["id"]) for job in recovered}
    for parent_id in sorted(parent_ids | touched_parent_ids):
        job = update_parent_aggregate_job(parent_id)
        if job is not None and int(job["id"]) not in seen_ids:
            recovered.append(job)
            seen_ids.add(int(job["id"]))
    return recovered
