"""Unified catalog status fixture and schema contract tests.

Purpose:
Validate shared status fixtures, JSON schema envelopes, and summary precedence
vectors used by backend and frontend.

Guarantees:
Catalog status contract version 1 remains serializable, schema-valid, and
stable across summary-state edge cases.

Run when:
Changing status schema fields, summary precedence, fixtures, or frontend status
contract types.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from backend.metadata_store.status_store import PrecedenceFacts, derive_summary_state

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "catalog_status"
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
TIMESTAMP_MS_MINIMUM = 10_000_000_000
FIXTURE_SUMMARIES = {
    "initial_scan_queued": "scanning",
    "scan_complete_metadata_indexing": "indexing",
    "ready_with_unavailable_import_path": "ready_with_issues",
    "failed_rebuild_with_usable_catalog": "ready_with_issues",
    "all_import_paths_unavailable": "offline",
    "scan_complete_metadata_stale_without_worker": "needs_update",
    "metadata_disabled_scan_complete": "ready",
    "empty_scanned_scope": "ready",
}


def _load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURE_ROOT / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _global_runtime() -> dict[str, Any]:
    return {
        "catalog_worker_count": 1,
        "catalog_alive_workers": 1,
        "catalog_active_jobs": 0,
        "catalog_queue_depth": 0,
        "catalog_supervisor_alive": True,
        "catalog_supervisor_last_check_at": None,
        "catalog_supervisor_last_recovered_jobs": 0,
        "catalog_supervisor_failures": 0,
        "metadata_worker_count": 2,
        "metadata_active_jobs": 0,
        "metadata_queue_depth": 0,
        "metadata_staged_queue_depth": 0,
        "watcher_enabled": True,
        "watcher_healthy": True,
        "watcher_issue": None,
        "scheduled_reconciliation_enabled": True,
        "derivative_configured_worker_count": 3,
        "derivative_worker_count": 3,
        "derivative_active_jobs": 0,
        "derivative_queue_depth": 0,
        "derivative_failed_jobs": 0,
        "derivative_skipped_jobs": 0,
        "derivative_stale_running_jobs": 0,
        "derivative_oldest_running_age_seconds": None,
        "derivative_reconcile_enabled": True,
        "derivative_reconcile_running": False,
        "derivative_last_reconcile_started_at": None,
        "derivative_last_reconcile_completed_at": None,
        "derivative_last_reconcile_status": None,
        "derivative_last_reconcile_created_jobs": 0,
    }


def _assert_timestamp_ms(value: int | None) -> None:
    assert value is None or (isinstance(value, int) and value > TIMESTAMP_MS_MINIMUM)


def test_unified_status_fixtures_match_shared_schema_and_invariants() -> None:
    document = _load_fixture("unified_status_v1.json")
    schema = _load_fixture("schema_v1.json")
    validator = Draft202012Validator(schema)

    assert document["contract_version"] == 1
    assert [fixture["name"] for fixture in document["fixtures"]] == list(FIXTURE_SUMMARIES)

    for fixture in document["fixtures"]:
        status = fixture["status"]
        validator.validate(status)
        assert status["summary_state"] == FIXTURE_SUMMARIES[fixture["name"]]

        scope = status["scope"]
        assert isinstance(scope["library_id"], int)
        assert isinstance(scope["import_path_count"], int)

        availability = status["availability"]
        assert availability["available_paths"] <= availability["total_paths"]

        scan = status["scan"]
        assert scan["operation"] in {"scan", "rebuild", None}
        assert scan["trigger"] in {"initial", "manual", "watcher", "scheduled", "startup", None}
        for field in ("active_job_id", "completed_units", "total_units"):
            assert scan[field] is None or isinstance(scan[field], int)

        metadata = status["metadata"]
        assert isinstance(metadata["global_active_outside_scope"], bool)
        if metadata["total_assets"] is None:
            assert metadata["state"] == "disabled"
            assert all(
                metadata[field] is None
                for field in (
                    "ready_assets",
                    "not_ready_assets",
                    "queued_assets",
                    "running_assets",
                    "stale_assets",
                    "idle_pending_assets",
                    "failed_assets",
                    "progress_percent",
                )
            )
        else:
            assert metadata["not_ready_assets"] == (
                metadata["total_assets"] - metadata["ready_assets"] - metadata["failed_assets"]
            )
            assert metadata["not_ready_assets"] == sum(
                metadata[field] for field in ("queued_assets", "running_assets", "stale_assets", "idle_pending_assets")
            )

        assert status["issue_count"] == sum(status["issues"].values())
        latest_issue = status["latest_issue"]
        if status["issue_count"] == 0:
            assert latest_issue is None
        else:
            assert latest_issue is not None
            assert latest_issue["source"] in status["issues"]
            assert status["issues"][latest_issue["source"]] > 0
            assert latest_issue["path"] is None or isinstance(latest_issue["path"], str)
            assert isinstance(latest_issue["message"], str) and latest_issue["message"]
            _assert_timestamp_ms(latest_issue["updated_at"])

        _assert_timestamp_ms(status["generated_at"])
        _assert_timestamp_ms(status["last_scan_at"])
        _assert_timestamp_ms(status["last_index_at"])


def test_response_envelopes_and_global_runtime_match_shared_schema() -> None:
    fixture = _load_fixture("unified_status_v1.json")["fixtures"][0]["status"]
    validator = Draft202012Validator(_load_fixture("schema_v1.json"))
    runtime = _global_runtime()

    envelope = {"contract_version": 1, "status": fixture, "global_runtime": runtime, "metadata_lifecycle": None}
    batch = {
        "contract_version": 1,
        "generated_at": fixture["generated_at"],
        "items": [{"library_id": fixture["scope"]["library_id"], "status": fixture}],
        "global_runtime": runtime,
        "metadata_lifecycle": None,
    }

    validator.validate(envelope)
    validator.validate(batch)


def test_summary_precedence_vectors_cover_every_summary_state() -> None:
    document = _load_fixture("summary_precedence_v1.json")
    defaults = document["defaults"]
    cases = document["cases"]

    assert document["contract_version"] == 1
    assert len({case["name"] for case in cases}) == len(cases)
    assert {case["expected"] for case in cases} == SUMMARY_STATES

    for case in cases:
        assert set(case["overrides"]) <= set(defaults), case["name"]
        facts = cast(PrecedenceFacts, defaults | case["overrides"])
        assert derive_summary_state(facts) == case["expected"], case["name"]


@pytest.mark.parametrize(("fixture_name", "expected_summary"), FIXTURE_SUMMARIES.items())
def test_required_fixture_summary_states(fixture_name: str, expected_summary: str) -> None:
    document = _load_fixture("unified_status_v1.json")
    fixture = next(item for item in document["fixtures"] if item["name"] == fixture_name)
    assert fixture["status"]["summary_state"] == expected_summary


def test_empty_scanned_scope_has_complete_progress() -> None:
    document = _load_fixture("unified_status_v1.json")
    status = next(item["status"] for item in document["fixtures"] if item["name"] == "empty_scanned_scope")

    assert status["scan"]["state"] == "complete"
    assert status["metadata"]["total_assets"] == 0
    assert status["metadata"]["progress_percent"] == 100


def test_indexing_with_issues_preserves_indexing_summary() -> None:
    document = _load_fixture("unified_status_v1.json")
    status = next(item["status"] for item in document["fixtures"] if item["name"] == "scan_complete_metadata_indexing")

    assert status["summary_state"] == "indexing"
    assert status["issue_count"] > 0
