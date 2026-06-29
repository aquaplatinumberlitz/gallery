"""Build semantic catalog status from persisted catalog facts."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from .. import config
from . import (
    _DB_LOCK,
    _connect,
    canonicalize_catalog_path,
    catalog_path_contains,
    initialize_database,
)
from .identity import (
    asset_matches_image_metadata_sql,
    asset_matches_metadata_job_sql,
)

SummaryState = Literal[
    "unknown",
    "offline",
    "needs_scan",
    "scanning",
    "indexing",
    "needs_update",
    "ready_with_issues",
    "ready",
    "error",
]
AvailabilityState = Literal["unknown", "available", "degraded", "unavailable"]
ScanState = Literal["never", "queued", "scanning", "complete", "failed"]
MetadataState = Literal["disabled", "queued", "indexing", "needs_update", "complete", "failed"]
CatalogOperation = Literal["scan", "rebuild"]
CatalogTrigger = Literal["initial", "manual", "watcher", "scheduled", "startup"]
IssueSource = Literal["availability", "scan", "metadata"]

CONTRACT_VERSION = 1
CATALOG_OPERATION_TYPES = ("scan", "rebuild")
ACTIVE_JOB_STATES = ("queued", "running")
TERMINAL_JOB_STATES = ("succeeded", "failed")
ASSET_TYPES = ("image", "video")


class PrecedenceFacts(TypedDict):
    """Normalized facts consumed by the contract-v1 precedence function."""

    resolved: bool
    availability: AvailabilityState
    active_catalog_job_state: Literal["queued", "running", "cancelled"] | None
    active_metadata_state: Literal["queued", "running", "cancelled"] | None
    latest_covering_scan_failed: bool
    prior_successful_covering_scan: bool
    has_failed_scan_attempt: bool
    metadata_pending_without_active_work: bool
    total_assets: int
    ready_assets: int
    failed_assets: int
    later_scan_failure: bool
    current_metadata_failures: int
    metadata_disabled: bool


class ScopeStatus(TypedDict):
    """Status scope identity."""

    kind: Literal["library", "path"]
    library_id: int
    path: str | None
    import_path_count: int


class AvailabilityStatus(TypedDict):
    """Import-path availability summary."""

    state: AvailabilityState
    available_paths: int
    total_paths: int


class ScanStatus(TypedDict):
    """Catalog scan or rebuild status for the requested scope."""

    state: ScanState
    operation: CatalogOperation | None
    trigger: CatalogTrigger | None
    active_job_id: int | None
    completed_units: int | None
    total_units: int | None
    progress_percent: float | None


class MetadataStatus(TypedDict):
    """Metadata extraction status for active assets in scope."""

    state: MetadataState
    total_assets: int | None
    ready_assets: int | None
    not_ready_assets: int | None
    queued_assets: int | None
    running_assets: int | None
    stale_assets: int | None
    idle_pending_assets: int | None
    failed_assets: int | None
    progress_percent: float | None
    global_active_outside_scope: bool


class Issue(TypedDict):
    """Latest issue details for one status source."""

    source: IssueSource
    path: str | None
    message: str
    updated_at: int


class UnifiedStatus(TypedDict):
    """Contract-v1 semantic status object."""

    contract_version: Literal[1]
    generated_at: int
    summary_state: SummaryState
    scope: ScopeStatus
    availability: AvailabilityStatus
    scan: ScanStatus
    metadata: MetadataStatus
    issue_count: int
    issues: dict[IssueSource, int]
    latest_issue: Issue | None
    last_scan_at: int | None
    last_index_at: int | None


class GlobalRuntime(TypedDict):
    """Process-wide runtime counters included once per response."""

    catalog_worker_count: int
    catalog_active_jobs: int
    catalog_queue_depth: int
    metadata_worker_count: int
    metadata_active_jobs: int
    metadata_queue_depth: int
    metadata_staged_queue_depth: int
    derivative_active_jobs: int
    derivative_queue_depth: int
    watcher_enabled: bool
    watcher_healthy: bool
    watcher_issue: str | None
    scheduled_reconciliation_enabled: bool


class StatusResponseEnvelope(TypedDict):
    """Single-scope status response envelope."""

    contract_version: Literal[1]
    status: UnifiedStatus
    global_runtime: GlobalRuntime
    metadata_lifecycle: dict[str, Any] | None


class LibraryStatusBatchResponse(TypedDict):
    """Admin library status batch response envelope."""

    contract_version: Literal[1]
    generated_at: int
    items: list[dict[str, Any]]
    global_runtime: GlobalRuntime
    metadata_lifecycle: dict[str, Any] | None


class CatalogStatusScopeError(ValueError):
    """Raised when a requested status scope is outside the library."""


def derive_summary_state(facts: PrecedenceFacts) -> SummaryState:
    """Apply the locked catalog status precedence for contract version 1."""
    if not facts["resolved"]:
        return "unknown"
    if facts["availability"] == "unavailable":
        return "offline"
    if facts["active_catalog_job_state"] in {"queued", "running"}:
        return "scanning"
    if facts["active_metadata_state"] in {"queued", "running"}:
        return "indexing"
    if facts["latest_covering_scan_failed"] and not facts["prior_successful_covering_scan"]:
        return "error"
    if not facts["prior_successful_covering_scan"] and not facts["has_failed_scan_attempt"]:
        return "needs_scan"
    if (
        not facts["metadata_disabled"]
        and facts["total_assets"] > 0
        and facts["ready_assets"] == 0
        and facts["failed_assets"] == facts["total_assets"]
    ):
        return "error"
    if facts["metadata_pending_without_active_work"]:
        return "needs_update"
    if facts["later_scan_failure"] or facts["current_metadata_failures"] > 0 or facts["availability"] == "degraded":
        return "ready_with_issues"
    return "ready"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    return int(float(value) * 1000)


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scope_sql(alias: str, scope_path: str | None) -> tuple[str, list[Any]]:
    if scope_path is None:
        return "", []
    path_expr = f"{alias}.path" if alias else "path"
    prefix = f"{scope_path.rstrip(os.sep)}{os.sep}"
    return (
        f" AND ({path_expr} = ? OR ({path_expr} LIKE ? ESCAPE '\\' COLLATE BINARY AND substr({path_expr}, 1, ?) = ?))",
        [
            scope_path,
            f"{_like_escape(prefix)}%",
            len(prefix),
            prefix,
        ],
    )


def _latest_metadata_jobs_sql() -> str:
    return """
        SELECT path, mtime_ns, size, state, error, updated_at, mtime
        FROM (
          SELECT mij.path, mij.mtime_ns, mij.size, mij.state, mij.error, mij.updated_at, mij.mtime,
                 row_number() OVER (
                   PARTITION BY mij.path, mij.mtime_ns, mij.size
                   ORDER BY mij.updated_at DESC, mij.rowid DESC
                 ) AS latest_rank
          FROM metadata_index_jobs AS mij
        )
        WHERE latest_rank = 1
    """


def _progress_percent(current: int | None, total: int | None, state: ScanState) -> float | None:
    if total is None:
        return None
    if total == 0:
        return 100 if state == "complete" else None
    completed = 0 if current is None else max(0, current)
    return min(100, max(0, (completed / total) * 100))


def _job_sort_time(job: Any) -> tuple[float, int]:
    timestamp = job["finished_at"] if job["finished_at"] is not None else job["updated_at"]
    return float(timestamp or job["created_at"] or 0), int(job["id"])


def _job_scope_covers_status(job_scope: str | None, requested_scope: str | None) -> bool:
    if requested_scope is None:
        return job_scope is None
    if job_scope is None:
        return True
    return catalog_path_contains(str(job_scope), requested_scope)


def _select_active_job(jobs: list[Any], scope_path: str | None) -> Any | None:
    covering = [
        job
        for job in jobs
        if job["state"] in ACTIVE_JOB_STATES and _job_scope_covers_status(job["scope_path"], scope_path)
    ]
    if not covering:
        return None
    return sorted(
        covering,
        key=lambda job: (
            0 if job["state"] == "running" else 1,
            -int(job["priority"] or 0),
            float(job["created_at"] or 0),
            int(job["id"]),
        ),
    )[0]


def _latest_terminal_job(jobs: list[Any], scope_path: str | None, *, state: str | None = None) -> Any | None:
    covering = [
        job
        for job in jobs
        if job["state"] in TERMINAL_JOB_STATES
        and (state is None or job["state"] == state)
        and _job_scope_covers_status(job["scope_path"], scope_path)
    ]
    if not covering:
        return None
    return max(covering, key=_job_sort_time)


def _scan_state_for_job(job: Any | None) -> ScanState:
    if job is None:
        return "never"
    state = str(job["state"])
    if state == "queued":
        return "queued"
    if state == "running":
        return "scanning"
    if state == "succeeded":
        return "complete"
    if state == "failed":
        return "failed"
    return "never"


def _scan_status(job: Any | None) -> ScanStatus:
    scan_state = _scan_state_for_job(job)
    if job is None:
        return {
            "state": "never",
            "operation": None,
            "trigger": None,
            "active_job_id": None,
            "completed_units": None,
            "total_units": None,
            "progress_percent": None,
        }
    current = int(job["progress_current"] or 0)
    total = int(job["progress_total"]) if job["progress_total"] is not None else None
    return {
        "state": scan_state,
        "operation": job["type"],
        "trigger": job["trigger"],
        "active_job_id": int(job["id"]) if scan_state in {"queued", "scanning"} else None,
        "completed_units": current,
        "total_units": total,
        "progress_percent": _progress_percent(current, total, scan_state),
    }


def _availability_for_import_paths(
    import_paths: list[Any], generated_at: int
) -> tuple[AvailabilityStatus, list[Issue]]:
    total_paths = len(import_paths)
    offline = [path for path in import_paths if not Path(path["path"]).is_dir()]
    available_paths = total_paths - len(offline)
    if total_paths == 0:
        state: AvailabilityState = "unknown"
    elif available_paths == 0:
        state = "unavailable"
    elif available_paths < total_paths:
        state = "degraded"
    else:
        state = "available"
    issues: list[Issue] = [
        {
            "source": "availability",
            "path": str(path["path"]),
            "message": "Import path is unavailable",
            "updated_at": _epoch_ms(path["updated_at"]) or generated_at,
        }
        for path in offline
    ]
    return {
        "state": state,
        "available_paths": available_paths,
        "total_paths": total_paths,
    }, issues


def _availability_for_path(scope_path: str, generated_at: int) -> tuple[AvailabilityStatus, list[Issue]]:
    available = Path(scope_path).is_dir()
    issues: list[Issue] = []
    if not available:
        issues.append(
            {
                "source": "availability",
                "path": scope_path,
                "message": "Scope path is unavailable",
                "updated_at": generated_at,
            }
        )
    return {
        "state": "available" if available else "unavailable",
        "available_paths": 1 if available else 0,
        "total_paths": 1,
    }, issues


def _metadata_status_from_counts(
    counts: dict[str, int],
    *,
    scan_state: ScanState,
    prior_successful_covering_scan: bool,
    active_catalog_job: Any | None,
    global_active_outside_scope: bool,
) -> MetadataStatus:
    if not config.METADATA_INDEXER_ENABLED:
        return {
            "state": "disabled",
            "total_assets": None,
            "ready_assets": None,
            "not_ready_assets": None,
            "queued_assets": None,
            "running_assets": None,
            "stale_assets": None,
            "idle_pending_assets": None,
            "failed_assets": None,
            "progress_percent": None,
            "global_active_outside_scope": global_active_outside_scope,
        }

    total_assets = counts["total"]
    ready_assets = min(counts["ready"], total_assets)
    failed_assets = min(counts["failed"], max(0, total_assets - ready_assets))
    queued_assets = min(counts["queued"], max(0, total_assets - ready_assets - failed_assets))
    running_assets = min(counts["running"], max(0, total_assets - ready_assets - failed_assets - queued_assets))
    stale_assets = min(
        counts["stale"],
        max(0, total_assets - ready_assets - failed_assets - queued_assets - running_assets),
    )
    not_ready_assets = max(0, total_assets - ready_assets - failed_assets)
    idle_pending_assets = max(0, not_ready_assets - queued_assets - running_assets - stale_assets)

    if active_catalog_job is not None and total_assets == 0 and not prior_successful_covering_scan:
        state: MetadataState = "queued"
        progress: float | None = None
    elif running_assets > 0:
        state = "indexing"
        progress = (ready_assets / total_assets) * 100 if total_assets else None
    elif queued_assets > 0:
        state = "queued"
        progress = (ready_assets / total_assets) * 100 if total_assets else None
    elif stale_assets > 0 or idle_pending_assets > 0:
        state = "needs_update"
        progress = (ready_assets / total_assets) * 100 if total_assets else None
    elif failed_assets > 0:
        state = "failed"
        progress = (ready_assets / total_assets) * 100 if total_assets else None
    else:
        state = "complete"
        if total_assets == 0:
            progress = 100 if scan_state == "complete" or prior_successful_covering_scan else None
        else:
            progress = (ready_assets / total_assets) * 100

    return {
        "state": state,
        "total_assets": total_assets,
        "ready_assets": ready_assets,
        "not_ready_assets": not_ready_assets,
        "queued_assets": queued_assets,
        "running_assets": running_assets,
        "stale_assets": stale_assets,
        "idle_pending_assets": idle_pending_assets,
        "failed_assets": failed_assets,
        "progress_percent": progress,
        "global_active_outside_scope": global_active_outside_scope,
    }


def _metadata_active_state(metadata: MetadataStatus) -> Literal["queued", "running", "cancelled"] | None:
    if metadata["state"] == "queued":
        return "queued"
    if metadata["state"] == "indexing":
        return "running"
    return None


def _latest_issue(issues: list[Issue]) -> Issue | None:
    if not issues:
        return None
    priority = {"scan": 2, "availability": 1, "metadata": 0}
    return max(issues, key=lambda item: (item["updated_at"], priority[item["source"]]))


def _metadata_counts_for_scope(conn: Any, library_id: int, scope_path: str | None) -> dict[str, int]:
    scope_filter, scope_params = _scope_sql("a", scope_path)
    row = conn.execute(
        f"""
        SELECT
          count(*) AS total,
          sum(CASE WHEN a.metadata_state = 'done' AND im.path IS NOT NULL THEN 1 ELSE 0 END) AS ready,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'queued'
                THEN 1 ELSE 0 END) AS queued,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'running'
                THEN 1 ELSE 0 END) AS running,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'stale'
                THEN 1 ELSE 0 END) AS stale,
          sum(CASE
                WHEN a.metadata_state = 'failed'
                  OR COALESCE(mij.state, '') = 'failed'
                THEN 1 ELSE 0 END) AS failed
        FROM assets AS a
        LEFT JOIN image_metadata AS im
          ON im.path = a.path AND im.size = a.size
         AND ({asset_matches_image_metadata_sql()})
        LEFT JOIN ({_latest_metadata_jobs_sql()}) AS mij
          ON mij.path = a.path AND mij.size = a.size
         AND ({asset_matches_metadata_job_sql(job_alias="mij")})
        WHERE a.library_id = ?
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
          {scope_filter}
        """,
        [library_id, *scope_params],
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "ready": int(row["ready"] or 0),
        "queued": int(row["queued"] or 0),
        "running": int(row["running"] or 0),
        "stale": int(row["stale"] or 0),
        "failed": int(row["failed"] or 0),
    }


def _batch_metadata_counts(conn: Any, library_ids: list[int]) -> dict[int, dict[str, int]]:
    if not library_ids:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    rows = conn.execute(
        f"""
        SELECT
          a.library_id,
          count(*) AS total,
          sum(CASE WHEN a.metadata_state = 'done' AND im.path IS NOT NULL THEN 1 ELSE 0 END) AS ready,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'queued'
                THEN 1 ELSE 0 END) AS queued,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'running'
                THEN 1 ELSE 0 END) AS running,
          sum(CASE
                WHEN a.metadata_state != 'done'
                 AND COALESCE(mij.state, '') = 'stale'
                THEN 1 ELSE 0 END) AS stale,
          sum(CASE
                WHEN a.metadata_state = 'failed'
                  OR COALESCE(mij.state, '') = 'failed'
                THEN 1 ELSE 0 END) AS failed
        FROM assets AS a
        LEFT JOIN image_metadata AS im
          ON im.path = a.path AND im.size = a.size
         AND ({asset_matches_image_metadata_sql()})
        LEFT JOIN ({_latest_metadata_jobs_sql()}) AS mij
          ON mij.path = a.path AND mij.size = a.size
         AND ({asset_matches_metadata_job_sql(job_alias="mij")})
        WHERE a.library_id IN ({placeholders})
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
        GROUP BY a.library_id
        """,
        library_ids,
    ).fetchall()
    empty = {"total": 0, "ready": 0, "queued": 0, "running": 0, "stale": 0, "failed": 0}
    counts = {library_id: dict(empty) for library_id in library_ids}
    for row in rows:
        counts[int(row["library_id"])] = {
            "total": int(row["total"] or 0),
            "ready": int(row["ready"] or 0),
            "queued": int(row["queued"] or 0),
            "running": int(row["running"] or 0),
            "stale": int(row["stale"] or 0),
            "failed": int(row["failed"] or 0),
        }
    return counts


def _last_index_at_for_scope(conn: Any, library_id: int, scope_path: str | None) -> int | None:
    scope_filter, scope_params = _scope_sql("a", scope_path)
    row = conn.execute(
        f"""
        SELECT max(COALESCE(im.indexed_at, im.updated_at)) AS last_index_at
        FROM assets AS a
        JOIN image_metadata AS im
          ON im.path = a.path AND im.size = a.size
         AND ({asset_matches_image_metadata_sql()})
        WHERE a.library_id = ?
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
          AND a.metadata_state = 'done'
          {scope_filter}
        """,
        [library_id, *scope_params],
    ).fetchone()
    return _epoch_ms(row["last_index_at"] if row else None)


def _batch_last_index_at(conn: Any, library_ids: list[int]) -> dict[int, int | None]:
    if not library_ids:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    rows = conn.execute(
        f"""
        SELECT a.library_id, max(COALESCE(im.indexed_at, im.updated_at)) AS last_index_at
        FROM assets AS a
        JOIN image_metadata AS im
          ON im.path = a.path AND im.size = a.size
         AND ({asset_matches_image_metadata_sql()})
        WHERE a.library_id IN ({placeholders})
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
          AND a.metadata_state = 'done'
        GROUP BY a.library_id
        """,
        library_ids,
    ).fetchall()
    result = dict.fromkeys(library_ids)
    for row in rows:
        result[int(row["library_id"])] = _epoch_ms(row["last_index_at"])
    return result


def _latest_metadata_issue_for_scope(conn: Any, library_id: int, scope_path: str | None) -> Issue | None:
    scope_filter, scope_params = _scope_sql("a", scope_path)
    row = conn.execute(
        f"""
        SELECT a.path, mij.error, mij.updated_at
        FROM assets AS a
        JOIN ({_latest_metadata_jobs_sql()}) AS mij
          ON mij.path = a.path AND mij.size = a.size
         AND ({asset_matches_metadata_job_sql(job_alias="mij")})
        WHERE a.library_id = ?
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
          AND mij.state = 'failed'
          {scope_filter}
        ORDER BY mij.updated_at DESC, a.path ASC
        LIMIT 1
        """,
        [library_id, *scope_params],
    ).fetchone()
    if row is None:
        return None
    return {
        "source": "metadata",
        "path": str(row["path"]),
        "message": row["error"] or "Metadata extraction failed",
        "updated_at": _epoch_ms(row["updated_at"]) or _now_ms(),
    }


def _batch_metadata_issues(conn: Any, library_ids: list[int]) -> dict[int, Issue | None]:
    if not library_ids:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    rows = conn.execute(
        f"""
        SELECT a.library_id, a.path, mij.error, mij.updated_at
        FROM assets AS a
        JOIN ({_latest_metadata_jobs_sql()}) AS mij
          ON mij.path = a.path AND mij.size = a.size
         AND ({asset_matches_metadata_job_sql(job_alias="mij")})
        WHERE a.library_id IN ({placeholders})
          AND a.type IN ('image', 'video')
          AND a.deleted_at IS NULL
          AND a.offline = 0
          AND mij.state = 'failed'
        ORDER BY a.library_id, mij.updated_at DESC, a.path ASC
        """,
        library_ids,
    ).fetchall()
    result = dict.fromkeys(library_ids)
    for row in rows:
        library_id = int(row["library_id"])
        if result[library_id] is None:
            result[library_id] = {
                "source": "metadata",
                "path": str(row["path"]),
                "message": row["error"] or "Metadata extraction failed",
                "updated_at": _epoch_ms(row["updated_at"]) or _now_ms(),
            }
    return result


def _active_metadata_paths(conn: Any) -> list[str]:
    rows = conn.execute(
        """
        SELECT path FROM metadata_index_jobs
        WHERE state IN ('queued', 'running')
        """
    ).fetchall()
    return [str(row["path"]) for row in rows]


def _global_active_outside_scope(active_paths: list[str], import_paths: list[Any], scope_path: str | None) -> bool:
    if not active_paths:
        return False
    if scope_path is not None:
        return any(not catalog_path_contains(scope_path, path) for path in active_paths)
    roots = [str(path["path"]) for path in import_paths]
    return any(not any(catalog_path_contains(root, path) for root in roots) for path in active_paths)


def _issue_counts(
    availability_issues: list[Issue], scan_issue: Issue | None, metadata_failures: int
) -> dict[IssueSource, int]:
    return {
        "availability": len(availability_issues),
        "scan": 1 if scan_issue is not None else 0,
        "metadata": metadata_failures,
    }


def _build_status(
    *,
    library_id: int,
    generated_at: int,
    scope: ScopeStatus,
    availability: AvailabilityStatus,
    availability_issues: list[Issue],
    jobs: list[Any],
    metadata_counts: dict[str, int],
    last_index_at: int | None,
    metadata_issue: Issue | None,
    active_metadata_paths: list[str],
    import_paths: list[Any],
) -> UnifiedStatus:
    scope_path = scope["path"]
    active_job = _select_active_job(jobs, scope_path)
    latest_terminal = _latest_terminal_job(jobs, scope_path)
    latest_success = _latest_terminal_job(jobs, scope_path, state="succeeded")
    scan_job = active_job or latest_terminal
    scan = _scan_status(scan_job)
    prior_successful_covering_scan = latest_success is not None
    last_scan_at = _epoch_ms(latest_success["finished_at"] if latest_success is not None else None)
    scan_issue: Issue | None = None
    later_scan_failure = latest_terminal is not None and latest_terminal["state"] == "failed"
    if active_job is None and later_scan_failure:
        scan_issue = {
            "source": "scan",
            "path": latest_terminal["scope_path"],
            "message": latest_terminal["message"] or latest_terminal["error"] or "Catalog update failed",
            "updated_at": _epoch_ms(latest_terminal["updated_at"]) or generated_at,
        }

    metadata = _metadata_status_from_counts(
        metadata_counts,
        scan_state=scan["state"],
        prior_successful_covering_scan=prior_successful_covering_scan,
        active_catalog_job=active_job,
        global_active_outside_scope=_global_active_outside_scope(active_metadata_paths, import_paths, scope_path),
    )
    metadata_failures = int(metadata["failed_assets"] or 0)
    issues = _issue_counts(availability_issues, scan_issue, metadata_failures)
    issue_list = [*availability_issues]
    if scan_issue is not None:
        issue_list.append(scan_issue)
    if metadata_issue is not None:
        issue_list.append(metadata_issue)

    facts: PrecedenceFacts = {
        "resolved": True,
        "availability": availability["state"],
        "active_catalog_job_state": active_job["state"] if active_job is not None else None,
        "active_metadata_state": _metadata_active_state(metadata),
        "latest_covering_scan_failed": latest_terminal is not None and latest_terminal["state"] == "failed",
        "prior_successful_covering_scan": prior_successful_covering_scan,
        "has_failed_scan_attempt": any(
            job["state"] == "failed" and _job_scope_covers_status(job["scope_path"], scope_path) for job in jobs
        ),
        "metadata_pending_without_active_work": metadata["state"] == "needs_update",
        "total_assets": int(metadata["total_assets"] or 0),
        "ready_assets": int(metadata["ready_assets"] or 0),
        "failed_assets": metadata_failures,
        "later_scan_failure": scan_issue is not None and prior_successful_covering_scan,
        "current_metadata_failures": metadata_failures,
        "metadata_disabled": metadata["state"] == "disabled",
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "summary_state": derive_summary_state(facts),
        "scope": scope,
        "availability": availability,
        "scan": scan,
        "metadata": metadata,
        "issue_count": sum(issues.values()),
        "issues": issues,
        "latest_issue": _latest_issue(issue_list),
        "last_scan_at": last_scan_at,
        "last_index_at": last_index_at,
    }


def build_global_runtime() -> GlobalRuntime:
    """Return process and durable-queue runtime status for one response envelope."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        catalog_running = int(
            conn.execute(
                """
                SELECT count(*) FROM library_jobs
                WHERE type IN ('scan', 'rebuild') AND state = 'running'
                """
            ).fetchone()[0]
        )
        catalog_queued = int(
            conn.execute(
                """
                SELECT count(*) FROM library_jobs
                WHERE type IN ('scan', 'rebuild') AND state = 'queued'
                """
            ).fetchone()[0]
        )
        derivative_running = int(
            conn.execute(
                """
                SELECT count(*) FROM derivative_jobs
                WHERE state = 'running'
                """
            ).fetchone()[0]
        )
        derivative_queued = int(
            conn.execute(
                """
                SELECT count(*) FROM derivative_jobs
                WHERE state = 'queued'
                """
            ).fetchone()[0]
        )

    from ..indexer import get_indexer_runtime_status
    from ..refresh import get_refresh_status
    from ..scan_worker import runtime_status
    from ..watcher import get_watcher_status

    catalog_runtime = runtime_status()
    metadata_runtime = get_indexer_runtime_status()
    watcher = get_watcher_status()
    refresh = get_refresh_status()

    watcher_enabled = bool(watcher["enabled"])
    watcher_healthy = True
    watcher_issue: str | None = None
    if watcher_enabled and not watcher["dependency_available"]:
        watcher_healthy = False
        watcher_issue = "watchdog dependency unavailable"
    elif watcher_enabled and watcher["roots"] and not watcher["alive"]:
        watcher_healthy = False
        watcher_issue = "watcher thread is not running"

    return {
        "catalog_worker_count": int(catalog_runtime["worker_count"]),
        "catalog_active_jobs": catalog_running,
        "catalog_queue_depth": catalog_queued,
        "metadata_worker_count": int(metadata_runtime["worker_count"]),
        "metadata_active_jobs": int(metadata_runtime["active_jobs"]),
        "metadata_queue_depth": int(metadata_runtime["runtime_queue_depth"]),
        "metadata_staged_queue_depth": int(metadata_runtime["staged_path_queue_depth"]),
        "derivative_active_jobs": derivative_running,
        "derivative_queue_depth": derivative_queued,
        "watcher_enabled": watcher_enabled,
        "watcher_healthy": watcher_healthy,
        "watcher_issue": watcher_issue,
        "scheduled_reconciliation_enabled": bool(refresh["enabled"]),
    }


