"""Durable priority scheduler for image derivative generation."""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import UnidentifiedImageError

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "backend"

from .config import DERIVATIVE_QUOTA_BYTES, DERIVATIVE_VARIANTS, DERIVATIVE_WORKER_COUNT, THUMBNAIL_CACHE_DIR
from .errors import APIError
from .metadata_store import _connect, initialize_database

logger = logging.getLogger(__name__)
_LEASE_DAYS = 15 / (24 * 60)
_SUPERVISOR_INTERVAL_SECONDS = 30
_MAX_ATTEMPTS = 3


def _ensure_database() -> None:
    """Initialize only when the derivative schema is not already present."""
    try:
        with _connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'derivative_jobs'"
            ).fetchone()
        if version >= 5 and table is not None:
            return
    except sqlite3.Error:
        pass
    initialize_database()


def derivative_variant(kind: str, max_long_edge: int, quality: int, format: str) -> str:
    """Return a stable variant name for derivative rendering settings."""
    for variant in DERIVATIVE_VARIANTS.get(kind, []):
        if format == "webp" and variant["max_long_edge"] == max_long_edge and variant["quality"] == quality:
            return str(variant["name"])
    return f"edge-{max_long_edge}-q-{quality}-{format}"


class DerivativeScheduler:
    """Run durable, coalesced derivative jobs using priority worker threads."""

    def __init__(self, worker_count: int = DERIVATIVE_WORKER_COUNT, quota_bytes: int = DERIVATIVE_QUOTA_BYTES):
        """Configure worker concurrency and the persisted-file quota."""
        self.worker_count = max(1, min(worker_count, 8))
        self.quota_bytes = max(0, quota_bytes)
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._file_lock = threading.RLock()
        self._generating_paths: set[str] = set()
        self._served_paths: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._supervisor_thread: threading.Thread | None = None
        self._instance_id = uuid.uuid4().hex

    def start(self) -> None:
        """Start workers and recover jobs interrupted by a prior process."""
        with self._lifecycle_lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            _ensure_database()
            self._recover_running_jobs()
            self._stop_event.clear()
            self._threads = [self._new_worker(index + 1) for index in range(self.worker_count)]
            for thread in self._threads:
                thread.start()
            self._supervisor_thread = threading.Thread(
                target=self._supervisor_loop,
                name="derivative-supervisor",
                daemon=True,
            )
            self._supervisor_thread.start()
            self._wake_event.set()

    def stop(self) -> None:
        """Stop workers and wait briefly for in-flight generation to finish."""
        with self._lifecycle_lock:
            threads = self._threads
            supervisor = self._supervisor_thread
            self._stop_event.set()
            self._wake_event.set()
        deadline = time.monotonic() + 1
        for thread in threads:
            with suppress(RuntimeError):
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if supervisor is not None:
            with suppress(RuntimeError):
                supervisor.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._lifecycle_lock:
            self._threads = [thread for thread in threads if thread.is_alive()]
            self._supervisor_thread = supervisor if supervisor is not None and supervisor.is_alive() else None

    def is_running(self) -> bool:
        """Return whether at least one configured worker is alive."""
        with self._lifecycle_lock:
            return any(thread.is_alive() for thread in self._threads)

    def alive_worker_count(self) -> int:
        """Return the current number of alive derivative workers."""
        with self._lifecycle_lock:
            return sum(thread.is_alive() for thread in self._threads)

    def _worker_id(self, slot: int) -> str:
        return f"{self._instance_id}:derivative-worker-{slot}"

    def _new_worker(self, slot: int) -> threading.Thread:
        worker_id = self._worker_id(slot)
        return threading.Thread(
            target=self._worker_loop,
            args=(worker_id,),
            name=f"derivative-worker-{slot}",
            daemon=True,
        )

    def schedule_derivative(
        self,
        asset_id: int,
        kind: str,
        variant: str,
        priority: int = 3,
        *,
        max_long_edge: int | None = None,
        quality: int | None = None,
        format: str = "webp",
    ) -> int:
        """Create or coalesce a derivative job and return its catalog ID."""
        if kind not in DERIVATIVE_VARIANTS:
            raise ValueError(f"Unsupported derivative kind: {kind}")
        priority = max(0, min(priority, 3))
        default_variant = DERIVATIVE_VARIANTS[kind][0]
        max_long_edge = max_long_edge or int(default_variant["max_long_edge"])
        quality = quality or int(default_variant["quality"])
        format = format or "webp"
        _ensure_database()
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            asset = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            source = Path(asset["path"])
            stat = source.stat()
            source_mtime_ns = float(stat.st_mtime_ns)
            conn.execute(
                """
                INSERT INTO asset_derivatives (
                  asset_id, kind, variant, source_mtime_ns, source_size, format,
                  quality, max_long_edge, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
                ON CONFLICT(asset_id, kind, variant, source_mtime_ns, source_size) DO NOTHING
                """,
                (asset_id, kind, variant, source_mtime_ns, stat.st_size, format, quality, max_long_edge),
            )
            derivative = conn.execute(
                """
                SELECT id, status, cache_path FROM asset_derivatives
                WHERE asset_id = ? AND kind = ? AND variant = ?
                  AND source_mtime_ns = ? AND source_size = ?
                """,
                (asset_id, kind, variant, source_mtime_ns, stat.st_size),
            ).fetchone()
            derivative_id = int(derivative["id"])
            if (
                derivative["status"] == "ready"
                and derivative["cache_path"]
                and Path(derivative["cache_path"]).is_file()
            ):
                return derivative_id
            job = conn.execute(
                """
                SELECT id, priority FROM derivative_jobs
                WHERE derivative_id = ? AND state IN ('queued', 'running')
                ORDER BY id DESC LIMIT 1
                """,
                (derivative_id,),
            ).fetchone()
            if job is not None:
                if priority < int(job["priority"]):
                    conn.execute(
                        "UPDATE derivative_jobs SET priority = ?, updated_at = julianday('now') WHERE id = ?",
                        (priority, job["id"]),
                    )
                self._wake_event.set()
                return derivative_id
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, ?, 'queued')",
                (derivative_id, priority),
            )
            conn.execute(
                "UPDATE asset_derivatives SET status = 'queued', last_error = NULL, updated_at = julianday('now') "
                "WHERE id = ?",
                (derivative_id,),
            )
        self._wake_event.set()
        return derivative_id

    def get_derivative_status(self, asset_id: int, kind: str, variant: str) -> str | None:
        """Return the current derivative state for the latest source version."""
        _ensure_database()
        with _connect() as conn:
            asset = conn.execute("SELECT path FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if asset is None:
                return None
            try:
                stat = Path(asset["path"]).stat()
            except OSError:
                return None
            row = conn.execute(
                """
                SELECT status FROM asset_derivatives
                WHERE asset_id = ? AND kind = ? AND variant = ?
                  AND source_mtime_ns = ? AND source_size = ?
                ORDER BY id DESC LIMIT 1
                """,
                (asset_id, kind, variant, float(stat.st_mtime_ns), stat.st_size),
            ).fetchone()
        if row is None:
            return None
        return "generating" if row["status"] == "running" else str(row["status"])

    def get_ready_derivative(self, asset_id: int, kind: str, variant: str) -> dict[str, Any] | None:
        """Return and touch a ready derivative for the current source version."""
        _ensure_database()
        with _connect() as conn:
            asset = conn.execute("SELECT path FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if asset is None:
                return None
            try:
                stat = Path(asset["path"]).stat()
            except OSError:
                return None
            row = conn.execute(
                """
                SELECT * FROM asset_derivatives
                WHERE asset_id = ? AND kind = ? AND variant = ? AND source_mtime_ns = ?
                  AND source_size = ? AND status = 'ready'
                ORDER BY id DESC LIMIT 1
                """,
                (asset_id, kind, variant, float(stat.st_mtime_ns), stat.st_size),
            ).fetchone()
            if row is None or not row["cache_path"] or not Path(row["cache_path"]).is_file():
                return None
            conn.execute(
                "UPDATE asset_derivatives SET last_accessed_at = julianday('now') WHERE id = ?",
                (row["id"],),
            )
            return dict(row)

    def find_asset_id(self, path: Path) -> int | None:
        """Resolve a source path to its active asset ID."""
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                "SELECT id FROM assets WHERE path = ? AND type = 'image' "
                "AND deleted_at IS NULL AND offline = 0 ORDER BY id LIMIT 1",
                (str(path.resolve()),),
            ).fetchone()
        return int(row["id"]) if row else None

    def get_asset_path(self, asset_id: int) -> Path | None:
        """Return the active source path for an asset ID."""
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
        return Path(row["path"]) if row else None

    def acquire_serving(self, cache_path: str) -> None:
        """Protect a derivative file while a response is streaming it."""
        with self._file_lock:
            self._served_paths.add(cache_path)

    def release_serving(self, cache_path: str) -> None:
        """Release a derivative file after a response completes."""
        with self._file_lock:
            self._served_paths.discard(cache_path)

    def warm_library(self, library_id: int, kind: str | None = None) -> dict[str, int | str | None]:
        """Schedule default derivative variants for a library.

        When ``kind`` is provided, only variants for that derivative kind are queued.
        """
        if kind is not None and kind not in DERIVATIVE_VARIANTS:
            raise ValueError(f"Unsupported derivative kind: {kind}")
        selected_variants = {kind: DERIVATIVE_VARIANTS[kind]} if kind is not None else DERIVATIVE_VARIANTS
        _ensure_database()
        with _connect() as conn:
            assets = conn.execute(
                """
                SELECT id FROM assets WHERE library_id = ? AND type = 'image'
                  AND deleted_at IS NULL AND offline = 0 ORDER BY id
                """,
                (library_id,),
            ).fetchall()
        scheduled = 0
        for asset in assets:
            for derivative_kind, variants in selected_variants.items():
                for variant in variants:
                    try:
                        self.schedule_derivative(
                            int(asset["id"]),
                            derivative_kind,
                            str(variant["name"]),
                            priority=3,
                            max_long_edge=int(variant["max_long_edge"]),
                            quality=int(variant["quality"]),
                        )
                        scheduled += 1
                    except OSError:
                        continue
        result: dict[str, int | str] = {"assets": len(assets), "derivatives_considered": scheduled}
        if kind is not None:
            result["kind"] = kind
        return result

    def library_status(self, library_id: int) -> dict[str, Any]:
        """Return warm coverage and quota utilization for one library."""
        _ensure_database()
        configured_variants = [
            (kind, str(variant["name"])) for kind, variants in DERIVATIVE_VARIANTS.items() for variant in variants
        ]
        by_kind: dict[str, dict[str, int]] = {
            kind: {"ready_derivatives": 0, "expected_derivatives": 0} for kind in DERIVATIVE_VARIANTS
        }
        expected_derivatives_per_asset = len(configured_variants)
        with _connect() as conn:
            if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
                raise KeyError(library_id)
            total_assets = int(
                conn.execute(
                    """
                    SELECT count(*) FROM assets
                    WHERE library_id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0
                    """,
                    (library_id,),
                ).fetchone()[0]
            )
            if configured_variants:
                variant_filter = " OR ".join("(d.kind = ? AND d.variant = ?)" for _ in configured_variants)
                variant_params = [value for pair in configured_variants for value in pair]
                ready_rows = conn.execute(
                    f"""
                    SELECT d.kind, d.cache_path, d.byte_size
                    FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
                    WHERE a.library_id = ? AND a.deleted_at IS NULL AND a.offline = 0
                      AND d.status = 'ready'
                      AND d.source_mtime_ns = a.mtime_ns
                      AND d.source_size = a.size
                      AND d.cache_path IS NOT NULL
                      AND ({variant_filter})
                    """,
                    (library_id, *variant_params),
                ).fetchall()
            else:
                ready_rows = []
            ready = 0
            used = 0
            for kind, variants in DERIVATIVE_VARIANTS.items():
                by_kind[kind]["expected_derivatives"] = total_assets * len(variants)
            for row in ready_rows:
                if Path(row["cache_path"]).is_file():
                    ready += 1
                    used += row["byte_size"] or 0
                    if row["kind"] in by_kind:
                        by_kind[str(row["kind"])]["ready_derivatives"] += 1
            job_counts = {"queued": 0, "running": 0, "failed": 0, "skipped": 0}
            oldest_running_age_seconds: float | None = None
            if configured_variants:
                lifecycle_rows = conn.execute(
                    f"""
                    SELECT j.state, count(*) AS count,
                           max(CASE WHEN j.state = 'running'
                               THEN (julianday('now') - j.started_at) * 86400 END) AS oldest_age
                    FROM derivative_jobs j
                    JOIN asset_derivatives d ON d.id = j.derivative_id
                    JOIN assets a ON a.id = d.asset_id
                    WHERE a.library_id = ? AND a.type = 'image'
                      AND a.deleted_at IS NULL AND a.offline = 0
                      AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
                      AND ({variant_filter})
                    GROUP BY j.state
                    """,
                    (library_id, *variant_params),
                ).fetchall()
                for row in lifecycle_rows:
                    state = str(row["state"])
                    if state in job_counts:
                        job_counts[state] = int(row["count"])
                    if state == "running" and row["oldest_age"] is not None:
                        oldest_running_age_seconds = max(0.0, float(row["oldest_age"]))
            alive_workers = self.alive_worker_count()
        return {
            "library_id": library_id,
            "total_assets": total_assets,
            "ready_derivatives": ready,
            "expected_derivatives": total_assets * expected_derivatives_per_asset,
            "by_kind": by_kind,
            "quota_bytes": self.quota_bytes,
            "quota_used_bytes": used,
            "quota_utilization": used / self.quota_bytes if self.quota_bytes else 0.0,
            "queued_jobs": job_counts["queued"],
            "running_jobs": job_counts["running"],
            "failed_jobs": job_counts["failed"],
            "skipped_jobs": job_counts["skipped"],
            "configured_worker_count": self.worker_count,
            "alive_worker_count": alive_workers,
            "worker_healthy": alive_workers > 0,
            "oldest_running_age_seconds": oldest_running_age_seconds,
        }

    def rebuild_stale(self) -> int:
        """Queue replacement work for ready derivatives whose source changed."""
        _ensure_database()
        stale: list[sqlite3.Row] = []
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, a.path FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
                WHERE d.status = 'ready' AND a.deleted_at IS NULL
                """
            ).fetchall()
            for row in rows:
                try:
                    stat = Path(row["path"]).stat()
                except OSError:
                    continue
                if float(stat.st_mtime_ns) != row["source_mtime_ns"] or stat.st_size != row["source_size"]:
                    stale.append(row)
                    conn.execute(
                        "UPDATE asset_derivatives SET status = 'queued', updated_at = julianday('now') WHERE id = ?",
                        (row["id"],),
                    )
        for row in stale:
            self.schedule_derivative(
                int(row["asset_id"]),
                str(row["kind"]),
                str(row["variant"]),
                priority=3,
                max_long_edge=int(row["max_long_edge"]),
                quality=int(row["quality"]),
                format=str(row["format"]),
            )
        return len(stale)

    def clear_all(self) -> dict[str, int]:
        """Clear derivative jobs/catalog rows and delete unserved cache files."""
        _ensure_database()
        from .thumbnails import clear_thumbnail_disk_cache

        with _connect() as conn:
            paths = [
                row[0] for row in conn.execute("SELECT cache_path FROM asset_derivatives WHERE cache_path IS NOT NULL")
            ]
            catalog_entries = int(conn.execute("SELECT count(*) FROM asset_derivatives").fetchone()[0])
            jobs = int(conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0])
            conn.execute("DELETE FROM derivative_jobs")
            conn.execute("DELETE FROM asset_derivatives")
        files_dir = THUMBNAIL_CACHE_DIR / "files"
        paths.extend(str(path) for path in files_dir.iterdir() if path.is_file()) if files_dir.is_dir() else None
        poster_dir = THUMBNAIL_CACHE_DIR / "video_posters"
        paths.extend(str(path) for path in poster_dir.iterdir() if path.is_file()) if poster_dir.is_dir() else None
        paths = list(dict.fromkeys(paths))
        deleted = 0
        with self._file_lock:
            protected = self._served_paths | self._generating_paths
            for path in paths:
                if path in protected:
                    continue
                with suppress(OSError):
                    Path(path).unlink()
                    deleted += 1
        disk_entries = clear_thumbnail_disk_cache()
        return {
            "catalog_entries_cleared": catalog_entries,
            "jobs_cleared": jobs,
            "files_deleted": deleted,
            "disk_entries_cleared": disk_entries,
        }

    def _claim_job(self, worker_id: str | None = None) -> sqlite3.Row | None:
        _ensure_database()
        worker_id = worker_id or f"{self._instance_id}:{threading.current_thread().name}"
        self._reconcile_queued_jobs()
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.*, a.path AS source_path
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                  AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                  AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
                ORDER BY j.priority ASC, j.created_at ASC, j.id ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["job_attempts"]) + 1
            claim_token = uuid.uuid4().hex
            conn.execute(
                """
                UPDATE derivative_jobs SET state = 'running', attempts = ?, started_at = julianday('now'),
                  completed_at = NULL, error = NULL, result_code = NULL, claimed_by = ?,
                  claim_token = ?, lease_expires_at = julianday('now') + ?,
                  updated_at = julianday('now') WHERE id = ? AND state = 'queued'
                """,
                (attempts, worker_id, claim_token, _LEASE_DAYS, row["job_id"]),
            )
            conn.execute(
                "UPDATE asset_derivatives SET status = 'running', attempts = ?, updated_at = julianday('now') WHERE id = ?",
                (attempts, row["id"]),
            )
            return conn.execute(
                """
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.*, a.path AS source_path,
                       j.claimed_by, j.claim_token, j.lease_expires_at
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                JOIN assets a ON a.id = d.asset_id
                WHERE j.id = ? AND j.claim_token = ?
                """,
                (row["job_id"], claim_token),
            ).fetchone()

    def _worker_loop(self, worker_id: str | None = None) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._claim_job(worker_id)
            except Exception:  # noqa: BLE001
                logger.exception("Derivative worker could not claim a job")
                self._stop_event.wait(0.5)
                continue
            if job is None:
                self._wake_event.clear()
                self._wake_event.wait(timeout=1)
                continue
            try:
                self._run_job(job)
            except Exception:  # noqa: BLE001
                # _run_job owns normal handler failures. This final boundary
                # protects worker availability if failure persistence itself
                # raises; startup/lease recovery repairs the abandoned claim.
                logger.exception("Unexpected exception escaped derivative job %s", job["job_id"])

    def _supervisor_loop(self) -> None:
        """Recover abandoned claims and restore the configured worker count."""
        while not self._stop_event.wait(_SUPERVISOR_INTERVAL_SECONDS):
            try:
                self._supervise_once()
            except Exception:  # noqa: BLE001
                logger.exception("Derivative supervisor iteration failed")

    def _supervise_once(self) -> None:
        dead_worker_ids: list[str] = []
        replacements: list[threading.Thread] = []
        with self._lifecycle_lock:
            alive: list[threading.Thread] = []
            alive_slots: set[int] = set()
            for thread in self._threads:
                slot = int(thread.name.rsplit("-", 1)[-1])
                if thread.is_alive():
                    alive.append(thread)
                    alive_slots.add(slot)
                else:
                    dead_worker_ids.append(self._worker_id(slot))
            for slot in range(1, self.worker_count + 1):
                if slot not in alive_slots and not self._stop_event.is_set():
                    replacement = self._new_worker(slot)
                    alive.append(replacement)
                    replacements.append(replacement)
            self._threads = alive
        for worker_id in dead_worker_ids:
            self._recover_running_jobs(claimed_by=worker_id)
        self._recover_running_jobs(expired_only=True)
        for thread in replacements:
            thread.start()
        if replacements:
            logger.warning("Restored %s derivative worker(s)", len(replacements))
            self._wake_event.set()

    def _reconcile_queued_jobs(self) -> None:
        """Terminalize queued work that no longer references an active/current source."""
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT j.id AS job_id, d.id AS derivative_id, d.source_mtime_ns, d.source_size,
                       a.id AS asset_id, a.path, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                LEFT JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                """
            ).fetchall()
            for row in rows:
                result_code = self._inapplicable_result(row)
                if result_code is None:
                    continue
                message = f"queued derivative is no longer applicable: {result_code}"
                conn.execute(
                    """
                    UPDATE derivative_jobs SET state = 'skipped', result_code = ?, error = ?,
                      completed_at = julianday('now'), updated_at = julianday('now')
                    WHERE id = ? AND state = 'queued'
                    """,
                    (result_code, message, row["job_id"]),
                )
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'skipped', last_error = ?, "
                    "updated_at = julianday('now') WHERE id = ?",
                    (message, row["derivative_id"]),
                )

    def _recover_running_jobs(self, *, claimed_by: str | None = None, expired_only: bool = False) -> int:
        """Recover abandoned claims using the same policy at startup and runtime."""
        _ensure_database()
        recovered = 0
        with _connect() as conn:
            clauses = ["j.state = 'running'"]
            params: list[Any] = []
            if claimed_by is not None:
                clauses.append("j.claimed_by = ?")
                params.append(claimed_by)
            elif expired_only:
                clauses.append("(j.lease_expires_at IS NULL OR j.lease_expires_at <= julianday('now'))")
            rows = conn.execute(
                f"""
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.id AS derivative_id,
                       d.source_mtime_ns, d.source_size, a.id AS asset_id, a.path, a.type,
                       a.deleted_at, a.offline, a.mtime_ns, a.size
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                LEFT JOIN assets a ON a.id = d.asset_id
                WHERE {" AND ".join(clauses)}
                """,
                params,
            ).fetchall()
            for row in rows:
                result_code = self._inapplicable_result(row)
                if result_code is not None:
                    state = "skipped"
                elif int(row["job_attempts"]) >= _MAX_ATTEMPTS:
                    state, result_code = "failed", "attempts_exhausted"
                else:
                    state = "queued"
                message = f"recovered abandoned derivative claim: {result_code or 'retry'}"
                conn.execute(
                    """
                    UPDATE derivative_jobs SET state = ?, result_code = ?, error = ?,
                      claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                      started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                      completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                      updated_at = julianday('now') WHERE id = ? AND state = 'running'
                    """,
                    (state, result_code, message, state, state, row["job_id"]),
                )
                conn.execute(
                    "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
                    (state, message, row["derivative_id"]),
                )
                recovered += 1
        if recovered:
            self._wake_event.set()
        return recovered

    @staticmethod
    def _inapplicable_result(row: sqlite3.Row) -> str | None:
        if row["asset_id"] is None or row["deleted_at"] is not None or row["offline"] or row["type"] != "image":
            return "asset_inactive"
        path = Path(row["path"])
        try:
            stat = path.stat()
        except OSError:
            return "source_missing"
        if (
            float(stat.st_mtime_ns) != float(row["source_mtime_ns"])
            or stat.st_size != int(row["source_size"])
            or row["mtime_ns"] is None
            or row["size"] is None
            or float(row["mtime_ns"]) != float(row["source_mtime_ns"])
            or int(row["size"]) != int(row["source_size"])
        ):
            return "source_changed"
        return None

    def _run_job(self, job: sqlite3.Row) -> None:
        from .thumbnails import derivative_cache_path, generate_derivative

        source = Path(job["source_path"])
        cache_path: str | None = None
        succeeded = False
        try:
            self._validate_claimed_source(job, source)
            cache_path = str(
                derivative_cache_path(
                    source,
                    kind=job["kind"],
                    max_long_edge=int(job["max_long_edge"]),
                    quality=int(job["quality"]),
                    format=job["format"],
                )
            )
            with self._file_lock:
                self._generating_paths.add(cache_path)
            derivative_bytes = generate_derivative(
                source,
                kind=job["kind"],
                max_long_edge=int(job["max_long_edge"]),
                quality=int(job["quality"]),
                format=job["format"],
                no_upscale=True,
            )
            self._validate_claimed_source(job, source)
            with _connect() as conn:
                completed = conn.execute(
                    """
                    UPDATE derivative_jobs SET state = 'done', error = NULL, completed_at = julianday('now'),
                      result_code = NULL, claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                      updated_at = julianday('now') WHERE id = ? AND state = 'running' AND claim_token = ?
                    """,
                    (job["job_id"], job["claim_token"]),
                )
                if completed.rowcount != 1:
                    logger.info("Ignored stale completion for derivative job %s", job["job_id"])
                    return
                conn.execute(
                    """
                    UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ?,
                      last_accessed_at = julianday('now'), last_error = NULL, updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (cache_path, len(derivative_bytes), job["id"]),
                )
            succeeded = True
        except Exception as exc:  # noqa: BLE001
            self._handle_failure(job, exc)
        finally:
            if cache_path is not None:
                with self._file_lock:
                    self._generating_paths.discard(cache_path)
            if succeeded:
                self._enforce_quota()

    def _validate_claimed_source(self, job: sqlite3.Row, source: Path) -> None:
        """Revalidate applicability after claim and before cache/render work."""
        with _connect() as conn:
            asset = conn.execute(
                "SELECT path, mtime_ns, size FROM assets "
                "WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (job["asset_id"],),
            ).fetchone()
        if asset is None:
            raise _DerivativeSkip("asset_inactive", "asset is deleted, offline, or no longer an image")
        try:
            stat = source.stat()
        except FileNotFoundError as exc:
            raise _DerivativeSkip("source_missing", f"source file is missing: {source}") from exc
        if (
            str(asset["path"]) != str(source)
            or float(stat.st_mtime_ns) != float(job["source_mtime_ns"])
            or stat.st_size != int(job["source_size"])
        ):
            raise _DerivativeSkip("source_changed", "source identity changed after derivative was queued")

    def _handle_failure(self, job: sqlite3.Row, exc: Exception) -> None:
        attempts = int(job["job_attempts"]) + 1
        if isinstance(exc, _DerivativeSkip):
            state, result_code, retry = "skipped", exc.result_code, False
        elif isinstance(exc, (FileNotFoundError,)):
            state, result_code, retry = "skipped", "source_missing", False
        elif isinstance(exc, UnidentifiedImageError) or (isinstance(exc, APIError) and exc.status_code < 500):
            state, result_code, retry = "failed", "invalid_source", False
        else:
            transient = isinstance(exc, (OSError, sqlite3.OperationalError))
            retry = transient and attempts < 3 and not self._stop_event.is_set()
            state = "queued" if retry else "failed"
            result_code = None if retry else ("attempts_exhausted" if transient else "internal_error")
        if retry:
            self._stop_event.wait(2 ** (attempts - 1))
        with _connect() as conn:
            transitioned = conn.execute(
                """
                UPDATE derivative_jobs SET state = ?, error = ?, result_code = ?,
                  completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                  started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                  claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                  updated_at = julianday('now')
                WHERE id = ? AND state = 'running' AND claim_token = ?
                """,
                (state, str(exc), result_code, state, state, job["job_id"], job["claim_token"]),
            )
            if transitioned.rowcount == 1:
                conn.execute(
                    "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
                    (state, str(exc), job["id"]),
                )
            else:
                logger.info("Ignored stale failure for derivative job %s", job["job_id"])
                return
        if retry:
            self._wake_event.set()
        elif state == "skipped":
            logger.info("Derivative job %s skipped (%s): %s", job["job_id"], result_code, exc)
        else:
            logger.warning("Derivative job %s failed permanently (%s): %s", job["job_id"], result_code, exc)

    def _enforce_quota(self) -> None:
        with _connect() as conn:
            total = int(
                conn.execute(
                    "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
                ).fetchone()[0]
            )
            if total <= self.quota_bytes:
                return
            candidates = conn.execute(
                """
                SELECT id, cache_path, byte_size FROM asset_derivatives
                WHERE status = 'ready' AND cache_path IS NOT NULL
                ORDER BY COALESCE(last_accessed_at, created_at) ASC
                """
            ).fetchall()
            for row in candidates:
                if total <= self.quota_bytes:
                    break
                cache_path = str(row["cache_path"])
                with self._file_lock:
                    if cache_path in self._generating_paths or cache_path in self._served_paths:
                        continue
                    with suppress(OSError):
                        Path(cache_path).unlink()
                total -= int(row["byte_size"] or 0)
                conn.execute(
                    """
                    UPDATE asset_derivatives SET status = 'queued', cache_path = NULL, byte_size = NULL,
                      updated_at = julianday('now') WHERE id = ?
                    """,
                    (row["id"],),
                )


scheduler = DerivativeScheduler()


class _DerivativeSkip(Exception):
    """Controlled terminal outcome for work that is no longer applicable."""

    def __init__(self, result_code: str, message: str):
        super().__init__(message)
        self.result_code = result_code
