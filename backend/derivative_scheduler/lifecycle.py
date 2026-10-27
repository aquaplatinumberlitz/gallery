"""Worker, supervisor, and reconciler thread lifecycle for the derivative scheduler."""

from __future__ import annotations

import threading
import time
from contextlib import suppress
from typing import Any

from ..catalog_maintenance_gate import maintenance_producer
from ..config import (
    DERIVATIVE_RECONCILE_ENABLED,
    DERIVATIVE_RECONCILE_INTERVAL_SECONDS,
    DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS,
)
from ._common import (
    _ensure_database,
    logger,
)


class LifecycleMixin:
    """Start/stop coordination and runtime status for ``DerivativeScheduler``.

    Relies on the state created by ``DerivativeScheduler.__init__``.
    """

    @maintenance_producer
    def start(self) -> None:
        """Start workers and recover jobs interrupted by a prior process.

        A restart after an incomplete stop must not permanently refuse to restore
        missing worker slots because a stale thread object remains in ``_threads``.
        Dead thread objects are pruned first, then one worker thread is created per
        missing slot so the configured worker count is restored exactly.

        Each invocation captures a request generation at entry.  If ``stop()``
        increments the scheduler generation before startup finishes, the cancelled
        start exits without launching any thread.
        """
        with self._start_condition:
            if self._stop_in_progress:
                return
            my_generation = self._generation
            while self._start_in_progress:
                self._start_condition.wait()
                if self._stop_in_progress or my_generation != self._generation:
                    return
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            cold_start = not self._threads
            self._start_in_progress = True
        try:
            if cold_start:
                _ensure_database()
                self._reconcile_queued_jobs()
                self._recover_running_jobs()
            with self._start_condition:
                if self._stop_in_progress or my_generation != self._generation:
                    self._start_in_progress = False
                    self._start_condition.notify_all()
                    return
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
        """Stop workers within one absolute bounded shutdown deadline.

        Sets the stop event so no new claims begin, wakes all workers, then joins
        each worker (and the supervisor/reconciler) within the same absolute
        timeout. Records whether shutdown completed cleanly so callers can detect
        an incomplete stop that left in-flight renders running.

        Uses an absolute monotonic deadline so that a hung cold-start recovery
        cannot make shutdown unbounded.  After joining known threads, waits for
        any in-progress ``start()`` to acknowledge cancellation against the same
        deadline, then snapshots fresh references for final bookkeeping.
        """
        deadline = time.monotonic() + DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS
        with self._start_condition:
            self._active_stop_calls += 1
            self._stop_in_progress = True
            threads = list(self._threads)
            supervisor = self._supervisor_thread
            reconciler = self._reconciler_thread
            self._generation += 1
            self._stop_event.set()
            self._reconciler_stop_event.set()
            self._wake_event.set()
        clean = True
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                clean = False
                break
            with suppress(RuntimeError):
                thread.join(timeout=remaining)
            if thread.is_alive():
                clean = False
        if supervisor is not None:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                with suppress(RuntimeError):
                    supervisor.join(timeout=remaining)
                if supervisor.is_alive():
                    clean = False
            elif supervisor.is_alive():
                clean = False
        if reconciler is not None:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                with suppress(RuntimeError):
                    reconciler.join(timeout=remaining)
                if reconciler.is_alive():
                    clean = False
            elif reconciler.is_alive():
                clean = False
        # Wait for in-progress start to acknowledge (bounded by deadline)
        with self._start_condition:
            while self._start_in_progress:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    clean = False
                    break
                self._start_condition.wait(timeout=remaining)
        # Take a fresh snapshot after acknowledgment
        with self._start_condition:
            self._threads = [t for t in self._threads if t.is_alive()]
            self._supervisor_thread = (
                self._supervisor_thread if self._supervisor_thread and self._supervisor_thread.is_alive() else None
            )
            self._reconciler_thread = (
                self._reconciler_thread if self._reconciler_thread and self._reconciler_thread.is_alive() else None
            )
            self._reconcile_status["running"] = bool(self._reconciler_thread)
            if self._threads or self._supervisor_thread is not None or self._reconciler_thread is not None:
                clean = False
            self._shutdown_clean = clean
            self._active_stop_calls -= 1
            self._stop_in_progress = self._active_stop_calls > 0
            self._start_condition.notify_all()

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
        from ..metadata_store import list_libraries

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
