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
import time
from pathlib import Path

import pytest

from backend.indexer import dispatch_metadata_index_paths, metadata_worker, recover_metadata_index_jobs
from backend.metadata_extract import extract_metadata
from backend.metadata_store import (
    _DB_LOCK,
    MAX_METADATA_JOB_ATTEMPTS,
    MetadataIndexJob,
    _connect,
    _persist_metadata_index_jobs,
    claim_next_metadata_job,
    complete_metadata_job,
    create_library,
    get_metadata_index_status,
    index_file,
    initialize_database,
    upsert_metadata_batch,
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
    claims directly from metadata_index_jobs. The old in-memory queue is not used.
    """

    image = tmp_path / "test.png"
    create_test_image(image)
    _persist_metadata_index_jobs([image])

    status = get_metadata_index_status(path=tmp_path)
    assert status["total"] == 1
    assert status["counts"].get("queued", 0) == 1

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

    _persist_metadata_index_jobs([image])

    first = claim_next_metadata_job()
    assert first is not None
    assert first.path == str(image.resolve())

    second = claim_next_metadata_job()
    assert second is None, "Job should already be claimed (running); no more queued jobs should be available"


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
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
            ),
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
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
            ),
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
    assert status["counts"].get("stale", 0) >= 1, "Job should be stale when image_metadata is missing"
    assert status["counts"].get("done", 0) == 0, "Job should NOT be done when image_metadata is missing"


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

    # Need a library for the metadata path to resolve
    from backend.metadata_store import create_library

    create_library([root], name="TestLib")
    stat = image.stat()
    assert index_file(
        image,
        image.name,
        image.parent,
        "image",
        stat.st_mtime,
        stat.st_size,
        64,
        64,
    )

    # Seed a metadata job
    _persist_metadata_index_jobs([image])
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
    assert status["counts"].get("done", 0) == 1, f"Job should be done after _run_job, got {status['counts']}"


# ---------------------------------------------------------------------------
# Test 9: Recovery resets running jobs to queued
# ---------------------------------------------------------------------------


def test_recovery_resets_running_jobs_to_queued(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """recover_metadata_index_jobs resets running jobs to queued,
    leaves queued jobs untouched, and wakes the worker."""
    from backend.indexer import metadata_worker

    now = time.time()
    # Clear any residual wake state
    metadata_worker._wake_event.clear()

    with _DB_LOCK, _connect() as conn:
        for state in ("running", "queued"):
            conn.execute(
                """
                INSERT INTO metadata_index_jobs (
                  path, name, parent_path, folder_path, root_path,
                  mtime, mtime_ns, size, state, queued_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(tmp_path / f"{state}.png"),
                    f"{state}.png",
                    str(tmp_path),
                    str(tmp_path),
                    str(tmp_path),
                    1000.0,
                    1000000000,
                    100,
                    state,
                    now,
                    now,
                ),
            )

    result = recover_metadata_index_jobs()

    assert result["running_reset"] == 1, f"Expected running_reset=1, got {result}"
    assert metadata_worker._wake_event.is_set(), "Worker should have been woken"

    with _DB_LOCK, _connect() as conn:
        rows = {row["path"]: row for row in conn.execute("SELECT path, state FROM metadata_index_jobs").fetchall()}

    running_path = str(tmp_path / "running.png")
    queued_path = str(tmp_path / "queued.png")

    running_row = rows.get(running_path)
    assert running_row is not None, "Running row should still exist"
    assert running_row["state"] == "queued", f"Running row should be reset to 'queued', got '{running_row['state']}'"

    queued_row = rows.get(queued_path)
    assert queued_row is not None, "Queued row should still exist"
    assert queued_row["state"] == "queued", f"Queued row should stay 'queued', got '{queued_row['state']}'"


# ---------------------------------------------------------------------------
# Test 10: Queued jobs survive restart and are processed by the worker
# ---------------------------------------------------------------------------


