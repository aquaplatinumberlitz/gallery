"""Per-library derivative coverage and quota status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DERIVATIVE_VARIANTS
from ..metadata_store import _connect
from ._common import _ensure_database


class StatusMixin:
    """Library derivative status read model for ``DerivativeScheduler``."""

    def library_status(self, library_id: int) -> dict[str, Any]:
        """Return warm coverage and quota utilization for one library."""
        _ensure_database()
        configured_variant_specs = [
            (kind, str(variant["name"]), int(variant["max_long_edge"]))
            for kind, variants in DERIVATIVE_VARIANTS.items()
            for variant in variants
        ]
        configured_variants = [(kind, variant) for kind, variant, _max_long_edge in configured_variant_specs]
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
        variant_statuses = [
            {
                "kind": kind,
                "variant": variant,
                "max_long_edge": max_long_edge,
                "ready_derivatives": 0,
                "expected_derivatives": 0,
                "desired_derivatives": 0,
                "missing_derivatives": 0,
                "queued_derivatives": 0,
                "running_derivatives": 0,
                "failed_derivatives": 0,
                "deferred_derivatives": 0,
            }
            for kind, variant, max_long_edge in configured_variant_specs
        ]
        by_variant = {(str(item["kind"]), str(item["variant"])): item for item in variant_statuses}
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
                    SELECT d.kind, d.variant, d.status, d.cache_path, d.byte_size,
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
            library_used = 0
            evicted = 0
            queued_without_job_by_kind = dict.fromkeys(DERIVATIVE_VARIANTS, 0)
            for kind, configured_kind_variants in DERIVATIVE_VARIANTS.items():
                by_kind[kind]["expected_derivatives"] = total_assets * len(configured_kind_variants)
                by_kind[kind]["desired_derivatives"] = (
                    total_assets * len(configured_kind_variants) if warm_enabled else 0
                )
            for values in variant_statuses:
                values["expected_derivatives"] = total_assets
                values["desired_derivatives"] = total_assets if warm_enabled else 0
            for row in derivative_rows:
                kind = str(row["kind"])
                variant_values = by_variant[(kind, str(row["variant"]))]
                if row["status"] == "ready" and row["cache_path"] and Path(row["cache_path"]).is_file():
                    ready += 1
                    library_used += row["byte_size"] or 0
                    by_kind[kind]["ready_derivatives"] += 1
                    variant_values["ready_derivatives"] += 1
                elif row["status"] == "queued":
                    by_kind[kind]["queued_derivatives"] += 1
                    variant_values["queued_derivatives"] += 1
                    if row["latest_job_state"] not in {"queued", "running"}:
                        queued_without_job_by_kind[kind] += 1
                elif row["status"] == "running":
                    by_kind[kind]["running_derivatives"] += 1
                    variant_values["running_derivatives"] += 1
                    if row["latest_job_state"] != "running":
                        queued_without_job_by_kind[kind] += 1
                elif row["status"] == "failed":
                    by_kind[kind]["failed_derivatives"] += 1
                    variant_values["failed_derivatives"] += 1
                elif row["status"] == "deferred_capacity":
                    by_kind[kind]["deferred_derivatives"] += 1
                    variant_values["deferred_derivatives"] += 1
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
            global_used = int(
                conn.execute(
                    "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
                ).fetchone()[0]
            )
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
        for values in variant_statuses:
            values["missing_derivatives"] = max(
                0, int(values["expected_derivatives"]) - int(values["ready_derivatives"])
            )
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
            "variants": variant_statuses,
            "library_used_bytes": library_used,
            "quota_bytes": self.quota_bytes,
            "quota_used_bytes": global_used,
            "quota_utilization": global_used / self.quota_bytes if self.quota_bytes else 0.0,
            "queued_jobs": job_counts["queued"],
            "running_jobs": job_counts["running"],
            "failed_jobs": job_counts["failed"],
            "skipped_jobs": job_counts["skipped"],
            "configured_worker_count": self.worker_count,
            "alive_worker_count": alive_workers,
            "worker_healthy": alive_workers > 0,
            "oldest_running_age_seconds": oldest_running_age_seconds,
        }
