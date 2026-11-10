"""Unified relevance candidates and opaque keyset cursors for gallery search."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..fielded_search_parser import ParsedQuery, build_fielded_conditions
from ..text_fold import fold_text
from ..workflow_discovery import build_workflow_group_conditions
from .cjk_index import CJK_FTS_TABLE, plan_short_query
from .identity import asset_owns_file_index_sql, catalog_import_path_owns_sql, file_index_matches_image_metadata_sql
from .path_utils import canonicalize_catalog_path
from .search_text_index import META_FOLD_TABLE
from .search_window_cache import SEARCH_WINDOW_CACHE, SearchWindowCache, WindowEntry, estimate_rows_size

SEARCH_CURSOR_VERSION = 1
SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1
# `/api/search/count` stops counting at this many distinct assets (the `+` convention of the match preview).
COUNT_CAP = 4096
# A filename source with at most this many FTS matches is read whole (exact cross-source dedup); a larger one is
# read through bounded, cursor pre-filtered hi/lo variants.
FILE_SOURCE_SMALL_LIMIT = 2048
# Rows each bounded preselect keeps (floor; a page of ``limit`` keeps ``(limit + 1) * 4`` when that is more).
FTS_CANDIDATE_FLOOR = 256
# Rows an ordered field-only probe may examine, per candidate it is asked for, before the sorting plan takes over.
FIELD_PROBE_ROWS_PER_CANDIDATE = 8
# Metadata rows a field-only count may probe row by row before it falls back to the set-driven plan.
COUNT_PROBE_ROWS = 12288
_CURRENT_METADATA_IDENTITY_SQL = file_index_matches_image_metadata_sql(fi_alias="fi", im_alias="m")
_METADATA_MTIME_SQL = "COALESCE({alias}.mtime_ns, CAST({alias}.mtime * 1000000000 AS INTEGER))"

# Relevance tiers. Word-prefix matches (and CJK substring matches, which have no word boundary) are the
# primary tiers, all >= 40. Latin substring (trigram) matches are secondary tiers, all < 40, so every prefix
# match of the same query ranks above every substring match.
TIER_PROMPT_PHRASE = 80
TIER_PROMPT = 65
TIER_NEGATIVE = 40
TIER_SUBSTRING_PROMPT_PHRASE = 39
TIER_SUBSTRING_FILENAME = 38
TIER_SUBSTRING_PROMPT = 37
TIER_SUBSTRING_METADATA = 36
TIER_SUBSTRING_NEGATIVE = 35


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


def _cursor_tuple_sql(*, tier_sql: str, rank_bin_sql: str, mtime_sql: str, asset_id_sql: str) -> str:
    """Rows strictly after the cursor, on integer sort keys; ``asset_id_sql`` only runs on an exact key tie.

    The row-value form reads each key once (a bm25 rank is expensive to read twice). The tie-break matters:
    more rows than the preselect limit can share one (tier, rank, mtime) key, and keyset paging only advances
    through them if rows at or before the cursor's asset id are excluded here.
    """
    after = f"(-{tier_sql}, {rank_bin_sql}, -{mtime_sql})"
    cursor = "(-:cursor_tier, :cursor_rank_bin, -:cursor_mtime_ns)"
    return f"AND ({after} > {cursor} OR ({after} = {cursor} AND {asset_id_sql} > :cursor_asset_id))"


_METADATA_ASSET_ID_SQL = (
    "(SELECT pre_a.id FROM image_metadata AS pre_mm "
    "JOIN file_index AS pre_f ON pre_f.path = pre_mm.path "
    "JOIN assets AS pre_a ON pre_a.library_id = pre_f.library_id AND pre_a.path = pre_f.path "
    "WHERE pre_mm.id = {id_sql})"
)
_FILE_ASSET_ID_SQL = (
    "(SELECT pre_a.id FROM file_index AS pre_f "
    "JOIN assets AS pre_a ON pre_a.library_id = pre_f.library_id AND pre_a.path = pre_f.path "
    "WHERE pre_f.rowid = {id_sql})"
)


# Where a bounded source's preselect goes inside its statement (the page plan can run the preselect on its own).
_PRESELECT_SLOT = "/*PRESELECT*/"
# The rows of a preselect the page plan hands back to the statement as JSON (`[[id, tier-or-rank-bin], ...]`).
_PRESELECT_ROWS_PARAM = "pre_rows"


class _Source(str):
    """One candidate SELECT of the ranked page plan, plus what the planner needs to know about it.

    ``kind`` is ``"meta"`` for metadata/prompt sources (bounded, cursor pre-filtered before the cross-source
    dedup) and ``"file"`` for filename sources (their rows reach the dedup unfiltered unless the match set is
    large). ``min_tier``/``max_tier`` bound the ``relevance_tier`` the SELECT can emit; the planner reads
    the sources from the highest tier down and stops once a full page outranks every source left.

    A file source also carries ``probe`` (its FTS table and MATCH parameter) and ``dense``: bounded hi/lo
    SELECTs that replace it when its FTS match set is larger than ``FILE_SOURCE_SMALL_LIMIT``.

    A bounded source built for the exact (scoped or fielded) page plan also carries ``pre_sql`` (its preselect
    on its own, ``fts_candidate_limit`` rows) and ``rows_sql`` (the same statement reading those rows from the
    ``:pre_rows`` JSON parameter): the plan then knows whether the preselect was cut short and whether the
    strict ownership joins dropped any of its rows. ``retry`` is the same source with its preselect also joining
    the active asset (offline and deleted matches never take a slot), read when the first attempt lost rows.
    """

    kind: str
    min_tier: int
    max_tier: int
    dense: tuple[_Source, ...]
    probe: tuple[str, str] | None
    file_type: str | None
    pre_sql: str | None
    rows_sql: str | None
    retry: _Source | None

    def __new__(
        cls,
        sql: str,
        *,
        kind: str,
        min_tier: int,
        max_tier: int,
        dense: tuple[_Source, ...] = (),
        probe: tuple[str, str] | None = None,
        file_type: str | None = None,
        pre_sql: str | None = None,
        rows_sql: str | None = None,
    ) -> _Source:
        self = super().__new__(cls, sql)
        self.kind = kind
        self.min_tier = min_tier
        self.max_tier = max_tier
        self.dense = dense
        self.probe = probe
        self.file_type = file_type
        self.pre_sql = pre_sql
        self.rows_sql = rows_sql
        self.retry = None
        return self


def _preselect_rows_subquery(columns: tuple[str, ...]) -> str:
    """The JSON-backed stand-in of a preselect: one column per entry of ``columns`` (all integers)."""
    selected = ", ".join(
        f"CAST(json_extract(value, '$[{index}]') AS INTEGER) AS {column}" for index, column in enumerate(columns)
    )
    return f"SELECT {selected} FROM json_each(:{_PRESELECT_ROWS_PARAM})"


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


def _short_match_params(query: str) -> dict[str, str]:
    """Match overrides for queries that cannot use trigram candidates (a token under three characters).

    Latin terms become token prefixes on the Unicode FTS table; CJK terms become bigram phrases or
    one-character prefixes on the CJK bigram table. Every term is ANDed; a mixed query matches the
    Latin terms on the Unicode table and constrains rows to the CJK table with ``IN (...)``.
    """
    plan = None if _can_use_trigram_candidates(query) else plan_short_query(query)
    if plan is None:
        return {}
    prefix_all = _unicode_prefix_match_query(query)
    params = {"metadata_match": f"(model : ({prefix_all})) OR (sampler : ({prefix_all}))"}
    for column, param in (("prompt", "positive"), ("negative_prompt", "negative")):
        if plan.cjk_terms:
            params[f"{param}_cjk_match"] = f"{column} : ({plan.cjk_match})"
        if plan.latin_terms:
            params[f"{param}_match"] = f"{column} : ({plan.latin_match})"
        else:
            params[f"{param}_match"] = params[f"{param}_cjk_match"]
    return params


def _text_match_params(residual: str) -> dict[str, Any]:
    """MATCH/LIKE parameters for a query: folded for the folded indexes, original for the LIKE fallbacks.

    Every ``*_match`` is a word-prefix expression for the unicode61 tables; ``*_substring_match`` feeds the
    trigram tables (used from three characters). ``fold_*`` values compare against folded stored text.
    """
    folded = fold_text(residual)
    prefix_all = _unicode_prefix_match_query(folded)
    substring = _trigram_token_match_query(folded)
    params: dict[str, Any] = {
        "filename_like": _like_pattern(residual),
        "filename_match": prefix_all,
        "filename_substring_match": _trigram_match_query(folded),
        "filename_prefix": f"{_like_escape(residual)}%",
        "fold_filename_prefix": f"{_like_escape(folded)}%",
        "fold_like": _like_pattern(folded),
        "fold_query": folded,
        "negative_match": f"negative_prompt : ({prefix_all})",
        "negative_substring_match": f"negative_prompt : ({substring})",
        "metadata_match": f"(model : ({prefix_all})) OR (sampler : ({prefix_all}))",
        "metadata_substring_match": f"(model : ({substring})) OR (sampler : ({substring}))",
        "positive_match": f"prompt : ({prefix_all})",
        "positive_substring_match": f"prompt : ({substring})",
        "query": residual,
        "text_like": _like_pattern(residual),
    }
    params.update(_short_match_params(folded))
    return params


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
    substring_tier: int = TIER_SUBSTRING_FILENAME,
    count_only: bool = False,
    extra_where: str = "",
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
    exact_sql = "fi.name = :query COLLATE NOCASE"
    prefix_sql = "fi.name LIKE :filename_prefix ESCAPE '\\' COLLATE NOCASE"
    if query_kind in {"fts", "trigram"}:
        # Folded names: word-prefix (unicode61) and substring (trigram) tables keyed by file_index.rowid.
        fts_table = "file_index_fold_fts_trigram" if query_kind == "trigram" else "file_index_fold_fts"
        match_param = "filename_substring_match" if query_kind == "trigram" else "filename_match"
        exact_sql = "ff.name = :fold_query"
        prefix_sql = "ff.name LIKE :fold_filename_prefix ESCAPE '\\'"
        source = f"""
          FROM {fts_table}
          CROSS JOIN file_index fi ON fi.rowid = {fts_table}.rowid
          JOIN file_index_fold ff ON ff.file_rowid = fi.rowid
          {_active_asset_join_sql()}
          {metadata_join}
          WHERE {fts_table} MATCH :{match_param}
            AND {type_sql}
            {scope_sql}
            {extra_where}
            {metadata_where}
        """
        rank_sql = f"round(bm25({fts_table}), 6)"
        fallback_tier = substring_tier if query_kind == "trigram" else 70
    else:
        source = f"""
          FROM file_index fi
          {_active_asset_join_sql()}
          {metadata_join}
          WHERE fi.name LIKE :filename_like ESCAPE '\\'
            AND {type_sql}
            {scope_sql}
            {extra_where}
            {metadata_where}
        """
        rank_sql = "0.0"
        fallback_tier = 50
    if count_only:
        return f"SELECT catalog_asset.id AS asset_id {source}"
    return f"""
      SELECT fi.path, fi.name, fi.type, fi.parent_path, fi.mtime,
             catalog_asset.mtime_ns, catalog_asset.size AS asset_size, catalog_asset.animated AS asset_animated, fi.width, fi.height,
             catalog_asset.duration_ms, catalog_asset.mime_type,
             catalog_asset.id AS asset_id,
             catalog_asset.library_id AS library_id,
             catalog_library.name AS library_name,
             CASE
               WHEN {exact_sql} THEN 100
               WHEN {prefix_sql} THEN 90
               ELSE {fallback_tier}
             END AS relevance_tier,
             CASE
               WHEN {exact_sql} THEN 0.0
               WHEN {prefix_sql} THEN 0.0
               ELSE {rank_sql}
             END AS rank,
             CASE
               WHEN {exact_sql} THEN 'filename_exact'
               WHEN {prefix_sql} THEN 'filename_prefix'
               ELSE 'filename'
             END AS match_type,
             '' AS prompt_snippet,
             {metadata_values}
      {source}
    """


def _metadata_candidate_select(**kwargs: Any) -> str:
    """One metadata/prompt candidate SELECT (see ``_metadata_candidate_parts`` for the arguments)."""
    return _metadata_candidate_parts(**kwargs)[0]


def _metadata_candidate_parts(
    *,
    source_kind: str,
    scope_sql: str,
    field_where: str,
    fts_table: str,
    bounded_fts: bool = False,
    bounded_field_only: bool = False,
    has_cursor: bool = False,
    cjk_match_param: str | None = None,
    secondary: bool = False,
    count_only: bool = False,
    preselected_ids: bool = False,
    scope: _ScopeFilter | None = None,
    extra_where: str = "",
    preselect_assets: bool = False,
) -> tuple[str, str | None, str | None]:
    """A metadata/prompt candidate SELECT, plus its preselect and its ``:pre_rows`` form when it is bounded.

    A bounded FTS source preselects the best ``fts_candidate_limit`` matches before the strict ownership joins.
    A scoped or field-filtered one applies the scope and the field conditions inside that preselect (the
    metadata row is aliased ``m``, its file row ``fi`` and its asset ``catalog_asset`` there, so the same
    predicates read in both places): the bound then keeps the best rows *inside* the scope and filters, and is
    equal to the old unbounded statement's top rows. ``preselect_assets`` also requires an active asset in the
    preselect, so offline and deleted matches never use up a slot.
    """
    preselect: str | None = None
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
        if preselected_ids:
            source = f"""
              FROM (SELECT CAST(value AS INTEGER) AS metadata_id FROM json_each(:field_probe_ids)) AS bounded_field_rows
              CROSS JOIN image_metadata m ON m.id = bounded_field_rows.metadata_id
              JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {_CURRENT_METADATA_IDENTITY_SQL}
            """
        elif bounded_field_only:
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
        phrase_hit = "{alias}.prompt LIKE :fold_like ESCAPE '\\'"
        if bounded_fts and scope_sql and scope is None:
            raise ValueError("a scoped bounded source needs its scope filter")
        filtered = bounded_fts and bool(scope_sql or field_where)
        pm = "m" if filtered else "pre_m"
        if source_kind in {"positive_fts", "positive_trigram"}:
            hit, miss = (
                (TIER_SUBSTRING_PROMPT_PHRASE, TIER_SUBSTRING_PROMPT)
                if secondary
                else (TIER_PROMPT_PHRASE, TIER_PROMPT)
            )
            tier = f"CASE WHEN {phrase_hit.format(alias='f')} THEN {hit} ELSE {miss} END"
            match_type_sql = f"CASE WHEN {phrase_hit.format(alias='f')} THEN 'prompt_phrase' ELSE 'prompt' END"
            snippet = "m.prompt"
            pre_tier = f"CASE WHEN {phrase_hit.format(alias='pre_f')} THEN {hit} ELSE {miss} END"
            pre_fold_join = f"LEFT JOIN {META_FOLD_TABLE} AS pre_f ON pre_f.metadata_id = {pm}.id"
        elif source_kind in {"negative_fts", "negative_trigram"}:
            tier = TIER_SUBSTRING_NEGATIVE if secondary else TIER_NEGATIVE
            match_type_sql = "'negative_prompt'"
            snippet = "m.negative_prompt"
            pre_tier = str(tier)
            pre_fold_join = ""
        else:
            tier = TIER_SUBSTRING_METADATA if secondary else TIER_PROMPT
            match_type_sql = "'metadata'"
            snippet = "coalesce(m.model, m.sampler, '')"
            pre_tier = str(tier)
            pre_fold_join = ""
        fold_join = (
            f"LEFT JOIN {META_FOLD_TABLE} AS f ON f.metadata_id = m.id" if source_kind.startswith("positive") else ""
        )
        cjk_subquery = (
            f"IN (SELECT rowid FROM {CJK_FTS_TABLE} WHERE {CJK_FTS_TABLE} MATCH :{cjk_match_param})"
            if cjk_match_param
            else ""
        )
        pre_cjk_filter = f"AND {pm}.id {cjk_subquery}" if cjk_subquery else ""
        cjk_filter = f"AND m.id {cjk_subquery}" if cjk_subquery else ""
        if bounded_fts:
            # bm25 as an integer in millionths (the page rank is that value / 1e6, i.e. ``round(bm25, 6)``):
            # sorting an integer key is much cheaper than ``round(rank, 6)`` on every match, and the key is
            # computed once per row, then shared by the cursor test and the sort.
            rank_bin = f"CAST({fts_table}.rank * 1000000.0 - 0.5 AS INTEGER)"
            pre_mtime = _METADATA_MTIME_SQL.format(alias=pm)
            pre_join = "JOIN" if not filtered else "CROSS JOIN"
            pre_extra_joins = ""
            pre_filters = ""
            if filtered:
                needs_assets = preselect_assets or "catalog_asset" in field_where
                has_fi = needs_assets or (scope is not None and scope.needs_file_index())
                if has_fi:
                    pre_extra_joins += "CROSS JOIN file_index AS fi ON fi.path = m.path "
                if needs_assets:
                    pre_extra_joins += _simple_active_asset_join_sql(
                        fi_alias="fi", asset_alias="catalog_asset"
                    ).replace("JOIN assets", "CROSS JOIN assets", 1)
                if scope is not None:
                    pre_filters += scope.sql("m.path", "fi.library_id" if has_fi else None, preselect=True)
                if field_where:
                    pre_filters += f" AND {field_where}"
            if has_cursor:
                # The unpaged plan's key (the metadata row's own mtime, equal to the asset's for every row that
                # survives the strict ownership join).
                pre_cursor = _cursor_tuple_sql(
                    tier_sql="pre_tier",
                    rank_bin_sql="pre_rank_bin",
                    mtime_sql="pre_mtime",
                    asset_id_sql=_METADATA_ASSET_ID_SQL.format(id_sql="pre_id"),
                )
                preselect = f"""
                SELECT metadata_id, pre_tier, pre_rank_bin FROM (
                  SELECT {fts_table}.rowid AS metadata_id, {pre_tier} AS pre_tier, {rank_bin} AS pre_rank_bin,
                         {pre_mtime} AS pre_mtime, {pm}.id AS pre_id
                  FROM {fts_table}
                  {pre_join} image_metadata AS {pm} ON {pm}.id = {fts_table}.rowid
                  {pre_extra_joins}
                  {pre_fold_join}
                  WHERE {fts_table} MATCH :{match_param}
                    {pre_cjk_filter} {pre_filters}
                  LIMIT -1
                )
                WHERE 1 = 1
                  {pre_cursor}
                ORDER BY pre_tier DESC, pre_rank_bin ASC, pre_mtime DESC, pre_id ASC
                LIMIT :fts_candidate_limit
                """
            else:
                preselect = f"""
                SELECT {fts_table}.rowid AS metadata_id, {pre_tier} AS pre_tier, {rank_bin} AS pre_rank_bin
                FROM {fts_table}
                {pre_join} image_metadata AS {pm} ON {pm}.id = {fts_table}.rowid
                {pre_extra_joins}
                {pre_fold_join}
                WHERE {fts_table} MATCH :{match_param}
                  {pre_cjk_filter} {pre_filters}
                ORDER BY pre_tier DESC, pre_rank_bin ASC, {pre_mtime} DESC, {pm}.id ASC
                LIMIT :fts_candidate_limit
                """
            source = f"""
              FROM ({_PRESELECT_SLOT}) AS bounded_fts_rows
              CROSS JOIN image_metadata m ON m.id = bounded_fts_rows.metadata_id
              {fold_join}
              CROSS JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql}
            """
            # The preselect already applied the field conditions: repeating them here would rebuild their
            # set subqueries (an FTS scan each) for a handful of rows.
            rank = "(bounded_fts_rows.pre_rank_bin / 1000000.0)"
        else:
            source = f"""
              FROM {fts_table}
              CROSS JOIN image_metadata m ON m.id = {fts_table}.rowid
              {fold_join}
              CROSS JOIN file_index fi ON fi.path = m.path
              {_active_asset_join_sql()}
              WHERE {fts_table} MATCH :{match_param}
                {cjk_filter}
                AND {_CURRENT_METADATA_IDENTITY_SQL} {scope_sql} {extra_where} {field_clause}
            """
            rank = f"round(bm25({fts_table}), 6)"
    if count_only:
        return f"SELECT catalog_asset.id AS asset_id {source}", None, None
    template = f"""
      SELECT m.path, m.name, fi.type, fi.parent_path, m.mtime,
             catalog_asset.mtime_ns, catalog_asset.size AS asset_size, catalog_asset.animated AS asset_animated, m.width, m.height,
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
    if preselect is None:
        return template, None, None
    rows_subquery = _preselect_rows_subquery(("metadata_id", "pre_tier", "pre_rank_bin"))
    return (
        template.replace(_PRESELECT_SLOT, preselect),
        preselect,
        template.replace(_PRESELECT_SLOT, rows_subquery),
    )