def build_catalog_status(library_id: int, scope_path: str | Path | None = None) -> StatusResponseEnvelope:
    """Build a status envelope for one library or one path inside that library."""
    initialize_database()
    requested_scope = canonicalize_catalog_path(scope_path) if scope_path is not None else None
    generated_at = _now_ms()
    with _DB_LOCK, _connect() as conn:
        library = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        if library is None:
            raise KeyError(library_id)
        import_paths = conn.execute(
            """
            SELECT id, library_id, path, position, created_at, updated_at
            FROM library_import_paths
            WHERE library_id = ?
            ORDER BY position, id
            """,
            (library_id,),
        ).fetchall()
        if requested_scope is not None and not any(
            catalog_path_contains(path["path"], requested_scope) for path in import_paths
        ):
            raise CatalogStatusScopeError("Status scope is outside this library")

        if requested_scope is None:
            scope: ScopeStatus = {
                "kind": "library",
                "library_id": library_id,
                "path": None,
                "import_path_count": len(import_paths),
            }
            availability, availability_issues = _availability_for_import_paths(import_paths, generated_at)
        else:
            scope = {
                "kind": "path",
                "library_id": library_id,
                "path": requested_scope,
                "import_path_count": 1,
            }
            availability, availability_issues = _availability_for_path(requested_scope, generated_at)

        jobs = conn.execute(
            """
            SELECT * FROM library_jobs
            WHERE library_id = ? AND type IN ('scan', 'rebuild')
            """,
            (library_id,),
        ).fetchall()
        active_paths = _active_metadata_paths(conn)
        status = _build_status(
            library_id=library_id,
            generated_at=generated_at,
            scope=scope,
            availability=availability,
            availability_issues=availability_issues,
            jobs=list(jobs),
            metadata_counts=_metadata_counts_for_scope(conn, library_id, requested_scope),
            last_index_at=_last_index_at_for_scope(conn, library_id, requested_scope),
            metadata_issue=_latest_metadata_issue_for_scope(conn, library_id, requested_scope),
            active_metadata_paths=active_paths,
            import_paths=list(import_paths),
        )
    # Wire metadata lifecycle diagnostics (lazy import to avoid circular deps)
    try:
        from backend.indexer import get_metadata_lifecycle_status

        lifecycle = get_metadata_lifecycle_status(scope_path=requested_scope)
    except Exception:
        lifecycle = None

    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "global_runtime": build_global_runtime(),
        "metadata_lifecycle": lifecycle,
    }