def test_queued_jobs_survive_restart(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """A queued metadata_index_job with matching file + asset is not affected
    by recovery; the worker later claims and completes it from SQLite."""

    root = tmp_path / "lib"
    root.mkdir()
    album = root / "album"
    album.mkdir()
    image = album / "test.png"
    create_test_png(image)
    stat = image.stat()

    # Seed asset + image_metadata
    _seed_asset_and_metadata(isolated_metadata_db, image, stat.st_mtime_ns, stat.st_size)

    # Seed a queued metadata_index_jobs row (simulates a pre-existing queued job)
    now = time.time()
    resolved = str(image.resolve())
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
            ),
        )

    # Recovery should NOT touch queued jobs
    result = recover_metadata_index_jobs()
    assert result["running_reset"] == 0

    # The worker can still claim and process this job from SQLite
    job = claim_next_metadata_job()
    assert job is not None, "Should be able to claim the queued job after recovery"
    assert job.path == resolved

    from backend.indexer import MetadataLifecycleWorker

    worker = MetadataLifecycleWorker()
    worker._run_job(job)

    # Verify job completed
    status = get_metadata_index_status(path=root)
    assert status["counts"].get("done", 0) == 1, f"Job should be done after _run_job, got {status['counts']}"
    # Verify asset is done
    with _DB_LOCK, _connect() as conn:
        asset_row = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_row is not None
    assert asset_row["metadata_state"] == "done", f"Asset should be 'done', got '{asset_row['metadata_state']}'"


# ---------------------------------------------------------------------------
# Test 11: Repair inconsistent done job
# ---------------------------------------------------------------------------


def test_repair_inconsistent_done_job(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """A done job with current image_metadata but pending asset state is
    repaired by recover_metadata_index_jobs."""
    root = tmp_path / "lib"
    root.mkdir()
    album = root / "album"
    album.mkdir()
    image = album / "test.png"
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    # Seed asset + image_metadata (metadata_state='pending')
    _seed_asset_and_metadata(isolated_metadata_db, image, stat.st_mtime_ns, stat.st_size)

    # Seed a DONE metadata_index_jobs row with matching identity
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, started_at, finished_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?, ?, ?)
            """,
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
                now,
                now,
            ),
        )

    # Verify pre-condition: asset is pending
    with _DB_LOCK, _connect() as conn:
        asset_before = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_before is not None
    assert asset_before["metadata_state"] == "pending", (
        f"Pre-condition: asset should be 'pending', got '{asset_before['metadata_state']}'"
    )

    result = recover_metadata_index_jobs()

    assert result["done_repaired"] == 1, f"Expected done_repaired=1, got {result}"
    assert result["done_demoted"] == 0, f"Expected done_demoted=0, got {result}"

    # Verify asset is now done
    with _DB_LOCK, _connect() as conn:
        asset_after = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_after is not None
    assert asset_after["metadata_state"] == "done", (
        f"Asset should be 'done' after repair, got '{asset_after['metadata_state']}'"
    )

    # Verify job stayed done
    status = get_metadata_index_status(path=root)
    assert status["counts"].get("done", 0) == 1, "Job should remain 'done' after repair"


def test_rebuild_metadata_worker_makes_library_status_ready(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """End-to-end producer-to-status coverage for scan/rebuild metadata identity."""
    from backend.indexer import MetadataLifecycleWorker, rebuild_index_scope
    from backend.metadata_store import claim_next_metadata_job
    from backend.metadata_store.status_store import build_catalog_status

    root = isolated_gallery_root / "ready-lib"
    root.mkdir()
    image = root / "asset.png"
    create_test_png(image)
    library = create_library([root], name="ReadyLib")
    library_id = int(library["id"])

    rebuild_index_scope(root)
    worker = MetadataLifecycleWorker()
    while job := claim_next_metadata_job():
        worker._run_job(job)

    metadata = build_catalog_status(library_id)["status"]["metadata"]
    assert metadata["total_assets"] == 1
    assert metadata["ready_assets"] == 1
    assert metadata["not_ready_assets"] == 0


def test_recovery_repairs_legacy_seconds_asset_mtime_and_stale_job(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """Legacy assets.mtime_ns seconds rows are backfilled and stale jobs restored."""
    from backend.metadata_store.status_store import build_catalog_status

    root = isolated_gallery_root / "legacy-lib"
    root.mkdir()
    image = root / "asset.png"
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())
    library = create_library([root], name="LegacyLib")
    library_id = int(library["id"])
    now = time.time()

    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO file_index (
              path, name, parent_path, type, mtime, mtime_ns, size,
              width, height, indexed_at, library_id
            ) VALUES (?, ?, ?, 'image', ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (resolved, image.name, str(root.resolve()), stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, library_id),
        )
        conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, NULL, NULL, ?, 'pending', 0, NULL)
            """,
            (library_id, resolved, str(root.resolve()), image.name, stat.st_mtime, stat.st_size, now),
        )
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, 64, 64, '{}', ?, ?)
            """,
            (resolved, image.name, stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, now),
        )
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, started_at, finished_at, updated_at,
              library_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'stale', ?, ?, ?, ?, ?)
            """,
            (
                resolved,
                image.name,
                str(root.resolve()),
                str(root.resolve()),
                str(root.resolve()),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
                now,
                now,
                library_id,
            ),
        )

    before = build_catalog_status(library_id)["status"]["metadata"]
    assert before["ready_assets"] == 0
    assert before["total_assets"] == 1

    result = recover_metadata_index_jobs()

    assert result["mtime_repaired_file_index"] == 1
    assert result["stale_repaired"] == 1
    after = build_catalog_status(library_id)["status"]["metadata"]
    assert after["ready_assets"] == 1
    assert after["not_ready_assets"] == 0


