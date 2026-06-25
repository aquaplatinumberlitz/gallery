"""Periodic background integrity checker for cross-table consistency."""

import logging
import threading
import time
from pathlib import Path

from .metadata_store import _DB_LOCK, _connect
from .metadata_store.identity import (
    asset_matches_image_metadata_sql,
    job_matches_image_metadata_sql,
)

logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Periodic background integrity checker for cross-table consistency."""

    def __init__(self, interval: int = 3600):
        """Initialize with configurable check interval (minimum 60s)."""
        self.interval = max(60, interval)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.is_running: bool = False

    def start(self) -> None:
        """Start the background checker daemon thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="integrity-checker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the background checker and wait for the thread to finish."""
        self._stop_event.set()
        with self._lock:
            if self._thread is not None:
                self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.interval):
            try:
                self.run_and_persist(trigger="daemon")
            except Exception:
                logger.exception("Integrity checker crashed")

    def run_and_persist(self, trigger: str = "manual") -> dict:
        """Run all checks and persist the summary to the integrity_check_runs table."""
        from .metadata_store.maintenance_store import insert_run

        self.is_running = True
        started_at = time.time()
        summary = {
            "trigger": trigger,
            "started_at": started_at,
            "finished_at": None,
            "status": "ok",
            "error": None,
            "issues": {},
            "repairs": {},
        }
        try:
            results = self.run_all_checks()
            issues = {
                "missing_source_files": results.get("job_active_no_file", 0),
                "generated_image_missing": results.get("derivative_ready_no_file", 0),
                "metadata_mismatch": results.get("asset_done_but_no_metadata", 0),
                "orphaned_work_item": results.get("job_active_no_asset", 0),
                "generated_image_job_mismatch": results.get("derivative_done_not_ready", 0),
            }
            repaired = results.get("job_done_asset_not_done", 0) + results.get("derivative_done_not_ready", 0)
            requeued = results.get("asset_done_but_no_metadata", 0) + results.get("derivative_ready_no_file", 0)
            failed = results.get("job_active_no_asset", 0) + results.get("job_active_no_file", 0)
            total_issues = sum(issues.values())
            unchanged = total_issues - repaired - requeued - failed
            if unchanged < 0:
                unchanged = 0
            repairs = {
                "repaired": repaired,
                "requeued": requeued,
                "failed": failed,
                "unchanged": unchanged,
            }
            summary["finished_at"] = time.time()
            summary["issues"] = issues
            summary["repairs"] = repairs
        except Exception as exc:
            summary["finished_at"] = time.time()
            summary["status"] = "error"
            summary["error"] = str(exc)
            summary["issues"] = {
                "missing_source_files": 0,
                "generated_image_missing": 0,
                "metadata_mismatch": 0,
                "orphaned_work_item": 0,
                "generated_image_job_mismatch": 0,
            }
            summary["repairs"] = {"repaired": 0, "requeued": 0, "failed": 0, "unchanged": 0}
        finally:
            try:
                with _DB_LOCK, _connect() as conn:
                    run_id = insert_run(conn, summary)
                    summary["id"] = run_id
            except Exception as e:
                logger.exception("Failed to persist integrity check run")
                summary["status"] = "error"
                if summary["error"] is None:
                    summary["error"] = str(e)
            finally:
                self.is_running = False
        return summary

    def run_all_checks(self) -> dict[str, int]:
        """Run all six checks and return a dict mapping check name to issue count."""
        total = {}
        with _DB_LOCK, _connect() as conn:
            total["asset_done_but_no_metadata"] = self._check_asset_done_no_metadata(conn)
            total["job_done_asset_not_done"] = self._check_job_done_asset_not_done(conn)
            total["job_active_no_asset"] = self._check_job_active_no_asset(conn)
            total["derivative_ready_no_file"] = self._check_derivative_ready_no_file(conn)
            total["derivative_done_not_ready"] = self._check_derivative_job_done_not_ready(conn)
            total["job_active_no_file"] = self._check_job_active_no_file(conn)
        return total

    def _check_asset_done_no_metadata(self, conn) -> int:
        rows = conn.execute(f"""
            SELECT a.path, a.library_id, a.mtime_ns, a.size
            FROM assets a
            WHERE a.metadata_state = 'done'
              AND NOT EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = a.path
                  AND ({asset_matches_image_metadata_sql()})
                  AND im.size = a.size
              )
        """).fetchall()
        now = time.time()
        for row in rows:
            conn.execute(
                "UPDATE assets SET metadata_state = 'pending' WHERE path = ?",
                (row["path"],),
            )
            conn.execute(
                """
                INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path,
                  root_path, mtime, mtime_ns, size, state, attempts,
                  error, queued_at, finished_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, ?, NULL, ?)
                ON CONFLICT(path) DO UPDATE SET
                  state = CASE
                    WHEN metadata_index_jobs.state = 'running' THEN metadata_index_jobs.state
                    ELSE 'queued'
                  END,
                  updated_at = excluded.updated_at
            """,
                (
                    row["path"],
                    Path(row["path"]).name,
                    str(Path(row["path"]).parent),
                    str(Path(row["path"]).parent),
                    "",
                    0 if row["mtime_ns"] is None else row["mtime_ns"] / 1e9,
                    row["mtime_ns"],
                    row["size"],
                    now,
                    now,
                ),
            )
        return len(rows)

    def _check_job_done_asset_not_done(self, conn) -> int:
        rows = conn.execute(f"""
            SELECT mj.path, mj.mtime_ns, mj.size
            FROM metadata_index_jobs mj
            JOIN assets a ON a.path = mj.path
            WHERE mj.state = 'done'
              AND (a.metadata_state IS NULL OR a.metadata_state NOT IN ('done', 'excluded'))
              AND EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = mj.path
                  AND ({job_matches_image_metadata_sql()})
                  AND im.size = mj.size
              )
        """).fetchall()
        for row in rows:
            if row["mtime_ns"] is not None:
                conn.execute(
                    "UPDATE assets SET metadata_state = 'done' WHERE path = ? AND ABS(mtime_ns - ?) < 1000 AND size = ?",
                    (row["path"], row["mtime_ns"], row["size"]),
                )
            else:
                conn.execute(
                    "UPDATE assets SET metadata_state = 'done' WHERE path = ? AND size = ?",
                    (row["path"], row["size"]),
                )
        return len(rows)

    def _check_job_active_no_asset(self, conn) -> int:
        rows = conn.execute("""
            SELECT mj.path
            FROM metadata_index_jobs mj
            WHERE mj.state IN ('queued', 'running')
              AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.path = mj.path)
        """).fetchall()
        now = time.time()
        for row in rows:
            conn.execute(
                "UPDATE metadata_index_jobs SET state = 'failed', error = ?, finished_at = ?, updated_at = ? WHERE path = ? AND state IN ('queued', 'running')",
                ("no asset row found (integrity check)", now, now, row["path"]),
            )
        return len(rows)

    def _check_derivative_ready_no_file(self, conn) -> int:
        rows = conn.execute("""
            SELECT id, cache_path FROM asset_derivatives
            WHERE status = 'ready'
        """).fetchall()
        requeued = 0
        now = time.time()
        for row in rows:
            if row["cache_path"] is None or not Path(row["cache_path"]).is_file():
                derivative_id = row["id"]
                # Clear stale cache fields on the catalog row
                conn.execute(
                    """
                    UPDATE asset_derivatives
                    SET status = 'queued', cache_path = NULL, byte_size = NULL,
                        last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("integrity: file missing", now, derivative_id),
                )
                # Reuse existing queued/running derivative_jobs row if one exists
                existing = conn.execute(
                    """
                    SELECT id FROM derivative_jobs
                    WHERE derivative_id = ? AND state IN ('queued', 'running')
                    LIMIT 1
                    """,
                    (derivative_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO derivative_jobs (derivative_id, priority, state)
                        VALUES (?, 3, 'queued')
                        """,
                        (derivative_id,),
                    )
                requeued += 1
        return requeued

    def _check_derivative_job_done_not_ready(self, conn) -> int:
        rows = conn.execute("""
            SELECT ad.id, ad.cache_path, dj.id AS job_id
            FROM derivative_jobs dj
            JOIN asset_derivatives ad ON ad.id = dj.derivative_id
            WHERE dj.state = 'done'
              AND ad.status != 'ready'
        """).fetchall()
        now = time.time()
        repaired = 0
        for row in rows:
            if row["cache_path"] is not None and Path(row["cache_path"]).is_file():
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'ready', updated_at = ? WHERE id = ? AND status != 'ready'",
                    (now, row["id"]),
                )
                repaired += 1
            else:
                conn.execute(
                    "UPDATE derivative_jobs SET state = 'failed', error = ?, updated_at = ? WHERE id = ? AND state = 'done'",
                    ("integrity: cache file missing", now, row["job_id"]),
                )
                repaired += 1
        return repaired

    def _check_job_active_no_file(self, conn) -> int:
        rows = conn.execute("""
            SELECT path FROM metadata_index_jobs
            WHERE state IN ('queued', 'running')
        """).fetchall()
        failed = 0
        now = time.time()
        for row in rows:
            if not Path(row["path"]).is_file():
                conn.execute(
                    "UPDATE metadata_index_jobs SET state = 'failed', error = ?, finished_at = ?, updated_at = ? WHERE path = ? AND state IN ('queued', 'running')",
                    ("integrity: file missing from disk", now, now, row["path"]),
                )
                failed += 1
        return failed


integrity_checker = IntegrityChecker()
