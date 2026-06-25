"""Durable priority scheduler for image derivative generation."""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
import time
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

    def start(self) -> None:
        """Start workers and recover jobs interrupted by a prior process."""
        with self._lifecycle_lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            _ensure_database()
            with _connect() as conn:
                conn.execute(
                    "UPDATE derivative_jobs SET state = 'queued', started_at = NULL, updated_at = julianday('now') "
                    "WHERE state = 'running'"
                )
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'queued', updated_at = julianday('now') "
                    "WHERE status = 'running'"
                )
            self._stop_event.clear()
            self._threads = [
                threading.Thread(target=self._worker_loop, name=f"derivative-worker-{index + 1}", daemon=True)
                for index in range(self.worker_count)
            ]
            for thread in self._threads:
                thread.start()
            self._wake_event.set()

    def stop(self) -> None:
        """Stop workers and wait briefly for in-flight generation to finish."""
        with self._lifecycle_lock:
            threads = self._threads
            self._stop_event.set()
            self._wake_event.set()
        deadline = time.monotonic() + 1
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._lifecycle_lock:
            self._threads = [thread for thread in threads if thread.is_alive()]

    def is_running(self) -> bool:
        """Return whether at least one configured worker is alive."""
        with self._lifecycle_lock:
            return any(thread.is_alive() for thread in self._threads)

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
            asset = conn.execute("SELECT path FROM assets WHERE id = ? AND deleted_at IS NULL", (asset_id,)).fetchone()
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
                "SELECT id FROM assets WHERE path = ? AND type = 'image' AND deleted_at IS NULL ORDER BY id LIMIT 1",
                (str(path.resolve()),),
            ).fetchone()
        return int(row["id"]) if row else None

    def get_asset_path(self, asset_id: int) -> Path | None:
        """Return the active source path for an asset ID."""
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL",
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

    def warm_library(self, library_id: int) -> dict[str, int]:
        """Schedule default thumbnail and preview derivatives for a library."""
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
            for kind, variants in DERIVATIVE_VARIANTS.items():
                for variant in variants:
                    try:
                        self.schedule_derivative(
                            int(asset["id"]),
                            kind,
                            str(variant["name"]),
                            priority=3,
                            max_long_edge=int(variant["max_long_edge"]),
                            quality=int(variant["quality"]),
                        )
                        scheduled += 1
                    except OSError:
                        continue
        return {"assets": len(assets), "derivatives_considered": scheduled}

    def library_status(self, library_id: int) -> dict[str, int | float]:
        """Return warm coverage and quota utilization for one library."""
        _ensure_database()
        with _connect() as conn:
            if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
                raise KeyError(library_id)
            total_assets = int(
                conn.execute(
                    "SELECT count(*) FROM assets WHERE library_id = ? AND type = 'image' AND deleted_at IS NULL",
                    (library_id,),
                ).fetchone()[0]
            )
            ready_rows = conn.execute(
                """
                SELECT d.cache_path, d.byte_size
                FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
                WHERE a.library_id = ? AND d.status = 'ready'
                  AND d.source_mtime_ns = a.mtime_ns
                  AND d.source_size = a.size
                  AND d.cache_path IS NOT NULL
                """,
                (library_id,),
            ).fetchall()
            ready = 0
            used = 0
            for row in ready_rows:
                if Path(row["cache_path"]).is_file():
                    ready += 1
                    used += row["byte_size"] or 0
        return {
            "library_id": library_id,
            "total_assets": total_assets,
            "ready_derivatives": ready,
            "expected_derivatives": total_assets * sum(len(variants) for variants in DERIVATIVE_VARIANTS.values()),
            "quota_bytes": self.quota_bytes,
            "quota_used_bytes": used,
            "quota_utilization": used / self.quota_bytes if self.quota_bytes else 0.0,
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
        with _connect() as conn:
            paths = [
                row[0] for row in conn.execute("SELECT cache_path FROM asset_derivatives WHERE cache_path IS NOT NULL")
            ]
            catalog_entries = int(conn.execute("SELECT count(*) FROM asset_derivatives").fetchone()[0])
            conn.execute("DELETE FROM derivative_jobs")
            conn.execute("DELETE FROM asset_derivatives")
        files_dir = THUMBNAIL_CACHE_DIR / "files"
        paths.extend(str(path) for path in files_dir.iterdir() if path.is_file()) if files_dir.is_dir() else None
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
        return {"catalog_entries_cleared": catalog_entries, "files_deleted": deleted}

    def _claim_job(self) -> sqlite3.Row | None:
        _ensure_database()
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT j.id AS job_id, j.attempts AS job_attempts, d.*, a.path AS source_path
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                ORDER BY j.priority ASC, j.created_at ASC, j.id ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["job_attempts"]) + 1
            conn.execute(
                """
                UPDATE derivative_jobs SET state = 'running', attempts = ?, started_at = julianday('now'),
                  updated_at = julianday('now') WHERE id = ?
                """,
                (attempts, row["job_id"]),
            )
            conn.execute(
                "UPDATE asset_derivatives SET status = 'running', attempts = ?, updated_at = julianday('now') WHERE id = ?",
                (attempts, row["id"]),
            )
            return row

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._claim_job()
            except sqlite3.OperationalError:
                logger.exception("Derivative worker could not read the job queue")
                self._stop_event.wait(0.5)
                continue
            if job is None:
                self._wake_event.clear()
                self._wake_event.wait(timeout=1)
                continue
            self._run_job(job)

    def _run_job(self, job: sqlite3.Row) -> None:
        from .thumbnails import derivative_cache_path, generate_derivative

        source = Path(job["source_path"])
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
        succeeded = False
        try:
            derivative_bytes = generate_derivative(
                source,
                kind=job["kind"],
                max_long_edge=int(job["max_long_edge"]),
                quality=int(job["quality"]),
                format=job["format"],
                no_upscale=True,
            )
            with _connect() as conn:
                conn.execute(
                    """
                    UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ?,
                      last_accessed_at = julianday('now'), last_error = NULL, updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (cache_path, len(derivative_bytes), job["id"]),
                )
                conn.execute(
                    """
                    UPDATE derivative_jobs SET state = 'done', error = NULL, completed_at = julianday('now'),
                      updated_at = julianday('now') WHERE id = ?
                    """,
                    (job["job_id"],),
                )
            succeeded = True
        except Exception as exc:  # noqa: BLE001
            self._handle_failure(job, exc)
        finally:
            with self._file_lock:
                self._generating_paths.discard(cache_path)
            if succeeded:
                self._enforce_quota()

    def _handle_failure(self, job: sqlite3.Row, exc: Exception) -> None:
        attempts = int(job["job_attempts"]) + 1
        permanent = isinstance(exc, (FileNotFoundError, UnidentifiedImageError)) or (
            isinstance(exc, APIError) and exc.status_code < 500
        )
        retry = not permanent and attempts < 3 and not self._stop_event.is_set()
        if retry:
            self._stop_event.wait(2 ** (attempts - 1))
        state = "queued" if retry else "failed"
        with _connect() as conn:
            conn.execute(
                "UPDATE derivative_jobs SET state = ?, error = ?, updated_at = julianday('now') WHERE id = ?",
                (state, str(exc), job["job_id"]),
            )
            conn.execute(
                "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
                (state, str(exc), job["id"]),
            )
        if retry:
            self._wake_event.set()
        else:
            logger.warning("Derivative job %s failed permanently: %s", job["job_id"], exc)

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
