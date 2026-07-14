"""Bounded, explainable metadata ranking for Related Assets."""

from __future__ import annotations

import os
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .generation_signatures import (
    GENERATION_SIGNATURE_EXTRACTOR_VERSION,
    PROMPT_NORMALIZER_VERSION,
    canonical_number,
    is_common_prompt_atom,
    normalize_prompt_atoms,
    select_prompt_atoms_for_fts,
)
from .metadata_store._db import _DB_LOCK, _connect, _table_exists
from .metadata_store.path_utils import canonicalize_catalog_path, named_path_scope_sql
from .models import RelatedSearchResultV1
from .search_scope import SearchScopeContext

RELATED_SCORING_POLICY_VERSION = 1
CANDIDATE_BRANCH_LIMIT = 250
MAX_METADATA_CANDIDATES = 600
MAX_WORKFLOW_CANDIDATE_PROPERTIES = 16

_WORKFLOW_RECIPE_KEYS = {
    "steps",
    "start_at_step",
    "end_at_step",
    "cfg",
    "sampler_name",
    "scheduler",
    "denoise",
    "add_noise",
    "return_with_leftover_noise",
    "width",
    "height",
    "batch_size",
    "strength_model",
    "strength_clip",
    "vae_name",
    "control_net_name",
    "weight_dtype",
    "clip_name",
    "clip_name1",
    "clip_name2",
    "type",
}


@dataclass(frozen=True)
class RankedCandidate:
    """One scored candidate with stable evidence and ordering fields."""

    row: dict[str, Any]
    tier: int
    reasons: tuple[str, ...]
    prompt_score: float
    resource_score: float
    compatibility_score: float
    settings_score: float


