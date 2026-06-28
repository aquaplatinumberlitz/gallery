"""Shared asset upsert helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from ..files import is_index_excluded_path

_MIN_REASONABLE_MTIME_NS = 1_000_000_000_000


def _normalize_asset_mtime_ns(value: float | int | None) -> int | None:
    """Return nanosecond mtimes only; reject legacy seconds-shaped values."""
    if value is None:
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return normalized if normalized >= _MIN_REASONABLE_MTIME_NS else None


def _upsert_asset_conn(
    conn: sqlite3.Connection,
    *,
    path: str | Path,
    name: str,
    parent_path: str | Path,
    type: str,
    mtime_ns: float | None,
    size: int | None,
    width: int | None = None,
    height: int | None = None,
    orientation: int | None = None,
    metadata_state: str | None = None,
    mime_type: str | None = None,
    duration_ms: int | None = None,
    codec: str | None = None,
    reactivate_existing: bool = True,
) -> int:
    from .library_store import _find_library_for_path_conn, _library_exclusion_patterns_conn

    resolved_path = str(Path(path).resolve())
    library = _find_library_for_path_conn(conn, resolved_path)
    if library is None:
        return 0
    library_id = int(library["id"])
    if is_index_excluded_path(
        resolved_path,
        library["matched_import_path"],
        _library_exclusion_patterns_conn(conn, library_id),
    ):
        return 0
    normalized_mtime_ns = _normalize_asset_mtime_ns(mtime_ns)
    normalized_type = "image" if type in {"image", "photo", "file"} else "video" if type == "video" else "folder"
    conn.execute(
        """
        INSERT INTO assets (
          library_id, path, parent_path, name, type, mtime_ns, size, width,
          height, orientation, indexed_at, metadata_state, offline, deleted_at,
          mime_type, duration_ms, codec
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, 'pending'), 0, NULL, ?, ?, ?)
        ON CONFLICT(library_id, path) DO UPDATE SET
          parent_path=excluded.parent_path,
          name=excluded.name,
          type=excluded.type,
          mtime_ns=COALESCE(excluded.mtime_ns, assets.mtime_ns),
          size=COALESCE(excluded.size, assets.size),
          width=COALESCE(excluded.width, assets.width),
          height=COALESCE(excluded.height, assets.height),
          orientation=COALESCE(excluded.orientation, assets.orientation),
          indexed_at=excluded.indexed_at,
          metadata_state=COALESCE(?, assets.metadata_state),
          mime_type=COALESCE(excluded.mime_type, assets.mime_type),
          duration_ms=COALESCE(excluded.duration_ms, assets.duration_ms),
          codec=COALESCE(excluded.codec, assets.codec),
          offline=CASE WHEN ? THEN 0 ELSE assets.offline END,
          deleted_at=CASE WHEN ? THEN NULL ELSE assets.deleted_at END
        """,
        (
            library_id,
            resolved_path,
            str(Path(parent_path).resolve()),
            name,
            normalized_type,
            normalized_mtime_ns,
            size,
            width,
            height,
            orientation,
            time.time(),
            metadata_state,
            mime_type,
            duration_ms,
            codec,
            metadata_state,
            int(reactivate_existing),
            int(reactivate_existing),
        ),
    )
    row = conn.execute(
        "SELECT id FROM assets WHERE library_id = ? AND path = ?",
        (library_id, resolved_path),
    ).fetchone()
    return int(row["id"])