# ---------------------------------------------------------------------------
# Test 15: Crash between upsert and completion
# ---------------------------------------------------------------------------


def test_crash_between_upsert_and_completion(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """Simulate a crash after image_metadata was written but before
    complete_metadata_job ran: job is 'running', image_metadata exists,
    asset is 'pending'. Recovery resets the job to queued (NOT done) and
    preserves image_metadata. The worker can later re-complete it."""
    root = tmp_path / "lib"
    root.mkdir()
    album = root / "album"
    album.mkdir()
    image = album / "test.png"
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    # Seed asset + image_metadata (metadata_state='pending')
    _seed_asset_and_metadata(isolated_metadata_db, image, stat.st_mtime_ns, stat.st_size)

    # Seed a 'running' metadata_index_jobs row (crashed before completion)
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (
              path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
                now,
            ),
        )

    # Verify pre-conditions
    with _DB_LOCK, _connect() as conn:
        job_before = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (resolved,)).fetchone()
    assert job_before is not None
    assert job_before["state"] == "running", "Pre-condition: job should be 'running'"

    with _DB_LOCK, _connect() as conn:
        im_before = conn.execute("SELECT 1 FROM image_metadata WHERE path = ?", (resolved,)).fetchone()
    assert im_before is not None, "Pre-condition: image_metadata should exist"

    result = recover_metadata_index_jobs()

    # Job was running → reset to queued (NOT done)
    assert result["running_reset"] == 1, f"Expected running_reset=1, got {result}"
    assert result["done_repaired"] == 0, f"Expected done_repaired=0, got {result}"
    assert result["done_demoted"] == 0, f"Expected done_demoted=0, got {result}"

    # Verify job is now queued (NOT done)
    with _DB_LOCK, _connect() as conn:
        job_after = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (resolved,)).fetchone()
    assert job_after is not None
    assert job_after["state"] == "queued", f"Job should be reset to 'queued', got '{job_after['state']}'"

    # Verify asset stays pending
    with _DB_LOCK, _connect() as conn:
        asset_row = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_row is not None
    assert asset_row["metadata_state"] == "pending", (
        f"Asset should still be 'pending', got '{asset_row['metadata_state']}'"
    )

    # Verify image_metadata is NOT lost
    with _DB_LOCK, _connect() as conn:
        im_after = conn.execute("SELECT 1 FROM image_metadata WHERE path = ?", (resolved,)).fetchone()
    assert im_after is not None, "image_metadata should NOT be lost after recovery"

    # Now simulate the worker claiming and re-completing the job
    job = claim_next_metadata_job()
    assert job is not None, "Should be able to claim the reset job"
    assert job.path == resolved

    from backend.indexer import MetadataLifecycleWorker

    worker = MetadataLifecycleWorker()
    worker._run_job(job)

    # Verify job is done after re-completion
    status = get_metadata_index_status(path=root)
    assert status["counts"].get("done", 0) == 1, f"Job should be 'done' after re-completion, got {status['counts']}"

    with _DB_LOCK, _connect() as conn:
        asset_final = conn.execute(
            "SELECT metadata_state FROM assets WHERE path = ?",
            (resolved,),
        ).fetchone()
    assert asset_final is not None
    assert asset_final["metadata_state"] == "done", (
        f"Asset should be 'done' after re-completion, got '{asset_final['metadata_state']}'"
    )


