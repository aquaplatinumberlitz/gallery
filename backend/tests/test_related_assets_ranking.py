"""Golden metadata ranking contracts for Related Assets R2.

Purpose:
Exercise the deterministic fixture through bounded candidate collection,
layered signature tiers, exact scoring, stable reason codes, and scope filters.

Guarantees:
Exact/recipe/family results outrank weaker overlap; same model, shared LoRA,
seed, and boilerplate alone are insufficient; primary scope excludes other
libraries and inactive assets; missing workflow discovery degrades safely.

Run when:
Changing metadata candidate sources, prompt boilerplate/weights, relation tiers,
reason codes, tie-breakers, scope filtering, or recipe profile behavior.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.related_ranking as ranking_module
from backend.generation_signatures import build_generation_signature_payload
from backend.metadata_store import register_library
from backend.metadata_store._db import _connect
from backend.related_ranking import rank_related_metadata
from backend.search_scope import SearchScopeContext

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "related_assets_v1.json"


def _resource(value: str) -> dict[str, str | None]:
    kind, name, resource_hash = value.split(":", 2)
    return {
        "kind": kind,
        "name": name,
        "hash": resource_hash,
        "resource_hash": resource_hash,
        "weight": None,
        "strength": None,
    }


def _metadata(value: dict) -> dict:  # noqa: ANN001
    return {
        "prompt": value.get("prompt", ""),
        "negative_prompt": value.get("negative_prompt", ""),
        "model": value.get("model", ""),
        "model_hash": value.get("model_hash", ""),
        "sampler": value.get("sampler", ""),
        "scheduler": value.get("scheduler", ""),
        "seed": value.get("seed", ""),
        "steps": value.get("steps"),
        "cfg_scale": value.get("cfg"),
        "width": value.get("width"),
        "height": value.get("height"),
        "denoising_strength": value.get("denoising_strength"),
        "hires_upscale": value.get("hires_upscale"),
        "hires_steps": value.get("hires_steps"),
        "vae": value.get("vae", ""),
        "metadata_json": "{}",
    }


def _seed_fixture(root: Path) -> tuple[dict, dict, dict[str, int]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    primary_root, secondary_root = root / "primary", root / "secondary"
    primary_root.mkdir()
    secondary_root.mkdir()
    libraries = {
        "primary": register_library(primary_root, name="Primary relations"),
        "secondary": register_library(secondary_root, name="Secondary relations"),
    }
    fixture_by_key = {item["key"]: item for item in fixture["assets"]}
    resolved_metadata: dict[str, dict] = {}
    ids: dict[str, int] = {}
    with _connect() as conn:
        for ordinal, item in enumerate(fixture["assets"]):
            if "visual_transform" in item or "metadata_raw" in item:
                continue
            if "copy_metadata_from" in item:
                metadata = deepcopy(resolved_metadata[item["copy_metadata_from"]])
                metadata.update(item.get("metadata_patch", {}))
            else:
                metadata = deepcopy(item.get("metadata", {}))
            resolved_metadata[item["key"]] = metadata
            library = libraries[item["library"]]
            library_root = primary_root if item["library"] == "primary" else secondary_root
            path = library_root / f"{item['key']}.png"
            mtime_ns = 10_000 + ordinal
            cursor = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  indexed_at, metadata_state, offline, deleted_at
                ) VALUES (?, ?, ?, ?, 'image', ?, 100, ?, 'done', ?, NULL)
                """,
                (
                    library["id"],
                    str(path),
                    str(path.parent),
                    path.name,
                    mtime_ns,
                    float(ordinal + 1),
                    int(not item.get("active", True)),
                ),
            )
            asset_id = int(cursor.lastrowid)
            ids[item["key"]] = asset_id
            normalized = _metadata(metadata)
            conn.execute(
                """
                INSERT INTO image_metadata (
                  path, name, mtime, mtime_ns, size, width, height, prompt,
                  negative_prompt, model, model_hash, sampler, scheduler, seed,
                  steps, cfg_scale, denoising_strength, metadata_json,
                  indexed_at, updated_at
                ) VALUES (?, ?, ?, ?, 100, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    str(path),
                    path.name,
                    float(ordinal + 1),
                    mtime_ns,
                    normalized["width"],
                    normalized["height"],
                    normalized["prompt"],
                    normalized["negative_prompt"],
                    normalized["model"],
                    normalized["model_hash"],
                    normalized["sampler"],
                    normalized["scheduler"],
                    normalized["seed"],
                    normalized["steps"],
                    normalized["cfg_scale"],
                    normalized["denoising_strength"],
                    float(ordinal + 1),
                    float(ordinal + 1),
                ),
            )
            resources = [_resource(value) for value in metadata.get("resources", [])]
            for resource in resources:
                conn.execute(
                    """
                    INSERT INTO image_resources (
                      path, kind, name, hash, resource_hash, weight, strength, raw_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)
                    """,
                    (
                        str(path),
                        resource["kind"],
                        resource["name"],
                        resource["hash"],
                        resource["resource_hash"],
                        resource["weight"],
                        resource["strength"],
                        float(ordinal + 1),
                    ),
                )
            source = {"metadata": normalized, "resources": resources}
            payload = build_generation_signature_payload(
                {
                    "id": asset_id,
                    "library_id": library["id"],
                    "path": str(path),
                    "type": "image",
                    "mtime_ns": mtime_ns,
                    "size": 100,
                },
                source,
            )
            if payload["prompt_hash"] is not None:
                conn.execute(
                    """
                    INSERT INTO asset_generation_signatures (
                      asset_id, library_id, prompt_hash, family_hash, recipe_hash,
                      exact_hash, normalizer_version, extractor_version,
                      source_mtime_ns, source_size, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        library["id"],
                        payload["prompt_hash"],
                        payload["family_hash"],
                        payload["recipe_hash"],
                        payload["exact_hash"],
                        payload["normalizer_version"],
                        payload["extractor_version"],
                        payload["source_mtime_ns"],
                        payload["source_size"],
                        float(ordinal + 1),
                    ),
                )
    assert fixture_by_key["reference"]["library"] == "primary"
    return libraries["primary"], libraries["secondary"], ids


