"""Library inspector listing and metadata detail helpers."""

from __future__ import annotations

import base64
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from ._db import _DB_LOCK, _connect
from ._resources import _iter_metadata_loras, _lora_summary, _split_lora_text
from ._schema import initialize_database
from .identity import current_file_metadata_sql
from .search_store import _build_scope_named, _folder_relative_path

_CURRENT_METADATA_SQL = current_file_metadata_sql(fi_alias="fi", im_alias="m")
_INSPECTOR_MTIME_SQL = "COALESCE(m.mtime_ns, CAST(m.mtime * 1000000000 AS INTEGER))"
_PRESELECT_ACTIVE_ASSET_SQL = """
JOIN assets AS catalog_asset
  ON catalog_asset.library_id = fi.library_id
 AND catalog_asset.path = fi.path
 AND catalog_asset.parent_path = fi.parent_path
 AND catalog_asset.offline = 0
 AND catalog_asset.deleted_at IS NULL
 AND catalog_asset.mtime_ns IS NOT NULL
 AND ((fi.mtime_ns IS NOT NULL AND catalog_asset.mtime_ns = fi.mtime_ns)
      OR (fi.mtime_ns IS NULL AND ABS(catalog_asset.mtime_ns / 1000000000.0 - fi.mtime) < 0.001))
 AND (catalog_asset.size = fi.size OR (catalog_asset.size IS NULL AND fi.size IS NULL))
"""


def _truncate_preview(text: str | None, limit: int = 140) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _format_inspector_row(row: sqlite3.Row, root: Path) -> dict[str, Any]:
    has_lora, lora_count, lora_preview = _lora_summary(row)
    parent_path = row["parent_path"] or str(Path(row["path"]).parent)
    row_keys = set(row.keys())
    width = row["indexed_width"] if "indexed_width" in row_keys else row["width"]
    height = row["indexed_height"] if "indexed_height" in row_keys else row["height"]
    return {
        "path": row["path"],
        "name": row["name"],
        "folder": parent_path,
        "relative_path": _folder_relative_path(parent_path, root),
        "mtime": row["mtime"],
        "width": width,
        "height": height,
        "model": row["model"] or "",
        "tool": row["tool"] or "",
        "sampler": row["sampler"] or "",
        "seed": row["seed"] or "",
        "prompt_preview": _truncate_preview(row["prompt_preview"], 140),
        "has_prompt": bool(row["has_prompt"]),
        "has_negative": bool(row["has_negative"]),
        "has_lora": has_lora,
        "lora_count": lora_count,
        "lora_preview": lora_preview,
        "metadata_detail_available": bool(
            row["has_metadata_json"] or row["has_prompt"] or row["has_negative"] or row["lora_count"]
        ),
    }


def _encode_inspector_cursor(values: dict[str, Any] | sqlite3.Row) -> str:
    keys = set(values.keys())
    mtime_ns = values["mtime_ns"] if "mtime_ns" in keys else round(float(values["mtime"]) * 1_000_000_000)
    cursor_data = {
        "mtime": values["mtime"],
        "mtime_ns": int(mtime_ns),
        "name": values["name"],
        "path": values["path"],
    }
    return base64.urlsafe_b64encode(json.dumps(cursor_data).encode()).decode()


