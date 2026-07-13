"""Unified relevance candidates and opaque keyset cursors for gallery search."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from ..fielded_search_parser import ParsedQuery, build_fielded_conditions
from ..metadata_extract import contains_cjk
from ..workflow_discovery import build_workflow_group_conditions
from .identity import asset_owns_file_index_sql, catalog_import_path_owns_sql, file_index_matches_image_metadata_sql
from .path_utils import canonicalize_catalog_path, named_path_scope_sql

SEARCH_CURSOR_VERSION = 1
_CURRENT_METADATA_IDENTITY_SQL = file_index_matches_image_metadata_sql(fi_alias="fi", im_alias="m")


def _active_asset_join_sql(*, fi_alias: str = "fi", asset_alias: str = "catalog_asset") -> str:
    ownership = asset_owns_file_index_sql(asset_alias=asset_alias, fi_alias=fi_alias)
    import_ownership = catalog_import_path_owns_sql(
        library_id_sql=f"{asset_alias}.library_id",
        path_sql=f"{fi_alias}.path",
    )
    return (
        f"JOIN assets AS {asset_alias} ON {ownership} "
        f"JOIN libraries AS catalog_library ON catalog_library.id = {asset_alias}.library_id "
        f"AND {import_ownership}"
    )


def _escape_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _unicode_match_query(query: str) -> str:
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _trigram_match_query(query: str) -> str:
    return _escape_fts_token(query.strip())


def _column_fts_query(column: str, query: str, *, trigram: bool) -> str:
    match = _trigram_match_query(query) if trigram else _unicode_match_query(query)
    return f"{column} : ({match})"


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(query: str) -> str:
    return f"%{_like_escape(query)}%"


def request_fingerprint(
    query: str,
    scope: str,
    root_path: str | Path | None,
    *,
    fielded: bool,
    library_id: int | None = None,
    prompt_groups: list[tuple[str, bytes]] | None = None,
    workflow_groups: list[Any] | None = None,
) -> str:
    """Return the stable request identity bound into pagination cursors."""
    payload = {
        "fielded": fielded,
        "library_id": library_id,
        "query": query.strip(),
        "root": canonicalize_catalog_path(root_path) if root_path is not None else None,
        "scope": scope,
        "prompt_groups": [{"kind": kind, "value_hash": value_hash.hex()} for kind, value_hash in (prompt_groups or [])],
        "workflow_groups": [group.model_dump(mode="json") for group in (workflow_groups or [])],
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_search_cursor(row: sqlite3.Row, fingerprint: str) -> str:
    """Encode the final relevance tuple as versioned base64url JSON."""
    payload = {
        "asset_id": int(row["asset_id"]),
        "fingerprint": fingerprint,
        "mtime_ns": int(row["mtime_ns"]),
        "rank": float(row["rank"]),
        "tier": int(row["relevance_tier"]),
        "version": SEARCH_CURSOR_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_search_cursor(cursor: str, fingerprint: str) -> dict[str, int | float]:
    """Decode and validate one request-bound opaque search cursor."""
    if not cursor or re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
        raise ValueError("Invalid search cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        version = int(payload["version"])
        payload_fingerprint = str(payload["fingerprint"])
        tier = int(payload["tier"])
        rank = float(payload["rank"])
        mtime_ns = int(payload["mtime_ns"])
        asset_id = int(payload["asset_id"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid search cursor") from exc
    if version != SEARCH_CURSOR_VERSION or payload_fingerprint != fingerprint or not math.isfinite(rank):
        raise ValueError("Invalid search cursor")
    return {"tier": tier, "rank": rank, "mtime_ns": mtime_ns, "asset_id": asset_id}


def _cursor_state(
    cursor: str | int | None,
    fingerprint: str,
) -> tuple[dict[str, int | float] | None, int | None]:
    if cursor is None:
        return None, None
    if isinstance(cursor, int):
        return None, max(0, cursor)
    if cursor.isdecimal():
        return None, max(0, int(cursor))
    return decode_search_cursor(cursor, fingerprint), None


def _prefix_sql_params(sql: str, params: dict[str, Any], prefix: str) -> tuple[str, dict[str, Any]]:
    prefixed = sql
    prefixed_params: dict[str, Any] = {}
    for name in sorted(params, key=len, reverse=True):
        new_name = f"{prefix}{name}"
        prefixed = prefixed.replace(f":{name}", f":{new_name}")
        prefixed_params[new_name] = params[name]
    return prefixed, prefixed_params


def _filename_candidate_select(
    *,
    file_type: str,
    query_kind: str,
    scope_sql: str,
    field_where: str,
) -> str:
    type_sql = "fi.type IN ('image', 'photo')" if file_type == "image" else "fi.type = 'video'"
    metadata_join = ""
    metadata_where = ""
    metadata_values = "'' AS model, '' AS sampler, '' AS seed"
    if field_where:
        metadata_join = f"JOIN image_metadata m ON m.path = fi.path AND {_CURRENT_METADATA_IDENTITY_SQL}"
        metadata_where = f"AND {field_where}"
        metadata_values = (
            "coalesce(m.model, '') AS model, coalesce(m.sampler, '') AS sampler, coalesce(m.seed, '') AS seed"
        )
    if query_kind == "fts":
        source = f"""
          FROM file_index_fts
          JOIN file_index fi ON fi.path = file_index_fts.path
          {_active_asset_join_sql()}
          {metadata_join}
          WHERE file_index_fts MATCH :filename_match
            AND {type_sql}
            {scope_sql}
            {metadata_where}
        """
        rank_sql = "round(bm25(file_index_fts), 6)"
        fallback_tier = 70
    else:
        source = f"""
          FROM file_index fi
          {_active_asset_join_sql()}
          {metadata_join}
          WHERE fi.name LIKE :filename_like ESCAPE '\\'
            AND {type_sql}
            {scope_sql}
            {metadata_where}
        """
        rank_sql = "0.0"
        fallback_tier = 50
    return f"""
      SELECT fi.path, fi.name, fi.type, fi.parent_path, fi.mtime,
             catalog_asset.mtime_ns, fi.width, fi.height,
             catalog_asset.duration_ms, catalog_asset.mime_type,
             catalog_asset.id AS asset_id,
             catalog_asset.library_id AS library_id,
             catalog_library.name AS library_name,
             CASE
               WHEN fi.name = :query COLLATE NOCASE THEN 100
               WHEN fi.name LIKE :filename_prefix ESCAPE '\\' COLLATE NOCASE THEN 90
               ELSE {fallback_tier}
             END AS relevance_tier,
             CASE
               WHEN fi.name = :query COLLATE NOCASE THEN 0.0
               WHEN fi.name LIKE :filename_prefix ESCAPE '\\' COLLATE NOCASE THEN 0.0
               ELSE {rank_sql}
             END AS rank,
             CASE
               WHEN fi.name = :query COLLATE NOCASE THEN 'filename_exact'
               WHEN fi.name LIKE :filename_prefix ESCAPE '\\' COLLATE NOCASE THEN 'filename_prefix'
               ELSE 'filename'
             END AS match_type,
             '' AS prompt_snippet,
             {metadata_values}
      {source}
    """


def _metadata_candidate_select(
    *,
    source_kind: str,
    scope_sql: str,
    field_where: str,
    fts_table: str,
) -> str:
    field_clause = f"AND {field_where}" if field_where else ""
    if source_kind == "positive_phrase":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE m.prompt LIKE :text_like ESCAPE '\\'
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type, snippet = 80, "0.0", "prompt_phrase", "m.prompt"
    elif source_kind == "negative_phrase":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE m.negative_prompt LIKE :text_like ESCAPE '\\'
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type, snippet = 40, "0.0", "negative_prompt", "m.negative_prompt"
    elif source_kind == "metadata_like":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE (m.model LIKE :text_like ESCAPE '\\' OR m.sampler LIKE :text_like ESCAPE '\\')
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type, snippet = 65, "0.0", "metadata", "coalesce(m.model, m.sampler, '')"
    elif source_kind == "field_only":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type, snippet = 30, "0.0", "filters", "coalesce(m.prompt, m.name, '')"
    else:
        match_param = "positive_match" if source_kind == "positive_fts" else "negative_match"
        source = f"""
          FROM {fts_table}
          JOIN image_metadata m ON m.id = {fts_table}.rowid
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE {fts_table} MATCH :{match_param}
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier = 65 if source_kind == "positive_fts" else 40
        rank = f"round(bm25({fts_table}), 6)"
        match_type = "prompt" if source_kind == "positive_fts" else "negative_prompt"
        snippet = "m.prompt" if source_kind == "positive_fts" else "m.negative_prompt"
    return f"""
      SELECT m.path, m.name, fi.type, fi.parent_path, m.mtime,
             catalog_asset.mtime_ns, m.width, m.height,
             NULL AS duration_ms, NULL AS mime_type,
             catalog_asset.id AS asset_id,
             catalog_asset.library_id AS library_id,
             catalog_library.name AS library_name,
             {tier} AS relevance_tier,
             {rank} AS rank,
             '{match_type}' AS match_type,
             substr(trim(coalesce({snippet}, '')), 1, 240) AS prompt_snippet,
             coalesce(m.model, '') AS model,
             coalesce(m.sampler, '') AS sampler,
             coalesce(m.seed, '') AS seed
      {source}
    """


