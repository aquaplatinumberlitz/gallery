from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .errors import APIError, ErrorType
from .metadata_store import _connect, initialize_database, _DB_LOCK
from .paths import is_path_safe, resolve_path

try:
    from prometheus_client import Histogram
except ImportError:
    Histogram = None

router = APIRouter()

FACET_FIELDS = {
    "tool": ("COALESCE(m.tool, '')", 50),
    "model": ("COALESCE(m.model, '')", 100),
    "sampler": ("COALESCE(m.sampler, '')", 50),
    "scheduler": ("COALESCE(m.scheduler, '')", 50),
}

if Histogram is not None:
    try:
        _facets_query_duration = Histogram(
            "gallery_facets_query_duration_seconds",
            "Time spent building facet aggregations",
        )
    except Exception:  # noqa: BLE001
        _facets_query_duration = None
else:
    _facets_query_duration = None

FACET_DEFAULT_LIMIT = 50


def _build_facet_query(field: str, value_expr: str, max_values: int, scope_where: str, scope_params: dict) -> str:
    return f"""
        SELECT {value_expr} AS value, count(*) AS count
        FROM image_metadata m
        JOIN file_index fi ON fi.path = m.path
        WHERE {value_expr} != '' {scope_where}
        GROUP BY {value_expr}
        ORDER BY count DESC, {value_expr} ASC
        LIMIT :limit
    """


def _build_scope(folder_path: str | None) -> tuple[str, dict]:
    if not folder_path:
        return "", {}
    try:
        resolved = str(Path(folder_path).resolve())
        prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
        return "AND (fi.path = :scope_root OR fi.path LIKE :scope_prefix ESCAPE '\\')", {
            "scope_root": resolved,
            "scope_prefix": f"{prefix}%",
        }
    except OSError:
        return "", {}


def _get_folder_list(scope_where: str, scope_params: dict, max_folders: int) -> list[dict]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT fi.parent_path AS value, count(*) AS count
            FROM file_index fi
            WHERE fi.type = 'photo' {scope_where}
            GROUP BY fi.parent_path
            ORDER BY count DESC, fi.parent_path ASC
            LIMIT :limit
            """,
            {**scope_params, "limit": max_folders},
        ).fetchall()
        return [{"value": r["value"], "count": int(r["count"])} for r in rows]


def _get_image_size_facets(scope_where: str, scope_params: dict, max_values: int) -> dict:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        orientation_rows = conn.execute(
            f"""
            SELECT
                CASE
                    WHEN m.width IS NOT NULL AND m.height IS NOT NULL
                        THEN CASE
                            WHEN m.width > m.height THEN 'landscape'
                            WHEN m.width < m.height THEN 'portrait'
                            ELSE 'square'
                        END
                    ELSE NULL
                END AS value,
                count(*) AS count
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE m.width IS NOT NULL {scope_where}
            GROUP BY value
            ORDER BY count DESC, value ASC
            LIMIT :limit
            """,
            {**scope_params, "limit": max_values},
        ).fetchall()
        return {
            "orientation": [
                {"value": r["value"], "count": int(r["count"])}
                for r in orientation_rows
                if r["value"] is not None
            ],
        }


def _get_seed_availability(scope_where: str, scope_params: dict) -> list[dict]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        has_seed = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE m.seed IS NOT NULL AND m.seed != '' {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        total = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index fi
            WHERE fi.type = 'photo' {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        return [
            {"value": "available", "count": int(has_seed)},
            {"value": "missing", "count": max(0, int(total) - int(has_seed))},
        ]


def _get_metadata_availability(scope_where: str, scope_params: dict) -> list[dict]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        has_metadata = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE m.metadata_json IS NOT NULL {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        total = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index fi
            WHERE fi.type = 'photo' {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        return [
            {"value": "available", "count": int(has_metadata)},
            {"value": "missing", "count": max(0, int(total) - int(has_metadata))},
        ]


def _get_lora_facet(scope_where: str, scope_params: dict, max_values: int) -> list[dict]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        return [
            {"value": row["name"], "count": int(row["count"])}
            for row in conn.execute(
                f"""
                SELECT ir.name, count(DISTINCT ir.path) AS count
                FROM image_resources ir
                JOIN file_index fi ON fi.path = ir.path
                WHERE ir.kind = 'lora' AND ir.name != '' {scope_where}
                GROUP BY ir.name
                ORDER BY count DESC, ir.name COLLATE NOCASE ASC
                LIMIT :max_values
                """,
                {**scope_params, "max_values": max_values},
            ).fetchall()
        ]


def build_facets(folder_path: str | None = None, max_values: int = FACET_DEFAULT_LIMIT) -> dict[str, Any]:
    import time
    start = time.perf_counter()
    scope_where, scope_params = _build_scope(folder_path)
    scope_params["limit"] = max_values
    result: dict[str, Any] = {}

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        for field, (value_expr, _) in FACET_FIELDS.items():
            rows = conn.execute(
                _build_facet_query(field, value_expr, max_values, scope_where, {**scope_params}),
                {**scope_params},
            ).fetchall()
            result[field] = [
                {"value": r["value"], "count": int(r["count"])}
                for r in rows
            ]

    result["folders"] = _get_folder_list(scope_where, scope_params, max_values)

    size_facets = _get_image_size_facets(scope_where, scope_params, max_values)
    result.update(size_facets)

    result["seed_availability"] = _get_seed_availability(scope_where, scope_params)
    result["metadata_availability"] = _get_metadata_availability(scope_where, scope_params)

    result["lora"] = _get_lora_facet(scope_where, scope_params, max_values)

    duration = time.perf_counter() - start
    if _facets_query_duration is not None:
        try:
            _facets_query_duration.observe(duration)
        except Exception:  # noqa: BLE001
            pass

    return result


@router.get("/api/facets")
async def api_facets(
    path: str | None = Query(None, description="Scope facets to this folder and its children"),
    max_values: int = Query(FACET_DEFAULT_LIMIT, ge=1, le=200, description="Maximum facet values per field"),
):
    folder_path = None
    if path:
        target = resolve_path(path)
        if not is_path_safe(target):
            raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
        if target.exists() and not target.is_dir():
            raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")
        if not target.exists():
            return {}
        folder_path = str(target)

    try:
        facets = await run_in_threadpool(build_facets, folder_path, max_values)
    except Exception as exc:
        raise APIError(500, ErrorType.SERVER_ERROR, f"Facet build failed: {exc}") from exc

    return facets
