"""Typed ComfyUI workflow extraction, registry validation, and query contracts.

Purpose:
Verify D3's fixed node/property registry, typed schema, durable extraction, and
same-node workflow search without dynamic SQL identifiers.

Guarantees:
API prompt inputs are normalized once; UI widgets use versioned mappings;
unsupported combinations return 422; links/containers/non-finite values are
skipped; failed parsing degrades instead of failing asset import; typed index
plans and the 25k-asset/500k-property budget remain covered.

Run when:
Changing ComfyUI parsing, workflow registry/schema, typed extraction limits,
workflow Search V2 predicates, capabilities, or performance indexes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import backend.metadata_store._schema as schema_module
from backend.metadata_extract import parse_comfy
from backend.metadata_store import index_directory_tree, register_library
from backend.metadata_store._db import _connect
from backend.metadata_store.search_index_store import create_search_index_job, get_search_index_job
from backend.search_indexer import run_search_index_once
from backend.workflow_discovery import WorkflowExtractionError, normalize_workflow_document


def _drop_v7_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS workflow_property_values")
    conn.execute("DROP TABLE IF EXISTS workflow_nodes")
    conn.execute("PRAGMA user_version = 6")
    conn.commit()


def _write_png(path: Path) -> None:
    Image.new("RGB", (16, 16), (12, 34, 56)).save(path, format="PNG")


def _seed_workflow_assets(root: Path) -> tuple[dict, list[int]]:
    workflows = [
        {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 10, "cfg": 7.0}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 2, "steps": 30, "cfg": 9.0}},
        },
        {"1": {"class_type": "KSampler", "inputs": {"seed": "18446744073709551615", "steps": 30, "cfg": 7.0}}},
        {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "safe-output"}}},
    ]
    for index in range(len(workflows)):
        _write_png(root / f"workflow-{index}.png")
    library = register_library(root, name="Workflow discovery")
    index_directory_tree(root, include_metadata=True)
    asset_ids: list[int] = []
    with _connect() as conn:
        for index, workflow in enumerate(workflows):
            path = str(root / f"workflow-{index}.png")
            asset = conn.execute(
                "SELECT id FROM assets WHERE library_id = ? AND path = ?", (library["id"], path)
            ).fetchone()
            assert asset is not None
            asset_ids.append(int(asset["id"]))
            normalized = normalize_workflow_document(workflow)
            conn.execute(
                """
                UPDATE image_metadata
                SET tool = 'ComfyUI', metadata_json = ?, raw_metadata_text = ?
                WHERE path = ?
                """,
                (
                    json.dumps({"tool": "ComfyUI", "_workflow_document": normalized}),
                    json.dumps(workflow),
                    path,
                ),
            )
    return library, asset_ids


def _run_workflow_index(library_id: int) -> dict:
    job = create_search_index_job(
        "workflow_properties",
        library_id,
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    assert run_search_index_once(worker_id="workflow-discovery-test") is True
    finished = get_search_index_job(int(job["id"]))
    assert finished is not None
    return finished


def test_v7_migration_is_additive_transactional_and_has_no_inline_backfill(
    isolated_metadata_db: Path,
) -> None:
    with _connect() as conn:
        _drop_v7_tables(conn)
        schema_module._migrate_v6_to_v7(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM workflow_nodes").fetchone()[0] == 0
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v6.bak").exists()


def test_v7_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        _drop_v7_tables(conn)
    original = schema_module._execute_v7_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v7 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v7_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v6_to_v7(conn)
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert (
            conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='workflow_nodes'").fetchone()[
                0
            ]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v6.bak").exists()


def test_comfy_parser_returns_normalized_internal_document_without_reparse() -> None:
    prompt = {
        "4": {
            "class_type": "KSampler",
            "_meta": {"title": "Primary sampler"},
            "inputs": {
                "seed": "18446744073709551615",
                "steps": 28,
                "cfg": 6.5,
                "sampler_name": "euler",
                "model": [1, 0],
                "bad": {"nested": True},
            },
        }
    }
    parsed = parse_comfy(json.dumps(prompt), None)
    document = parsed["_workflow_document"]
    assert document["version"] == 1
    node = document["nodes"][0]
    assert node["title"] == "Primary sampler"
    values = {item["property_key"]: item for item in node["properties"]}
    assert values["seed"]["value_type"] == "uint64_token"
    assert values["seed"]["value_text"] == "18446744073709551615"
    assert "model" not in values
    assert "bad" not in values


def test_ui_widget_mapping_is_versioned_and_unknown_nodes_keep_identity_only() -> None:
    document = normalize_workflow_document(
        {
            "nodes": [
                {"id": 1, "type": "EmptyLatentImage", "title": "Canvas", "widgets_values": [1024, 768, 2]},
                {"id": 2, "type": "UnknownCustomNode", "title": "Keep me", "widgets_values": ["unsafe"]},
            ]
        }
    )
    canvas, unknown = document["nodes"]
    assert {item["property_key"] for item in canvas["properties"]} == {"width", "height", "batch_size"}
    assert unknown["node_type"] == "UnknownCustomNode"
    assert unknown["title"] == "Keep me"
    assert unknown["properties"] == []


def test_extraction_limits_skip_unsafe_scalars_and_reject_oversized_documents() -> None:
    document = normalize_workflow_document(
        {
            "1": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": -1,
                    "steps": float("nan"),
                    "cfg": float("inf"),
                    "sampler_name": "x" * 513,
                    "scheduler": [2, 0],
                },
            },
            "x" * 129: {"class_type": "SaveImage", "inputs": {"filename_prefix": "ignored"}},
        }
    )
    assert document["nodes"][0]["properties"] == []
    assert len(document["nodes"]) == 1

    too_many_nodes = {str(index): {"class_type": "UnknownNode", "inputs": {}} for index in range(2_049)}
    with pytest.raises(WorkflowExtractionError, match="workflow_node_limit"):
        normalize_workflow_document(too_many_nodes)

    oversized = parse_comfy('{"padding":"' + "x" * (2 * 1024 * 1024) + '"}', None)
    assert oversized["_workflow_error"] == "workflow_source_too_large"
    assert "_workflow_document" not in oversized


def test_same_node_semantics_typed_values_capabilities_and_injection_safety(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    library, asset_ids = _seed_workflow_assets(isolated_gallery_root)
    finished = _run_workflow_index(int(library["id"]))
    assert finished["state"] == "succeeded"

    capabilities = isolated_app.get("/api/search/capabilities")
    registry = capabilities.json()["workflow_registry"]
    assert registry["version"] == 1
    assert registry["nodes"]["KSampler"]["seed"] == {"type": "uint64_token", "operators": ["eq"]}

    response = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "workflow",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {
                "prompt_groups": [],
                "workflow_groups": [
                    {
                        "node_type": "KSampler",
                        "predicates": [
                            {"property": "steps", "op": "gte", "value": 20},
                            {"property": "cfg", "op": "lte", "value": 8.0},
                        ],
                    }
                ],
            },
            "limit": 20,
        },
    )
    assert response.status_code == 200, response.text
    assert [item["asset_id"] for item in response.json()["media"]] == [asset_ids[1]]

    uint64 = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "workflow",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {
                "prompt_groups": [],
                "workflow_groups": [
                    {
                        "node_type": "KSampler",
                        "predicates": [{"property": "seed", "op": "eq", "value": "18446744073709551615"}],
                    }
                ],
            },
            "limit": 20,
        },
    )
    assert uint64.status_code == 200
    assert [item["asset_id"] for item in uint64.json()["media"]] == [asset_ids[1]]

    unsupported = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "workflow",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {
                "prompt_groups": [],
                "workflow_groups": [
                    {"node_type": "KSampler", "predicates": [{"property": "steps", "op": "contains", "value": 20}]}
                ],
            },
            "limit": 20,
        },
    )
    assert unsupported.status_code == 422
    assert "predicates[0].op" in unsupported.text

    injection = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "workflow",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {
                "prompt_groups": [],
                "workflow_groups": [
                    {
                        "node_type": "SaveImage",
                        "predicates": [
                            {"property": "filename_prefix", "op": "contains", "value": "%'; DROP TABLE assets;--"}
                        ],
                    }
                ],
            },
            "limit": 20,
        },
    )
    assert injection.status_code == 200
    assert injection.json()["returned"] == 0
    with _connect() as conn:
        assert conn.execute(
            f"SELECT count(*) FROM assets WHERE id IN ({','.join('?' for _ in asset_ids)})",
            asset_ids,
        ).fetchone()[0] == len(asset_ids)


def test_parse_failure_marks_extraction_failed_and_index_degraded(isolated_gallery_root: Path) -> None:
    library, _asset_ids = _seed_workflow_assets(isolated_gallery_root)
    with _connect() as conn:
        path = str(isolated_gallery_root / "workflow-2.png")
        conn.execute(
            "UPDATE image_metadata SET metadata_json = ?, raw_metadata_text = ? WHERE path = ?",
            (json.dumps({"tool": "ComfyUI"}), "not valid workflow json", path),
        )
    finished = _run_workflow_index(int(library["id"]))
    assert finished["state"] == "succeeded"
    assert finished["failed_count"] == 1
    with _connect() as conn:
        failed = conn.execute(
            """
            SELECT extraction.status, extraction.error_code
            FROM asset_search_extractions AS extraction
            JOIN assets AS asset ON asset.id = extraction.asset_id
            WHERE extraction.index_name = 'workflow_properties' AND asset.name = 'workflow-2.png'
            """
        ).fetchone()
        state = conn.execute(
            "SELECT state FROM search_index_states WHERE index_name = 'workflow_properties' AND library_id = ?",
            (library["id"],),
        ).fetchone()
    assert dict(failed) == {"status": "failed", "error_code": "workflow_parse_failed"}
    assert state["state"] == "degraded"


def test_typed_query_plan_and_25k_500k_property_budget(isolated_gallery_root: Path) -> None:
    library = register_library(isolated_gallery_root, name="Workflow perf")
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
                    str(isolated_gallery_root / f"workflow-perf-{index}.png"),
                    str(isolated_gallery_root),
                    f"workflow-perf-{index}.png",
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
            INSERT INTO workflow_nodes (
              asset_id, node_key, node_type, extractor_version, source_fingerprint
            ) VALUES (?, '1', 'KSampler', 1, '1:100')
            """,
            ((asset_id,) for asset_id in asset_ids),
        )
        node_ids = [
            int(row["id"])
            for row in conn.execute(
                """
                SELECT node.id FROM workflow_nodes AS node
                JOIN assets AS asset ON asset.id = node.asset_id
                WHERE asset.library_id = ? ORDER BY node.id
                """,
                (library["id"],),
            )
        ]

        def property_rows():  # noqa: ANN202
            for node_id in node_ids:
                yield (node_id, "steps", 0, "integer", None, None, 30, None, None)
                yield (node_id, "cfg", 0, "real", None, None, None, 7.0, None)
                for ordinal in range(18):
                    yield (node_id, f"padding_{ordinal}", 0, "integer", None, None, ordinal, None, None)

        conn.executemany(
            """
            INSERT INTO workflow_property_values (
              node_id, property_key, ordinal, value_type, value_text,
              value_text_folded, value_integer, value_real, value_boolean
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            property_rows(),
        )
        conn.commit()
        plan = conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT node.id FROM workflow_nodes AS node
            JOIN assets AS asset ON asset.id = node.asset_id
            WHERE asset.library_id = ? AND node.node_type = 'KSampler'
              AND EXISTS (
                SELECT 1 FROM workflow_property_values AS value
                WHERE value.node_id = node.id AND value.property_key = 'steps'
                  AND value.value_type = 'integer' AND value.value_integer >= 20
              )
            LIMIT 50
            """,
            (library["id"],),
        ).fetchall()
    assert any("idx_workflow_property_node_integer" in " ".join(str(value) for value in row) for row in plan)

    started = time.perf_counter()
    with _connect() as conn:
        count = conn.execute(
            """
            SELECT count(*) FROM workflow_nodes AS node
            JOIN assets AS asset ON asset.id = node.asset_id
            WHERE asset.library_id = ? AND node.node_type = 'KSampler'
              AND EXISTS (
                SELECT 1 FROM workflow_property_values AS steps
                WHERE steps.node_id = node.id AND steps.property_key = 'steps'
                  AND steps.value_type = 'integer' AND steps.value_integer >= 20
              )
              AND EXISTS (
                SELECT 1 FROM workflow_property_values AS cfg
                WHERE cfg.node_id = node.id AND cfg.property_key = 'cfg'
                  AND cfg.value_type = 'real' AND cfg.value_real <= 8.0
              )
            """,
            (library["id"],),
        ).fetchone()[0]
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert count == 25_000
    assert elapsed_ms < 300
