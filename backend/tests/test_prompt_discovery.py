"""Prompt discovery schema, indexing, usage, exact filtering, and model aliases.

Purpose:
Verify D2 normalized prompt identities and observed model mappings are built
from persisted metadata and queried through authorized canonical scopes.

Guarantees:
Whitespace/case variants group, polarity remains distinct, cursors contain no
prompt text, missing metadata is not applicable, exact groups compose with
Search V2, and ambiguous model names expand to every observed hash.

Run when:
Changing prompt normalization/schema, prompt usage/search APIs, derived search
index extraction, or model field semantics.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.metadata_store._schema as schema_module
from backend.metadata_store import index_directory_tree, list_libraries
from backend.metadata_store._db import _connect
from backend.metadata_store.search_index_store import (
    create_search_index_job,
    get_search_index_job,
    list_search_index_states,
)
from backend.prompt_discovery import normalize_discovery_text, prompt_value_hash, query_prompt_usage
from backend.search_indexer import run_search_index_once

from .conftest import create_test_png_with_metadata


def _drop_v6_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS model_identity_aliases")
    conn.execute("DROP TABLE IF EXISTS asset_model_identity_values")
    conn.execute("DROP TABLE IF EXISTS asset_prompt_values")
    conn.execute("PRAGMA user_version = 5")
    conn.commit()


def _build_prompt_index(root: Path) -> dict:
    index_directory_tree(root, include_metadata=True)
    library = list_libraries()[0]
    job = create_search_index_job(
        "prompt_values",
        int(library["id"]),
        mode="full",
        schema_version=1,
        extractor_version=1,
    )
    for _ in range(20):
        if get_search_index_job(int(job["id"]))["state"] in {"succeeded", "failed", "cancelled"}:
            break
        assert run_search_index_once(worker_id="prompt-discovery-test") is True
    assert get_search_index_job(int(job["id"]))["state"] == "succeeded"
    return {"library": library, "job": job}


def test_metadata_update_invalidates_ready_prompt_coverage_and_coalesces_rebuild(
    temp_gallery_with_metadata: Path,
) -> None:
    built = _build_prompt_index(temp_gallery_with_metadata)
    library_id = int(built["library"]["id"])
    create_test_png_with_metadata(
        temp_gallery_with_metadata / "mika_album" / "new-discovery.png",
        prompt="brand new discovery prompt",
        model="Discovery Model",
        seed="777",
    )
    index_directory_tree(temp_gallery_with_metadata, include_metadata=True)

    state = next(
        item for item in list_search_index_states(library_id=library_id) if item["index_name"] == "prompt_values"
    )
    assert state["state"] == "degraded"
    assert state["active_job_id"] is not None
    with _connect() as conn:
        queued = conn.execute(
            """
            SELECT id FROM search_index_jobs
            WHERE index_name = 'prompt_values' AND library_id = ?
              AND state IN ('queued', 'running', 'cancel_requested', 'interrupted')
            """,
            (library_id,),
        ).fetchone()
    assert queued is not None
    for _ in range(20):
        if get_search_index_job(int(queued["id"]))["state"] in {"succeeded", "failed", "cancelled"}:
            break
        assert run_search_index_once(worker_id="prompt-refresh-test") is True
    assert get_search_index_job(int(queued["id"]))["state"] == "succeeded"
    result = query_prompt_usage(
        polarity="positive",
        scope="library",
        root_path=None,
        library_id=library_id,
        prefix=None,
        text_query="brand new discovery prompt",
        sort="usage",
        cursor=None,
        limit=10,
    )
    assert result["returned"] == 1


def test_v6_migration_is_additive_and_has_no_inline_backfill(
    isolated_metadata_db: Path,
) -> None:
    with _connect() as conn:
        _drop_v6_tables(conn)
        schema_module._migrate_v5_to_v6(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM asset_prompt_values").fetchone()[0] == 0
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v5.bak").exists()


def test_v6_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        _drop_v6_tables(conn)
    original = schema_module._execute_v6_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v6 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v6_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v5_to_v6(conn)
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_prompt_values'"
            ).fetchone()[0]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v5.bak").exists()


def test_prompt_normalization_groups_case_and_whitespace_but_separates_polarity() -> None:
    display_a, search_a = normalize_discovery_text("  Masterpiece\n portrait  ")
    display_b, search_b = normalize_discovery_text("masterpiece portrait")
    assert display_a == "Masterpiece portrait"
    assert search_a == search_b
    assert prompt_value_hash("positive", search_a) == prompt_value_hash("positive", search_b)
    assert prompt_value_hash("positive", search_a) != prompt_value_hash("negative", search_a)


def test_backfill_usage_exact_groups_and_cursor_privacy(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
) -> None:
    built = _build_prompt_index(temp_gallery_with_metadata)
    library = built["library"]
    request = {
        "polarity": "positive",
        "scope": {"kind": "library", "library_id": library["id"]},
        "sort": "usage",
        "limit": 1,
    }
    first = isolated_app.post("/api/search/prompt-usage/query", json=request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["items"]
    assert body["has_more"] is True
    assert len(body["items"][0]["value_id"]) == 43
    decoded_cursor = json.loads(base64.urlsafe_b64decode(body["next_cursor"] + "=" * (-len(body["next_cursor"]) % 4)))
    assert "prompt" not in decoded_cursor
    assert "text" not in decoded_cursor

    second = isolated_app.post(
        "/api/search/prompt-usage/query",
        json={**request, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["value_id"] != body["items"][0]["value_id"]

    value_id = body["items"][0]["value_id"]
    exact = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {"prompt_groups": [{"kind": "positive", "value_id": value_id}], "workflow_groups": []},
            "limit": 20,
        },
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["returned"] == body["items"][0]["asset_count"]

    negative = isolated_app.post(
        "/api/search/prompt-usage/query",
        json={**request, "polarity": "negative", "limit": 100},
    )
    assert negative.status_code == 200
    assert {item["kind"] for item in negative.json()["items"]} == {"negative"}


def test_missing_metadata_is_not_applicable_and_backfill_never_opens_media(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = list_libraries()[0] if list_libraries() else None
    if library is None:
        from backend.metadata_store import register_library

        library = register_library(isolated_gallery_root, name="No metadata")
    path = isolated_gallery_root / "missing-metadata.png"
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', 10, 20, 1, 'done', 0, NULL)
            """,
            (library["id"], str(path), str(path.parent), path.name),
        )
        asset_id = int(cursor.lastrowid)

    def forbidden_open(*_args, **_kwargs):  # noqa: ANN202
        raise AssertionError("media file was reopened")

    monkeypatch.setattr("builtins.open", forbidden_open)
    job = create_search_index_job(
        "prompt_values", int(library["id"]), mode="full", schema_version=1, extractor_version=1
    )
    for _ in range(20):
        if get_search_index_job(int(job["id"]))["state"] in {"succeeded", "failed", "cancelled"}:
            break
        assert run_search_index_once(worker_id="db-only-prompt-test") is True
    assert get_search_index_job(int(job["id"]))["state"] == "succeeded"
    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'prompt_values'",
            (asset_id,),
        ).fetchone()
        assert row["status"] == "not_applicable"
        assert (
            conn.execute("SELECT count(*) FROM asset_prompt_values WHERE asset_id = ?", (asset_id,)).fetchone()[0] == 0
        )
    assert job["state"] == "queued"


