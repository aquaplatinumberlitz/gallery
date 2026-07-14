"""Durable search-index schema, claims, worker, status, and API contracts.

Purpose:
Verify schema v5 and the single-writer derived-search-index lifecycle are
transactional, resumable, fenced, cancellable, observable, and feature-gated.

Guarantees:
Migration performs no inline backfill; workers use asset-ID keysets capped at
200; stale claims cannot complete newer work; cancellation and duplicate
enqueue are deterministic; public status separates state from usability.

Run when:
Changing search-index migrations, registry definitions, worker claims/batches,
rebuild APIs, capabilities, cancellation, or readiness errors.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.metadata_store._schema as schema_module
import backend.search_indexer as indexer_module
from backend.metadata_store import register_library
from backend.metadata_store._db import _connect
from backend.metadata_store.search_index_store import (
    SearchIndexJobConflict,
    claim_next_search_index_job,
    create_search_index_job,
    finish_search_index_job,
    get_search_index_job,
    list_search_index_asset_batch,
    list_search_index_states,
    record_search_index_extraction,
    recover_search_index_jobs,
    request_search_index_job_cancel,
)
from backend.search_indexer import (
    SearchExtractionResult,
    SearchIndexDefinition,
    SearchIndexWorker,
    register_search_index_definition,
    run_search_index_once,
)


@pytest.fixture(autouse=True)
def _isolate_search_index_database(isolated_metadata_db: Path) -> None:
    """Keep unrelated metadata/derivative backfill jobs out of lifecycle cases."""


def _drop_v5_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS search_index_states")
    conn.execute("DROP TABLE IF EXISTS asset_search_extractions")
    conn.execute("DROP TABLE IF EXISTS search_index_jobs")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()


def _seed_assets(root: Path, count: int) -> tuple[dict, list[int]]:
    library = register_library(root, name="Search index lifecycle")
    ids: list[int] = []
    with _connect() as conn:
        for index in range(count):
            cursor = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  indexed_at, metadata_state, offline, deleted_at
                ) VALUES (?, ?, ?, ?, 'image', ?, ?, 1, 'done', 0, NULL)
                """,
                (
                    library["id"],
                    str(root / f"asset-{index:04d}.png"),
                    str(root),
                    f"asset-{index:04d}.png",
                    1_000 + index,
                    100 + index,
                ),
            )
            ids.append(int(cursor.lastrowid))
    return library, ids


def _enabled_definition(name: str) -> SearchIndexDefinition:
    return SearchIndexDefinition(
        name=name,
        schema_version=1,
        extractor_version=1,
        enabled=True,
        required_mode="workflow",
        extractor=lambda asset: SearchExtractionResult(status="ready", payload={"asset_id": asset["id"]}),
        persist=lambda _conn, _asset, _payload: None,
    )


def test_v5_migration_is_additive_transactional_and_has_no_inline_backfill(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
) -> None:
    _library, asset_ids = _seed_assets(isolated_gallery_root, 1)
    with _connect() as conn:
        _drop_v5_tables(conn)
        schema_module._migrate_v4_to_v5(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM asset_search_extractions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM assets WHERE id = ?", (asset_ids[0],)).fetchone()[0] == 1
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v4.bak").exists()


def test_v5_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        _drop_v5_tables(conn)

    original = schema_module._execute_v5_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v5 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v5_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v4_to_v5(conn)

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'search_index_%'"
            ).fetchone()[0]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v4.bak").exists()