def test_golden_metadata_tiers_reasons_order_scope_and_recipe_profile(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    context = SearchScopeContext(kind="library", library_id=primary["id"], library_name=primary["name"])
    results = rank_related_metadata(ids["reference"], context, profile="related", limit=60)
    by_id = {item.asset_id: item for item in results}

    exact = by_id[ids["same_exact_recorded_settings"]]
    assert exact.relation_tier == 100
    assert [reason.value for reason in exact.relation_reasons] == [
        "same_exact_signature",
        "same_recipe",
        "same_generation_family",
    ]
    recipe = by_id[ids["same_family_different_seed"]]
    assert recipe.relation_tier == 90
    assert [reason.value for reason in recipe.relation_reasons] == ["same_recipe", "same_generation_family"]
    rare = by_id[ids["rare_prompt_with_common_boilerplate"]]
    assert rare.relation_tier == 60
    assert [reason.value for reason in rare.relation_reasons][:2] == ["strong_prompt_overlap", "same_model_hash"]

    assert ids["same_model_unrelated_prompt"] not in by_id
    assert ids["shared_lora_unrelated_prompt"] not in by_id
    assert ids["missing_metadata"] not in by_id
    assert ids["inactive_match"] not in by_id
    assert ids["cross_library_match"] not in by_id
    assert [item.relation_tier for item in results] == sorted((item.relation_tier for item in results), reverse=True)

    recipe_results = rank_related_metadata(ids["reference"], context, profile="recipe", limit=60)
    assert [item.asset_id for item in recipe_results] == [
        ids["same_exact_recorded_settings"],
        ids["same_family_different_seed"],
    ]


def test_missing_workflow_index_degrades_and_candidate_load_is_bounded(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    context = SearchScopeContext(kind="library", library_id=primary["id"], library_name=primary["name"])
    observed: list[int] = []
    original = ranking_module._candidate_rows

    def capture(conn, candidate_ids, scope):  # noqa: ANN001, ANN202
        observed.append(len(candidate_ids))
        return original(conn, candidate_ids, scope)

    monkeypatch.setattr(ranking_module, "_table_exists", lambda *_args: False)
    monkeypatch.setattr(ranking_module, "_candidate_rows", capture)
    results = rank_related_metadata(ids["reference"], context, profile="related", limit=60)
    assert results
    assert observed and observed[0] <= ranking_module.MAX_METADATA_CANDIDATES


def test_shared_typed_workflow_property_is_visible_evidence(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    with _connect() as conn:
        for asset_id, node_key in (
            (ids["reference"], "reference-sampler"),
            (ids["rare_prompt_with_common_boilerplate"], "rare-sampler"),
        ):
            cursor = conn.execute(
                """
                INSERT INTO workflow_nodes (
                  asset_id, node_key, node_type, extractor_version, source_fingerprint
                ) VALUES (?, ?, 'KSampler', 1, 'fixture')
                """,
                (asset_id, node_key),
            )
            conn.execute(
                """
                INSERT INTO workflow_property_values (
                  node_id, property_key, ordinal, value_type, value_text, value_text_folded
                ) VALUES (?, 'scheduler', 0, 'text', 'karras', 'karras')
                """,
                (int(cursor.lastrowid),),
            )
    context = SearchScopeContext(kind="library", library_id=primary["id"], library_name=primary["name"])
    results = rank_related_metadata(ids["reference"], context, profile="related", limit=60)
    rare = next(item for item in results if item.asset_id == ids["rare_prompt_with_common_boilerplate"])
    assert "shared_workflow_property" in {reason.value for reason in rare.relation_reasons}


def test_related_api_returns_ranked_items_and_excludes_stale_or_seed_only_candidates(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO search_index_states (
              index_name, library_id, state, schema_version, extractor_version,
              indexed_count, target_count, failed_count, skipped_count, updated_at
            ) VALUES ('generation_signatures', ?, 'ready', 1, 1, 8, 8, 0, 0, 1)
            """,
            (primary["id"],),
        )
        conn.execute("UPDATE image_metadata SET seed = '101' WHERE path LIKE '%same_model_unrelated_prompt.png'")

    request = {
        "schema_version": 1,
        "reference_asset_id": ids["reference"],
        "profile": "related",
        "scope": {"kind": "library", "library_id": primary["id"]},
        "limit": 60,
    }
    response = isolated_app.post("/api/search/related", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["returned"] == len(body["items"])
    assert body["items"][0]["asset_id"] == ids["same_exact_recorded_settings"]
    assert ids["same_model_unrelated_prompt"] not in {item["asset_id"] for item in body["items"]}

    with _connect() as conn:
        conn.execute(
            "UPDATE assets SET mtime_ns = mtime_ns + 1 WHERE id = ?",
            (ids["same_exact_recorded_settings"],),
        )
    stale_response = isolated_app.post("/api/search/related", json=request)
    assert stale_response.status_code == 200
    assert ids["same_exact_recorded_settings"] not in {item["asset_id"] for item in stale_response.json()["items"]}
