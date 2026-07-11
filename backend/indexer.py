"""Background metadata indexing queues, workers, and metrics."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .catalog_maintenance_gate import maintenance_producer, producer_gate
from .config import (
    METADATA_INDEXER_ENABLED as METADATA_INDEXER_ENABLED,  # noqa: F401 — monkeypatched by tests
)
from .config import (
    METADATA_INDEXER_WORKER_SLEEP_SECONDS as METADATA_INDEXER_WORKER_SLEEP_SECONDS,  # noqa: F401 — monkeypatched by tests
)
from .metadata_extract import ExtractedMetadata as ExtractedMetadata  # noqa: F401 — monkeypatched by tests
from .metadata_extract import extract_metadata
from .metadata_store import (
    _DB_LOCK,
    MAX_METADATA_JOB_ATTEMPTS,
    MetadataIndexJob,
    _connect,
    _persist_metadata_index_jobs,
    asset_matches_image_metadata_sql,
    claim_next_metadata_job,
    complete_metadata_job,
    fail_metadata_job,
    get_library_for_path,
    index_directory_tree,
    initialize_database,
    job_matches_image_metadata_sql,
    list_recoverable_metadata_jobs,
    mark_metadata_job_stale,
    reconcile_library_assets,
    repair_inconsistent_asset_states,
    repair_legacy_asset_mtime_ns,
    reset_running_jobs_to_queued,
)
from .metadata_store.search_store import _like_escape

try:  # prometheus-fastapi-instrumentator depends on prometheus_client.
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # noqa: BLE001  # pragma: no cover - metrics are optional at import time.
    Counter = Gauge = Histogram = None  # type: ignore[assignment]


router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _metric(factory: Any, name: str, documentation: str, *args: Any, **kwargs: Any) -> Any:
    if factory is None:
        return None
    try:
        return factory(name, documentation, *args, **kwargs)
    except ValueError:
        return None


def _inc(metric: Any, *labels: str, amount: float = 1.0) -> None:
    if metric is None:
        return
    target = metric.labels(*labels) if labels else metric
    target.inc(amount)


def _observe(metric: Any, value: float) -> None:
    if metric is not None:
        metric.observe(value)


def _normalized_path_text(path: str | Path | None) -> str:
    if not path:
        return ""
    return str(Path(path).resolve())


def _is_path_in_scope(path: str | Path | None, scope_root: str | Path | None) -> bool:
    path_text = _normalized_path_text(path)
    root_text = _normalized_path_text(scope_root)
    if not path_text or not root_text:
        return False
    if path_text == root_text:
        return True
    if root_text == os.sep:
        return path_text.startswith(os.sep)
    return path_text.startswith(f"{root_text.rstrip(os.sep)}{os.sep}")


def _metadata_runtime_scope_sql(
    scope_path: str | Path | None,
    column: str = "path",
) -> tuple[str, list[str]]:
    if scope_path is None:
        return "", []

    scope_text = _normalized_path_text(scope_path)
    if not scope_text or scope_text == os.sep:
        return "", []

    prefix = f"{scope_text.rstrip(os.sep)}{os.sep}"
    return f" AND ({column} = ? OR {column} LIKE ? ESCAPE '\\')", [scope_text, f"{_like_escape(prefix)}%"]


def get_indexer_runtime_status(scope_path: str | Path | None = None) -> dict[str, Any]:
    """Return runtime status from the SQLite metadata queue and worker pool."""
    initialize_database()
    scope_sql, scope_params = _metadata_runtime_scope_sql(scope_path)
    with _DB_LOCK, _connect() as conn:
        queued_count = int(
            conn.execute(
                f"SELECT count(*) FROM metadata_index_jobs WHERE state = 'queued'{scope_sql}",
                scope_params,
            ).fetchone()[0]
        )
        running_count = int(
            conn.execute(
                f"SELECT count(*) FROM metadata_index_jobs WHERE state = 'running'{scope_sql}",
                scope_params,
            ).fetchone()[0]
        )
        queued_rows = conn.execute(
            f"""
            SELECT path, priority, attempts, queued_at, updated_at, library_id
            FROM metadata_index_jobs
            WHERE state = 'queued'{scope_sql}
            ORDER BY priority ASC, queued_at ASC, updated_at ASC
            LIMIT 50
            """,
            scope_params,
        ).fetchall()
        running_rows = conn.execute(
            f"""
            SELECT path, started_at, attempts, updated_at, library_id
            FROM metadata_index_jobs
            WHERE state = 'running'{scope_sql}
            ORDER BY started_at ASC, updated_at ASC
            LIMIT 50
            """,
            scope_params,
        ).fetchall()

    return {
        "worker_count": metadata_worker.alive_worker_count(),
        "active_jobs": running_count,
        "runtime_queue_depth": queued_count,
        "coalesced_duplicates": 0,
        "active_job_paths": {
            str(row["path"]): {
                "started_at": row["started_at"],
                "attempts": int(row["attempts"] or 0),
                "updated_at": row["updated_at"],
                "library_id": row["library_id"],
            }
            for row in running_rows
        },
        "queued_jobs": [
            {
                "path": row["path"],
                "priority": int(row["priority"] or 3),
                "attempts": int(row["attempts"] or 0),
                "queued_at": row["queued_at"],
                "updated_at": row["updated_at"],
                "library_id": row["library_id"],
            }
            for row in queued_rows
        ],
        "staged_path_queue_depth": 0,
        "staged_path_coalesced": 0,
        "staged_path_failed": 0,
        "staged_path_flushes_forced": 0,
        "staged_path_worker_count": 0,
        "active_scan_requests": 0,
        "active_scan_roots": {},
        "staged_paths": [],
        "active_rebuild_roots": {},
        "deprecated": False,
    }


def rebuild_index_scope(root: str | Path) -> dict[str, Any]:
    """Rebuild non-destructively for files: recreate DB index rows for a scoped root."""
    root_path = Path(root).resolve()
    image_paths: list[Path] = []
    asset_paths: set[str] = set()
    indexed = index_directory_tree(
        root_path,
        include_metadata=False,
        collected_image_paths=image_paths,
        collected_asset_paths=asset_paths,
    )
    library = get_library_for_path(root_path)
    reconciled = 0
    if library is not None:
        reconciled = reconcile_library_assets(int(library["id"]), asset_paths, scope_path=root_path)

    metadata = dispatch_metadata_index_paths(image_paths, root_path)

    return {
        "path": str(root_path),
        "indexed": indexed,
        "reconciled": reconciled,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# DB-claim metadata worker (Phase 1)
# ---------------------------------------------------------------------------


@maintenance_producer
def dispatch_metadata_index_paths(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    priority: int = 3,
) -> dict[str, int]:
    """Persist/coalesce metadata_index_jobs in SQLite and wake the DB-claim worker.

    This is the single scheduling entrypoint for all metadata work. It does
    NOT push jobs into the in-memory ``_job_queue``; the DB-claim worker
    claims directly from SQLite.

    Phase 2 replaces all direct calls to ``queue_metadata_index_paths`` +
    ``_enqueue_metadata_jobs_from_result`` with this unified entrypoint.
    """
    result = _persist_metadata_index_jobs(list(paths), root_path, priority=priority)
    metadata_worker.wake()
    return {
        "queued": len(result.enqueued),
        "coalesced": result.coalesced,
        "skipped": result.skipped,
        "failed": result.failed,
    }


class MetadataLifecycleWorker:
    """DB-claim metadata worker, modeled on ``DerivativeScheduler``.

    Claims queued metadata jobs from SQLite, processes them, and materializes
    completion state. The worker does NOT use an in-memory ``_job_queue`` as
    the source of work — it claims directly from ``metadata_index_jobs``.
    """

    _logger = logging.getLogger("gallery.metadata")

    def __init__(self, worker_count: int = 1):
        """Initialize metadata worker thread pool."""
        self.worker_count = max(1, min(worker_count, 4))
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lifecycle_lock = threading.RLock()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start DB-claim metadata worker threads. Recovery deferred to Phase 4."""
        with self._lifecycle_lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            self._stop_event.clear()
            self._threads = [
                threading.Thread(
                    target=self._worker_loop,
                    name=f"gallery-metadata-worker-{i + 1}",
                    daemon=True,
                )
                for i in range(self.worker_count)
            ]
            for thread in self._threads:
                thread.start()
            self._wake_event.set()

    def stop(self) -> None:
        """Stop workers and wait briefly for in-flight work to finish."""
        with self._lifecycle_lock:
            threads = self._threads
            self._stop_event.set()
            self._wake_event.set()
        deadline = time.monotonic() + 1
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._lifecycle_lock:
            self._threads = [t for t in threads if t.is_alive()]

    def is_running(self) -> bool:
        """Return whether at least one configured worker is alive."""
        return self.alive_worker_count() > 0

    def alive_worker_count(self) -> int:
        """Return the number of metadata worker threads currently alive."""
        with self._lifecycle_lock:
            return sum(1 for thread in self._threads if thread.is_alive())

    def wake(self) -> None:
        """Wake workers to check for new queued jobs."""
        self._wake_event.set()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with producer_gate():
                    job = self._claim_job()
                    if job is not None:
                        self._run_job(job)
            except Exception:  # noqa: BLE001
                self._logger.exception("DB-claim worker could not read the job queue")
                self._stop_event.wait(0.5)
                continue
            if job is None:
                self._wake_event.clear()
                self._wake_event.wait(timeout=1)
                continue

    def _claim_job(self) -> MetadataIndexJob | None:
        """Claim one queued metadata job from SQLite.

        Mirrors ``DerivativeScheduler._claim_job`` (derivative_scheduler.py:392-420).
        """
        return claim_next_metadata_job()

    def _run_job(self, job: MetadataIndexJob) -> None:
        """Extract metadata and complete the job in short transactions."""
        from .metadata_store import _DB_LOCK, _connect

        try:
            if not self._is_job_current(job):
                with _DB_LOCK, _connect() as conn:
                    mark_metadata_job_stale(conn, job)
                return

            metadata = extract_metadata(Path(job.path))

            if not self._is_job_current(job):
                with _DB_LOCK, _connect() as conn:
                    mark_metadata_job_stale(conn, job)
                return

            # Write image_metadata in its own short transaction
            from .metadata_store import upsert_metadata_batch as _upbatch

            _upbatch([metadata])

            # Complete job + materialize asset state in another short transaction
            with _DB_LOCK, _connect() as conn:
                complete_metadata_job(conn, job)
                asset = conn.execute(
                    "SELECT id FROM assets WHERE path = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                    (job.path,),
                ).fetchone()
            if asset is not None:
                from .derivative_scheduler import scheduler

                try:
                    scheduler.reconcile_desired_derivatives(
                        asset_ids=[int(asset["id"])],
                        reason="metadata_completion",
                    )
                except Exception:  # noqa: BLE001
                    # Metadata completion is durable and must not be rewritten
                    # as failed because the derivative safety net is unavailable.
                    self._logger.exception(
                        "Derivative safety-net reconciliation failed after metadata completion for %s",
                        job.path,
                    )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Metadata job %s failed: %s", job.path, exc)
            try:
                with _DB_LOCK, _connect() as conn:
                    fail_metadata_job(conn, job, str(exc))
            except Exception:  # noqa: BLE001
                self._logger.exception("Could not mark job %s as failed", job.path)

    @staticmethod
    def _is_job_current(job: MetadataIndexJob) -> bool:
        """Return whether the file on disk still matches the job's identity.

        Primary check uses st_mtime_ns (nanoseconds). Falls back to
        st_mtime (seconds) for legacy jobs without mtime_ns.
        """
        try:
            stat = Path(job.path).stat()
        except OSError:
            return False
        if job.mtime_ns is not None:
            return stat.st_mtime_ns == job.mtime_ns and stat.st_size == job.size
        return stat.st_mtime == job.mtime and stat.st_size == job.size