def test_ambiguous_model_alias_expands_all_hashes_deterministically(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
) -> None:
    index_directory_tree(temp_gallery_with_metadata, include_metadata=True)
    with _connect() as conn:
        rows = conn.execute("SELECT path FROM image_metadata ORDER BY path").fetchall()
        assert len(rows) == 2
        conn.execute(
            "UPDATE image_metadata SET model = 'Shared Model', model_hash = 'HASH-A' WHERE path = ?", (rows[0]["path"],)
        )
        conn.execute(
            "UPDATE image_metadata SET model = 'Shared Model', model_hash = 'HASH-B' WHERE path = ?", (rows[1]["path"],)
        )
    built = _build_prompt_index(temp_gallery_with_metadata)
    with _connect() as conn:
        aliases = conn.execute(
            "SELECT normalized_hash FROM model_identity_aliases WHERE normalized_name = 'shared model' ORDER BY normalized_hash"
        ).fetchall()
        assert [row["normalized_hash"] for row in aliases] == ["hash-a", "hash-b"]
        conn.execute("UPDATE image_metadata SET model = 'Renamed A' WHERE model_hash = 'HASH-A'")
        conn.execute("UPDATE image_metadata SET model = 'Renamed B' WHERE model_hash = 'HASH-B'")
    response = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": 'model:"Shared Model"',
            "scope": {"kind": "library", "library_id": built["library"]["id"]},
            "filters": {"prompt_groups": [], "workflow_groups": []},
            "limit": 20,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["returned"] == 2


def test_prompt_usage_25k_first_page_meets_lexical_budget(isolated_gallery_root: Path) -> None:
    from backend.metadata_store import register_library

    library = register_library(isolated_gallery_root, name="Prompt perf")
    digest = prompt_value_hash("positive", "masterpiece portrait")
    with _connect() as conn:
        conn.execute("BEGIN")
        for index in range(25_000):
            asset = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  indexed_at, metadata_state, offline, deleted_at
                ) VALUES (?, ?, ?, ?, 'image', ?, 100, 1, 'done', 0, NULL)
                """,
                (
                    library["id"],
                    str(isolated_gallery_root / f"perf-{index}.png"),
                    str(isolated_gallery_root),
                    f"perf-{index}.png",
                    index,
                ),
            )
            conn.execute(
                """
                INSERT INTO asset_prompt_values (
                  asset_id, kind, display_text, normalized_text, search_text,
                  value_hash, extractor_version, source_fingerprint
                ) VALUES (?, 'positive', 'Masterpiece portrait', 'Masterpiece portrait',
                          'masterpiece portrait', ?, 1, '1:100')
                """,
                (int(asset.lastrowid), digest),
            )
        conn.commit()
    started = time.perf_counter()
    result = query_prompt_usage(
        polarity="positive",
        scope="library",
        root_path=None,
        library_id=int(library["id"]),
        prefix=None,
        text_query=None,
        sort="usage",
        cursor=None,
        limit=100,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result["items"][0]["asset_count"] == 25_000
    assert elapsed_ms < 300

    started = time.perf_counter()
    with _connect() as conn:
        exact_count = conn.execute(
            """
            SELECT count(*)
            FROM assets AS asset
            WHERE asset.library_id = ? AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND EXISTS (
                SELECT 1 FROM asset_prompt_values AS prompt
                WHERE prompt.asset_id = asset.id AND prompt.kind = 'positive'
                  AND prompt.value_hash = ?
              )
            """,
            (library["id"], digest),
        ).fetchone()[0]
    exact_elapsed_ms = (time.perf_counter() - started) * 1000
    assert exact_count == 25_000
    assert exact_elapsed_ms < 300