def _filename_dense_selects(
    *,
    file_type: str,
    fts_table: str,
    match_param: str,
    lo_tier: int,
    has_cursor: bool,
    scope_sql: str = "",
    scope: _ScopeFilter | None = None,
    field_where: str = "",
    preselect_assets: bool = False,
) -> tuple[_Source, ...]:
    """Bounded hi/lo replacements of a filename source whose FTS match set is large.

    ``hi`` holds the exact (100) and prefix (90) filename matches, found by scanning the compact folded names
    with the FTS table as a membership test instead of ranking every match; ``lo`` holds the remaining matches
    ranked by bm25. Both keep only the best ``fts_candidate_limit`` rows after the cursor, ordered like the page
    (tier, rank, mtime, id), before the strict ownership joins run on that handful. The ``mtime_ns`` of the
    ``file_index`` row stands in for the asset's (equal for every row that survives the strict join).

    A scoped or field-filtered source applies the scope (on the preselect's ``pre_fi``) and the field conditions
    (on the file's metadata row, aliased ``m`` as in the strict statement) inside the preselect, so the bound
    keeps the best rows inside the scope and filters.
    """
    if scope_sql and scope is None:
        raise ValueError("a scoped dense source needs its scope filter")
    type_sql = "fi.type IN ('image', 'photo')" if file_type == "image" else "fi.type = 'video'"
    pre_type_sql = type_sql.replace("fi.", "pre_fi.")
    exact = "{alias}.name = :fold_query"
    prefix = "{alias}.name LIKE :fold_filename_prefix ESCAPE '\\'"
    mtime_sql = "pre_fi.mtime_ns"
    # Scope and field filters of the preselect, evaluated right after `pre_fi` (before the other lookups).
    pre_joins = ""
    pre_filters = ""
    if scope is not None:
        pre_filters += scope.sql("pre_fi.path", "pre_fi.library_id", preselect=True)
    if field_where:
        pre_joins += (
            "CROSS JOIN image_metadata AS m ON m.path = pre_fi.path AND "
            + file_index_matches_image_metadata_sql(fi_alias="pre_fi", im_alias="m")
            + " "
        )
        pre_filters += f" AND {field_where}"
    if preselect_assets or "catalog_asset" in field_where:
        pre_joins += (
            _simple_active_asset_join_sql(fi_alias="pre_fi", asset_alias="catalog_asset").replace(
                "JOIN assets", "CROSS JOIN assets", 1
            )
            + " "
        )
    metadata_join = ""
    metadata_values = "'' AS model, '' AS sampler, '' AS seed"
    if field_where:
        metadata_join = f"CROSS JOIN image_metadata m ON m.path = fi.path AND {_CURRENT_METADATA_IDENTITY_SQL}"
        metadata_values = (
            "coalesce(m.model, '') AS model, coalesce(m.sampler, '') AS sampler, coalesce(m.seed, '') AS seed"
        )

    def outer(tier_sql: str, rank_sql: str, match_sql: str) -> str:
        return f"""
      SELECT fi.path, fi.name, fi.type, fi.parent_path, fi.mtime,
             catalog_asset.mtime_ns, catalog_asset.size AS asset_size, catalog_asset.animated AS asset_animated, fi.width, fi.height,
             catalog_asset.duration_ms, catalog_asset.mime_type,
             catalog_asset.id AS asset_id,
             catalog_asset.library_id AS library_id,
             catalog_library.name AS library_name,
             {tier_sql} AS relevance_tier,
             {rank_sql} AS rank,
             {match_sql} AS match_type,
             '' AS prompt_snippet,
             {metadata_values}
      FROM (INNER_SELECT) AS bounded_file_rows
      CROSS JOIN file_index fi ON fi.rowid = bounded_file_rows.file_rowid
      {_active_asset_join_sql()}
      {metadata_join}
      WHERE {type_sql} {scope_sql}
    """

    hi_tier = f"CASE WHEN {exact.format(alias='ff')} THEN 100 ELSE 90 END"
    hi_cursor = (
        _cursor_tuple_sql(
            tier_sql=f"({hi_tier})",
            rank_bin_sql="0",
            mtime_sql=mtime_sql,
            asset_id_sql=_FILE_ASSET_ID_SQL.format(id_sql="pre_fi.rowid"),
        )
        if has_cursor
        else ""
    )
    hi_inner = f"""
        SELECT ff.file_rowid AS file_rowid, {hi_tier} AS pre_tier
        FROM file_index_fold AS ff
        CROSS JOIN file_index AS pre_fi ON pre_fi.rowid = ff.file_rowid
        {pre_joins}
        WHERE ({exact.format(alias="ff")} OR {prefix.format(alias="ff")}) AND {pre_type_sql}
          AND +ff.file_rowid IN (SELECT rowid FROM {fts_table} WHERE {fts_table} MATCH :{match_param})
          {pre_filters}
          {hi_cursor}
        ORDER BY pre_tier DESC, {mtime_sql} DESC, pre_fi.rowid ASC
        LIMIT :fts_candidate_limit
    """
    hi_template = outer(
        "bounded_file_rows.pre_tier",
        "0.0",
        "CASE WHEN bounded_file_rows.pre_tier = 100 THEN 'filename_exact' ELSE 'filename_prefix' END",
    )
    hi_rows = _preselect_rows_subquery(("file_rowid", "pre_tier"))

    lo_rank_bin = f"CAST({fts_table}.rank * 1000000.0 - 0.5 AS INTEGER)"
    if has_cursor:
        lo_cursor = _cursor_tuple_sql(
            tier_sql=str(lo_tier),
            rank_bin_sql="pre_rank_bin",
            mtime_sql="pre_mtime",
            asset_id_sql=_FILE_ASSET_ID_SQL.format(id_sql="file_rowid"),
        )
        lo_inner = f"""
        SELECT file_rowid, pre_rank_bin FROM (
          SELECT {fts_table}.rowid AS file_rowid, {lo_rank_bin} AS pre_rank_bin, {mtime_sql} AS pre_mtime
          FROM {fts_table}
          CROSS JOIN file_index AS pre_fi ON pre_fi.rowid = {fts_table}.rowid
          {pre_joins}
          CROSS JOIN file_index_fold AS pre_ff ON pre_ff.file_rowid = pre_fi.rowid
          WHERE {fts_table} MATCH :{match_param} AND {pre_type_sql}
            {pre_filters}
            AND NOT ({exact.format(alias="pre_ff")} OR {prefix.format(alias="pre_ff")})
          LIMIT -1
        )
        WHERE 1 = 1
          {lo_cursor}
        ORDER BY pre_rank_bin ASC, pre_mtime DESC, file_rowid ASC
        LIMIT :fts_candidate_limit
        """
    else:
        lo_inner = f"""
        SELECT {fts_table}.rowid AS file_rowid, {lo_rank_bin} AS pre_rank_bin
        FROM {fts_table}
        CROSS JOIN file_index AS pre_fi ON pre_fi.rowid = {fts_table}.rowid
        {pre_joins}
        CROSS JOIN file_index_fold AS pre_ff ON pre_ff.file_rowid = pre_fi.rowid
        WHERE {fts_table} MATCH :{match_param} AND {pre_type_sql}
          {pre_filters}
          AND NOT ({exact.format(alias="pre_ff")} OR {prefix.format(alias="pre_ff")})
        ORDER BY pre_rank_bin ASC, {mtime_sql} DESC, pre_fi.rowid ASC
        LIMIT :fts_candidate_limit
        """
    lo_template = outer(str(lo_tier), "(bounded_file_rows.pre_rank_bin / 1000000.0)", "'filename'")
    lo_rows = _preselect_rows_subquery(("file_rowid", "pre_rank_bin"))
    return (
        _Source(
            hi_template.replace("INNER_SELECT", hi_inner),
            kind="file",
            min_tier=90,
            max_tier=100,
            file_type=file_type,
            pre_sql=hi_inner,
            rows_sql=hi_template.replace("INNER_SELECT", hi_rows),
        ),
        _Source(
            lo_template.replace("INNER_SELECT", lo_inner),
            kind="file",
            min_tier=lo_tier,
            max_tier=lo_tier,
            file_type=file_type,
            pre_sql=lo_inner,
            rows_sql=lo_template.replace("INNER_SELECT", lo_rows),
        ),
    )


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
    count_only: bool = False,
    scope: _ScopeFilter | None = None,
    extra_where: str = "",
    preselect_assets: bool = False,
    retry_preselect: bool = False,
) -> list[str]:
    """Candidate SELECTs of one query, each a ``_Source`` that knows its tier range and source kind.

    With ``count_only`` every SELECT yields just ``asset_id`` and skips tier, rank and the bounded preselects,
    which is all the capped distinct count needs. A scoped query (``scope_sql``) is bounded only when it also
    passes its ``scope`` filter, which the preselects evaluate before they cut to the best rows.
    ``extra_where`` adds an ``AND ...`` condition over ``fi`` to the unbounded FTS sources (the page plan's
    shadow check). ``retry_preselect`` attaches to every bounded source its ``retry`` (the preselect also joining
    the active asset).
    """
    if field_only:
        return [
            _Source(
                _metadata_candidate_select(
                    source_kind="field_only",
                    scope_sql=scope_sql,
                    field_where=field_where,
                    fts_table="image_metadata_fts",
                    bounded_field_only=bounded_candidates and not count_only,
                    has_cursor=has_cursor,
                    count_only=count_only,
                ),
                kind="meta",
                min_tier=30,
                max_tier=30,
            )
        ]

    if not include_fts:
        selects = [
            _filename_candidate_select(
                file_type="image",
                query_kind="like",
                scope_sql=scope_sql,
                field_where=field_where,
                count_only=count_only,
            ),
            _metadata_candidate_select(
                source_kind="positive_phrase",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table="image_metadata_fts",
                count_only=count_only,
            ),
            _metadata_candidate_select(
                source_kind="negative_phrase",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table="image_metadata_fts",
                count_only=count_only,
            ),
            _metadata_candidate_select(
                source_kind="metadata_like",
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table="image_metadata_fts",
                count_only=count_only,
            ),
        ]
        if include_videos:
            selects.append(
                _filename_candidate_select(
                    file_type="video",
                    query_kind="like",
                    scope_sql=scope_sql,
                    field_where="",
                    count_only=count_only,
                )
            )
        return selects

    folded_query = fold_text(query)
    use_trigram = _can_use_trigram_candidates(folded_query)
    plan = plan_short_query(folded_query)
    has_cjk_terms = plan is not None and bool(plan.cjk_terms)
    # Latin queries of three or more characters add a lower substring tier below the word-prefix tier.
    # Queries with CJK text keep substring semantics as the primary tier (CJK has no word boundaries).
    substring_secondary = use_trigram and not has_cjk_terms
    short_plan = None if use_trigram else plan
    prompt_table = "image_metadata_fold_fts"
    prompt_cjk_param: str | None = None
    negative_cjk_param: str | None = None
    if short_plan is not None and short_plan.cjk_terms:
        if short_plan.latin_terms:
            prompt_cjk_param, negative_cjk_param = "positive_cjk_match", "negative_cjk_match"
        else:
            prompt_table = CJK_FTS_TABLE
    trigram_table = "image_metadata_fold_fts_trigram"
    bounded_metadata_fts = bounded_candidates and not count_only and (not scope_sql or scope is not None)
    dense_files = bounded_metadata_fts

    def metadata_selects(kind: str, table: str, *, secondary: bool, cjk_param: str | None = None) -> _Source:
        if kind.startswith("positive"):
            low, high = (
                (TIER_SUBSTRING_PROMPT, TIER_SUBSTRING_PROMPT_PHRASE)
                if secondary
                else (TIER_PROMPT, TIER_PROMPT_PHRASE)
            )
        elif kind.startswith("negative"):
            low = high = TIER_SUBSTRING_NEGATIVE if secondary else TIER_NEGATIVE
        else:
            low = high = TIER_SUBSTRING_METADATA if secondary else TIER_PROMPT

        def build(with_assets: bool) -> _Source:
            sql, pre_sql, rows_sql = _metadata_candidate_parts(
                source_kind=kind,
                scope_sql=scope_sql,
                field_where=field_where,
                fts_table=table,
                bounded_fts=bounded_metadata_fts,
                has_cursor=has_cursor,
                cjk_match_param=cjk_param,
                secondary=secondary,
                count_only=count_only,
                scope=scope,
                extra_where=extra_where,
                preselect_assets=with_assets,
            )
            return _Source(sql, kind="meta", min_tier=low, max_tier=high, pre_sql=pre_sql, rows_sql=rows_sql)

        source = build(preselect_assets)
        if retry_preselect and source.pre_sql is not None:
            source.retry = build(True)
        return source

    def file_source(file_type: str, query_kind: str, *, lo_tier: int, field_where_for_type: str) -> _Source:
        fts_table = "file_index_fold_fts_trigram" if query_kind == "trigram" else "file_index_fold_fts"
        match_param = "filename_substring_match" if query_kind == "trigram" else "filename_match"
        dense: tuple[_Source, ...] = ()
        if dense_files:

            def build_dense(with_assets: bool) -> tuple[_Source, ...]:
                return _filename_dense_selects(
                    file_type=file_type,
                    fts_table=fts_table,
                    match_param=match_param,
                    lo_tier=lo_tier,
                    has_cursor=has_cursor,
                    scope_sql=scope_sql,
                    scope=scope,
                    field_where=field_where_for_type,
                    preselect_assets=with_assets,
                )

            dense = build_dense(preselect_assets)
            if retry_preselect:
                for source, retry in zip(dense, build_dense(True), strict=True):
                    source.retry = retry
        return _Source(
            _filename_candidate_select(
                file_type=file_type,
                query_kind=query_kind,
                scope_sql=scope_sql,
                field_where=field_where_for_type,
                substring_tier=lo_tier,
                count_only=count_only,
                extra_where=extra_where,
            ),
            kind="file",
            min_tier=lo_tier,
            max_tier=100,
            dense=dense,
            probe=(fts_table, match_param),
            file_type=file_type,
        )

    selects: list[str] = [file_source("image", "fts", lo_tier=70, field_where_for_type=field_where)]
    if use_trigram and not substring_secondary:
        # CJK-bearing query: the trigram table is the primary (substring) source.
        selects += [
            metadata_selects("positive_trigram", trigram_table, secondary=False),
            metadata_selects("negative_trigram", trigram_table, secondary=False),
            metadata_selects("metadata_trigram", trigram_table, secondary=False),
        ]
    else:
        selects += [
            metadata_selects("positive_fts", prompt_table, secondary=False, cjk_param=prompt_cjk_param),
            metadata_selects("negative_fts", prompt_table, secondary=False, cjk_param=negative_cjk_param),
            metadata_selects("metadata_fts", "image_metadata_fold_fts", secondary=False),
        ]
        if substring_secondary:
            selects += [
                metadata_selects("positive_trigram", trigram_table, secondary=True),
                metadata_selects("negative_trigram", trigram_table, secondary=True),
                metadata_selects("metadata_trigram", trigram_table, secondary=True),
            ]
    if include_videos:
        selects.append(file_source("video", "fts", lo_tier=70, field_where_for_type=""))
    if use_trigram:
        trigram_filename_tier = TIER_SUBSTRING_FILENAME if substring_secondary else 50
        selects.append(file_source("image", "trigram", lo_tier=trigram_filename_tier, field_where_for_type=field_where))
        if include_videos:
            selects.append(file_source("video", "trigram", lo_tier=trigram_filename_tier, field_where_for_type=""))
    return selects


