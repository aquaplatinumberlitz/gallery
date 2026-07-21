"""Opt-in raw workflow schema, budgets, FTS, deadline, and API contracts.

Purpose:
Verify D4 canonical raw workflow indexing remains separately disabled by
default, size/budget bounded, visible when degraded, literal-only, scoped, and
terminated by a dedicated SQLite progress deadline.

Guarantees:
Migration is rollback-safe with no backfill; skipped documents are counted;
raw queries use trigram FTS and strict bounds; control terms and legacy raw
aliases fail clearly; timeout responses are typed; the 25k fixture stays below
the 500 ms product budget and the 250 ms database deadline.

Run when:
Changing raw workflow configuration/schema/extraction, index status counts,
raw FTS/cursors/deadlines, fielded raw/JSON aliases, or capability behavior.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import backend.metadata_store._schema as schema_module
import backend.search as search_module
import backend.search_indexer as indexer_module
import backend.workflow_raw_search as raw_module
from backend.metadata_store import index_directory_tree, register_library
from backend.metadata_store._db import _connect
from backend.metadata_store.search_index_store import (
    create_search_index_job,
    get_search_index_job,
    list_search_index_states,
)
from backend.search_indexer import run_search_index_once
from backend.workflow_raw_search import RawWorkflowTimeout, query_raw_workflows


def _drop_v8_schema(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER IF EXISTS workflow_raw_documents_au")
    conn.execute("DROP TRIGGER IF EXISTS workflow_raw_documents_ad")
    conn.execute("DROP TRIGGER IF EXISTS workflow_raw_documents_ai")
    conn.execute("DROP TABLE IF EXISTS workflow_raw_fts")
    conn.execute("DROP TABLE IF EXISTS workflow_raw_documents")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()


def _enable_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    definition = indexer_module._DEFINITIONS["workflow_raw"]
    monkeypatch.setitem(indexer_module._DEFINITIONS, "workflow_raw", replace(definition, enabled=True))


def _seed_raw_assets(root: Path, documents: list[dict]) -> tuple[dict, list[int]]:
    for index in range(len(documents)):
        Image.new("RGB", (8, 8), (index, 20, 30)).save(root / f"raw-{index}.png", format="PNG")
    library = register_library(root, name="Raw workflows")
    index_directory_tree(root, include_metadata=True)
    asset_ids: list[int] = []
    with _connect() as conn:
        for index, document in enumerate(documents):
            path = str(root / f"raw-{index}.png")
            asset = conn.execute(
                "SELECT id FROM assets WHERE library_id = ? AND path = ?", (library["id"], path)
            ).fetchone()
            assert asset is not None
            asset_ids.append(int(asset["id"]))
            raw = json.dumps(document, ensure_ascii=False, indent=2)
            conn.execute(
                "UPDATE image_metadata SET tool = 'ComfyUI', metadata_json = ?, raw_metadata_text = ? WHERE path = ?",
                (json.dumps({"tool": "ComfyUI"}), raw, path),
            )
    return library, asset_ids


def _run_raw_index(library_id: int) -> dict:
    job = create_search_index_job("workflow_raw", library_id, mode="full", schema_version=1, extractor_version=1)
    for _ in range(20):
        if get_search_index_job(int(job["id"]))["state"] in {"succeeded", "failed", "cancelled"}:
            break
        assert run_search_index_once(worker_id="raw-workflow-test") is True
    finished = get_search_index_job(int(job["id"]))
    assert finished is not None
    return finished


def test_metadata_change_invalidates_initialized_raw_document_and_queues_repair(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_raw(monkeypatch)
    library, asset_ids = _seed_raw_assets(
        isolated_gallery_root,
        [{"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "stale"}}}],
    )
    assert _run_raw_index(int(library["id"]))["state"] == "succeeded"
    Image.new("RGB", (9, 9), (90, 40, 20)).save(isolated_gallery_root / "raw-0.png", format="PNG")
    index_directory_tree(isolated_gallery_root, include_metadata=True)

    with _connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM workflow_raw_documents WHERE asset_id = ?", (asset_ids[0],)).fetchone()[
                0
            ]
            == 0
        )
        queued = conn.execute(
            """
            SELECT id FROM search_index_jobs
            WHERE index_name = 'workflow_raw' AND library_id = ?
              AND state IN ('queued', 'running', 'cancel_requested', 'interrupted')
            """,
            (library["id"],),
        ).fetchone()
    assert queued is not None
    state = next(
        item for item in list_search_index_states(library_id=int(library["id"])) if item["index_name"] == "workflow_raw"
    )
    assert state["state"] == "pending"


def test_raw_workflow_document_detection_handles_wrappers_and_invalid_payloads() -> None:
    prompt_document = {"nodes": []}
    api_document = {"1": {"class_type": "SaveImage", "inputs": {}}}

    assert raw_module._is_workflow_document([]) is False
    assert raw_module._is_workflow_document(prompt_document) is True
    assert raw_module._workflow_json_from_raw(f"prompt: {json.dumps(prompt_document)}") == prompt_document
    assert raw_module._workflow_json_from_raw(f"workflow: {json.dumps(api_document)}") == api_document
    assert raw_module._workflow_json_from_raw("not json\nworkflow: also not json") is None


def test_v8_migration_is_additive_transactional_and_has_no_inline_backfill(
    isolated_metadata_db: Path,
) -> None:
    with _connect() as conn:
        _drop_v8_schema(conn)
        schema_module._migrate_v7_to_v8(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM workflow_raw_documents").fetchone()[0] == 0
        assert "skipped_count" in {row["name"] for row in conn.execute("PRAGMA table_info(search_index_states)")}
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v7.bak").exists()


def test_v8_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        _drop_v8_schema(conn)
        conn.execute("ALTER TABLE search_index_jobs DROP COLUMN skipped_count")
        conn.execute("ALTER TABLE search_index_states DROP COLUMN skipped_count")
    original = schema_module._execute_v8_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v8 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v8_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v7_to_v8(conn)
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='workflow_raw_documents'"
            ).fetchone()[0]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v7.bak").exists()


def test_disabled_raw_feature_does_not_block_startup_and_returns_clear_errors(
    isolated_app: TestClient,
) -> None:
    capabilities = isolated_app.get("/api/search/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["raw_search"]["enabled"] is False
    response = isolated_app.post(
        "/api/search/workflow/raw",
        json={"query": "model", "scope": {"kind": "all"}, "limit": 10},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "feature_disabled"
    legacy = isolated_app.get("/api/search", params={"q": "raw:model", "scope": "all"})
    assert legacy.status_code == 409
    assert "deprecated" in legacy.text


def test_canonical_fts_api_scope_cursor_warning_and_json_key_grammar(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_raw(monkeypatch)
    capabilities = isolated_app.get("/api/search/capabilities").json()
    assert capabilities["raw_search"]["enabled"] is True
    assert capabilities["enabled_modes"] == ["lexical", "workflow"]
    library, asset_ids = _seed_raw_assets(
        isolated_gallery_root,
        [
            {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "special_model.safetensors"}}},
            {"2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "special_model_output"}}},
        ],
    )
    finished = _run_raw_index(int(library["id"]))
    assert finished["state"] == "succeeded"
    with _connect() as conn:
        stored = conn.execute(
            "SELECT canonical_text, byte_length FROM workflow_raw_documents ORDER BY asset_id"
        ).fetchall()
    assert len(stored) == 2
    assert all("\n" not in row["canonical_text"] for row in stored)
    assert all(row["byte_length"] == len(row["canonical_text"].encode()) for row in stored)

    request = {
        "query": "special_model",
        "scope": {"kind": "library", "library_id": library["id"]},
        "limit": 1,
    }
    first = isolated_app.post("/api/search/workflow/raw", json=request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["warning"]
    assert body["capability"]["deadline_ms"] == 250
    assert body["has_more"] is True
    assert body["items"][0]["asset_id"] in asset_ids
    second = isolated_app.post("/api/search/workflow/raw", json={**request, "cursor": body["next_cursor"]})
    assert second.status_code == 200
    assert second.json()["items"][0]["asset_id"] != body["items"][0]["asset_id"]

    control = isolated_app.post(
        "/api/search/workflow/raw",
        json={"query": "bad\u0001term", "scope": {"kind": "library", "library_id": library["id"]}},
    )
    assert control.status_code == 400
    literal_injection = isolated_app.post(
        "/api/search/workflow/raw",
        json={"query": "';DROP TABLE assets;--", "scope": {"kind": "library", "library_id": library["id"]}},
    )
    assert literal_injection.status_code == 400
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE library_id = ?", (library["id"],)).fetchone()[0] >= 2

    invalid_key = isolated_app.get("/api/search", params={"q": "param:bad-key:value", "scope": "all"})
    assert invalid_key.status_code == 400
    assert "identifier" in invalid_key.text


def test_oversize_and_budget_skips_are_visible_as_degraded_status(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_raw(monkeypatch)
    monkeypatch.setattr(raw_module, "GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES", 180)
    monkeypatch.setattr(raw_module, "GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES", 100)
    library, _asset_ids = _seed_raw_assets(
        isolated_gallery_root,
        [
            {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "first"}}},
            {"2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "second"}}},
            {"3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x" * 300}}},
        ],
    )
    finished = _run_raw_index(int(library["id"]))
    assert finished["state"] == "succeeded"
    assert finished["skipped_count"] == 2
    with _connect() as conn:
        state = conn.execute(
            "SELECT state, skipped_count FROM search_index_states WHERE index_name = 'workflow_raw' AND library_id = ?",
            (library["id"],),
        ).fetchone()
        reasons = {
            row["error_code"]
            for row in conn.execute(
                """
                SELECT extraction.error_code
                FROM asset_search_extractions AS extraction
                JOIN assets AS asset ON asset.id = extraction.asset_id
                WHERE extraction.index_name = 'workflow_raw' AND asset.library_id = ?
                  AND extraction.status = 'skipped'
                """,
                (library["id"],),
            )
        }
    assert dict(state) == {"state": "degraded", "skipped_count": 2}
    assert reasons == {"raw_document_too_large", "raw_index_budget_exceeded"}
    statuses = isolated_app.get("/api/search/indexes", params={"library_id": library["id"]})
    raw_status = next(item for item in statuses.json() if item["index_name"] == "workflow_raw")
    assert raw_status["skip_reasons"] == {
        "raw_document_too_large": 1,
        "raw_index_budget_exceeded": 1,
    }


def test_timeout_maps_to_typed_complete_failure(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_raw(monkeypatch)
    library, _asset_ids = _seed_raw_assets(
        isolated_gallery_root,
        [{"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "deadline"}}}],
    )
    _run_raw_index(int(library["id"]))
    monkeypatch.setattr(
        search_module, "query_raw_workflows", lambda **_kwargs: (_ for _ in ()).throw(RawWorkflowTimeout())
    )
    response = isolated_app.post(
        "/api/search/workflow/raw",
        json={"query": "deadline", "scope": {"kind": "library", "library_id": library["id"]}},
    )
    assert response.status_code == 504
    assert response.json()["detail"]["error"] == "search_timeout"
    assert "items" not in response.json()


def test_raw_workflow_25k_fixture_meets_500ms_budget_and_250ms_deadline(
    isolated_gallery_root: Path,
) -> None:
    library = register_library(isolated_gallery_root, name="Raw perf")
    canonical = json.dumps(
        {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "bounded_search_target"}}},
        separators=(",", ":"),
        sort_keys=True,
    )
    with _connect() as conn:
        conn.execute("BEGIN")
        conn.executemany(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, 100, 1, 'done', 0, NULL)
            """,
            (
                (
                    library["id"],
                    str(isolated_gallery_root / f"raw-perf-{index}.png"),
                    str(isolated_gallery_root),
                    f"raw-perf-{index}.png",
                    index,
                )
                for index in range(25_000)
            ),
        )
        asset_ids = [
            int(row["id"])
            for row in conn.execute("SELECT id FROM assets WHERE library_id = ? ORDER BY id", (library["id"],))
        ]
        conn.executemany(
            """
            INSERT INTO workflow_raw_documents (
              asset_id, library_id, canonical_text, byte_length, source_fingerprint, extractor_version
            ) VALUES (?, ?, ?, ?, '1:100', 1)
            """,
            ((asset_id, library["id"], canonical, len(canonical.encode())) for asset_id in asset_ids),
        )
        conn.commit()
    durations: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        result = query_raw_workflows(
            query="bounded_search_target",
            scope="library",
            root_path=None,
            library_id=int(library["id"]),
            cursor=None,
            limit=50,
        )
        durations.append((time.perf_counter() - started) * 1000)
        assert result["returned"] == 50
    assert sorted(durations)[-1] < 500
    assert sorted(durations)[-1] < raw_module.RAW_WORKFLOW_QUERY_DEADLINE_SECONDS * 1000


