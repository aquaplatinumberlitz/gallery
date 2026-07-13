"""Metadata and file index search helpers."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from ..fielded_search_parser import ParsedQuery, build_fielded_conditions
from ..metadata_extract import contains_cjk
from ._db import _DB_LOCK, _connect
from ._schema import initialize_database
from .identity import active_catalog_file_sql, catalog_folder_has_active_asset_sql, current_file_metadata_sql
from .path_utils import named_path_scope_sql, path_scope_sql


def _metadata_store_build_album_metadata(path: Path) -> dict[str, Any]:
    from . import build_album_metadata

    return build_album_metadata(path)


SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
ALBUM_SUGGESTION_LIMIT = 12
_CURRENT_METADATA_SQL = current_file_metadata_sql(fi_alias="fi", im_alias="m")
_ACTIVE_FILE_SQL = active_catalog_file_sql(fi_alias="fi")
_CATALOG_FOLDER_SQL = catalog_folder_has_active_asset_sql(fi_alias="fi")


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
    clause, params = path_scope_sql(root, column=f"{alias}.path", leading_and=True)
    return clause, params, root


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
    catalog_sql = _CATALOG_FOLDER_SQL if file_type == "folder" else _ACTIVE_FILE_SQL
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
                WHERE fts MATCH ? AND {type_sql} AND {catalog_sql} {scope_sql}
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
            WHERE fi.name LIKE ? ESCAPE '\\' AND {type_sql} AND {catalog_sql} {scope_sql}
            ORDER BY fi.mtime DESC, fi.name ASC
            LIMIT ?
            """,
            [pattern, *type_params, *scope_params, limit],
        )
    )
    return rows, root


def _partition_media_page(
    media: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    photos: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    prompt: list[dict[str, Any]] = []
    for result in media:
        if result.get("match_type") == "prompt":
            prompt.append(result)
        elif result.get("type") == "video":
            videos.append(result)
        else:
            photos.append(result)
    return photos, videos, prompt


def _empty_search_response(
    query: str,
    scope: str,
    root: Path | str,
    limit: int,
) -> dict[str, Any]:
    return {
        "query": query,
        "scope": scope,
        "root": str(root),
        "albums": [],
        "photos": [],
        "videos": [],
        "prompt": [],
        "media": [],
        "next_cursor": None,
        "has_more": False,
        "returned": 0,
        "limit": limit,
    }


def _format_media_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
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
                "match_type": row["match_type"],
                "prompt_snippet": row["prompt_snippet"] or "",
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
        JOIN file_index fi ON fi.path = m.path
        WHERE {table} MATCH ? AND {_CURRENT_METADATA_SQL}
        ORDER BY rank ASC, m.mtime DESC, m.name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (match_query, limit, offset)))


def _count_fts(conn: sqlite3.Connection, table: str, match_query: str) -> int:
    row = conn.execute(
        f"""SELECT count(*) AS total
            FROM {table}
            JOIN image_metadata m ON m.id = {table}.rowid
            JOIN file_index fi ON fi.path = m.path
            WHERE {table} MATCH ? AND {_CURRENT_METADATA_SQL}""",
        (match_query,),
    ).fetchone()
    return int(row["total"] if row else 0)


def _search_like(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[sqlite3.Row]:
    pattern = _like_pattern(query)
    where = " OR ".join(f"m.{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    sql = f"""
        SELECT m.*
        FROM image_metadata m
        JOIN file_index fi ON fi.path = m.path
        WHERE ({where}) AND {_CURRENT_METADATA_SQL}
        ORDER BY m.mtime DESC, m.name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (*([pattern] * len(SEARCH_FIELDS)), limit, offset)))


def _count_like(conn: sqlite3.Connection, query: str) -> int:
    pattern = _like_pattern(query)
    where = " OR ".join(f"m.{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    row = conn.execute(
        f"""SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE ({where}) AND {_CURRENT_METADATA_SQL}""",
        [pattern] * len(SEARCH_FIELDS),
    ).fetchone()
    return int(row["total"] if row else 0)