def _candidate_selects(
    query: str,
    scope_sql: str,
    *,
    include_fts: bool,
    field_where: str = "",
    include_videos: bool = True,
    field_only: bool = False,
) -> list[str]:
    if field_only:
        return [
            _metadata_candidate_select(
                source_kind="field_only",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table="image_metadata_fts",
            )
        ]

    selects = [
        _filename_candidate_select(
            file_type="image",
            query_kind="like",
            scope_sql=scope_sql,
            field_where=field_where,
        ),
        _metadata_candidate_select(
            source_kind="positive_phrase",
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table="image_metadata_fts",
        ),
        _metadata_candidate_select(
            source_kind="negative_phrase",
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table="image_metadata_fts",
        ),
        _metadata_candidate_select(
            source_kind="metadata_like",
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table="image_metadata_fts",
        ),
    ]
    if include_videos:
        selects.append(
            _filename_candidate_select(
                file_type="video",
                query_kind="like",
                scope_sql=scope_sql,
                field_where="",
            )
        )
    if not include_fts:
        return selects

    trigram = contains_cjk(query) and len(query) >= 3
    metadata_table = "image_metadata_fts_trigram" if trigram else "image_metadata_fts"
    selects.extend(
        [
            _filename_candidate_select(
                file_type="image",
                query_kind="fts",
                scope_sql=scope_sql,
                field_where=field_where,
            ),
            _metadata_candidate_select(
                source_kind="positive_fts",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table=metadata_table,
            ),
            _metadata_candidate_select(
                source_kind="negative_fts",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table=metadata_table,
            ),
        ]
    )
    if include_videos:
        selects.append(
            _filename_candidate_select(
                file_type="video",
                query_kind="fts",
                scope_sql=scope_sql,
                field_where="",
            )
        )
    return selects


