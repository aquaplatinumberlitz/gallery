"""Imported-data maintenance operations."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .catalog_maintenance_gate import MaintenanceGateBusy, maintenance_gate
from .derivative_scheduler import scheduler
from .errors import APIError
from .library_events import event_payload, publish
from .metadata_store import _DB_LOCK, CatalogJobConflict, _connect, create_job, list_libraries, update_job_state
from .metadata_store._schema import initialize_database
from .scan_worker import queue_rebuild

RESET_CONFIRM_PHRASE = "RESET CATALOG DATABASE"


@contextmanager
def _maintenance_operation() -> Iterator[None]:
    try:
        with maintenance_gate():
            yield
    except MaintenanceGateBusy as exc:
        raise APIError(409, "maintenance_busy", "Another maintenance operation is active") from exc


def _require_confirm(confirm: bool) -> None:
    if not confirm:
        raise APIError(400, "confirmation_required", "Maintenance action requires explicit confirmation")


def _active_work_counts_conn(conn: Any) -> dict[str, int]:
    return {
        "catalog_jobs": int(
            conn.execute("SELECT count(*) FROM library_jobs WHERE state IN ('queued', 'running')").fetchone()[0]
        ),
        "metadata_jobs": int(
            conn.execute("SELECT count(*) FROM metadata_index_jobs WHERE state IN ('queued', 'running')").fetchone()[0]
        ),
        "derivative_jobs": int(
            conn.execute("SELECT count(*) FROM derivative_jobs WHERE state IN ('queued', 'running')").fetchone()[0]
        ),
    }


def _raise_if_active_work() -> None:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        counts = _active_work_counts_conn(conn)
    if any(counts.values()):
        raise APIError(409, "maintenance_busy", "Maintenance cannot run while jobs are active", extra=counts)


def _count_rows_conn(conn: Any, table: str) -> int:
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _clear_imported_data_rows() -> dict[str, int]:
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        counts = {
            "assets_cleared": _count_rows_conn(conn, "assets"),
            "file_index_rows_cleared": _count_rows_conn(conn, "file_index"),
            "image_metadata_rows_cleared": _count_rows_conn(conn, "image_metadata"),
            "image_resource_rows_cleared": _count_rows_conn(conn, "image_resources"),
            "metadata_jobs_cleared": _count_rows_conn(conn, "metadata_index_jobs"),
            "library_jobs_cleared": _count_rows_conn(conn, "library_jobs"),
            "rebuild_staging_rows_cleared": _count_rows_conn(conn, "catalog_rebuild_entries"),
            "folder_index_rows_cleared": _count_rows_conn(conn, "folder_index_state"),
            "integrity_runs_cleared": _count_rows_conn(conn, "integrity_check_runs"),
        }
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM catalog_rebuild_entries")
            conn.execute("DELETE FROM library_jobs")
            conn.execute("DELETE FROM metadata_index_jobs")
            conn.execute("DELETE FROM image_resources")
            conn.execute("DELETE FROM image_metadata")
            conn.execute("DELETE FROM file_index_fts")
            conn.execute("DELETE FROM file_index")
            conn.execute("DELETE FROM folder_index_state")
            conn.execute("DELETE FROM assets")
            conn.execute("DELETE FROM integrity_check_runs")
            conn.execute(
                """
                UPDATE libraries
                SET state = 'discovering',
                    last_scan_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                """,
                (now,),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return counts


def _derivative_clear_counts(result: dict[str, int]) -> dict[str, int]:
    return {
        "derivative_catalog_entries_cleared": int(result.get("catalog_entries_cleared", 0)),
        "preview_files_deleted": int(result.get("files_deleted", 0)),
    }


def clear_imported_data(*, confirm: bool) -> dict[str, Any]:
    """Clear scan-derived data while preserving registered libraries."""
    _require_confirm(confirm)
    with _maintenance_operation():
        _raise_if_active_work()
        derivative_result = scheduler.clear_all()
        counts = _clear_imported_data_rows()
        return {
            "state": "cleared",
            "libraries_preserved": len(list_libraries()),
            **counts,
            **_derivative_clear_counts(derivative_result),
        }


def _emit_job(job: dict[str, Any], event_type: str = "job.updated") -> None:
    publish(event_payload(event_type, job))
    if job["library_id"] is not None:
        publish(event_payload("library.progress", job))


def rebuild_imported_data(*, confirm: bool) -> dict[str, Any]:
    """Clear imported data and queue whole-library rebuild jobs."""
    _require_confirm(confirm)
    with _maintenance_operation():
        _raise_if_active_work()
        derivative_result = scheduler.clear_all()
        clear_counts = _clear_imported_data_rows()
        libraries = list_libraries()
        parent = create_job(
            "rebuild_imported_data",
            progress_total=len(libraries),
            message="Rebuild imported data queued",
        )
        _emit_job(parent)
        if not libraries:
            running = update_job_state(
                int(parent["id"]),
                "running",
                progress_current=0,
                progress_total=0,
                message="No libraries to rebuild",
            )
            if running is not None:
                _emit_job(running)
            completed = update_job_state(
                int(parent["id"]),
                "succeeded",
                progress_current=0,
                progress_total=0,
                message="No libraries to rebuild",
            )
            if completed is not None:
                _emit_job(completed, "job.completed")
            return {
                "job_id": parent["id"],
                "state": "succeeded",
                "child_job_ids": [],
                "count": 0,
                "clear": {**clear_counts, **_derivative_clear_counts(derivative_result)},
            }

        child_job_ids: list[int] = []
        for library in libraries:
            try:
                job, _created = queue_rebuild(int(library["id"]), parent_job_id=int(parent["id"]))
            except CatalogJobConflict as exc:
                raise APIError(409, "maintenance_busy", "Maintenance cannot run while jobs are active") from exc
            child_job_ids.append(int(job["id"]))
        running = update_job_state(
            int(parent["id"]),
            "running",
            progress_current=0,
            progress_total=len(child_job_ids),
            message="Rebuilding imported data",
            counters={"total": len(child_job_ids), "succeeded": 0, "failed": 0},
        )
        if running is not None:
            _emit_job(running)
        return {
            "job_id": parent["id"],
            "state": "running",
            "child_job_ids": child_job_ids,
            "count": len(child_job_ids),
            "clear": {**clear_counts, **_derivative_clear_counts(derivative_result)},
        }


def reset_catalog_database(*, confirm_phrase: str) -> dict[str, Any]:
    """Clear all catalog database rows, including registered libraries."""
    if confirm_phrase != RESET_CONFIRM_PHRASE:
        raise APIError(400, "confirmation_required", f"Reset requires typing {RESET_CONFIRM_PHRASE}")
    with _maintenance_operation():
        _raise_if_active_work()
        derivative_result = scheduler.clear_all()
        initialize_database()
        with _DB_LOCK, _connect() as conn:
            counts = {
                "libraries_deleted": _count_rows_conn(conn, "libraries"),
                "import_paths_deleted": _count_rows_conn(conn, "library_import_paths"),
                "exclusion_patterns_deleted": _count_rows_conn(conn, "library_exclusion_patterns"),
                "assets_deleted": _count_rows_conn(conn, "assets"),
                "image_metadata_rows_deleted": _count_rows_conn(conn, "image_metadata"),
                "metadata_jobs_deleted": _count_rows_conn(conn, "metadata_index_jobs"),
                "library_jobs_deleted": _count_rows_conn(conn, "library_jobs"),
            }
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM catalog_rebuild_entries")
                conn.execute("DELETE FROM library_jobs")
                conn.execute("DELETE FROM metadata_index_jobs")
                conn.execute("DELETE FROM image_resources")
                conn.execute("DELETE FROM image_metadata")
                conn.execute("DELETE FROM file_index_fts")
                conn.execute("DELETE FROM file_index")
                conn.execute("DELETE FROM folder_index_state")
                conn.execute("DELETE FROM assets")
                conn.execute("DELETE FROM library_exclusion_patterns")
                conn.execute("DELETE FROM library_import_paths")
                conn.execute("DELETE FROM libraries")
                conn.execute("DELETE FROM integrity_check_runs")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return {"state": "reset", **counts, **_derivative_clear_counts(derivative_result)}