# ---------------------------------------------------------------------------
# _raw_workflow_source: no metadata row (line 70)
# ---------------------------------------------------------------------------


def test_raw_workflow_source_no_row():
    from backend.workflow_raw_search import _raw_workflow_source

    document, looks_comfy = _raw_workflow_source({"path": "/nonexistent"})
    assert document is None
    assert looks_comfy is False


# ---------------------------------------------------------------------------
# _raw_workflow_source: JSON decode error in metadata (lines 76-77)
# ---------------------------------------------------------------------------


def test_raw_workflow_source_bad_metadata_json(isolated_metadata_db: Path):
    from backend.metadata_store._db import _connect
    from backend.workflow_raw_search import _raw_workflow_source

    with _connect() as conn:
        conn.execute(
            "INSERT INTO image_metadata(path, name, mtime, size, metadata_json) "
            "VALUES ('/test.png', 'test.png', 1000, 100, '{bad json')"
        )

    document, looks_comfy = _raw_workflow_source({"path": "/test.png"})
    assert document is None
    assert looks_comfy is False


# ---------------------------------------------------------------------------
# extract_raw_workflow: non-ComfyUI, no document (lines 88-90)
# ---------------------------------------------------------------------------


def test_extract_raw_workflow_not_applicable(isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.search_indexer import SearchExtractionResult
    from backend.workflow_raw_search import extract_raw_workflow

    def non_comfy_source(asset):
        return None, False

    monkeypatch.setattr("backend.workflow_raw_search._raw_workflow_source", non_comfy_source)
    result = extract_raw_workflow({"path": "/test.png"})
    assert isinstance(result, SearchExtractionResult)
    assert result.status == "not_applicable"


# ---------------------------------------------------------------------------
# _validate_query: too short (line 205)
# ---------------------------------------------------------------------------


def test_raw_validate_query_too_short():
    from backend.workflow_raw_search import _validate_query

    with pytest.raises(ValueError, match="3-128"):
        _validate_query("ab")


# ---------------------------------------------------------------------------
# _decode_cursor: bad format (line 187)
# ---------------------------------------------------------------------------


def test_raw_decode_cursor_bad_format():
    from backend.workflow_raw_search import _decode_cursor

    with pytest.raises(ValueError, match="Invalid raw workflow cursor"):
        _decode_cursor("bad-cursor!!!", "fingerprint")


# ---------------------------------------------------------------------------
# _decode_cursor: version mismatch (line 196)
# ---------------------------------------------------------------------------


def test_raw_decode_cursor_version_mismatch():
    import base64
    import json

    from backend.workflow_raw_search import RAW_WORKFLOW_CURSOR_VERSION, _decode_cursor

    old_version = RAW_WORKFLOW_CURSOR_VERSION - 1
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"version": old_version, "fingerprint": "fp", "rank": 1.0, "mtime_ns": 0, "asset_id": 1}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )

    with pytest.raises(ValueError, match="Invalid raw workflow cursor"):
        _decode_cursor(payload, "fp")