def build_candidate_page_query(
    selects: list[str],
    *,
    has_cursor: bool,
    legacy_offset: bool,
) -> str:
    """Build the deduped relevance query, adding OFFSET only for legacy input."""
    union_sql = "\nUNION ALL\n".join(selects)
    cursor_where = ""
    if has_cursor:
        cursor_where = """
          AND (
            relevance_tier < :cursor_tier
            OR (relevance_tier = :cursor_tier AND rank > :cursor_rank)
            OR (relevance_tier = :cursor_tier AND rank = :cursor_rank AND mtime_ns < :cursor_mtime_ns)
            OR (relevance_tier = :cursor_tier AND rank = :cursor_rank
                AND mtime_ns = :cursor_mtime_ns AND asset_id > :cursor_asset_id)
          )
        """
    offset_sql = " OFFSET :legacy_offset" if legacy_offset else ""
    return f"""
      WITH candidates AS (
        {union_sql}
      ),
      deduped AS (
        SELECT *,
               row_number() OVER (
                 PARTITION BY asset_id
                 ORDER BY relevance_tier DESC, rank ASC, mtime_ns DESC, asset_id ASC
               ) AS candidate_rank
        FROM candidates
      )
      SELECT *
      FROM deduped
      WHERE candidate_rank = 1
      {cursor_where}
      ORDER BY relevance_tier DESC, rank ASC, mtime_ns DESC, asset_id ASC
      LIMIT :page_limit{offset_sql}
    """