def _clean_identity(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(unicodedata.normalize("NFKC", str(value)).strip().split()).casefold()
    return text or None


def _resource_identity(row: dict[str, Any]) -> tuple[str, str, str] | None:
    kind = _clean_identity(row.get("kind")) or "resource"
    resource_hash = _clean_identity(row.get("resource_hash") or row.get("hash"))
    if resource_hash:
        return kind, "hash", resource_hash
    name = _clean_identity(row.get("name"))
    return (kind, "name", name) if name else None


def _workflow_value(row: sqlite3.Row | dict[str, Any]) -> str | None:
    value_type = str(row["value_type"])
    if value_type == "text":
        return _clean_identity(row["value_text"])
    if value_type == "integer":
        return canonical_number(row["value_integer"])
    if value_type == "real":
        return canonical_number(row["value_real"])
    if value_type == "boolean":
        return "true" if int(row["value_boolean"]) else "false"
    if value_type == "uint64_token":
        return str(row["value_text"])
    return None


def _workflow_key(row: sqlite3.Row | dict[str, Any]) -> tuple[str, str, str, str] | None:
    property_key = str(row["property_key"])
    value = _workflow_value(row)
    if property_key not in _WORKFLOW_RECIPE_KEYS or value is None:
        return None
    return str(row["node_type"]), property_key, str(row["value_type"]), value


def _scope_predicate(context: SearchScopeContext) -> tuple[str, dict[str, Any]]:
    if context.kind == "all":
        return "", {}
    if context.kind == "library":
        return " AND asset.library_id = :scope_library_id", {"scope_library_id": context.library_id}
    assert context.folder_path is not None and context.library_id is not None
    path_sql, params = named_path_scope_sql(
        context.folder_path,
        column="asset.path",
        parameter_prefix="related_scope",
        leading_and=True,
    )
    params["scope_library_id"] = context.library_id
    return f" AND asset.library_id = :scope_library_id{path_sql}", params


def _eligible_cte(context: SearchScopeContext) -> tuple[str, dict[str, Any]]:
    scope_sql, params = _scope_predicate(context)
    return (
        f"""
        WITH eligible AS (
          SELECT asset.id AS asset_id, asset.library_id, asset.path, asset.parent_path,
                 asset.name, asset.mtime_ns, library.name AS library_name,
                 metadata.id AS metadata_id, metadata.mtime, metadata.prompt,
                 metadata.negative_prompt, metadata.model, metadata.model_hash,
                 metadata.sampler, metadata.scheduler, metadata.seed,
                 metadata.steps, metadata.cfg_scale, metadata.width,
                 metadata.height, metadata.denoising_strength,
                 signature.prompt_hash, signature.family_hash,
                 signature.recipe_hash, signature.exact_hash
          FROM assets AS asset
          JOIN libraries AS library ON library.id = asset.library_id
          JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
          JOIN image_metadata AS metadata
            ON metadata.path = asset.path
           AND metadata.mtime_ns = asset.mtime_ns
           AND metadata.size = asset.size
          WHERE asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
            AND signature.source_mtime_ns = asset.mtime_ns
            AND signature.source_size = asset.size
            AND signature.normalizer_version = :normalizer_version
            AND signature.extractor_version = :signature_extractor_version
            {scope_sql}
        )
        """,
        {
            **params,
            "normalizer_version": PROMPT_NORMALIZER_VERSION,
            "signature_extractor_version": GENERATION_SIGNATURE_EXTRACTOR_VERSION,
        },
    )


def _reference_row(conn: sqlite3.Connection, reference_asset_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT asset.id AS asset_id, asset.library_id, asset.path, asset.parent_path,
               asset.name, asset.mtime_ns, library.name AS library_name,
               metadata.id AS metadata_id, metadata.mtime, metadata.prompt,
               metadata.negative_prompt, metadata.model, metadata.model_hash,
               metadata.sampler, metadata.scheduler, metadata.seed,
               metadata.steps, metadata.cfg_scale, metadata.width,
               metadata.height, metadata.denoising_strength,
               signature.prompt_hash, signature.family_hash,
               signature.recipe_hash, signature.exact_hash
        FROM assets AS asset
        JOIN libraries AS library ON library.id = asset.library_id
        JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
        JOIN image_metadata AS metadata
          ON metadata.path = asset.path
         AND metadata.mtime_ns = asset.mtime_ns
         AND metadata.size = asset.size
        WHERE asset.id = ? AND asset.type = 'image'
          AND asset.offline = 0 AND asset.deleted_at IS NULL
          AND signature.source_mtime_ns = asset.mtime_ns
          AND signature.source_size = asset.size
          AND signature.normalizer_version = ?
          AND signature.extractor_version = ?
        """,
        (reference_asset_id, PROMPT_NORMALIZER_VERSION, GENERATION_SIGNATURE_EXTRACTOR_VERSION),
    ).fetchone()
    return dict(row) if row is not None else None


def _load_resources(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_path = {str(row["path"]): int(row["asset_id"]) for row in rows}
    if not by_path:
        return {}
    placeholders = ",".join("?" for _ in by_path)
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        f"""
        SELECT path, kind, name, hash, resource_hash, weight, strength
        FROM image_resources WHERE path IN ({placeholders}) ORDER BY path, id
        """,
        tuple(by_path),
    ):
        result[by_path[str(row["path"])]].append(dict(row))
    return result


def _load_workflow(conn: sqlite3.Connection, asset_ids: list[int]) -> dict[int, set[tuple[str, str, str, str]]]:
    if not asset_ids or not _table_exists(conn, "workflow_nodes"):
        return {}
    placeholders = ",".join("?" for _ in asset_ids)
    result: dict[int, set[tuple[str, str, str, str]]] = defaultdict(set)
    rows = conn.execute(
        f"""
        SELECT node.asset_id, node.node_type, value.property_key, value.value_type,
               value.value_text, value.value_integer, value.value_real, value.value_boolean
        FROM workflow_nodes AS node
        JOIN workflow_property_values AS value ON value.node_id = node.id
        WHERE node.asset_id IN ({placeholders})
        """,
        asset_ids,
    )
    for row in rows:
        key = _workflow_key(row)
        if key is not None:
            result[int(row["asset_id"])].add(key)
    return result


def _candidate_ids(
    conn: sqlite3.Connection,
    reference: dict[str, Any],
    context: SearchScopeContext,
    reference_resources: list[dict[str, Any]],
    reference_workflow: set[tuple[str, str, str, str]],
    *,
    profile: str,
) -> list[int]:
    scope_sql, scope_params = _scope_predicate(context)
    params: dict[str, Any] = {
        **scope_params,
        "reference_asset_id": int(reference["asset_id"]),
        "normalizer_version": PROMPT_NORMALIZER_VERSION,
        "signature_extractor_version": GENERATION_SIGNATURE_EXTRACTOR_VERSION,
    }
    candidate_ids: list[int] = []
    seen: set[int] = set()

    def extend(rows) -> None:  # noqa: ANN001
        for row in rows:
            asset_id = int(row["asset_id"])
            if asset_id in seen:
                continue
            seen.add(asset_id)
            candidate_ids.append(asset_id)
            if len(candidate_ids) >= MAX_METADATA_CANDIDATES:
                return

    hash_fields = (
        ("exact_hash", "recipe_hash")
        if profile == "recipe"
        else (
            "exact_hash",
            "recipe_hash",
            "family_hash",
            "prompt_hash",
        )
    )
    for field in hash_fields:
        value = reference.get(field)
        if value is None:
            continue
        rows = conn.execute(
            f"""
            SELECT signature.asset_id
            FROM asset_generation_signatures AS signature
            JOIN assets AS asset ON asset.id = signature.asset_id
            WHERE signature.library_id = asset.library_id
              AND signature.{field} = :reference_hash
              AND signature.asset_id != :reference_asset_id
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              {scope_sql}
            ORDER BY signature.asset_id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
            {**params, "reference_hash": value},
        ).fetchall()
        extend(rows)
        if len(candidate_ids) >= MAX_METADATA_CANDIDATES:
            return candidate_ids

    if profile == "recipe":
        return candidate_ids

    model_hash = _clean_identity(reference.get("model_hash"))
    model_name = _clean_identity(reference.get("model"))
    if model_hash:
        model_predicate = "lower(trim(metadata.model_hash)) = :reference_model"
        model_value = model_hash
    elif model_name:
        model_predicate = "lower(trim(metadata.model)) = :reference_model"
        model_value = model_name
    else:
        model_predicate = ""
        model_value = None
    if model_value is not None:
        rows = []
        if _table_exists(conn, "asset_model_identity_values"):
            identity_predicate = (
                "identity.normalized_hash = :reference_model"
                if model_hash
                else "identity.normalized_name = :reference_model"
            )
            rows = conn.execute(
                f"""
                SELECT asset.id AS asset_id
                FROM asset_model_identity_values AS identity
                JOIN assets AS asset ON asset.id = identity.asset_id
                JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
                WHERE {identity_predicate}
                  AND asset.id != :reference_asset_id
                  AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
                  AND signature.source_mtime_ns = asset.mtime_ns
                  AND signature.source_size = asset.size
                  AND signature.normalizer_version = :normalizer_version
                  AND signature.extractor_version = :signature_extractor_version
                  {scope_sql}
                ORDER BY asset.id
                LIMIT {CANDIDATE_BRANCH_LIMIT}
                """,
                {**params, "reference_model": model_value},
            ).fetchall()
        if not rows:
            rows = conn.execute(
                f"""
            SELECT asset.id AS asset_id
            FROM image_metadata AS metadata
            JOIN assets AS asset
              ON asset.path = metadata.path
             AND asset.mtime_ns = metadata.mtime_ns
             AND asset.size = metadata.size
            JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
            WHERE {model_predicate}
              AND asset.id != :reference_asset_id
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              {scope_sql}
            ORDER BY asset.id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
                {**params, "reference_model": model_value},
            ).fetchall()
        extend(rows)

    identities = {_resource_identity(resource) for resource in reference_resources}
    resource_hashes = sorted(identity[2] for identity in identities if identity is not None and identity[1] == "hash")[
        :8
    ]
    resource_names = sorted(identity[2] for identity in identities if identity is not None and identity[1] == "name")[
        :8
    ]
    for _index, value in enumerate(resource_hashes):
        rows = conn.execute(
            f"""
            SELECT asset.id AS asset_id
            FROM image_resources AS resource
            JOIN assets AS asset ON asset.path = resource.path
            JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
            WHERE lower(trim(coalesce(resource.resource_hash, resource.hash))) = :resource_value
              AND asset.id != :reference_asset_id
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              {scope_sql}
            ORDER BY asset.id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
            {**params, "resource_value": value},
        ).fetchall()
        extend(rows)
    for _index, value in enumerate(resource_names):
        rows = conn.execute(
            f"""
            SELECT asset.id AS asset_id
            FROM image_resources AS resource
            JOIN assets AS asset ON asset.path = resource.path
            JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
            WHERE lower(trim(resource.name)) = :resource_value
              AND asset.id != :reference_asset_id
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              {scope_sql}
            ORDER BY asset.id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
            {**params, "resource_value": value},
        ).fetchall()
        extend(rows)

    for _index, (node_type, property_key, value_type, value) in enumerate(
        sorted(reference_workflow)[:MAX_WORKFLOW_CANDIDATE_PROPERTIES]
    ):
        typed_value = (
            int(value)
            if value_type == "integer"
            else float(value)
            if value_type == "real"
            else int(value == "true")
            if value_type == "boolean"
            else value
        )
        column = {
            "text": "value.value_text_folded",
            "integer": "value.value_integer",
            "real": "value.value_real",
            "boolean": "value.value_boolean",
            "uint64_token": "value.value_text",
        }[value_type]
        rows = conn.execute(
            f"""
            SELECT asset.id AS asset_id
            FROM workflow_nodes AS node
            JOIN workflow_property_values AS value ON value.node_id = node.id
            JOIN assets AS asset ON asset.id = node.asset_id
            JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
            WHERE node.node_type = :workflow_node
              AND value.property_key = :workflow_property
              AND value.value_type = :workflow_type
              AND {column} = :workflow_value
              AND asset.id != :reference_asset_id
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              {scope_sql}
            ORDER BY asset.id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
            {
                **params,
                "workflow_node": node_type,
                "workflow_property": property_key,
                "workflow_type": value_type,
                "workflow_value": typed_value,
            },
        ).fetchall()
        extend(rows)

    atoms = normalize_prompt_atoms(reference.get("prompt")) + normalize_prompt_atoms(reference.get("negative_prompt"))
    selected = [atom for atom in select_prompt_atoms_for_fts(atoms) if not is_common_prompt_atom(atom.identity)]
    if selected and len(candidate_ids) < MAX_METADATA_CANDIDATES:
        fts_query = " OR ".join(f'"{atom.identity.replace(chr(34), chr(34) * 2)}"' for atom in selected)
        rows = conn.execute(
            f"""
            SELECT asset.id AS asset_id
            FROM image_metadata_fts AS fts
            JOIN image_metadata AS metadata ON metadata.id = fts.rowid
            JOIN assets AS asset
              ON asset.path = metadata.path
             AND asset.mtime_ns = metadata.mtime_ns
             AND asset.size = metadata.size
            JOIN asset_generation_signatures AS signature ON signature.asset_id = asset.id
            WHERE image_metadata_fts MATCH :prompt_fts_query
              AND asset.id != :reference_asset_id
              AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
              AND signature.source_mtime_ns = asset.mtime_ns
              AND signature.source_size = asset.size
              AND signature.normalizer_version = :normalizer_version
              AND signature.extractor_version = :signature_extractor_version
              {scope_sql}
            ORDER BY bm25(image_metadata_fts), asset.id
            LIMIT {CANDIDATE_BRANCH_LIMIT}
            """,
            {**params, "prompt_fts_query": fts_query},
        ).fetchall()
        extend(rows)
    return candidate_ids


def _candidate_rows(
    conn: sqlite3.Connection, candidate_ids: list[int], context: SearchScopeContext
) -> list[dict[str, Any]]:
    if not candidate_ids:
        return []
    cte, params = _eligible_cte(context)
    placeholders = ",".join(f":candidate_{index}" for index in range(len(candidate_ids)))
    params.update({f"candidate_{index}": asset_id for index, asset_id in enumerate(candidate_ids)})
    rows = conn.execute(cte + f"SELECT * FROM eligible WHERE asset_id IN ({placeholders})", params).fetchall()
    by_id = {int(row["asset_id"]): dict(row) for row in rows}
    return [by_id[asset_id] for asset_id in candidate_ids if asset_id in by_id]


def _prompt_weights(row: dict[str, Any]) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for kind, field in (("positive", "prompt"), ("negative", "negative_prompt")):
        for atom in normalize_prompt_atoms(row.get(field)):
            salience = 0.15 if is_common_prompt_atom(atom.identity) else 1.0
            weight = float(Decimal(atom.weight)) * salience * min(1.5, 0.75 + len(atom.identity) / 80)
            result[(kind, atom.identity)] = max(result.get((kind, atom.identity), 0.0), weight)
    return result


def _weighted_jaccard(left: dict[tuple[str, str], float], right: dict[tuple[str, str], float]) -> tuple[float, bool]:
    keys = set(left) | set(right)
    if not keys:
        return 0.0, False
    intersection = sum(min(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    union = sum(max(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    meaningful = any(key in left and key in right and not is_common_prompt_atom(key[1]) for key in keys)
    return (intersection / union if union else 0.0), meaningful


def _settings_proximity(reference: dict[str, Any], candidate: dict[str, Any]) -> float:
    comparisons: list[float] = []
    for field in ("sampler", "scheduler"):
        left, right = _clean_identity(reference.get(field)), _clean_identity(candidate.get(field))
        if left is not None and right is not None:
            comparisons.append(float(left == right))
    for field, tolerance in (
        ("steps", 10.0),
        ("cfg_scale", 3.0),
        ("width", 1024.0),
        ("height", 1024.0),
        ("denoising_strength", 0.5),
    ):
        left, right = canonical_number(reference.get(field)), canonical_number(candidate.get(field))
        if left is None or right is None:
            continue
        distance = abs(float(Decimal(left)) - float(Decimal(right)))
        comparisons.append(max(0.0, 1.0 - distance / tolerance))
    return sum(comparisons) / len(comparisons) if comparisons else 0.0


def _signal_reasons(
    same_model_hash: bool,
    same_model_name: bool,
    shared_resources: set[tuple[str, str, str]],
    shared_workflow: set[tuple[str, str, str, str]],
) -> list[str]:
    reasons: list[str] = []
    if same_model_hash:
        reasons.append("same_model_hash")
    elif same_model_name:
        reasons.append("same_model_name")
    if any("lora" in identity[0] for identity in shared_resources):
        reasons.append("shared_lora")
    elif shared_resources:
        reasons.append("shared_resource")
    if shared_workflow:
        reasons.append("shared_workflow_property")
    return reasons


def _score_candidate(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    resources: dict[int, list[dict[str, Any]]],
    workflow: dict[int, set[tuple[str, str, str, str]]],
) -> RankedCandidate | None:
    reference_id, candidate_id = int(reference["asset_id"]), int(candidate["asset_id"])
    prompt_score, meaningful_prompt = _weighted_jaccard(_prompt_weights(reference), _prompt_weights(candidate))
    reference_resources = {
        identity for row in resources.get(reference_id, []) if (identity := _resource_identity(row)) is not None
    }
    candidate_resources = {
        identity for row in resources.get(candidate_id, []) if (identity := _resource_identity(row)) is not None
    }
    shared_resources = reference_resources & candidate_resources
    resource_score = len(shared_resources) / len(reference_resources | candidate_resources) if shared_resources else 0.0
    reference_model_hash, candidate_model_hash = (
        _clean_identity(reference.get("model_hash")),
        _clean_identity(candidate.get("model_hash")),
    )
    same_model_hash = bool(reference_model_hash and reference_model_hash == candidate_model_hash)
    reference_model_name, candidate_model_name = (
        _clean_identity(reference.get("model")),
        _clean_identity(candidate.get("model")),
    )
    same_model_name = bool(
        not same_model_hash and reference_model_name and reference_model_name == candidate_model_name
    )
    shared_workflow = workflow.get(reference_id, set()) & workflow.get(candidate_id, set())
    compatibility_score = max(
        float(same_model_hash or same_model_name), resource_score, min(1.0, len(shared_workflow) / 3)
    )
    settings_score = _settings_proximity(reference, candidate)
    signal = same_model_hash or same_model_name or bool(shared_resources) or bool(shared_workflow)
    exact_same = bool(reference.get("exact_hash") and reference["exact_hash"] == candidate.get("exact_hash"))
    recipe_same = bool(reference.get("recipe_hash") and reference["recipe_hash"] == candidate.get("recipe_hash"))
    family_same = bool(reference.get("family_hash") and reference["family_hash"] == candidate.get("family_hash"))
    prompt_same = bool(reference.get("prompt_hash") and reference["prompt_hash"] == candidate.get("prompt_hash"))

    if exact_same:
        tier, reasons = 100, ("same_exact_signature", "same_recipe", "same_generation_family")
    elif recipe_same:
        tier, reasons = 90, ("same_recipe", "same_generation_family")
    elif family_same and (meaningful_prompt or shared_resources):
        tier, reasons = 80, ("same_generation_family",)
    elif prompt_same and meaningful_prompt and signal:
        tier, reasons = (
            70,
            (
                "same_prompt",
                *_signal_reasons(same_model_hash, same_model_name, shared_resources, shared_workflow),
            ),
        )
    elif prompt_score >= 0.2 and meaningful_prompt and signal:
        reason_list = [
            "strong_prompt_overlap",
            *_signal_reasons(same_model_hash, same_model_name, shared_resources, shared_workflow),
        ]
        if settings_score >= 0.65:
            reason_list.append("similar_generation_settings")
        tier, reasons = 60, tuple(reason_list)
    elif meaningful_prompt and prompt_score >= 0.1 and signal:
        tier, reasons = 40, ("strong_prompt_overlap",)
    else:
        return None
    return RankedCandidate(candidate, tier, reasons, prompt_score, resource_score, compatibility_score, settings_score)


def _relative_parent(parent_path: str, context: SearchScopeContext) -> str:
    root = Path(context.folder_path) if context.kind == "folder" and context.folder_path else Path(os.sep)
    try:
        relative = Path(canonicalize_catalog_path(parent_path)).relative_to(canonicalize_catalog_path(root))
    except ValueError:
        return ""
    return "" if str(relative) == "." else str(relative)


def _result(candidate: RankedCandidate, context: SearchScopeContext) -> RelatedSearchResultV1:
    row = candidate.row
    metadata_score = round(
        candidate.prompt_score * 0.55
        + candidate.resource_score * 0.2
        + candidate.compatibility_score * 0.15
        + candidate.settings_score * 0.1,
        6,
    )
    prompt = " ".join(str(row.get("prompt") or row.get("negative_prompt") or "").split())[:240]
    return RelatedSearchResultV1(
        asset_id=int(row["asset_id"]),
        library_id=int(row["library_id"]),
        library_name=str(row["library_name"]),
        name=str(row["name"]),
        path=str(row["path"]),
        type="image",
        parent_path=str(row["parent_path"]),
        relative_path=_relative_parent(str(row["parent_path"]), context),
        mtime=float(row["mtime"] or 0),
        width=row.get("width"),
        height=row.get("height"),
        match_type="related",
        prompt_snippet=prompt,
        model=str(row.get("model") or ""),
        sampler=str(row.get("sampler") or ""),
        seed=str(row.get("seed") or ""),
        relation_tier=candidate.tier,
        relation_reasons=list(candidate.reasons),
        metadata_score=metadata_score,
    )


def rank_related_metadata(
    reference_asset_id: int,
    context: SearchScopeContext,
    *,
    profile: str,
    limit: int,
) -> list[RelatedSearchResultV1]:
    """Collect bounded persisted candidates, then score them outside SQLite."""
    with _DB_LOCK, _connect() as conn:
        reference = _reference_row(conn, reference_asset_id)
        if reference is None:
            return []
        reference_resources = _load_resources(conn, [reference])
        reference_workflow = _load_workflow(conn, [reference_asset_id])
        candidate_ids = _candidate_ids(
            conn,
            reference,
            context,
            reference_resources.get(reference_asset_id, []),
            reference_workflow.get(reference_asset_id, set()),
            profile=profile,
        )
        candidates = _candidate_rows(conn, candidate_ids, context)
        all_rows = [reference, *candidates]
        resources = _load_resources(conn, all_rows)
        workflow = _load_workflow(conn, [int(row["asset_id"]) for row in all_rows])

    scored = [
        ranked
        for candidate in candidates
        if (ranked := _score_candidate(reference, candidate, resources, workflow)) is not None
        and (profile != "recipe" or ranked.tier >= 90)
    ]
    scored.sort(
        key=lambda item: (
            -item.tier,
            -item.prompt_score,
            -item.resource_score,
            -item.compatibility_score,
            -item.settings_score,
            -int(item.row.get("mtime_ns") or 0),
            int(item.row["asset_id"]),
        )
    )
    return [_result(item, context) for item in scored[:limit]]
