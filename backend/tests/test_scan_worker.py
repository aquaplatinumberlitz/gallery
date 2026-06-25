"""
Purpose:
Characterization tests for Bug 1: rebuild schedules DB jobs but does not
dispatch runtime metadata work, so metadata_index_jobs rows can exist in
SQLite without a matching in-memory _job_queue entry.

Guarantees:
* After execute_rebuild_job, metadata_index_jobs rows exist in SQLite
* After execute_rebuild_job, indexer._job_queue.qsize() == 0 (the bug)
* These tests capture the buggy behavior before the refactor fixes it

Run when:
* touching rebuild/index tests or metadata job scheduling behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.metadata_store import _connect, create_library, initialize_database
from backend.metadata_store.metadata_queue import get_metadata_index_status
from backend.scan_worker import execute_rebuild_job, queue_rebuild
from tests.conftest import create_test_png


def test_rebuild_schedules_db_jobs_but_not_runtime_dispatch(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Rebuild creates metadata_index_jobs rows in SQLite but does NOT
    enqueue them into indexer._job_queue (the in-memory runtime queue).

    This is Bug 1: a DB job can exist without runtime worker dispatch.
    After the D full clean refactor, this test should be updated to assert
    that the DB-claim worker processes these jobs directly from SQLite.
    """
    import backend.indexer as indexer
    from backend.metadata_store.job_store import _initialize_database as _init_jobs_db

    _init_jobs_db()

    # Create library with an import path containing an image
    root = isolated_gallery_root / "lib"
    root.mkdir()
    album = root / "album_a"
    album.mkdir(parents=True)
    image = album / "test.png"
    create_test_png(image)

    lib = create_library([root], name="TestLib")
    library_id = int(lib["id"])

    # Drain any pre-existing items in the in-memory job queue
    while not indexer._job_queue.empty():
        indexer._job_queue.get_nowait()

    # Queue a rebuild job (creates a real library_jobs row)
    job, _created = queue_rebuild(library_id)
    job_id = int(job["id"])

    # Claim it the same way scan_worker.run_once does
    from backend.metadata_store.job_store import claim_next_catalog_job

    claimed = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed is not None, "Should be able to claim the rebuild job"
    assert int(claimed["id"]) == job_id

    success = execute_rebuild_job(claimed)
    assert success, "Rebuild job should succeed"

    # Verify metadata_index_jobs rows exist in SQLite
    status = get_metadata_index_status(path=root)
    assert status["total"] > 0, (
        "Expected metadata_index_jobs rows in SQLite after rebuild, "
        f"got total={status['total']}"
    )
    assert status["counts"].get("queued", 0) > 0, (
        "Expected queued metadata jobs, "
        f"got counts={status['counts']}"
    )

    # THE BUG: _job_queue is empty because execute_rebuild_job calls
    # queue_metadata_index_paths (DB-only) and does NOT call
    # _enqueue_metadata_jobs_from_result
    assert indexer._job_queue.qsize() == 0, (
        "Bug 1: rebuild path should NOT populate the in-memory job queue "
        "(the DB-claim worker will replace this in Phase 1)"
    )
