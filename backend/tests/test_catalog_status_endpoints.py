"""Catalog status endpoint contract coverage.

Purpose:
Exercise `/api/libraries/{id}/status` and `/api/libraries/status` with real
library/job/index state.

Guarantees:
Status endpoints return contract-v1 envelopes with scoped counts, availability,
runtime fields, and validation errors intact.

Run when:
Changing library status endpoints, status aggregation SQL, or schema validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.metadata_store import (
    create_job,
    index_file,
    register_library,
    update_job_state,
    update_library,
)
from tests.conftest import create_test_png

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "catalog_status"


def _enable_metadata_status(monkeypatch) -> None:
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)


def _schema_validator() -> Draft202012Validator:
    with (FIXTURE_ROOT / "schema_v1.json").open(encoding="utf-8") as schema_file:
        return Draft202012Validator(json.load(schema_file))


def test_library_status_endpoint_reports_initial_scan_queued(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "photos"
    root.mkdir()

    created = isolated_app.post(
        "/api/libraries",
        json={"name": "Photos", "import_paths": [str(root)]},
    )
    assert created.status_code == 201
    library = created.json()

    response = isolated_app.get(f"/api/libraries/{library['id']}/status")

    assert response.status_code == 200
    body = response.json()
    _schema_validator().validate(body)
    status = body["status"]
    assert status["summary_state"] == "scanning"
    assert status["scope"] == {
        "kind": "library",
        "library_id": library["id"],
        "path": None,
        "import_path_count": 1,
    }
    assert status["scan"]["state"] == "queued"
    assert status["scan"]["operation"] == "scan"
    assert status["scan"]["trigger"] == "initial"
    assert status["scan"]["active_job_id"] == library["initial_scan_job_id"]
    assert status["metadata"]["state"] == "queued"
    assert body["global_runtime"]["catalog_queue_depth"] == 1


def test_library_status_batch_uses_contract_envelope(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    first.mkdir()
    second.mkdir()
    first_id = int(register_library(first)["id"])
    second_id = int(register_library(second)["id"])

    response = isolated_app.get("/api/libraries/status")

    assert response.status_code == 200
    body = response.json()
    _schema_validator().validate(body)
    assert body["contract_version"] == 1
    assert [item["library_id"] for item in body["items"]] == [first_id, second_id]
    assert isinstance(body["global_runtime"]["scheduled_reconciliation_enabled"], bool)


def test_scoped_status_counts_descendants_without_sibling_prefix_leak(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "registered"
    album = root / "album"
    sibling = root / "album2"
    album.mkdir(parents=True)
    sibling.mkdir()
    album_image = album / "a.png"
    sibling_image = sibling / "b.png"
    create_test_png(album_image)
    create_test_png(sibling_image)
    library_id = int(register_library(root)["id"])
    for image in (album_image, sibling_image):
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, None, None)

    response = isolated_app.get(
        f"/api/libraries/{library_id}/status",
        params={"scope_path": str(album)},
    )

    assert response.status_code == 200
    status = response.json()["status"]
    assert status["scope"]["kind"] == "path"
    assert status["scope"]["path"] == str(album.resolve())
    assert status["availability"]["state"] == "available"
    assert status["metadata"]["total_assets"] == 1


def test_scoped_status_rejects_path_outside_library(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    root = isolated_gallery_root / "registered"
    outside = isolated_gallery_root / "outside"
    root.mkdir()
    outside.mkdir()
    library_id = int(register_library(root)["id"])

    response = isolated_app.get(
        f"/api/libraries/{library_id}/status",
        params={"scope_path": str(outside)},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "bad_request"


def test_library_status_reports_degraded_availability_after_successful_scan(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    first = isolated_gallery_root / "first"
    second = isolated_gallery_root / "second"
    offline = isolated_gallery_root / "offline"
    first.mkdir()
    second.mkdir()
    offline.mkdir()
    library_id = int(register_library(first)["id"])
    update_library(library_id, import_paths=[first, second, offline])
    offline.rmdir()
    job = create_job(
        "scan",
        library_id=library_id,
        trigger="scheduled",
        priority=10,
        progress_total=0,
    )
    update_job_state(int(job["id"]), "running", progress_current=0, progress_total=0)
    update_job_state(int(job["id"]), "succeeded", progress_current=0, progress_total=0)

    response = isolated_app.get(f"/api/libraries/{library_id}/status")

    assert response.status_code == 200
    status = response.json()["status"]
    assert status["summary_state"] == "ready_with_issues"
    assert status["availability"] == {
        "state": "degraded",
        "available_paths": 2,
        "total_paths": 3,
    }
    assert status["issues"]["availability"] == 1
    assert status["latest_issue"]["source"] == "availability"
