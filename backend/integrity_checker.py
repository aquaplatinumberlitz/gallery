"""Periodic background integrity checker for cross-table consistency."""

import logging
import threading
import time
from pathlib import Path

from .config import DERIVATIVE_VARIANTS
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
                "generated_image_abandoned": results.get("derivative_abandoned_jobs", 0),
                "metadata_mismatch": results.get("asset_done_but_no_metadata", 0),
                "orphaned_work_item": results.get("job_active_no_asset", 0),
                "generated_image_job_mismatch": results.get("derivative_done_not_ready", 0),
                "generated_image_expected_row_missing": results.get("derivative_expected_row_missing", 0),
                "generated_image_queued_without_job": results.get("derivative_queued_without_job", 0),
                "generated_image_policy_deferred": results.get("derivative_policy_deferred", 0),
            }
            repaired = (
                results.get("job_done_asset_not_done", 0)
                + results.get("derivative_done_repaired", 0)
                + results.get("derivative_expected_row_missing", 0)
            )
            requeued = (
                results.get("asset_done_but_no_metadata", 0)
                + results.get("derivative_ready_requeued", 0)
                + results.get("derivative_abandoned_requeued", 0)
                + results.get("derivative_queued_without_job_repaired", 0)
                + results.get("derivative_policy_deferred", 0)
            )
            failed = (
                results.get("job_active_no_asset", 0)
                + results.get("job_active_no_file", 0)
                + results.get("derivative_done_failed", 0)
                + results.get("derivative_abandoned_failed", 0)
            )
            skipped = (
                results.get("derivative_ready_skipped", 0)
                + results.get("derivative_abandoned_skipped", 0)
                + results.get("derivative_queued_without_job_skipped", 0)
            )
            recovered = results.get("derivative_abandoned_jobs", 0)
            total_issues = sum(issues.values())
            unchanged = total_issues - repaired - requeued - failed - skipped
            if unchanged < 0:
                unchanged = 0
            repairs = {
                "repaired": repaired,
                "requeued": requeued,
                "failed": failed,
                "skipped": skipped,
                "recovered": recovered,
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
                "generated_image_abandoned": 0,
                "metadata_mismatch": 0,
                "orphaned_work_item": 0,
                "generated_image_job_mismatch": 0,
                "generated_image_expected_row_missing": 0,
                "generated_image_queued_without_job": 0,
                "generated_image_policy_deferred": 0,
            }
            summary["repairs"] = {
                "repaired": 0,
                "requeued": 0,
                "failed": 0,
                "skipped": 0,
                "recovered": 0,
                "unchanged": 0,
            }
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
        """Run all checks and return a dict mapping check name to issue count.

        Keys:
        asset_done_but_no_metadata, job_done_asset_not_done,
        job_active_no_asset, job_active_no_file,
        derivative_ready_no_file, derivative_ready_requeued,
        derivative_ready_skipped, derivative_abandoned_jobs,
        derivative_abandoned_requeued, derivative_abandoned_skipped,
        derivative_abandoned_failed, derivative_done_not_ready,
        derivative_done_repaired, derivative_done_failed.
        """
        total = {}
        # All checks that mutate metadata/catalog rows finish before desired
        # derivative reconciliation starts.  The reconciler opens its own
        # BEGIN IMMEDIATE transaction; calling it while this connection owns
        # pending writes self-deadlocks SQLite.
        with _DB_LOCK, _connect() as conn:
            total["asset_done_but_no_metadata"] = self._check_asset_done_no_metadata(conn)
            total["job_done_asset_not_done"] = self._check_job_done_asset_not_done(conn)
            total["job_active_no_asset"] = self._check_job_active_no_asset(conn)
            derivative_ready = self._check_derivative_ready_no_file_details(conn)
            total["derivative_ready_no_file"] = derivative_ready["requeued"] + derivative_ready["skipped"]
            total["derivative_ready_requeued"] = derivative_ready["requeued"]
            total["derivative_ready_skipped"] = derivative_ready["skipped"]
            abandoned = self._check_abandoned_derivative_jobs(conn)
            total["derivative_abandoned_jobs"] = sum(abandoned.values())
            total["derivative_abandoned_requeued"] = abandoned["requeued"]
            total["derivative_abandoned_skipped"] = abandoned["skipped"]
            total["derivative_abandoned_failed"] = abandoned["failed"]
            result = self._check_derivative_job_done_not_ready(conn)
            total["derivative_done_not_ready"] = result["repaired"] + result["failed"]
            total["derivative_done_repaired"] = result["repaired"]
            total["derivative_done_failed"] = result["failed"]
            total["job_active_no_file"] = self._check_job_active_no_file(conn)
            expected_ids = self._find_expected_row_missing(conn)
            queued_ids = self._find_queued_without_job(conn)
            deferred_ids = self._find_policy_deferred(conn)

        from .derivative_scheduler import scheduler

        expected_summary = (
            scheduler.reconcile_desired_derivatives(asset_ids=expected_ids, reason="integrity")
            if expected_ids
            else None
        )
        queued_repair = scheduler.repair_derivative_consistency(queued_ids) if queued_ids else None
        deferred_summary = (
            scheduler.reconcile_desired_derivatives(asset_ids=deferred_ids, reason="integrity")
            if deferred_ids
            else None
        )
        total["derivative_expected_row_missing"] = len(expected_ids)
        total["derivative_expected_row_created"] = expected_summary.created_derivative_rows if expected_summary else 0
        total["derivative_queued_without_job"] = queued_repair.issues_considered if queued_repair else 0
        total["derivative_queued_without_job_repaired"] = queued_repair.jobs_created if queued_repair else 0
        total["derivative_queued_without_job_active"] = queued_repair.already_active if queued_repair else 0
        total["derivative_queued_without_job_skipped"] = queued_repair.terminal_skipped if queued_repair else 0
        total["derivative_policy_deferred"] = len(deferred_ids)
        total["derivative_policy_deferred_requeued"] = (
            (deferred_summary.created_jobs + deferred_summary.requeued_without_job) if deferred_summary else 0
        )
        return total

    @staticmethod
    def _find_expected_row_missing(conn) -> list[int]:
        """Find assets missing an exact configured kind/variant identity."""
        configured = [
            (kind, str(variant["name"])) for kind, variants in DERIVATIVE_VARIANTS.items() for variant in variants
        ]
        rows = conn.execute(
            """SELECT a.id, a.mtime_ns, a.size FROM assets a
               JOIN libraries l ON l.id = a.library_id
               WHERE l.warm_enabled = 1 AND a.type = 'image'
                 AND a.deleted_at IS NULL AND a.offline = 0
                 AND a.mtime_ns IS NOT NULL AND a.size IS NOT NULL"""
        ).fetchall()
        missing: list[int] = []
        for row in rows:
            present = {
                (d["kind"], d["variant"])
                for d in conn.execute(
                    "SELECT kind, variant FROM asset_derivatives WHERE asset_id = ? AND source_mtime_ns = ? AND source_size = ?",
                    (row["id"], row["mtime_ns"], row["size"]),
                ).fetchall()
            }
            if any(identity not in present for identity in configured):
                missing.append(int(row["id"]))
        return missing

    @staticmethod
    def _find_queued_without_job(conn) -> list[int]:
        return [
            int(row["id"])
            for row in conn.execute(
                """SELECT d.id FROM asset_derivatives d
               JOIN assets a ON a.id = d.asset_id
               WHERE d.status = 'queued' AND a.deleted_at IS NULL AND a.offline = 0
                 AND a.type = 'image' AND NOT EXISTS (
                   SELECT 1 FROM derivative_jobs j WHERE j.derivative_id = d.id
                     AND j.state IN ('queued', 'running'))"""
            ).fetchall()
        ]

    @staticmethod
    def _find_policy_deferred(conn) -> list[int]:
        return [
            int(row["asset_id"])
            for row in conn.execute(
                """SELECT DISTINCT d.asset_id FROM asset_derivatives d
               JOIN assets a ON a.id = d.asset_id
               JOIN libraries l ON l.id = a.library_id
               WHERE d.status IN ('deferred_capacity', 'evicted')
                 AND l.warm_enabled = 1 AND a.deleted_at IS NULL AND a.offline = 0
                 AND a.type = 'image'"""
            ).fetchall()
        ]

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
        """Repair missing ready files and return the number requeued."""
        return self._check_derivative_ready_no_file_details(conn)["requeued"]

    def _check_derivative_ready_no_file_details(self, conn) -> dict[str, int]:
        """Repair missing ready files and return outcome-specific counters."""
        rows = conn.execute("""
            SELECT d.id, d.cache_path, d.source_mtime_ns, d.source_size,
                   a.id AS asset_id, a.path, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
            FROM asset_derivatives d
            LEFT JOIN assets a ON a.id = d.asset_id
            WHERE d.status = 'ready'
        """).fetchall()
        counts = {"requeued": 0, "skipped": 0}
        for row in rows:
            if row["cache_path"] is None or not Path(row["cache_path"]).is_file():
                derivative_id = row["id"]
                result_code = self._derivative_inapplicable_result(row)
                if result_code is not None:
                    message = f"integrity: derivative is no longer applicable ({result_code})"
                    conn.execute(
                        """
                        UPDATE asset_derivatives
                        SET status = 'skipped', cache_path = NULL, byte_size = NULL,
                            last_error = ?, updated_at = julianday('now')
                        WHERE id = ?
                        """,
                        (message, derivative_id),
                    )
                    conn.execute(
                        """
                        UPDATE derivative_jobs
                        SET state = 'skipped', result_code = ?, error = ?,
                            claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                            completed_at = julianday('now'), updated_at = julianday('now')
                        WHERE derivative_id = ? AND state IN ('queued', 'running')
                        """,
                        (result_code, message, derivative_id),
                    )
                    counts["skipped"] += 1
                    continue
                # Clear stale cache fields on the catalog row
                conn.execute(
                    """
                    UPDATE asset_derivatives
                    SET status = 'queued', cache_path = NULL, byte_size = NULL,
                        last_error = ?, updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    ("integrity: file missing", derivative_id),
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
                counts["requeued"] += 1
        return counts

    def _check_abandoned_derivative_jobs(self, conn) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT j.id AS job_id, j.attempts, j.claim_token, d.id AS derivative_id,
                   d.source_mtime_ns, d.source_size, a.id AS asset_id, a.path,
                   a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
            FROM derivative_jobs j
            JOIN asset_derivatives d ON d.id = j.derivative_id
            LEFT JOIN assets a ON a.id = d.asset_id
            WHERE j.state = 'running'
              AND (j.lease_expires_at IS NULL OR j.lease_expires_at <= julianday('now'))
            """
        ).fetchall()
        counts = {"requeued": 0, "skipped": 0, "failed": 0}
        for row in rows:
            result_code = self._derivative_inapplicable_result(row)
            if result_code is not None:
                state = "skipped"
            elif int(row["attempts"]) >= 3:
                state, result_code = "failed", "attempts_exhausted"
            else:
                state = "queued"
            message = f"integrity: recovered abandoned derivative ({result_code or 'retry'})"
            transitioned = conn.execute(
                """
                UPDATE derivative_jobs
                SET state = ?, result_code = ?, error = ?, claimed_by = NULL,
                    claim_token = NULL, lease_expires_at = NULL,
                    started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                    completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                    updated_at = julianday('now')
                WHERE id = ? AND state = 'running' AND claim_token IS ?
                """,
                (state, result_code, message, state, state, row["job_id"], row["claim_token"]),
            )
            if transitioned.rowcount == 1:
                conn.execute(
                    """
                    UPDATE asset_derivatives SET status = ?, last_error = ?,
                        updated_at = julianday('now') WHERE id = ?
                    """,
                    (state, message, row["derivative_id"]),
                )
                counts["requeued" if state == "queued" else state] += 1
        return counts

    @staticmethod
    def _derivative_inapplicable_result(row) -> str | None:
        if row["asset_id"] is None or row["deleted_at"] is not None or row["offline"] or row["type"] != "image":
            return "asset_inactive"
        try:
            stat = Path(row["path"]).stat()
        except OSError:
            return "source_missing"
        if (
            row["mtime_ns"] is None
            or row["size"] is None
            or float(stat.st_mtime_ns) != float(row["source_mtime_ns"])
            or stat.st_size != int(row["source_size"])
            or float(row["mtime_ns"]) != float(row["source_mtime_ns"])
            or int(row["size"]) != int(row["source_size"])
        ):
            return "source_changed"
        return None

    def _check_derivative_job_done_not_ready(self, conn) -> dict[str, int]:
        rows = conn.execute("""
            SELECT ad.id, ad.cache_path, dj.id AS job_id
            FROM derivative_jobs dj
            JOIN asset_derivatives ad ON ad.id = dj.derivative_id
            WHERE dj.state = 'done'
              AND ad.status != 'ready'
        """).fetchall()
        repaired = 0
        failed = 0
        for row in rows:
            if row["cache_path"] is not None and Path(row["cache_path"]).is_file():
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'ready', updated_at = julianday('now') "
                    "WHERE id = ? AND status != 'ready'",
                    (row["id"],),
                )
                repaired += 1
            else:
                conn.execute(
                    "UPDATE derivative_jobs SET state = 'failed', error = ?, result_code = 'internal_error', "
                    "updated_at = julianday('now') WHERE id = ? AND state = 'done'",
                    ("integrity: cache file missing", row["job_id"]),
                )
                failed += 1
        return {"repaired": repaired, "failed": failed}

    def _check_derivative_expected_row_missing(self, conn) -> int:
        """Close absent current derivative rows for warm-library assets via the reconciler.

        This discovers active current images that lack a current derivative row for a
        configured variant (a gap integrity repair from existing rows cannot see) and
        repairs it through the same ``reconcile_desired_derivatives`` entrypoint used by
        scan/startup/periodic producers. Returns the number of derivative rows created.
        """
        from .derivative_scheduler import DerivativeScheduler

        expected_variants = sum(len(variants) for variants in DERIVATIVE_VARIANTS.values())
        created = 0
        libraries = conn.execute("SELECT id FROM libraries WHERE warm_enabled = 1").fetchall()
        for library in libraries:
            rows = conn.execute(
                """
                SELECT a.id FROM assets a
                WHERE a.library_id = ?
                  AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                  AND a.mtime_ns IS NOT NULL AND a.size IS NOT NULL
                  AND (
                    SELECT count(*) FROM asset_derivatives d
                    WHERE d.asset_id = a.id
                      AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
                  ) < ?
                """,
                (int(library["id"]), expected_variants),
            ).fetchall()
            if not rows:
                continue
            asset_ids = [int(row["id"]) for row in rows]
            created += (
                DerivativeScheduler()
                .reconcile_desired_derivatives(asset_ids=asset_ids, reason="integrity")
                .created_derivative_rows
            )
        return created

    def _check_derivative_queued_without_job(self, conn) -> int:
        """Repair ``queued`` derivatives whose latest job is not queued/running."""
        from .derivative_scheduler import scheduler

        derivative_ids = [
            int(row["id"])
            for row in conn.execute(
                """SELECT d.id FROM asset_derivatives d
               JOIN assets a ON a.id = d.asset_id
               WHERE d.status = 'queued'
                 AND a.deleted_at IS NULL AND a.offline = 0 AND a.type = 'image'
                 AND NOT EXISTS (
                   SELECT 1 FROM derivative_jobs j
                   WHERE j.derivative_id = d.id AND j.state IN ('queued', 'running')
                 )"""
            ).fetchall()
        ]
        if not derivative_ids:
            return 0
        return scheduler.repair_derivative_consistency(derivative_ids)

    def _check_derivative_policy_deferred(self, conn) -> int:
        """Reconsider ``deferred_capacity``/``evicted`` current derivatives when capacity allows.

        A quota increase, cache clear, or periodic reconciliation should give deferred
        work another chance; this uses the reconciler so capacity re-evaluation reuses the
        single desired-state code path rather than duplicate SQL.
        """
        from .derivative_scheduler import DerivativeScheduler

        rows = conn.execute(
            """
            SELECT DISTINCT d.asset_id FROM asset_derivatives d
            JOIN assets a ON a.id = d.asset_id
            WHERE d.status IN ('deferred_capacity', 'evicted')
              AND a.deleted_at IS NULL AND a.offline = 0 AND a.type = 'image'
            """
        ).fetchall()
        if not rows:
            return 0
        asset_ids = [int(row["asset_id"]) for row in rows]
        summary = DerivativeScheduler().reconcile_desired_derivatives(asset_ids=asset_ids, reason="integrity")
        return summary.created_jobs + summary.requeued_without_job

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