def build_capped_count_query(selects: list[str]) -> str:
    """Count the distinct assets of rank-free ``asset_id`` SELECTs, stopping at ``:count_cap``.

    ``DISTINCT`` streams and the outer ``LIMIT`` ends the scan, so a dense query costs about ``:count_cap``
    strict-ownership probes instead of one per match. Below the cap the count is exact.
    """
    union_sql = "\nUNION ALL\n".join(selects)
    return f"""
      SELECT count(*) AS total
      FROM (
        SELECT DISTINCT asset_id
        FROM (
          {union_sql}
        )
        LIMIT :count_cap
      )
    """


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


@dataclass(frozen=True)
class _ScopeFilter:
    """A search scope as sargable predicates, renderable against any aliases of a candidate source.

    ``root`` selects the paths of a folder (the folder itself or anything under it, matched as the range
    ``[root + sep, root + sep')`` so only whole path components match: ``a1111`` never matches ``a11112``);
    ``library`` selects one library by id (an unknown id, ``None``, matches nothing). ``library_elided`` drops the
    library predicate where it would be a tautology (every file row belongs to that library); it is only ever
    set for the bounded preselects, whose strict outer statement still applies the full predicate.
    """

    root: str | None = None
    lo: str = ""
    hi: str = ""
    library: bool = False
    library_id: int | None = None
    library_elided: bool = False

    @property
    def params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.root is not None:
            params.update(scope_root=self.root, scope_lo=self.lo, scope_hi=self.hi)
        if self.library:
            params["scope_library_id"] = self.library_id
        return params

    def sql(self, path_column: str, library_column: str | None, *, preselect: bool = False) -> str:
        """The ``AND ...`` predicate over the given columns; ``preselect`` honours ``library_elided``."""
        parts: list[str] = []
        if self.root is not None:
            parts.append(
                f" AND ({path_column} = :scope_root OR ({path_column} >= :scope_lo AND {path_column} < :scope_hi))"
            )
        if self.library and library_column is not None and not (preselect and self.library_elided):
            parts.append(f" AND {library_column} = :scope_library_id")
        return "".join(parts)

    def needs_file_index(self) -> bool:
        """Whether a preselect has to join ``file_index`` to evaluate the scope (the library id lives there)."""
        return self.library and not self.library_elided


