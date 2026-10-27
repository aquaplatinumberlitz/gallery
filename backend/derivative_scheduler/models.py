"""Summary records and type aliases for derivative reconciliation and repair."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

ReconcileCandidate = tuple[int, int, int]
PendingCapacity = tuple[dict[str, Any], int, bool]


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


@dataclass
class DerivativeRepairSummary:
    """Bounded counters from one exact derivative consistency repair pass."""

    issues_considered: int = 0
    jobs_created: int = 0
    already_active: int = 0
    terminal_skipped: int = 0
    terminal_failed: int = 0
    unchanged: int = 0