# Singleton instance
metadata_worker = MetadataLifecycleWorker()


def recover_metadata_index_jobs() -> dict[str, int]:
    """Recover interrupted metadata jobs from SQLite.

    Recovery does NOT mean "re-dispatch DB jobs into memory queue." It means
    "make SQLite job state claimable and consistent."

    Mirrors DerivativeScheduler.start() recovery pattern.

    Running jobs with attempts >= MAX_METADATA_JOB_ATTEMPTS become failed.
    Remaining running jobs are reset to queued.

    Returns:
        dict with counters: running_reset, running_failed_exhausted,
        done_repaired, done_demoted, done_skipped, total
    """
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        running_jobs = list_recoverable_metadata_jobs(conn, ("running",), limit=0)
        now = time.time()
        exhausted_paths: list[tuple[str, float, int, int | None]] = []
        reset_paths: list[tuple[str, float, int, int | None]] = []
        for j in running_jobs:
            attempts = int(j["attempts"] or 0)
            path = j["path"]
            mtime_ns = j["mtime_ns"]
            mtime = j["mtime"]
            size = j["size"]
            if attempts >= MAX_METADATA_JOB_ATTEMPTS:
                if mtime_ns is not None:
                    conn.execute(
                        """
                        UPDATE metadata_index_jobs
                        SET state='failed', error=?, finished_at=?, updated_at=?
                        WHERE path=? AND mtime_ns = ? AND size=? AND state='running'
                        """,
                        ("exhausted recovery attempts", now, now, path, mtime_ns, size),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE metadata_index_jobs
                        SET state='failed', error=?, finished_at=?, updated_at=?
                        WHERE path=? AND mtime=? AND size=? AND state='running'
                        """,
                        ("exhausted recovery attempts", now, now, path, mtime, size),
                    )
                exhausted_paths.append((path, mtime, size, mtime_ns))
            else:
                reset_paths.append((path, mtime, size, mtime_ns))
        reset_running_jobs_to_queued(conn, reset_paths)
        mtime_repair_result = repair_legacy_asset_mtime_ns(conn)
        repair_result = repair_inconsistent_asset_states(conn)

    metadata_worker.wake()

    return {
        "running_reset": len(reset_paths),
        "running_failed_exhausted": len(exhausted_paths),
        "done_repaired": repair_result["repaired"],
        "done_demoted": repair_result["demoted"],
        "done_skipped": repair_result["skipped"],
        "stale_repaired": repair_result["stale_repaired"],
        "mtime_repaired_file_index": mtime_repair_result["file_index"],
        "mtime_repaired_filesystem": mtime_repair_result["filesystem"],
        "mtime_repair_skipped": mtime_repair_result["skipped"],
        "total": len(reset_paths)
        + len(exhausted_paths)
        + repair_result["repaired"]
        + repair_result["demoted"]
        + repair_result["skipped"]
        + mtime_repair_result["file_index"]
        + mtime_repair_result["filesystem"],
    }


def get_metadata_lifecycle_status(scope_path: str | Path | None = None) -> dict[str, Any]:
    """Return metadata lifecycle diagnostics counters from §5.7 of the plan.

    Provides 15 counters covering job queue depth, inconsistency detection,
    worker health, and throughput.
    """
    initialize_database()
    now = time.time()
    result: dict[str, Any] = {}

    mj_scope, scope_params = _metadata_runtime_scope_sql(scope_path, "mj.path")
    a_scope, _asset_scope_params = _metadata_runtime_scope_sql(scope_path, "a.path")

    with _DB_LOCK, _connect() as conn:
        # Job state counts
        for state in ("queued", "running", "done", "stale", "failed", "skipped"):
            row = conn.execute(
                f"SELECT count(*) AS cnt FROM metadata_index_jobs mj WHERE mj.state = ? {mj_scope}",
                [state, *scope_params],
            ).fetchone()
            result[f"{state}_metadata_jobs"] = int(row["cnt"])

        # oldest_queued_metadata_job_age
        row = conn.execute(
            f"SELECT min(mj.queued_at) AS oldest FROM metadata_index_jobs mj WHERE mj.state = 'queued' {mj_scope}",
            scope_params,
        ).fetchone()
        oldest = row["oldest"]
        result["oldest_queued_metadata_job_age"] = round(now - oldest, 3) if oldest else None

        # done_jobs_with_pending_assets: done job whose asset is NOT done
        row = conn.execute(
            f"""
            SELECT count(*) AS cnt FROM metadata_index_jobs mj
            LEFT JOIN assets a ON a.path = mj.path
            WHERE mj.state = 'done'
              AND (a.path IS NULL OR a.metadata_state IS NULL OR a.metadata_state != 'done')
              {mj_scope}
            """,
            scope_params,
        ).fetchone()
        result["done_jobs_with_pending_assets"] = int(row["cnt"])

        # current_image_metadata_with_pending_assets: image_metadata current for path
        # but asset not done.  Mirrors _image_metadata_exists_for_job matching.
        row = conn.execute(
            f"""
            SELECT count(*) AS cnt FROM image_metadata im
            JOIN assets a ON a.path = im.path
            WHERE (a.metadata_state IS NULL OR a.metadata_state != 'done')
              AND ({asset_matches_image_metadata_sql()}) AND im.size = a.size
              {a_scope}
            """,
            scope_params,
        ).fetchone()
        result["current_image_metadata_with_pending_assets"] = int(row["cnt"])

        # metadata_jobs_without_matching_assets
        row = conn.execute(
            f"""
            SELECT count(*) AS cnt FROM metadata_index_jobs mj
            LEFT JOIN assets a ON a.path = mj.path
            WHERE a.path IS NULL
              {mj_scope}
            """,
            scope_params,
        ).fetchone()
        result["metadata_jobs_without_matching_assets"] = int(row["cnt"])

        # assets_done_but_metadata_missing_or_stale
        row = conn.execute(
            f"""
            SELECT count(*) AS cnt FROM assets a
            WHERE a.metadata_state = 'done'
              AND NOT EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = a.path AND im.size = a.size
                  AND ({asset_matches_image_metadata_sql()})
              )
              {a_scope}
            """,
            scope_params,
        ).fetchone()
        result["assets_done_but_metadata_missing_or_stale"] = int(row["cnt"])

        # repairable_metadata_assets: done job + current metadata + pending asset
        # Matching mirrors _image_metadata_exists_for_job: modern job can match legacy metadata.
        row = conn.execute(
            f"""
            SELECT count(*) AS cnt FROM metadata_index_jobs mj
            JOIN assets a ON a.path = mj.path
            WHERE mj.state = 'done'
              AND (a.metadata_state IS NULL OR a.metadata_state != 'done')
              AND EXISTS (
                SELECT 1 FROM image_metadata im
                WHERE im.path = mj.path AND im.size = mj.size
                  AND ({job_matches_image_metadata_sql()})
              )
              {mj_scope}
            """,
            scope_params,
        ).fetchone()
        result["repairable_metadata_assets"] = int(row["cnt"])

        # metadata_worker_last_claimed_at
        row = conn.execute(
            f"SELECT max(mj.started_at) AS last FROM metadata_index_jobs mj WHERE mj.state IN ('running', 'done') {mj_scope}",
            scope_params,
        ).fetchone()
        result["metadata_worker_last_claimed_at"] = row["last"]

        # metadata_worker_last_completed_at
        row = conn.execute(
            f"SELECT max(mj.finished_at) AS last FROM metadata_index_jobs mj WHERE mj.state IN ('done', 'failed', 'stale', 'skipped') {mj_scope}",
            scope_params,
        ).fetchone()
        result["metadata_worker_last_completed_at"] = row["last"]

    # metadata_worker_alive (runtime check, not DB)
    result["metadata_worker_alive"] = metadata_worker.is_running()

    return result