def _scope_filter(scope: str, root_path: str | Path | None, library_id: int | None) -> _ScopeFilter | None:
    """The scope predicates of a request, or None for an unscoped (all libraries) search."""
    if scope in {"current", "folder"} and root_path is not None:
        resolved = canonicalize_catalog_path(root_path)
        prefix = resolved if resolved.endswith(os.sep) else resolved + os.sep
        lo, hi = prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)
        library = scope == "folder" and library_id is not None
        return _ScopeFilter(root=resolved, lo=lo, hi=hi, library=library, library_id=library_id if library else None)
    if scope == "library":
        return _ScopeFilter(library=True, library_id=library_id)
    return None


def _scope_clause(scope: str, root_path: str | Path | None, library_id: int | None) -> tuple[str, dict[str, Any]]:
    """The strict ``AND ...`` scope predicate over ``fi`` (the file row) and its named parameters."""
    scope_filter = _scope_filter(scope, root_path, library_id)
    if scope_filter is None:
        return "", {}
    return scope_filter.sql("fi.path", "fi.library_id"), scope_filter.params


def _library_covers_every_file(conn: sqlite3.Connection, library_id: int | None) -> bool:
    """Whether no file row belongs to another library (three index probes on ``library_id``)."""
    if library_id is None:
        return False
    row = conn.execute(
        "SELECT NOT (EXISTS (SELECT 1 FROM file_index WHERE library_id < :library_id) "
        "OR EXISTS (SELECT 1 FROM file_index WHERE library_id > :library_id) "
        "OR EXISTS (SELECT 1 FROM file_index WHERE library_id IS NULL))",
        {"library_id": library_id},
    ).fetchone()
    return bool(row[0])