def _media_file_select(
    *,
    query_kind: str,
    file_type: str,
    section_order: int,
    scope_sql: str,
    extra_join: str = "",
    extra_where: str = "",
) -> str:
    type_sql = "fi.type IN ('image', 'photo')" if file_type in {"image", "photo"} else "fi.type = 'video'"
    if query_kind == "fts":
        source_sql = f"""
            FROM file_index_fts fts
            JOIN file_index fi ON fi.path = fts.path
            {extra_join}
            WHERE fts MATCH :filename_match
              AND {type_sql}
              AND {_ACTIVE_FILE_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "bm25(file_index_fts)"
    else:
        source_sql = f"""
            FROM file_index fi
            {extra_join}
            WHERE fi.name LIKE :filename_like ESCAPE '\\'
              AND {type_sql}
              AND {_ACTIVE_FILE_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "0.0"

    return f"""
        SELECT
          fi.path AS path,
          fi.name AS name,
          fi.type AS type,
          fi.parent_path AS parent_path,
          fi.mtime AS mtime,
          fi.width AS width,
          fi.height AS height,
          (SELECT a.duration_ms FROM assets a
           WHERE a.path = fi.path AND a.duration_ms IS NOT NULL
           LIMIT 1) AS duration_ms,
          (SELECT a.mime_type FROM assets a
           WHERE a.path = fi.path AND a.mime_type IS NOT NULL
           LIMIT 1) AS mime_type,
          {section_order} AS section_order,
          {rank_sql} AS rank,
          'filename' AS match_type,
          '' AS prompt_snippet,
          '' AS model,
          '' AS sampler,
          '' AS seed
        {source_sql}
    """


def _media_prompt_select(
    *,
    query_kind: str,
    section_order: int,
    scope_sql: str,
    extra_where: str = "",
) -> str:
    if query_kind == "fts":
        source_sql = f"""
            FROM image_metadata_fts fts
            JOIN image_metadata m ON m.id = fts.rowid
            JOIN file_index fi ON fi.path = m.path
            WHERE image_metadata_fts MATCH :prompt_match
              AND {_CURRENT_METADATA_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "bm25(image_metadata_fts)"
    elif query_kind == "trigram":
        source_sql = f"""
            FROM image_metadata_fts_trigram fts
            JOIN image_metadata m ON m.id = fts.rowid
            JOIN file_index fi ON fi.path = m.path
            WHERE image_metadata_fts_trigram MATCH :prompt_match
              AND {_CURRENT_METADATA_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "bm25(image_metadata_fts_trigram)"
    elif query_kind == "fielded":
        source_sql = f"""
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE 1=1
              AND {_CURRENT_METADATA_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "0.0"
    else:
        prompt_where = " OR ".join(f"m.{field} LIKE :prompt_like ESCAPE '\\'" for field in PROMPT_SEARCH_FIELDS)
        source_sql = f"""
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE ({prompt_where})
              AND {_CURRENT_METADATA_SQL}
              {scope_sql}
              {extra_where}
        """
        rank_sql = "0.0"

    return f"""
        SELECT
          m.path AS path,
          m.name AS name,
          fi.type AS type,
          fi.parent_path AS parent_path,
          m.mtime AS mtime,
          m.width AS width,
          m.height AS height,
          NULL AS duration_ms,
          NULL AS mime_type,
          {section_order} AS section_order,
          {rank_sql} AS rank,
          'prompt' AS match_type,
          substr(
            trim(
              coalesce(nullif(m.prompt, ''), nullif(m.negative_prompt, ''), nullif(m.raw_metadata_text, ''),
                       nullif(m.model, ''), nullif(m.sampler, ''), nullif(m.name, ''), '')
            ),
            1,
            240
          ) AS prompt_snippet,
          coalesce(m.model, '') AS model,
          coalesce(m.sampler, '') AS sampler,
          coalesce(m.seed, '') AS seed
        {source_sql}
    """


def _count_filename_matches(
    conn: sqlite3.Connection,
    query: str,
    file_type: str,
    scope: str,
    root_path: str | Path | None,
) -> tuple[str, int]:
    scope_sql, scope_params, _root = _scope_clause(scope, root_path, "fi")
    type_sql = "fi.type IN ('image', 'photo')" if file_type in {"image", "photo"} else "fi.type = ?"
    type_params = [] if file_type in {"image", "photo"} else [file_type]
    try:
        match_query = _unicode_match_query(query)
        row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index_fts fts
            JOIN file_index fi ON fi.path = fts.path
            WHERE fts MATCH ? AND {type_sql} AND {_ACTIVE_FILE_SQL} {scope_sql}
            """,
            [match_query, *type_params, *scope_params],
        ).fetchone()
        total = int(row["total"] if row else 0)
        if total:
            return "fts", total
    except sqlite3.OperationalError:
        pass

    pattern = _like_pattern(query)
    row = conn.execute(
        f"""
        SELECT count(*) AS total
        FROM file_index fi
        WHERE fi.name LIKE ? ESCAPE '\\' AND {type_sql} AND {_ACTIVE_FILE_SQL} {scope_sql}
        """,
        [pattern, *type_params, *scope_params],
    ).fetchone()
    return "like", int(row["total"] if row else 0)


def _prompt_match_kind(conn: sqlite3.Connection, query: str, scope: str, root_path: str | Path | None) -> str:
    scope_sql, scope_params, _root = _scope_clause(scope, root_path, "fi")
    try:
        if contains_cjk(query) and len(query) >= 3:
            row = conn.execute(
                f"""
                SELECT count(*) AS total
                FROM image_metadata_fts_trigram fts
                JOIN image_metadata m ON m.id = fts.rowid
                JOIN file_index fi ON fi.path = m.path
                WHERE image_metadata_fts_trigram MATCH ? AND {_CURRENT_METADATA_SQL} {scope_sql}
                """,
                [_trigram_match_query(query), *scope_params],
            ).fetchone()
            if int(row["total"] if row else 0):
                return "trigram"
        elif not contains_cjk(query):
            row = conn.execute(
                f"""
                SELECT count(*) AS total
                FROM image_metadata_fts fts
                JOIN image_metadata m ON m.id = fts.rowid
                JOIN file_index fi ON fi.path = m.path
                WHERE image_metadata_fts MATCH ? AND {_CURRENT_METADATA_SQL} {scope_sql}
                """,
                [_unicode_match_query(query), *scope_params],
            ).fetchone()
            if int(row["total"] if row else 0):
                return "fts"
    except sqlite3.OperationalError:
        pass
    return "like"


def _paged_media_query(selects: list[str]) -> str:
    union_sql = "\nUNION ALL\n".join(selects)
    return f"""
        WITH candidates AS (
            {union_sql}
        ),
        deduped AS (
            SELECT
              *,
              row_number() OVER (
                PARTITION BY path
                ORDER BY section_order ASC, rank ASC, mtime DESC, name ASC, path ASC
              ) AS path_rank
            FROM candidates
        ),
        ordered AS (
            SELECT *
            FROM deduped
            WHERE path_rank = 1
            ORDER BY section_order ASC, rank ASC, mtime DESC, name ASC, path ASC
            LIMIT :page_limit OFFSET :page_offset
        )
        SELECT *
        FROM ordered
        ORDER BY section_order ASC, rank ASC, mtime DESC, name ASC, path ASC
    """


def _search_media_page(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
    cursor: int,
) -> tuple[list[sqlite3.Row], Path, bool]:
    _scope_sql, _scope_params, root = _scope_clause(scope, root_path, "fi")
    filename_kind, _filename_count = _count_filename_matches(conn, query, "photo", scope, root_path)
    video_kind, _video_count = _count_filename_matches(conn, query, "video", scope, root_path)
    prompt_kind = _prompt_match_kind(conn, query, scope, root_path)
    params: dict[str, Any] = {
        "filename_match": _unicode_match_query(query),
        "filename_like": _like_pattern(query),
        "prompt_match": _trigram_match_query(query) if prompt_kind == "trigram" else _unicode_match_query(query),
        "prompt_like": _like_pattern(query),
        "page_limit": limit + 1,
        "page_offset": cursor,
    }
    named_scope_sql, named_scope_params = _build_scope_named(scope, root_path, "fi")
    params.update(named_scope_params)

    rows = list(
        conn.execute(
            _paged_media_query(
                [
                    _media_file_select(
                        query_kind=filename_kind,
                        file_type="photo",
                        section_order=0,
                        scope_sql=named_scope_sql,
                    ),
                    _media_file_select(
                        query_kind=video_kind,
                        file_type="video",
                        section_order=1,
                        scope_sql=named_scope_sql,
                    ),
                    _media_prompt_select(
                        query_kind=prompt_kind,
                        section_order=2,
                        scope_sql=named_scope_sql,
                    ),
                ]
            ),
            params,
        )
    )
    return rows[:limit], root, len(rows) > limit


def _prefix_sql_params(sql: str, params: dict[str, Any], prefix: str) -> tuple[str, dict[str, Any]]:
    prefixed = sql
    prefixed_params: dict[str, Any] = {}
    for name in sorted(params, key=len, reverse=True):
        new_name = f"{prefix}{name}"
        prefixed = prefixed.replace(f":{name}", f":{new_name}")
        prefixed_params[new_name] = params[name]
    return prefixed, prefixed_params


def _search_fielded_media_page(
    conn: sqlite3.Connection,
    parsed: ParsedQuery,
    scope: str,
    root_path: str | Path | None,
    limit: int,
    cursor: int,
) -> tuple[list[sqlite3.Row], Path, bool]:
    _scope_sql, _scope_params, root = _scope_clause(scope, root_path, "fi")
    named_scope_sql, named_scope_params = _build_scope_named(scope, root_path, "fi")
    params: dict[str, Any] = {"page_limit": limit + 1, "page_offset": cursor}
    params.update(named_scope_params)

    selects: list[str] = []
    ctes: list[str] = []
    residual = (parsed.residual_text or "").strip()
    if residual:
        field_parsed = ParsedQuery(residual_text="", fields=parsed.fields)
        field_conditions, field_params = build_fielded_conditions(field_parsed)
        field_where = " AND ".join(field_conditions) if field_conditions else "1=1"
        field_where, prefixed_params = _prefix_sql_params(field_where, field_params, "fp_")
        params.update(prefixed_params)
        ctes.append(
            """
            field_paths AS (
                SELECT m.path
                FROM image_metadata m
                JOIN file_index fi ON fi.path = m.path
                WHERE __FIELD_WHERE__ AND __CURRENT_METADATA__
            )
            """.replace("__FIELD_WHERE__", field_where).replace("__CURRENT_METADATA__", _CURRENT_METADATA_SQL)
        )
        params["filename_like"] = _like_pattern(residual)
        selects.append(
            _media_file_select(
                query_kind="like",
                file_type="photo",
                section_order=0,
                scope_sql=named_scope_sql,
                extra_join="JOIN field_paths fp ON fp.path = fi.path",
            )
        )

    prompt_conditions, prompt_params = build_fielded_conditions(parsed)
    prompt_where = " AND ".join(prompt_conditions) if prompt_conditions else "1=1"
    prompt_where, prefixed_prompt_params = _prefix_sql_params(prompt_where, prompt_params, "pm_")
    params.update(prefixed_prompt_params)
    selects.append(
        _media_prompt_select(
            query_kind="fielded",
            section_order=2,
            scope_sql=named_scope_sql,
            extra_where=f" AND {prompt_where}",
        )
    )
    query = _paged_media_query(selects)
    if ctes:
        query = query.replace("WITH candidates AS (", "WITH " + ",\n".join(ctes) + ",\ncandidates AS (", 1)

    rows = list(conn.execute(query, params))
    return rows[:limit], root, len(rows) > limit


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


def search_index(
    query: str,
    scope: str,
    root_path: str | Path | None = None,
    limit: int = 50,
    cursor: int = 0,
) -> dict[str, Any]:
    """Search indexed albums, photos, and prompts using free-text query semantics."""
    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    cursor = max(0, int(cursor))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed:
        return _empty_search_response(query, normalized_scope, display_root, limit)

    if normalized_scope == "current" and root is None:
        return _empty_search_response(query, normalized_scope, "", limit)

    with _DB_LOCK, _connect() as conn:
        if cursor == 0:
            album_rows, root = _search_file_index_fts(
                conn, trimmed, "folder", normalized_scope, root_path, ALBUM_SUGGESTION_LIMIT
            )
        else:
            album_rows = []
        media_rows, root, has_more = _search_media_page(conn, trimmed, normalized_scope, root_path, limit, cursor)

    format_root = root if root is not None else Path(os.sep)
    media = _format_media_rows(media_rows, format_root)
    page_photos, page_videos, page_prompt = _partition_media_page(media)
    next_cursor = cursor + len(media) if has_more else None
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": page_photos,
        "videos": page_videos,
        "prompt": page_prompt,
        "media": media,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "returned": len(media),
        "limit": limit,
    }


