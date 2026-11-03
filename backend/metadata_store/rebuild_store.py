"""Catalog rebuild staging and reconciliation helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ..config import GALLERY_CATALOG_WRITE_BATCH_SIZE
from ..files import asset_type_for_path, is_asset_path, is_index_excluded_path
from ._db import _active_asset_where
from .db_writer import LANE_NORMAL, run_write
from .file_index import (
    CatalogRecord,
    _normalize_file_type,
    build_asset_record,
    build_folder_record,
    upsert_catalog_records_conn,
)
from .library_store import get_library
from .path_utils import canonicalize_catalog_path, catalog_path_contains, path_scope_sql


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def enumerate_to_rebuild_staging(
    job_id: int,
    library_id: int,
    scope_paths: list[str | Path],
    claim_token: str,
    claim_lease_seconds: float = 900,
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

        def write(conn: sqlite3.Connection) -> None:
            from .job_store import assert_catalog_job_claim_conn, refresh_catalog_job_claim_before_commit_conn

            assert_catalog_job_claim_conn(conn, job_id, claim_token, library_id=library_id)
            conn.executemany(
                """
            INSERT INTO catalog_rebuild_entries (
              job_id, library_id, path, parent_path, name, type,
              mtime, mtime_ns, size, width, height, mime_type, duration_ms,
              codec, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, path) DO UPDATE SET
              parent_path=excluded.parent_path,
              name=excluded.name,
              type=excluded.type,
              mtime=excluded.mtime,
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
            refresh_catalog_job_claim_before_commit_conn(
                conn,
                job_id,
                claim_token,
                lease_seconds=claim_lease_seconds,
                library_id=library_id,
            )

        run_write(write, lane=LANE_NORMAL)

    def stage_entry(record: CatalogRecord) -> None:
        nonlocal discovered, folders, assets
        batch.append(
            (
                job_id,
                library_id,
                record.path,
                record.parent_path,
                record.name,
                record.type,
                record.mtime,
                record.mtime_ns,
                record.size,
                record.width,
                record.height,
                record.mime_type,
                record.duration_ms,
                record.codec,
                time.time(),
            )
        )
        discovered += 1
        if record.type == "folder":
            folders += 1
        else:
            assets += 1
            asset_paths.append(record.path)
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
            stage_entry(build_folder_record(folder.resolve(), stat))
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
                        stage_entry(build_asset_record(entry, entry.stat(), asset_type_for_path(entry)))
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
    claim_token: str,
    claim_lease_seconds: float = 900,
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

    def activate(conn: sqlite3.Connection) -> dict[str, int]:
        from .job_store import assert_catalog_job_claim_conn

        assert_catalog_job_claim_conn(conn, job_id, claim_token, library_id=library_id)
        staged = conn.execute(
            """
            SELECT path, parent_path, name, type, mtime, mtime_ns, size, width, height,
                   mime_type, duration_ms, codec
            FROM catalog_rebuild_entries
            WHERE job_id = ? AND library_id = ?
            """,
            (job_id, library_id),
        ).fetchall()
        staged_paths = {row["path"] for row in staged}
        created = 0
        updated = 0
        metadata_reset = 0
        records: list[CatalogRecord] = []
        for row in staged:
            existing = conn.execute(
                "SELECT mtime_ns, size FROM assets WHERE library_id = ? AND path = ?",
                (library_id, row["path"]),
            ).fetchone()
            normalized_type = _normalize_file_type(row["type"])
            if existing is None:
                created += 1
            else:
                updated += 1
                # The shared writer resets metadata_state for a changed image only; count what it will reset.
                if normalized_type == "image" and (
                    existing["mtime_ns"] != row["mtime_ns"] or existing["size"] != row["size"]
                ):
                    metadata_reset += 1
            mtime = row["mtime"]
            if mtime is None and row["mtime_ns"] is not None:  # staged by a build that predates the column
                mtime = row["mtime_ns"] / 1e9
            records.append(
                CatalogRecord(
                    row["path"],
                    row["name"],
                    row["parent_path"],
                    normalized_type,
                    mtime,
                    row["mtime_ns"],
                    row["size"],
                    row["width"],
                    row["height"],
                    now,
                    row["mime_type"],
                    row["duration_ms"],
                    row["codec"],
                )
            )
        # Same upsert as a scan: one record shape, one SQL path (file_index, file_index_fts, assets).
        upsert_catalog_records_conn(conn, records, library_id, last_seen_scan_job_id=job_id)

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
        from .job_store import refresh_catalog_job_claim_before_commit_conn

        refresh_catalog_job_claim_before_commit_conn(
            conn,
            job_id,
            claim_token,
            lease_seconds=claim_lease_seconds,
            library_id=library_id,
        )
        return {
            "discovered": len(staged),
            "created": created,
            "updated": updated,
            "offline": len(missing),
            "metadata_reset": metadata_reset,
        }

    # One atomic op by contract: a failed activation leaves the canonical generation and the staging rows
    # untouched, so it is never split. (A very large library holds the write lock for the whole merge.)
    return run_write(activate, lane=LANE_NORMAL)


def delete_rebuild_staging(job_id: int, *, claim_token: str | None = None) -> None:
    """Remove orphaned rebuild staging rows for a failed/cancelled job."""
    _initialize_database()

    def delete(conn: sqlite3.Connection) -> None:
        if claim_token is not None:
            from .job_store import assert_catalog_job_claim_conn

            assert_catalog_job_claim_conn(conn, job_id, claim_token)
        conn.execute("DELETE FROM catalog_rebuild_entries WHERE job_id = ?", (job_id,))

    run_write(delete, lane=LANE_NORMAL)


def delete_rebuild_staging_for_lost_claim(job_id: int, claim_token: str) -> bool:
    """Delete stale staging unless the job has already gained a newer live claim."""
    _initialize_database()
    now = time.time()

    def delete(conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT state, claim_token, lease_expires_at FROM library_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        newer_live_claim = (
            row["state"] == "running"
            and row["claim_token"] != claim_token
            and row["lease_expires_at"] is not None
            and float(row["lease_expires_at"]) > now
        )
        if newer_live_claim:
            return False
        conn.execute("DELETE FROM catalog_rebuild_entries WHERE job_id = ?", (job_id,))
        return True

    return run_write(delete, lane=LANE_NORMAL)


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
    claim_job_id: int | None = None,
    claim_token: str | None = None,
    claim_lease_seconds: float = 900,
) -> int:
    """Reconcile active assets for a library or scoped subtree."""
    normalized = {str(Path(path).resolve()) for path in discovered_paths}
    if (claim_job_id is None) != (claim_token is None):
        raise ValueError("Catalog claim job id and token must be provided together")
    _initialize_database()

    def reconcile(conn: sqlite3.Connection) -> int:
        if claim_job_id is not None and claim_token is not None:
            from .job_store import assert_catalog_job_claim_conn

            assert_catalog_job_claim_conn(conn, claim_job_id, claim_token, library_id=library_id)
        reconciled = _reconcile_assets_conn(conn, library_id, normalized, scope_path=scope_path)
        if claim_job_id is not None and claim_token is not None:
            from .job_store import refresh_catalog_job_claim_before_commit_conn

            refresh_catalog_job_claim_before_commit_conn(
                conn,
                claim_job_id,
                claim_token,
                lease_seconds=claim_lease_seconds,
                library_id=library_id,
            )
        return reconciled

    return run_write(reconcile, lane=LANE_NORMAL)