def _field_conditions(
    parsed: ParsedQuery,
    prompt_groups: list[tuple[str, bytes]] | None,
    workflow_groups: list[Any] | None,
    *,
    probe_friendly: bool = False,
) -> tuple[str, dict[str, Any]]:
    """The ``field_``-prefixed WHERE clause and parameters of a fielded query."""
    conditions, raw_params = build_fielded_conditions(
        ParsedQuery(residual_text="", fields=parsed.fields), probe_friendly=probe_friendly
    )
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
    return _prefix_sql_params(field_where, raw_params, "field_")


def _row_key(row: sqlite3.Row) -> tuple[int, float, int, int]:
    """Ascending sort key of the page order: tier desc, rank asc, mtime desc, asset id asc."""
    return (-int(row["relevance_tier"]), float(row["rank"]), -int(row["mtime_ns"]), int(row["asset_id"]))


def _is_after_cursor(row: sqlite3.Row, cursor: dict[str, int | float]) -> bool:
    return _row_key(row) > (
        -int(cursor["tier"]),
        float(cursor["rank"]),
        -int(cursor["mtime_ns"]),
        int(cursor["asset_id"]),
    )


def _cursor_key(cursor: dict[str, int | float]) -> tuple[int, float, int, int]:
    """The cursor in the ascending sort key of the page order (see ``_row_key``)."""
    return (-int(cursor["tier"]), float(cursor["rank"]), -int(cursor["mtime_ns"]), int(cursor["asset_id"]))