def build_library_status_batch() -> LibraryStatusBatchResponse:
    """Build admin-list statuses with grouped DB queries and one global runtime."""
    initialize_database()
    generated_at = _now_ms()
    with _DB_LOCK, _connect() as conn:
        libraries = conn.execute("SELECT * FROM libraries ORDER BY id").fetchall()
        library_ids = [int(library["id"]) for library in libraries]
        if not library_ids:
            items: list[dict[str, Any]] = []
        else:
            placeholders = ",".join("?" for _ in library_ids)
            import_path_rows = conn.execute(
                f"""
                SELECT id, library_id, path, position, created_at, updated_at
                FROM library_import_paths
                WHERE library_id IN ({placeholders})
                ORDER BY library_id, position, id
                """,
                library_ids,
            ).fetchall()
            import_paths_by_library: dict[int, list[Any]] = {library_id: [] for library_id in library_ids}
            for row in import_path_rows:
                import_paths_by_library[int(row["library_id"])].append(row)

            job_rows = conn.execute(
                f"""
                SELECT * FROM library_jobs
                WHERE library_id IN ({placeholders})
                  AND type IN ('scan', 'rebuild')
                  AND scope_path IS NULL
                """,
                library_ids,
            ).fetchall()
            jobs_by_library: dict[int, list[Any]] = {library_id: [] for library_id in library_ids}
            for row in job_rows:
                jobs_by_library[int(row["library_id"])].append(row)

            metadata_counts = _batch_metadata_counts(conn, library_ids)
            last_index_at = _batch_last_index_at(conn, library_ids)
            metadata_issues = _batch_metadata_issues(conn, library_ids)
            active_paths = _active_metadata_paths(conn)
            items = []
            for library in libraries:
                library_id = int(library["id"])
                import_paths = import_paths_by_library[library_id]
                scope: ScopeStatus = {
                    "kind": "library",
                    "library_id": library_id,
                    "path": None,
                    "import_path_count": len(import_paths),
                }
                availability, availability_issues = _availability_for_import_paths(import_paths, generated_at)
                status = _build_status(
                    library_id=library_id,
                    generated_at=generated_at,
                    scope=scope,
                    availability=availability,
                    availability_issues=availability_issues,
                    jobs=jobs_by_library[library_id],
                    metadata_counts=metadata_counts[library_id],
                    last_index_at=last_index_at[library_id],
                    metadata_issue=metadata_issues[library_id],
                    active_metadata_paths=active_paths,
                    import_paths=import_paths,
                )
                items.append({"library_id": library_id, "status": status})
    try:
        from backend.indexer import get_metadata_lifecycle_status

        lifecycle = get_metadata_lifecycle_status()
    except Exception:
        lifecycle = None

    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "items": items,
        "global_runtime": build_global_runtime(),
        "metadata_lifecycle": lifecycle,
    }
