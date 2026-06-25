"""
Purpose:
Phase 2 test: rebuild path now schedules metadata jobs through
dispatch_metadata_index_paths which persists in SQLite and wakes the
DB-claim worker. The in-memory _job_queue is no longer the source of work.

Guarantees:
* After execute_rebuild_job, metadata_index_jobs rows exist in SQLite
* After execute_rebuild_job, indexer._job_queue.qsize() == 0 (DB-claim worker
  claims from SQLite, not from memory)
* dispatch_metadata_index_paths is called (not raw queue_metadata_index_paths)

Run when:
* touching rebuild/index tests or metadata job scheduling behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.metadata_store import create_library
from backend.metadata_store.metadata_queue import get_metadata_index_status
from backend.scan_worker import execute_rebuild_job, queue_rebuild
from tests.conftest import create_test_png


def test_rebuild_path_uses_dispatch_metadata_index_paths(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Rebuild creates metadata_index_jobs rows in SQLite and wakes the
    DB-claim worker via dispatch_metadata_index_paths.

    The in-memory _job_queue is NOT populated because the DB-claim worker
    claims directly from SQLite (Phase 2).
    """
    import backend.indexer as indexer
    from backend.metadata_store.job_store import _initialize_database as _init_jobs_db

    _init_jobs_db()

    # Track calls to dispatch_metadata_index_paths
    dispatch_calls = []
    original_dispatch = indexer.dispatch_metadata_index_paths

    def tracking_dispatch(paths, root_path=None, **kwargs):
        dispatch_calls.append(
            (list(paths) if hasattr(paths, "__iter__") else [str(paths)], str(root_path) if root_path else None)
        )
        return original_dispatch(paths, root_path, **kwargs)

    monkeypatch.setattr(indexer, "dispatch_metadata_index_paths", tracking_dispatch)

    # scan_worker imports dispatch at module level; patch its reference too
    import backend.scan_worker as scan_worker_mod

    monkeypatch.setattr(scan_worker_mod, "dispatch_metadata_index_paths", tracking_dispatch)

    root = isolated_gallery_root / "lib"
    root.mkdir()
    album = root / "album_a"
    album.mkdir(parents=True)
    image = album / "test.png"
    create_test_png(image)

    lib = create_library([root], name="TestLib")
    library_id = int(lib["id"])

    job, _created = queue_rebuild(library_id)
    job_id = int(job["id"])

    from backend.metadata_store.job_store import claim_next_catalog_job

    claimed = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed is not None, "Should be able to claim the rebuild job"
    assert int(claimed["id"]) == job_id

    success = execute_rebuild_job(claimed)
    assert success, "Rebuild job should succeed"

    # Verify dispatch_metadata_index_paths was called (not raw queue)
    assert len(dispatch_calls) > 0, "Rebuild path should call dispatch_metadata_index_paths"

    # Verify metadata_index_jobs rows exist in SQLite
    status = get_metadata_index_status(path=root)
    assert status["total"] > 0, (
        f"Expected metadata_index_jobs rows in SQLite after rebuild, got total={status['total']}"
    )
    assert status["counts"].get("queued", 0) > 0, f"Expected queued metadata jobs, got counts={status['counts']}"
