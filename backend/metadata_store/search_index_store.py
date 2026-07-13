"""Durable search-index state, jobs, claims, and per-asset extraction records."""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from typing import Any

from ._db import _DB_LOCK, _connect
from ._schema import initialize_database

ACTIVE_SEARCH_INDEX_JOB_STATES = ("queued", "running", "cancel_requested", "interrupted")
SEARCH_INDEX_TERMINAL_STATES = ("cancelled", "succeeded", "failed")
SEARCH_EXTRACTION_STATUSES = ("ready", "not_applicable", "skipped", "failed")


class SearchIndexJobConflict(RuntimeError):
    """Raised when the same library/index already has durable active work."""


class SearchIndexClaimLost(RuntimeError):
    """Raised when a worker attempts a write after its fenced claim expired."""


def source_fingerprint(asset: dict[str, Any]) -> str:
    """Return the stable catalog source fingerprint used by missing rebuilds."""
    return f"{int(asset.get('mtime_ns') or 0)}:{int(asset.get('size') or 0)}"


def _sanitize_error_code(value: str | None, fallback: str = "search_index_failed") -> str:
    candidate = (value or fallback).strip().lower()[:64]
    return candidate if re.fullmatch(r"[a-z][a-z0-9_]*", candidate) else fallback


def _sanitize_error_summary(value: str | None, fallback: str = "Search index operation failed") -> str:
    if not value:
        return fallback
    single_line = " ".join(value.split())
    if "/" in single_line or "\\" in single_line or len(single_line) > 240:
        return fallback
    return single_line


def _state_usable(row: sqlite3.Row | dict[str, Any]) -> bool:
    state = str(row["state"])
    indexed_count = int(row["indexed_count"] or 0)
    target_count = int(row["target_count"] or 0)
    return state == "ready" or (state in {"building", "degraded"} and (indexed_count > 0 or target_count == 0))


