"""Tests for the maintenance file-health API router.

Purpose:
Validate the GET/POST maintenance file-health endpoints and their response
envelope.

Guarantees:
Never-run, latest-run, manual-check, daemon-run, failed-run, and concurrent-run
responses keep the stable file-health contract used by the Maintenance page.

Run when:
Changing maintenance routes, IntegrityChecker.run_and_persist, file-health
response models, or the concurrent-run 409 envelope.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.integrity_checker import integrity_checker
from backend.metadata_store import _DB_LOCK, _connect, initialize_database
from backend.metadata_store.maintenance_store import insert_run


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path) -> None:
    initialize_database()


@pytest.fixture(autouse=True)
def _reset_checker() -> None:
    integrity_checker.is_running = False


FILE_HEALTH_ISSUES = {
    "missing_source_files",
    "generated_image_missing",
    "generated_image_abandoned",
    "metadata_mismatch",
    "file_index_ownership_mismatch",
    "orphaned_work_item",
    "generated_image_job_mismatch",
    "generated_image_expected_row_missing",
    "generated_image_queued_without_job",
    "generated_image_policy_deferred",
}
FILE_HEALTH_REPAIRS = {"repaired", "requeued", "failed", "skipped", "recovered", "unchanged"}


def _make_dummy_run(trigger: str = "manual", now: float | None = None) -> dict:
    if now is None:
        now = time.time()
    return {
        "trigger": trigger,
        "started_at": now - 10,
        "finished_at": now - 5,
        "status": "ok",
        "error": None,
        "issues": dict.fromkeys(FILE_HEALTH_ISSUES, 0),
        "repairs": dict.fromkeys(FILE_HEALTH_REPAIRS, 0),
    }


class TestGetFileHealth:
    def test_route_is_sync_so_sqlite_runs_in_fastapi_threadpool(self) -> None:
        from backend.maintenance import get_file_health

        assert inspect.iscoroutinefunction(get_file_health) is False

    def test_never_run_returns_null(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/file-health")
        assert resp.status_code == 200
        assert resp.json() == {"run": None}

    def test_after_manual_run(self, isolated_app: TestClient) -> None:
        isolated_app.post("/api/maintenance/file-health/check")
        resp = isolated_app.get("/api/maintenance/file-health")
        assert resp.status_code == 200
        data = resp.json()
        run = data["run"]
        assert run is not None
        assert set(run.keys()) == {
            "id",
            "trigger",
            "started_at",
            "finished_at",
            "status",
            "error",
            "issues",
            "repairs",
        }
        assert run["trigger"] == "manual"
        assert run["status"] == "ok"
        assert run["error"] is None
        assert set(run["issues"].keys()) == FILE_HEALTH_ISSUES
        assert set(run["repairs"].keys()) == FILE_HEALTH_REPAIRS

    def test_after_daemon_run(self, isolated_app: TestClient) -> None:
        now = time.time()
        with _DB_LOCK, _connect() as conn:
            insert_run(conn, _make_dummy_run(trigger="daemon", now=now))
        resp = isolated_app.get("/api/maintenance/file-health")
        assert resp.status_code == 200
        assert resp.json()["run"]["trigger"] == "daemon"


class TestPostFileHealthCheck:
    def test_creates_run(self, isolated_app: TestClient) -> None:
        resp = isolated_app.post("/api/maintenance/file-health/check")
        assert resp.status_code == 200
        data = resp.json()
        run = data["run"]
        assert run["status"] == "ok"
        assert run["trigger"] == "manual"
        assert run["error"] is None
        assert set(run["issues"].keys()) == FILE_HEALTH_ISSUES
        assert set(run["repairs"].keys()) == FILE_HEALTH_REPAIRS

    def test_concurrency_returns_409(self, isolated_app: TestClient) -> None:
        integrity_checker.is_running = True
        try:
            resp = isolated_app.post("/api/maintenance/file-health/check")
            assert resp.status_code == 409
            data = resp.json()
            assert data == {"run": None, "error": "check already running"}
        finally:
            integrity_checker.is_running = False

    def test_error_run(self, isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*args: object, **kwargs: object) -> dict:
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(integrity_checker, "run_all_checks", _raise)
        resp = isolated_app.post("/api/maintenance/file-health/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["status"] == "error"
        assert "simulated crash" in data["run"]["error"]
        assert data["run"]["issues"] == dict.fromkeys(FILE_HEALTH_ISSUES, 0)
        assert data["run"]["repairs"] == dict.fromkeys(FILE_HEALTH_REPAIRS, 0)
