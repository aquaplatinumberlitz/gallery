"""``DerivativeScheduler``: durable priority scheduler for image derivative generation."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future
from typing import Any

from ..config import DERIVATIVE_QUOTA_BYTES, DERIVATIVE_RECONCILE_ENABLED, DERIVATIVE_WORKER_COUNT
from .capacity import CapacityMixin
from .execution import JobExecutionMixin
from .lifecycle import LifecycleMixin
from .lookup import LookupMixin
from .maintenance import CacheMaintenanceMixin
from .reconcile import ReconcileMixin
from .recovery import RecoveryMixin
from .scheduling import SchedulingMixin
from .status import StatusMixin
from .supersede import SupersedeMixin


class DerivativeScheduler(
    LifecycleMixin,
    CapacityMixin,
    SchedulingMixin,
    SupersedeMixin,
    LookupMixin,
    ReconcileMixin,
    StatusMixin,
    CacheMaintenanceMixin,
    RecoveryMixin,
    JobExecutionMixin,
):
    """Run durable, coalesced derivative jobs using priority worker threads.

    Behaviour is split across cohesive mixins; this class owns construction and shared state.
    """

    def __init__(self, worker_count: int = DERIVATIVE_WORKER_COUNT, quota_bytes: int = DERIVATIVE_QUOTA_BYTES):
        """Configure worker concurrency and the persisted-file quota."""
        self.worker_count = max(1, min(worker_count, 8))
        self.quota_bytes = max(0, quota_bytes)
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._start_condition = threading.Condition(self._lifecycle_lock)
        self._start_in_progress = False
        self._stop_in_progress = False
        self._active_stop_calls = 0
        self._file_lock = threading.RLock()
        self._generating_paths: set[str] = set()
        self._served_paths: set[str] = set()
        self._deferred_unlinks: set[str] = set()
        self._pending_touches: dict[str, Future] = {}
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
        self._eviction_lock = threading.RLock()
        self._generation = 0