def _build_library_inspector_keyset_where(sort: str, cursor_str: str | None) -> tuple[str, dict[str, Any]]:
    """Return SQL conditions and params for Library Inspector keyset pagination."""
    if not cursor_str:
        return "", {}

    if re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", cursor_str) is None:
        raise ValueError("Invalid pagination cursor")
    try:
        cursor = json.loads(base64.b64decode(cursor_str.encode(), altchars=b"-_", validate=True))
        if not isinstance(cursor, dict):
            raise ValueError
        cursor_mtime = cursor.get("mtime")
        cursor_mtime_ns = cursor.get("mtime_ns")
        cursor_name = cursor["name"]
        cursor_path = cursor["path"]
    except Exception as exc:
        raise ValueError("Invalid pagination cursor") from exc
    if not isinstance(cursor_name, str) or not isinstance(cursor_path, str):
        raise ValueError("Invalid pagination cursor")
    if cursor_mtime_ns is None:
        if (
            not isinstance(cursor_mtime, int | float)
            or isinstance(cursor_mtime, bool)
            or not math.isfinite(cursor_mtime)
        ):
            raise ValueError("Invalid pagination cursor")
        cursor_mtime_ns = round(float(cursor_mtime) * 1_000_000_000)
    if (
        not isinstance(cursor_mtime_ns, int)
        or isinstance(cursor_mtime_ns, bool)
        or not -(2**63) <= cursor_mtime_ns <= 2**63 - 1
    ):
        raise ValueError("Invalid pagination cursor")

    mtime_expr = _INSPECTOR_MTIME_SQL
    params: dict[str, Any] = {
        "ks_mtime": cursor_mtime_ns,
        "ks_name": cursor_name,
        "ks_path": cursor_path,
    }

    if sort == "date_desc":
        cond = f"""
            ({mtime_expr} < :ks_mtime) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL = :ks_name AND m.path > :ks_path)
        """
    elif sort == "date_asc":
        cond = f"""
            ({mtime_expr} > :ks_mtime) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL = :ks_name AND m.path > :ks_path)
        """
    elif sort == "name_asc":
        cond = f"""
            (m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} < :ks_mtime) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} = :ks_mtime AND m.path > :ks_path)
        """
    elif sort == "name_desc":
        cond = f"""
            (m.name COLLATE GALLERY_NATURAL < :ks_name) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} < :ks_mtime) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} = :ks_mtime AND m.path > :ks_path)
        """
    else:
        return "", {}

    return f"({cond})", params


