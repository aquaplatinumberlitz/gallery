"""Typed, code-owned ComfyUI workflow extraction and same-node SQL predicates."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from .metadata_store._db import _DB_LOCK, _connect
from .metadata_store._schema import initialize_database

WORKFLOW_EXTRACTOR_VERSION = 1
MAX_WORKFLOW_SOURCE_BYTES = 2 * 1024 * 1024
MAX_WORKFLOW_NODES = 2_048
MAX_PROPERTIES_PER_NODE = 32
MAX_PROPERTY_ROWS = 8_192
MAX_IDENTIFIER_CHARS = 128
MAX_TEXT_VALUE_CHARS = 512
UINT64_MAX = (1 << 64) - 1

ValueType = Literal["text", "integer", "real", "boolean", "uint64_token"]


@dataclass(frozen=True)
class WorkflowPropertyDefinition:
    """One fixed searchable property and its allowed operators."""

    value_type: ValueType
    operators: tuple[str, ...]


TEXT = WorkflowPropertyDefinition("text", ("eq", "prefix", "contains"))
INTEGER = WorkflowPropertyDefinition("integer", ("eq", "gt", "gte", "lt", "lte"))
REAL = WorkflowPropertyDefinition("real", ("eq", "gt", "gte", "lt", "lte"))
BOOLEAN = WorkflowPropertyDefinition("boolean", ("eq",))
UINT64 = WorkflowPropertyDefinition("uint64_token", ("eq",))

WORKFLOW_REGISTRY_V1: dict[str, dict[str, WorkflowPropertyDefinition]] = {
    "KSampler": {
        "seed": UINT64,
        "steps": INTEGER,
        "cfg": REAL,
        "sampler_name": TEXT,
        "scheduler": TEXT,
        "denoise": REAL,
    },
    "KSamplerAdvanced": {
        "noise_seed": UINT64,
        "steps": INTEGER,
        "start_at_step": INTEGER,
        "end_at_step": INTEGER,
        "cfg": REAL,
        "sampler_name": TEXT,
        "scheduler": TEXT,
        "add_noise": BOOLEAN,
        "return_with_leftover_noise": BOOLEAN,
    },
    "CheckpointLoaderSimple": {"ckpt_name": TEXT},
    "LoraLoader": {"lora_name": TEXT, "strength_model": REAL, "strength_clip": REAL},
    "LoraLoaderModelOnly": {"lora_name": TEXT, "strength_model": REAL, "strength_clip": REAL},
    "EmptyLatentImage": {"width": INTEGER, "height": INTEGER, "batch_size": INTEGER},
    "VAELoader": {"vae_name": TEXT},
    "ControlNetLoader": {"control_net_name": TEXT},
    "UNETLoader": {"unet_name": TEXT, "weight_dtype": TEXT},
    "CLIPLoader": {"clip_name": TEXT, "clip_name1": TEXT, "clip_name2": TEXT, "type": TEXT},
    "DualCLIPLoader": {"clip_name": TEXT, "clip_name1": TEXT, "clip_name2": TEXT, "type": TEXT},
    "SaveImage": {"filename_prefix": TEXT},
}

# Versioned UI-graph widget positions. API prompt graphs use named inputs and
# remain authoritative whenever they are available.
UI_WIDGET_KEYS_V1: dict[str, tuple[str, ...]] = {
    "KSampler": ("seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"),
    "KSamplerAdvanced": (
        "add_noise",
        "noise_seed",
        "control_after_generate",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "start_at_step",
        "end_at_step",
        "return_with_leftover_noise",
    ),
    "CheckpointLoaderSimple": ("ckpt_name",),
    "LoraLoader": ("lora_name", "strength_model", "strength_clip"),
    "LoraLoaderModelOnly": ("lora_name", "strength_model"),
    "EmptyLatentImage": ("width", "height", "batch_size"),
    "VAELoader": ("vae_name",),
    "ControlNetLoader": ("control_net_name",),
    "UNETLoader": ("unet_name", "weight_dtype"),
    "CLIPLoader": ("clip_name", "type"),
    "DualCLIPLoader": ("clip_name1", "clip_name2", "type"),
    "SaveImage": ("filename_prefix",),
}


class WorkflowExtractionError(ValueError):
    """Bounded workflow extraction failure with a public-safe code."""

    def __init__(self, code: str) -> None:
        """Store a bounded machine-readable extraction error code."""
        super().__init__(code)
        self.code = code


def workflow_registry_capability() -> dict[str, Any]:
    """Serialize the fixed registry for capability-driven clients."""
    return {
        "version": 1,
        "nodes": {
            node_type: {
                property_key: {"type": definition.value_type, "operators": list(definition.operators)}
                for property_key, definition in properties.items()
            }
            for node_type, properties in WORKFLOW_REGISTRY_V1.items()
        },
    }


def _node_title(node: dict[str, Any]) -> str | None:
    meta = node.get("_meta")
    candidate = meta.get("title") if isinstance(meta, dict) else node.get("title")
    if not isinstance(candidate, str):
        return None
    title = candidate.strip()
    return title[:MAX_IDENTIFIER_CHARS] if title else None


def _typed_value(value: Any, definition: WorkflowPropertyDefinition) -> dict[str, Any] | None:
    if isinstance(value, (list, dict)) or value is None:
        return None
    if definition.value_type == "text":
        if not isinstance(value, str) or len(value) > MAX_TEXT_VALUE_CHARS:
            return None
        return {"value_type": "text", "value_text": value, "value_text_folded": value.casefold()}
    if definition.value_type == "boolean":
        return {"value_type": "boolean", "value_boolean": int(value)} if isinstance(value, bool) else None
    if definition.value_type == "uint64_token":
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
            parsed = int(value)
        else:
            return None
        if parsed < 0 or parsed > UINT64_MAX:
            return None
        return {"value_type": "uint64_token", "value_text": str(parsed)}
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    if definition.value_type == "integer":
        if int(value) != value or value < -(1 << 63) or value > (1 << 63) - 1:
            return None
        return {"value_type": "integer", "value_integer": int(value)}
    return {"value_type": "real", "value_real": float(value)}


def _normalized_node(node_key: Any, node: dict[str, Any], *, ui_graph: bool) -> dict[str, Any] | None:
    key = str(node_key)
    node_type = node.get("class_type") or node.get("type")
    if not key or len(key) > MAX_IDENTIFIER_CHARS or not isinstance(node_type, str):
        return None
    if not node_type or len(node_type) > MAX_IDENTIFIER_CHARS:
        return None
    registry = WORKFLOW_REGISTRY_V1.get(node_type)
    properties: list[dict[str, Any]] = []
    if registry is not None:
        if ui_graph:
            widget_keys = UI_WIDGET_KEYS_V1.get(node_type)
            widgets = node.get("widgets_values")
            inputs = dict(zip(widget_keys, widgets, strict=False)) if widget_keys and isinstance(widgets, list) else {}
        else:
            inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        for property_key, definition in registry.items():
            if property_key not in inputs:
                continue
            typed = _typed_value(inputs[property_key], definition)
            if typed is not None:
                properties.append({"property_key": property_key, "ordinal": 0, **typed})
            if len(properties) >= MAX_PROPERTIES_PER_NODE:
                break
    return {
        "node_key": key,
        "node_type": node_type,
        "title": _node_title(node),
        "properties": properties,
    }


def normalize_workflow_document(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize one API prompt graph or version-mapped UI graph."""
    raw_nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else data
    ui_graph = isinstance(raw_nodes, list)
    if ui_graph:
        source_nodes = [node for node in raw_nodes if isinstance(node, dict)]
        iterable = ((node.get("id"), node) for node in source_nodes)
    elif isinstance(raw_nodes, dict):
        iterable = raw_nodes.items()
    else:
        raise WorkflowExtractionError("workflow_invalid_document")
    nodes: list[dict[str, Any]] = []
    property_rows = 0
    for node_key, node in iterable:
        if len(nodes) >= MAX_WORKFLOW_NODES:
            raise WorkflowExtractionError("workflow_node_limit")
        if not isinstance(node, dict):
            continue
        normalized = _normalized_node(node_key, node, ui_graph=ui_graph)
        if normalized is None:
            continue
        property_rows += len(normalized["properties"])
        if property_rows > MAX_PROPERTY_ROWS:
            raise WorkflowExtractionError("workflow_property_limit")
        nodes.append(normalized)
    return {"version": 1, "nodes": nodes}


