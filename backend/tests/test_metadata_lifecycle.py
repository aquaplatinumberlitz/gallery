"""
Purpose:
Phase 0B contract tests for the DB-claim metadata worker. These tests verify
that the new claim/completion primitives and worker class introduced in Phase 1
behave correctly. They reference symbols that do not exist before Phase 1.

Guarantees:
* claim_next_metadata_job claims queued jobs from SQLite with atomicity
* complete_metadata_job materializes both job done and asset done with mtime_ns
* MetadataLifecycleWorker._run_job completes jobs in short transactions
* Worker does not hold long write transactions during extraction

Run when:
* changing claim_next_metadata_job, complete_metadata_job, MetadataLifecycleWorker
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from backend.metadata_store import (
    MetadataIndexJob,
    _DB_LOCK,
    _connect,
    claim_next_metadata_job,
    complete_metadata_job,
    fail_metadata_job,
    get_metadata_index_status,
    initialize_database,
    mark_metadata_job_stale,
    queue_metadata_index_paths,
    reset_running_jobs_to_queued,
)
from tests.conftest import create_test_image, create_test_png


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Ensure the database is initialized for each test."""
    initialize_database()


def _seed_asset_and_metadata(db_path: Path, path: Path, mtime_ns: int, size: int) -> int:
    """Insert an assets row and image_metadata row for the given path."""
    from backend.metadata_store import create_library

    root = path.parent.parent
    lib = create_library([root], name="TestLib")
    library_id = int(lib["id"])
    now = time.time()
    resolved = str(path.resolve())
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, NULL, NULL, ?, 'pending', 0, NULL)
            """,
            (library_id, resolved, str(path.parent), path.name, mtime_ns, size, now),
        )
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, 64, 64, '{}', ?, ?)
            """,
            (resolved, path.name, mtime_ns / 1_000_000_000, mtime_ns, size, now, now),
        )
    return library_id


# ---------------------------------------------------------------------------
# Test 3: Metadata worker claims queued jobs directly from SQLite
# ---------------------------------------------------------------------------


