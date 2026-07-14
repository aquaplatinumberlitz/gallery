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
from ..workflow_discovery import build_workflow_group_conditions
from .identity import asset_owns_file_index_sql, catalog_import_path_owns_sql, file_index_matches_image_metadata_sql
from .path_utils import canonicalize_catalog_path, named_path_scope_sql

SEARCH_CURSOR_VERSION = 1
SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1
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


def _simple_active_asset_join_sql(*, fi_alias: str, asset_alias: str) -> str:
    """Join active assets for bounded preselection; strict ownership is applied outside."""
    return (
        f"JOIN assets AS {asset_alias} ON {asset_alias}.library_id = {fi_alias}.library_id "
        f"AND {asset_alias}.path = {fi_alias}.path "
        f"AND {asset_alias}.offline = 0 AND {asset_alias}.deleted_at IS NULL "
        f"AND {asset_alias}.mtime_ns IS NOT NULL"
    )


def _candidate_cursor_sql(*, tier_sql: str, rank_sql: str, mtime_sql: str, asset_id_sql: str) -> str:
    return f"""
      AND (
        {tier_sql} < :cursor_tier
        OR ({tier_sql} = :cursor_tier AND {rank_sql} > :cursor_rank)
        OR ({tier_sql} = :cursor_tier AND {rank_sql} = :cursor_rank AND {mtime_sql} < :cursor_mtime_ns)
        OR ({tier_sql} = :cursor_tier AND {rank_sql} = :cursor_rank
            AND {mtime_sql} = :cursor_mtime_ns AND {asset_id_sql} > :cursor_asset_id)
      )
    """


def _escape_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _unicode_match_query(query: str) -> str:
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _unicode_prefix_match_query(query: str) -> str:
    """Return a bounded token-prefix query for filename discovery."""
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(f"{_escape_fts_token(token)}*" for token in tokens)


def _trigram_match_query(query: str) -> str:
    return _escape_fts_token(query.strip())


