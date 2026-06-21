from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "catalog_status"
SUMMARY_STATES = {
    "unknown",
    "offline",
    "needs_scan",
    "scanning",
    "indexing",
    "needs_update",
    "ready_with_issues",
    "ready",
    "error",
}


def _load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURE_ROOT / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _derive_summary_state(facts: dict[str, Any]) -> str:
    """Test oracle for the locked precedence in plan section 7.4."""
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
    if facts["metadata_pending_without_active_work"]:
        return "needs_update"
    if (
        not facts["metadata_disabled"]
        and facts["total_assets"] > 0
        and facts["ready_assets"] == 0
        and facts["failed_assets"] == facts["total_assets"]
    ):
        return "error"
    if facts["later_scan_failure"] or facts["current_metadata_failures"] > 0 or facts["availability"] == "degraded":
        return "ready_with_issues"
    return "ready"


def test_required_unified_status_fixtures_match_contract_v1() -> None:
    document = _load_fixture("unified_status_v1.json")

    assert document["contract_version"] == 1
    assert [fixture["name"] for fixture in document["fixtures"]] == [
        "initial_scan_queued",
        "scan_complete_metadata_indexing",
        "ready_with_unavailable_import_path",
        "failed_rebuild_with_usable_catalog",
    ]

    for fixture in document["fixtures"]:
        status = fixture["status"]
        assert set(status) == {
            "contract_version",
            "generated_at",
            "summary_state",
            "scope",
            "availability",
            "scan",
            "metadata",
            "issue_count",
            "issues",
            "latest_issue",
            "last_scan_at",
            "last_index_at",
        }
        assert status["contract_version"] == 1
        assert status["summary_state"] in SUMMARY_STATES
        assert isinstance(status["generated_at"], int)
        assert status["scope"]["kind"] in {"library", "path"}
        assert status["scope"]["path"] is None or isinstance(status["scope"]["path"], str)
        assert status["availability"]["state"] in {
            "unknown",
            "available",
            "degraded",
            "unavailable",
        }
        assert status["scan"]["state"] in {"never", "queued", "scanning", "complete", "failed"}
        assert status["metadata"]["state"] in {
            "disabled",
            "queued",
            "indexing",
            "needs_update",
            "complete",
            "failed",
        }
        assert status["issue_count"] == sum(status["issues"].values())

        metadata = status["metadata"]
        if metadata["total_assets"] is not None:
            assert metadata["not_ready_assets"] == (
                metadata["total_assets"] - metadata["ready_assets"] - metadata["failed_assets"]
            )
            assert metadata["not_ready_assets"] == sum(
                metadata[field] for field in ("queued_assets", "running_assets", "stale_assets", "idle_pending_assets")
            )

        for progress in (status["scan"]["progress_percent"], metadata["progress_percent"]):
            assert progress is None or 0 <= progress <= 100


def test_summary_precedence_vectors_cover_every_summary_state() -> None:
    document = _load_fixture("summary_precedence_v1.json")
    defaults = document["defaults"]
    cases = document["cases"]

    assert document["contract_version"] == 1
    assert len({case["name"] for case in cases}) == len(cases)
    assert {case["expected"] for case in cases} == SUMMARY_STATES

    for case in cases:
        assert set(case["overrides"]) <= set(defaults), case["name"]
        facts = defaults | case["overrides"]
        assert _derive_summary_state(facts) == case["expected"], case["name"]


@pytest.mark.parametrize(
    ("fixture_name", "expected_summary"),
    [
        ("initial_scan_queued", "scanning"),
        ("scan_complete_metadata_indexing", "indexing"),
        ("ready_with_unavailable_import_path", "ready_with_issues"),
        ("failed_rebuild_with_usable_catalog", "ready_with_issues"),
    ],
)
def test_required_fixture_summary_states(fixture_name: str, expected_summary: str) -> None:
    document = _load_fixture("unified_status_v1.json")
    fixture = next(item for item in document["fixtures"] if item["name"] == fixture_name)

    assert fixture["status"]["summary_state"] == expected_summary