def _build_scope_named(scope: str, root_path: str | Path | None, alias: str = "fi") -> tuple[str, dict[str, Any]]:
    """Build scope WHERE fragment and named params dict."""
    if scope != "current" or not root_path:
        return "", {}
    return named_path_scope_sql(root_path, column=f"{alias}.path", leading_and=True)


def search_index_fielded(
    query: str,
    scope: str,
    root_path: str | Path | None = None,
    limit: int = 50,
    cursor: int = 0,
) -> dict[str, Any]:
    """Search indexed albums and photos with structured field filters."""
    from ..fielded_search_parser import (
        parse_fielded_query,
    )

    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    cursor = max(0, int(cursor))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed:
        return _empty_search_response(query, normalized_scope, display_root, limit)

    if normalized_scope == "current" and root is None:
        return _empty_search_response(query, normalized_scope, "", limit)

    parsed = parse_fielded_query(trimmed)

    # ── Albums section ──────────────────────────────────────────────────
    # Albums use ONLY residual_text (plain text outside field tokens like
    # seed: / model:).  They are intentionally NOT narrowed by metadata
    # field filters.  Albums are folder/album *suggestions* — navigation
    # aids based on folder name / path — not strict filtered image results.
    # This is a deliberate product decision; do not "fix" it without one.
    # ─────────────────────────────────────────────────────────────────────
    album_query = parsed.residual_text if parsed.residual_text else ""

    with _DB_LOCK, _connect() as conn:
        if album_query and cursor == 0:
            album_rows, root = _search_file_index_fts(
                conn, album_query, "folder", normalized_scope, root_path, ALBUM_SUGGESTION_LIMIT
            )
        else:
            album_rows = []
        media_rows, root, has_more = _search_fielded_media_page(
            conn, parsed, normalized_scope, root_path, limit, cursor
        )

    format_root = root if root is not None else Path(os.sep)
    media = _format_media_rows(media_rows, format_root)
    page_photos, page_videos, page_prompt = _partition_media_page(media)
    next_cursor = cursor + len(media) if has_more else None
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": page_photos,
        "videos": page_videos,
        "prompt": page_prompt,
        "media": media,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "returned": len(media),
        "limit": limit,
    }