# ---------------------------------------------------------------------------
# Migration test: legacy v1 DB missing additive columns
# ---------------------------------------------------------------------------


def test_legacy_v1_db_migration_adds_all_columns(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A legacy v1 database missing post-v1 additive columns is safely migrated
    by initialize_database() and recover_metadata_index_jobs() does not crash.

    Creates a minimal v1 schema, sets PRAGMA user_version=1, then calls
    initialize_database() and recover_metadata_index_jobs() to verify all
    additive columns/indexes exist and recovery runs without error.
    """
    import backend.metadata_store._db as _db
    from backend.metadata_store import initialize_database

    # Force re-initialization by clearing the global flag
    _db._DB_INITIALIZED = False

    # Connect directly to the isolated DB and create a minimal v1 schema
    # that *intentionally* misses post-v1 columns
    conn = sqlite3.connect(str(isolated_metadata_db))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS image_metadata (
          id INTEGER PRIMARY KEY,
          path TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          mtime REAL,
          mtime_ns INTEGER,
          size INTEGER,
          width INTEGER,
          height INTEGER,
          prompt TEXT,
          negative_prompt TEXT,
          model TEXT,
          sampler TEXT,
          seed TEXT,
          steps INTEGER,
          cfg_scale REAL,
          raw_metadata_text TEXT,
          metadata_json TEXT,
          indexed_at REAL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts USING fts5(
          name, prompt, negative_prompt, model, sampler, raw_metadata_text,
          content='image_metadata', content_rowid='id', tokenize='unicode61'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts_trigram USING fts5(
          name, prompt, negative_prompt, model, sampler, raw_metadata_text,
          content='image_metadata', content_rowid='id',
          tokenize='trigram', content='image_metadata_fts'
        );
        CREATE TABLE IF NOT EXISTS metadata_index_jobs (
          path TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          parent_path TEXT NOT NULL,
          mtime REAL,
          size INTEGER,
          state TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0,
          queued_at REAL,
          started_at REAL,
          finished_at REAL,
          updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS assets (
          library_id INTEGER NOT NULL,
          path TEXT NOT NULL,
          parent_path TEXT NOT NULL,
          name TEXT NOT NULL,
          type TEXT NOT NULL DEFAULT 'image',
          mtime_ns REAL,
          size INTEGER,
          width INTEGER,
          height INTEGER,
          indexed_at REAL,
          metadata_state TEXT NOT NULL DEFAULT 'pending',
          offline INTEGER NOT NULL DEFAULT 0,
          deleted_at REAL,
          UNIQUE(library_id, path)
        );
        CREATE TABLE IF NOT EXISTS image_dimensions (
          id INTEGER PRIMARY KEY,
          path TEXT NOT NULL UNIQUE,
          width INTEGER,
          height INTEGER,
          indexed_at REAL
        );
        CREATE TABLE IF NOT EXISTS folder_index_state (
          folder_path TEXT PRIMARY KEY,
          state TEXT NOT NULL DEFAULT 'pending',
          last_error TEXT,
          indexed_at REAL,
          updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS library_jobs (
          id INTEGER PRIMARY KEY,
          library_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'queued',
          scope_path TEXT,
          created_at REAL,
          started_at REAL,
          completed_at REAL,
          error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS derivative_jobs (
          id INTEGER PRIMARY KEY,
          derivative_id INTEGER NOT NULL,
          priority INTEGER NOT NULL DEFAULT 3,
          state TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0,
          created_at REAL,
          started_at REAL,
          completed_at REAL,
          updated_at REAL,
          error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS asset_derivatives (
          id INTEGER PRIMARY KEY,
          asset_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          variant TEXT NOT NULL,
          source_mtime_ns REAL,
          source_size INTEGER,
          status TEXT NOT NULL DEFAULT 'queued',
          cache_path TEXT,
          byte_size INTEGER,
          error_message TEXT,
          updated_at REAL,
          UNIQUE(asset_id, kind, variant)
        );
        CREATE TABLE IF NOT EXISTS file_index (
          path TEXT NOT NULL,
          name TEXT NOT NULL,
          parent_path TEXT NOT NULL,
          type TEXT NOT NULL DEFAULT 'file',
          mtime_ns REAL,
          size INTEGER,
          indexed_at REAL,
          PRIMARY KEY(path, parent_path)
        );
        CREATE TABLE IF NOT EXISTS libraries (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          scan_interval_hours REAL NOT NULL DEFAULT 24
        );
        CREATE TABLE IF NOT EXISTS library_exclusion_patterns (
          id INTEGER PRIMARY KEY,
          library_id INTEGER NOT NULL,
          pattern TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          UNIQUE(library_id, pattern),
          UNIQUE(library_id, position)
        );
        CREATE TABLE IF NOT EXISTS catalog_rebuild_entries (
          job_id INTEGER NOT NULL,
          path TEXT NOT NULL,
          library_id INTEGER NOT NULL,
          parent_path TEXT NOT NULL,
          name TEXT NOT NULL,
          type TEXT NOT NULL,
          mtime_ns REAL,
          size INTEGER,
          width INTEGER,
          height INTEGER,
          metadata_state TEXT,
          PRIMARY KEY(job_id, path)
        );
        PRAGMA user_version = 1;
    """)
    conn.close()

    # Now call initialize_database() — this should run _ensure_post_v1_additive_columns
    initialize_database()

    # Verify the critical additive columns exist by querying each table
    with _DB_LOCK, sqlite3.connect(str(isolated_metadata_db)) as check:
        check.row_factory = sqlite3.Row

        # metadata_index_jobs additive columns
        cols = {r[1] for r in check.execute("PRAGMA table_info(metadata_index_jobs)").fetchall()}
        for col in ("folder_path", "root_path", "library_id", "priority", "mtime_ns"):
            assert col in cols, f"metadata_index_jobs missing column '{col}' after migration"

        # image_metadata additive columns
        cols = {r[1] for r in check.execute("PRAGMA table_info(image_metadata)").fetchall()}
        for col in (
            "format",
            "mode",
            "has_alpha",
            "updated_at",
            "tool",
            "scheduler",
            "model_hash",
            "lora_text",
            "generation_time",
            "clip_skip",
            "hires_upscale",
            "hires_steps",
            "denoising_strength",
            "vae",
            "ensd",
            "aesthetic_score",
            "date",
            "aspect_ratio",
        ):
            assert col in cols, f"image_metadata missing column '{col}' after migration"

        # file_index additive columns
        cols = {r[1] for r in check.execute("PRAGMA table_info(file_index)").fetchall()}
        for col in ("library_id", "mtime_ns", "last_seen_scan_job_id"):
            assert col in cols, f"file_index missing column '{col}' after migration"

        # assets additive columns
        cols = {r[1] for r in check.execute("PRAGMA table_info(assets)").fetchall()}
        for col in ("mime_type", "duration_ms", "codec", "last_seen_scan_job_id"):
            assert col in cols, f"assets missing column '{col}' after migration"

        # library_jobs additive columns
        cols = {r[1] for r in check.execute("PRAGMA table_info(library_jobs)").fetchall()}
        for col in (
            "scope_path",
            "trigger",
            "priority",
            "discovered_assets",
            "created_assets",
            "updated_assets",
            "offline_assets",
            "metadata_queued_assets",
        ):
            assert col in cols, f"library_jobs missing column '{col}' after migration"

        # Verify indexes exist
        idx_info = {r[1] for r in check.execute("SELECT * FROM sqlite_master WHERE type='index'").fetchall()}
        for idx in (
            "idx_metadata_index_jobs_claim",
            "idx_metadata_index_jobs_library_state",
            "idx_assets_metadata_state",
            "idx_image_metadata_mtime_size",
        ):
            assert idx in idx_info, f"Missing index '{idx}' after migration"

    # Verify recover_metadata_index_jobs() does not crash on the migrated DB
    import backend.indexer as indexer_mod
    from backend.indexer import recover_metadata_index_jobs

    # Reset the module-level initialized flag so recovery uses this DB
    monkeypatch.setattr(indexer_mod, "metadata_worker", type("FakeWorker", (), {"wake": lambda self: None})())
    result = recover_metadata_index_jobs()
    assert isinstance(result, dict)
    assert "running_reset" in result
    assert "done_repaired" in result
    assert "done_demoted" in result
    assert "done_skipped" in result