def _read_search_generation(conn: sqlite3.Connection) -> tuple[str, int] | None:
    """The database's (epoch, search generation), or None when it has none (cache off)."""
    try:
        row = conn.execute("SELECT epoch, value FROM search_generation WHERE id = 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return None if row is None else (str(row[0]), int(row[1]))


class _WindowSession:
    """One request's view of the ranked-window cache (BL-15).

    A bounded source keeps the rows it read after a cursor (``bound``): every row of the source after the bound
    that sorts strictly before the last of them is in the list. A later keyset page whose cursor lies at or after
    the bound filters that list instead of ranking the FTS match set again. ``generation`` was read from the
    database before any data of this request, so an entry stored under it can only be too old to serve, never
    newer than the data it was read from.

    Only keyset pages (a cursor) are served from the cache; the first page always reads its sources and
    refreshes their entries. The caller reruns a plan that used the cache and gave up, with ``serve`` off.
    """

    def __init__(
        self, cache: SearchWindowCache, epoch: str, generation: int, scope_key: tuple[Any, ...], *, serve: bool
    ) -> None:
        self.cache = cache
        self.epoch = epoch
        self.generation = generation
        self.scope_key = scope_key
        self.serve = serve
        self.hits = 0

    def _key(self, source_key: tuple[Any, ...]) -> tuple[Any, ...]:
        return (self.epoch, self.scope_key, source_key)

    def lookup(
        self, source_key: tuple[Any, ...], cursor_position: dict[str, int | float] | None
    ) -> tuple[list[sqlite3.Row], tuple[int, float, int] | None] | None:
        """The cached rows of a source after the cursor and its cover, or None when the cache cannot answer."""
        if not self.serve or cursor_position is None:
            return None
        entry = self.cache.get(self._key(source_key), self.generation)
        if entry is None:
            return None
        cursor_key = _cursor_key(cursor_position)
        if entry.bound is not None and cursor_key < entry.bound:
            return None  # the list starts after this cursor
        rows = [row for row in entry.rows if _row_key(row) > cursor_key]
        if entry.cut_short and not rows:
            return None  # the cursor is past the cached list: only a read can tell what follows
        self.hits += 1
        return rows, entry.cover  # type: ignore[return-value]

    def store(
        self,
        source_key: tuple[Any, ...],
        cursor_position: dict[str, int | float] | None,
        rows: list[sqlite3.Row],
        *,
        cut_short: bool,
    ) -> None:
        """Keep the rows a source just read after ``cursor_position`` (its surviving rows, before the cursor test)."""
        cover = max(_row_key(row) for row in rows)[:3] if rows and cut_short else None
        self.cache.put(
            self._key(source_key),
            WindowEntry(
                generation=self.generation,
                bound=None if cursor_position is None else _cursor_key(cursor_position),
                rows=tuple(rows),
                cut_short=cut_short,
                cover=cover,
                size=estimate_rows_size(rows),
            ),
        )


def _open_window(conn: sqlite3.Connection, scope_key: tuple[Any, ...], *, serve: bool) -> _WindowSession | None:
    """The request's window session, or None when the cache is off or the database has no search generation."""
    cache = SEARCH_WINDOW_CACHE
    if not cache.enabled:
        return None
    generation = _read_search_generation(conn)
    if generation is None:
        return None
    return _WindowSession(cache, generation[0], generation[1], scope_key, serve=serve)


def _file_source_is_small(conn: sqlite3.Connection, source: _Source, params: dict[str, Any]) -> bool:
    """Whether a filename source matches few enough FTS rows to read whole (a rank-free, early-exit probe)."""
    assert source.probe is not None
    table, match_param = source.probe
    row = conn.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {table} MATCH :match LIMIT {FILE_SOURCE_SMALL_LIMIT + 1})",
        {"match": params[match_param]},
    ).fetchone()
    return int(row[0]) <= FILE_SOURCE_SMALL_LIMIT


def _plan_sources(
    conn: sqlite3.Connection, selects: list[_Source], params: dict[str, Any]
) -> list[tuple[int, _Source]]:
    """Resolve each filename source into itself (small match set) or its bounded hi/lo variants (large one).

    Each entry carries the position of the source in ``selects``, so the exact plan can pair it with the
    unbounded statement of the same source.
    """
    has_videos: bool | None = None
    planned: list[tuple[int, _Source]] = []
    for position, source in enumerate(selects):
        if source.kind != "file":
            planned.append((position, source))
            continue
        if source.file_type == "video":
            if has_videos is None:
                has_videos = (
                    conn.execute("SELECT EXISTS (SELECT 1 FROM file_index WHERE type = 'video')").fetchone()[0] == 1
                )
            if not has_videos:
                continue
        if source.dense and not _file_source_is_small(conn, source, params):
            planned.extend((position, dense) for dense in source.dense)
        else:
            planned.append((position, source))
    return planned


# The condition the exact plan's shadow check adds to a source: only the candidate assets (by path).
SHADOW_PATHS_WHERE = " AND fi.path IN (SELECT value FROM json_each(:shadow_paths))"


def _read_preselected(
    conn: sqlite3.Connection,
    source: _Source,
    params: dict[str, Any],
    cursor_position: dict[str, int | float] | None,
    covers: list[tuple[int, float, int]],
    window: _WindowSession | None = None,
    window_key: tuple[Any, ...] = (),
) -> list[sqlite3.Row] | None:
    """Rows of a bounded source after the cursor, or None when the bound may have dropped valid rows.

    The preselect runs on its own (the best ``fts_candidate_limit`` rows inside the scope and filters), then the
    strict ownership statement reads exactly those rows. A preselect that was cut short (it returned the limit)
    and lost rows to the strict joins (offline, mismatched or unowned assets) may have hidden valid rows beyond
    the limit; that is None. A cut-short preselect with no losses records its ``cover``: the (tier, rank, mtime)
    prefix of its last row. The source is known complete only strictly before that prefix: the preselect breaks
    ties by its own row id (metadata or file rowid), not the page's asset id, so rows that tie the last one on
    tier, rank and mtime may have been cut while sorting before rows that were kept.
    """
    assert source.pre_sql is not None and source.rows_sql is not None
    if cursor_position is not None and source.min_tier > int(cursor_position["tier"]):
        return []  # every row ranks before the cursor
    if window is not None:
        cached = window.lookup(window_key, cursor_position)
        if cached is not None:
            rows, cover = cached
            if cover is not None:
                covers.append(cover)
            return rows
    pre_rows = conn.execute(source.pre_sql, params).fetchall()
    if not pre_rows:
        if window is not None:
            window.store(window_key, cursor_position, [], cut_short=False)
        return []
    survivors = conn.execute(
        source.rows_sql, {**params, _PRESELECT_ROWS_PARAM: json.dumps([list(row) for row in pre_rows])}
    ).fetchall()
    rows = (
        survivors if cursor_position is None else [row for row in survivors if _is_after_cursor(row, cursor_position)]
    )
    cut_short = len(pre_rows) >= int(params["fts_candidate_limit"])
    if cut_short and (len(survivors) < len(pre_rows) or not rows):
        return None
    if window is not None:
        window.store(window_key, cursor_position, survivors, cut_short=cut_short)
    if cut_short:
        covers.append(max(_row_key(row) for row in rows)[:3])
    return rows


def _exact_or_prefix_paths(conn: sqlite3.Connection, paths: list[str], params: dict[str, Any]) -> list[str]:
    """The paths whose folded file name equals the query or starts with it (the filename tiers 100 and 90)."""
    rows = conn.execute(
        "SELECT fi.path FROM file_index AS fi JOIN file_index_fold AS ff ON ff.file_rowid = fi.rowid "
        "WHERE fi.path IN (SELECT value FROM json_each(:shadow_paths)) "
        "AND (ff.name = :fold_query OR ff.name LIKE :fold_filename_prefix ESCAPE '\\')",
        {
            "shadow_paths": json.dumps(paths),
            "fold_query": params["fold_query"],
            "fold_filename_prefix": params["fold_filename_prefix"],
        },
    ).fetchall()
    return [str(row[0]) for row in rows]