def test_worker_uses_bounded_keyset_batches_and_missing_fingerprints(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _enabled_definition("test_batched")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    library, asset_ids = _seed_assets(isolated_gallery_root, 401)
    job = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    observed_batch_sizes: list[int] = []
    original = indexer_module.list_search_index_asset_batch

    def capture_batch(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        rows = original(*args, **kwargs)
        observed_batch_sizes.append(len(rows))
        return rows

    monkeypatch.setattr(indexer_module, "list_search_index_asset_batch", capture_batch)
    assert run_search_index_once(worker_id="test-worker") is True
    finished = get_search_index_job(int(job["id"]))
    assert finished is not None
    assert finished["state"] == "succeeded"
    assert finished["processed_count"] == 401
    assert observed_batch_sizes[:3] == [200, 200, 1]
    assert max(observed_batch_sizes) <= 200

    missing = create_search_index_job(
        definition.name,
        library["id"],
        mode="missing",
        schema_version=1,
        extractor_version=1,
    )
    assert run_search_index_once(worker_id="test-worker") is True
    assert get_search_index_job(int(missing["id"]))["processed_count"] == 0

    with _connect() as conn:
        conn.execute("UPDATE assets SET mtime_ns = mtime_ns + 1 WHERE id = ?", (asset_ids[0],))
    changed = create_search_index_job(
        definition.name,
        library["id"],
        mode="missing",
        schema_version=1,
        extractor_version=1,
    )
    assert run_search_index_once(worker_id="test-worker") is True
    assert get_search_index_job(int(changed["id"]))["processed_count"] == 1


def test_interrupted_job_resumes_and_old_claim_cannot_complete_new_claim(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _enabled_definition("test_resume")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    library, _asset_ids = _seed_assets(isolated_gallery_root, 3)
    job = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    first_claim = claim_next_search_index_job("worker-one", lease_seconds=300)
    assert first_claim is not None
    batch = list_search_index_asset_batch(first_claim, extractor_version=1)
    record_search_index_extraction(
        int(job["id"]),
        str(first_claim["claim_token"]),
        batch[0],
        index_name=definition.name,
        extractor_version=1,
        status="ready",
        error_code=None,
        payload=None,
        persist=lambda _conn, _asset, _payload: None,
    )
    assert recover_search_index_jobs()[0]["state"] == "interrupted"
    second_claim = claim_next_search_index_job("worker-two", lease_seconds=300)
    assert second_claim is not None
    assert second_claim["claim_token"] != first_claim["claim_token"]
    assert finish_search_index_job(int(job["id"]), str(first_claim["claim_token"]), "succeeded") is None

    # Return the newer claim to interrupted state, then let the regular worker
    # resume from the persisted asset-ID cursor.
    assert recover_search_index_jobs()[0]["state"] == "interrupted"
    assert run_search_index_once(worker_id="worker-three") is True
    finished = get_search_index_job(int(job["id"]))
    assert finished["state"] == "succeeded"
    assert finished["processed_count"] == 3
    with _connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM asset_search_extractions WHERE index_name = ?",
                (definition.name,),
            ).fetchone()[0]
            == 3
        )


def test_expired_claim_is_recovered_and_reclaimed_without_restart(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _enabled_definition("test_expired_reclaim")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    library, _asset_ids = _seed_assets(isolated_gallery_root, 1)
    job = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    first = claim_next_search_index_job("expired-worker", lease_seconds=300)
    assert first is not None
    with _connect() as conn:
        conn.execute("UPDATE search_index_jobs SET lease_expires_at = 0 WHERE id = ?", (int(job["id"]),))

    reclaimed = claim_next_search_index_job("replacement-worker", lease_seconds=300)
    assert reclaimed is not None
    assert reclaimed["id"] == job["id"]
    assert reclaimed["claim_token"] != first["claim_token"]
    assert finish_search_index_job(int(job["id"]), str(first["claim_token"]), "succeeded") is None
    assert finish_search_index_job(int(job["id"]), str(reclaimed["claim_token"]), "succeeded") is not None


def test_duplicate_and_cancel_are_idempotent_and_state_never_becomes_ready(
    isolated_gallery_root: Path,
) -> None:
    library, _asset_ids = _seed_assets(isolated_gallery_root, 2)
    job = create_search_index_job("cancel_test", library["id"], schema_version=1, extractor_version=1)
    with pytest.raises(SearchIndexJobConflict):
        create_search_index_job("cancel_test", library["id"], schema_version=1, extractor_version=1)
    cancelled = request_search_index_job_cancel(int(job["id"]))
    assert cancelled["state"] == "cancelled"
    assert request_search_index_job_cancel(int(job["id"]))["state"] == "cancelled"
    state = next(
        item for item in list_search_index_states(library_id=library["id"]) if item["index_name"] == "cancel_test"
    )
    assert state["state"] == "pending"
    assert state["usable"] is False


def test_old_index_remains_usable_during_rebuild_cancel_and_extraction_failure(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _enabled_definition("test_stale_usable")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    library, _asset_ids = _seed_assets(isolated_gallery_root, 2)
    initial = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    assert run_search_index_once(worker_id="initial") is True
    assert get_search_index_job(int(initial["id"]))["state"] == "succeeded"

    rebuilding = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    claim = claim_next_search_index_job("rebuild", lease_seconds=300)
    assert claim is not None
    status = next(
        item
        for item in isolated_app.get("/api/search/indexes", params={"library_id": library["id"]}).json()
        if item["index_name"] == definition.name
    )
    assert status["state"] == "building"
    assert status["usable"] is True
    assert status["warning"] == "rebuild_in_progress_using_previous_index"

    assert request_search_index_job_cancel(int(rebuilding["id"]))["state"] == "cancel_requested"
    assert finish_search_index_job(int(rebuilding["id"]), str(claim["claim_token"]), "cancelled") is not None
    cancelled_state = next(
        item for item in list_search_index_states(library_id=library["id"]) if item["index_name"] == definition.name
    )
    assert cancelled_state["state"] == "degraded"
    assert cancelled_state["usable"] is True

    failing = replace(
        definition,
        extractor=lambda _asset: (_ for _ in ()).throw(RuntimeError("private /catalog/path prompt")),
    )
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, failing)
    failed_rebuild = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    assert run_search_index_once(worker_id="failing") is True
    assert get_search_index_job(int(failed_rebuild["id"]))["failed_count"] == 2
    degraded = next(
        item for item in list_search_index_states(library_id=library["id"]) if item["index_name"] == definition.name
    )
    assert degraded["state"] == "degraded"
    assert degraded["usable"] is True
    assert degraded["failed_count"] == 2


def test_capabilities_status_rebuild_cancel_and_readiness_errors(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library, _asset_ids = _seed_assets(isolated_gallery_root, 1)
    definition = _enabled_definition("test_api_index")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    monkeypatch.setattr(indexer_module.search_index_worker, "wake", lambda: None)

    capabilities = isolated_app.get("/api/search/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled_modes"] == ["lexical", "workflow"]
    assert capabilities.json()["index_requirements"]["workflow"] == ["workflow_properties"]
    schema = isolated_app.get("/openapi.json").json()
    assert schema["paths"]["/api/search/capabilities"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/SearchCapabilitiesResponse"}

    statuses = isolated_app.get("/api/search/indexes", params={"library_id": library["id"]})
    assert statuses.status_code == 200
    assert any(item["index_name"] == definition.name and item["state"] == "pending" for item in statuses.json())

    queued = isolated_app.post(
        f"/api/search/indexes/{definition.name}/rebuild",
        json={"library_id": library["id"], "mode": "missing"},
    )
    assert queued.status_code == 202
    duplicate = isolated_app.post(
        f"/api/search/indexes/{definition.name}/rebuild",
        json={"library_id": library["id"], "mode": "missing"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["active_job_id"] == queued.json()["id"]
    assert isolated_app.get(f"/api/search/index-jobs/{queued.json()['id']}").status_code == 200
    cancelled = isolated_app.post(f"/api/search/index-jobs/{queued.json()['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert isolated_app.post(f"/api/search/index-jobs/{queued.json()['id']}/cancel").json()["state"] == "cancelled"

    disabled = isolated_app.post(
        "/api/search/indexes/workflow_raw/rebuild",
        json={"library_id": library["id"]},
    )
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["error"] == "feature_disabled"

    monkeypatch.setitem(indexer_module._DEFINITIONS, "workflow_properties", _enabled_definition("workflow_properties"))
    not_ready = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "workflow",
            "text": "steps",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {"prompt_groups": [], "workflow_groups": []},
            "limit": 60,
        },
    )
    assert not_ready.status_code == 503
    assert not_ready.headers["retry-after"] == "5"
    assert not_ready.json()["detail"]["error"] == "search_index_not_ready"

    lexical = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "missing",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {"prompt_groups": [], "workflow_groups": []},
            "limit": 60,
        },
    )
    assert lexical.status_code == 200


def test_search_index_api_not_found_disabled_and_version_mismatch_branches(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library, _asset_ids = _seed_assets(isolated_gallery_root, 1)
    definition = _enabled_definition("test_api_state_branches")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)

    job = create_search_index_job(
        definition.name,
        library["id"],
        mode="full",
        schema_version=definition.schema_version,
        extractor_version=definition.extractor_version,
    )
    assert run_search_index_once(worker_id="state-branches") is True
    assert get_search_index_job(int(job["id"]))["state"] == "succeeded"

    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, replace(definition, enabled=False))
    disabled = next(
        item
        for item in isolated_app.get("/api/search/indexes", params={"library_id": library["id"]}).json()
        if item["index_name"] == definition.name
    )
    assert disabled["state"] == "disabled"
    assert disabled["usable"] is False

    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, replace(definition, schema_version=2))
    mismatched = next(
        item
        for item in isolated_app.get("/api/search/indexes", params={"library_id": library["id"]}).json()
        if item["index_name"] == definition.name
    )
    assert mismatched["state"] == "degraded"
    assert mismatched["usable"] is True
    assert mismatched["warning"] == "version_mismatch"

    assert isolated_app.get("/api/search/indexes").status_code == 200
    assert isolated_app.get("/api/search/indexes", params={"library_id": 999_999}).status_code == 404
    assert isolated_app.get("/api/search/index-jobs/999999").status_code == 404
    assert (
        isolated_app.post(
            "/api/search/indexes/not_registered/rebuild",
            json={"library_id": library["id"]},
        ).status_code
        == 404
    )
    assert (
        isolated_app.post(
            f"/api/search/indexes/{definition.name}/rebuild",
            json={"library_id": 999_999},
        ).status_code
        == 404
    )
    assert isolated_app.post("/api/search/index-jobs/999999/cancel").status_code == 404


def test_search_index_registry_and_worker_failure_control_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Invalid search index definition"):
        register_search_index_definition(SearchIndexDefinition("", 0, 0, False, "workflow"))
    with pytest.raises(ValueError, match="require extractor"):
        register_search_index_definition(SearchIndexDefinition("missing_callbacks", 1, 1, True, "workflow"))

    finished: list[tuple[int, str, str, dict]] = []
    monkeypatch.setattr(
        indexer_module,
        "finish_search_index_job",
        lambda job_id, token, state, **kwargs: finished.append((job_id, token, state, kwargs)),
    )
    job = {"id": 41, "claim_token": "claim", "index_name": "not_registered"}
    monkeypatch.setattr(indexer_module, "claim_next_search_index_job", lambda *_args, **_kwargs: dict(job))
    assert run_search_index_once(worker_id="disabled") is True
    assert finished[-1][2:] == (
        "failed",
        {"error_code": "feature_disabled", "error_summary": "Search index feature is disabled"},
    )

    definition = _enabled_definition("worker_control_branches")
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    job["index_name"] = definition.name

    monkeypatch.setattr(indexer_module, "search_index_job_control_state", lambda *_args: "cancel_requested")
    assert run_search_index_once(worker_id="cancel") is True
    assert finished[-1][2] == "cancelled"

    monkeypatch.setattr(indexer_module, "search_index_job_control_state", lambda *_args: "running")
    monkeypatch.setattr(indexer_module, "renew_search_index_job_lease", lambda *_args, **_kwargs: False)
    assert run_search_index_once(worker_id="lost-claim") is True

    monkeypatch.setattr(
        indexer_module,
        "search_index_job_control_state",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("worker failure")),
    )
    assert run_search_index_once(worker_id="failed") is True
    assert finished[-1][2:] == (
        "failed",
        {"error_code": "worker_failed", "error_summary": "Search index worker failed"},
    )


def test_single_writer_lifecycle_is_idempotent(isolated_metadata_db: Path) -> None:
    worker = SearchIndexWorker()
    worker.start()
    first_thread = worker._thread
    assert first_thread is not None and first_thread.is_alive()
    worker.start()
    assert worker._thread is first_thread
    assert worker.stop() is True
    assert worker._thread is None
    assert worker.stop() is True