def _json_workflow_from_raw(raw: str) -> dict[str, Any] | None:
    if len(raw.encode("utf-8")) > MAX_WORKFLOW_SOURCE_BYTES:
        raise WorkflowExtractionError("workflow_source_too_large")
    candidates = [raw]
    for line in raw.splitlines():
        if line.startswith(("prompt: ", "workflow: ")):
            candidates.append(line.split(": ", 1)[1])
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            try:
                return normalize_workflow_document(decoded)
            except WorkflowExtractionError as exc:
                if exc.code != "workflow_invalid_document":
                    raise
    return None


def _workflow_source(asset: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT metadata_json, raw_metadata_text, tool FROM image_metadata WHERE path = ?",
            (str(asset["path"]),),
        ).fetchone()
    if row is None:
        return None, False
    metadata: dict[str, Any] = {}
    try:
        decoded = json.loads(str(row["metadata_json"] or "{}"))
        metadata = decoded if isinstance(decoded, dict) else {}
    except json.JSONDecodeError:
        pass
    normalized = metadata.get("_workflow_document")
    if isinstance(normalized, dict) and normalized.get("version") == 1 and isinstance(normalized.get("nodes"), list):
        return normalized, True
    raw = str(row["raw_metadata_text"] or "")
    document = _json_workflow_from_raw(raw) if raw else None
    looks_comfy = str(row["tool"] or metadata.get("tool") or "") == "ComfyUI"
    return document, looks_comfy


