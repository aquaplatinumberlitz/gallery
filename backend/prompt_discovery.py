"""Normalized prompt usage, exact prompt groups, and observed model aliases."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Literal

from .metadata_store._db import _DB_LOCK, _connect
from .metadata_store._schema import initialize_database
from .metadata_store.path_utils import canonicalize_catalog_path, named_path_scope_sql

PROMPT_EXTRACTOR_VERSION = 1
PROMPT_CURSOR_VERSION = 1


def normalize_discovery_text(value: str) -> tuple[str, str]:
    """Return fixed NFKC/collapsed display normalization and casefolded search text."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    return normalized, normalized.casefold()


def prompt_value_hash(kind: str, search_text: str) -> bytes:
    """Return the stable kind-separated prompt identity digest."""
    return hashlib.sha256(f"{kind}\0{search_text}".encode()).digest()


def encode_prompt_value_id(value_hash: bytes) -> str:
    """Encode a SHA-256 prompt digest as an unpadded base64url identity."""
    return base64.urlsafe_b64encode(value_hash).decode("ascii").rstrip("=")


def decode_prompt_value_id(value_id: str) -> bytes:
    """Validate and decode one public prompt group identity."""
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", value_id) is None:
        raise ValueError("Invalid prompt value id")
    try:
        decoded = base64.urlsafe_b64decode(value_id + "=")
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid prompt value id") from exc
    if len(decoded) != 32:
        raise ValueError("Invalid prompt value id")
    return decoded


def _clean_identity(value: Any) -> tuple[str, str]:
    if value is None:
        return "", ""
    display, normalized = normalize_discovery_text(str(value))
    return display, normalized


