"""Desired-state derivative reconciliation for libraries, scopes, and asset sets."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..catalog_maintenance_gate import maintenance_producer
from ..config import (
    DERIVATIVE_RECONCILE_BATCH_SIZE,
    DERIVATIVE_RECONCILE_YIELD_SECONDS,
    DERIVATIVE_VARIANTS,
)
from ..metadata_store import _connect
from ._common import (
    _CAPACITY_DEFERRED_AUTOMATIC_REASONS,
    _ensure_database,
)
from .models import DerivativeReconcileSummary, PendingCapacity, ReconcileCandidate


class ReconcileMixin:
    """Reconciliation of configured derivative variants for ``DerivativeScheduler``."""

    @staticmethod
    def _configured_variants(kinds: Sequence[str] | None) -> list[tuple[str, dict[str, Any]]]:
        """Validate and flatten the configured variants requested by a caller."""
        selected_kinds = list(DERIVATIVE_VARIANTS) if kinds is None else list(kinds)
        unknown = next((kind for kind in selected_kinds if kind not in DERIVATIVE_VARIANTS), None)
        if unknown is not None:
            raise ValueError(f"Unsupported derivative kind: {unknown}")
        return [(kind, variant) for kind in selected_kinds for variant in DERIVATIVE_VARIANTS[kind]]

    def _select_reconcile_assets(
        self,
        *,
        library_id: int | None,
        scope_path: str | None,
        asset_ids: Sequence[int] | None,
        respect_warm_policy: bool,
    ) -> list[sqlite3.Row]:
        """Select the active image assets belonging to one reconciliation scope."""
        with _connect() as conn:
            scope_clause = ""
            scope_params: list[Any] = []
            if scope_path is not None:
                from ..metadata_store import get_library_for_path
                from ..metadata_store.path_utils import path_scope_sql

                library = get_library_for_path(scope_path)
                if library is None:
                    raise KeyError(scope_path)
                library_id = int(library["id"])
                path = str(Path(scope_path).resolve())
                scope_clause, scope_params = path_scope_sql(path, column="a.path", leading_and=True)
            if library_id is not None:
                library = conn.execute("SELECT warm_enabled FROM libraries WHERE id = ?", (library_id,)).fetchone()
                if library is None:
                    raise KeyError(library_id)
                if respect_warm_policy and not bool(library["warm_enabled"]):
                    return []
                where = "a.library_id = ?"
                params: list[Any] = [library_id, *scope_params]
            else:
                requested_ids = [int(asset_id) for asset_id in asset_ids or ()]
                if not requested_ids:
                    return []
                where = f"a.id IN ({', '.join('?' for _ in requested_ids)})"
                if respect_warm_policy:
                    where += " AND EXISTS (SELECT 1 FROM libraries l WHERE l.id = a.library_id AND l.warm_enabled = 1)"
                params = [*requested_ids, *scope_params]
            return conn.execute(
                f"""
                SELECT a.id, a.path, a.mtime_ns, a.size
                FROM assets a
                WHERE {where} AND a.type = 'image' AND a.deleted_at IS NULL AND a.offline = 0
                {scope_clause}
                ORDER BY a.id
                """,
                params,
            ).fetchall()

    @staticmethod
    def _validated_reconcile_candidates(
        assets: Sequence[sqlite3.Row],
        variant_count: int,
        summary: DerivativeReconcileSummary,
    ) -> list[ReconcileCandidate]:
        """Validate on-disk source identity before scheduling derivative candidates."""
        candidates: list[ReconcileCandidate] = []
        for asset in assets:
            try:
                stat = Path(asset["path"]).stat()
            except OSError:
                summary.source_unavailable += variant_count
                continue
            if (
                asset["mtime_ns"] is None
                or asset["size"] is None
                or int(asset["mtime_ns"]) != stat.st_mtime_ns
                or int(asset["size"]) != stat.st_size
            ):
                summary.source_unavailable += variant_count
                continue
            candidates.append((int(asset["id"]), stat.st_mtime_ns, stat.st_size))
        return candidates

    @staticmethod
    def _record_reconcile_outcome(summary: DerivativeReconcileSummary, outcome: str) -> None:
        """Account for one coalescing outcome in the public reconciliation summary."""
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
        elif outcome == "capacity_needed_created":
            summary.created_derivative_rows += 1
            summary.deferred_capacity += 1
        elif outcome in {"capacity_needed", "deferred_capacity"}:
            summary.deferred_capacity += 1

    def _coalesce_reconcile_candidates(
        self,
        candidates: Sequence[ReconcileCandidate],
        variants: Sequence[tuple[str, dict[str, Any]]],
        *,
        priority: int,
        retry_failed: bool,
        reason: str,
        summary: DerivativeReconcileSummary,
    ) -> list[PendingCapacity]:
        """Revalidate identities transactionally and collect capacity-dependent work."""
        pending_capacity: list[PendingCapacity] = []
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            estimated_bytes = self._estimate_new_derivative_bytes(conn)
            for asset_id, mtime_ns, size in candidates:
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
                    coalesce_args: dict[str, Any] = {
                        "asset_id": asset_id,
                        "kind": kind,
                        "variant": str(variant["name"]),
                        "source_mtime_ns": mtime_ns,
                        "source_size": size,
                        "max_long_edge": int(variant["max_long_edge"]),
                        "quality": int(variant["quality"]),
                        "format": "webp",
                        "priority": priority,
                        "retry_failed": retry_failed,
                        "deferrable": True,
                        "reconsider_deferred_capacity": reason not in _CAPACITY_DEFERRED_AUTOMATIC_REASONS,
                        "estimated_bytes": estimated_bytes,
                    }
                    _derivative_id, outcome = self._coalesce_derivative_job(conn, **coalesce_args)
                    if outcome in {"capacity_needed", "capacity_needed_created"}:
                        pending_capacity.append((coalesce_args, estimated_bytes, outcome == "capacity_needed_created"))
                    else:
                        self._record_reconcile_outcome(summary, outcome)
        return pending_capacity

    def _apply_reconcile_capacity_policy(
        self,
        pending_capacity: Sequence[PendingCapacity],
        summary: DerivativeReconcileSummary,
        cancel_event: threading.Event | None,
    ) -> None:
        """Reserve quota for deferred candidates and account for final outcomes."""
        for coalesce_args, estimated_bytes, created_pending in pending_capacity:
            pending_outcome = "capacity_needed_created" if created_pending else "capacity_needed"
            if cancel_event is not None and cancel_event.is_set():
                self._record_reconcile_outcome(summary, pending_outcome)
                continue
            if not self._reserve_capacity(estimated_bytes):
                self._record_reconcile_outcome(summary, pending_outcome)
                continue
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                _derivative_id, outcome = self._coalesce_derivative_job(conn, **coalesce_args)
            if created_pending and outcome == "requeued":
                outcome = "created"
            self._record_reconcile_outcome(summary, outcome)

    @maintenance_producer
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
        assets = self._select_reconcile_assets(
            library_id=library_id,
            scope_path=scope_path,
            asset_ids=asset_ids,
            respect_warm_policy=respect_warm_policy,
        )
        summary = DerivativeReconcileSummary(assets_considered=len(assets))
        candidates = self._validated_reconcile_candidates(assets, len(variants), summary)
        summary.desired_derivatives = len(candidates) * len(variants)

        for offset in range(0, len(candidates), DERIVATIVE_RECONCILE_BATCH_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                break
            jobs_before = summary.created_jobs
            with self._eviction_lock:
                pending_capacity = self._coalesce_reconcile_candidates(
                    candidates[offset : offset + DERIVATIVE_RECONCILE_BATCH_SIZE],
                    variants,
                    priority=priority,
                    retry_failed=retry_failed,
                    reason=reason,
                    summary=summary,
                )
                self._apply_reconcile_capacity_policy(pending_capacity, summary, cancel_event)
            if summary.created_jobs > jobs_before:
                self._wake_event.set()
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
