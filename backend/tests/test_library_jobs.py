"""Phase 2 library job, stats, scan-all, and SSE coverage.

Purpose:
Cover durable library job state transitions, scan-all behavior, stats, and SSE
event formatting.

Guarantees:
Job counters, parent/child relationships, stale recovery, and event payloads
remain stable.

Run when:
Changing library job storage, scan-all orchestration, stats aggregation, or SSE
event payloads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend import scan_worker as catalog_service
from backend.library_events import event_payload, format_sse
from backend.metadata_store import (
    create_job,
    get_job,
    initialize_database,
    recover_stale_jobs,
    register_library,
    update_job_state,
)
from tests.conftest import create_test_png


def test_job_state_transitions_and_failure(isolated_metadata_db: Path, isolated_gallery_root: Path):
    library_id = int(register_library(isolated_gallery_root)["id"])
    succeeded = create_job("scan", library_id=library_id, progress_total=2)
    running = update_job_state(succeeded["id"], "running", progress_current=1, counters={"indexed": 1})
    assert running is not None
    assert running["state"] == "running"
    assert running["started_at"] is not None
    complete = update_job_state(
        succeeded["id"],
        "succeeded",
        progress_current=2,
        progress_total=2,
        counters={"indexed": 2},
    )
    assert complete is not None
    assert complete["state"] == "succeeded"
    assert complete["finished_at"] is not None
    assert complete["counters"] == {"indexed": 2}

    failed = create_job("rebuild", library_id=library_id)
    update_job_state(failed["id"], "running")
    failure = update_job_state(failed["id"], "failed", error="broken")
    assert failure is not None
    assert failure["state"] == "failed"
    assert failure["error"] == "broken"


def test_recover_stale_running_and_queued_jobs(isolated_metadata_db: Path, isolated_gallery_root: Path):
    library_id = int(register_library(isolated_gallery_root)["id"])
    running = create_job("scan", library_id=library_id)
    queued = create_job("scan", library_id=library_id)
    update_job_state(running["id"], "running")

    recovered = recover_stale_jobs()
    recovered_by_id = {job["id"]: job for job in recovered}

    assert set(recovered_by_id) == {running["id"]}
    assert get_job(running["id"])["state"] == "failed"
    assert get_job(running["id"])["error"] == "Interrupted by server restart"
    assert get_job(queued["id"])["state"] == "queued"
    assert get_job(queued["id"])["error"] is None


def test_scan_all_creates_parent_and_linked_children(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_app,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    create_test_png(first / "one.png")
    create_test_png(second / "two.png")
    first_id = int(register_library(first)["id"])
    second_id = int(register_library(second)["id"])

    response = isolated_app.post("/api/libraries/scan-all")
    assert response.status_code == 202
    body = response.json()
    assert body["count"] == 2
    assert len(body["child_job_ids"]) == 2
    parent = isolated_app.get(f"/api/jobs/{body['job_id']}").json()
    children = [isolated_app.get(f"/api/jobs/{job_id}").json() for job_id in body["child_job_ids"]]

    assert parent["type"] == "scan_all"
    assert parent["state"] == "running"
    assert parent["counters"] == {"total": 2, "succeeded": 0, "failed": 0, "coalesced": 0}
    assert {job["library_id"] for job in children} == {first_id, second_id}
    assert all(job["parent_job_id"] == parent["id"] for job in children)
    assert all(job["state"] == "queued" for job in children)
    assert all(job["trigger"] == "manual" for job in children)


def test_stats_and_job_history_endpoints(isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_app):
    create_test_png(isolated_gallery_root / "active.png", size=(20, 10))
    create_test_png(isolated_gallery_root / "offline.png", size=(30, 10))
    library_id = int(register_library(isolated_gallery_root)["id"])

    scan = isolated_app.post(f"/api/libraries/{library_id}/scan")
    assert scan.status_code == 202
    catalog_service.run_once()
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE assets SET offline = 1 WHERE path = ?",
            (str((isolated_gallery_root / "offline.png").resolve()),),
        )
    library_stats = isolated_app.get(f"/api/libraries/{library_id}/stats")
    gallery_stats = isolated_app.get("/api/stats")
    library_jobs = isolated_app.get(f"/api/libraries/{library_id}/jobs")
    all_jobs = isolated_app.get("/api/jobs")
    job = isolated_app.get(f"/api/jobs/{scan.json()['job_id']}")

    assert library_stats.status_code == 200
    assert library_stats.json() == {
        "photos": 1,
        "videos": 0,
        "total_assets": 1,
        "active_assets": 1,
        "offline_assets": 1,
        "usage_bytes": (isolated_gallery_root / "active.png").stat().st_size,
        "import_path_count": 1,
    }
    assert gallery_stats.json() == {
        "photos": 1,
        "videos": 0,
        "total_assets": 1,
        "active_assets": 1,
        "offline_assets": 1,
        "usage_bytes": (isolated_gallery_root / "active.png").stat().st_size,
        "library_count": 1,
    }
    assert library_jobs.json()[0]["type"] == "scan"
    assert all_jobs.json()[0]["id"] == scan.json()["job_id"]
    assert job.json()["state"] == "succeeded"


def test_sse_event_shape_and_frame(isolated_metadata_db: Path, isolated_gallery_root: Path):
    initialize_database()
    library_id = int(register_library(isolated_gallery_root)["id"])
    job = create_job("scan", library_id=library_id, message="Scan queued")
    payload = event_payload("job.updated", job)
    assert set(payload) == {
        "type",
        "job_id",
        "library_id",
        "state",
        "progress_current",
        "progress_total",
        "message",
        "error",
        "updated_at",
    }
    frame = format_sse(payload)
    assert frame.startswith(f"event: job.updated\nid: {job['id']}\ndata: {{")
    assert '"type":"job.updated"' in frame
    assert frame.endswith("\n\n")


def test_scan_progress_reports_active_job_id(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_app,
):
    """POST scan -> GET progress -> active_job_id is set while the job is active."""
    create_test_png(isolated_gallery_root / "image.png")
    library_id = int(register_library(isolated_gallery_root)["id"])

    scan = isolated_app.post(f"/api/libraries/{library_id}/scan")
    assert scan.status_code == 202
    job_id = scan.json()["job_id"]

    progress = isolated_app.get(f"/api/libraries/{library_id}/progress")

    assert progress.status_code == 200
    assert progress.json()["active_job_id"] == job_id


def test_scan_all_with_zero_libraries(isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_app):
    """POST /api/libraries/scan-all succeeds with no registered libraries."""
    response = isolated_app.post("/api/libraries/scan-all")
    assert response.status_code == 202
    body = response.json()
    assert body["count"] == 0
    assert body["child_job_ids"] == []

    parent = isolated_app.get(f"/api/jobs/{body['job_id']}").json()

    assert parent["type"] == "scan_all"
    assert parent["state"] == "succeeded"
    assert parent["message"] == "No libraries to update"