# ---------------------------------------------------------------------------
# Regression: complete_metadata_job with no asset row → skipped
# ---------------------------------------------------------------------------


def test_complete_metadata_job_skipped_when_no_asset_row(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """complete_metadata_job marks job skipped when no asset row exists for the path."""
    image = tmp_path / "lib" / "noasset.png"
    image.parent.mkdir(parents=True)
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    initialize_database()
    now = time.time()

    # Seed image_metadata but no asset row
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, metadata_json, updated_at, indexed_at)
            VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
            """,
            (resolved, image.name, stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, now),
        )
        # Seed a running job
        conn.execute(
            """
            INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
            ),
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

    with _DB_LOCK, _connect() as conn:
        job_row = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (resolved,)).fetchone()
    assert job_row is not None
    assert job_row["state"] == "skipped", f"Expected skipped, got {job_row['state']}"


# ---------------------------------------------------------------------------
# Regression: complete_metadata_job with stale asset version → stale
# ---------------------------------------------------------------------------


def test_complete_metadata_job_stale_when_asset_version_mismatch(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """complete_metadata_job marks stale when asset row exists but version mismatches."""
    image = tmp_path / "lib" / "staleasset.png"
    image.parent.mkdir(parents=True)
    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    lib = create_library([image.parent.parent], name="TestLib")
    library_id = int(lib["id"])
    now = time.time()

    # Seed asset with DIFFERENT mtime_ns (stale version)
    stale_mtime_ns = stat.st_mtime_ns - 1_000_000_000
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
               indexed_at, metadata_state) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 'pending')""",
            (library_id, resolved, str(image.parent), image.name, stale_mtime_ns, stat.st_size, now),
        )
        # Seed image_metadata matching the JOB version
        conn.execute(
            """INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, metadata_json, updated_at, indexed_at)
            VALUES (?, ?, ?, ?, ?, '{}', ?, ?)""",
            (resolved, image.name, stat.st_mtime, stat.st_mtime_ns, stat.st_size, now, now),
        )
        # Seed a running job
        conn.execute(
            """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path,
              mtime, mtime_ns, size, state, queued_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
            (
                resolved,
                image.name,
                str(image.parent),
                str(image.parent),
                str(image.parent.parent),
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                now,
                now,
            ),
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

    with _DB_LOCK, _connect() as conn:
        job_row = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (resolved,)).fetchone()
    assert job_row is not None
    assert job_row["state"] == "stale", f"Expected stale, got {job_row['state']}"