def list_library_inspector_rows(
    query: str = "",
    scope: str = "current",
    root_path: str | Path | None = None,
    limit: int = 200,
    sort: str = "date_desc",
    cursor: str | None = None,
    model_filter: str | None = None,
    prompt_filter: str = "all",
) -> dict[str, Any]:
    """Return bounded DB/index-backed rows for the read-only Library Inspector."""
    from ..fielded_search_parser import build_fielded_conditions, parse_fielded_query

    initialize_database()
    trimmed = query.strip()
    normalized_scope = "current" if scope == "current" else "all"
    bounded_limit = max(1, min(limit, 1000))
    normalized_sort = sort if sort in {"name_asc", "name_desc", "date_asc", "date_desc"} else "date_desc"
    order_sql = {
        "name_asc": f"m.name COLLATE GALLERY_NATURAL ASC, {_INSPECTOR_MTIME_SQL} DESC, m.path ASC",
        "name_desc": f"m.name COLLATE GALLERY_NATURAL DESC, {_INSPECTOR_MTIME_SQL} DESC, m.path ASC",
        "date_asc": f"{_INSPECTOR_MTIME_SQL} ASC, m.name COLLATE GALLERY_NATURAL ASC, m.path ASC",
        "date_desc": f"{_INSPECTOR_MTIME_SQL} DESC, m.name COLLATE GALLERY_NATURAL ASC, m.path ASC",
    }[normalized_sort]
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    if normalized_scope == "current" and root is None:
        return {
            "root": "",
            "scope": normalized_scope,
            "query": query,
            "limit": bounded_limit,
            "generated_at": time.time(),
            "total_indexed": 0,
            "returned": 0,
            "truncated": False,
            "next_cursor": None,
            "has_more": False,
            "sort": normalized_sort,
            "rows": [],
        }
    display_root = root if root is not None else Path(os.sep)
    scope_cond, scope_params = _build_scope_named(normalized_scope, root, "fi")

    with _DB_LOCK, _connect() as conn:
        parsed = parse_fielded_query(trimmed)
        field_conditions: list[str] = []
        field_params: dict[str, Any] = {}
        if trimmed:
            field_conditions, field_params = build_fielded_conditions(parsed)
        keyset_condition, keyset_params = _build_library_inspector_keyset_where(normalized_sort, cursor)

        where_parts = ["fi.type IN ('image', 'photo')", _CURRENT_METADATA_SQL]
        if field_conditions:
            where_parts.extend(field_conditions)
        normalized_model_filter = (model_filter or "").strip()
        if normalized_model_filter:
            where_parts.append("COALESCE(NULLIF(m.model, ''), NULLIF(m.tool, ''), '') = :model_filter")
            field_params["model_filter"] = normalized_model_filter
        if prompt_filter == "has_prompt":
            where_parts.append("m.prompt IS NOT NULL AND m.prompt != ''")
        elif prompt_filter == "no_prompt":
            where_parts.append("(m.prompt IS NULL OR m.prompt = '')")
        if keyset_condition:
            where_parts.append(keyset_condition)
        where_sql = " AND ".join(where_parts)

        params: dict[str, Any] = dict(scope_params)
        params.update(field_params)
        params.update(keyset_params)
        params["limit"] = bounded_limit + 1
        params["candidate_limit"] = bounded_limit + 8
        params["candidate_offset"] = bounded_limit + 7

        use_date_index_preselection = (
            normalized_scope == "all"
            and normalized_sort in {"date_asc", "date_desc"}
            and not trimmed
            and not cursor
            and not normalized_model_filter
            and prompt_filter == "all"
        )
        metadata_source_sql = (
            "image_metadata m INDEXED BY idx_image_metadata_inspector_date"
            if use_date_index_preselection
            else "image_metadata m"
        )
        file_index_join_sql = (
            "CROSS JOIN file_index fi ON fi.path = m.path"
            if use_date_index_preselection
            else "JOIN file_index fi ON fi.path = m.path"
        )
        date_cutoff_cte_sql = ""
        date_cutoff_condition = ""
        if use_date_index_preselection:
            cutoff_mtime_sql = _INSPECTOR_MTIME_SQL.replace("m.", "cutoff_m.")
            direction = "ASC" if normalized_sort == "date_asc" else "DESC"
            comparison = "<=" if normalized_sort == "date_asc" else ">="
            fallback = "9223372036854775807" if normalized_sort == "date_asc" else "-9223372036854775808"
            date_cutoff_cte_sql = f"""
                date_cutoff AS MATERIALIZED (
                  SELECT {cutoff_mtime_sql} AS cutoff_mtime
                  FROM image_metadata cutoff_m INDEXED BY idx_image_metadata_inspector_date
                  ORDER BY {cutoff_mtime_sql} {direction}
                  LIMIT 1 OFFSET :candidate_offset
                ),
            """
            date_cutoff_condition = (
                f" AND {_INSPECTOR_MTIME_SQL} {comparison} COALESCE((SELECT cutoff_mtime FROM date_cutoff), {fallback})"
            )

        fetched_rows = list(
            conn.execute(
                f"""
                WITH {date_cutoff_cte_sql} bounded_rows AS MATERIALIZED (
                  SELECT m.id AS metadata_id
                  FROM {metadata_source_sql}
                  {file_index_join_sql}
                  {_PRESELECT_ACTIVE_ASSET_SQL}
                  WHERE {where_sql.replace(_CURRENT_METADATA_SQL, "1 = 1")}
                  {date_cutoff_condition}
                  {scope_cond}
                  ORDER BY {order_sql}
                  LIMIT :candidate_limit
                )
                SELECT
                  m.path,
                  m.name,
                  COALESCE(m.mtime, fi.mtime) AS mtime,
                  {_INSPECTOR_MTIME_SQL} AS mtime_ns,
                  m.width,
                  m.height,
                  m.model,
                  m.tool,
                  m.sampler,
                  m.seed,
                  substr(COALESCE(m.prompt, ''), 1, 141) AS prompt_preview,
                  CASE WHEN m.prompt IS NOT NULL AND m.prompt != '' THEN 1 ELSE 0 END AS has_prompt,
                  CASE WHEN m.negative_prompt IS NOT NULL AND m.negative_prompt != '' THEN 1 ELSE 0 END AS has_negative,
                  CASE WHEN m.metadata_json IS NOT NULL AND m.metadata_json != '' THEN 1 ELSE 0 END AS has_metadata_json,
                  COALESCE(lr.lora_count, 0) AS lora_count,
                  COALESCE(lr.lora_preview, '') AS lora_preview,
                  fi.parent_path,
                  fi.type AS file_type,
                  COALESCE(fi.width, m.width) AS indexed_width,
                  COALESCE(fi.height, m.height) AS indexed_height
                FROM bounded_rows bounded
                CROSS JOIN image_metadata m ON m.id = bounded.metadata_id
                CROSS JOIN file_index fi ON fi.path = m.path
                LEFT JOIN (
                  SELECT path, count(*) AS lora_count, group_concat(name, ', ') AS lora_preview
                  FROM image_resources
                  WHERE kind = 'lora' AND path IN (
                    SELECT bounded_metadata.path
                    FROM bounded_rows bounded_resource
                    JOIN image_metadata bounded_metadata ON bounded_metadata.id = bounded_resource.metadata_id
                  )
                  GROUP BY path
                ) lr ON lr.path = m.path
                WHERE fi.type IN ('image', 'photo') AND {_CURRENT_METADATA_SQL}
                ORDER BY {order_sql}
                LIMIT :limit
                """,
                params,
            )
        )
        rows = fetched_rows[:bounded_limit]
        next_cursor = _encode_inspector_cursor(rows[-1]) if len(fetched_rows) > bounded_limit and rows else None

        count_scope_cond, count_scope_params = _build_scope_named(normalized_scope, root, "m")
        total_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            WHERE 1 = 1
            {count_scope_cond}
            """,
            count_scope_params,
        ).fetchone()

    return {
        "root": str(display_root),
        "scope": normalized_scope,
        "query": query,
        "limit": bounded_limit,
        "generated_at": time.time(),
        "total_indexed": int(total_row["total"] if total_row else 0),
        "returned": len(rows),
        "truncated": len(fetched_rows) > bounded_limit,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "sort": normalized_sort,
        "rows": _dedupe_inspector_rows(rows, display_root),
    }


def _dedupe_inspector_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        results.append(_format_inspector_row(row, root))
    return results


def get_library_inspector_metadata(path: str | Path) -> dict[str, Any] | None:
    """Read full inspector metadata from indexed DB rows only."""
    resolved = str(Path(path).resolve())
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            f"""
            SELECT
              m.*,
              fi.parent_path,
              fi.type AS file_type,
              COALESCE(fi.width, m.width) AS indexed_width,
              COALESCE(fi.height, m.height) AS indexed_height
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE m.path = ? AND fi.type IN ('image', 'photo')
              AND {_CURRENT_METADATA_SQL}
            """,
            (resolved,),
        ).fetchone()
        if row is None:
            return None

    metadata = _safe_json_loads(row["metadata_json"])
    loras = _iter_metadata_loras(metadata)
    if not loras:
        loras = [
            {"name": name, "hash": None, "resource_hash": None, "weight": None, "strength": None}
            for name in _split_lora_text(row["lora_text"])
        ]

    resources: list[dict[str, Any]] = []
    if isinstance(metadata, dict):
        for key in ("resources", "Resources"):
            value = metadata.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        resources.append(
                            {
                                "name": item.get("name") or item.get("resource_name") or "",
                                "hash": item.get("hash"),
                                "resource_hash": item.get("resource_hash") or item.get("hash"),
                                "weight": item.get("weight") or item.get("strength"),
                                "strength": item.get("strength") or item.get("weight"),
                            }
                        )

    public_metadata = (
        {key: value for key, value in metadata.items() if not str(key).startswith("_")}
        if isinstance(metadata, dict)
        else metadata
    )

    return {
        "path": row["path"],
        "prompt": row["prompt"] or "",
        "negative_prompt": row["negative_prompt"] or "",
        "raw_metadata": public_metadata,
        "model": row["model"] or "",
        "tool": row["tool"] or "",
        "sampler": row["sampler"] or "",
        "seed": row["seed"] or "",
        "width": row["indexed_width"],
        "height": row["indexed_height"],
        "mtime": row["mtime"],
        "loras": loras,
        "resources": resources,
        "metadata_detail_available": bool(metadata or row["prompt"] or row["negative_prompt"] or loras or resources),
    }
