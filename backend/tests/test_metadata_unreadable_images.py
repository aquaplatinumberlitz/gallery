"""CP-03 regression: an unreadable image fails its metadata job instead of completing as an empty `done` row.

Purpose:
Pin ``ARCHITECTURE.md`` metadata invariant 6 ("Parse and format errors (unreadable image, ...) fail
immediately") for images Pillow cannot decode: non-image bytes, a truncated PNG, and a decompression bomb.
Before the fix ``extract_metadata`` swallowed the decode error, the job ended ``done`` with an empty
``Unknown`` row, and the status envelope showed no failure.

Guarantees:
* the metadata job for an unreadable image ends ``failed`` (no retry, no ``image_metadata`` row, asset not
  ``done``), also when a same-stem ``.txt`` sidecar exists;
* the failure is counted in ``metadata.failed_assets`` of the library status envelope;
* ``GET /api/metadata`` answers a typed 422 ``image_unreadable`` (never 500) and persists nothing, so no
  ``done`` job or row appears behind the response;
* a transient ``OSError(EBUSY)`` while reading the image still requeues the job through the retry path.

Run when:
Changing ``extract_metadata``, ``UnreadableImageError``, metadata job failure handling, or the lazy
``/api/metadata`` fallback.
"""

from __future__ import annotations

import errno
import io
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import indexer, metadata_extract, metadata_parse
from backend.indexer import MetadataLifecycleWorker
from backend.metadata_extract import UnreadableImageError, extract_metadata
from tests.conftest import create_test_png
from tests.worker_contention_support import (
    install_metadata_clock,
    metadata_job_row,
    seed_queued_metadata_jobs,
)

UNREADABLE_KINDS = ["not_an_image", "truncated_png", "decompression_bomb"]


