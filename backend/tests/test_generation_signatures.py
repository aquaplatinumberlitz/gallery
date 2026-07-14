"""Prompt normalization, generation-signature schema, hashing, and lifecycle.

Purpose:
Protect the compact metadata relation layer used by Related Assets.

Guarantees:
Normalization and numeric formatting are versioned and bounded; hash layers
change only for their documented inputs; weak metadata cannot create strong
families; schema migration is transactional; durable reindexing is active-only
and idempotent; metadata writes invalidate stale signatures and queue repair.

Run when:
Changing prompt atoms, generation signature inputs/schema, metadata persistence,
or the generation_signatures derived-index definition.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import backend.metadata_store._schema as schema_module
import backend.search_indexer as search_indexer_module
from backend.generation_signatures import (
    GENERATION_SIGNATURE_EXTRACTOR_VERSION,
    MAX_FTS_PROMPT_ATOMS,
    MAX_PROMPT_ATOMS,
    build_generation_signature_payload,
    canonical_number,
    extract_generation_signature,
    invalidate_generation_signature_conn,
    normalize_prompt_atoms,
    persist_generation_signature,
    schedule_generation_signature_backfill,
    select_prompt_atoms_for_fts,
)
from backend.metadata_extract import ExtractedMetadata
from backend.metadata_store import register_library
from backend.metadata_store._db import _connect
from backend.metadata_store.metadata_persist import upsert_extracted_metadata
from backend.metadata_store.search_index_store import (
    create_search_index_job,
    get_search_index_job,
    list_search_index_states,
)
from backend.search_indexer import SearchIndexDefinition, run_search_index_once


def _source(**overrides) -> dict:  # noqa: ANN003
    metadata = {
        "prompt": "portrait, dramatic light",
        "negative_prompt": "blurry",
        "model": "Example XL",
        "model_hash": "ABC123",
        "sampler": "Euler a",
        "scheduler": "normal",
        "seed": "42",
        "steps": 24,
        "cfg_scale": 6.5,
        "width": 1024,
        "height": 1024,
        "denoising_strength": 0.4,
        "hires_upscale": 2,
        "hires_steps": 12,
        "vae": "vae.safetensors",
        "metadata_json": "{}",
    }
    metadata.update(overrides)
    return {"metadata": metadata, "resources": []}


def _asset(asset_id: int = 1, *, library_id: int = 1, mtime_ns: int = 1000, size: int = 100) -> dict:
    return {
        "id": asset_id,
        "library_id": library_id,
        "path": f"/library/{asset_id}.png",
        "type": "image",
        "mtime_ns": mtime_ns,
        "size": size,
    }


def _seed_asset(
    root: Path, *, name: str = "asset.png", offline: int = 0, deleted_at: float | None = None
) -> tuple[dict, int]:
    library = register_library(root, name="Generation signatures")
    path = root / name
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', 1000, 100, 1, 'done', ?, ?)
            """,
            (library["id"], str(path), str(root), name, offline, deleted_at),
        )
        asset_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, prompt,
              negative_prompt, model, model_hash, sampler, seed, steps,
              cfg_scale, metadata_json, indexed_at, updated_at
            ) VALUES (?, ?, 1, 1000, 100, 1024, 1024, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 1, 1)
            """,
            (str(path), name, "portrait, dramatic light", "blurry", "Example XL", "ABC123", "Euler", "42", 24, 6.5),
        )
    return library, asset_id


def test_prompt_atoms_normalize_unicode_emphasis_limits_and_fts_selection() -> None:
    atoms = normalize_prompt_atoms("  ＣＡＦÉ  , (Dramatic   Light:9), [soft focus]\nline art ")
    assert [(atom.display, atom.identity, atom.weight) for atom in atoms] == [
        ("CAFÉ", "café", "1"),
        ("Dramatic Light", "dramatic light", "2"),
        ("soft focus", "soft focus", "0.9"),
        ("line art", "line art", "1"),
    ]
    assert normalize_prompt_atoms("x" * 161) == []
    assert normalize_prompt_atoms("\x00\x01\x02bad") == []
    capped = normalize_prompt_atoms(",".join(f"atom {index}" for index in range(80)))
    assert len(capped) == MAX_PROMPT_ATOMS
    selected = select_prompt_atoms_for_fts(capped + capped)
    assert len(selected) == MAX_FTS_PROMPT_ATOMS
    assert len({atom.identity for atom in selected}) == MAX_FTS_PROMPT_ATOMS
    distinctive = select_prompt_atoms_for_fts(normalize_prompt_atoms("masterpiece, best quality, rare glass fox"))
    assert [atom.identity for atom in distinctive] == ["rare glass fox", "best quality", "masterpiece"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, "1"), (1.0, "1"), ("1.2300", "1.23"), (-0.0, "0"), ("1e-7", "0.0000001"), (float("inf"), None)],
)
def test_canonical_number_is_stable(value, expected: str | None) -> None:  # noqa: ANN001
    assert canonical_number(value) == expected


def test_hash_layers_follow_prompt_seed_recipe_and_family_boundaries() -> None:
    baseline = build_generation_signature_payload(_asset(), _source())
    equivalent = build_generation_signature_payload(
        _asset(),
        _source(prompt="  PORTRAIT, dramatic   light ", cfg_scale=6.5000),
    )
    assert equivalent["prompt_hash"] == baseline["prompt_hash"]
    assert equivalent["family_hash"] == baseline["family_hash"]
    assert equivalent["recipe_hash"] == baseline["recipe_hash"]

    seed_change = build_generation_signature_payload(_asset(), _source(seed="43"))
    assert seed_change["family_hash"] == baseline["family_hash"]
    assert seed_change["recipe_hash"] == baseline["recipe_hash"]
    assert seed_change["exact_hash"] != baseline["exact_hash"]

    recipe_change = build_generation_signature_payload(_asset(), _source(sampler="DPM++ 2M", cfg_scale=7))
    assert recipe_change["family_hash"] == baseline["family_hash"]
    assert recipe_change["recipe_hash"] != baseline["recipe_hash"]
    assert recipe_change["exact_hash"] != baseline["exact_hash"]

    model_change = build_generation_signature_payload(_asset(), _source(model_hash="DEF456"))
    assert model_change["family_hash"] != baseline["family_hash"]
    assert model_change["recipe_hash"] != baseline["recipe_hash"]
    assert model_change["exact_hash"] != baseline["exact_hash"]


def test_resource_identity_prefers_hash_and_lora_changes_family() -> None:
    source = _source()
    source["resources"] = [{"kind": "lora", "name": "Style", "resource_hash": "HASH-A", "weight": "0.8"}]
    baseline = build_generation_signature_payload(_asset(), source)
    renamed = _source()
    renamed["resources"] = [{"kind": "LORA", "name": "Renamed style", "resource_hash": "hash-a", "weight": "0.80"}]
    assert build_generation_signature_payload(_asset(), renamed)["family_hash"] == baseline["family_hash"]
    changed = _source()
    changed["resources"] = [{"kind": "lora", "name": "Style", "resource_hash": "HASH-B", "weight": "0.8"}]
    changed_payload = build_generation_signature_payload(_asset(), changed)
    assert changed_payload["family_hash"] != baseline["family_hash"]
    assert changed_payload["recipe_hash"] != baseline["recipe_hash"]
    assert changed_payload["exact_hash"] != baseline["exact_hash"]


def test_explicit_zero_resource_weight_is_not_treated_as_missing() -> None:
    zero = _source()
    zero["resources"] = [{"kind": "lora", "name": "Style", "resource_hash": "HASH-A", "weight": 0}]
    missing = _source()
    missing["resources"] = [{"kind": "lora", "name": "Style", "resource_hash": "HASH-A"}]

    zero_payload = build_generation_signature_payload(_asset(), zero)
    missing_payload = build_generation_signature_payload(_asset(), missing)

    assert zero_payload["recipe_hash"] != missing_payload["recipe_hash"]
    assert zero_payload["exact_hash"] != missing_payload["exact_hash"]


def test_missing_prompt_never_creates_a_strong_family_from_defaults() -> None:
    payload = build_generation_signature_payload(
        _asset(),
        _source(prompt="", negative_prompt="", model="common-model", model_hash="", sampler="Euler", seed="1"),
    )
    assert payload["prompt_hash"] is None
    assert payload["family_hash"] is None
    assert payload["recipe_hash"] is None
    assert payload["exact_hash"] is None


def test_only_registry_typed_workflow_properties_participate() -> None:
    document = {
        "version": 1,
        "nodes": [
            {
                "node_type": "KSampler",
                "properties": [
                    {"property_key": "cfg", "value_type": "real", "value_real": 7.0},
                    {"property_key": "seed", "value_type": "uint64_token", "value_text": "99"},
                    {"property_key": "private_blob", "value_type": "text", "value_text": "ignored"},
                ],
            }
        ],
    }
    first = build_generation_signature_payload(
        _asset(), _source(metadata_json=json.dumps({"_workflow_document": document}))
    )
    document["unbounded_raw_workflow"] = {"anything": [1, 2, 3]}
    document["nodes"][0]["properties"][2]["value_text"] = "still ignored"
    second = build_generation_signature_payload(
        _asset(), _source(metadata_json=json.dumps({"_workflow_document": document}))
    )
    assert second["recipe_hash"] == first["recipe_hash"]
    assert second["exact_hash"] == first["exact_hash"]


def test_v10_migration_is_transactional_backed_up_and_has_no_inline_backfill(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
) -> None:
    _library, asset_id = _seed_asset(isolated_gallery_root)
    with _connect() as conn:
        conn.execute("DROP TABLE asset_generation_signatures")
        conn.execute("PRAGMA user_version = 8")
        conn.commit()
        schema_module._migrate_v8_to_v10(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM asset_generation_signatures").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM assets WHERE id = ?", (asset_id,)).fetchone()[0] == 1
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v8.bak").exists()


def test_v10_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        conn.execute("DROP TABLE asset_generation_signatures")
        conn.execute("PRAGMA user_version = 8")
        conn.commit()

    original = schema_module._execute_v10_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v10 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v10_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v8_to_v10(conn)
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'asset_generation_signatures'"
            ).fetchone()[0]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v8.bak").exists()


def test_durable_backfill_is_active_only_and_idempotent(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    library, active_id = _seed_asset(isolated_gallery_root, name="active.png")
    inactive_ids: list[int] = []
    with _connect() as conn:
        for name, offline, deleted_at in (("offline.png", 1, None), ("deleted.png", 0, 1)):
            cursor = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  indexed_at, metadata_state, offline, deleted_at
                ) VALUES (?, ?, ?, ?, 'image', 1000, 100, 1, 'done', ?, ?)
                """,
                (
                    library["id"],
                    str(isolated_gallery_root / name),
                    str(isolated_gallery_root),
                    name,
                    offline,
                    deleted_at,
                ),
            )
            inactive_ids.append(int(cursor.lastrowid))
    job = create_search_index_job(
        "generation_signatures", library["id"], mode="full", schema_version=1, extractor_version=1
    )
    assert run_search_index_once(worker_id="generation-test") is True
    assert get_search_index_job(int(job["id"]))["processed_count"] == 1
    with _connect() as conn:
        rows = conn.execute("SELECT asset_id FROM asset_generation_signatures ORDER BY asset_id").fetchall()
        assert [int(row["asset_id"]) for row in rows] == [active_id]
        assert (
            conn.execute(
                "SELECT count(*) FROM asset_generation_signatures WHERE asset_id IN (?, ?)",
                tuple(inactive_ids),
            ).fetchone()[0]
            == 0
        )

    missing = create_search_index_job(
        "generation_signatures", library["id"], mode="missing", schema_version=1, extractor_version=1
    )
    assert run_search_index_once(worker_id="generation-test") is True
    assert get_search_index_job(int(missing["id"]))["processed_count"] == 0
    state = next(
        item
        for item in list_search_index_states(library_id=library["id"])
        if item["index_name"] == "generation_signatures"
    )
    assert state["state"] == "ready"
    assert state["indexed_count"] == state["target_count"] == 1