def _trigram_token_match_query(query: str) -> str:
    """Preserve AND-token semantics while using the trigram candidate table."""
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _trigram_match_query(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _can_use_trigram_candidates(query: str) -> bool:
    trimmed = query.strip()
    if len(trimmed) < 3:
        return False
    tokens = re.findall(r"[\w.-]+", trimmed, flags=re.UNICODE)
    return bool(tokens) and all(len(token) >= 3 for token in tokens)


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
        version = payload["version"]
        payload_fingerprint = payload["fingerprint"]
        tier = payload["tier"]
        rank = payload["rank"]
        mtime_ns = payload["mtime_ns"]
        asset_id = payload["asset_id"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid search cursor") from exc
    integer_values = (version, tier, mtime_ns, asset_id)
    if any(not isinstance(value, int) or isinstance(value, bool) for value in integer_values):
        raise ValueError("Invalid search cursor")
    if not isinstance(payload_fingerprint, str):
        raise ValueError("Invalid search cursor")
    if not isinstance(rank, int | float) or isinstance(rank, bool):
        raise ValueError("Invalid search cursor")
    if (
        version != SEARCH_CURSOR_VERSION
        or payload_fingerprint != fingerprint
        or not math.isfinite(rank)
        or not 0 <= tier <= SQLITE_INT_MAX
        or not SQLITE_INT_MIN <= mtime_ns <= SQLITE_INT_MAX
        or not 1 <= asset_id <= SQLITE_INT_MAX
    ):
        raise ValueError("Invalid search cursor")
    return {"tier": tier, "rank": float(rank), "mtime_ns": mtime_ns, "asset_id": asset_id}


def _cursor_state(
    cursor: str | int | None,
    fingerprint: str,
) -> tuple[dict[str, int | float] | None, int | None]:
    if cursor is None:
        return None, None
    if isinstance(cursor, int):
        if isinstance(cursor, bool) or not 0 <= cursor <= SQLITE_INT_MAX:
            raise ValueError("Invalid search cursor")
        return None, cursor
    if cursor.isdecimal():
        legacy_offset = int(cursor)
        if legacy_offset > SQLITE_INT_MAX:
            raise ValueError("Invalid search cursor")
        return None, legacy_offset
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
        metadata_join = f"CROSS JOIN image_metadata m ON m.path = fi.path AND {_CURRENT_METADATA_IDENTITY_SQL}"
        metadata_where = f"AND {field_where}"
        metadata_values = (
            "coalesce(m.model, '') AS model, coalesce(m.sampler, '') AS sampler, coalesce(m.seed, '') AS seed"
        )
    if query_kind in {"fts", "trigram"}:
        fts_table = "file_index_fts_trigram" if query_kind == "trigram" else "file_index_fts"
        match_param = "filename_substring_match" if query_kind == "trigram" else "filename_match"
        source = f"""
          FROM {fts_table}
          CROSS JOIN file_index fi ON fi.rowid = {fts_table}.rowid
          {_active_asset_join_sql()}
          {metadata_join}
          WHERE {fts_table} MATCH :{match_param}
            AND {type_sql}
            {scope_sql}
            {metadata_where}
        """
        rank_sql = f"round(bm25({fts_table}), 6)"
        fallback_tier = 50 if query_kind == "trigram" else 70
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
    bounded_fts: bool = False,
    bounded_field_only: bool = False,
    has_cursor: bool = False,
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
        tier, rank, match_type_sql, snippet = 80, "0.0", "'prompt_phrase'", "m.prompt"
    elif source_kind == "negative_phrase":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE m.negative_prompt LIKE :text_like ESCAPE '\\'
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type_sql, snippet = 40, "0.0", "'negative_prompt'", "m.negative_prompt"
    elif source_kind == "metadata_like":
        source = f"""
          FROM image_metadata m
          JOIN file_index fi ON fi.path = m.path
          {_active_asset_join_sql()}
          WHERE (m.model LIKE :text_like ESCAPE '\\' OR m.sampler LIKE :text_like ESCAPE '\\')
            AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
        """
        tier, rank, match_type_sql, snippet = 65, "0.0", "'metadata'", "coalesce(m.model, m.sampler, '')"
    elif source_kind == "field_only":
        if bounded_field_only:
            pre_cursor = (
                _candidate_cursor_sql(
                    tier_sql="30",
                    rank_sql="0.0",
                    mtime_sql="catalog_asset.mtime_ns",
                    asset_id_sql="catalog_asset.id",
                )
                if has_cursor
                else ""
            )
            source = f"""
              FROM (
                SELECT m.id AS metadata_id
                FROM image_metadata m
                JOIN file_index fi ON fi.path = m.path
                {_simple_active_asset_join_sql(fi_alias="fi", asset_alias="catalog_asset")}
                WHERE 1 = 1 {scope_sql} {field_clause} {pre_cursor}
                ORDER BY catalog_asset.mtime_ns DESC, catalog_asset.id ASC
                LIMIT :field_candidate_limit
              ) AS bounded_field_rows
              CROSS JOIN image_metadata m ON m.id = bounded_field_rows.metadata_id
              JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {_CURRENT_METADATA_IDENTITY_SQL}
            """
        else:
            source = f"""
              FROM image_metadata m
              JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
            """
        tier, rank, match_type_sql, snippet = 30, "0.0", "'filters'", "coalesce(m.prompt, m.name, '')"
    else:
        match_param = {
            "positive_fts": "positive_match",
            "negative_fts": "negative_match",
            "metadata_fts": "metadata_match",
            "positive_trigram": "positive_substring_match",
            "negative_trigram": "negative_substring_match",
            "metadata_trigram": "metadata_substring_match",
        }[source_kind]
        if source_kind in {"positive_fts", "positive_trigram"}:
            tier = "CASE WHEN m.prompt LIKE :text_like ESCAPE '\\' THEN 80 ELSE 65 END"
            match_type_sql = "CASE WHEN m.prompt LIKE :text_like ESCAPE '\\' THEN 'prompt_phrase' ELSE 'prompt' END"
            snippet = "m.prompt"
            pre_tier = "CASE WHEN pre_m.prompt LIKE :text_like ESCAPE '\\' THEN 80 ELSE 65 END"
        elif source_kind in {"negative_fts", "negative_trigram"}:
            tier = 40
            match_type_sql = "'negative_prompt'"
            snippet = "m.negative_prompt"
            pre_tier = "40"
        else:
            tier = 65
            match_type_sql = "'metadata'"
            snippet = "coalesce(m.model, m.sampler, '')"
            pre_tier = "65"
        if bounded_fts:
            pre_rank = f"round({fts_table}.rank, 6)"
            if has_cursor:
                pre_joins = "JOIN file_index AS pre_fi ON pre_fi.path = pre_m.path " + _simple_active_asset_join_sql(
                    fi_alias="pre_fi", asset_alias="pre_asset"
                )
                pre_cursor = _candidate_cursor_sql(
                    tier_sql=pre_tier,
                    rank_sql=pre_rank,
                    mtime_sql="pre_asset.mtime_ns",
                    asset_id_sql="pre_asset.id",
                )
                pre_order = "pre_asset.mtime_ns DESC, pre_asset.id ASC"
            else:
                pre_joins = ""
                pre_cursor = ""
                pre_order = "COALESCE(pre_m.mtime_ns, CAST(pre_m.mtime * 1000000000 AS INTEGER)) DESC, pre_m.id ASC"
            source = f"""
              FROM (
                SELECT {fts_table}.rowid AS metadata_id, {pre_tier} AS pre_tier, {pre_rank} AS pre_rank
                FROM {fts_table}
                JOIN image_metadata AS pre_m ON pre_m.id = {fts_table}.rowid
                {pre_joins}
                WHERE {fts_table} MATCH :{match_param} {pre_cursor}
                ORDER BY pre_tier DESC, pre_rank ASC, {pre_order}
                LIMIT :fts_candidate_limit
              ) AS bounded_fts_rows
              CROSS JOIN image_metadata m ON m.id = bounded_fts_rows.metadata_id
              CROSS JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {_CURRENT_METADATA_IDENTITY_SQL}
            """
            rank = "bounded_fts_rows.pre_rank"
        else:
            source = f"""
              FROM {fts_table}
              CROSS JOIN image_metadata m ON m.id = {fts_table}.rowid
              CROSS JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {fts_table} MATCH :{match_param}
                AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {field_clause}
            """
            rank = f"round(bm25({fts_table}), 6)"
    return f"""
      SELECT m.path, m.name, fi.type, fi.parent_path, m.mtime,
             catalog_asset.mtime_ns, m.width, m.height,
             NULL AS duration_ms, NULL AS mime_type,
             catalog_asset.id AS asset_id,
             catalog_asset.library_id AS library_id,
             catalog_library.name AS library_name,
             {tier} AS relevance_tier,
             {rank} AS rank,
             {match_type_sql} AS match_type,
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
    bounded_candidates: bool = False,
    has_cursor: bool = False,
) -> list[str]:
    if field_only:
        return [
            _metadata_candidate_select(
                source_kind="field_only",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table="image_metadata_fts",
                bounded_field_only=bounded_candidates,
                has_cursor=has_cursor,
            )
        ]

    if not include_fts:
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
        return selects

    use_trigram = _can_use_trigram_candidates(query)
    metadata_table = "image_metadata_fts_trigram" if use_trigram else "image_metadata_fts"
    positive_kind = "positive_trigram" if use_trigram else "positive_fts"
    negative_kind = "negative_trigram" if use_trigram else "negative_fts"
    metadata_kind = "metadata_trigram" if use_trigram else "metadata_fts"
    bounded_metadata_fts = bounded_candidates and not scope_sql and not field_where
    selects = [
        _filename_candidate_select(
            file_type="image",
            query_kind="fts",
            scope_sql=scope_sql,
            field_where=field_where,
        ),
        _metadata_candidate_select(
            source_kind=positive_kind,
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table=metadata_table,
            bounded_fts=bounded_metadata_fts,
            has_cursor=has_cursor,
        ),
        _metadata_candidate_select(
            source_kind=negative_kind,
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table=metadata_table,
            bounded_fts=bounded_metadata_fts,
            has_cursor=has_cursor,
        ),
        _metadata_candidate_select(
            source_kind=metadata_kind,
            scope_sql=scope_sql,
            field_where=field_where,
            fts_table=metadata_table,
            bounded_fts=bounded_metadata_fts,
            has_cursor=has_cursor,
        ),
    ]
    if include_videos:
        selects.append(
            _filename_candidate_select(
                file_type="video",
                query_kind="fts",
                scope_sql=scope_sql,
                field_where="",
            )
        )
    if use_trigram:
        selects.append(
            _filename_candidate_select(
                file_type="image",
                query_kind="trigram",
                scope_sql=scope_sql,
                field_where=field_where,
            )
        )
        if include_videos:
            selects.append(
                _filename_candidate_select(
                    file_type="video",
                    query_kind="trigram",
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
    if len(selects) == 1:
        return f"""
          WITH candidates AS (
            {union_sql}
          )
          SELECT *
          FROM candidates
          WHERE 1 = 1
          {cursor_where}
          ORDER BY relevance_tier DESC, rank ASC, mtime_ns DESC, asset_id ASC
          LIMIT :page_limit{offset_sql}
        """
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

    trigram = _can_use_trigram_candidates(residual)
    metadata_substring_query = _trigram_token_match_query(residual) if trigram else _unicode_match_query(residual)
    params: dict[str, Any] = {
        "filename_like": _like_pattern(residual),
        "filename_match": _unicode_prefix_match_query(residual),
        "filename_substring_match": _trigram_match_query(residual),
        "filename_prefix": f"{_like_escape(residual)}%",
        "negative_match": _column_fts_query("negative_prompt", residual, trigram=False),
        "negative_substring_match": f"negative_prompt : ({metadata_substring_query})",
        "metadata_match": (
            f"({_column_fts_query('model', residual, trigram=False)}) OR "
            f"({_column_fts_query('sampler', residual, trigram=False)})"
        ),
        "metadata_substring_match": (
            f"(model : ({metadata_substring_query})) OR (sampler : ({metadata_substring_query}))"
        ),
        "page_limit": limit + 1,
        "positive_match": _column_fts_query("prompt", residual, trigram=False),
        "positive_substring_match": f"prompt : ({metadata_substring_query})",
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
    bounded_candidates = legacy_offset is None
    try:
        selects = _candidate_selects(
            residual,
            scope_sql,
            include_fts=not field_only,
            field_where=field_where,
            include_videos=include_videos,
            field_only=field_only,
            bounded_candidates=bounded_candidates,
            has_cursor=cursor_position is not None,
        )
        params["fts_candidate_limit"] = max(256, (limit + 1) * 4)
        params["field_candidate_limit"] = max(256, (limit + 1) * 4)
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
            bounded_candidates=False,
            has_cursor=cursor_position is not None,
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