def _run_page_plan(
    conn: sqlite3.Connection,
    selects: list[_Source],
    params: dict[str, Any],
    *,
    page_limit: int,
    row_limit: int,
    cursor_position: dict[str, int | float] | None,
    shadow_selects: Callable[[], list[_Source]] | None = None,
    window: _WindowSession | None = None,
) -> list[sqlite3.Row] | None:
    """Return one page by reading the candidate sources from the highest tier down.

    Every source is a complete SELECT of the old single-statement plan; the planner only decides which ones
    to run and merges their rows exactly as the statement did (best row per asset, then cursor, then order).
    Each source yields all of its bounded candidate rows (at most ``row_limit``): a row shadowed by a better
    row of the same asset must not cost the page a slot. A source whose rows all rank below a full page is
    never run, so ``a``/``m``/``c`` are served from the prompt-phrase tier without ranking every filename and
    model match.

    ``shadow_selects`` switches on the exact plan (scoped and field-filtered queries, whose pre-plan answer was
    the exact single statement). The page then equals that statement's page:

    * on a keyset page, an asset that also has a row at or before the cursor in a source whose bounded rows were
      pre-filtered by the cursor is dropped (the single statement dedups before it applies the cursor), found by
      reading only the candidate assets' paths out of the unbounded statements of the sources that can hold
      such a row (their ``max_tier`` reaches the cursor's tier);
    * a bounded source that was cut short is read through ``_read_preselected``, and the page must lie inside
      the range every cut-short source covers, else the plan gives up (None) and the caller runs the exact
      statement. A page never silently drops, or repeats, a match.

    Both plans cover a cut-short bounded source the same way. ``window`` lets a keyset page take a bounded
    source's rows from the ranked-window cache instead of ranking its match set again (see ``_WindowSession``);
    a cached source's cover is the cache's, which never reaches further than a read's, so a page the cache cannot
    guarantee gives up (None) and the caller runs the plan again without the cache.
    """
    exact = shadow_selects is not None
    placed = sorted(_plan_sources(conn, selects, params), key=lambda item: -item[1].max_tier)
    absent = set(range(len(selects))) - {position for position, _source in placed}  # e.g. videos of a library without
    has_cursor = cursor_position is not None
    best: dict[int, sqlite3.Row] = {}
    origin: dict[int, set[int]] = {}  # asset id -> positions of the sources that returned a row for it
    whole: set[int] = set()  # positions read whole: their rows were never cursor-filtered
    covers: list[tuple[int, float, int]] = []
    excluded: set[int] = set()
    checked: set[int] = set()
    shadow_sources: list[_Source] | None = None

    def shadowed(pending: list[sqlite3.Row]) -> set[int]:
        nonlocal shadow_sources
        assert cursor_position is not None and shadow_selects is not None
        if shadow_sources is None:
            shadow_sources = shadow_selects()
        cursor_tier = int(cursor_position["tier"])
        before_cursor = _candidate_cursor_sql(
            tier_sql="relevance_tier", rank_sql="rank", mtime_sql="mtime_ns", asset_id_sql="asset_id"
        )
        found: set[int] = set()
        for position, source in enumerate(shadow_sources):
            if position in whole or position in absent or source.max_tier < cursor_tier:
                continue
            paths = [str(row["path"]) for row in pending if origin[int(row["asset_id"])] - {position}]
            if paths and source.probe is not None and cursor_tier > source.min_tier:
                # A filename source ranks a file at its exact (100) or prefix (90) tier, else at `min_tier`, below
                # the cursor: only files whose folded name is an exact or prefix match can sit before it.
                paths = _exact_or_prefix_paths(conn, paths, params)
            if not paths:
                continue
            rows = conn.execute(
                f"SELECT DISTINCT asset_id FROM ({source}) WHERE NOT (1 = 1 {before_cursor})",
                {**params, "shadow_paths": json.dumps(paths)},
            ).fetchall()
            found.update(int(row[0]) for row in rows)
        checked.update(int(row["asset_id"]) for row in pending)
        return found

    def page_rows() -> list[sqlite3.Row]:
        rows = [row for asset_id, row in best.items() if asset_id not in excluded]
        if cursor_position is not None:
            rows = [row for row in rows if _is_after_cursor(row, cursor_position)]
        return sorted(rows, key=_row_key)[:page_limit]

    def settled_page() -> list[sqlite3.Row]:
        while True:
            page = page_rows()
            if not (exact and has_cursor):
                return page
            pending = [row for row in page if int(row["asset_id"]) not in checked]
            if not pending:
                return page
            excluded.update(shadowed(pending))

    index = 0
    page: list[sqlite3.Row] = []
    while index < len(placed):
        tier = placed[index][1].max_tier
        group: list[tuple[int, _Source]] = []
        while index < len(placed) and placed[index][1].max_tier == tier:
            group.append(placed[index])
            index += 1
        for position, source in group:
            if source.probe is not None:
                # A filename source read whole (small match set): its rows reach the dedup unfiltered, so they
                # shadow lower-tier rows of the same asset even before the cursor, as the old statement let them.
                rows = conn.execute(str(source), params).fetchall()
                whole.add(position)
            elif exact and source.pre_sql is not None:
                window_key = (position, source.min_tier, source.max_tier)
                read = _read_preselected(conn, source, params, cursor_position, covers, window, window_key)
                if read is None and source.retry is not None:
                    read = _read_preselected(
                        conn, source.retry, params, cursor_position, covers, window, (*window_key, "retry")
                    )
                if read is None:
                    return None
                rows = read
            else:
                if cursor_position is not None and source.min_tier > int(cursor_position["tier"]):
                    continue  # every row ranks before the cursor
                window_key = (position, source.min_tier, source.max_tier)
                cached = None if exact or window is None else window.lookup(window_key, cursor_position)
                if cached is not None:
                    rows, cover = cached
                    if cover is not None:
                        covers.append(cover)
                else:
                    rows = conn.execute(
                        build_candidate_page_query([source], has_cursor=has_cursor, legacy_offset=False),
                        {**params, "page_limit": row_limit},
                    ).fetchall()
                    # A bounded source that returned a full bound may have been cut short (BL-16): it is complete
                    # only strictly before the (tier, rank, mtime) of its last row, as in `_read_preselected`.
                    cut_short = len(rows) >= row_limit
                    if cut_short and not exact:
                        covers.append(max(_row_key(row) for row in rows)[:3])
                        if window is not None:
                            # Only a full bound is cached: a shorter list is either the whole (cheap) match set or a
                            # cut-short preselect that lost rows to the strict joins, which this single statement
                            # cannot tell apart, and a lossy list must never be served as complete.
                            window.store(window_key, cursor_position, rows, cut_short=True)
            for row in rows:
                asset_id = int(row["asset_id"])
                origin.setdefault(asset_id, set()).add(position)
                held = best.get(asset_id)
                if held is None or _row_key(row) < _row_key(held):
                    best[asset_id] = row
        page = settled_page()
        if index >= len(placed):
            break
        if len(page) == page_limit and int(page[-1]["relevance_tier"]) > placed[index][1].max_tier:
            break
    # Every cut-short source holds all of its valid rows strictly before its cover: the page must end there.
    if covers and (len(page) < page_limit or any(_row_key(page[-1])[:3] >= cover for cover in covers)):
        return None
    return page


def _field_only_rows(
    conn: sqlite3.Connection,
    *,
    scope_sql: str,
    field_where: str,
    probe_field_where: str,
    params: dict[str, Any],
    cursor_position: dict[str, int | float] | None,
    candidate_limit: int,
) -> list[sqlite3.Row]:
    """Field-only page: an ordered probe of the newest rows first, the sorting plan when the probe falls short.

    All field-only rows share tier 30 and rank 0, so the page order is just ``mtime_ns DESC, asset id ASC``.
    The probe walks ``image_metadata`` newest first through its mtime index and stops at ``candidate_limit``
    matches, so a dense filter (``prompt:c``) touches a few hundred rows instead of sorting every match.
    A filter too sparse for the probe (fewer matches than wanted inside its row budget) uses the original plan.
    """
    probe_ids = _probe_field_only_ids(
        conn,
        scope_sql=scope_sql,
        probe_field_where=probe_field_where,
        params=params,
        cursor_position=cursor_position,
        candidate_limit=candidate_limit,
    )
    if probe_ids is not None:
        params["field_probe_ids"] = json.dumps(probe_ids)
        selects = [
            _Source(
                _metadata_candidate_select(
                    source_kind="field_only",
                    scope_sql=scope_sql,
                    field_where=field_where,
                    fts_table="image_metadata_fts",
                    preselected_ids=True,
                ),
                kind="meta",
                min_tier=30,
                max_tier=30,
            )
        ]
    else:
        selects = _candidate_selects(
            "",
            scope_sql,
            include_fts=False,
            field_where=field_where,
            include_videos=False,
            field_only=True,
            bounded_candidates=True,
            has_cursor=cursor_position is not None,
        )
    return list(
        conn.execute(
            build_candidate_page_query(selects, has_cursor=cursor_position is not None, legacy_offset=False),
            params,
        )
    )


def _probe_field_only_ids(
    conn: sqlite3.Connection,
    *,
    scope_sql: str,
    probe_field_where: str,
    params: dict[str, Any],
    cursor_position: dict[str, int | float] | None,
    candidate_limit: int,
) -> list[int] | None:
    """``image_metadata`` ids of the first ``candidate_limit`` field matches in page order, or None."""
    mtime = _METADATA_MTIME_SQL.format(alias="m")
    probe_rows = max(2048, FIELD_PROBE_ROWS_PER_CANDIDATE * candidate_limit)
    cursor_bound = ""
    cursor_clause = ""
    bound_params: dict[str, Any] = {"probe_rows": probe_rows}
    if cursor_position is not None:
        cursor_clause = _candidate_cursor_sql(
            tier_sql="30", rank_sql="0.0", mtime_sql="catalog_asset.mtime_ns", asset_id_sql="catalog_asset.id"
        )
        if int(cursor_position["tier"]) == 30 and float(cursor_position["rank"]) == 0.0:
            cursor_bound = f"AND {mtime} <= :cursor_mtime_ns"
            bound_params["cursor_mtime_ns"] = params["cursor_mtime_ns"]
    try:
        floor_row = conn.execute(
            f"""
            SELECT {mtime} FROM image_metadata AS m INDEXED BY idx_image_metadata_inspector_date
            WHERE 1 = 1 {cursor_bound}
            ORDER BY {mtime} DESC
            LIMIT 1 OFFSET :probe_rows
            """,
            bound_params,
        ).fetchone()
        floor_clause = ""
        probe_params = dict(params)
        if floor_row is not None:
            floor_clause = f"AND {mtime} >= :probe_floor"
            probe_params["probe_floor"] = floor_row[0]
        ids = [
            int(row[0])
            for row in conn.execute(
                f"""
                SELECT m.id
                FROM image_metadata AS m INDEXED BY idx_image_metadata_inspector_date
                CROSS JOIN file_index AS fi ON fi.path = m.path
                CROSS JOIN assets AS catalog_asset ON catalog_asset.library_id = fi.library_id
                  AND catalog_asset.path = fi.path AND catalog_asset.offline = 0
                  AND catalog_asset.deleted_at IS NULL AND catalog_asset.mtime_ns IS NOT NULL
                WHERE 1 = 1 {floor_clause} {cursor_bound} {scope_sql} AND {probe_field_where} {cursor_clause}
                ORDER BY {mtime} DESC, catalog_asset.id ASC
                LIMIT :field_candidate_limit
                """,
                probe_params,
            )
        ]
    except sqlite3.OperationalError:
        return None
    if len(ids) >= candidate_limit or floor_row is None:
        return ids
    return None


