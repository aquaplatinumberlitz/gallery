"""IM-4: prompt_values and workflow_properties build on their own once a library's metadata is complete.

Purpose:
Before this change the two derived indexes were scheduled after a metadata commit only when they were
already initialized, so a new library never built them and prompt-group and workflow search answered 503
until someone pressed Rebuild in Advanced Search. They read only persisted ``image_metadata`` rows, so
they are cheap (measured in ``docs/ARCHITECTURE.md``) and now build automatically.

Guarantees:
* a new library gets one ``prompt_values`` and one ``workflow_properties`` job when its last metadata job
  completes, and none while metadata jobs are still queued or running;
* ``workflow_raw`` (own storage budget) is never scheduled automatically;
* repeated completions coalesce into the single active job per index;
* a library that predates auto-building (metadata done, no index state) is scheduled at startup, a library
  whose indexes are already ready at the current versions is left alone, and a stale or failed index is
  scheduled again;
* the app lifespan runs that startup scheduling and a failure there never blocks startup;
* after the single index worker drains the jobs, prompt-group and workflow search stop answering 503.

Run when:
Changing ``_schedule_derived_search_backfills``, ``schedule_auto_built_search_indexes``,
``schedule_startup_search_index_backfills``, the metadata completion hook, or the search-index registry.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend import search_indexer
from backend.indexer import MetadataLifecycleWorker
from backend.metadata_store import create_library, index_directory_tree
from backend.metadata_store._db import open_connection
from backend.search_indexer import (
    SearchIndexDefinition,
    get_search_index_definition,
    register_search_index_definition,
    run_search_index_once,
    schedule_startup_search_index_backfills,
)
from tests.conftest import create_test_png
from tests.worker_contention_support import seed_queued_metadata_jobs

AUTO = {"prompt_values", "workflow_properties"}


def _jobs(db_path: Path) -> list[tuple[int, str, str]]:
    with open_connection(db_path) as conn:
        return [
            (int(row[0]), str(row[1]), str(row[2]))
            for row in conn.execute("SELECT library_id, index_name, state FROM search_index_jobs ORDER BY id")
        ]


def _index_names(db_path: Path) -> set[str]:
    return {name for _library_id, name, _state in _jobs(db_path)}


def _worker() -> MetadataLifecycleWorker:
    return MetadataLifecycleWorker(worker_count=1, lease_seconds=30, write_retry_delays=())


def _run_one_metadata_job(worker: MetadataLifecycleWorker) -> None:
    job = worker._claim_job()
    assert job is not None
    worker._run_job(job)


@pytest.fixture
def raw_workflow_enabled(monkeypatch: pytest.MonkeyPatch):
    """Make ``workflow_raw`` an enabled index, so only the scheduling policy keeps it opt-in."""
    original = get_search_index_definition("workflow_raw")
    assert original is not None
    register_search_index_definition(
        SearchIndexDefinition(
            name="workflow_raw",
            schema_version=original.schema_version,
            extractor_version=original.extractor_version,
            enabled=True,
            required_mode="raw",
            extractor=original.extractor,
            persist=original.persist,
        )
    )
    yield
    register_search_index_definition(original)


def test_new_library_builds_both_indexes_once_its_metadata_work_is_complete(
    isolated_metadata_db: Path, isolated_gallery_root: Path, raw_workflow_enabled: None
) -> None:
    library_id, _images = seed_queued_metadata_jobs(isolated_gallery_root / "lib", 3)
    worker = _worker()

    _run_one_metadata_job(worker)
    _run_one_metadata_job(worker)
    assert _index_names(isolated_metadata_db) & AUTO == set(), "metadata jobs are still queued: not yet"

    _run_one_metadata_job(worker)
    jobs = _jobs(isolated_metadata_db)
    assert {(lib, name) for lib, name, _state in jobs if name in AUTO} == {
        (library_id, "prompt_values"),
        (library_id, "workflow_properties"),
    }
    assert all(state == "queued" for _lib, name, state in jobs if name in AUTO)
    assert "workflow_raw" not in _index_names(isolated_metadata_db), "workflow_raw stays opt-in"


def test_completions_coalesce_into_one_active_job_per_index(
    isolated_metadata_db: Path, isolated_gallery_root: Path
) -> None:
    library_id, images = seed_queued_metadata_jobs(isolated_gallery_root / "lib", 1)
    worker = _worker()
    _run_one_metadata_job(worker)
    from backend.metadata_store import schedule_derived_search_backfills

    schedule_derived_search_backfills(library_id)
    schedule_derived_search_backfills(library_id)

    jobs = [name for _lib, name, _state in _jobs(isolated_metadata_db) if name in AUTO]
    assert sorted(jobs) == ["prompt_values", "workflow_properties"]
    assert images


def test_scheduled_indexes_become_usable_without_a_manual_rebuild(
    isolated_app, isolated_metadata_db: Path, isolated_gallery_root: Path
) -> None:
    library_id, _images = seed_queued_metadata_jobs(isolated_gallery_root / "lib", 2)
    worker = _worker()
    _run_one_metadata_job(worker)
    _run_one_metadata_job(worker)

    for _ in range(40):
        if not run_search_index_once(worker_id="auto-build-test"):
            break
    states = {
        item["index_name"]: item
        for item in isolated_app.get("/api/search/indexes", params={"library_id": library_id}).json()
    }
    assert states["prompt_values"]["state"] == "ready" and states["prompt_values"]["usable"] is True
    assert states["workflow_properties"]["state"] == "ready" and states["workflow_properties"]["usable"] is True
    assert states["workflow_raw"]["state"] in {"pending", "disabled"}


def test_startup_schedules_both_indexes_for_a_library_that_predates_auto_building(
    isolated_metadata_db: Path, isolated_gallery_root: Path, raw_workflow_enabled: None
) -> None:
    root = isolated_gallery_root / "old"
    root.mkdir()
    create_test_png(root / "a.png")
    create_test_png(root / "b.png")
    library_id = int(create_library([root], name="Old")["id"])
    index_directory_tree(root, include_metadata=True)
    with open_connection(isolated_metadata_db) as conn:  # what an upgraded database looks like
        conn.execute("DELETE FROM search_index_jobs")
        conn.execute("DELETE FROM search_index_states")
    assert _jobs(isolated_metadata_db) == []

    scheduled = schedule_startup_search_index_backfills()

    assert set(scheduled) == {(library_id, "prompt_values"), (library_id, "workflow_properties")}
    assert _index_names(isolated_metadata_db) == AUTO, "workflow_raw is not part of auto-building"


def test_startup_leaves_ready_indexes_alone_and_rebuilds_stale_or_failed_ones(
    isolated_metadata_db: Path, isolated_gallery_root: Path
) -> None:
    library_id, _images = seed_queued_metadata_jobs(isolated_gallery_root / "lib", 1)
    _run_one_metadata_job(_worker())
    for _ in range(40):
        if not run_search_index_once(worker_id="auto-build-test"):
            break
    job_count = len(_jobs(isolated_metadata_db))

    assert schedule_startup_search_index_backfills() == [], "already ready: a restart adds no job"
    assert len(_jobs(isolated_metadata_db)) == job_count

    with open_connection(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE search_index_states SET state = 'failed' WHERE index_name = 'prompt_values' AND library_id = ?",
            (library_id,),
        )
        conn.execute(
            "UPDATE search_index_states SET extractor_version = 0 "
            "WHERE index_name = 'workflow_properties' AND library_id = ?",
            (library_id,),
        )
    assert set(schedule_startup_search_index_backfills()) == {
        (library_id, "prompt_values"),
        (library_id, "workflow_properties"),
    }


def test_startup_waits_for_a_library_that_still_has_metadata_work(
    isolated_metadata_db: Path, isolated_gallery_root: Path
) -> None:
    seed_queued_metadata_jobs(isolated_gallery_root / "lib", 2)
    assert schedule_startup_search_index_backfills() == []
    assert _jobs(isolated_metadata_db) == []


def test_app_lifespan_schedules_the_startup_backfills(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    disable_background_services: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = isolated_gallery_root / "old"
    root.mkdir()
    create_test_png(root / "a.png")
    library_id = int(create_library([root], name="Old")["id"])
    index_directory_tree(root, include_metadata=True)
    with open_connection(isolated_metadata_db) as conn:
        conn.execute("DELETE FROM search_index_jobs")
        conn.execute("DELETE FROM search_index_states")
    import backend.app as app_module

    monkeypatch.setattr(app_module, "GALLERY_SEARCH_INDEXER_ENABLED", True)
    monkeypatch.setattr(search_indexer.search_index_worker, "start", lambda: None)
    monkeypatch.setattr(search_indexer.search_index_worker, "stop", lambda: True)

    async def run_lifespan() -> None:
        async with app_module.app.router.lifespan_context(app_module.app):
            pass

    asyncio.run(run_lifespan())
    assert {(lib, name) for lib, name, _state in _jobs(isolated_metadata_db)} == {
        (library_id, "prompt_values"),
        (library_id, "workflow_properties"),
    }


def test_startup_scheduling_failure_does_not_block_app_startup(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    disable_background_services: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app as app_module

    def boom() -> list:
        raise RuntimeError("scheduler broke")

    monkeypatch.setattr(app_module, "GALLERY_SEARCH_INDEXER_ENABLED", True)
    monkeypatch.setattr(app_module, "schedule_startup_search_index_backfills", boom)
    monkeypatch.setattr(search_indexer.search_index_worker, "start", lambda: None)
    monkeypatch.setattr(search_indexer.search_index_worker, "stop", lambda: True)

    async def run_lifespan() -> None:
        async with app_module.app.router.lifespan_context(app_module.app):
            pass

    asyncio.run(run_lifespan())  # must not raise