def test_generation_backfill_retries_when_metadata_changes_between_extract_and_persist(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library, asset_id = _seed_asset(isolated_gallery_root)
    actual_definition = search_indexer_module.get_search_index_definition("generation_signatures")
    assert actual_definition is not None
    extraction_count = 0

    def extract_with_concurrent_metadata_update(asset: dict):
        nonlocal extraction_count
        extraction_count += 1
        result = extract_generation_signature(asset)
        if extraction_count == 1:
            with _connect() as conn:
                conn.execute(
                    "UPDATE image_metadata SET prompt = 'portrait, new light' WHERE path = ?",
                    (asset["path"],),
                )
                invalidate_generation_signature_conn(conn, int(asset["id"]))
            schedule_generation_signature_backfill(int(asset["library_id"]))
        return result

    monkeypatch.setitem(
        search_indexer_module._DEFINITIONS,
        "generation_signatures",
        SearchIndexDefinition(
            name="generation_signatures",
            schema_version=1,
            extractor_version=GENERATION_SIGNATURE_EXTRACTOR_VERSION,
            enabled=True,
            required_mode="related",
            extractor=extract_with_concurrent_metadata_update,
            persist=persist_generation_signature,
        ),
    )
    job = create_search_index_job(
        "generation_signatures",
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=GENERATION_SIGNATURE_EXTRACTOR_VERSION,
    )

    assert run_search_index_once(worker_id="generation-race-test") is True
    assert get_search_index_job(int(job["id"]))["state"] == "succeeded"
    assert extraction_count == 2
    expected = build_generation_signature_payload(
        _asset(asset_id, library_id=library["id"]), _source(prompt="portrait, new light")
    )
    with _connect() as conn:
        signature = conn.execute(
            "SELECT prompt_hash FROM asset_generation_signatures WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        extraction = conn.execute(
            """
            SELECT status, error_code FROM asset_search_extractions
            WHERE asset_id = ? AND index_name = 'generation_signatures'
            """,
            (asset_id,),
        ).fetchone()
        active_jobs = conn.execute(
            """
            SELECT count(*) FROM search_index_jobs
            WHERE index_name = 'generation_signatures' AND state IN ('queued', 'running')
            """
        ).fetchone()[0]
    assert signature is not None and signature["prompt_hash"] == expected["prompt_hash"]
    assert dict(extraction) == {"status": "ready", "error_code": None}
    assert active_jobs == 0

    monkeypatch.setitem(search_indexer_module._DEFINITIONS, "generation_signatures", actual_definition)


def test_metadata_persist_invalidates_signature_and_queues_missing_repair(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    library, asset_id = _seed_asset(isolated_gallery_root)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO asset_generation_signatures (
              asset_id, library_id, prompt_hash, normalizer_version, extractor_version,
              source_mtime_ns, source_size, indexed_at
            ) VALUES (?, ?, X'01', 1, 1, 1000, 100, 1)
            """,
            (asset_id, library["id"]),
        )
        conn.execute(
            """
            INSERT INTO asset_search_extractions (
              asset_id, index_name, source_fingerprint, extractor_version, status, indexed_at
            ) VALUES (?, 'generation_signatures', '1000:100', 1, 'ready', 1)
            """,
            (asset_id,),
        )
    metadata = ExtractedMetadata(
        path=str(isolated_gallery_root / "asset.png"),
        name="asset.png",
        mtime=1,
        mtime_ns=1000,
        size=100,
        width=1024,
        height=1024,
        format="PNG",
        mode="RGB",
        has_alpha=0,
        prompt="portrait, new light",
        negative_prompt="blurry",
        model="Example XL",
        sampler="Euler",
        seed="43",
        steps=24,
        cfg_scale=6.5,
        raw_metadata_text="",
        metadata_json="{}",
        indexed_at=2,
        model_hash="ABC123",
    )
    assert upsert_extracted_metadata(metadata) is True
    with _connect() as conn:
        assert (
            conn.execute("SELECT 1 FROM asset_generation_signatures WHERE asset_id = ?", (asset_id,)).fetchone() is None
        )
        assert (
            conn.execute(
                "SELECT 1 FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'generation_signatures'",
                (asset_id,),
            ).fetchone()
            is None
        )
        queued = conn.execute(
            """
            SELECT state FROM search_index_jobs
            WHERE index_name = 'generation_signatures' AND library_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (library["id"],),
        ).fetchone()
        assert queued is not None and queued["state"] == "queued"
