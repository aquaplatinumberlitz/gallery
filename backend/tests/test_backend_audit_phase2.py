"""
Purpose:
Protect metadata and catalog convergence fixes from backend audit phase 2.

Guarantees:
* sidecar create/change/delete requeues unchanged images
* oversized sidecars return 413 and fail background work with bounded errors
* metadata status counts active images only
* offline import roots are reconciled into tombstones
* gated library mutations reject active work and orphan metadata cannot reappear

Run when:
* changing sidecar identity, metadata jobs/status, catalog reconciliation, or library mutation gates
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.indexer import MetadataLifecycleWorker, recover_metadata_index_jobs
from backend.metadata_extract import extract_metadata
from backend.metadata_store import (
    _DB_LOCK,
    _connect,
    _persist_metadata_index_jobs,
    claim_next_catalog_job,
    claim_next_metadata_job,
    create_library,
    get_metadata_index_status,
    index_file,
    unregister_library,
    upsert_extracted_metadata,
    upsert_metadata_batch,
)
from backend.metadata_store.job_store import create_job, update_job_state
from backend.metadata_store.status_store import build_catalog_status
from backend.scan_worker import execute_scan_job, queue_scan
from tests.conftest import create_test_png


def _seed_image(root: Path, *, sidecar_text: str | None = None) -> tuple[int, Path]:
    root.mkdir(parents=True, exist_ok=True)
    image = root / "image.png"
    create_test_png(image)
    if sidecar_text is not None:
        image.with_suffix(".txt").write_text(sidecar_text, encoding="utf-8")
    library = create_library([root], name=root.name)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    return int(library["id"]), image


@pytest.mark.parametrize("change", ["create", "change", "delete"])
def test_sidecar_identity_changes_requeue_unchanged_image(isolated_gallery_root: Path, change: str):
    initial = None if change == "create" else "first prompt\nSteps: 10, Seed: 1"
    _library_id, image = _seed_image(isolated_gallery_root / change, sidecar_text=initial)
    assert upsert_extracted_metadata(extract_metadata(image), mark_job_done=True)

    sidecar = image.with_suffix(".txt")
    if change == "create":
        sidecar.write_text("created prompt\nSteps: 11, Seed: 2", encoding="utf-8")
    elif change == "change":
        sidecar.write_text("changed prompt\nSteps: 12, Seed: 3", encoding="utf-8")
    else:
        sidecar.unlink()

    result = _persist_metadata_index_jobs([image])
    assert len(result.enqueued) == 1
    assert result.skipped == 0


def test_oversized_sidecar_returns_413_and_background_failure_is_bounded(
    isolated_app,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import backend.metadata_extract as metadata_extract

    _library_id, image = _seed_image(isolated_gallery_root / "oversized")
    image.with_suffix(".txt").write_text("x" * 64, encoding="utf-8")
    monkeypatch.setattr(metadata_extract, "METADATA_SIDECAR_MAX_BYTES", 16)

    response = isolated_app.get("/api/metadata", params={"path": image})
    assert response.status_code == 413

    _persist_metadata_index_jobs([image])
    job = claim_next_metadata_job()
    assert job is not None
    MetadataLifecycleWorker()._run_job(job)
    status = get_metadata_index_status(image.parent)
    assert status["counts"]["failed"] == 1
    with _DB_LOCK, _connect() as conn:
        error = conn.execute(
            "SELECT error FROM metadata_index_jobs WHERE path = ?", (str(image.resolve()),)
        ).fetchone()[0]
    assert len(error) <= 1000
    assert "exceeds 16 bytes" in error


def test_startup_recovery_demotes_done_job_after_sidecar_change(isolated_gallery_root: Path):
    _library_id, image = _seed_image(
        isolated_gallery_root / "recovery",
        sidecar_text="first prompt\nSteps: 10, Seed: 1",
    )
    assert upsert_extracted_metadata(extract_metadata(image), mark_job_done=True)
    image.with_suffix(".txt").write_text("second prompt\nSteps: 11, Seed: 2", encoding="utf-8")

    result = recover_metadata_index_jobs()

    assert result["done_demoted"] == 1
    assert get_metadata_index_status(image.parent)["counts"]["queued"] == 1


def test_video_only_library_metadata_status_is_complete_with_zero_assets(isolated_gallery_root: Path):
    root = isolated_gallery_root / "videos"
    root.mkdir()
    video = root / "clip.mp4"
    video.write_bytes(b"video")
    library = create_library([root], name="Videos")
    stat = video.stat()
    assert index_file(video, video.name, video.parent, "video", stat.st_mtime, stat.st_size, None, None, "video/mp4")
    job = create_job("scan", library_id=int(library["id"]))
    update_job_state(int(job["id"]), "running", message="Updating library")
    update_job_state(int(job["id"]), "succeeded", message="Update completed")

    metadata = build_catalog_status(int(library["id"]))["status"]["metadata"]
    assert metadata["total_assets"] == 0
    assert metadata["ready_assets"] == 0
    assert metadata["state"] == "complete"


def test_scan_reconciles_offline_import_root_with_empty_discovery(isolated_gallery_root: Path):
    online = isolated_gallery_root / "online"
    offline = isolated_gallery_root / "offline"
    _library_id, online_image = _seed_image(online)
    offline.mkdir()
    offline_image = offline / "offline.png"
    create_test_png(offline_image)

    with _DB_LOCK, _connect() as conn:
        library_id = int(conn.execute("SELECT id FROM libraries LIMIT 1").fetchone()[0])
        now = conn.execute("SELECT updated_at FROM libraries WHERE id = ?", (library_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO library_import_paths (library_id, path, position, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (library_id, str(offline.resolve()), now, now),
        )
    stat = offline_image.stat()
    assert index_file(
        offline_image,
        offline_image.name,
        offline_image.parent,
        "image",
        stat.st_mtime,
        stat.st_size,
        64,
        64,
    )
    shutil.rmtree(offline)

    queued, _created = queue_scan(library_id, trigger="manual")
    claimed = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed is not None and int(claimed["id"]) == int(queued["id"])
    assert execute_scan_job(claimed)

    with _DB_LOCK, _connect() as conn:
        rows = {Path(row["path"]).name: int(row["offline"]) for row in conn.execute("SELECT path, offline FROM assets")}
    assert rows[online_image.name] == 0
    assert rows["offline.png"] == 1


def test_unregister_prevents_orphan_metadata_recreation(isolated_gallery_root: Path):
    library_id, image = _seed_image(isolated_gallery_root / "unregister")
    extracted = extract_metadata(image)

    assert unregister_library(library_id)
    assert upsert_metadata_batch([extracted]) == 0
    with _DB_LOCK, _connect() as conn:
        assert conn.execute("SELECT count(*) FROM image_metadata WHERE path = ?", (extracted.path,)).fetchone()[0] == 0


def test_import_path_update_rejects_active_metadata_work(
    isolated_app,
    isolated_gallery_root: Path,
):
    library_id, image = _seed_image(isolated_gallery_root / "busy")
    _persist_metadata_index_jobs([image])

    response = isolated_app.patch(
        f"/api/libraries/{library_id}",
        json={"import_paths": [str(image.parent)]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "maintenance_busy"