def test_worker_claims_queued_jobs_directly_from_sqlite(
    isolated_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """The DB-claim worker claims jobs from SQLite, not from an in-memory queue.

    After Phase 1, the worker's _claim_job calls claim_next_metadata_job() which
    claims directly from metadata_index_jobs. The old indexer._job_queue is
    bypassed and remains empty.
    """
    import backend.indexer as indexer

    while not indexer._job_queue.empty():
        indexer._job_queue.get_nowait()

    image = tmp_path / "test.png"
    create_test_image(image)
    queue_metadata_index_paths([image])

    status = get_metadata_index_status(path=tmp_path)
    assert status["total"] == 1
    assert status["counts"].get("queued", 0) == 1

    assert indexer._job_queue.qsize() == 0

    job = claim_next_metadata_job()
    assert job is not None
    assert job.path == str(image.resolve())

    status = get_metadata_index_status(path=tmp_path)
    assert status["counts"].get("running", 0) == 1
    assert status["counts"].get("queued", 0) == 0

    assert isinstance(job, MetadataIndexJob)
    assert job.mtime_ns is not None, "Job should have mtime_ns populated"
    assert job.mtime_ns == image.stat().st_mtime_ns


# ---------------------------------------------------------------------------
# Test 4: Claimed jobs move queued -> running (atomicity)
# ---------------------------------------------------------------------------


def test_claim_next_metadata_job_atomicity(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """Claimed jobs atomically transition queued -> running.

    Once claimed, no other call to claim_next_metadata_job can return
    the same job.
    """
    image = tmp_path / "test.png"
    create_test_image(image)

    queue_metadata_index_paths([image])

    first = claim_next_metadata_job()
    assert first is not None
    assert first.path == str(image.resolve())

    second = claim_next_metadata_job()
    assert second is None, (
        "Job should already be claimed (running); "
        "no more queued jobs should be available"
    )


# ---------------------------------------------------------------------------
# Test 5 variant: complete_metadata_job materializes job done + asset done
# ---------------------------------------------------------------------------


def test_complete_metadata_job_materializes_job_and_asset_done(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """complete_metadata_job marks job done and asset done in one transaction.

    It verifies image_metadata is current before marking done.
    After completion:
      - metadata_index_jobs.state == 'done'
      - assets.metadata_state == 'done'
    """
    image = tmp_path / "lib" / "album" / "test.png"
    image.parent.mkdir(parents=True)
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    # Seed asset and image_metadata rows
    _seed_asset_and_metadata(isolated_metadata_db, image, stat.st_mtime_ns, stat.st_size)

    # Also seed a metadata_index_jobs row (simulating a claimed job)
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (resolved, image.name, str(image.parent), str(image.parent), str(image.parent.parent),
             stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, now),
        )

    # Create a matching MetadataIndexJob
    job = MetadataIndexJob(
        path=resolved,
        name=image.name,
        parent_path=str(image.parent),
        folder_path=str(image.parent),
        root_path=str(image.parent.parent),
        mtime=stat.st_mtime,
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
    )

    with _DB_LOCK, _connect() as conn:
        complete_metadata_job(conn, job)

    # Verify job is done
    status = get_metadata_index_status(path=image.parent)
    assert status["counts"].get("done", 0) == 1, "Job should be done after completion"

    # Verify asset is done
    with _DB_LOCK, _connect() as conn:
        asset_row = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_row is not None
    assert asset_row["metadata_state"] == "done", (
        f"Asset should be 'done' after completion, got '{asset_row['metadata_state']}'"
    )


def test_complete_metadata_job_stales_job_when_metadata_missing(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """complete_metadata_job marks job stale when image_metadata is missing
    (no current metadata for the job identity)."""
    image = tmp_path / "lib" / "test.png"
    image.parent.mkdir(parents=True)
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    # Seed a library and asset row but NO image_metadata
    from backend.metadata_store import create_library

    lib = create_library([image.parent.parent], name="TestLib")
    library_id = int(lib["id"])
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, NULL, NULL, ?, 'pending', 0, NULL)
            """,
            (library_id, resolved, str(image.parent), image.name, stat.st_mtime_ns, stat.st_size, now),
        )
        # Seed a metadata_index_jobs row
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (resolved, image.name, str(image.parent), str(image.parent), str(image.parent.parent),
             stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, now),
        )

    job = MetadataIndexJob(
        path=resolved,
        name=image.name,
        parent_path=str(image.parent),
        folder_path=str(image.parent),
        root_path=str(image.parent.parent),
        mtime=stat.st_mtime,
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
    )

    with _DB_LOCK, _connect() as conn:
        complete_metadata_job(conn, job)

    # Verify job is stale (not done) because no image_metadata exists
    status = get_metadata_index_status(path=image.parent)
    assert status["counts"].get("stale", 0) >= 1, (
        "Job should be stale when image_metadata is missing"
    )
    assert status["counts"].get("done", 0) == 0, (
        "Job should NOT be done when image_metadata is missing"
    )


# ---------------------------------------------------------------------------
# Test 16: Worker does not hold long write transactions during extraction
# ---------------------------------------------------------------------------


def test_worker_does_not_hold_long_write_transactions(
    isolated_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """The worker's _run_job releases the claim transaction before calling
    extract_metadata. No write transaction is held during extraction.

    We verify this by monkeypatching extract_metadata to check that no
    write transaction is active on the metadata DB connection.
    """
    from backend.indexer import MetadataLifecycleWorker

    # Create a library and seed a job
    root = tmp_path / "lib"
    root.mkdir()
    album = root / "album"
    album.mkdir()
    image = album / "test.png"
    create_test_png(image)
    stat = image.stat()

    # Need a library for the metadata path to resolve
    from backend.metadata_store import create_library
    create_library([root], name="TestLib")

    # Seed a metadata job
    queue_metadata_index_paths([image])
    job = claim_next_metadata_job()
    assert job is not None
    assert job.mtime_ns is not None

    # Monkeypatch extract_metadata to verify no write tx is open
    from backend.metadata_extract import extract_metadata as original_extract

    extraction_had_open_tx = [False]
    db_path = isolated_metadata_db

    def tracking_extract(path):
        """Check whether a write transaction is open on the metadata DB."""
        # Open a separate connection to check transaction state
        conn2 = sqlite3.connect(str(db_path))
        try:
            # Check if a write transaction is open by attempting to acquire
            # a RESERVED lock. If another connection holds a write transaction,
            # this will raise OperationalError.
            conn2.execute("BEGIN IMMEDIATE")
            conn2.execute("SELECT 1 FROM metadata_index_jobs LIMIT 1")
            extraction_had_open_tx[0] = False
        except sqlite3.OperationalError:
            extraction_had_open_tx[0] = True
        finally:
            conn2.close()
        return original_extract(path)

    monkeypatch.setattr(
        "backend.metadata_extract.extract_metadata",
        tracking_extract,
    )

    worker = MetadataLifecycleWorker()
    worker._run_job(job)

    # Verify extraction did NOT happen inside a write transaction
    assert not extraction_had_open_tx[0], (
        "extract_metadata was called while a write transaction was open; "
        "the claim/complete transactions should bracket extraction, not overlap"
    )

    # Verify the job completed
    status = get_metadata_index_status(path=root)
    assert status["counts"].get("done", 0) == 1, (
        f"Job should be done after _run_job, got {status['counts']}"
    )
