"""Durable priority scheduler for image derivative generation.

The implementation is split into cohesive modules (see ``core.DerivativeScheduler``); this package
re-exports the public names so ``from backend.derivative_scheduler import scheduler`` and every other
historical import path keep working.

Module-level settings (for example ``DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS``) are read by the module that
uses them and are deliberately *not* re-exported here: patching a re-exported copy would silently have no
effect.
"""

from __future__ import annotations

from ._common import derivative_variant as derivative_variant
from .core import DerivativeScheduler as DerivativeScheduler
from .execution import _DerivativeSkip as _DerivativeSkip
from .execution import _LeaseHeartbeat as _LeaseHeartbeat
from .models import DerivativeReconcileSummary as DerivativeReconcileSummary
from .models import DerivativeRepairSummary as DerivativeRepairSummary
from .models import PendingCapacity as PendingCapacity
from .models import ReconcileCandidate as ReconcileCandidate

scheduler = DerivativeScheduler()
