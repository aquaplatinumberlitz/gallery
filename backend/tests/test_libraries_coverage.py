"""Targeted coverage for backend/libraries.py validation and error branches.

Exercises uncovered HTTP handler branches for library CRUD validation,
import path validation errors, scan/rebuild edge cases, derivative
endpoints, and internal helper functions so backend line coverage stays
above the release threshold.

Purpose:
Cover edge and error branches in `backend/libraries.py` handlers and helpers.

Guarantees:
Validation, scan/rebuild, derivative, event, and error-response branches remain
covered by focused backend tests.

Run when:
Changing library route validation, management actions, derivative endpoints, or
coverage-sensitive helper branches.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.libraries as libraries_module
from backend import scan_worker as catalog_service
from backend.errors import APIError, ErrorType
from backend.libraries import (
    LibraryCreate,
    _effective_create_paths,
    _emit_job,
    _normalized_validated_values,
    _set_job_state,
    _trim_value,
    _validate_settings,
)
from backend.metadata_store import (
    LibraryOverlapError,
    create_job,
    register_library,
    update_job_state,
)
from tests.conftest import create_test_png

# ---------------------------------------------------------------------------
# _trim_value (line 84 — quoted value stripping)
# ---------------------------------------------------------------------------


def test_trim_value_strips_matching_double_quotes():
    assert _trim_value('"hello"') == "hello"


def test_trim_value_strips_matching_single_quotes():
    assert _trim_value("'hello'") == "hello"


def test_trim_value_strips_inner_whitespace_inside_quotes():
    assert _trim_value('"  hello  "') == "hello"


# ---------------------------------------------------------------------------
# _effective_create_paths (lines 90, 93-95)
# ---------------------------------------------------------------------------


def test_effective_create_paths_rejects_both_root_and_import():
    payload = LibraryCreate(root_path="/tmp", import_paths=["/tmp"])
    with pytest.raises(APIError) as exc:
        _effective_create_paths(payload)
    assert exc.value.status_code == 400


def test_effective_create_paths_with_root_path_only():
    assert _effective_create_paths(LibraryCreate(root_path="/tmp")) == ["/tmp"]


def test_effective_create_paths_with_neither_returns_empty():
    assert _effective_create_paths(LibraryCreate()) == []


# ---------------------------------------------------------------------------
# _validate_settings — import path validation (lines 121-151, 156-163)
# ---------------------------------------------------------------------------


def test_validate_settings_empty_import_path(isolated_metadata_db: Path, isolated_gallery_root: Path):
    result = _validate_settings([""], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path cannot be empty"


def test_validate_settings_non_absolute_import_path(isolated_metadata_db: Path, isolated_gallery_root: Path):
    result = _validate_settings(["relative/path"], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path must be absolute"


def test_validate_settings_unresolvable_import_path(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    original = libraries_module.resolve_path

    def fail_resolve(raw_path: str) -> Path:
        if "unresolvable" in raw_path:
            raise RuntimeError("mocked")
        return original(raw_path)

    monkeypatch.setattr(libraries_module, "resolve_path", fail_resolve)
    result = _validate_settings(["/unresolvable/path"], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path could not be resolved"


def test_validate_settings_path_outside_safety_root(
    isolated_metadata_db: Path, isolated_gallery_root: Path, tmp_path: Path
):
    outside = tmp_path / "outside_safety"
    outside.mkdir()
    result = _validate_settings([str(outside)], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path is outside the allowed safety root"


def test_validate_settings_nonexistent_path(isolated_metadata_db: Path, isolated_gallery_root: Path):
    result = _validate_settings([str(isolated_gallery_root / "nonexistent")], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path does not exist"


def test_validate_settings_file_not_directory(isolated_metadata_db: Path, isolated_gallery_root: Path):
    file_path = isolated_gallery_root / "file.png"
    create_test_png(file_path)
    result = _validate_settings([str(file_path)], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path is not a directory"


def test_validate_settings_unreadable_path(isolated_metadata_db: Path, isolated_gallery_root: Path):
    unreadable = isolated_gallery_root / "noread"
    unreadable.mkdir()
    os.chmod(unreadable, 0o000)
    try:
        result = _validate_settings([str(unreadable)], [])
    finally:
        os.chmod(unreadable, 0o755)
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path is not readable"


def test_validate_settings_scandir_permission_error(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    readable = isolated_gallery_root / "readable"
    readable.mkdir()

    def fail_scandir(_path):
        raise PermissionError("mocked scandir failure")

    monkeypatch.setattr(os, "scandir", fail_scandir)
    result = _validate_settings([str(readable)], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path is not readable"


def test_validate_settings_duplicate_and_invalid_paths(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """Mix of invalid (empty) and duplicate valid paths covers lines 156, 158, 163."""
    valid = isolated_gallery_root / "valid"
    valid.mkdir()
    result = _validate_settings(["", str(valid), str(valid)], [])
    assert not result["is_valid"]
    assert result["import_paths"][0]["message"] == "Import path cannot be empty"
    assert result["import_paths"][2]["message"] == "Duplicate import path"


# ---------------------------------------------------------------------------
# _validate_settings — exclusion pattern validation (lines 189-207)
# ---------------------------------------------------------------------------


def test_validate_settings_too_many_exclusion_patterns(isolated_metadata_db: Path, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    patterns = [f"pat{i}" for i in range(129)]
    result = _validate_settings([str(root)], patterns)
    assert not result["is_valid"]
    assert result["exclusion_patterns"][128]["message"] == "At most 128 exclusion patterns are allowed"


def test_validate_settings_empty_exclusion_pattern(isolated_metadata_db: Path, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    result = _validate_settings([str(root)], [""])
    assert not result["is_valid"]
    assert result["exclusion_patterns"][0]["message"] == "Exclusion pattern cannot be empty"


def test_validate_settings_absolute_exclusion_pattern(isolated_metadata_db: Path, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    result = _validate_settings([str(root)], ["/absolute/path"])
    assert not result["is_valid"]
    msg = result["exclusion_patterns"][0]["message"]
    assert "Exclusion patterns must be relative" in msg


def test_validate_settings_parent_ref_exclusion_pattern(isolated_metadata_db: Path, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    result = _validate_settings([str(root)], ["../escape"])
    assert not result["is_valid"]
    msg = result["exclusion_patterns"][0]["message"]
    assert "Exclusion patterns must be relative" in msg


def test_validate_settings_duplicate_exclusion_pattern(isolated_metadata_db: Path, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    result = _validate_settings([str(root)], ["cache/**", "cache/**"])
    assert not result["is_valid"]
    assert result["exclusion_patterns"][1]["message"] == "Duplicate exclusion pattern"


def test_validate_settings_invalid_glob_pattern(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """glob.compile raising maps to 'Invalid exclusion pattern' (lines 206-207)."""
    root = isolated_gallery_root / "root"
    root.mkdir()

    real_compile = libraries_module.glob.compile

    def fail_compile(_pattern, *_args, **_kwargs):
        raise ValueError("mocked invalid pattern")

    monkeypatch.setattr(libraries_module.glob, "compile", fail_compile)
    try:
        result = _validate_settings([str(root)], ["bad/**"])
    finally:
        monkeypatch.setattr(libraries_module.glob, "compile", real_compile)
    assert not result["is_valid"]
    assert result["exclusion_patterns"][0]["message"] == "Invalid exclusion pattern"


# ---------------------------------------------------------------------------
# _normalized_validated_values (lines 251, 253, 258)
# ---------------------------------------------------------------------------


def test_normalized_validated_values_404_for_nonexistent_path():
    result = {
        "is_valid": False,
        "import_paths": [{"is_valid": False, "message": "Import path does not exist", "normalized_value": None}],
        "exclusion_patterns": [],
    }
    with pytest.raises(APIError) as exc:
        _normalized_validated_values(result, "import_paths")
    assert exc.value.status_code == 404
    assert exc.value.detail["error"] == ErrorType.NOT_FOUND


def test_normalized_validated_values_400_for_not_directory():
    result = {
        "is_valid": False,
        "import_paths": [{"is_valid": False, "message": "Import path is not a directory", "normalized_value": None}],
        "exclusion_patterns": [],
    }
    with pytest.raises(APIError) as exc:
        _normalized_validated_values(result, "import_paths")
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == ErrorType.NOT_DIRECTORY


def test_normalized_validated_values_403_for_outside_safety_root():
    result = {
        "is_valid": False,
        "import_paths": [
            {
                "is_valid": False,
                "message": "Import path is outside the allowed safety root",
                "normalized_value": None,
            }
        ],
        "exclusion_patterns": [],
    }
    with pytest.raises(APIError) as exc:
        _normalized_validated_values(result, "import_paths")
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == ErrorType.PERMISSION_DENIED


# ---------------------------------------------------------------------------
# _emit_job / _set_job_state (lines 266, 272, 277)
# ---------------------------------------------------------------------------


def test_emit_job_publishes_library_progress(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """_emit_job publishes a library.progress event when library_id is not None (line 266)."""
    library_id = int(register_library(isolated_gallery_root)["id"])
    job = create_job("scan", library_id=library_id, message="Scan queued")
    _emit_job(job)


def test_set_job_state_failed_event_type(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """_set_job_state uses job.failed event type for failed transitions (line 277)."""
    library_id = int(register_library(isolated_gallery_root)["id"])
    job = create_job("scan", library_id=library_id)
    update_job_state(int(job["id"]), "running")
    failed = _set_job_state(int(job["id"]), "failed", error="broken")
    assert failed["state"] == "failed"


def test_set_job_state_raises_when_job_disappears(isolated_metadata_db: Path, isolated_gallery_root: Path):
    """_set_job_state raises RuntimeError when update_job_state returns None (line 272)."""
    with pytest.raises(RuntimeError, match="disappeared"):
        _set_job_state(999999, "running")


# ---------------------------------------------------------------------------
# API: register / validate create (lines 321-337)
# ---------------------------------------------------------------------------


def test_api_register_library_create_overlap_409(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """create_library raising LibraryOverlapError maps to 409 (lines 321-322)."""
    root = isolated_gallery_root / "root"
    root.mkdir()

    def raise_overlap(*_args, **_kwargs):
        raise LibraryOverlapError("Import paths overlap")

    monkeypatch.setattr(libraries_module, "create_library", raise_overlap)
    response = isolated_app.post("/api/libraries", json={"import_paths": [str(root)]})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_overlap"


def test_api_validate_create_with_both_root_and_import(isolated_app: TestClient):
    """Validate endpoint returns structured error when both root_path and import_paths given (lines 334-337)."""
    response = isolated_app.post("/api/libraries/validate", json={"root_path": "/tmp", "import_paths": ["/tmp"]})
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    assert "not both" in body["import_paths"][0]["message"]


# ---------------------------------------------------------------------------
# API: not-found branches (lines 428, 435, 449-452, 546-547, 556, 566-567, 574)
# ---------------------------------------------------------------------------


def test_api_get_job_not_found(isolated_app: TestClient):
    assert isolated_app.get("/api/jobs/999999").status_code == 404


def test_api_events_stream(isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch):
    """GET /api/events returns a StreamingResponse (line 435)."""

    async def finite_stream(_request):
        yield ": keep-alive\n\n"

    monkeypatch.setattr(libraries_module, "event_stream", finite_stream)
    response = isolated_app.get("/api/events")
    assert response.status_code == 200


def test_api_get_library_not_found(isolated_app: TestClient):
    assert isolated_app.get("/api/libraries/999999").status_code == 404


def test_api_get_library_success(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.get(f"/api/libraries/{library_id}")
    assert response.status_code == 200
    assert response.json()["id"] == library_id


def test_api_library_progress_not_found(isolated_app: TestClient):
    assert isolated_app.get("/api/libraries/999999/progress").status_code == 404


def test_api_library_status_not_found(isolated_app: TestClient):
    """KeyError from build_catalog_status maps to 404 (line 556)."""
    assert isolated_app.get("/api/libraries/999999/status").status_code == 404


def test_api_library_stats_not_found(isolated_app: TestClient):
    assert isolated_app.get("/api/libraries/999999/stats").status_code == 404


def test_api_library_jobs_not_found(isolated_app: TestClient):
    assert isolated_app.get("/api/libraries/999999/jobs").status_code == 404


# ---------------------------------------------------------------------------
# API: validate update (lines 458-469)
# ---------------------------------------------------------------------------


def test_api_validate_update_library_not_found(isolated_app: TestClient):
    response = isolated_app.post("/api/libraries/999999/validate", json={"name": "New"})
    assert response.status_code == 404


def test_api_validate_update_existing_library(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.post(
        f"/api/libraries/{library_id}/validate",
        json={"import_paths": [str(root)], "exclusion_patterns": ["*.tmp"]},
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


# ---------------------------------------------------------------------------
# API: PATCH library (lines 479, 481, 484, 488, 513, 522-525)
# ---------------------------------------------------------------------------


def test_api_patch_library_no_fields(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={})
    assert response.status_code == 400


def test_api_patch_library_null_field(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={"name": None})
    assert response.status_code == 400


def test_api_patch_library_not_found(isolated_app: TestClient):
    response = isolated_app.patch("/api/libraries/999999", json={"name": "New"})
    assert response.status_code == 404


def test_api_patch_library_busy(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    create_job("scan", library_id=library_id)
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={"import_paths": [str(root)]})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_busy"


def test_api_patch_library_empty_name(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={"name": "   "})
    assert response.status_code == 400


def test_api_patch_library_update_overlap_409(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """update_library raising LibraryOverlapError maps to 409 (lines 522-523)."""
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])

    def raise_overlap(*_args, **_kwargs):
        raise LibraryOverlapError("Import path overlaps registered path")

    monkeypatch.setattr(libraries_module, "update_library", raise_overlap)
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={"name": "New Name"})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_overlap"


def test_api_patch_library_update_returns_none_404(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """update_library returning None maps to 404 (line 525)."""
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    monkeypatch.setattr(libraries_module, "update_library", lambda *_a, **_kw: None)
    response = isolated_app.patch(f"/api/libraries/{library_id}", json={"name": "New Name"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# API: scan library (lines 583, 588, 590-592, 594-595, 603-605)
# ---------------------------------------------------------------------------


def test_api_scan_library_not_found(isolated_app: TestClient):
    assert isolated_app.post("/api/libraries/999999/scan").status_code == 404


def test_api_scan_library_scope_outside(isolated_app: TestClient, isolated_gallery_root: Path, tmp_path: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    outside = tmp_path / "outside"
    outside.mkdir()
    response = isolated_app.post(f"/api/libraries/{library_id}/scan", json={"scope_path": str(outside)})
    assert response.status_code == 400


def test_api_scan_library_scope_offline(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()
    library_id = int(register_library(root)["id"])
    sub.rmdir()
    response = isolated_app.post(f"/api/libraries/{library_id}/scan", json={"scope_path": str(sub)})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_offline"


def test_api_scan_library_all_paths_offline(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    root.rmdir()
    response = isolated_app.post(f"/api/libraries/{library_id}/scan")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_offline"


def test_api_scan_library_conflict_with_rebuild(isolated_app: TestClient, isolated_gallery_root: Path):
    """CatalogJobConflict from scan while rebuild is queued maps to 409 (lines 603-605)."""
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    catalog_service.queue_rebuild(library_id)
    response = isolated_app.post(f"/api/libraries/{library_id}/scan")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_busy"


# ---------------------------------------------------------------------------
# API: rebuild library (lines 638, 651-655, 657-658, 665-667)
# ---------------------------------------------------------------------------


def test_api_rebuild_library_not_found(isolated_app: TestClient):
    response = isolated_app.post("/api/libraries/999999/rebuild", json={"confirm": True})
    assert response.status_code == 404


def test_api_rebuild_library_scope_offline(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()
    library_id = int(register_library(root)["id"])
    sub.rmdir()
    response = isolated_app.post(
        f"/api/libraries/{library_id}/rebuild",
        json={"confirm": True, "scope_path": str(sub)},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_offline"


def test_api_rebuild_library_all_paths_offline(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    root.rmdir()
    response = isolated_app.post(f"/api/libraries/{library_id}/rebuild", json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_offline"


def test_api_rebuild_library_conflict_with_running_scan(isolated_app: TestClient, isolated_gallery_root: Path):
    """CatalogJobConflict from rebuild while scan is running maps to 409 (lines 665-667)."""
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    scan_job, _created = catalog_service.queue_scan(library_id, trigger="manual")
    update_job_state(int(scan_job["id"]), "running")
    response = isolated_app.post(f"/api/libraries/{library_id}/rebuild", json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_busy"


# ---------------------------------------------------------------------------
# API: unregister library (lines 705, 707)
# ---------------------------------------------------------------------------


def test_api_unregister_library_busy(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    create_job("scan", library_id=library_id)
    response = isolated_app.delete(f"/api/libraries/{library_id}?confirm=true")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "library_busy"


def test_api_unregister_library_not_found(isolated_app: TestClient):
    response = isolated_app.delete("/api/libraries/999999?confirm=true")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# API: derivatives (lines 714-747)
# ---------------------------------------------------------------------------


def test_api_derivative_status_not_found(isolated_app: TestClient):
    response = isolated_app.get("/api/derivatives/status", params={"library_id": 999999})
    assert response.status_code == 404


def test_api_derivative_status_success(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.get("/api/derivatives/status", params={"library_id": library_id})
    assert response.status_code == 200
    assert "quota_bytes" in response.json()


def test_api_warm_derivatives_not_found(isolated_app: TestClient):
    response = isolated_app.post("/api/derivatives/warm", params={"library_id": 999999})
    assert response.status_code == 404


def test_api_warm_derivatives_success(isolated_app: TestClient, isolated_gallery_root: Path):
    root = isolated_gallery_root / "root"
    root.mkdir()
    library_id = int(register_library(root)["id"])
    response = isolated_app.post("/api/derivatives/warm", params={"library_id": library_id})
    assert response.status_code == 202
    assert response.json()["state"] == "queued"


def test_api_rebuild_derivatives_requires_confirmation(isolated_app: TestClient):
    response = isolated_app.post("/api/derivatives/rebuild")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_api_rebuild_derivatives_success(isolated_app: TestClient):
    response = isolated_app.post("/api/derivatives/rebuild?confirm=true")
    assert response.status_code == 202
    assert response.json()["state"] == "queued"


def test_api_clear_derivatives_requires_confirmation(isolated_app: TestClient):
    response = isolated_app.post("/api/derivatives/clear")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "confirmation_required"


def test_api_clear_derivatives_success(isolated_app: TestClient):
    response = isolated_app.post("/api/derivatives/clear?confirm=true")
    assert response.status_code == 200
    assert "catalog_entries_cleared" in response.json()


# ---------------------------------------------------------------------------
# Stale derivative readiness (P1 bug: stale rows counted as ready)
# ---------------------------------------------------------------------------


def test_derivative_status_stale_source_not_counted(isolated_app: TestClient, isolated_gallery_root: Path):
    """After a source image changes, its old derivative rows must not count
    as ready in library_status() or browse derivative_ready."""
    import time as _time

    from backend.derivative_scheduler import scheduler as deriv_scheduler
    from backend.metadata_store import _connect

    root = isolated_gallery_root / "root"
    root.mkdir()
    photo = root / "img.png"
    create_test_png(photo)
    library_id = int(register_library(root)["id"])

    # Ensure derivative scheduler is running (isolated_app may skip startup events)
    deriv_scheduler.start()

    # Directly insert the asset row so we don't need the scan worker
    photo_stat = photo.stat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO assets (library_id, path, name, parent_path, type, mtime_ns, size, metadata_state)
               VALUES (?, ?, ?, ?, 'image', ?, ?, 'pending')""",
            (library_id, str(photo), "img.png", str(root), photo_stat.st_mtime_ns, photo_stat.st_size),
        )
        asset_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    # Warm derivatives for this asset by calling scheduler directly
    deriv_scheduler.warm_library(library_id)

    # Wait for derivative workers to finish processing
    for _ in range(30):
        _time.sleep(0.5)
        status_resp = isolated_app.get("/api/derivatives/status", params={"library_id": library_id})
        assert status_resp.status_code == 200
        first_status = status_resp.json()
        if first_status["ready_derivatives"] > 0:
            break

    assert first_status["ready_derivatives"] > 0, (
        f"expected ready derivatives after warm. Status: {first_status}"
    )

    # Modify source image (new content = new mtime_ns and size)
    _time.sleep(0.01)  # ensure different mtime
    create_test_png(photo, size=(128, 128), color=(255, 0, 0))
    after_stat = photo.stat()
    assert (
        photo_stat.st_mtime_ns != after_stat.st_mtime_ns or photo_stat.st_size != after_stat.st_size
    ), "source must differ after rewrite"

    # Update the asset row to reflect the new file version
    with _connect() as conn:
        conn.execute(
            "UPDATE assets SET mtime_ns = ?, size = ? WHERE id = ?",
            (after_stat.st_mtime_ns, after_stat.st_size, asset_id),
        )

    # Re-fetch derivative status — stale rows must be excluded
    status_resp = isolated_app.get("/api/derivatives/status", params={"library_id": library_id})
    assert status_resp.status_code == 200
    stale_status = status_resp.json()
    assert (
        stale_status["ready_derivatives"] == 0
    ), "stale derivatives must not be counted as ready after source change"

    # Browse endpoint must not report derivative_ready for the stale asset
    browse_resp = isolated_app.get("/api/browse", params={"library_id": library_id})
    assert browse_resp.status_code == 200
    browse_data = browse_resp.json()
    for media in browse_data.get("media", []):
        dr = media.get("derivative_ready")
        if dr is not None:
            assert dr.get("preview") is False, "stale asset must not report preview ready"
            assert dr.get("thumbnail") is False, "stale asset must not report thumbnail ready"
