"""Catalog rebuild staging and reconciliation helpers."""

from __future__ import annotations

import mimetypes
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..config import GALLERY_CATALOG_WRITE_BATCH_SIZE
from ..files import asset_type_for_path, is_asset_path, is_index_excluded_path
from ._db import _DB_LOCK, _active_asset_where, _connect
from .library_store import get_library
from .path_utils import canonicalize_catalog_path, catalog_path_contains, path_scope_sql


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def enumerate_to_rebuild_staging(
    job_id: int,
    library_id: int,
    scope_paths: list[str | Path],
) -> tuple[dict[str, int], list[str]]:
    """Walk scope_paths and write discovered entries to catalog_rebuild_entries.

    Browse continues serving the canonical generation while enumeration runs.
    Filesystem enumeration never occurs inside a SQLite write transaction;
    staging rows are flushed in bounded batches. Returns counters plus the
    list of supported asset paths (for later metadata queueing).
    """
    library = get_library(library_id)
    if library is None:
        raise KeyError(library_id)
    exclusion_patterns = list(library["exclusion_patterns"])
    import_roots = [str(Path(item["path"]).resolve()) for item in library["import_paths"]]

    discovered = 0
    folders = 0
    assets = 0
    asset_paths: list[str] = []
    batch: list[tuple[Any, ...]] = []

    def flush() -> None:
        nonlocal batch
        if not batch:
            return
        rows = batch
        batch = []
        _initialize_database()
        with _DB_LOCK, _connect() as conn:
            conn.executemany(
                """
                INSERT INTO catalog_rebuild_entries (
                  job_id, library_id, path, parent_path, name, type,
                  mtime_ns, size, width, height, mime_type, duration_ms,
                  codec, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, path) DO UPDATE SET
                  parent_path=excluded.parent_path,
                  name=excluded.name,
                  type=excluded.type,
                  mtime_ns=excluded.mtime_ns,
                  size=excluded.size,
                  width=excluded.width,
                  height=excluded.height,
                  mime_type=excluded.mime_type,
                  duration_ms=excluded.duration_ms,
                  codec=excluded.codec
                """,
                rows,
            )

    def stage_entry(
        *,
        path: Path,
        entry_type: str,
        mtime_ns: int | None,
        size: int | None,
        width: int | None = None,
        height: int | None = None,
        mime_type: str | None = None,
        duration_ms: int | None = None,
        codec: str | None = None,
    ) -> None:
        nonlocal discovered, folders, assets
        resolved = path.resolve()
        resolved_text = str(resolved)
        batch.append(
            (
                job_id,
                library_id,
                resolved_text,
                str(resolved.parent),
                resolved.name or resolved_text,
                entry_type,
                mtime_ns,
                size,
                width,
                height,
                mime_type,
                duration_ms,
                codec,
                time.time(),
            )
        )
        discovered += 1
        if entry_type == "folder":
            folders += 1
        else:
            assets += 1
            asset_paths.append(resolved_text)
        if len(batch) >= GALLERY_CATALOG_WRITE_BATCH_SIZE:
            flush()

    def visit(folder: Path, import_root: str, visited_inodes: set[tuple[int, int]]) -> None:
        if is_index_excluded_path(folder, import_root, exclusion_patterns):
            return
        try:
            stat = folder.stat()
        except OSError:
            return
        if folder.is_dir():
            inode = (stat.st_dev, stat.st_ino)
            if inode in visited_inodes:
                return
            visited_inodes.add(inode)
            stage_entry(path=folder, entry_type="folder", mtime_ns=stat.st_mtime_ns, size=None)
            try:
                entries = list(folder.iterdir())
            except (OSError, PermissionError):
                return
            for entry in entries:
                if entry.name.startswith(".") or is_index_excluded_path(entry, import_root, exclusion_patterns):
                    continue
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        visit(entry, import_root, visited_inodes)
                    elif entry.is_file() and is_asset_path(entry):
                        file_stat = entry.stat()
                        asset_type = asset_type_for_path(entry) or "image"
                        mime_type = mimetypes.guess_type(entry.name)[0]
                        stage_entry(
                            path=entry,
                            entry_type=asset_type,
                            mtime_ns=file_stat.st_mtime_ns,
                            size=file_stat.st_size,
                            mime_type=mime_type,
                        )
                except (OSError, PermissionError):
                    continue

    for scope in scope_paths:
        scope_path = Path(scope).resolve()
        import_root = next((root for root in import_roots if catalog_path_contains(root, scope_path)), None)
        if import_root is None:
            continue
        visit(scope_path, import_root, set())
    flush()
    return (
        {"discovered": discovered, "folders": folders, "assets": assets},
        asset_paths,
    )