def search_ranked_media_page(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
    cursor: str | int | None,
    *,
    parsed: ParsedQuery | None = None,
    library_id: int | None = None,
    prompt_groups: list[tuple[str, bytes]] | None = None,
    workflow_groups: list[Any] | None = None,
) -> tuple[list[sqlite3.Row], bool, str]:
    """Return one ranked media page plus its request fingerprint."""
    scope_sql, scope_params = ("", {})
    if scope == "current" and root_path is not None:
        scope_sql, scope_params = named_path_scope_sql(root_path, column="fi.path", leading_and=True)
    elif scope == "folder" and root_path is not None:
        scope_sql, scope_params = named_path_scope_sql(root_path, column="fi.path", leading_and=True)
        if library_id is not None:
            scope_sql += " AND fi.library_id = :scope_library_id"
            scope_params["scope_library_id"] = library_id
    elif scope == "library":
        scope_sql = " AND fi.library_id = :scope_library_id"
        scope_params = {"scope_library_id": library_id}
    is_fielded = parsed is not None
    fingerprint = request_fingerprint(
        query,
        scope,
        root_path,
        fielded=is_fielded,
        library_id=library_id,
        prompt_groups=prompt_groups,
        workflow_groups=workflow_groups,
    )
    cursor_position, legacy_offset = _cursor_state(cursor, fingerprint)
    residual = parsed.residual_text.strip() if parsed is not None else query.strip()

    field_where = ""
    field_params: dict[str, Any] = {}
    if parsed is not None:
        conditions, raw_params = build_fielded_conditions(ParsedQuery(residual_text="", fields=parsed.fields))
        for index, (kind, value_hash) in enumerate(prompt_groups or []):
            conditions.append(
                "EXISTS (SELECT 1 FROM asset_prompt_values AS prompt_group "
                "WHERE prompt_group.asset_id = catalog_asset.id "
                f"AND prompt_group.kind = :prompt_kind_{index} "
                f"AND prompt_group.value_hash = :prompt_hash_{index})"
            )
            raw_params[f"prompt_kind_{index}"] = kind
            raw_params[f"prompt_hash_{index}"] = value_hash
        workflow_conditions, workflow_params = build_workflow_group_conditions(workflow_groups or [])
        conditions.extend(workflow_conditions)
        raw_params.update(workflow_params)
        field_where = " AND ".join(conditions) if conditions else "1=1"
        field_where, field_params = _prefix_sql_params(field_where, raw_params, "field_")

    trigram = contains_cjk(residual) and len(residual) >= 3
    params: dict[str, Any] = {
        "filename_like": _like_pattern(residual),
        "filename_match": _unicode_match_query(residual),
        "filename_prefix": f"{_like_escape(residual)}%",
        "negative_match": _column_fts_query("negative_prompt", residual, trigram=trigram),
        "page_limit": limit + 1,
        "positive_match": _column_fts_query("prompt", residual, trigram=trigram),
        "query": residual,
        "text_like": _like_pattern(residual),
        **scope_params,
        **field_params,
    }
    if cursor_position is not None:
        params.update(
            {
                "cursor_tier": cursor_position["tier"],
                "cursor_rank": cursor_position["rank"],
                "cursor_mtime_ns": cursor_position["mtime_ns"],
                "cursor_asset_id": cursor_position["asset_id"],
            }
        )
    if legacy_offset is not None:
        params["legacy_offset"] = legacy_offset

    field_only = parsed is not None and not residual
    include_videos = parsed is None
    try:
        selects = _candidate_selects(
            residual,
            scope_sql,
            include_fts=not field_only,
            field_where=field_where,
            include_videos=include_videos,
            field_only=field_only,
        )
        rows = list(
            conn.execute(
                build_candidate_page_query(
                    selects,
                    has_cursor=cursor_position is not None,
                    legacy_offset=legacy_offset is not None,
                ),
                params,
            )
        )
    except sqlite3.OperationalError:
        if field_only:
            raise
        selects = _candidate_selects(
            residual,
            scope_sql,
            include_fts=False,
            field_where=field_where,
            include_videos=include_videos,
        )
        rows = list(
            conn.execute(
                build_candidate_page_query(
                    selects,
                    has_cursor=cursor_position is not None,
                    legacy_offset=legacy_offset is not None,
                ),
                params,
            )
        )
    return rows[:limit], len(rows) > limit, fingerprint


def is_first_search_page(cursor: str | int | None) -> bool:
    """Return whether album suggestions may be included for this request."""
    return cursor is None or cursor == 0 or cursor == "0"