def _metadata_source(asset: dict[str, Any]) -> dict[str, Any] | None:
    """Read only persisted metadata/resource rows; never reopen the media file."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        metadata = conn.execute(
            """
            SELECT prompt, negative_prompt, model, model_hash
            FROM image_metadata
            WHERE path = ?
            """,
            (str(asset["path"]),),
        ).fetchone()
        resources = conn.execute(
            """
            SELECT kind, name, hash, resource_hash
            FROM image_resources
            WHERE path = ? AND lower(kind) IN ('checkpoint', 'model')
            ORDER BY id
            """,
            (str(asset["path"]),),
        ).fetchall()
    if metadata is None and not resources:
        return None
    return {"metadata": dict(metadata) if metadata is not None else {}, "resources": [dict(row) for row in resources]}


def _identity_rows(source: dict[str, Any]) -> list[dict[str, str]]:
    metadata = source["metadata"]
    candidates: list[tuple[str, str]] = []
    model_name, normalized_model_name = _clean_identity(metadata.get("model"))
    model_hash, normalized_model_hash = _clean_identity(metadata.get("model_hash"))
    if normalized_model_name and normalized_model_hash:
        candidates.append((model_name, model_hash))
    for resource in source["resources"]:
        display_name, normalized_name = _clean_identity(resource.get("name"))
        display_hash, normalized_hash = _clean_identity(resource.get("resource_hash") or resource.get("hash"))
        if normalized_name and normalized_hash:
            candidates.append((display_name, display_hash))
        elif normalized_model_name and normalized_hash:
            candidates.append((model_name, display_hash))
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for display_name, display_hash in candidates:
        _, normalized_name = _clean_identity(display_name)
        _, normalized_hash = _clean_identity(display_hash)
        if normalized_name and normalized_hash:
            rows[(normalized_name, normalized_hash)] = {
                "normalized_name": normalized_name,
                "normalized_hash": normalized_hash,
                "display_name": display_name,
                "display_hash": display_hash,
            }
    return [rows[key] for key in sorted(rows)]


def extract_prompt_discovery(asset: dict[str, Any]):  # noqa: ANN201
    """Build normalized derived rows from the existing metadata database."""
    from .search_indexer import SearchExtractionResult

    source = _metadata_source(asset)
    if source is None:
        return SearchExtractionResult(status="not_applicable", payload={"prompts": [], "identities": []})
    prompts: list[dict[str, Any]] = []
    for kind, column in (("positive", "prompt"), ("negative", "negative_prompt")):
        raw = source["metadata"].get(column)
        if raw is None:
            continue
        display_text, search_text = normalize_discovery_text(str(raw))
        if not search_text:
            continue
        prompts.append(
            {
                "kind": kind,
                "display_text": display_text,
                "normalized_text": display_text,
                "search_text": search_text,
                "value_hash": prompt_value_hash(kind, search_text),
            }
        )
    payload = {"prompts": prompts, "identities": _identity_rows(source)}
    status = "ready" if prompts else "not_applicable"
    return SearchExtractionResult(status=status, payload=payload)


def _refresh_model_alias(conn: sqlite3.Connection, normalized_name: str, normalized_hash: str) -> None:
    row = conn.execute(
        """
        WITH active AS (
          SELECT value.display_name, value.display_hash, asset.mtime_ns, asset.id
          FROM asset_model_identity_values AS value
          JOIN assets AS asset ON asset.id = value.asset_id
          WHERE value.normalized_name = ? AND value.normalized_hash = ?
            AND asset.offline = 0 AND asset.deleted_at IS NULL
        )
        SELECT
          (SELECT display_name FROM active ORDER BY mtime_ns DESC, id DESC LIMIT 1) AS display_name,
          (SELECT display_hash FROM active ORDER BY mtime_ns DESC, id DESC LIMIT 1) AS display_hash,
          count(*) AS asset_count,
          max(coalesce(mtime_ns, 0)) AS last_seen_mtime_ns
        FROM active
        HAVING count(*) > 0
        """,
        (normalized_name, normalized_hash),
    ).fetchone()
    if row is None:
        conn.execute(
            "DELETE FROM model_identity_aliases WHERE normalized_name = ? AND normalized_hash = ?",
            (normalized_name, normalized_hash),
        )
        return
    conn.execute(
        """
        INSERT INTO model_identity_aliases (
          normalized_name, normalized_hash, display_name, display_hash,
          asset_count, last_seen_mtime_ns
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_name, normalized_hash) DO UPDATE SET
          display_name = excluded.display_name,
          display_hash = excluded.display_hash,
          asset_count = excluded.asset_count,
          last_seen_mtime_ns = excluded.last_seen_mtime_ns
        """,
        (
            normalized_name,
            normalized_hash,
            str(row["display_name"]),
            str(row["display_hash"]),
            int(row["asset_count"]),
            int(row["last_seen_mtime_ns"]),
        ),
    )


def persist_prompt_discovery(conn: sqlite3.Connection, asset: dict[str, Any], payload: dict[str, Any]) -> None:
    """Atomically replace one asset's prompt/model rows and touched aliases."""
    asset_id = int(asset["id"])
    fingerprint = f"{int(asset.get('mtime_ns') or 0)}:{int(asset.get('size') or 0)}"
    old_pairs = {
        (str(row["normalized_name"]), str(row["normalized_hash"]))
        for row in conn.execute(
            "SELECT normalized_name, normalized_hash FROM asset_model_identity_values WHERE asset_id = ?",
            (asset_id,),
        )
    }
    conn.execute("DELETE FROM asset_prompt_values WHERE asset_id = ?", (asset_id,))
    conn.execute("DELETE FROM asset_model_identity_values WHERE asset_id = ?", (asset_id,))
    conn.executemany(
        """
        INSERT INTO asset_prompt_values (
          asset_id, kind, display_text, normalized_text, search_text, value_hash,
          extractor_version, source_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                asset_id,
                row["kind"],
                row["display_text"],
                row["normalized_text"],
                row["search_text"],
                row["value_hash"],
                PROMPT_EXTRACTOR_VERSION,
                fingerprint,
            )
            for row in payload.get("prompts", [])
        ),
    )
    identities = payload.get("identities", [])
    conn.executemany(
        """
        INSERT INTO asset_model_identity_values (
          asset_id, normalized_name, normalized_hash, display_name, display_hash, source_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                asset_id,
                row["normalized_name"],
                row["normalized_hash"],
                row["display_name"],
                row["display_hash"],
                fingerprint,
            )
            for row in identities
        ),
    )
    new_pairs = {(str(row["normalized_name"]), str(row["normalized_hash"])) for row in identities}
    for normalized_name, normalized_hash in sorted(old_pairs | new_pairs):
        _refresh_model_alias(conn, normalized_name, normalized_hash)