def test_stale_metadata_persistence_preserves_newer_asset_identity(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """Metadata extracted for an old version cannot restore that asset identity."""
    root = tmp_path / "lib"
    root.mkdir()
    image = root / "race.png"
    create_test_png(image, size=(64, 64))
    create_library([root], name="Race")
    stat = image.stat()
    assert index_file(
        image,
        image.name,
        image.parent,
        "image",
        stat.st_mtime,
        stat.st_size,
        64,
        64,
    )
    stale_metadata = extract_metadata(image)

    newer_mtime_ns = stale_metadata.mtime_ns + 1_000_000_000
    newer_size = stale_metadata.size + 17
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE assets SET mtime_ns = ?, size = ?, width = 999, height = 888 WHERE path = ?",
            (newer_mtime_ns, newer_size, stale_metadata.path),
        )

    assert upsert_metadata_batch([stale_metadata]) == 0

    with _DB_LOCK, _connect() as conn:
        asset = conn.execute(
            "SELECT mtime_ns, size, width, height FROM assets WHERE path = ?",
            (stale_metadata.path,),
        ).fetchone()
        metadata_row = conn.execute(
            "SELECT 1 FROM image_metadata WHERE path = ?",
            (stale_metadata.path,),
        ).fetchone()
    assert asset is not None
    assert abs(float(asset["mtime_ns"]) - float(newer_mtime_ns)) < 1000
    assert asset["size"] == newer_size
    assert asset["width"] == 999
    assert asset["height"] == 888
    assert metadata_row is None


# ---------------------------------------------------------------------------
# Regression: priority is persisted and claim_next_metadata_job picks lower numeric first
# ---------------------------------------------------------------------------


