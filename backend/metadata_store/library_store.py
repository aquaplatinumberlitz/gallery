"""Library registration and catalog state helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ..files import is_index_excluded_path
from ._db import _DB_LOCK, _active_asset_where, _connect
from .path_utils import _catalog_paths_overlap, _path_is_within
from .types import LibraryOverlapError


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _find_library_for_path_conn(conn: sqlite3.Connection, path: str | Path) -> sqlite3.Row | None:
    resolved = str(Path(path).resolve())
    libraries = conn.execute(
        """
        SELECT l.*, lip.id AS matched_import_path_id,
               lip.path AS matched_import_path, lip.position AS matched_import_path_position
        FROM libraries AS l
        JOIN library_import_paths AS lip ON lip.library_id = l.id
        ORDER BY length(lip.path) DESC, l.id, lip.position, lip.id
        """
    ).fetchall()
    return next((row for row in libraries if _path_is_within(resolved, row["matched_import_path"])), None)


def _library_exclusion_patterns_conn(conn: sqlite3.Connection, library_id: int) -> list[str]:
    return [
        str(row["pattern"])
        for row in conn.execute(
            """
            SELECT pattern FROM library_exclusion_patterns
            WHERE library_id = ?
            ORDER BY position, id
            """,
            (library_id,),
        )
    ]


def _serialize_library_conn(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    library = dict(row)
    # Convert timestamps to milliseconds
    for key in ("created_at", "updated_at", "last_scan_at"):
        if key in library and library[key] is not None:
            library[key] = int(library[key] * 1000)
    library_id = int(row["id"])
    import_paths = [
        dict(import_path)
        for import_path in conn.execute(
            """
            SELECT id, library_id, path, position, created_at, updated_at
            FROM library_import_paths
            WHERE library_id = ?
            ORDER BY position, id
            """,
            (library_id,),
        )
    ]
    # Convert import_path timestamps to milliseconds
    for ip in import_paths:
        for key in ("created_at", "updated_at"):
            if ip.get(key) is not None:
                ip[key] = int(ip[key] * 1000)
    library["import_paths"] = import_paths
    library["exclusion_patterns"] = _library_exclusion_patterns_conn(conn, library_id)
    row_keys = set(row.keys())
    library["root_path"] = (
        import_paths[0]["path"] if import_paths else str(row["root_path"]) if "root_path" in row_keys else ""
    )
    library["asset_count"] = int(
        conn.execute(
            f"""
            SELECT count(*) FROM assets
            WHERE library_id = ? AND type IN ('image', 'video') AND {_active_asset_where()}
            """,
            (library_id,),
        ).fetchone()[0]
    )
    return library


def get_library_stats(library_id: int) -> dict[str, int]:
    """Return media counts and storage use for one registered library."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
            raise KeyError(library_id)
        row = conn.execute(
            """
            SELECT
              sum(CASE WHEN type = 'image' AND offline = 0 THEN 1 ELSE 0 END) AS photos,
              sum(CASE WHEN type = 'video' AND offline = 0 THEN 1 ELSE 0 END) AS videos,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 0 THEN 1 ELSE 0 END) AS active_assets,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 1 THEN 1 ELSE 0 END) AS offline_assets,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 0 THEN COALESCE(size, 0) ELSE 0 END)
                AS usage_bytes
            FROM assets WHERE library_id = ? AND deleted_at IS NULL
            """,
            (library_id,),
        ).fetchone()
        import_path_count = int(
            conn.execute("SELECT count(*) FROM library_import_paths WHERE library_id = ?", (library_id,)).fetchone()[0]
        )
        active = int(row["active_assets"] or 0)
        return {
            "photos": int(row["photos"] or 0),
            "videos": int(row["videos"] or 0),
            "total_assets": active,
            "active_assets": active,
            "offline_assets": int(row["offline_assets"] or 0),
            "usage_bytes": int(row["usage_bytes"] or 0),
            "import_path_count": import_path_count,
        }


