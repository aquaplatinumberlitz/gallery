"""Metadata and file index search helpers."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from ..metadata_extract import contains_cjk
from ._db import _DB_LOCK, _connect
from ._schema import initialize_database


def _metadata_store_build_album_metadata(path: Path) -> dict[str, Any]:
    from . import build_album_metadata

    return build_album_metadata(path)


SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
MIN_PLAIN_SEARCH_QUERY_LENGTH = 2


def _escape_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _unicode_match_query(query: str) -> str:
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _trigram_match_query(query: str) -> str:
    return _escape_fts_token(query.strip())


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _folder_relative_path(parent_path: str, root: Path) -> str:
    try:
        relative = Path(parent_path).resolve().relative_to(root)
    except (OSError, ValueError):
        return ""
    if str(relative) == ".":
        return ""
    return str(relative)


def _is_inside_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        return resolved == resolved_root or resolved_root in resolved.parents
    except (OSError, RuntimeError):
        return False


def _path_prefix(root: Path) -> tuple[str, str]:
    root_str = str(root.resolve())
    root_prefix = f"{root_str.rstrip(os.sep)}{os.sep}"
    return root_str, f"{_like_escape(root_prefix)}%"


def _scope_clause(scope: str, root_path: str | Path | None, alias: str = "fi") -> tuple[str, list[Any], Path]:
    root = Path(root_path).resolve() if scope == "current" and root_path else None
    if root is None:
        return "", [], Path(os.sep)
    root_str, root_prefix = _path_prefix(root)
    return f" AND ({alias}.path = ? OR {alias}.path LIKE ? ESCAPE '\\')", [root_str, root_prefix], root


def _format_file_index_rows(rows: list[sqlite3.Row], root: Path, match_type: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        result = {
            "name": row["name"],
            "path": row["path"],
            "type": row["type"],
            "parent_path": row["parent_path"],
            "relative_path": _folder_relative_path(row["parent_path"], root),
            "mtime": row["mtime"],
            "width": row["width"],
            "height": row["height"],
            "duration_ms": _optional_row_value(row, "duration_ms"),
            "mime_type": _optional_row_value(row, "mime_type"),
        }
        if row["type"] == "folder":
            resolved_path = Path(row["path"]).resolve()
            if resolved_path.exists() and resolved_path.is_dir():
                meta = _metadata_store_build_album_metadata(resolved_path)
                result["cover_images"] = meta["cover_images"]
                result["image_count"] = meta["image_count"]
            else:
                result["cover_images"] = []
                result["image_count"] = 0
        result.update(
            {
                "match_type": match_type,
                "prompt_snippet": "",
                "model": "",
                "sampler": "",
                "seed": "",
            }
        )
        results.append(result)
    return results


def _optional_row_value(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except IndexError:
        return None


def _search_file_index_fts(
    conn: sqlite3.Connection,
    query: str,
    file_type: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    scope_sql, scope_params, root = _scope_clause(scope, root_path, "fi")
    type_sql = "fi.type IN ('image', 'photo')" if file_type in {"image", "photo"} else "fi.type = ?"
    type_params = [] if file_type in {"image", "photo"} else [file_type]
    try:
        match_query = _unicode_match_query(query)
        rows = list(
            conn.execute(
                f"""
                SELECT fi.*,
                       (SELECT a.duration_ms FROM assets a
                        WHERE a.path = fi.path AND a.duration_ms IS NOT NULL
                        LIMIT 1) AS duration_ms,
                       (SELECT a.mime_type FROM assets a
                        WHERE a.path = fi.path AND a.mime_type IS NOT NULL
                        LIMIT 1) AS mime_type
                FROM file_index_fts fts
                JOIN file_index fi ON fi.path = fts.path
                WHERE fts MATCH ? AND {type_sql} {scope_sql}
                ORDER BY bm25(file_index_fts) ASC, fi.mtime DESC, fi.name ASC
                LIMIT ?
                """,
                [match_query, *type_params, *scope_params, limit],
            )
        )
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(query)
    rows = list(
        conn.execute(
            f"""
            SELECT fi.*,
                   (SELECT a.duration_ms FROM assets a
                    WHERE a.path = fi.path AND a.duration_ms IS NOT NULL
                    LIMIT 1) AS duration_ms,
                   (SELECT a.mime_type FROM assets a
                    WHERE a.path = fi.path AND a.mime_type IS NOT NULL
                    LIMIT 1) AS mime_type
            FROM file_index fi
            WHERE fi.name LIKE ? ESCAPE '\\' AND {type_sql} {scope_sql}
            ORDER BY fi.mtime DESC, fi.name ASC
            LIMIT ?
            """,
            [pattern, *type_params, *scope_params, limit],
        )
    )
    return rows, root


def _search_prompt_rows(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    scope_sql, scope_params, root = _scope_clause(scope, root_path, "fi")
    rows: list[sqlite3.Row] = []
    try:
        if contains_cjk(query) and len(query) >= 3:
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts_trigram) AS rank
                    FROM image_metadata_fts_trigram fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts_trigram MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_trigram_match_query(query), *scope_params, limit],
                )
            )
        elif not contains_cjk(query):
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts) AS rank
                    FROM image_metadata_fts fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_unicode_match_query(query), *scope_params, limit],
                )
            )
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(query)
    where = " OR ".join(f"m.{field} LIKE ? ESCAPE '\\'" for field in PROMPT_SEARCH_FIELDS)
    rows = list(
        conn.execute(
            f"""
            SELECT m.*, fi.parent_path, fi.type AS file_type
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE ({where}) {scope_sql}
            ORDER BY m.mtime DESC, m.name ASC
            LIMIT ?
            """,
            [*([pattern] * len(PROMPT_SEARCH_FIELDS)), *scope_params, limit],
        )
    )
    return rows, root


def _format_prompt_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        results.append(
            {
                "name": row["name"],
                "path": row["path"],
                "type": "photo",
                "parent_path": row["parent_path"],
                "relative_path": _folder_relative_path(row["parent_path"], root),
                "mtime": row["mtime"],
                "width": row["width"],
                "height": row["height"],
                "match_type": "prompt",
                "prompt_snippet": _snippet(row),
                "model": row["model"] or "",
                "sampler": row["sampler"] or "",
                "seed": row["seed"] or "",
            }
        )
    return results


def _snippet(row: sqlite3.Row) -> str:
    for field in ("prompt", "negative_prompt", "raw_metadata_text", "model", "sampler", "name"):
        text = row[field] or ""
        if text:
            text = " ".join(text.split())
            return text[:240]
    return ""


def _format_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [
        {
            "name": row["name"],
            "path": row["path"],
            "type": "file",
            "mtime": row["mtime"],
            "width": row["width"],
            "height": row["height"],
            "model": row["model"] or "",
            "sampler": row["sampler"] or "",
            "seed": row["seed"] or "",
            "prompt_snippet": _snippet(row),
        }
        for row in rows
    ]


def _search_fts(
    conn: sqlite3.Connection, table: str, bm25_table: str, match_query: str, limit: int, offset: int
) -> list[sqlite3.Row]:
    sql = f"""
        SELECT m.*, bm25({bm25_table}) AS rank
        FROM {table}
        JOIN image_metadata m ON m.id = {table}.rowid
        WHERE {table} MATCH ?
        ORDER BY rank ASC, m.mtime DESC, m.name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (match_query, limit, offset)))


