"""Opt-in bounded canonical raw-workflow indexing and deadline-limited search."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import (
    GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES,
    GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES,
)
from .metadata_store._db import _DB_LOCK, _connect, _gallery_metadata_db_path
from .metadata_store._schema import initialize_database
from .metadata_store.path_utils import canonicalize_catalog_path, named_path_scope_sql

RAW_WORKFLOW_EXTRACTOR_VERSION = 1
RAW_WORKFLOW_CURSOR_VERSION = 1
RAW_WORKFLOW_QUERY_DEADLINE_SECONDS = 0.250


class RawWorkflowTimeout(RuntimeError):
    """Raised when SQLite's progress handler ends a raw workflow query."""


def _is_workflow_document(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("nodes"), list):
        return True
    return any(
        isinstance(node, dict) and bool(node.get("class_type") or node.get("type") or node.get("inputs"))
        for node in value.values()
    )


def _workflow_json_from_raw(raw: str) -> dict[str, Any] | None:
    candidates: list[str] = []
    for line in raw.splitlines():
        if line.startswith("prompt: "):
            candidates.append(line.split(": ", 1)[1])
    for line in raw.splitlines():
        if line.startswith("workflow: "):
            candidates.append(line.split(": ", 1)[1])
    candidates.append(raw)
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if _is_workflow_document(decoded):
            return decoded
    return None


def _raw_workflow_source(asset: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT raw_metadata_text, tool, metadata_json FROM image_metadata WHERE path = ?",
            (str(asset["path"]),),
        ).fetchone()
    if row is None:
        return None, False
    metadata_tool = ""
    try:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        if isinstance(metadata, dict):
            metadata_tool = str(metadata.get("tool") or "")
    except json.JSONDecodeError:
        pass
    raw = str(row["raw_metadata_text"] or "")
    return (_workflow_json_from_raw(raw) if raw else None), str(row["tool"] or metadata_tool) == "ComfyUI"


def extract_raw_workflow(asset: dict[str, Any]):  # noqa: ANN201
    """Canonicalize one persisted workflow and enforce size/global budget bounds."""
    from .search_indexer import SearchExtractionResult

    document, looks_comfy = _raw_workflow_source(asset)
    if document is None:
        if looks_comfy:
            return SearchExtractionResult(status="failed", error_code="raw_workflow_parse_failed")
        return SearchExtractionResult(status="not_applicable", payload=None)
    canonical_text = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    byte_length = len(canonical_text.encode("utf-8"))
    if byte_length > GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES:
        return SearchExtractionResult(status="skipped", error_code="raw_document_too_large", payload=None)
    with _DB_LOCK, _connect() as conn:
        current_bytes = int(
            conn.execute(
                "SELECT coalesce(sum(byte_length), 0) FROM workflow_raw_documents WHERE asset_id != ?",
                (int(asset["id"]),),
            ).fetchone()[0]
        )
    if current_bytes + byte_length > GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES:
        return SearchExtractionResult(status="skipped", error_code="raw_index_budget_exceeded", payload=None)
    return SearchExtractionResult(
        status="ready",
        payload={"canonical_text": canonical_text, "byte_length": byte_length},
    )


