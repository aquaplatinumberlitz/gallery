"""Metadata resource extraction and persistence helpers."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any


def _iter_metadata_loras(metadata: Any) -> list[dict[str, Any]]:
    if not isinstance(metadata, dict):
        return []

    params = metadata.get("params")
    candidates: list[Any] = []
    for container in (metadata, params if isinstance(params, dict) else {}):
        for key in ("loras", "Loras", "lora", "Lora", "LoRA"):
            value = container.get(key)
            if value:
                candidates.append(value)

    loras: list[dict[str, Any]] = []
    for candidate in candidates:
        items = candidate if isinstance(candidate, list) else [candidate]
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("model") or item.get("resource_name") or item.get("alias")
                loras.append(
                    {
                        "name": name or "",
                        "hash": item.get("hash") or item.get("model_hash") or item.get("resource_hash"),
                        "resource_hash": item.get("resource_hash") or item.get("hash"),
                        "weight": item.get("weight") or item.get("strength"),
                        "strength": item.get("strength") or item.get("weight"),
                    }
                )
            elif isinstance(item, str) and item.strip():
                loras.append(
                    {"name": item.strip(), "hash": None, "resource_hash": None, "weight": None, "strength": None}
                )

    return loras


def _clean_resource_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_resource_kind(value: Any) -> str:
    kind = _clean_resource_text(value).lower()
    if "lora" in kind:
        return "lora"
    if kind:
        return kind[:64]
    return "resource"


def _resource_raw_json(item: Any) -> str:
    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True) if item is not None else ""
    except (TypeError, ValueError):
        return str(item)


def _iter_metadata_resources(metadata: Any) -> list[dict[str, Any]]:
    if not isinstance(metadata, dict):
        return []

    resources: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_resource(kind: str, item: dict[str, Any]) -> None:
        name = _clean_resource_text(
            item.get("name") or item.get("model") or item.get("resource_name") or item.get("alias")
        )
        resource_hash = _clean_resource_text(item.get("resource_hash") or item.get("hash") or item.get("model_hash"))
        hash_value = _clean_resource_text(item.get("hash") or item.get("model_hash") or item.get("resource_hash"))
        normalized_kind = _normalize_resource_kind(kind)
        key = (normalized_kind, name.lower(), resource_hash.lower(), hash_value.lower())
        if (not name and not resource_hash and not hash_value) or key in seen:
            return
        seen.add(key)
        resources.append(
            {
                "kind": normalized_kind,
                "name": name,
                "hash": hash_value,
                "resource_hash": resource_hash,
                "weight": _clean_resource_text(item.get("weight") or item.get("strength")),
                "strength": _clean_resource_text(item.get("strength") or item.get("weight")),
                "raw_json": _resource_raw_json(item),
            }
        )

    for item in _iter_metadata_loras(metadata):
        add_resource("lora", item)

    for key in ("resources", "Resources"):
        value = metadata.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            kind = (
                item.get("type")
                or item.get("kind")
                or item.get("resource_type")
                or item.get("resourceType")
                or "resource"
            )
            add_resource(str(kind), item)

    return resources


def _split_lora_text(lora_text: str | None) -> list[str]:
    if not lora_text:
        return []
    parts = re.split(r"[\n,;]+", lora_text)
    return [part.strip() for part in parts if part.strip()]


def _resource_rows_from_metadata(
    metadata_json: str | None, lora_text: str | None, updated_at: float
) -> list[dict[str, Any]]:
    from . import _safe_json_loads

    resources = _iter_metadata_resources(_safe_json_loads(metadata_json))
    seen = {
        (
            item["kind"],
            item["name"].lower(),
            (item["resource_hash"] or "").lower(),
            (item["hash"] or "").lower(),
        )
        for item in resources
    }

    for text_item in _split_lora_text(lora_text):
        name = text_item.split(":", 1)[0].strip() if ":" in text_item else text_item.strip()
        if not name:
            continue
        key = ("lora", name.lower(), "", "")
        if key in seen:
            continue
        seen.add(key)
        resources.append(
            {
                "kind": "lora",
                "name": name,
                "hash": "",
                "resource_hash": "",
                "weight": text_item.split(":", 1)[1].strip() if ":" in text_item else "",
                "strength": text_item.split(":", 1)[1].strip() if ":" in text_item else "",
                "raw_json": "",
            }
        )

    for item in resources:
        item["updated_at"] = updated_at
    return resources


def _replace_image_resources_conn(
    conn: sqlite3.Connection,
    path: str,
    metadata_json: str | None,
    lora_text: str | None,
    updated_at: float,
) -> None:
    conn.execute("DELETE FROM image_resources WHERE path = ?", (path,))
    rows = _resource_rows_from_metadata(metadata_json, lora_text, updated_at)
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO image_resources (
          path, kind, name, hash, resource_hash, weight, strength, raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                path,
                item["kind"],
                item["name"],
                item["hash"],
                item["resource_hash"],
                item["weight"],
                item["strength"],
                item["raw_json"],
                item["updated_at"],
            )
            for item in rows
        ),
    )


def _backfill_image_resources_conn(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT count(*) AS total FROM image_resources").fetchone()
    if existing and int(existing["total"] or 0) > 0:
        return
    rows = conn.execute(
        """
        SELECT path, metadata_json, lora_text, COALESCE(updated_at, indexed_at, mtime, 0) AS updated_at
        FROM image_metadata
        WHERE (metadata_json IS NOT NULL AND metadata_json != '')
           OR (lora_text IS NOT NULL AND lora_text != '')
        """
    ).fetchall()
    for row in rows:
        _replace_image_resources_conn(
            conn,
            row["path"],
            row["metadata_json"],
            row["lora_text"],
            float(row["updated_at"] or time.time()),
        )


def _lora_summary(row: sqlite3.Row) -> tuple[bool, int, str]:
    from . import _truncate_preview

    count = int(row["lora_count"] or 0)
    preview = row["lora_preview"] or ""
    return count > 0, count, _truncate_preview(preview, 120)