def test_priority_persisted_and_claim_order(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """dispatch_metadata_index_paths with priority=1 is claimed before priority=3."""
    initialize_database()
    img1 = tmp_path / "p1.png"
    img1.write_bytes(b"data")
    img2 = tmp_path / "p3.png"
    img2.write_bytes(b"data")

    dispatch_metadata_index_paths([img1], priority=1)
    dispatch_metadata_index_paths([img2], priority=3)

    # Verify priority persisted
    with _DB_LOCK, _connect() as conn:
        rows = {r["path"]: r for r in conn.execute("SELECT path, priority FROM metadata_index_jobs").fetchall()}
    assert rows[str(img1.resolve())]["priority"] == 1
    assert rows[str(img2.resolve())]["priority"] == 3

    # Claim should return the lower-number (higher-priority) job first
    first = claim_next_metadata_job()
    assert first is not None
    assert first.path == str(img1.resolve()), f"Expected priority 1 job first, got {first.path}"

    second = claim_next_metadata_job()
    assert second is not None
    assert second.path == str(img2.resolve()), f"Expected priority 3 job second, got {second.path}"


# ---------------------------------------------------------------------------
# Regression: recovery handles >1000 running jobs and fails exhausted attempts
# ---------------------------------------------------------------------------


def test_recovery_more_than_1000_running_jobs(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """recover_metadata_index_jobs handles more than 1000 running jobs (unbounded)."""
    initialize_database()
    now = time.time()

    # Insert 1001 running jobs
    with _DB_LOCK, _connect() as conn:
        for i in range(1001):
            path = str(tmp_path / f"img{i}.png")
            conn.execute(
                """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path,
                   mtime, mtime_ns, size, state, queued_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1.0, 1000000000, 100, 'running', ?, ?)""",
                (path, f"img{i}.png", str(tmp_path), str(tmp_path), str(tmp_path), now, now),
            )

    # Suppress wake to avoid worker interference
    metadata_worker._wake_event.clear()
    result = recover_metadata_index_jobs()

    assert result["running_reset"] == 1001, f"Expected 1001 running_reset, got {result}"

    # All should now be queued
    with _DB_LOCK, _connect() as conn:
        queued = conn.execute("SELECT count(*) FROM metadata_index_jobs WHERE state = 'queued'").fetchone()[0]
    assert queued == 1001, f"Expected 1001 queued, got {queued}"


def test_recovery_fails_exhausted_attempts(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """recover_metadata_index_jobs fails running jobs with attempts >= MAX."""
    initialize_database()
    now = time.time()

    exhausted_path = str(tmp_path / "exhausted.png")
    recoverable_path = str(tmp_path / "recoverable.png")

    with _DB_LOCK, _connect() as conn:
        for path, attempts in [(exhausted_path, MAX_METADATA_JOB_ATTEMPTS), (recoverable_path, 1)]:
            conn.execute(
                """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path,
                   mtime, mtime_ns, size, state, attempts, queued_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1.0, 1000000000, 100, 'running', ?, ?, ?)""",
                (path, Path(path).name, str(tmp_path), str(tmp_path), str(tmp_path), attempts, now, now),
            )

    metadata_worker._wake_event.clear()
    result = recover_metadata_index_jobs()

    assert result["running_reset"] == 1, f"Expected 1 running_reset, got {result}"
    assert result["running_failed_exhausted"] == 1, f"Expected 1 running_failed_exhausted, got {result}"

    with _DB_LOCK, _connect() as conn:
        exhausted_state = conn.execute(
            "SELECT state FROM metadata_index_jobs WHERE path = ?", (exhausted_path,)
        ).fetchone()["state"]
        recoverable_state = conn.execute(
            "SELECT state FROM metadata_index_jobs WHERE path = ?", (recoverable_path,)
        ).fetchone()["state"]

    assert exhausted_state == "failed", f"Exhausted job should be failed, got {exhausted_state}"
    assert recoverable_state == "queued", f"Recoverable job should be queued, got {recoverable_state}"


# ---------------------------------------------------------------------------
# Regression: legacy image_metadata.mtime_ns NULL + matching mtime/size
# ---------------------------------------------------------------------------


def test_legacy_mtime_ns_null_matching_through_persist(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """Legacy image_metadata row with mtime_ns=NULL but matching mtime/size
    should result in job done/skipped and asset metadata_state='done'."""
    root = tmp_path / "lib"
    root.mkdir()
    image = root / "test.png"
    from tests.conftest import create_test_png

    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    lib = create_library([root], name="TestLib")
    library_id = int(lib["id"])
    now = time.time()

    # Seed asset row
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
               indexed_at, metadata_state) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 'pending')""",
            (library_id, resolved, str(image.parent), image.name, stat.st_mtime_ns, stat.st_size, now),
        )
        # Seed legacy image_metadata with mtime_ns=NULL
        conn.execute(
            """INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, metadata_json, updated_at, indexed_at)
            VALUES (?, ?, ?, NULL, ?, '{}', ?, ?)""",
            (resolved, image.name, stat.st_mtime, stat.st_size, now, now),
        )

    # Call _persist_metadata_index_jobs — the "already current" shortcut
    # should fire, matching the legacy row by mtime + size
    result = _persist_metadata_index_jobs([image])
    assert result.skipped >= 1, "Expected at least 1 skipped (already current)"

    with _DB_LOCK, _connect() as conn:
        job_state = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (resolved,)).fetchone()
        asset_state = conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (resolved,)).fetchone()

    assert job_state is not None
    # _mark_current_metadata_done delegates to complete_metadata_job which may skip
    # since asset version matches → done
    assert job_state["state"] in ("done", "skipped"), f"Expected done or skipped, got {job_state['state']}"
    assert asset_state is not None
    assert asset_state["metadata_state"] == "done", (
        f"Asset metadata_state should be 'done', got {asset_state['metadata_state']}"
    )


# ---------------------------------------------------------------------------
# Regression: get_metadata_lifecycle_status returns correct counters
# ---------------------------------------------------------------------------


def test_metadata_runtime_scope_escapes_like_wildcards(tmp_path: Path):
    from backend.indexer import _metadata_runtime_scope_sql

    scope = tmp_path / r"percent%_back\slash"
    sql, params = _metadata_runtime_scope_sql(scope)

    assert "ESCAPE '\\'" in sql
    assert params[1].endswith("percent\\%\\_back\\\\slash/%")


def test_get_metadata_lifecycle_status_returns_counters(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """get_metadata_lifecycle_status returns all 15 counters with correct values."""
    from backend.indexer import get_metadata_lifecycle_status

    initialize_database()
    now = time.time()
    root = tmp_path / "lib"
    root.mkdir()
    image = root / "test.png"
    from tests.conftest import create_test_png

    create_test_png(image)
    stat = image.stat()
    resolved = str(image.resolve())

    lib = create_library([root], name="Lib")
    library_id = int(lib["id"])

    # Seed asset with matching version + NON-matching image_metadata so the
    # "already current" shortcut does not fire and the job stays queued.
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
               indexed_at, metadata_state) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 'done')""",
            (library_id, resolved, str(image.parent), image.name, stat.st_mtime_ns, stat.st_size, now),
        )
        # Deliberately different mtime/size so _current_metadata_is_complete returns False
        conn.execute(
            """INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, metadata_json, updated_at, indexed_at)
            VALUES (?, ?, 1.0, 1000, 999, '{}', ?, ?)""",
            (resolved, image.name, now, now),
        )

    # Seed a queued job (will not be shortcut because image_metadata doesn't match)
    dispatch_metadata_index_paths([image], priority=2)

    result = get_metadata_lifecycle_status()
    assert isinstance(result, dict)
    assert result["queued_metadata_jobs"] >= 1
    assert result["done_metadata_jobs"] >= 0
    assert result["running_metadata_jobs"] == 0
    assert result["failed_metadata_jobs"] == 0
    assert result["stale_metadata_jobs"] == 0
    assert result["skipped_metadata_jobs"] == 0
    assert isinstance(result["oldest_queued_metadata_job_age"], (int, float, type(None)))
    assert isinstance(result["done_jobs_with_pending_assets"], int)
    assert isinstance(result["current_image_metadata_with_pending_assets"], int)
    assert isinstance(result["metadata_jobs_without_matching_assets"], int)
    assert isinstance(result["assets_done_but_metadata_missing_or_stale"], int)
    assert isinstance(result["repairable_metadata_assets"], int)
    assert isinstance(result["metadata_worker_alive"], bool)
    assert "metadata_worker_last_claimed_at" in result
    assert "metadata_worker_last_completed_at" in result
