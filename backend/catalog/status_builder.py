"""Build semantic catalog status from scope facts."""

from __future__ import annotations

from typing import Literal, TypedDict

SummaryState = Literal[
    "unknown",
    "offline",
    "needs_scan",
    "scanning",
    "indexing",
    "needs_update",
    "ready_with_issues",
    "ready",
    "error",
]


class PrecedenceFacts(TypedDict):
    """Normalized facts consumed by the contract-v1 precedence function."""

    resolved: bool
    availability: Literal["unknown", "available", "degraded", "unavailable"]
    active_catalog_job_state: Literal["queued", "running", "cancelled"] | None
    active_metadata_state: Literal["queued", "running", "cancelled"] | None
    latest_covering_scan_failed: bool
    prior_successful_covering_scan: bool
    has_failed_scan_attempt: bool
    metadata_pending_without_active_work: bool
    total_assets: int
    ready_assets: int
    failed_assets: int
    later_scan_failure: bool
    current_metadata_failures: int
    metadata_disabled: bool


def derive_summary_state(facts: PrecedenceFacts) -> SummaryState:
    """Apply the locked catalog status precedence for contract version 1."""
    if not facts["resolved"]:
        return "unknown"
    if facts["availability"] == "unavailable":
        return "offline"
    if facts["active_catalog_job_state"] in {"queued", "running"}:
        return "scanning"
    if facts["active_metadata_state"] in {"queued", "running"}:
        return "indexing"
    if facts["latest_covering_scan_failed"] and not facts["prior_successful_covering_scan"]:
        return "error"
    if not facts["prior_successful_covering_scan"] and not facts["has_failed_scan_attempt"]:
        return "needs_scan"
    if (
        not facts["metadata_disabled"]
        and facts["total_assets"] > 0
        and facts["ready_assets"] == 0
        and facts["failed_assets"] == facts["total_assets"]
    ):
        return "error"
    if facts["metadata_pending_without_active_work"]:
        return "needs_update"
    if (
        facts["later_scan_failure"]
        or facts["current_metadata_failures"] > 0
        or facts["availability"] == "degraded"
    ):
        return "ready_with_issues"
    return "ready"
