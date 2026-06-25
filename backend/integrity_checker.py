"""Periodic background integrity checker for cross-table consistency."""

import logging
import threading
import time
from pathlib import Path

from .metadata_store import _DB_LOCK, _connect

logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Periodic background integrity checker for cross-table consistency."""

    def __init__(self, interval: int = 3600):
        """Initialize with configurable check interval (minimum 60s)."""
        self.interval = max(60, interval)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

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
                results = self.run_all_checks()
                if any(results.values()):
                    logger.info("Integrity check results: %s", results)
            except Exception:
                logger.exception("Integrity checker crashed")

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
        rows = conn.execute("""
            SELECT a.path, a.library_id, a.mtime_ns, a.size
            FROM assets a
            WHERE a.metadata_state = 'done'
              AND NOT EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = a.path
                  AND ABS(im.mtime_ns - COALESCE(a.mtime_ns, 0)) < 1000
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
                  state = CASE WHEN excluded.state = 'queued' AND metadata_index_jobs.state IN ('queued', 'failed')
                    THEN excluded.state ELSE metadata_index_jobs.state END,
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
        rows = conn.execute("""
            SELECT mj.path, mj.mtime_ns, mj.size
            FROM metadata_index_jobs mj
            JOIN assets a ON a.path = mj.path
            WHERE mj.state = 'done'
              AND (a.metadata_state IS NULL OR a.metadata_state NOT IN ('done', 'excluded'))
              AND EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = mj.path
                  AND ((mj.mtime_ns IS NOT NULL AND ABS(im.mtime_ns - mj.mtime_ns) < 1000 AND im.size = mj.size)
                    OR (mj.mtime_ns IS NULL AND im.size = mj.size))
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
              AND cache_path IS NOT NULL
        """).fetchall()
        requeued = 0
        now = time.time()
        for row in rows:
            if not Path(row["cache_path"]).is_file():
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'queued', last_error = ?, updated_at = ? WHERE id = ?",
                    ("integrity: file missing", now, row["id"]),
                )
                requeued += 1
        return requeued

    def _check_derivative_job_done_not_ready(self, conn) -> int:
        rows = conn.execute("""
            SELECT ad.asset_id, ad.kind, ad.variant
            FROM derivative_jobs dj
            JOIN asset_derivatives ad ON ad.id = dj.derivative_id
            WHERE dj.state = 'done'
              AND ad.status != 'ready'
              AND EXISTS (
                SELECT 1 FROM asset_derivatives ad2
                WHERE ad2.asset_id = ad.asset_id AND ad2.kind = ad.kind AND ad2.variant = ad.variant
                  AND ad2.status = 'ready'
                  AND ad2.id >= ad.id
              )
        """).fetchall()
        now = time.time()
        for row in rows:
            conn.execute(
                "UPDATE asset_derivatives SET status = 'ready', updated_at = ? WHERE asset_id = ? AND kind = ? AND variant = ?",
                (now, row["asset_id"], row["kind"], row["variant"]),
            )
        return len(rows)

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