def get_gallery_stats() -> dict[str, int]:
    """Return aggregate media counts and storage use across all libraries."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT
              sum(CASE WHEN type = 'image' AND offline = 0 THEN 1 ELSE 0 END) AS photos,
              sum(CASE WHEN type = 'video' AND offline = 0 THEN 1 ELSE 0 END) AS videos,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 0 THEN 1 ELSE 0 END) AS active_assets,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 1 THEN 1 ELSE 0 END) AS offline_assets,
              sum(CASE WHEN type IN ('image', 'video') AND offline = 0 THEN COALESCE(size, 0) ELSE 0 END)
                AS usage_bytes
            FROM assets WHERE deleted_at IS NULL
            """
        ).fetchone()
        active = int(row["active_assets"] or 0)
        return {
            "photos": int(row["photos"] or 0),
            "videos": int(row["videos"] or 0),
            "total_assets": active,
            "active_assets": active,
            "offline_assets": int(row["offline_assets"] or 0),
            "usage_bytes": int(row["usage_bytes"] or 0),
            "library_count": int(conn.execute("SELECT count(*) FROM libraries").fetchone()[0]),
        }


def list_libraries() -> list[dict[str, Any]]:
    """Return all registered libraries in stable ID order."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        return [_serialize_library_conn(conn, row) for row in conn.execute("SELECT * FROM libraries ORDER BY id")]


def get_library(library_id: int) -> dict[str, Any] | None:
    """Return one registered library."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        return _serialize_library_conn(conn, row) if row else None


def get_library_for_path(path: str | Path) -> dict[str, Any] | None:
    """Return the most-specific registered library containing path."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = _find_library_for_path_conn(conn, path)
        if row is None:
            return None
        library = _serialize_library_conn(conn, row)
        library["library_state"] = library["state"]
        library["matched_import_path_id"] = int(row["matched_import_path_id"])
        library["matched_import_path"] = str(row["matched_import_path"])
        return library


def get_asset_state_for_path(path: str | Path) -> dict[str, Any] | None:
    """Return the indexed asset row state (type, offline, deleted_at) for a path.

    Returns None when the path has not been cataloged. Used by the media-path
    authorization helper to reject requests for assets marked offline/deleted.
    """
    _initialize_database()
    resolved = str(Path(path).resolve())
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT type, offline, deleted_at FROM assets WHERE path = ? LIMIT 1",
            (resolved,),
        ).fetchone()
    if row is None:
        return None
    return {
        "type": str(row["type"]),
        "offline": int(row["offline"]) == 1,
        "deleted_at": None if row["deleted_at"] is None else float(row["deleted_at"]),
    }


def get_first_library_root() -> Path | None:
    """Return the first registered library root, if one exists."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT lip.path
            FROM libraries AS l
            JOIN library_import_paths AS lip ON lip.library_id = l.id
            ORDER BY l.id, lip.position, lip.id
            LIMIT 1
            """
        ).fetchone()
        return Path(row["path"]).resolve() if row else None


def _assert_no_import_path_overlap_conn(
    conn: sqlite3.Connection,
    import_paths: list[str],
    *,
    exclude_library_id: int | None = None,
) -> None:
    # 1. Check new paths don't overlap each other (same-library)
    for i, left in enumerate(import_paths):
        for right in import_paths[i + 1 :]:
            if _catalog_paths_overlap(left, right):
                raise LibraryOverlapError(f"Import paths overlap each other: {left} vs {right}")
    # 2. Cross-library check
    query = "SELECT library_id, path FROM library_import_paths"
    params: tuple[Any, ...] = ()
    if exclude_library_id is not None:
        query += " WHERE library_id != ?"
        params = (exclude_library_id,)
    for existing in conn.execute(query, params):
        existing_path = str(existing["path"])
        for path in import_paths:
            if _path_is_within(path, existing_path) or _path_is_within(existing_path, path):
                raise LibraryOverlapError(f"Library import path overlaps registered path: {existing_path}")


def _replace_library_paths_conn(
    conn: sqlite3.Connection,
    library_id: int,
    import_paths: list[str],
    *,
    now: float,
) -> None:
    if not import_paths:
        raise ValueError("At least one import path is required")
    conn.execute("DELETE FROM library_import_paths WHERE library_id = ?", (library_id,))
    conn.executemany(
        """
        INSERT INTO library_import_paths (
          library_id, path, position, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ((library_id, path, position, now, now) for position, path in enumerate(import_paths)),
    )
    conn.execute("UPDATE libraries SET updated_at = ? WHERE id = ?", (now, library_id))