def _count_fts(conn: sqlite3.Connection, table: str, match_query: str) -> int:
    row = conn.execute(f"SELECT count(*) AS total FROM {table} WHERE {table} MATCH ?", (match_query,)).fetchone()
    return int(row["total"] if row else 0)


def _search_like(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[sqlite3.Row]:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    sql = f"""
        SELECT *
        FROM image_metadata
        WHERE {where}
        ORDER BY mtime DESC, name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (*([pattern] * len(SEARCH_FIELDS)), limit, offset)))


def _count_like(conn: sqlite3.Connection, query: str) -> int:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    row = conn.execute(
        f"SELECT count(*) AS total FROM image_metadata WHERE {where}", [pattern] * len(SEARCH_FIELDS)
    ).fetchone()
    return int(row["total"] if row else 0)


def search_metadata(query: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Search extracted metadata text with FTS and LIKE fallbacks."""
    initialize_database()
    trimmed = query.strip()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if not trimmed:
        return {"query": query, "total": 0, "results": []}

    with _DB_LOCK, _connect() as conn:
        rows: list[sqlite3.Row] = []
        total = 0
        try:
            if contains_cjk(trimmed):
                if len(trimmed) >= 3:
                    match_query = _trigram_match_query(trimmed)
                    rows = _search_fts(
                        conn, "image_metadata_fts_trigram", "image_metadata_fts_trigram", match_query, limit, offset
                    )
                    total = _count_fts(conn, "image_metadata_fts_trigram", match_query)
                if not rows:
                    rows = _search_like(conn, trimmed, limit, offset)
                    total = _count_like(conn, trimmed)
            else:
                match_query = _unicode_match_query(trimmed)
                rows = _search_fts(conn, "image_metadata_fts", "image_metadata_fts", match_query, limit, offset)
                total = _count_fts(conn, "image_metadata_fts", match_query)
        except sqlite3.OperationalError:
            rows = _search_like(conn, trimmed, limit, offset)
            total = _count_like(conn, trimmed)

        if not rows and not contains_cjk(trimmed):
            rows = _search_like(conn, trimmed, limit, offset)
            total = _count_like(conn, trimmed)

        return {
            "query": query,
            "total": total,
            "results": _format_rows(rows),
        }


def search_index(query: str, scope: str, root_path: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    """Search indexed albums, photos, and prompts using free-text query semantics."""
    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed or len(trimmed) < MIN_PLAIN_SEARCH_QUERY_LENGTH:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(display_root),
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    if normalized_scope == "current" and root is None:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": "",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    with _DB_LOCK, _connect() as conn:
        album_rows, root = _search_file_index_fts(conn, trimmed, "folder", normalized_scope, root_path, limit)
        photo_rows, root = _search_file_index_fts(conn, trimmed, "photo", normalized_scope, root_path, limit)
        video_rows, root = _search_file_index_fts(conn, trimmed, "video", normalized_scope, root_path, limit)
        prompt_rows, root = _search_prompt_rows(conn, trimmed, normalized_scope, root_path, limit)

    format_root = root if root is not None else Path(os.sep)
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": _format_file_index_rows(photo_rows, format_root, "filename"),
        "videos": _format_file_index_rows(video_rows, format_root, "filename"),
        "prompt": _format_prompt_rows(prompt_rows, format_root),
    }


def _build_scope_named(scope: str, root_path: str | Path | None, alias: str = "fi") -> tuple[str, dict[str, str]]:
    """Build scope WHERE fragment and named params dict."""
    if scope != "current" or not root_path:
        return "", {}
    root = Path(root_path).resolve()
    root_str, root_prefix = _path_prefix(root)
    cond = f" AND ({alias}.path = :scope_root OR {alias}.path LIKE :scope_prefix ESCAPE '\\')"
    return cond, {"scope_root": root_str, "scope_prefix": root_prefix}


def _search_fielded_photos(
    conn: sqlite3.Connection,
    parsed: Any,
    scope: str,
    root_path: str | Path | None,
    root: Path,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    """Intersect filename matches with field-filtered paths using a CTE.

    NOTE: This function is used ONLY for the Photos (and indirectly Prompt) result
    sections.  It applies field filters (seed:, model:, etc.) to narrow results.
    The Albums section does NOT call this function — albums are folder suggestions
    based solely on residual text and are intentionally not field-filtered.

    WITH field_paths AS (
      SELECT m.path FROM image_metadata m JOIN file_index fi ON fi.path = m.path
      WHERE <field conditions>
    )
    SELECT fi.*
    FROM file_index_fts fts
    JOIN file_index fi ON fi.path = fts.path
    JOIN field_paths fp ON fp.path = fi.path
    WHERE fts MATCH <residual> AND fi.type = 'photo' <scope>
    ORDER BY ...

    Falls back to LIKE on fi.name when FTS returns zero rows.
    """
    from ..fielded_search_parser import (
        ParsedQuery,
        build_fielded_conditions,
    )

    photo_query = (parsed.residual_text or "").strip()
    if not photo_query:
        return [], root

    scope_cond, scope_params = _build_scope_named(scope, root_path, "fi")

    field_parsed = ParsedQuery(residual_text="", fields=parsed.fields)
    field_conditions, field_params = build_fielded_conditions(field_parsed)
    field_where = " AND ".join(field_conditions) if field_conditions else "1=1"

    def _build_params(**extra: Any) -> dict[str, Any]:
        p = dict(scope_params)
        p.update(field_params)
        p.update(extra)
        return p

    try:
        fts_query = _unicode_match_query(photo_query)
        params = _build_params(fts_query=fts_query, limit=limit)
        sql = f"""
            WITH field_paths AS (
                SELECT m.path
                FROM image_metadata m
                JOIN file_index fi ON fi.path = m.path
                WHERE {field_where}
            )
            SELECT fi.*
            FROM file_index_fts fts
            JOIN file_index fi ON fi.path = fts.path
            JOIN field_paths fp ON fp.path = fi.path
            WHERE fts MATCH :fts_query
              AND fi.type IN ('image', 'photo')
              {scope_cond}
            ORDER BY bm25(file_index_fts), fi.mtime DESC, fi.name ASC
            LIMIT :limit
        """
        rows = list(conn.execute(sql, params))
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(photo_query)
    params = _build_params(like_pattern=pattern, limit=limit)
    sql = f"""
        WITH field_paths AS (
            SELECT m.path
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE {field_where}
        )
        SELECT fi.*
        FROM file_index fi
        JOIN field_paths fp ON fp.path = fi.path
        WHERE fi.name LIKE :like_pattern ESCAPE '\\'
          AND fi.type IN ('image', 'photo')
          {scope_cond}
        ORDER BY fi.mtime DESC, fi.name ASC
        LIMIT :limit
    """
    rows = list(conn.execute(sql, params))
    return rows, root


def search_index_fielded(
    query: str, scope: str, root_path: str | Path | None = None, limit: int = 50
) -> dict[str, Any]:
    """Search indexed albums and photos with structured field filters."""
    from ..fielded_search_parser import (
        build_fielded_search_sql,
        parse_fielded_query,
    )

    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(display_root),
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    if normalized_scope == "current" and root is None:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": "",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    parsed = parse_fielded_query(trimmed)
    if not parsed.fields and len(trimmed) < MIN_PLAIN_SEARCH_QUERY_LENGTH:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(display_root),
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    # ── Albums section ──────────────────────────────────────────────────
    # Albums use ONLY residual_text (plain text outside field tokens like
    # seed: / model:).  They are intentionally NOT narrowed by metadata
    # field filters.  Albums are folder/album *suggestions* — navigation
    # aids based on folder name / path — not strict filtered image results.
    # This is a deliberate product decision; do not "fix" it without one.
    # ─────────────────────────────────────────────────────────────────────
    album_query = parsed.residual_text if parsed.residual_text else ""

    with _DB_LOCK, _connect() as conn:
        video_query = parsed.residual_text if parsed.residual_text else trimmed
        video_rows, root = _search_file_index_fts(conn, video_query, "video", normalized_scope, root_path, limit)
        if album_query:
            album_rows, root = _search_file_index_fts(conn, album_query, "folder", normalized_scope, root_path, limit)
        else:
            album_rows = []

        if parsed.fields:
            # ── Photos & Prompt sections (field-filtered) ──────────────
            # Photos intersect residual-text filename matches with
            # metadata field filters (seed:, model:, etc.) via a CTE.
            # Prompt/image-result rows are also narrowed by field filters.
            # These sections ARE guaranteed to satisfy metadata filters.
            # ───────────────────────────────────────────────────────────
            photo_rows, root = _search_fielded_photos(conn, parsed, normalized_scope, root_path, root, limit)

            if parsed.fields or parsed.residual_text:
                sql, sql_params = build_fielded_search_sql(parsed, limit)
                if normalized_scope == "current":
                    root_str, root_prefix = _path_prefix(root)
                    if "WHERE" in sql:
                        sql = sql.replace(
                            "WHERE ", "WHERE (fi.path = :scope_root OR fi.path LIKE :scope_prefix ESCAPE '\\') AND "
                        )
                    else:
                        sql = sql.replace(
                            "ORDER BY",
                            "WHERE (fi.path = :scope_root OR fi.path LIKE :scope_prefix ESCAPE '\\') ORDER BY",
                        )
                    sql_params["scope_root"] = root_str
                    sql_params["scope_prefix"] = root_prefix
                try:
                    prompt_rows = list(conn.execute(sql, sql_params))
                except Exception:  # noqa: BLE001
                    prompt_rows = []
            else:
                prompt_rows = []
        elif parsed.residual_text:
            # No fields, residual only — plain filename + metadata search
            photo_rows, root = _search_file_index_fts(
                conn, parsed.residual_text, "photo", normalized_scope, root_path, limit
            )
            prompt_rows, root = _search_prompt_rows(conn, parsed.residual_text, normalized_scope, root_path, limit)
        else:
            photo_rows = []
            prompt_rows = []

    format_root = root if root is not None else Path(os.sep)
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": _format_file_index_rows(photo_rows, format_root, "filename"),
        "videos": _format_file_index_rows(video_rows, format_root, "filename"),
        "prompt": _format_prompt_rows(prompt_rows, format_root),
    }
