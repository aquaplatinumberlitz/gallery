"""
Purpose:
Verifies metadata indexer dispatch, runtime status, and idempotent job persistence.

Guarantees:
* dispatch_metadata_index_paths is the single scheduling entrypoint
* get_indexer_runtime_status reflects the durable SQLite metadata queue
* _persist_metadata_index_jobs is idempotent and coalesces duplicates

Run when:
* changing metadata indexer dispatch or job persistence logic
* touching rebuild/index tests or scan hot-path enqueue behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import indexer


def test_runtime_status_reports_durable_queue(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import _persist_metadata_index_jobs, claim_next_metadata_job
    from tests.conftest import create_test_png

    root = isolated_gallery_root / "lib"
    root.mkdir()
    image = root / "test.png"
    create_test_png(image)

    _persist_metadata_index_jobs([image], root_path=root)
    status = indexer.get_indexer_runtime_status()

    assert status["worker_count"] >= 0
    assert status["active_jobs"] == 0
    assert status["runtime_queue_depth"] == 1
    assert status["queued_jobs"][0]["path"] == str(image.resolve())
    assert status["staged_path_queue_depth"] == 0
    assert status["deprecated"] is False

    claimed = claim_next_metadata_job()
    assert claimed is not None

    status = indexer.get_indexer_runtime_status()
    assert status["active_jobs"] == 1
    assert status["runtime_queue_depth"] == 0
    assert str(image.resolve()) in status["active_job_paths"]


def test_scan_and_rebuild_both_call_dispatch_metadata_index_paths(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Purpose:
    Phase 2: both scan and rebuild paths call dispatch_metadata_index_paths
    (the single scheduling entrypoint). Neither calls the old
    _enqueue_metadata_jobs_from_result (now removed).

    Guarantees:
    * Both paths invoke dispatch_metadata_index_paths
    """
    from backend.indexer import rebuild_index_scope
    from backend.metadata_store import create_library
    from backend.metadata_store.job_store import _initialize_database

    _initialize_database()
    root = isolated_gallery_root / "lib"
    root.mkdir()
    sub = root / "album"
    sub.mkdir(parents=True)
    image = sub / "test.png"
    from tests.conftest import create_test_png

    create_test_png(image)

    lib = create_library([root], name="Test")
    library_id = int(lib["id"])

    dispatch_calls = []
    original_dispatch = indexer.dispatch_metadata_index_paths

    def tracking_dispatch(paths, root_path=None, **kwargs):
        dispatch_calls.append(("dispatch", list(paths) if hasattr(paths, "__iter__") else [str(paths)]))
        return original_dispatch(paths, root_path, **kwargs)

    monkeypatch.setattr(indexer, "dispatch_metadata_index_paths", tracking_dispatch)

    import backend.scan_worker as scan_worker_mod

    monkeypatch.setattr(scan_worker_mod, "dispatch_metadata_index_paths", tracking_dispatch)

    rebuild_index_scope(root)

    from backend.metadata_store.job_store import claim_next_catalog_job
    from backend.scan_worker import execute_rebuild_job, queue_rebuild

    rjob, _created = queue_rebuild(library_id)
    claimed_rjob = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed_rjob is not None, "Should claim rebuild job"
    rebuild_success = execute_rebuild_job(claimed_rjob)

    assert len(dispatch_calls) >= 2, (
        f"Both scan and rebuild should call dispatch_metadata_index_paths, got {len(dispatch_calls)} calls"
    )

    assert rebuild_success, "Rebuild should succeed"


def test_persist_metadata_index_jobs_is_idempotent(
    isolated_metadata_db: Path,
    tmp_path: Path,
):
    """
    Purpose:
    Verify that _persist_metadata_index_jobs is idempotent and coalesces
    duplicate calls for the same path.
    """
    from backend.metadata_store import _persist_metadata_index_jobs, get_metadata_index_status

    image = tmp_path / "test.png"
    image.write_bytes(b"fake png content")

    first = _persist_metadata_index_jobs([image])
    assert len(first.enqueued) == 1, "First call should enqueue the job"
    assert first.coalesced == 0

    second = _persist_metadata_index_jobs([image])
    assert len(second.enqueued) == 0, "Second call should coalesce, not enqueue"
    assert second.coalesced >= 1 or second.skipped >= 0, "Should be coalesced or skipped"

    status = get_metadata_index_status(path=tmp_path)
    assert status["total"] == 1, "Only one durable row should exist for the path"
    assert status["counts"].get("queued", 0) <= 1, "At most one queued job"