# ---------------------------------------------------------------------------
# _decode_cursor: fingerprint mismatch (line 198-199)
# ---------------------------------------------------------------------------


def test_raw_decode_cursor_fingerprint_mismatch():
    import base64
    import json

    from backend.workflow_raw_search import RAW_WORKFLOW_CURSOR_VERSION, _decode_cursor

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "version": RAW_WORKFLOW_CURSOR_VERSION,
                    "fingerprint": "wrong_fp",
                    "rank": 1.0,
                    "mtime_ns": 0,
                    "asset_id": 1,
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )

    with pytest.raises(ValueError, match="Invalid raw workflow cursor"):
        _decode_cursor(payload, "expected_fp")


# ---------------------------------------------------------------------------
# query_raw_workflows: scope=folder with root_path (lines 245-249)
# ---------------------------------------------------------------------------


def test_raw_query_scope_folder(isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.workflow_raw_search import query_raw_workflows

    result = query_raw_workflows(
        query="test",
        scope="folder",
        root_path="/tmp",
        library_id=1,
        cursor=None,
        limit=1,
    )
    assert result["returned"] == 0


# ---------------------------------------------------------------------------
# query_raw_workflows: timeout path (lines 293-296)
# ---------------------------------------------------------------------------


def test_raw_query_operational_error_interrupted(isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from unittest.mock import MagicMock

    from backend.workflow_raw_search import RawWorkflowTimeout, query_raw_workflows

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError("interrupted")
    mock_conn.row_factory = None
    monkeypatch.setattr("backend.workflow_raw_search._readonly_connection", lambda: mock_conn)

    with pytest.raises(RawWorkflowTimeout):
        query_raw_workflows(
            query="test",
            scope="all",
            root_path=None,
            library_id=None,
            cursor=None,
            limit=1,
        )
