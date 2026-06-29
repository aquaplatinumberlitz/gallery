"""Tests for the maintenance runtime diagnostics API.

Purpose:
Validate GET /api/maintenance/runtime returns global runtime diagnostics and
metadata lifecycle counters without requiring any library to exist.

Guarantees:
Endpoint is read-only, returns 200 with global_runtime and metadata_lifecycle
keys. Global runtime includes catalog/metadata worker counts, queue depths,
watcher fields, and scheduled refresh field.

Run when:
Maintenance runtime response fields or global diagnostic counters change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import _DB_LOCK, _connect, create_library, initialize_database
from tests.conftest import create_test_png


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path) -> None:
    initialize_database()


class TestGetMaintenanceRuntime:
    def test_returns_200_without_any_library(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        assert resp.status_code == 200

    def test_response_has_global_runtime(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        assert "global_runtime" in data

    def test_response_has_metadata_lifecycle(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        assert "metadata_lifecycle" in data

    def test_global_runtime_includes_expected_fields(self, isolated_app: TestClient) -> None:
        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        gr = data["global_runtime"]
        assert "catalog_worker_count" in gr
        assert "catalog_active_jobs" in gr
        assert "catalog_queue_depth" in gr
        assert "watcher_enabled" in gr
        assert "watcher_healthy" in gr
        assert "watcher_issue" in gr
        assert "scheduled_reconciliation_enabled" in gr
        assert "metadata_worker_count" in gr
        assert "metadata_queue_depth" in gr
        assert "metadata_staged_queue_depth" in gr
        assert "derivative_active_jobs" in gr
        assert "derivative_queue_depth" in gr

    def test_global_runtime_includes_derivative_job_counts(
        self, isolated_app: TestClient, isolated_gallery_root: Path
    ) -> None:
        image = isolated_gallery_root / "one.png"
        create_test_png(image)
        library = create_library([isolated_gallery_root], name="Derivative counts")
        with _DB_LOCK, _connect() as conn:
            asset = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size, indexed_at,
                  metadata_state, offline
                ) VALUES (?, ?, ?, ?, 'image', ?, ?, 0, 'done', 0)
                """,
                (
                    library["id"],
                    str(image),
                    str(image.parent),
                    image.name,
                    image.stat().st_mtime_ns,
                    image.stat().st_size,
                ),
            )
            first_derivative = conn.execute(
                """
                INSERT INTO asset_derivatives (
                  asset_id, kind, variant, source_mtime_ns, source_size, status,
                  max_long_edge, format, quality
                ) VALUES (?, 'thumbnail', 'thumbnail_512_webp_80', ?, ?, 'running', 512, 'webp', 80)
                """,
                (int(asset.lastrowid), image.stat().st_mtime_ns, image.stat().st_size),
            )
            second_derivative = conn.execute(
                """
                INSERT INTO asset_derivatives (
                  asset_id, kind, variant, source_mtime_ns, source_size, status,
                  max_long_edge, format, quality
                ) VALUES (?, 'preview', 'preview_1440_webp_85', ?, ?, 'queued', 1440, 'webp', 85)
                """,
                (int(asset.lastrowid), image.stat().st_mtime_ns, image.stat().st_size),
            )
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, state) VALUES (?, 'running')",
                (int(first_derivative.lastrowid),),
            )
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, state) VALUES (?, 'queued')",
                (int(second_derivative.lastrowid),),
            )

        resp = isolated_app.get("/api/maintenance/runtime")
        data = resp.json()
        gr = data["global_runtime"]
        assert gr["derivative_active_jobs"] == 1
        assert gr["derivative_queue_depth"] == 1
