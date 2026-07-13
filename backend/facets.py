"""Build metadata facet aggregations for indexed gallery images."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Query

from .errors import APIError, ErrorType
from .metadata_store import _DB_LOCK, _connect, initialize_database
from .metadata_store.identity import active_catalog_file_sql, current_file_metadata_sql
from .metadata_store.path_utils import named_path_scope_sql
from .models import APIErrorResponse, FacetResponse
from .scan import require_registered_path_allowed
from .search_scope import SearchScopeInput, resolve_search_scope

try:
    from prometheus_client import Histogram
except ImportError:
    Histogram = None

router = APIRouter()
LOGGER = logging.getLogger(__name__)

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
_CURRENT_METADATA_SQL = current_file_metadata_sql(fi_alias="fi", im_alias="m")
_ACTIVE_FILE_SQL = active_catalog_file_sql(fi_alias="fi")


def _build_facet_query(field: str, value_expr: str, max_values: int, scope_where: str, scope_params: dict) -> str:
    return f"""
        SELECT {value_expr} AS value, count(*) AS count
        FROM image_metadata m
        JOIN file_index fi ON fi.path = m.path
        WHERE {value_expr} != '' AND {_CURRENT_METADATA_SQL} {scope_where}
        GROUP BY {value_expr}
        ORDER BY count DESC, {value_expr} ASC
        LIMIT :limit
    """


def _build_scope(
    folder_path: str | None,
    *,
    scope: str = "all",
    library_id: int | None = None,
) -> tuple[str, dict]:
    if folder_path and scope == "all":
        scope = "folder"
    if scope == "library":
        return " AND fi.library_id = :scope_library_id", {"scope_library_id": library_id}
    if scope != "folder" or not folder_path:
        return "", {}
    try:
        scope_where, scope_params = named_path_scope_sql(folder_path, column="fi.path", leading_and=True)
        if library_id is not None:
            scope_where += " AND fi.library_id = :scope_library_id"
            scope_params["scope_library_id"] = library_id
        return scope_where, scope_params
    except OSError:
        return "", {}


def _validate_facet_scope(path: str) -> str | None:
    target, _library = require_registered_path_allowed(path)
    if target.exists() and not target.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")
    if not target.exists():
        return None
    return str(target)


def _get_folder_list(scope_where: str, scope_params: dict, max_folders: int) -> list[dict]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT fi.parent_path AS value, count(*) AS count
            FROM file_index fi
            WHERE fi.type IN ('image', 'photo') AND {_ACTIVE_FILE_SQL} {scope_where}
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
            WHERE m.width IS NOT NULL AND {_CURRENT_METADATA_SQL} {scope_where}
            GROUP BY value
            ORDER BY count DESC, value ASC
            LIMIT :limit
            """,
            {**scope_params, "limit": max_values},
        ).fetchall()
        return {
            "orientation": [
                {"value": r["value"], "count": int(r["count"])} for r in orientation_rows if r["value"] is not None
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
            WHERE m.seed IS NOT NULL AND m.seed != '' AND {_CURRENT_METADATA_SQL} {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        total = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index fi
            WHERE fi.type IN ('image', 'photo') AND {_ACTIVE_FILE_SQL} {scope_where}
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
            WHERE m.metadata_json IS NOT NULL AND {_CURRENT_METADATA_SQL} {scope_where}
            """,
            scope_params,
        ).fetchone()["total"]
        total = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index fi
            WHERE fi.type IN ('image', 'photo') AND {_ACTIVE_FILE_SQL} {scope_where}
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
                JOIN image_metadata m ON m.path = ir.path
                JOIN file_index fi ON fi.path = ir.path
                WHERE ir.kind = 'lora' AND ir.name != '' AND {_CURRENT_METADATA_SQL} {scope_where}
                GROUP BY ir.name
                ORDER BY count DESC, ir.name COLLATE NOCASE ASC
                LIMIT :max_values
                """,
                {**scope_params, "max_values": max_values},
            ).fetchall()
        ]


def build_facets(
    folder_path: str | None = None,
    max_values: int = FACET_DEFAULT_LIMIT,
    *,
    scope: str = "all",
    library_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate indexed metadata values into filter facets, optionally scoped to a folder."""
    import time

    start = time.perf_counter()
    scope_where, scope_params = _build_scope(folder_path, scope=scope, library_id=library_id)
    scope_params["limit"] = max_values
    result: dict[str, Any] = {}

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        for field, (value_expr, _) in FACET_FIELDS.items():
            rows = conn.execute(
                _build_facet_query(field, value_expr, max_values, scope_where, {**scope_params}),
                {**scope_params},
            ).fetchall()
            result[field] = [{"value": r["value"], "count": int(r["count"])} for r in rows]

    result["folders"] = _get_folder_list(scope_where, scope_params, max_values)

    size_facets = _get_image_size_facets(scope_where, scope_params, max_values)
    result.update(size_facets)

    result["seed_availability"] = _get_seed_availability(scope_where, scope_params)
    result["metadata_availability"] = _get_metadata_availability(scope_where, scope_params)

    result["lora"] = _get_lora_facet(scope_where, scope_params, max_values)

    duration = time.perf_counter() - start
    if _facets_query_duration is not None:
        with suppress(Exception):
            _facets_query_duration.observe(duration)

    return result


_FACET_ERROR_RESPONSES = {
    404: {"model": APIErrorResponse, "description": "Library or folder scope not found"},
    503: {"model": APIErrorResponse, "description": "Required facet index unavailable"},
    500: {"model": APIErrorResponse, "description": "Sanitized internal failure"},
}


@router.get("/api/facets", responses=_FACET_ERROR_RESPONSES)
def api_facets(
    scope: Annotated[
        SearchScopeInput,
        Query(description="Folder, library, or all-library facet scope; current is a legacy folder alias"),
    ] = "all",
    library_id: Annotated[int | None, Query(ge=1, description="Registered library for folder/library scope")] = None,
    path: Annotated[str | None, Query(description="Absolute registered folder path for folder scope")] = None,
    max_values: Annotated[int, Query(ge=1, le=200, description="Maximum facet values per field")] = FACET_DEFAULT_LIMIT,
) -> FacetResponse:
    """Return metadata facet counts for the requested folder scope."""
    effective_scope: SearchScopeInput = "current" if scope == "all" and path else scope
    context = resolve_search_scope(effective_scope, library_id=library_id, path=path)

    try:
        facets = build_facets(
            context.folder_path,
            max_values,
            scope=context.kind,
            library_id=context.library_id,
        )
    except sqlite3.OperationalError as exc:
        raise APIError(503, ErrorType.SERVER_ERROR, "Facet index temporarily unavailable") from exc
    except Exception as exc:
        LOGGER.exception("Facet build failed")
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    return FacetResponse.model_validate(facets)