def _probe_field_only_count(
    conn: sqlite3.Connection,
    *,
    scope_sql: str,
    probe_field_where: str,
    params: dict[str, Any],
) -> int | None:
    """Count a field-only query row by row over the first ``COUNT_PROBE_ROWS`` metadata rows, or None.

    A dense filter reaches the cap after a few thousand rows without building the set of every match (a
    ``name:`` set holds a path string per match). The answer is final when the cap is reached or the probe
    covered every metadata row; a filter too sparse for that falls back to the set-driven count.
    """
    bound_row = conn.execute(
        "SELECT id FROM image_metadata ORDER BY id LIMIT 1 OFFSET :probe_rows", {"probe_rows": COUNT_PROBE_ROWS}
    ).fetchone()
    probe_params = dict(params)
    bounded_scope = scope_sql
    if bound_row is not None:
        probe_params["count_probe_hi"] = int(bound_row[0])
        bounded_scope = f"{scope_sql} AND m.id < :count_probe_hi"
    selects = _candidate_selects(
        "",
        bounded_scope,
        include_fts=False,
        field_where=probe_field_where,
        include_videos=False,
        field_only=True,
        count_only=True,
    )
    total = int(conn.execute(build_capped_count_query(selects), probe_params).fetchone()["total"])
    return total if bound_row is None or total >= COUNT_CAP else None


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
    scope_sql, scope_params = _scope_clause(scope, root_path, library_id)
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
    probe_field_where = ""
    field_params: dict[str, Any] = {}
    if parsed is not None:
        field_where, field_params = _field_conditions(parsed, prompt_groups, workflow_groups)
        probe_field_where, _probe_params = _field_conditions(
            parsed, prompt_groups, workflow_groups, probe_friendly=True
        )

    params: dict[str, Any] = {
        "page_limit": limit + 1,
        **_text_match_params(residual),
        **scope_params,
        **field_params,
    }
    if cursor_position is not None:
        params.update(
            {
                "cursor_tier": cursor_position["tier"],
                "cursor_rank": cursor_position["rank"],
                "cursor_rank_bin": round(float(cursor_position["rank"]) * 1_000_000),
                "cursor_mtime_ns": cursor_position["mtime_ns"],
                "cursor_asset_id": cursor_position["asset_id"],
            }
        )
    if legacy_offset is not None:
        params["legacy_offset"] = legacy_offset

    field_only = parsed is not None and not residual
    include_videos = parsed is None
    bounded_candidates = legacy_offset is None
    candidate_limit = max(FTS_CANDIDATE_FLOOR, (limit + 1) * 4)
    params["fts_candidate_limit"] = candidate_limit
    params["field_candidate_limit"] = candidate_limit
    exact_plan = bool(scope_sql or field_where)
    try:
        if field_only and bounded_candidates:
            rows = _field_only_rows(
                conn,
                scope_sql=scope_sql,
                field_where=field_where,
                probe_field_where=probe_field_where,
                params=params,
                cursor_position=cursor_position,
                candidate_limit=candidate_limit,
            )
        else:
            rows = None
            if bounded_candidates and not field_only:
                scope_filter = _scope_filter(scope, root_path, library_id)
                if (
                    scope_filter is not None
                    and scope_filter.library
                    and _library_covers_every_file(conn, scope_filter.library_id)
                ):
                    scope_filter = replace(scope_filter, library_elided=True)
                selects = _candidate_selects(
                    residual,
                    scope_sql,
                    include_fts=True,
                    field_where=field_where,
                    include_videos=include_videos,
                    bounded_candidates=True,
                    has_cursor=cursor_position is not None,
                    scope=scope_filter,
                    retry_preselect=exact_plan,
                )
                window = None
                if parsed is None or not (parsed.fields or prompt_groups or workflow_groups):
                    window = _open_window(
                        conn,
                        (fingerprint, candidate_limit, include_videos, exact_plan),
                        serve=cursor_position is not None,
                    )

                def plan(used_window: _WindowSession | None) -> list[sqlite3.Row] | None:
                    return _run_page_plan(
                        conn,
                        selects,  # type: ignore[arg-type]
                        params,
                        page_limit=limit + 1,
                        row_limit=candidate_limit,
                        cursor_position=cursor_position,
                        shadow_selects=(
                            lambda: _candidate_selects(  # type: ignore[return-value]
                                residual,
                                scope_sql,
                                include_fts=True,
                                field_where=field_where,
                                include_videos=include_videos,
                                has_cursor=cursor_position is not None,
                                extra_where=SHADOW_PATHS_WHERE,
                            )
                        )
                        if exact_plan
                        else None,
                        window=used_window,
                    )

                rows = plan(window)
                if rows is None and window is not None and window.hits:
                    # The cached windows could not guarantee this page: rank the sources again, as without a cache.
                    window.serve = False
                    rows = plan(window)
            if rows is None:
                # Legacy offsets, field-only queries, and any scoped or field-filtered page the bounded plan
                # could not guarantee: the exact single statement over every source.
                selects = _candidate_selects(
                    residual,
                    scope_sql,
                    include_fts=not field_only,
                    field_where=field_where,
                    include_videos=include_videos,
                    field_only=field_only,
                    bounded_candidates=bounded_candidates and field_only,
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


def search_ranked_media_count(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    *,
    parsed: ParsedQuery | None = None,
    library_id: int | None = None,
    prompt_groups: list[tuple[str, bytes]] | None = None,
    workflow_groups: list[Any] | None = None,
) -> int:
    """Return the number of distinct matching assets, counted up to ``COUNT_CAP``.

    The count reads the same sources as the page but needs no tier, rank or ordering, so it streams
    rank-free candidates through ``DISTINCT`` and stops at the cap: below it the total equals the paged
    total, above it the caller shows the ``+`` convention. A plain-text query counts like the plain search
    (videos included).
    """
    if parsed is not None and not parsed.fields and not prompt_groups and not workflow_groups:
        parsed = None
    scope_sql, scope_params = _scope_clause(scope, root_path, library_id)
    residual = parsed.residual_text.strip() if parsed is not None else query.strip()

    field_where = ""
    field_params: dict[str, Any] = {}
    if parsed is not None:
        field_where, field_params = _field_conditions(parsed, prompt_groups, workflow_groups)

    params: dict[str, Any] = {
        **_text_match_params(residual),
        **scope_params,
        **field_params,
        "count_cap": COUNT_CAP,
    }

    field_only = parsed is not None and not residual
    include_videos = parsed is None
    if field_only and parsed is not None:
        probed = _probe_field_only_count(
            conn,
            scope_sql=scope_sql,
            probe_field_where=_field_conditions(parsed, prompt_groups, workflow_groups, probe_friendly=True)[0],
            params=params,
        )
        if probed is not None:
            return probed
    try:
        selects = _candidate_selects(
            residual,
            scope_sql,
            include_fts=not field_only,
            field_where=field_where,
            include_videos=include_videos,
            field_only=field_only,
            count_only=True,
        )
        row = conn.execute(build_capped_count_query(selects), params).fetchone()
        return int(row["total"]) if row else 0
    except sqlite3.OperationalError:
        if field_only:
            raise
        selects = _candidate_selects(
            residual,
            scope_sql,
            include_fts=False,
            field_where=field_where,
            include_videos=include_videos,
            count_only=True,
        )
        row = conn.execute(build_capped_count_query(selects), params).fetchone()
        return int(row["total"]) if row else 0


def is_first_search_page(cursor: str | int | None) -> bool:
    """Return whether album suggestions may be included for this request."""
    return cursor is None or cursor == 0 or cursor == "0"