def persist_raw_workflow(conn: sqlite3.Connection, asset: dict[str, Any], payload: dict[str, Any] | None) -> None:
    """Replace one raw document atomically with its extraction status write."""
    asset_id = int(asset["id"])
    conn.execute("DELETE FROM workflow_raw_documents WHERE asset_id = ?", (asset_id,))
    if payload is None:
        return
    conn.execute(
        """
        INSERT INTO workflow_raw_documents (
          asset_id, library_id, canonical_text, byte_length,
          source_fingerprint, extractor_version
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            int(asset["library_id"]),
            payload["canonical_text"],
            int(payload["byte_length"]),
            f"{int(asset.get('mtime_ns') or 0)}:{int(asset.get('size') or 0)}",
            RAW_WORKFLOW_EXTRACTOR_VERSION,
        ),
    )


def invalidate_raw_workflow_conn(conn: sqlite3.Connection, asset_id: int, library_id: int) -> None:
    """Remove stale canonical raw JSON and mark initialized coverage incomplete."""
    extraction = conn.execute(
        "SELECT status FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'workflow_raw'",
        (asset_id,),
    ).fetchone()
    conn.execute("DELETE FROM workflow_raw_documents WHERE asset_id = ?", (asset_id,))
    conn.execute(
        "DELETE FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'workflow_raw'",
        (asset_id,),
    )
    from .metadata_store.search_index_store import mark_search_index_asset_stale_conn

    mark_search_index_asset_stale_conn(
        conn,
        "workflow_raw",
        library_id,
        str(extraction["status"]) if extraction is not None else None,
    )


def _request_fingerprint(
    query: str,
    scope: str,
    root_path: str | Path | None,
    library_id: int | None,
) -> str:
    payload = {
        "library_id": library_id,
        "query": query,
        "root": canonicalize_catalog_path(root_path) if root_path is not None else None,
        "scope": scope,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _encode_cursor(row: sqlite3.Row, fingerprint: str) -> str:
    payload = {
        "asset_id": int(row["asset_id"]),
        "fingerprint": fingerprint,
        "mtime_ns": int(row["mtime_ns"]),
        "rank": float(row["rank"]),
        "version": RAW_WORKFLOW_CURSOR_VERSION,
    }
    return (
        base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def _decode_cursor(cursor: str, fingerprint: str) -> dict[str, Any]:
    if re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
        raise ValueError("Invalid raw workflow cursor")
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        rank = float(payload["rank"])
        if (
            int(payload["version"]) != RAW_WORKFLOW_CURSOR_VERSION
            or str(payload["fingerprint"]) != fingerprint
            or not math.isfinite(rank)
        ):
            raise ValueError
        return {"rank": rank, "mtime_ns": int(payload["mtime_ns"]), "asset_id": int(payload["asset_id"])}
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid raw workflow cursor") from exc


def _validate_query(query: str) -> str:
    normalized = query.strip()
    if len(normalized) < 3 or len(normalized) > 128:
        raise ValueError("Raw workflow query must contain 3-128 characters")
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in normalized):
        raise ValueError("Raw workflow query contains control characters")
    if re.search(
        r"(?i)(?:--|/\*|\*/|;\s*(?:drop|delete|insert|update|alter|pragma|attach)\b)",
        normalized,
    ):
        raise ValueError("Raw workflow query contains a rejected control sequence")
    return normalized


def _readonly_connection() -> sqlite3.Connection:
    database = _gallery_metadata_db_path()
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.25)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=250")
    return conn


def query_raw_workflows(
    *,
    query: str,
    scope: str,
    root_path: str | Path | None,
    library_id: int | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    """Run one literal trigram FTS page with a hard SQLite progress deadline."""
    initialize_database()
    normalized = _validate_query(query)
    fingerprint = _request_fingerprint(normalized, scope, root_path, library_id)
    cursor_values = _decode_cursor(cursor, fingerprint) if cursor else None
    scope_sql = ""
    params: dict[str, Any] = {
        "match": '"' + normalized.replace('"', '""') + '"',
        "page_limit": min(max(1, limit), 50) + 1,
    }
    if scope == "folder" and root_path is not None:
        scope_sql, scope_params = named_path_scope_sql(root_path, column="asset.path", leading_and=True)
        params.update(scope_params)
        if library_id is not None:
            scope_sql += " AND asset.library_id = :scope_library_id"
            params["scope_library_id"] = library_id
    elif scope == "library":
        scope_sql = " AND asset.library_id = :scope_library_id"
        params["scope_library_id"] = library_id
    cursor_sql = ""
    if cursor_values is not None:
        params.update(
            cursor_rank=cursor_values["rank"],
            cursor_mtime_ns=cursor_values["mtime_ns"],
            cursor_asset_id=cursor_values["asset_id"],
        )
        cursor_sql = """
          AND (
            rank > :cursor_rank
            OR (rank = :cursor_rank AND mtime_ns < :cursor_mtime_ns)
            OR (rank = :cursor_rank AND mtime_ns = :cursor_mtime_ns AND asset_id > :cursor_asset_id)
          )
        """
    sql = f"""
      WITH matches AS (
        SELECT document.asset_id, asset.library_id, library.name AS library_name,
               asset.path, asset.name, coalesce(asset.mtime_ns, 0) AS mtime_ns,
               round(bm25(workflow_raw_fts), 6) AS rank
        FROM workflow_raw_fts
        JOIN workflow_raw_documents AS document ON document.asset_id = workflow_raw_fts.rowid
        JOIN assets AS asset ON asset.id = document.asset_id
        JOIN libraries AS library ON library.id = asset.library_id
        WHERE workflow_raw_fts MATCH :match
          AND asset.offline = 0 AND asset.deleted_at IS NULL
          {scope_sql}
      )
      SELECT * FROM matches
      WHERE 1=1 {cursor_sql}
      ORDER BY rank ASC, mtime_ns DESC, asset_id ASC
      LIMIT :page_limit
    """
    started = time.monotonic()
    conn = _readonly_connection()
    conn.set_progress_handler(
        lambda: int(time.monotonic() - started >= RAW_WORKFLOW_QUERY_DEADLINE_SECONDS),
        1_000,
    )
    try:
        rows = list(conn.execute(sql, params))
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower() or time.monotonic() - started >= RAW_WORKFLOW_QUERY_DEADLINE_SECONDS:
            raise RawWorkflowTimeout from exc
        raise
    finally:
        conn.close()
    page = rows[:limit]
    items = [
        {
            "asset_id": int(row["asset_id"]),
            "library_id": int(row["library_id"]),
            "library_name": str(row["library_name"]),
            "path": str(row["path"]),
            "name": str(row["name"]),
            "mtime_ns": int(row["mtime_ns"]),
        }
        for row in page
    ]
    next_cursor = _encode_cursor(page[-1], fingerprint) if len(rows) > limit and page else None
    return {
        "query": normalized,
        "items": items,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "returned": len(items),
        "warning": "Raw workflow search is an opt-in expensive operation over bounded canonical JSON.",
        "capability": {
            "deadline_ms": int(RAW_WORKFLOW_QUERY_DEADLINE_SECONDS * 1000),
            "max_query_chars": 128,
            "max_limit": 50,
        },
    }