def extract_workflow_properties(asset: dict[str, Any]):  # noqa: ANN201
    """Read persisted metadata once and return typed workflow rows."""
    from .search_indexer import SearchExtractionResult

    try:
        document, looks_comfy = _workflow_source(asset)
    except WorkflowExtractionError as exc:
        return SearchExtractionResult(status="failed", error_code=exc.code)
    if document is None:
        if looks_comfy:
            return SearchExtractionResult(status="failed", error_code="workflow_parse_failed")
        return SearchExtractionResult(status="not_applicable", payload={"nodes": []})
    return SearchExtractionResult(status="ready", payload=document)


def persist_workflow_properties(conn: sqlite3.Connection, asset: dict[str, Any], payload: dict[str, Any]) -> None:
    """Atomically replace one asset's normalized nodes and typed properties."""
    asset_id = int(asset["id"])
    fingerprint = f"{int(asset.get('mtime_ns') or 0)}:{int(asset.get('size') or 0)}"
    conn.execute("DELETE FROM workflow_nodes WHERE asset_id = ?", (asset_id,))
    for node in payload.get("nodes", []):
        cursor = conn.execute(
            """
            INSERT INTO workflow_nodes (
              asset_id, node_key, node_type, title, extractor_version, source_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                node["node_key"],
                node["node_type"],
                node.get("title"),
                WORKFLOW_EXTRACTOR_VERSION,
                fingerprint,
            ),
        )
        node_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO workflow_property_values (
              node_id, property_key, ordinal, value_type, value_text,
              value_text_folded, value_integer, value_real, value_boolean
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    node_id,
                    prop["property_key"],
                    int(prop.get("ordinal", 0)),
                    prop["value_type"],
                    prop.get("value_text"),
                    prop.get("value_text_folded"),
                    prop.get("value_integer"),
                    prop.get("value_real"),
                    prop.get("value_boolean"),
                )
                for prop in node.get("properties", [])
            ),
        )


def invalidate_workflow_properties_conn(conn: sqlite3.Connection, asset_id: int, library_id: int) -> None:
    """Remove stale typed workflow rows and mark initialized coverage incomplete."""
    extraction = conn.execute(
        "SELECT status FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'workflow_properties'",
        (asset_id,),
    ).fetchone()
    conn.execute("DELETE FROM workflow_nodes WHERE asset_id = ?", (asset_id,))
    conn.execute(
        "DELETE FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'workflow_properties'",
        (asset_id,),
    )
    from .metadata_store.search_index_store import mark_search_index_asset_stale_conn

    mark_search_index_asset_stale_conn(
        conn,
        "workflow_properties",
        library_id,
        str(extraction["status"]) if extraction is not None else None,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_workflow_groups(groups: list[Any]) -> None:
    """Reject unsupported registry/property/operator/value combinations."""
    for group_index, group in enumerate(groups):
        node_type = str(group.node_type)
        registry = WORKFLOW_REGISTRY_V1.get(node_type)
        if registry is None:
            raise ValueError(f"workflow_groups[{group_index}].node_type is unsupported")
        for predicate_index, predicate in enumerate(group.predicates):
            definition = registry.get(str(predicate.property))
            field = f"workflow_groups[{group_index}].predicates[{predicate_index}]"
            if definition is None:
                raise ValueError(f"{field}.property is unsupported for {node_type}")
            if predicate.op not in definition.operators:
                raise ValueError(f"{field}.op is unsupported for {definition.value_type}")
            if _typed_value(predicate.value, definition) is None:
                raise ValueError(f"{field}.value is invalid for {definition.value_type}")


def build_workflow_group_conditions(groups: list[Any]) -> tuple[list[str], dict[str, Any]]:
    """Build fixed same-node EXISTS predicates with bound values only."""
    validate_workflow_groups(groups)
    conditions: list[str] = []
    params: dict[str, Any] = {}
    operator_sql = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    for group_index, group in enumerate(groups):
        node_param = f"workflow_node_type_{group_index}"
        params[node_param] = group.node_type
        predicates: list[str] = []
        registry = WORKFLOW_REGISTRY_V1[group.node_type]
        for predicate_index, predicate in enumerate(group.predicates):
            definition = registry[predicate.property]
            prefix = f"workflow_{group_index}_{predicate_index}"
            params[f"{prefix}_property"] = predicate.property
            typed = _typed_value(predicate.value, definition)
            assert typed is not None
            if definition.value_type == "text":
                column = "value_text_folded"
                value = str(predicate.value).casefold()
                if predicate.op == "prefix":
                    value = f"{_escape_like(value)}%"
                elif predicate.op == "contains":
                    value = f"%{_escape_like(value)}%"
                comparison = "LIKE" if predicate.op in {"prefix", "contains"} else "="
                escape = " ESCAPE '\\'" if comparison == "LIKE" else ""
            elif definition.value_type == "integer":
                column, value, comparison, escape = (
                    "value_integer",
                    typed["value_integer"],
                    operator_sql[predicate.op],
                    "",
                )
            elif definition.value_type == "real":
                column, value, comparison, escape = "value_real", typed["value_real"], operator_sql[predicate.op], ""
            elif definition.value_type == "boolean":
                column, value, comparison, escape = "value_boolean", typed["value_boolean"], "=", ""
            else:
                column, value, comparison, escape = "value_text", typed["value_text"], "=", ""
            params[f"{prefix}_value"] = value
            params[f"{prefix}_type"] = definition.value_type
            predicates.append(
                "EXISTS (SELECT 1 FROM workflow_property_values AS workflow_value "
                "WHERE workflow_value.node_id = workflow_node.id "
                f"AND workflow_value.property_key = :{prefix}_property "
                f"AND workflow_value.value_type = :{prefix}_type "
                f"AND workflow_value.{column} {comparison} :{prefix}_value{escape})"
            )
        conditions.append(
            "EXISTS (SELECT 1 FROM workflow_nodes AS workflow_node "
            "WHERE workflow_node.asset_id = catalog_asset.id "
            f"AND workflow_node.node_type = :{node_param} AND " + " AND ".join(predicates) + ")"
        )
    return conditions, params