def _prompt_usage_fingerprint(
    *,
    polarity: str,
    scope: str,
    root_path: str | Path | None,
    library_id: int | None,
    prefix: str | None,
    text_query: str | None,
    sort: str,
) -> str:
    payload = {
        "library_id": library_id,
        "polarity": polarity,
        "prefix": prefix,
        "root": canonicalize_catalog_path(root_path) if root_path is not None else None,
        "scope": scope,
        "sort": sort,
        "text": text_query,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _encode_usage_cursor(row: sqlite3.Row, fingerprint: str, sort: str) -> str:
    payload = {
        "asset_count": int(row["asset_count"]),
        "fingerprint": fingerprint,
        "last": int(row["last_asset_mtime_ns"]),
        "sort": sort,
        "value_id": encode_prompt_value_id(bytes(row["value_hash"])),
        "version": PROMPT_CURSOR_VERSION,
    }
    return (
        base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def _decode_usage_cursor(cursor: str, fingerprint: str, sort: str) -> dict[str, Any]:
    if re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
        raise ValueError("Invalid prompt usage cursor")
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if (
            int(payload["version"]) != PROMPT_CURSOR_VERSION
            or str(payload["fingerprint"]) != fingerprint
            or str(payload["sort"]) != sort
        ):
            raise ValueError
        return {
            "asset_count": int(payload["asset_count"]),
            "last": int(payload["last"]),
            "value_hash": decode_prompt_value_id(str(payload["value_id"])),
        }
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid prompt usage cursor") from exc


def query_prompt_usage(
    *,
    polarity: Literal["positive", "negative"],
    scope: str,
    root_path: str | Path | None,
    library_id: int | None,
    prefix: str | None,
    text_query: str | None,
    sort: Literal["usage", "recent"],
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    """Return one active-catalog keyset page of normalized prompt groups."""
    initialize_database()
    scope_sql = ""
    params: dict[str, Any] = {"kind": polarity, "page_limit": limit + 1}
    if scope == "folder" and root_path is not None:
        scope_sql, scope_params = named_path_scope_sql(root_path, column="asset.path", leading_and=True)
        params.update(scope_params)
        if library_id is not None:
            scope_sql += " AND asset.library_id = :scope_library_id"
            params["scope_library_id"] = library_id
    elif scope == "library":
        scope_sql = " AND asset.library_id = :scope_library_id"
        params["scope_library_id"] = library_id

    text_sql = ""
    if prefix is not None:
        _, normalized_prefix = normalize_discovery_text(prefix)
        text_sql = " AND prompt.search_text LIKE :text_match ESCAPE '\\'"
        params["text_match"] = normalized_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    elif text_query is not None:
        _, normalized_query = normalize_discovery_text(text_query)
        text_sql = " AND prompt.search_text LIKE :text_match ESCAPE '\\'"
        escaped = normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["text_match"] = f"%{escaped}%"

    fingerprint = _prompt_usage_fingerprint(
        polarity=polarity,
        scope=scope,
        root_path=root_path,
        library_id=library_id,
        prefix=prefix,
        text_query=text_query,
        sort=sort,
    )
    cursor_values = _decode_usage_cursor(cursor, fingerprint, sort) if cursor else None
    order_sql = (
        "asset_count DESC, last_asset_mtime_ns DESC, value_hash ASC"
        if sort == "usage"
        else "last_asset_mtime_ns DESC, asset_count DESC, value_hash ASC"
    )
    cursor_sql = ""
    if cursor_values is not None:
        params.update(
            cursor_count=cursor_values["asset_count"],
            cursor_last=cursor_values["last"],
            cursor_hash=cursor_values["value_hash"],
        )
        if sort == "usage":
            cursor_sql = """
              WHERE asset_count < :cursor_count
                 OR (asset_count = :cursor_count AND last_asset_mtime_ns < :cursor_last)
                 OR (asset_count = :cursor_count AND last_asset_mtime_ns = :cursor_last AND value_hash > :cursor_hash)
            """
        else:
            cursor_sql = """
              WHERE last_asset_mtime_ns < :cursor_last
                 OR (last_asset_mtime_ns = :cursor_last AND asset_count < :cursor_count)
                 OR (last_asset_mtime_ns = :cursor_last AND asset_count = :cursor_count AND value_hash > :cursor_hash)
            """
    sql = f"""
      WITH eligible AS (
        SELECT prompt.value_hash, prompt.search_text, prompt.display_text,
               asset.id AS asset_id, asset.library_id, asset.path,
               coalesce(asset.mtime_ns, 0) AS mtime_ns,
               row_number() OVER (
                 PARTITION BY prompt.value_hash
                 ORDER BY asset.mtime_ns DESC, asset.id DESC
               ) AS sample_rank
        FROM asset_prompt_values AS prompt
        JOIN assets AS asset ON asset.id = prompt.asset_id
        WHERE prompt.kind = :kind AND asset.offline = 0 AND asset.deleted_at IS NULL
          {scope_sql} {text_sql}
      ), grouped AS (
        SELECT value_hash, min(search_text) AS search_text,
               max(CASE WHEN sample_rank = 1 THEN display_text END) AS display_text,
               count(*) AS asset_count, max(mtime_ns) AS last_asset_mtime_ns,
               max(CASE WHEN sample_rank = 1 THEN asset_id END) AS sample_asset_id,
               max(CASE WHEN sample_rank = 1 THEN library_id END) AS sample_library_id,
               max(CASE WHEN sample_rank = 1 THEN path END) AS sample_path
        FROM eligible
        GROUP BY value_hash
      )
      SELECT * FROM grouped
      {cursor_sql}
      ORDER BY {order_sql}
      LIMIT :page_limit
    """
    with _DB_LOCK, _connect() as conn:
        rows = list(conn.execute(sql, params))
    page = rows[:limit]
    items = [
        {
            "value_id": encode_prompt_value_id(bytes(row["value_hash"])),
            "kind": polarity,
            "text": str(row["display_text"]),
            "asset_count": int(row["asset_count"]),
            "last_asset_mtime_ns": int(row["last_asset_mtime_ns"]),
            "sample_asset": {
                "asset_id": int(row["sample_asset_id"]),
                "library_id": int(row["sample_library_id"]),
                "path": str(row["sample_path"]),
            },
        }
        for row in page
    ]
    next_cursor = _encode_usage_cursor(page[-1], fingerprint, sort) if len(rows) > limit and page else None
    return {"items": items, "next_cursor": next_cursor, "has_more": next_cursor is not None, "returned": len(items)}
