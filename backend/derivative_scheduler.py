"""Durable priority scheduler for image derivative generation."""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import UnidentifiedImageError

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "backend"

from .config import (
    DERIVATIVE_JOB_LEASE_SECONDS,
    DERIVATIVE_LEASE_HEARTBEAT_SECONDS,
    DERIVATIVE_QUOTA_BYTES,
    DERIVATIVE_RECONCILE_BATCH_SIZE,
    DERIVATIVE_RECONCILE_ENABLED,
    DERIVATIVE_RECONCILE_INTERVAL_SECONDS,
    DERIVATIVE_RECONCILE_YIELD_SECONDS,
    DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS,
    DERIVATIVE_VARIANTS,
    DERIVATIVE_WORKER_COUNT,
    THUMBNAIL_CACHE_DIR,
)
from .errors import APIError
from .metadata_store import _connect, initialize_database

logger = logging.getLogger(__name__)
_SUPERVISOR_INTERVAL_SECONDS = 30
_MAX_ATTEMPTS = 3


def _lease_days() -> float:
    """Return the configured job lease duration expressed in Julian days."""
    return float(DERIVATIVE_JOB_LEASE_SECONDS) / 86400.0


@dataclass
class DerivativeReconcileSummary:
    """Bounded counters from one configured derivative reconciliation pass."""

    assets_considered: int = 0
    desired_derivatives: int = 0
    already_ready: int = 0
    already_active: int = 0
    created_derivative_rows: int = 0
    created_jobs: int = 0
    requeued_without_job: int = 0
    terminal_failed: int = 0
    terminal_skipped: int = 0
    deferred_capacity: int = 0
    source_unavailable: int = 0

    def as_dict(self) -> dict[str, int]:
        """Serialize counters without candidate path data."""
        return asdict(self)


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
        self._start_condition = threading.Condition(self._lifecycle_lock)
        self._start_in_progress = False
        self._file_lock = threading.RLock()
        self._generating_paths: set[str] = set()
        self._served_paths: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._supervisor_thread: threading.Thread | None = None
        self._reconciler_thread: threading.Thread | None = None
        self._reconciler_stop_event = threading.Event()
        self._reconcile_status: dict[str, Any] = {
            "enabled": DERIVATIVE_RECONCILE_ENABLED,
            "running": False,
            "last_reconcile_started_at": None,
            "last_reconcile_completed_at": None,
            "last_reconcile_status": None,
            "last_reconcile_created_jobs": 0,
            "lease_renewal_failures_total": 0,
        }
        self._lease_renewal_failures: int = 0
        self._shutdown_clean: bool | None = None
        self._instance_id = uuid.uuid4().hex
        self._pending_unlinks: list[tuple[str, int, int]] = []

    def start(self) -> None:
        """Start workers and recover jobs interrupted by a prior process.

        A restart after an incomplete stop must not permanently refuse to restore
        missing worker slots because a stale thread object remains in ``_threads``.
        Dead thread objects are pruned first, then one worker thread is created per
        missing slot so the configured worker count is restored exactly.
        """
        with self._start_condition:
            while self._start_in_progress:
                self._start_condition.wait()
            # Drop stale dead thread objects left behind by an incomplete stop.
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            cold_start = not self._threads
            self._start_in_progress = True
            if self._stop_event.is_set():
                cold_start = False
        try:
            if cold_start:
                # Recovery must happen before any newly-created worker can claim a
                # queued job.  This is deliberately outside the lifecycle lock:
                # SQLite work may wake code that needs that lock.
                _ensure_database()
                self._reconcile_queued_jobs()
                self._recover_running_jobs()
            with self._start_condition:
                alive_slots: set[int] = set()
                for thread in self._threads:
                    try:
                        alive_slots.add(int(thread.name.rsplit("-", 1)[-1]))
                    except (ValueError, IndexError):
                        continue
                self._stop_event.clear()
                self._wake_event.set()
                replacements: list[threading.Thread] = []
                for slot in range(1, self.worker_count + 1):
                    if slot not in alive_slots:
                        worker = self._new_worker(slot)
                        self._threads.append(worker)
                        replacements.append(worker)
                for worker in replacements:
                    worker.start()
                if self._supervisor_thread is None or not self._supervisor_thread.is_alive():
                    self._supervisor_thread = threading.Thread(
                        target=self._supervisor_loop,
                        name="derivative-supervisor",
                        daemon=True,
                    )
                    self._supervisor_thread.start()
                self._start_reconciler()
        except BaseException:
            with self._start_condition:
                self._start_in_progress = False
                self._start_condition.notify_all()
            raise
        with self._start_condition:
            self._start_in_progress = False
            self._start_condition.notify_all()

    def stop(self) -> None:
        """Stop workers and wait a bounded timeout per worker.

        Sets the stop event so no new claims begin, wakes all workers, then joins
        each worker (and the supervisor/reconciler) with a per-worker bounded
        timeout. Records whether shutdown completed cleanly so callers can detect
        an incomplete stop that left in-flight renders running.
        """
        with self._lifecycle_lock:
            threads = list(self._threads)
            supervisor = self._supervisor_thread
            reconciler = self._reconciler_thread
            self._stop_event.set()
            self._reconciler_stop_event.set()
            self._wake_event.set()
        clean = True
        for thread in threads:
            with suppress(RuntimeError):
                thread.join(timeout=DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS)
            if thread.is_alive():
                clean = False
        if supervisor is not None:
            with suppress(RuntimeError):
                supervisor.join(timeout=DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS)
            if supervisor.is_alive():
                clean = False
        if reconciler is not None:
            with suppress(RuntimeError):
                reconciler.join(timeout=DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS)
            if reconciler.is_alive():
                clean = False
        with self._lifecycle_lock:
            self._threads = [thread for thread in threads if thread.is_alive()]
            self._supervisor_thread = supervisor if supervisor is not None and supervisor.is_alive() else None
            self._reconciler_thread = reconciler if reconciler is not None and reconciler.is_alive() else None
            self._reconcile_status["running"] = bool(self._reconciler_thread)
            self._shutdown_clean = clean

    def last_shutdown_clean(self) -> bool | None:
        """Return whether the most recent stop() completed within its timeout."""
        with self._lifecycle_lock:
            return self._shutdown_clean

    def is_running(self) -> bool:
        """Return whether at least one configured worker is alive."""
        with self._lifecycle_lock:
            return any(thread.is_alive() for thread in self._threads)

    def alive_worker_count(self) -> int:
        """Return the current number of alive derivative workers."""
        with self._lifecycle_lock:
            return sum(thread.is_alive() for thread in self._threads)

    def reconciliation_status(self) -> dict[str, Any]:
        """Return bounded desired-state runtime diagnostics."""
        with self._lifecycle_lock:
            status = dict(self._reconcile_status)
            status["lease_renewal_failures_total"] = self._lease_renewal_failures
            return status

    def _start_reconciler(self) -> None:
        """Start startup catch-up and periodic reconciliation without blocking readiness."""
        if not DERIVATIVE_RECONCILE_ENABLED:
            return
        if self._reconciler_thread is not None and self._reconciler_thread.is_alive():
            return
        self._reconciler_stop_event.clear()
        self._reconciler_thread = threading.Thread(
            target=self._reconciler_loop,
            name="derivative-reconciler",
            daemon=True,
        )
        self._reconciler_thread.start()

    def _reconciler_loop(self) -> None:
        first = True
        while not self._reconciler_stop_event.is_set():
            self._run_reconcile_all("startup" if first else "periodic")
            first = False
            if self._reconciler_stop_event.wait(DERIVATIVE_RECONCILE_INTERVAL_SECONDS):
                break
        with self._lifecycle_lock:
            self._reconcile_status["running"] = False

    def _run_reconcile_all(self, reason: str) -> None:
        """Apply automatic desired-state policy to all warm-enabled libraries."""
        from .metadata_store import list_libraries

        now_ms = int(time.time() * 1000)
        with self._lifecycle_lock:
            self._reconcile_status.update(
                running=True,
                last_reconcile_started_at=now_ms,
                last_reconcile_status="running",
                last_reconcile_created_jobs=0,
            )
        created_jobs = 0
        stopped = False
        try:
            for library in list_libraries():
                if self._reconciler_stop_event.is_set():
                    stopped = True
                    break
                if not bool(library["warm_enabled"]):
                    continue
                created_jobs += self.reconcile_desired_derivatives(
                    library_id=int(library["id"]),
                    reason=reason,
                    cancel_event=self._reconciler_stop_event,
                ).created_jobs
            status = "stopped" if stopped or self._reconciler_stop_event.is_set() else "ok"
        except Exception:  # noqa: BLE001
            logger.exception("Derivative %s reconciliation failed", reason)
            status = "error"
        with self._lifecycle_lock:
            self._reconcile_status.update(
                running=False,
                last_reconcile_completed_at=int(time.time() * 1000),
                last_reconcile_status=status,
                last_reconcile_created_jobs=created_jobs,
            )

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

    @staticmethod
    def _configured_variants(kinds: Sequence[str] | None) -> list[tuple[str, dict[str, Any]]]:
        """Validate and flatten the configured variants requested by a caller."""
        selected_kinds = list(DERIVATIVE_VARIANTS) if kinds is None else list(kinds)
        unknown = next((kind for kind in selected_kinds if kind not in DERIVATIVE_VARIANTS), None)
        if unknown is not None:
            raise ValueError(f"Unsupported derivative kind: {unknown}")
        return [(kind, variant) for kind in selected_kinds for variant in DERIVATIVE_VARIANTS[kind]]

    _ESTIMATED_DERIVATIVE_BYTES_FALLBACK = 64 * 1024

    def _estimate_new_derivative_bytes(self, conn: sqlite3.Connection) -> int:
        """Return a bounded estimate for one new derivative's on-disk size."""
        average = conn.execute(
            "SELECT COALESCE(avg(byte_size), 0) FROM asset_derivatives WHERE status = 'ready' AND byte_size > 0"
        ).fetchone()[0]
        if average and float(average) > 0:
            return int(average)
        return self._ESTIMATED_DERIVATIVE_BYTES_FALLBACK

    def _reserve_capacity(self, conn: sqlite3.Connection, estimated_bytes: int) -> bool:
        """Reserve capacity for one new derivative, evicting eligible cached files.

        Returns True when the new derivative fits under the quota. Eligible LRU
        ``ready`` files that are not currently served or generating are evicted to
        make room. Evicted rows become ``evicted`` (a visible, non-ready state)
        rather than a false ``queued`` row.

        File deletion is deferred to after the caller's write transaction
        completes (via ``_process_pending_unlinks``) so that a transaction
        rollback cannot leave a ``ready`` row with no cache file.
        """
        ready_used = int(
            conn.execute("SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'").fetchone()[
                0
            ]
        )
        reserved = (
            int(
                conn.execute(
                    """SELECT count(*) FROM derivative_jobs j
                   JOIN asset_derivatives d ON d.id = j.derivative_id
                   WHERE j.state IN ('queued', 'running') AND d.status != 'ready'"""
                ).fetchone()[0]
            )
            * estimated_bytes
        )
        used = ready_used + reserved
        if used + estimated_bytes <= self.quota_bytes:
            return True
        needed = (used + estimated_bytes) - self.quota_bytes
        evict_ids: list[int] = []
        evict_paths: list[str] = []
        evict_bytes: list[int] = []
        candidates = conn.execute(
            """
            SELECT id, cache_path, byte_size FROM asset_derivatives
            WHERE status = 'ready' AND cache_path IS NOT NULL
            ORDER BY COALESCE(last_accessed_at, created_at) ASC
            """
        ).fetchall()
        for row in candidates:
            if sum(evict_bytes) >= needed:
                break
            cache_path = str(row["cache_path"])
            with self._file_lock:
                if cache_path in self._served_paths or cache_path in self._generating_paths:
                    continue
            evict_ids.append(int(row["id"]))
            evict_paths.append(cache_path)
            evict_bytes.append(int(row["byte_size"] or 0))
        if not evict_ids:
            return False
        placeholders = ",".join("?" for _ in evict_ids)
        conn.execute(
            f"""
            UPDATE asset_derivatives
            SET status = 'evicted', cache_path = NULL, byte_size = NULL,
                last_error = 'evicted: capacity reservation', updated_at = julianday('now')
            WHERE id IN ({placeholders}) AND status = 'ready'
            """,
            evict_ids,
        )
        for i in range(len(evict_ids)):
            self._pending_unlinks.append((evict_paths[i], evict_ids[i], evict_bytes[i]))
        return True

    def repair_derivative_consistency(self, derivative_ids: list[int]) -> int:
        """Create a queued job for each current ``queued`` derivative without one.

        Unlike ``reconcile_desired_derivatives``, this repair overrides
        ``warm_enabled`` because an already-existing ``queued`` row must have a
        job regardless of library policy.  Historical or source-changed identities
        are terminalized with the appropriate skipped result code.
        """
        if not derivative_ids:
            return 0
        created = 0
        _ensure_database()
        for offset in range(0, len(derivative_ids), DERIVATIVE_RECONCILE_BATCH_SIZE):
            batch = derivative_ids[offset : offset + DERIVATIVE_RECONCILE_BATCH_SIZE]
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for did in batch:
                    row = conn.execute(
                        """
                        SELECT d.id, d.status, d.asset_id, d.kind, d.variant,
                               d.source_mtime_ns, d.source_size, d.format, d.max_long_edge, d.quality,
                               a.id AS a_id, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
                        FROM asset_derivatives d
                        LEFT JOIN assets a ON a.id = d.asset_id
                        WHERE d.id = ?
                        """,
                        (did,),
                    ).fetchone()
                    if row is None:
                        continue
                    if row["status"] != "queued":
                        continue
                    latest_job = conn.execute(
                        "SELECT state FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
                        (did,),
                    ).fetchone()
                    if latest_job is not None and latest_job["state"] in ("queued", "running"):
                        continue
                    # Check if identity is still current
                    if row["a_id"] is None or row["type"] != "image" or row["deleted_at"] is not None or row["offline"]:
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "asset_inactive",
                            "integrity: derivative asset is inactive",
                        )
                        continue
                    try:
                        stat = Path(
                            conn.execute("SELECT path FROM assets WHERE id = ?", (row["asset_id"],)).fetchone()[0]
                        ).stat()
                    except (OSError, TypeError):
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "source_missing",
                            "integrity: derivative source file is missing",
                        )
                        continue
                    if (
                        float(stat.st_mtime_ns) != float(row["source_mtime_ns"])
                        or stat.st_size != int(row["source_size"])
                        or float(row["mtime_ns"]) != float(row["source_mtime_ns"])
                        or int(row["size"]) != int(row["source_size"])
                    ):
                        self._terminalize_derivative(
                            conn,
                            did,
                            row,
                            "skipped",
                            "source_changed",
                            "integrity: derivative source identity changed",
                        )
                        continue
                    # Valid current identity: create a queued job
                    conn.execute(
                        "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'queued')",
                        (did,),
                    )
                    created += 1
            self._wake_event.set()
        return created

    @staticmethod
    def _terminalize_derivative(
        conn: sqlite3.Connection,
        derivative_id: int,
        row: sqlite3.Row,
        state: str,
        result_code: str,
        message: str,
    ) -> None:
        """Terminalize a derivative row and any active jobs."""
        conn.execute(
            "UPDATE asset_derivatives SET status = ?, last_error = ?, updated_at = julianday('now') WHERE id = ?",
            (state, message, derivative_id),
        )
        conn.execute(
            """
            UPDATE derivative_jobs
            SET state = ?, result_code = ?, error = ?,
                claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                completed_at = julianday('now'), updated_at = julianday('now')
            WHERE derivative_id = ? AND state IN ('queued', 'running')
            """,
            (state, result_code, message, derivative_id),
        )

    def _process_pending_unlinks(self) -> None:
        """Delete files for evicted derivatives, compensating on failure.

        Must be called after the write transaction that produced pending
        unlinks has committed. A deletion failure restores the ready row
        so no ``ready`` row ever points to a deleted cache file.
        """
        pending = list(self._pending_unlinks)
        self._pending_unlinks.clear()
        if not pending:
            return
        for cache_path, evict_id, byte_size in pending:
            try:
                path = Path(cache_path)
                if path.exists():
                    path.unlink()
            except OSError:
                with _connect() as conn:
                    conn.execute(
                        """
                        UPDATE asset_derivatives
                        SET status = 'ready', cache_path = ?, byte_size = ?,
                            last_error = NULL, updated_at = julianday('now')
                        WHERE id = ? AND status = 'evicted'
                        """,
                        (cache_path, byte_size, evict_id),
                    )

    def _coalesce_derivative_job(
        self,
        conn: sqlite3.Connection,
        *,
        asset_id: int,
        kind: str,
        variant: str,
        source_mtime_ns: float,
        source_size: int,
        max_long_edge: int,
        quality: int,
        format: str,
        priority: int,
        retry_failed: bool,
        deferrable: bool = False,
    ) -> tuple[int, str]:
        """Create or repair one identity while the caller owns a write transaction.

        When ``deferrable`` is True (automatic background reconciliation), an
        identity that cannot reserve quota capacity is written as ``deferred_capacity``
        without creating a runnable job. Interactive/manual callers pass
        ``deferrable=False`` and rely on post-render eviction instead.
        """
        inserted = (
            conn.execute(
                """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format,
              quality, max_long_edge, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
            ON CONFLICT(asset_id, kind, variant, source_mtime_ns, source_size) DO NOTHING
            """,
                (asset_id, kind, variant, source_mtime_ns, source_size, format, quality, max_long_edge),
            ).rowcount
            == 1
        )
        derivative = conn.execute(
            """
            SELECT id, status, cache_path FROM asset_derivatives
            WHERE asset_id = ? AND kind = ? AND variant = ?
              AND source_mtime_ns = ? AND source_size = ?
            """,
            (asset_id, kind, variant, source_mtime_ns, source_size),
        ).fetchone()
        if derivative is None:
            raise RuntimeError("Derivative identity was not available after insert")
        derivative_id = int(derivative["id"])
        if derivative["status"] == "ready" and derivative["cache_path"] and Path(derivative["cache_path"]).is_file():
            return derivative_id, "ready"
        latest = conn.execute(
            "SELECT result_code FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
            (derivative_id,),
        ).fetchone()
        result_code = latest["result_code"] if latest is not None else None
        if (
            derivative["status"] in {"failed", "skipped"}
            and not retry_failed
            and not (derivative["status"] == "skipped" and result_code in {"source_missing", "asset_inactive"})
        ):
            return derivative_id, str(derivative["status"])
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
            return derivative_id, "active"
        if derivative["status"] in {"deferred_capacity", "evicted"}:
            reservable = self._reserve_capacity(conn, self._estimate_new_derivative_bytes(conn))
            if not reservable:
                conn.execute(
                    """
                    UPDATE asset_derivatives
                    SET status = ?, last_error = 'deferred: capacity unavailable',
                        updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (derivative["status"], derivative_id),
                )
                return derivative_id, str(derivative["status"])
        elif deferrable:
            reservable = self._reserve_capacity(conn, self._estimate_new_derivative_bytes(conn))
            if not reservable:
                conn.execute(
                    """
                    UPDATE asset_derivatives
                    SET status = 'deferred_capacity', last_error = 'deferred: capacity unavailable',
                        updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (derivative_id,),
                )
                return derivative_id, "deferred_capacity"
        conn.execute(
            "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, ?, 'queued')",
            (derivative_id, priority),
        )
        conn.execute(
            """
            UPDATE asset_derivatives
            SET status = 'queued', cache_path = NULL, byte_size = NULL, last_error = NULL,
                updated_at = julianday('now')
            WHERE id = ?
            """,
            (derivative_id,),
        )
        return derivative_id, "created" if inserted else "requeued"

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
            asset = conn.execute(
                "SELECT path FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
        if asset is None:
            raise KeyError(asset_id)
        stat = Path(asset["path"]).stat()
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT 1 FROM assets WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0",
                (asset_id,),
            ).fetchone()
            if current is None:
                raise KeyError(asset_id)
            derivative_id, _outcome = self._coalesce_derivative_job(
                conn,
                asset_id=asset_id,
                kind=kind,
                variant=variant,
                source_mtime_ns=float(stat.st_mtime_ns),
                source_size=stat.st_size,
                max_long_edge=max_long_edge,
                quality=quality,
                format=format,
                priority=priority,
                retry_failed=True,
                deferrable=False,
            )
        self._wake_event.set()
        self._process_pending_unlinks()
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

    def get_derivative_outcome(self, derivative_id: int) -> dict[str, Any] | None:
        """Return a bounded read model for one scheduled derivative by ID.

        The read model exposes the derivative state, latest fenced job outcome,
        result code, error, cache path, and whether the identity is still current.
        Request waiters use this to branch on ready/failed/skipped/deferred outcomes
        without polling by source identity or parsing error strings.
        """
        _ensure_database()
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT d.id, d.status, d.cache_path, d.last_error,
                  (SELECT j.state FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS latest_job_state,
                  (SELECT j.result_code FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS result_code,
                  (SELECT j.error FROM derivative_jobs j WHERE j.derivative_id = d.id
                     ORDER BY j.id DESC LIMIT 1) AS error,
                  a.id AS asset_id, a.mtime_ns, a.size, d.source_mtime_ns, d.source_size
                FROM asset_derivatives d LEFT JOIN assets a ON a.id = d.asset_id
                WHERE d.id = ?
                """,
                (derivative_id,),
            ).fetchone()
        if row is None:
            return None
        is_current = (
            row["asset_id"] is not None
            and row["mtime_ns"] is not None
            and row["size"] is not None
            and float(row["mtime_ns"]) == float(row["source_mtime_ns"])
            and int(row["size"]) == int(row["source_size"])
        )
        return {
            "derivative_id": int(row["id"]),
            "derivative_state": str(row["status"]),
            "latest_job_state": str(row["latest_job_state"]) if row["latest_job_state"] is not None else None,
            "result_code": row["result_code"],
            "error": row["error"],
            "cache_path": row["cache_path"],
            "is_current": bool(is_current),
        }

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

    def reconcile_desired_derivatives(
        self,
        *,
        library_id: int | None = None,
        scope_path: str | None = None,
        asset_ids: Sequence[int] | None = None,
        kinds: Sequence[str] | None = None,
        priority: int = 3,
        retry_failed: bool = False,
        reason: str,
        respect_warm_policy: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> DerivativeReconcileSummary:
        """Create/coalesce the configured current variants for exactly one scope."""
        if sum(value is not None for value in (library_id, scope_path, asset_ids)) != 1:
            raise ValueError("Exactly one of library_id, scope_path, or asset_ids is required")
        variants = self._configured_variants(kinds)
        priority = max(0, min(priority, 3))
        _ensure_database()
        with _connect() as conn:
            scope_clause = ""
            scope_params: list[Any] = []
            if scope_path is not None:
                from .metadata_store import get_library_for_path

                library = get_library_for_path(scope_path)
                if library is None:
                    raise KeyError(scope_path)
                library_id = int(library["id"])
                path = str(Path(scope_path).resolve())
                escaped_path = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                scope_clause = " AND (a.path = ? OR a.path LIKE ? ESCAPE '\\')"
                scope_params = [path, escaped_path.rstrip("/") + "/%"]
            if library_id is not None:
                library = conn.execute("SELECT warm_enabled FROM libraries WHERE id = ?", (library_id,)).fetchone()
                if library is None:
                    raise KeyError(library_id)
                if respect_warm_policy and not bool(library["warm_enabled"]):
                    return DerivativeReconcileSummary()
                where = "a.library_id = ?"
                params: list[Any] = [library_id, *scope_params]
            else:
                requested_ids = [int(asset_id) for asset_id in asset_ids or ()]
                if not requested_ids:
                    return DerivativeReconcileSummary()
                where = f"a.id IN ({', '.join('?' for _ in requested_ids)})"
                if respect_warm_policy:
                    where += " AND EXISTS (SELECT 1 FROM libraries l WHERE l.id = a.library_id AND l.warm_enabled = 1)"
                params = [*requested_ids, *scope_params]
            assets = conn.execute(
                f"""
                SELECT a.id, a.path, a.mtime_ns, a.size
                FROM assets a
                WHERE {where} AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                {scope_clause}
                ORDER BY a.id
                """,
                params,
            ).fetchall()

        summary = DerivativeReconcileSummary(assets_considered=len(assets))
        candidates: list[tuple[int, float, int]] = []
        for asset in assets:
            try:
                stat = Path(asset["path"]).stat()
            except OSError:
                summary.source_unavailable += len(variants)
                continue
            if (
                asset["mtime_ns"] is None
                or asset["size"] is None
                or (float(asset["mtime_ns"]) != float(stat.st_mtime_ns) or int(asset["size"]) != stat.st_size)
            ):
                summary.source_unavailable += len(variants)
                continue
            candidates.append((int(asset["id"]), float(stat.st_mtime_ns), stat.st_size))
        summary.desired_derivatives = len(candidates) * len(variants)

        for offset in range(0, len(candidates), DERIVATIVE_RECONCILE_BATCH_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                break
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for asset_id, mtime_ns, size in candidates[offset : offset + DERIVATIVE_RECONCILE_BATCH_SIZE]:
                    current = conn.execute(
                        """
                        SELECT 1 FROM assets
                        WHERE id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0
                          AND mtime_ns = ? AND size = ?
                        """,
                        (asset_id, mtime_ns, size),
                    ).fetchone()
                    if current is None:
                        summary.source_unavailable += len(variants)
                        continue
                    for kind, variant in variants:
                        _derivative_id, outcome = self._coalesce_derivative_job(
                            conn,
                            asset_id=asset_id,
                            kind=kind,
                            variant=str(variant["name"]),
                            source_mtime_ns=mtime_ns,
                            source_size=size,
                            max_long_edge=int(variant["max_long_edge"]),
                            quality=int(variant["quality"]),
                            format="webp",
                            priority=priority,
                            retry_failed=retry_failed,
                            deferrable=True,
                        )
                        if outcome == "ready":
                            summary.already_ready += 1
                        elif outcome == "active":
                            summary.already_active += 1
                        elif outcome == "created":
                            summary.created_derivative_rows += 1
                            summary.created_jobs += 1
                        elif outcome == "requeued":
                            summary.requeued_without_job += 1
                            summary.created_jobs += 1
                        elif outcome == "failed":
                            summary.terminal_failed += 1
                        elif outcome == "skipped":
                            summary.terminal_skipped += 1
                        elif outcome == "deferred_capacity":
                            summary.deferred_capacity += 1
            self._wake_event.set()
            self._process_pending_unlinks()
            if offset + DERIVATIVE_RECONCILE_BATCH_SIZE < len(candidates):
                if cancel_event is not None:
                    if cancel_event.wait(DERIVATIVE_RECONCILE_YIELD_SECONDS):
                        break
                elif DERIVATIVE_RECONCILE_YIELD_SECONDS:
                    time.sleep(DERIVATIVE_RECONCILE_YIELD_SECONDS)
        return summary

    def warm_library(self, library_id: int, kind: str | None = None) -> dict[str, int | str | None]:
        """Schedule default derivative variants for a library.

        When ``kind`` is provided, only variants for that derivative kind are queued.
        """
        if kind is not None and kind not in DERIVATIVE_VARIANTS:
            raise ValueError(f"Unsupported derivative kind: {kind}")
        selected = [kind] if kind is not None else None
        # Keep test and extension seams that replace the bound scheduling method
        # functional; normal production calls always use the reconciler below.
        if "schedule_derivative" in self.__dict__:
            _ensure_database()
            with _connect() as conn:
                assets = conn.execute(
                    "SELECT id FROM assets WHERE library_id = ? AND type = 'image' AND deleted_at IS NULL AND offline = 0 ORDER BY id",
                    (library_id,),
                ).fetchall()
            variants_by_kind = {key: DERIVATIVE_VARIANTS[key] for key in (selected or DERIVATIVE_VARIANTS)}
            considered = 0
            for asset in assets:
                for derivative_kind, variants in variants_by_kind.items():
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
                            considered += 1
                        except (KeyError, OSError):
                            continue
            result: dict[str, int | str] = {"assets": len(assets), "derivatives_considered": considered}
            if kind is not None:
                result["kind"] = kind
            return result
        summary = self.reconcile_desired_derivatives(
            library_id=library_id,
            kinds=selected,
            priority=3,
            retry_failed=True,
            reason="manual_generate",
            respect_warm_policy=False,
        )
        result: dict[str, int | str] = {
            "assets": summary.assets_considered,
            "derivatives_considered": summary.desired_derivatives,
        }
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
            kind: {
                "ready_derivatives": 0,
                "expected_derivatives": 0,
                "desired_derivatives": 0,
                "missing_derivatives": 0,
                "queued_derivatives": 0,
                "running_derivatives": 0,
                "failed_derivatives": 0,
                "deferred_derivatives": 0,
            }
            for kind in DERIVATIVE_VARIANTS
        }
        expected_derivatives_per_asset = len(configured_variants)
        with _connect() as conn:
            library = conn.execute("SELECT warm_enabled FROM libraries WHERE id = ?", (library_id,)).fetchone()
            if library is None:
                raise KeyError(library_id)
            warm_enabled = bool(library["warm_enabled"])
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
                derivative_rows = conn.execute(
                    f"""
                    SELECT d.kind, d.status, d.cache_path, d.byte_size,
                      (SELECT j.state FROM derivative_jobs j WHERE j.derivative_id = d.id ORDER BY j.id DESC LIMIT 1)
                        AS latest_job_state
                    FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
                    WHERE a.library_id = ? AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                      AND d.source_mtime_ns = a.mtime_ns
                      AND d.source_size = a.size
                      AND ({variant_filter})
                    """,
                    (library_id, *variant_params),
                ).fetchall()
            else:
                derivative_rows = []
            ready = 0
            used = 0
            evicted = 0
            queued_without_job_by_kind = dict.fromkeys(DERIVATIVE_VARIANTS, 0)
            for kind, variants in DERIVATIVE_VARIANTS.items():
                by_kind[kind]["expected_derivatives"] = total_assets * len(variants)
                by_kind[kind]["desired_derivatives"] = total_assets * len(variants) if warm_enabled else 0
            for row in derivative_rows:
                kind = str(row["kind"])
                if row["status"] == "ready" and row["cache_path"] and Path(row["cache_path"]).is_file():
                    ready += 1
                    used += row["byte_size"] or 0
                    by_kind[kind]["ready_derivatives"] += 1
                elif row["status"] == "queued":
                    by_kind[kind]["queued_derivatives"] += 1
                    if row["latest_job_state"] not in {"queued", "running"}:
                        queued_without_job_by_kind[kind] += 1
                elif row["status"] == "running":
                    by_kind[kind]["running_derivatives"] += 1
                    if row["latest_job_state"] != "running":
                        queued_without_job_by_kind[kind] += 1
                elif row["status"] == "failed":
                    by_kind[kind]["failed_derivatives"] += 1
                elif row["status"] == "deferred_capacity":
                    by_kind[kind]["deferred_derivatives"] += 1
                elif row["status"] == "evicted":
                    evicted += 1
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
                      AND j.id = (
                          SELECT max(latest.id) FROM derivative_jobs latest
                          WHERE latest.derivative_id = j.derivative_id
                      )
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
        desired = total_assets * expected_derivatives_per_asset if warm_enabled else 0
        actionable_missing = 0
        terminal_failed = 0
        deferred = 0
        for kind, values in by_kind.items():
            current_missing = max(0, values["expected_derivatives"] - values["ready_derivatives"])
            values["missing_derivatives"] = current_missing
            terminal_failed += values["failed_derivatives"]
            deferred += values["deferred_derivatives"]
            if warm_enabled:
                active = values["queued_derivatives"] + values["running_derivatives"]
                active -= queued_without_job_by_kind[kind]
                terminal = values["failed_derivatives"] + values["deferred_derivatives"]
                actionable_missing += max(0, current_missing - active - terminal)
        return {
            "library_id": library_id,
            "warm_enabled": warm_enabled,
            "policy": "warm" if warm_enabled else "on_demand",
            "converged": not warm_enabled or actionable_missing == 0,
            "total_assets": total_assets,
            "ready_derivatives": ready,
            "expected_derivatives": total_assets * expected_derivatives_per_asset,
            "desired_derivatives": desired,
            "actionable_missing_derivatives": actionable_missing,
            "deferred_derivatives": deferred,
            "terminal_failed_derivatives": terminal_failed,
            "evicted_derivatives": evicted,
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
                conn.commit()
                self._reconcile_queued_jobs()
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
                (attempts, worker_id, claim_token, _lease_days(), row["job_id"]),
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
        self._reconcile_queued_jobs()
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
                       a.id AS asset_id, a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
                FROM derivative_jobs j
                JOIN asset_derivatives d ON d.id = j.derivative_id
                LEFT JOIN assets a ON a.id = d.asset_id
                WHERE j.state = 'queued'
                  AND (
                    a.id IS NULL OR a.type != 'image' OR a.deleted_at IS NOT NULL OR a.offline != 0
                    OR a.mtime_ns IS NULL OR a.size IS NULL
                    OR d.source_mtime_ns != a.mtime_ns OR d.source_size != a.size
                  )
                """
            ).fetchall()
            for row in rows:
                result_code = (
                    "asset_inactive"
                    if row["asset_id"] is None
                    or row["deleted_at"] is not None
                    or row["offline"]
                    or row["type"] != "image"
                    else "source_changed"
                )
                message = f"queued derivative is no longer applicable: {result_code}"
                transitioned = conn.execute(
                    """
                    UPDATE derivative_jobs SET state = 'skipped', result_code = ?, error = ?,
                      completed_at = julianday('now'), updated_at = julianday('now')
                    WHERE id = ? AND state = 'queued'
                    """,
                    (result_code, message, row["job_id"]),
                )
                if transitioned.rowcount == 1:
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
                clauses.append("(j.lease_expires_at IS NULL OR j.lease_expires_at <= julianday('now'))")  # noqa: E501
            rows = conn.execute(
                f"""
                SELECT j.id AS job_id, j.attempts AS job_attempts, j.claim_token,
                       d.id AS derivative_id,
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
                transitioned = conn.execute(
                    """
                    UPDATE derivative_jobs SET state = ?, result_code = ?, error = ?,
                      claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                      started_at = CASE WHEN ? = 'queued' THEN NULL ELSE started_at END,
                      completed_at = CASE WHEN ? IN ('skipped', 'failed') THEN julianday('now') ELSE NULL END,
                      updated_at = julianday('now')
                    WHERE id = ? AND state = 'running' AND claim_token IS ?
                    """,
                    (state, result_code, message, state, state, row["job_id"], row["claim_token"]),
                )
                if transitioned.rowcount == 1:
                    conn.execute(
                        "UPDATE asset_derivatives SET status = ?, last_error = ?, "
                        "updated_at = julianday('now') WHERE id = ?",
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

    def _renew_lease(self, job_id: int, claim_token: str) -> bool:
        """Extend the lease of a still-running, still-owned derivative claim.

        Returns True only when the matching running row with the same claim token
        was found and updated. A claim that already completed, failed, or was
        fenced by recovery is not touched. A database error is recorded as a lease
        renewal failure but never overwrites the worker's render outcome; fenced
        recovery arbitrates instead.
        """
        _ensure_database()
        try:
            with _connect() as conn:
                result = conn.execute(
                    """
                    UPDATE derivative_jobs
                    SET lease_expires_at = julianday('now') + ?
                    WHERE id = ? AND state = 'running' AND claim_token = ?
                    """,
                    (_lease_days(), job_id, claim_token),
                )
                renewed = result.rowcount == 1
        except sqlite3.Error:
            logger.warning("Derivative lease renewal failed for job %s", job_id)
            with self._lifecycle_lock:
                self._lease_renewal_failures += 1
                self._reconcile_status["lease_renewal_failures_total"] = self._lease_renewal_failures
            renewed = False
        if not renewed:
            logger.debug("Derivative lease renewal found no matching running claim for job %s", job_id)
        return renewed

    def _run_job(self, job: sqlite3.Row) -> None:
        from .thumbnails import derivative_cache_path, generate_derivative

        source = Path(job["source_path"])
        cache_path: str | None = None
        succeeded = False
        heartbeat = _LeaseHeartbeat(self, job["job_id"], job["claim_token"], DERIVATIVE_LEASE_HEARTBEAT_SECONDS)
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
            heartbeat.start()
            derivative_bytes = generate_derivative(
                source,
                kind=job["kind"],
                max_long_edge=int(job["max_long_edge"]),
                quality=int(job["quality"]),
                format=job["format"],
                no_upscale=True,
            )
            heartbeat.stop()
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
            heartbeat.stop()
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
        attempts = int(job["job_attempts"])
        if isinstance(exc, _DerivativeSkip):
            state, result_code, retry = "skipped", exc.result_code, False
        elif isinstance(exc, (FileNotFoundError,)):
            state, result_code, retry = "skipped", "source_missing", False
        elif isinstance(exc, UnidentifiedImageError) or (isinstance(exc, APIError) and exc.status_code < 500):
            state, result_code, retry = "failed", "invalid_source", False
        else:
            transient = isinstance(exc, (OSError, sqlite3.OperationalError))
            retry = transient and attempts < _MAX_ATTEMPTS and not self._stop_event.is_set()
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
                    UPDATE asset_derivatives
                    SET status = 'evicted', cache_path = NULL, byte_size = NULL,
                        last_error = 'evicted: quota capacity', updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
            if total > self.quota_bytes:
                logger.warning(
                    "Derivative quota still exceeded after eviction (%s > %s bytes); "
                    "a single derivative exceeds the configured quota",
                    total,
                    self.quota_bytes,
                )


scheduler = DerivativeScheduler()


class _LeaseHeartbeat:
    """Lightweight lease renewal owned by one claimed derivative job.

    The heartbeat runs on its own daemon thread and renews ``lease_expires_at``
    at most every ``interval_seconds`` (bounded to one third of the lease). It
    only updates a row that is still ``running`` with the same claim token, so a
    long render cannot be duplicated by expired-claim recovery while the heartbeat
    is healthy. The heartbeat stops before the worker persists its terminal
    outcome; a failed renewal is logged, not used to overwrite render state.
    """

    def __init__(self, scheduler: DerivativeScheduler, job_id: int, claim_token: str, interval_seconds: float):
        self._scheduler = scheduler
        self._job_id = job_id
        self._claim_token = claim_token
        self._interval = max(0.05, float(interval_seconds))
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"derivative-lease-{job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            # Renewal writes are bounded DB operations, but under contention a
            # in-flight renewal can outlast a short join. Wait generously so the
            # caller can safely persist terminal state without a heartbeat race.
            self._thread.join(timeout=max(2.0, self._interval + 2.0))

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._scheduler._renew_lease(self._job_id, self._claim_token)


class _DerivativeSkip(Exception):
    """Controlled terminal outcome for work that is no longer applicable."""

    def __init__(self, result_code: str, message: str):
        super().__init__(message)
        self.result_code = result_code