def _serialize_state(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    state = dict(row)
    state["usable"] = _state_usable(row)
    return state


def _serialize_job(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    job = dict(row)
    job.pop("claim_token", None)
    return job


def ensure_search_index_state(
    index_name: str,
    library_id: int,
    *,
    schema_version: int,
    extractor_version: int,
    enabled: bool,
) -> dict[str, Any]:
    """Create or refresh one definition-backed library state without backfilling."""
    initialize_database()
    now = time.time()
    desired_state = "pending" if enabled else "disabled"
    with _DB_LOCK, _connect() as conn:
        if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
            raise KeyError(library_id)
        conn.execute(
            """
            INSERT INTO search_index_states (
              index_name, library_id, state, schema_version, extractor_version,
              indexed_count, target_count, failed_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)
            ON CONFLICT(index_name, library_id) DO UPDATE SET
              state = CASE
                WHEN excluded.state = 'disabled' THEN 'disabled'
                WHEN search_index_states.state = 'disabled' THEN 'pending'
                ELSE search_index_states.state
              END,
              schema_version = excluded.schema_version,
              extractor_version = excluded.extractor_version,
              updated_at = excluded.updated_at
            """,
            (index_name, library_id, desired_state, schema_version, extractor_version, now),
        )
        row = conn.execute(
            "SELECT * FROM search_index_states WHERE index_name = ? AND library_id = ?",
            (index_name, library_id),
        ).fetchone()
    return _serialize_state(row)


def list_search_index_states(*, library_id: int | None = None) -> list[dict[str, Any]]:
    """List persisted per-library search-index state with a separate usable flag."""
    initialize_database()
    query = "SELECT * FROM search_index_states"
    params: tuple[Any, ...] = ()
    if library_id is not None:
        query += " WHERE library_id = ?"
        params = (library_id,)
    query += " ORDER BY library_id, index_name"
    with _DB_LOCK, _connect() as conn:
        result: list[dict[str, Any]] = []
        for row in conn.execute(query, params):
            item = _serialize_state(row)
            reasons = conn.execute(
                """
                SELECT extraction.error_code, count(*) AS count
                FROM asset_search_extractions AS extraction
                JOIN assets AS asset ON asset.id = extraction.asset_id
                WHERE extraction.index_name = ? AND asset.library_id = ?
                  AND extraction.status = 'skipped' AND extraction.error_code IS NOT NULL
                GROUP BY extraction.error_code
                ORDER BY extraction.error_code
                """,
                (row["index_name"], row["library_id"]),
            ).fetchall()
            item["skip_reasons"] = {str(reason["error_code"]): int(reason["count"]) for reason in reasons}
            result.append(item)
        return result


def get_search_index_job(job_id: int) -> dict[str, Any] | None:
    """Return one public durable search-index job."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (job_id,)).fetchone()
    return _serialize_job(row) if row is not None else None


def create_search_index_job(
    index_name: str,
    library_id: int,
    *,
    mode: str = "missing",
    schema_version: int,
    extractor_version: int,
) -> dict[str, Any]:
    """Queue one missing/full rebuild or raise on duplicate active work."""
    if mode not in {"missing", "full"}:
        raise ValueError("Invalid search index rebuild mode")
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
                raise KeyError(library_id)
            placeholders = ",".join("?" for _ in ACTIVE_SEARCH_INDEX_JOB_STATES)
            active = conn.execute(
                f"""
                SELECT id FROM search_index_jobs
                WHERE index_name = ? AND library_id = ? AND state IN ({placeholders})
                LIMIT 1
                """,
                (index_name, library_id, *ACTIVE_SEARCH_INDEX_JOB_STATES),
            ).fetchone()
            if active is not None:
                raise SearchIndexJobConflict(int(active["id"]))
            target_count = int(
                conn.execute(
                    """
                    SELECT count(*) FROM assets
                    WHERE library_id = ? AND offline = 0 AND deleted_at IS NULL
                      AND type IN ('image', 'video')
                    """,
                    (library_id,),
                ).fetchone()[0]
            )
            cursor = conn.execute(
                """
                INSERT INTO search_index_jobs (
                  index_name, library_id, mode, state, processed_count,
                  target_count, failed_count, requested_at
                ) VALUES (?, ?, ?, 'queued', 0, ?, 0, ?)
                """,
                (index_name, library_id, mode, target_count, now),
            )
            job_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO search_index_states (
                  index_name, library_id, state, schema_version, extractor_version,
                  indexed_count, target_count, failed_count, active_job_id, updated_at
                ) VALUES (?, ?, 'pending', ?, ?, 0, ?, 0, ?, ?)
                ON CONFLICT(index_name, library_id) DO UPDATE SET
                  state = CASE
                    WHEN search_index_states.state IN ('ready', 'degraded') THEN search_index_states.state
                    ELSE 'pending'
                  END,
                  schema_version = excluded.schema_version,
                  extractor_version = excluded.extractor_version,
                  target_count = excluded.target_count,
                  active_job_id = excluded.active_job_id,
                  updated_at = excluded.updated_at,
                  error_code = NULL,
                  error_summary = NULL
                """,
                (index_name, library_id, schema_version, extractor_version, target_count, job_id, now),
            )
            row = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return _serialize_job(row)


def claim_next_search_index_job(
    worker_id: str,
    *,
    lease_seconds: float = 300,
) -> dict[str, Any] | None:
    """Claim one queued/interrupted job with a fresh fencing token."""
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            running = conn.execute(
                "SELECT 1 FROM search_index_jobs WHERE state IN ('running', 'cancel_requested') LIMIT 1"
            ).fetchone()
            if running is not None:
                conn.commit()
                return None
            row = conn.execute(
                """
                SELECT * FROM search_index_jobs
                WHERE state IN ('queued', 'interrupted')
                ORDER BY requested_at, id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            token = uuid.uuid4().hex
            cursor = conn.execute(
                """
                UPDATE search_index_jobs
                SET state = 'running', started_at = COALESCE(started_at, ?),
                    claimed_by = ?, claim_token = ?, lease_expires_at = ?
                WHERE id = ? AND state IN ('queued', 'interrupted')
                """,
                (now, worker_id, token, now + max(1.0, lease_seconds), int(row["id"])),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return None
            conn.execute(
                """
                UPDATE search_index_states
                SET state = 'building', active_job_id = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE index_name = ? AND library_id = ?
                """,
                (int(row["id"]), now, now, row["index_name"], int(row["library_id"])),
            )
            claimed = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (int(row["id"]),)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    job = dict(claimed)
    job["claim_token"] = token
    return job


def renew_search_index_job_lease(job_id: int, claim_token: str, *, lease_seconds: float = 300) -> bool:
    """Renew an exact running/cancel-requested claim."""
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE search_index_jobs SET lease_expires_at = ?
            WHERE id = ? AND claim_token = ? AND state IN ('running', 'cancel_requested')
            """,
            (now + max(1.0, lease_seconds), job_id, claim_token),
        )
    return cursor.rowcount == 1


def list_search_index_asset_batch(
    job: dict[str, Any],
    *,
    extractor_version: int,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Read the next active-asset keyset batch for one claimed job."""
    initialize_database()
    batch_limit = min(max(1, limit), 200)
    cursor_asset_id = int(job.get("cursor_asset_id") or 0)
    params: list[Any] = [str(job["index_name"]), int(job["library_id"]), cursor_asset_id]
    missing_predicate = ""
    if str(job["mode"]) == "missing":
        missing_predicate = """
          AND (
            extraction.asset_id IS NULL
            OR extraction.source_fingerprint != printf('%d:%d', COALESCE(asset.mtime_ns, 0), COALESCE(asset.size, 0))
            OR extraction.extractor_version != ?
            OR extraction.status = 'failed'
          )
        """
        params.append(extractor_version)
    params.append(batch_limit)
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT asset.*
            FROM assets AS asset
            LEFT JOIN asset_search_extractions AS extraction
              ON extraction.asset_id = asset.id AND extraction.index_name = ?
            WHERE asset.library_id = ? AND asset.id > ?
              AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND asset.type IN ('image', 'video')
              {missing_predicate}
            ORDER BY asset.id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def record_search_index_extraction(
    job_id: int,
    claim_token: str,
    asset: dict[str, Any],
    *,
    index_name: str,
    extractor_version: int,
    status: str,
    error_code: str | None,
    payload: Any,
    persist: Callable[[sqlite3.Connection, dict[str, Any], Any], None],
    lease_seconds: float = 300,
) -> None:
    """Atomically persist one asset's derived rows, extraction status, and cursor."""
    if status not in SEARCH_EXTRACTION_STATUSES:
        raise ValueError("Invalid search extraction status")
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            job = conn.execute(
                """
                SELECT * FROM search_index_jobs
                WHERE id = ? AND claim_token = ?
                  AND state IN ('running', 'cancel_requested')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
                """,
                (job_id, claim_token, now),
            ).fetchone()
            if job is None:
                raise SearchIndexClaimLost(job_id)
            if status != "failed":
                persist(conn, asset, payload)
            conn.execute(
                """
                INSERT INTO asset_search_extractions (
                  asset_id, index_name, source_fingerprint, extractor_version,
                  status, error_code, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, index_name) DO UPDATE SET
                  source_fingerprint = CASE
                    WHEN excluded.status = 'failed'
                     AND asset_search_extractions.status IN ('ready', 'not_applicable', 'skipped')
                    THEN asset_search_extractions.source_fingerprint
                    ELSE excluded.source_fingerprint
                  END,
                  extractor_version = CASE
                    WHEN excluded.status = 'failed'
                     AND asset_search_extractions.status IN ('ready', 'not_applicable', 'skipped')
                    THEN asset_search_extractions.extractor_version
                    ELSE excluded.extractor_version
                  END,
                  status = CASE
                    WHEN excluded.status = 'failed'
                     AND asset_search_extractions.status IN ('ready', 'not_applicable', 'skipped')
                    THEN asset_search_extractions.status
                    ELSE excluded.status
                  END,
                  error_code = excluded.error_code,
                  indexed_at = excluded.indexed_at
                """,
                (
                    int(asset["id"]),
                    index_name,
                    source_fingerprint(asset),
                    extractor_version,
                    status,
                    _sanitize_error_code(error_code, "extraction_failed") if error_code else None,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE search_index_jobs
                SET cursor_asset_id = ?, processed_count = processed_count + 1,
                    failed_count = failed_count + ?, skipped_count = skipped_count + ?,
                    lease_expires_at = ?
                WHERE id = ? AND claim_token = ?
                """,
                (
                    int(asset["id"]),
                    int(status == "failed"),
                    int(status == "skipped"),
                    now + max(1.0, lease_seconds),
                    job_id,
                    claim_token,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _current_extraction_counts(conn: sqlite3.Connection, index_name: str, library_id: int) -> tuple[int, int, int, int]:
    row = conn.execute(
        """
        SELECT
          count(*) AS target_count,
          count(extraction.asset_id) FILTER (WHERE extraction.status IN ('ready', 'not_applicable', 'skipped')) AS indexed_count,
          count(extraction.asset_id) FILTER (WHERE extraction.status = 'failed') AS failed_count,
          count(extraction.asset_id) FILTER (WHERE extraction.status = 'skipped') AS skipped_count
        FROM assets AS asset
        LEFT JOIN asset_search_extractions AS extraction
          ON extraction.asset_id = asset.id AND extraction.index_name = ?
        WHERE asset.library_id = ? AND asset.offline = 0 AND asset.deleted_at IS NULL
          AND asset.type IN ('image', 'video')
        """,
        (index_name, library_id),
    ).fetchone()
    return (
        int(row["indexed_count"]),
        int(row["target_count"]),
        int(row["failed_count"]),
        int(row["skipped_count"]),
    )


def finish_search_index_job(
    job_id: int,
    claim_token: str,
    state: str,
    *,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any] | None:
    """Fenced terminal transition that also updates the per-library index state."""
    if state not in SEARCH_INDEX_TERMINAL_STATES:
        raise ValueError("Invalid terminal search index job state")
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT * FROM search_index_jobs
                WHERE id = ? AND claim_token = ?
                  AND state IN ('running', 'cancel_requested')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
                """,
                (job_id, claim_token, now),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            code = _sanitize_error_code(error_code) if state == "failed" else None
            summary = _sanitize_error_summary(error_summary) if state == "failed" else None
            conn.execute(
                """
                UPDATE search_index_jobs
                SET state = ?, finished_at = ?, claimed_by = NULL, claim_token = NULL,
                    lease_expires_at = NULL, error_code = ?, error_summary = ?
                WHERE id = ? AND claim_token = ?
                """,
                (state, now, code, summary, job_id, claim_token),
            )
            indexed_count, target_count, failed_count, skipped_count = _current_extraction_counts(
                conn, str(row["index_name"]), int(row["library_id"])
            )
            failed_count = max(failed_count, int(row["failed_count"] or 0))
            skipped_count = max(skipped_count, int(row["skipped_count"] or 0))
            if state == "succeeded":
                index_state = "degraded" if failed_count or skipped_count else "ready"
            elif indexed_count > 0 or target_count == 0:
                index_state = "degraded"
            else:
                index_state = "failed" if state == "failed" else "pending"
            conn.execute(
                """
                UPDATE search_index_states
                SET state = ?, indexed_count = ?, target_count = ?, failed_count = ?, skipped_count = ?,
                    active_job_id = NULL, completed_at = ?, updated_at = ?,
                    error_code = ?, error_summary = ?
                WHERE index_name = ? AND library_id = ? AND active_job_id = ?
                """,
                (
                    index_state,
                    indexed_count,
                    target_count,
                    failed_count,
                    skipped_count,
                    now,
                    now,
                    code,
                    summary,
                    row["index_name"],
                    int(row["library_id"]),
                    job_id,
                ),
            )
            result = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return _serialize_job(result)


def request_search_index_job_cancel(job_id: int) -> dict[str, Any] | None:
    """Request idempotent cancellation, immediately cancelling unclaimed work."""
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                conn.commit()
                return None
            current = str(row["state"])
            if current in SEARCH_INDEX_TERMINAL_STATES or current == "cancel_requested":
                conn.commit()
                return _serialize_job(row)
            if current in {"queued", "interrupted"}:
                conn.execute(
                    "UPDATE search_index_jobs SET state = 'cancelled', finished_at = ? WHERE id = ?",
                    (now, job_id),
                )
                conn.execute(
                    """
                    UPDATE search_index_states
                    SET state = CASE WHEN indexed_count > 0 OR target_count = 0 THEN 'degraded' ELSE 'pending' END,
                        active_job_id = NULL, updated_at = ?
                    WHERE active_job_id = ?
                    """,
                    (now, job_id),
                )
            else:
                conn.execute("UPDATE search_index_jobs SET state = 'cancel_requested' WHERE id = ?", (job_id,))
            updated = conn.execute("SELECT * FROM search_index_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return _serialize_job(updated)


def recover_search_index_jobs(*, reason: str = "Interrupted by server restart") -> list[dict[str, Any]]:
    """Mark stale running work interrupted so the next claim resumes its cursor."""
    initialize_database()
    now = time.time()
    recovered: list[dict[str, Any]] = []
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                "SELECT * FROM search_index_jobs WHERE state IN ('running', 'cancel_requested')"
            ).fetchall()
            for row in rows:
                next_state = "cancelled" if row["state"] == "cancel_requested" else "interrupted"
                conn.execute(
                    """
                    UPDATE search_index_jobs
                    SET state = ?, claimed_by = NULL, claim_token = NULL,
                        lease_expires_at = NULL, finished_at = CASE WHEN ? = 'cancelled' THEN ? ELSE finished_at END,
                        error_code = CASE WHEN ? = 'interrupted' THEN 'interrupted' ELSE error_code END,
                        error_summary = CASE WHEN ? = 'interrupted' THEN ? ELSE error_summary END
                    WHERE id = ? AND claim_token IS ?
                    """,
                    (next_state, next_state, now, next_state, next_state, reason, int(row["id"]), row["claim_token"]),
                )
                if next_state == "cancelled":
                    conn.execute(
                        "UPDATE search_index_states SET active_job_id = NULL, updated_at = ? WHERE active_job_id = ?",
                        (now, int(row["id"])),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE search_index_states
                        SET state = CASE WHEN indexed_count > 0 THEN 'degraded' ELSE 'pending' END,
                            updated_at = ?, error_code = 'interrupted', error_summary = ?
                        WHERE active_job_id = ?
                        """,
                        (now, reason, int(row["id"])),
                    )
                updated = dict(row)
                updated["state"] = next_state
                updated.pop("claim_token", None)
                recovered.append(updated)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return recovered


def search_index_job_control_state(job_id: int, claim_token: str) -> str | None:
    """Return the state for an exact live claim, or None after claim loss."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT state FROM search_index_jobs
            WHERE id = ? AND claim_token = ? AND lease_expires_at > ?
            """,
            (job_id, claim_token, time.time()),
        ).fetchone()
    return str(row["state"]) if row is not None else None