def _replace_library_patterns_conn(
    conn: sqlite3.Connection,
    library_id: int,
    exclusion_patterns: list[str],
    *,
    now: float,
) -> None:
    conn.execute("DELETE FROM library_exclusion_patterns WHERE library_id = ?", (library_id,))
    conn.executemany(
        """
        INSERT INTO library_exclusion_patterns (
          library_id, pattern, position, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ((library_id, pattern, position, now, now) for position, pattern in enumerate(exclusion_patterns)),
    )


def _reconcile_library_configuration_conn(conn: sqlite3.Connection, library_id: int) -> None:
    roots = [
        str(row["path"])
        for row in conn.execute(
            "SELECT path FROM library_import_paths WHERE library_id = ? ORDER BY length(path) DESC, position, id",
            (library_id,),
        )
    ]
    patterns = _library_exclusion_patterns_conn(conn, library_id)
    now = time.time()
    updates: list[tuple[int, float, int]] = []
    out_of_scope_paths: list[str] = []
    for row in conn.execute(
        "SELECT id, path, offline, deleted_at FROM assets WHERE library_id = ?",
        (library_id,),
    ):
        path = str(row["path"])
        import_root = next((root for root in roots if _path_is_within(path, root)), None)
        in_scope = bool(
            import_root
            and not is_index_excluded_path(path, import_root, patterns)
            and Path(path).exists()
            and row["deleted_at"] is None
        )
        offline = 0 if in_scope else 1
        if offline:
            out_of_scope_paths.append(path)
        if int(row["offline"]) != offline:
            updates.append((offline, now, int(row["id"])))
    if updates:
        conn.executemany("UPDATE assets SET offline = ?, indexed_at = ? WHERE id = ?", updates)
    if out_of_scope_paths:
        values = ((path,) for path in out_of_scope_paths)
        conn.executemany("DELETE FROM file_index_fts WHERE path = ?", values)
        for table in ("file_index", "metadata_index_jobs", "folder_index_state"):
            conn.executemany("DELETE FROM " + table + " WHERE path = ?", ((path,) for path in out_of_scope_paths))


def create_library(
    import_paths: list[str | Path],
    *,
    name: str | None = None,
    exclusion_patterns: list[str] | None = None,
    warm_enabled: bool = True,
    queue_initial_scan: bool = False,
) -> dict[str, Any]:
    """Create one library with ordered import paths and exclusion patterns."""
    canonical_paths = [str(Path(path).resolve()) for path in import_paths]
    patterns = list(exclusion_patterns or [])
    if not canonical_paths:
        raise ValueError("At least one import path is required")
    if len(set(canonical_paths)) != len(canonical_paths):
        raise ValueError("Duplicate import paths are not allowed")
    if len(set(patterns)) != len(patterns):
        raise ValueError("Duplicate exclusion patterns are not allowed")
    display_name = (name or Path(canonical_paths[0]).name or canonical_paths[0]).strip()
    now = time.time()
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        _assert_no_import_path_overlap_conn(conn, canonical_paths)
        cursor = conn.execute(
            """
            INSERT INTO libraries (
              name, state, warm_enabled, created_at, updated_at
            ) VALUES (?, 'discovering', ?, ?, ?)
            """,
            (display_name, int(warm_enabled), now, now),
        )
        library_id = int(cursor.lastrowid)
        _replace_library_paths_conn(conn, library_id, canonical_paths, now=now)
        _replace_library_patterns_conn(conn, library_id, patterns, now=now)
        initial_scan_job_id: int | None = None
        if queue_initial_scan:
            cursor = conn.execute(
                """
                INSERT INTO library_jobs (
                  library_id, type, state, scope_path, trigger, priority,
                  progress_current, progress_total, message, counters, created_at, updated_at
                ) VALUES (?, 'scan', 'queued', NULL, 'initial', 100, 0, NULL, 'Initial update queued', '{}', ?, ?)
                """,
                (library_id, now, now),
            )
            initial_scan_job_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        library = _serialize_library_conn(conn, row)
        if initial_scan_job_id is not None:
            library["initial_scan_job_id"] = initial_scan_job_id
        return library


def update_library(
    library_id: int,
    *,
    name: str | None = None,
    import_paths: list[str | Path] | None = None,
    exclusion_patterns: list[str] | None = None,
    warm_enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Replace supplied library fields and reconcile existing catalog scope."""
    canonical_paths = [str(Path(path).resolve()) for path in import_paths] if import_paths is not None else None
    patterns = list(exclusion_patterns) if exclusion_patterns is not None else None
    if canonical_paths is not None and not canonical_paths:
        raise ValueError("At least one import path is required")
    if canonical_paths is not None and len(set(canonical_paths)) != len(canonical_paths):
        raise ValueError("Duplicate import paths are not allowed")
    if patterns is not None and len(set(patterns)) != len(patterns):
        raise ValueError("Duplicate exclusion patterns are not allowed")
    now = time.time()
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        if row is None:
            return None
        if canonical_paths is not None:
            _assert_no_import_path_overlap_conn(conn, canonical_paths, exclude_library_id=library_id)
            _replace_library_paths_conn(conn, library_id, canonical_paths, now=now)
        if patterns is not None:
            _replace_library_patterns_conn(conn, library_id, patterns, now=now)
        if name is not None:
            conn.execute(
                "UPDATE libraries SET name = ?, updated_at = ? WHERE id = ?",
                (name.strip(), now, library_id),
            )
        if warm_enabled is not None:
            conn.execute(
                "UPDATE libraries SET warm_enabled = ?, updated_at = ? WHERE id = ?",
                (int(warm_enabled), now, library_id),
            )
        if canonical_paths is not None or patterns is not None:
            _reconcile_library_configuration_conn(conn, library_id)
        row = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        return _serialize_library_conn(conn, row)


def register_library(root_path: str | Path, name: str | None = None) -> dict[str, Any]:
    """Register a canonical, non-overlapping library root."""
    return create_library([root_path], name=name)


def unregister_library(library_id: int) -> bool:
    """Delete catalog records for a library without touching source files."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        if conn.execute("SELECT 1 FROM libraries WHERE id = ?", (library_id,)).fetchone() is None:
            return False
        conn.execute(
            "DELETE FROM derivative_jobs WHERE derivative_id IN "
            "(SELECT d.id FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id WHERE a.library_id = ?)",
            (library_id,),
        )
        conn.execute(
            "DELETE FROM asset_derivatives WHERE asset_id IN (SELECT id FROM assets WHERE library_id = ?)",
            (library_id,),
        )
        conn.execute("DELETE FROM assets WHERE library_id = ?", (library_id,))
        conn.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
        return True


def update_library_state(
    library_id: int,
    state: str,
    *,
    last_error: str | None = None,
    scan_completed: bool = False,
) -> None:
    """Persist discovery/indexing lifecycle state for a library."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE libraries
            SET state = ?, last_error = ?, updated_at = ?,
                last_scan_at = CASE WHEN ? THEN ? ELSE last_scan_at END
            WHERE id = ?
            """,
            (state, last_error, time.time(), int(scan_completed), time.time(), library_id),
        )


def get_library_progress(library_id: int) -> dict[str, Any]:
    """Return asset coverage, library state, and the newest active job."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        library = conn.execute("SELECT state FROM libraries WHERE id = ?", (library_id,)).fetchone()
        if library is None:
            raise KeyError(library_id)
        indexed = int(
            conn.execute(
                f"""
                SELECT count(*) FROM assets
                WHERE library_id = ? AND type = 'image' AND {_active_asset_where()} AND metadata_state = 'done'
                """,
                (library_id,),
            ).fetchone()[0]
        )
        estimated = int(
            conn.execute(
                f"""
                SELECT count(*) FROM assets WHERE library_id = ? AND type = 'image' AND {_active_asset_where()}
                """,
                (library_id,),
            ).fetchone()[0]
        )
        active_job = conn.execute(
            """
            SELECT id FROM library_jobs
            WHERE library_id = ? AND state IN ('queued', 'running')
              AND type IN ('scan', 'rebuild', 'reconcile')
            ORDER BY id DESC LIMIT 1
            """,
            (library_id,),
        ).fetchone()
        return {
            "indexed_assets": indexed,
            "estimated_assets": estimated,
            "discovery_complete": library["state"] in {"ready", "error", "offline"},
            "library_state": library["state"],
            "active_job_id": int(active_job["id"]) if active_job else None,
        }
