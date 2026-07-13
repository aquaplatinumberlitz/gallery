"""Versioned prompt normalization and compact generation-intent signatures."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

PROMPT_NORMALIZER_VERSION = 1
GENERATION_SIGNATURE_EXTRACTOR_VERSION = 1
MAX_PROMPT_ATOMS = 64
MAX_PROMPT_ATOM_CHARS = 160
MAX_FTS_PROMPT_ATOMS = 16
PROMPT_BOILERPLATE_POLICY_VERSION = 1
MIN_EMPHASIS_WEIGHT = Decimal("0.1")
MAX_EMPHASIS_WEIGHT = Decimal("2")

_EXPLICIT_WEIGHT = re.compile(r"^\((.*):([+-]?(?:\d+(?:\.\d+)?|\.\d+))\)$", re.DOTALL)
_COMMON_PROMPT_ATOMS_V1 = frozenset(
    {
        "4k",
        "8k",
        "best quality",
        "high quality",
        "highres",
        "masterpiece",
        "ultra detailed",
    }
)
_RECIPE_WORKFLOW_PROPERTIES = {
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
_EXACT_WORKFLOW_PROPERTIES = {"seed", "noise_seed"}


@dataclass(frozen=True)
class PromptAtom:
    """One normalized prompt atom with stable identity and bounded emphasis."""

    display: str
    identity: str
    weight: str


def canonical_number(value: Any) -> str | None:
    """Format finite numeric metadata without exponent notation or negative zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not decimal.is_finite():
        return None
    if decimal == 0:
        return "0"
    rendered = format(decimal.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _canonical_weight(value: Decimal) -> str:
    return canonical_number(min(MAX_EMPHASIS_WEIGHT, max(MIN_EMPHASIS_WEIGHT, value))) or "1"


def _split_prompt_atoms(value: str) -> list[str]:
    atoms: list[str] = []
    current: list[str] = []
    round_depth = 0
    square_depth = 0
    for character in value:
        if character == "(":
            round_depth += 1
        elif character == ")" and round_depth:
            round_depth -= 1
        elif character == "[":
            square_depth += 1
        elif character == "]" and square_depth:
            square_depth -= 1
        if character in {",", "\n", "\r"} and round_depth == 0 and square_depth == 0:
            atoms.append("".join(current))
            current = []
        else:
            current.append(character)
    atoms.append("".join(current))
    return atoms


def _unwrap_emphasis(value: str) -> tuple[str, str]:
    text = value
    weight = Decimal("1")
    explicit = _EXPLICIT_WEIGHT.fullmatch(text)
    if explicit is not None:
        text = explicit.group(1)
        try:
            weight *= Decimal(explicit.group(2))
        except InvalidOperation:
            weight = Decimal("1")
    else:
        while len(text) >= 2 and text.startswith("(") and text.endswith(")"):
            text = text[1:-1].strip()
            weight *= Decimal("1.1")
        while len(text) >= 2 and text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
            weight *= Decimal("0.9")
    return text, _canonical_weight(weight)


def normalize_prompt_atoms(value: Any, *, limit: int = MAX_PROMPT_ATOMS) -> list[PromptAtom]:
    """Normalize a positive or negative prompt into bounded comma/newline atoms."""
    if not isinstance(value, str) or limit < 1:
        return []
    normalized = unicodedata.normalize("NFKC", value)
    result: list[PromptAtom] = []
    for candidate in _split_prompt_atoms(normalized):
        controls = sum(unicodedata.category(character).startswith("C") for character in candidate)
        if controls > max(1, len(candidate) // 10):
            continue
        display, weight = _unwrap_emphasis(" ".join(candidate.strip().split()))
        display = " ".join(display.strip().split())
        if not display or len(display) > MAX_PROMPT_ATOM_CHARS:
            continue
        identity = display.casefold()
        if not identity:
            continue
        result.append(PromptAtom(display=display, identity=identity, weight=weight))
        if len(result) >= min(limit, MAX_PROMPT_ATOMS):
            break
    return result


def select_prompt_atoms_for_fts(atoms: list[PromptAtom], *, limit: int = MAX_FTS_PROMPT_ATOMS) -> list[PromptAtom]:
    """Select one bounded stable set of distinct atoms for candidate lookup."""
    distinct: dict[str, tuple[int, PromptAtom]] = {}
    for ordinal, atom in enumerate(atoms):
        existing = distinct.get(atom.identity)
        if existing is None or Decimal(atom.weight) > Decimal(existing[1].weight):
            distinct[atom.identity] = (ordinal, atom)
    ranked = sorted(
        distinct.values(),
        key=lambda item: (
            item[1].identity in _COMMON_PROMPT_ATOMS_V1,
            -float(Decimal(item[1].weight)),
            -len(item[1].identity),
            item[0],
            item[1].identity,
        ),
    )
    return [item[1] for item in ranked[: min(max(1, limit), MAX_FTS_PROMPT_ATOMS)]]


def is_common_prompt_atom(identity: str) -> bool:
    """Return the version-1 boilerplate classification used by ranking."""
    return identity in _COMMON_PROMPT_ATOMS_V1


def _clean_identity(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", str(value)).strip().split()).casefold()
    return normalized or None


def _digest(value: Any) -> bytes:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _typed_workflow_values(metadata_json: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        metadata = json.loads(metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return [], []
    if not isinstance(metadata, dict):
        return [], []
    document = metadata.get("_workflow_document")
    if not isinstance(document, dict) or document.get("version") != 1 or not isinstance(document.get("nodes"), list):
        return [], []
    recipe: list[dict[str, Any]] = []
    exact: list[dict[str, Any]] = []
    for node in document["nodes"][:2048]:
        if not isinstance(node, dict):
            continue
        node_type = _clean_identity(node.get("node_type"))
        if node_type is None:
            continue
        for prop in node.get("properties", [])[:32]:
            if not isinstance(prop, dict):
                continue
            key = str(prop.get("property_key") or "")
            if key not in _RECIPE_WORKFLOW_PROPERTIES | _EXACT_WORKFLOW_PROPERTIES:
                continue
            value_type = prop.get("value_type")
            if value_type == "text":
                value = _clean_identity(prop.get("value_text"))
            elif value_type in {"integer", "real"}:
                value = canonical_number(prop.get(f"value_{value_type}"))
            elif value_type == "boolean":
                raw_boolean = prop.get("value_boolean")
                value = bool(raw_boolean) if raw_boolean in {0, 1} else None
            elif value_type == "uint64_token":
                value = str(prop.get("value_text")) if prop.get("value_text") is not None else None
            else:
                value = None
            if value is None:
                continue
            row = {"node_type": node_type, "property": key, "value": value}
            (exact if key in _EXACT_WORKFLOW_PROPERTIES else recipe).append(row)

    def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return row["node_type"], row["property"], str(row["value"])

    return sorted(recipe, key=sort_key), sorted(exact, key=sort_key)


def _metadata_source(asset: dict[str, Any]) -> dict[str, Any] | None:
    from .metadata_store._db import _DB_LOCK, _connect
    from .metadata_store._schema import initialize_database

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT prompt, negative_prompt, model, sampler, seed, steps, cfg_scale,
                   scheduler, model_hash, hires_upscale, hires_steps,
                   denoising_strength, vae, width, height, metadata_json
            FROM image_metadata
            WHERE path = ? AND mtime_ns = ? AND size = ?
            """,
            (str(asset["path"]), int(asset.get("mtime_ns") or 0), int(asset.get("size") or 0)),
        ).fetchone()
        resources = conn.execute(
            """
            SELECT kind, name, hash, resource_hash, weight, strength
            FROM image_resources WHERE path = ? ORDER BY id
            """,
            (str(asset["path"]),),
        ).fetchall()
    if row is None:
        return None
    return {"metadata": dict(row), "resources": [dict(item) for item in resources]}


def _resource_inputs(resources: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str | None]]]:
    identities: dict[tuple[str, str, str], dict[str, str]] = {}
    recipe: dict[tuple[str, str, str], dict[str, str | None]] = {}
    for resource in resources:
        kind = _clean_identity(resource.get("kind")) or "resource"
        resource_hash = _clean_identity(resource.get("resource_hash") or resource.get("hash"))
        name = _clean_identity(resource.get("name"))
        if resource_hash:
            identity = {"kind": kind, "identity_type": "hash", "identity": resource_hash}
        elif name:
            identity = {"kind": kind, "identity_type": "name", "identity": name}
        else:
            continue
        identity_key = (identity["kind"], identity["identity_type"], identity["identity"])
        identities[identity_key] = identity
        recipe[identity_key] = {
            **identity,
            "weight": canonical_number(resource.get("weight") or resource.get("strength")),
        }
    return [identities[key] for key in sorted(identities)], [recipe[key] for key in sorted(recipe)]


def build_generation_signature_payload(asset: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Build explicit canonical signature layers from one persisted metadata snapshot."""
    metadata = source["metadata"]
    positive = normalize_prompt_atoms(metadata.get("prompt"))
    negative = normalize_prompt_atoms(metadata.get("negative_prompt"))
    prompt_input = {
        "positive": [{"identity": atom.identity, "weight": atom.weight} for atom in positive],
        "negative": [{"identity": atom.identity, "weight": atom.weight} for atom in negative],
    }
    prompt_hash = _digest(prompt_input) if positive or negative else None

    model_hash = _clean_identity(metadata.get("model_hash"))
    model_name = _clean_identity(metadata.get("model"))
    model_identity = (
        {"identity_type": "hash", "identity": model_hash}
        if model_hash
        else ({"identity_type": "name", "identity": model_name} if model_name else None)
    )
    resource_identities, resource_recipe = _resource_inputs(source["resources"])
    family_input = {
        "prompt_hash": prompt_hash.hex() if prompt_hash else None,
        "model": model_identity,
        "resources": resource_identities,
    }
    family_hash = _digest(family_input) if prompt_hash and (model_identity or resource_identities) else None

    workflow_recipe, workflow_exact = _typed_workflow_values(metadata.get("metadata_json"))
    recipe_input = {
        "family_hash": family_hash.hex() if family_hash else None,
        "sampler": _clean_identity(metadata.get("sampler")),
        "scheduler": _clean_identity(metadata.get("scheduler")),
        "steps": canonical_number(metadata.get("steps")),
        "cfg": canonical_number(metadata.get("cfg_scale")),
        "width": canonical_number(metadata.get("width")),
        "height": canonical_number(metadata.get("height")),
        "denoising": canonical_number(metadata.get("denoising_strength")),
        "hires_upscale": canonical_number(metadata.get("hires_upscale")),
        "hires_steps": canonical_number(metadata.get("hires_steps")),
        "vae": _clean_identity(metadata.get("vae")),
        "resources": resource_recipe,
        "workflow": workflow_recipe,
    }
    recipe_hash = _digest(recipe_input) if family_hash else None
    recorded_seed = _clean_identity(metadata.get("seed"))
    exact_input = {
        "recipe_hash": recipe_hash.hex() if recipe_hash else None,
        "seed": recorded_seed,
        "workflow": workflow_exact,
    }
    exact_hash = _digest(exact_input) if recipe_hash and (recorded_seed or workflow_exact) else None
    return {
        "prompt_hash": prompt_hash,
        "family_hash": family_hash,
        "recipe_hash": recipe_hash,
        "exact_hash": exact_hash,
        "normalizer_version": PROMPT_NORMALIZER_VERSION,
        "extractor_version": GENERATION_SIGNATURE_EXTRACTOR_VERSION,
        "source_mtime_ns": int(asset.get("mtime_ns") or 0),
        "source_size": int(asset.get("size") or 0),
    }


def extract_generation_signature(asset: dict[str, Any]):  # noqa: ANN201
    """Extract a compact signature from current persisted metadata only."""
    from .search_indexer import SearchExtractionResult

    if str(asset.get("type")) != "image":
        return SearchExtractionResult(status="not_applicable", payload=None)
    source = _metadata_source(asset)
    if source is None:
        return SearchExtractionResult(status="not_applicable", payload=None)
    payload = build_generation_signature_payload(asset, source)
    status = "ready" if payload["prompt_hash"] is not None else "not_applicable"
    return SearchExtractionResult(status=status, payload=payload)


def persist_generation_signature(
    conn: sqlite3.Connection, asset: dict[str, Any], payload: dict[str, Any] | None
) -> None:
    """Atomically replace one active asset's current signature row."""
    asset_id = int(asset["id"])
    conn.execute("DELETE FROM asset_generation_signatures WHERE asset_id = ?", (asset_id,))
    if payload is None:
        return
    conn.execute(
        """
        INSERT INTO asset_generation_signatures (
          asset_id, library_id, prompt_hash, family_hash, recipe_hash, exact_hash,
          normalizer_version, extractor_version, source_mtime_ns, source_size, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            int(asset["library_id"]),
            payload["prompt_hash"],
            payload["family_hash"],
            payload["recipe_hash"],
            payload["exact_hash"],
            int(payload["normalizer_version"]),
            int(payload["extractor_version"]),
            int(payload["source_mtime_ns"]),
            int(payload["source_size"]),
            time.time(),
        ),
    )


def invalidate_generation_signature_conn(conn: sqlite3.Connection, asset_id: int) -> None:
    """Remove a stale signature and extraction marker inside a metadata write."""
    conn.execute("DELETE FROM asset_generation_signatures WHERE asset_id = ?", (asset_id,))
    conn.execute(
        "DELETE FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'generation_signatures'",
        (asset_id,),
    )


def schedule_generation_signature_backfill(library_id: int) -> None:
    """Coalesce one durable missing-signature rebuild for a library."""
    from .metadata_store.search_index_store import SearchIndexJobConflict, create_search_index_job
    from .search_indexer import search_index_worker

    with suppress(SearchIndexJobConflict):
        create_search_index_job(
            "generation_signatures",
            library_id,
            mode="missing",
            schema_version=1,
            extractor_version=GENERATION_SIGNATURE_EXTRACTOR_VERSION,
        )
    search_index_worker.wake()