def activate_rebuild_staging(
    job_id: int,
    library_id: int,
    scope_path: str | Path | None,
) -> dict[str, int]:
    """Merge staged rebuild rows into the canonical catalog in one short transaction.

    Idempotent merge: staged rows upsert into file_index and assets, missing
    rows in scope are marked offline, changed assets reset metadata_state to
    pending, last_seen_scan_job_id is updated, and staging rows for this job
    are deleted only after commit. Failed activation rolls back, leaving the
    canonical generation and staging rows untouched.
    """
    _initialize_database()
    now = time.time()
    scope_text = canonicalize_catalog_path(scope_path) if scope_path is not None else None
    with _DB_LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            staged = conn.execute(
                """
                SELECT path, parent_path, name, type, mtime_ns, size, mime_type,
                       duration_ms, codec
                FROM catalog_rebuild_entries
                WHERE job_id = ? AND library_id = ?
                """,
                (job_id, library_id),
            ).fetchall()
            staged_paths = {row["path"] for row in staged}
            created = 0
            updated = 0
            metadata_reset = 0
            for row in staged:
                existing = conn.execute(
                    "SELECT mtime_ns, size, metadata_state FROM assets WHERE library_id = ? AND path = ?",
                    (library_id, row["path"]),
                ).fetchone()
                normalized_type = (
                    "image"
                    if row["type"] in {"image", "photo", "file"}
                    else "video"
                    if row["type"] == "video"
                    else "folder"
                )
                metadata_state = None
                if existing is None:
                    created += 1
                    metadata_state = "pending"
                else:
                    updated += 1
                    if existing["mtime_ns"] != row["mtime_ns"] or existing["size"] != row["size"]:
                        metadata_state = "pending"
                        metadata_reset += 1
                conn.execute(
                    """
                    INSERT INTO file_index (
                      path, name, parent_path, type, mtime, mtime_ns, size,
                      indexed_at, library_id, last_seen_scan_job_id
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                      name=excluded.name,
                      parent_path=excluded.parent_path,
                      type=excluded.type,
                      mtime_ns=excluded.mtime_ns,
                      size=excluded.size,
                      indexed_at=excluded.indexed_at,
                      library_id=excluded.library_id,
                      last_seen_scan_job_id=excluded.last_seen_scan_job_id
                    """,
                    (
                        row["path"],
                        row["name"],
                        row["parent_path"],
                        normalized_type,
                        row["mtime_ns"],
                        row["size"],
                        now,
                        library_id,
                        job_id,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO assets (
                      library_id, path, parent_path, name, type, mtime_ns, size,
                      width, height, indexed_at, metadata_state, offline, deleted_at,
                      mime_type, duration_ms, codec, last_seen_scan_job_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, 0, NULL, ?, ?, ?, ?)
                    ON CONFLICT(library_id, path) DO UPDATE SET
                      parent_path=excluded.parent_path,
                      name=excluded.name,
                      type=excluded.type,
                      mtime_ns=excluded.mtime_ns,
                      size=excluded.size,
                      indexed_at=excluded.indexed_at,
                      metadata_state=COALESCE(excluded.metadata_state, assets.metadata_state),
                      mime_type=COALESCE(excluded.mime_type, assets.mime_type),
                      duration_ms=COALESCE(excluded.duration_ms, assets.duration_ms),
                      codec=COALESCE(excluded.codec, assets.codec),
                      offline=0,
                      deleted_at=NULL,
                      last_seen_scan_job_id=excluded.last_seen_scan_job_id
                    """,
                    (
                        library_id,
                        row["path"],
                        row["parent_path"],
                        row["name"],
                        normalized_type,
                        row["mtime_ns"],
                        row["size"],
                        now,
                        metadata_state,
                        row["mime_type"],
                        row["duration_ms"],
                        row["codec"],
                        job_id,
                    ),
                )
                conn.execute("DELETE FROM file_index_fts WHERE path = ?", (row["path"],))
                conn.execute(
                    "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, ?, ?)",
                    (row["name"], row["path"], normalized_type, row["parent_path"]),
                )

            scope_sql = ""
            params: list[Any] = [library_id]
            if scope_text is not None:
                scope_sql, scope_params = path_scope_sql(scope_text, leading_and=True)
                params.extend(scope_params)
            in_scope = conn.execute(
                f"""
                SELECT path FROM assets
                WHERE library_id = ? AND offline = 0 AND deleted_at IS NULL
                  {scope_sql}
                """,
                params,
            ).fetchall()
            missing = [row["path"] for row in in_scope if row["path"] not in staged_paths]
            if missing:
                conn.executemany(
                    "UPDATE assets SET offline = 1, indexed_at = ? WHERE library_id = ? AND path = ?",
                    ((now, library_id, path) for path in missing),
                )
            conn.execute("DELETE FROM catalog_rebuild_entries WHERE job_id = ?", (job_id,))
            conn.execute("COMMIT")
            return {
                "discovered": len(staged),
                "created": created,
                "updated": updated,
                "offline": len(missing),
                "metadata_reset": metadata_reset,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise


def delete_rebuild_staging(job_id: int) -> None:
    """Remove orphaned rebuild staging rows for a failed/cancelled job."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute("DELETE FROM catalog_rebuild_entries WHERE job_id = ?", (job_id,))


def _reconcile_assets_conn(
    conn: sqlite3.Connection,
    library_id: int,
    discovered_paths: set[str],
    *,
    scope_path: str | Path | None = None,
) -> int:
    """Mark catalog rows missing from the latest discovery offline without deleting derivatives."""
    params: list[Any] = [library_id]
    scope_sql = ""
    if scope_path is not None:
        scope_sql, scope_params = path_scope_sql(scope_path, leading_and=True)
        params.extend(scope_params)

    existing = conn.execute(
        f"""
        SELECT path
        FROM assets
        WHERE library_id = ?
          AND {_active_asset_where()}
          {scope_sql}
        """,
        params,
    ).fetchall()
    missing_paths = [row["path"] for row in existing if row["path"] not in discovered_paths]
    if not missing_paths:
        return 0

    now = time.time()
    conn.executemany(
        "UPDATE assets SET offline = 1, indexed_at = ? WHERE library_id = ? AND path = ?",
        ((now, library_id, path) for path in missing_paths),
    )
    return len(missing_paths)


def reconcile_library_assets(
    library_id: int,
    discovered_paths: set[str | Path],
    *,
    scope_path: str | Path | None = None,
) -> int:
    """Reconcile active assets for a library or scoped subtree."""
    normalized = {str(Path(path).resolve()) for path in discovered_paths}
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        return _reconcile_assets_conn(conn, library_id, normalized, scope_path=scope_path)