def _write_unreadable(path: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if kind == "not_an_image":
        path.write_bytes(b"this is not an image at all")
    elif kind == "truncated_png":
        buffer = io.BytesIO()
        Image.frombytes("RGB", (128, 128), os.urandom(128 * 128 * 3)).save(buffer, format="PNG")
        path.write_bytes(buffer.getvalue()[: len(buffer.getvalue()) // 2])
    else:
        create_test_png(path, size=(64, 64))
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)  # 4096 px > 2 x 100: DecompressionBombError
    assert path.exists()


def _worker() -> MetadataLifecycleWorker:
    return MetadataLifecycleWorker(worker_count=1, lease_seconds=30, write_retry_delays=())


def _seed_unreadable_job(root: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> tuple[int, Path]:
    """One library whose single image is unreadable, with its metadata job queued."""
    from backend.metadata_store import _persist_metadata_index_jobs, index_file

    library_id, (image,) = seed_queued_metadata_jobs(root, 1)
    _write_unreadable(image, kind, monkeypatch)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 0, 0)
    assert _persist_metadata_index_jobs([image], root).enqueued
    return library_id, image


def _scalar(db_path: Path, sql: str, params: tuple = ()) -> object:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


@pytest.mark.parametrize("kind", UNREADABLE_KINDS)
def test_extract_metadata_raises_unreadable_image_error(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "bad.png"
    _write_unreadable(image, kind, monkeypatch)
    with pytest.raises(UnreadableImageError):
        extract_metadata(image)


@pytest.mark.parametrize("kind", UNREADABLE_KINDS)
def test_unreadable_image_metadata_job_ends_failed(
    kind: str, isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _library_id, image = _seed_unreadable_job(isolated_gallery_root / "lib", kind, monkeypatch)
    worker = _worker()

    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)

    row = metadata_job_row(isolated_metadata_db, image)
    assert row["state"] == "failed", row
    assert "Cannot read image" in (row["error"] or "")
    assert row["attempts"] == 1, "a permanent decode error is not retried"
    assert _scalar(isolated_metadata_db, "SELECT count(*) FROM image_metadata WHERE path = ?", (str(image),)) == 0
    assert _scalar(isolated_metadata_db, "SELECT metadata_state FROM assets WHERE path = ?", (str(image),)) != "done"


def test_unreadable_image_with_sidecar_still_fails(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sidecar does not rescue an undecodable image: the invariant is "unreadable image fails"."""
    _library_id, image = _seed_unreadable_job(isolated_gallery_root / "lib", "not_an_image", monkeypatch)
    image.with_suffix(".txt").write_text("a castle\nSteps: 20, Sampler: Euler, CFG scale: 7, Seed: 1\n")
    worker = _worker()

    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)

    assert metadata_job_row(isolated_metadata_db, image)["state"] == "failed"
    assert _scalar(isolated_metadata_db, "SELECT count(*) FROM image_metadata") == 0


@pytest.mark.parametrize("kind", UNREADABLE_KINDS)
def test_unreadable_image_counts_in_status_failed_numbers(
    kind: str,
    isolated_app: TestClient,
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)  # the test app disables the indexer
    library_id, image = _seed_unreadable_job(isolated_gallery_root / "lib", kind, monkeypatch)
    worker = _worker()
    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)

    envelope = isolated_app.get(f"/api/libraries/{library_id}/status").json()["status"]
    metadata = envelope["metadata"]
    assert metadata["failed_assets"] == 1, metadata
    assert metadata["ready_assets"] == 0, metadata
    assert metadata["state"] == "failed", metadata
    assert envelope["issues"]["metadata"] == 1, envelope["issues"]
    batch = isolated_app.get("/api/libraries/status").json()["items"]
    assert batch[0]["status"]["metadata"]["failed_assets"] == 1


@pytest.mark.parametrize("kind", UNREADABLE_KINDS)
def test_api_metadata_returns_typed_unreadable_error_and_persists_nothing(
    kind: str,
    isolated_app: TestClient,
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _library_id, image = _seed_unreadable_job(isolated_gallery_root / "lib", kind, monkeypatch)
    with metadata_parse._metadata_cache_lock:
        metadata_parse._metadata_cache.clear()

    response = isolated_app.get("/api/metadata", params={"path": str(image)})

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "image_unreadable"
    assert detail["message"] == "This file can't be read"
    assert _scalar(isolated_metadata_db, "SELECT count(*) FROM image_metadata") == 0, "no silent `done` row"
    assert metadata_job_row(isolated_metadata_db, image)["state"] != "done"
    # Repeat requests stay typed (nothing was cached as a success).
    assert isolated_app.get("/api/metadata", params={"path": str(image)}).status_code == 422


def test_api_metadata_with_truncated_png_and_sidecar_is_unreadable(
    isolated_app: TestClient, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _library_id, image = _seed_unreadable_job(isolated_gallery_root / "lib", "truncated_png", monkeypatch)
    image.with_suffix(".txt").write_text("a castle\nSteps: 20\n")
    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "image_unreadable"


def test_transient_ebusy_while_reading_the_image_still_requeues(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decode-error wrapper must not swallow `EAGAIN`/`EBUSY`/`EINTR`: those keep the retry path."""
    _library_id, (image,) = seed_queued_metadata_jobs(isolated_gallery_root / "lib", 1)
    clock = install_metadata_clock(monkeypatch)
    real_read = metadata_extract._read_image_info
    calls: list[int] = []

    def busy_once(path: Path):
        calls.append(1)
        if len(calls) == 1:
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real_read(path)

    monkeypatch.setattr(metadata_extract, "_read_image_info", busy_once)
    worker = _worker()

    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)
    row = metadata_job_row(isolated_metadata_db, image)
    assert row["state"] == "queued", "a transient read error must requeue, not fail"
    assert row["attempts"] == 1

    clock.advance(indexer.metadata_retry_delay_seconds(1) + 0.01)
    retry = worker._claim_job()
    assert retry is not None
    worker._run_job(retry)
    row = metadata_job_row(isolated_metadata_db, image)
    assert row["state"] == "done" and row["attempts"] == 2


@pytest.mark.parametrize("code", [errno.EAGAIN, errno.EBUSY, errno.EINTR])
def test_extract_metadata_propagates_transient_oserror_unchanged(
    code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "ok.png"
    create_test_png(image)

    def raise_transient(_path: Path):
        raise OSError(code, "transient")

    monkeypatch.setattr(metadata_extract, "_read_image_info", raise_transient)
    with pytest.raises(OSError) as excinfo:
        extract_metadata(image)
    assert not isinstance(excinfo.value, UnreadableImageError)
    assert indexer.is_transient_metadata_error(excinfo.value)
