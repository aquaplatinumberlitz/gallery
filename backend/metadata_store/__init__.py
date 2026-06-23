"""Persist gallery file indexes, extracted metadata, job queues, and search queries."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "backend.metadata_store"

from ..albums import build_album_metadata
from ..config import (
    ENABLE_WARM_INDEXED_LISTING,
    GALLERY_METADATA_DB,
    THUMBNAIL_CACHE_DIR,
)
from ..config import (
    GALLERY_CATALOG_WRITE_BATCH_SIZE as GALLERY_CATALOG_WRITE_BATCH_SIZE,
)
from ..config import (
    PATH_SAFETY_ROOT as PATH_SAFETY_ROOT,
)
from ..files import asset_type_for_path, is_asset_path, is_image_path, is_index_excluded_path
from ..metadata_extract import (
    ExtractedMetadata,
    contains_cjk,
    extract_metadata,
    parse_float,
    parse_int,
    safe_text,
    sanitize_metadata_for_json,
)
from ..models import FileNode, VideoFileNode
from . import _db as _db
from . import path_utils as path_utils
from ._asset_store import (
    _upsert_asset_conn as _upsert_asset_conn,
)
from ._db import (
    _DB_INITIALIZED as _DB_INITIALIZED,
)
from ._db import (
    _DB_INITIALIZED_PATH as _DB_INITIALIZED_PATH,
)
from ._db import (
    _DB_LOCK as _DB_LOCK,
)
from ._db import (
    ACTIVE_ASSET_WHERE as ACTIVE_ASSET_WHERE,
)
from ._db import (
    LIBRARY_JOB_ACTIVE_STATES as LIBRARY_JOB_ACTIVE_STATES,
)
from ._db import (
    LIBRARY_JOB_TERMINAL_STATES as LIBRARY_JOB_TERMINAL_STATES,
)
from ._db import (
    MAX_METADATA_JOB_ATTEMPTS as MAX_METADATA_JOB_ATTEMPTS,
)
from ._db import (
    METADATA_JOB_STATES as METADATA_JOB_STATES,
)
from ._db import (
    _active_asset_where as _active_asset_where,
)
from ._db import (
    _connect as _connect,
)
from ._db import (
    _database_has_application_tables as _database_has_application_tables,
)
from ._db import (
    _ensure_column as _ensure_column,
)
from ._db import (
    _table_columns as _table_columns,
)
from ._db import (
    _table_exists as _table_exists,
)
from ._db import (
    init_db as init_db,
)
from ._resources import (
    _backfill_image_resources_conn as _backfill_image_resources_conn,
)
from ._resources import (
    _clean_resource_text as _clean_resource_text,
)
from ._resources import (
    _iter_metadata_loras as _iter_metadata_loras,
)
from ._resources import (
    _iter_metadata_resources as _iter_metadata_resources,
)
from ._resources import (
    _lora_summary as _lora_summary,
)
from ._resources import (
    _normalize_resource_kind as _normalize_resource_kind,
)
from ._resources import (
    _replace_image_resources_conn as _replace_image_resources_conn,
)
from ._resources import (
    _resource_raw_json as _resource_raw_json,
)
from ._resources import (
    _resource_rows_from_metadata as _resource_rows_from_metadata,
)
from ._resources import (
    _split_lora_text as _split_lora_text,
)
from .browse_store import (
    _browse_availability_from_library_state as _browse_availability_from_library_state,
)
from .browse_store import (
    _browse_folder_counts_batch_conn as _browse_folder_counts_batch_conn,
)
from .browse_store import (
    _browse_folder_counts_conn as _browse_folder_counts_conn,
)
from .browse_store import (
    _browse_import_paths_conn as _browse_import_paths_conn,
)
from .browse_store import (
    _browse_import_root_name as _browse_import_root_name,
)
from .browse_store import (
    _browse_visibility_sql as _browse_visibility_sql,
)
from .browse_store import (
    _catalog_browse_path_conn as _catalog_browse_path_conn,
)
from .browse_store import (
    _catalog_browse_virtual_root_conn as _catalog_browse_virtual_root_conn,
)
from .browse_store import (
    _import_root_availability as _import_root_availability,
)
from .browse_store import (
    _validate_browse_scope as _validate_browse_scope,
)
from .browse_store import (
    get_asset_folder_listing as get_asset_folder_listing,
)
from .browse_store import (
    get_catalog_browse_listing as get_catalog_browse_listing,
)
from .job_store import (
    _job_scope_covers as _job_scope_covers,
)
from .job_store import (
    _serialize_catalog_enqueue_result as _serialize_catalog_enqueue_result,
)
from .job_store import (
    _serialize_library_job as _serialize_library_job,
)
from .job_store import (
    claim_next_catalog_job as claim_next_catalog_job,
)
from .job_store import (
    create_job as create_job,
)
from .job_store import (
    create_or_coalesce_catalog_job as create_or_coalesce_catalog_job,
)
from .job_store import (
    create_or_get_active_scan_job as create_or_get_active_scan_job,
)
from .job_store import (
    enqueue_startup_catalog_scans as enqueue_startup_catalog_scans,
)
from .job_store import (
    get_job as get_job,
)
from .job_store import (
    get_library_jobs as get_library_jobs,
)
from .job_store import (
    list_active_jobs as list_active_jobs,
)
from .job_store import (
    list_jobs as list_jobs,
)
from .job_store import (
    recover_stale_jobs as recover_stale_jobs,
)
from .job_store import (
    update_job_state as update_job_state,
)
from .library_store import (
    _assert_no_import_path_overlap_conn as _assert_no_import_path_overlap_conn,
)
from .library_store import (
    _ensure_default_library_conn as _ensure_default_library_conn,
)
from .library_store import (
    _find_library_for_path_conn as _find_library_for_path_conn,
)
from .library_store import (
    _library_exclusion_patterns_conn as _library_exclusion_patterns_conn,
)
from .library_store import (
    _reconcile_library_configuration_conn as _reconcile_library_configuration_conn,
)
from .library_store import (
    _replace_library_paths_conn as _replace_library_paths_conn,
)
from .library_store import (
    _replace_library_patterns_conn as _replace_library_patterns_conn,
)
from .library_store import (
    _serialize_library_conn as _serialize_library_conn,
)
from .library_store import (
    create_library as create_library,
)
from .library_store import (
    get_asset_state_for_path as get_asset_state_for_path,
)
from .library_store import (
    get_first_library_root as get_first_library_root,
)
from .library_store import (
    get_gallery_stats as get_gallery_stats,
)
from .library_store import (
    get_library as get_library,
)
from .library_store import (
    get_library_for_path as get_library_for_path,
)
from .library_store import (
    get_library_progress as get_library_progress,
)
from .library_store import (
    get_library_stats as get_library_stats,
)
from .library_store import (
    list_libraries as list_libraries,
)
from .library_store import (
    register_library as register_library,
)
from .library_store import (
    unregister_library as unregister_library,
)
from .library_store import (
    update_library as update_library,
)
from .library_store import (
    update_library_state as update_library_state,
)
from .path_utils import (
    _catalog_paths_overlap as _catalog_paths_overlap,
)
from .path_utils import (
    _compare_natural_sql as _compare_natural_sql,
)
from .path_utils import (
    _natural_sort_parts as _natural_sort_parts,
)
from .path_utils import (
    _path_is_within as _path_is_within,
)
from .path_utils import (
    canonicalize_catalog_path as canonicalize_catalog_path,
)
from .path_utils import (
    catalog_path_contains as catalog_path_contains,
)
from .rebuild_store import (
    _reconcile_assets_conn as _reconcile_assets_conn,
)
from .rebuild_store import (
    activate_rebuild_staging as activate_rebuild_staging,
)
from .rebuild_store import (
    delete_rebuild_staging as delete_rebuild_staging,
)
from .rebuild_store import (
    enumerate_to_rebuild_staging as enumerate_to_rebuild_staging,
)
from .rebuild_store import (
    reconcile_library_assets as reconcile_library_assets,
)
from .types import (
    CachedDimensions as CachedDimensions,
)
from .types import (
    CatalogBrowseScopeError as CatalogBrowseScopeError,
)
from .types import (
    CatalogJobConflict as CatalogJobConflict,
)
from .types import (
    LibraryOverlapError as LibraryOverlapError,
)
from .types import (
    MetadataIndexJob as MetadataIndexJob,
)
from .types import (
    MetadataQueueResult as MetadataQueueResult,
)

SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
CATALOG_SCHEMA_VERSION = 9
logger = logging.getLogger(__name__)


def _v9_backup_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return GALLERY_METADATA_DB.with_name(
        f"{GALLERY_METADATA_DB.stem}.v8-backup-{timestamp}{GALLERY_METADATA_DB.suffix}"
    )


def _backup_database_before_v9(conn: sqlite3.Connection) -> Path:
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    backup_path = _v9_backup_path()
    suffix = 1
    while backup_path.exists():
        backup_path = backup_path.with_name(
            f"{GALLERY_METADATA_DB.stem}.v8-backup-"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{suffix}{GALLERY_METADATA_DB.suffix}"
        )
        suffix += 1
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as backup_conn:
        conn.backup(backup_conn)
    return backup_path


def _v9_import_paths(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT lip.library_id, lip.path, l.name AS library_name
        FROM library_import_paths AS lip
        JOIN libraries AS l ON l.id = lip.library_id
        ORDER BY lip.library_id, lip.position, lip.id
        """
    ).fetchall()


def _format_path_conflict(left: sqlite3.Row, right: sqlite3.Row) -> str:
    return (
        f"library {left['library_id']} ({left['path']}) conflicts with library {right['library_id']} ({right['path']})"
    )


def _validate_v9_preflight(conn: sqlite3.Connection) -> None:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version != 8:
        raise RuntimeError(f"Catalog v9 migration requires an existing v8 database, found v{version}")

    missing_import_paths = conn.execute(
        """
        SELECT l.id, l.name
        FROM libraries AS l
        WHERE NOT EXISTS (
          SELECT 1 FROM library_import_paths AS lip WHERE lip.library_id = l.id
        )
        ORDER BY l.id
        """
    ).fetchall()
    if missing_import_paths:
        ids = ", ".join(f"{row['id']}:{row['name']}" for row in missing_import_paths)
        raise RuntimeError(f"Catalog v9 migration preflight failed: libraries without import paths: {ids}")

    import_paths = _v9_import_paths(conn)
    for index, left in enumerate(import_paths):
        left_path = canonicalize_catalog_path(left["path"])
        for right in import_paths[index + 1 :]:
            right_path = canonicalize_catalog_path(right["path"])
            if _catalog_paths_overlap(left_path, right_path):
                raise RuntimeError(
                    "Catalog v9 migration preflight failed: overlapping import paths: "
                    f"{_format_path_conflict(left, right)}"
                )
            try:
                left_resolved = canonicalize_catalog_path(Path(left["path"]).resolve())
                right_resolved = canonicalize_catalog_path(Path(right["path"]).resolve())
            except (OSError, RuntimeError):
                continue
            if _catalog_paths_overlap(left_resolved, right_resolved):
                raise RuntimeError(
                    "Catalog v9 migration preflight failed: resolved import path aliases: "
                    f"{_format_path_conflict(left, right)}"
                )

    ownership_paths = [(int(row["library_id"]), canonicalize_catalog_path(row["path"])) for row in import_paths]

    def assigned_libraries(path: str) -> list[int]:
        canonical = canonicalize_catalog_path(path)
        return [library_id for library_id, root in ownership_paths if catalog_path_contains(root, canonical)]

    for table_name in ("assets", "file_index"):
        if not _table_exists(conn, table_name):
            continue
        for row in conn.execute(f"SELECT path FROM {table_name} WHERE path IS NOT NULL"):
            owners = assigned_libraries(str(row["path"]))
            if len(owners) != 1:
                raise RuntimeError(
                    "Catalog v9 migration preflight failed: "
                    f"{table_name} row {row['path']} maps to {len(owners)} libraries"
                )

    if _table_exists(conn, "assets") and "library_id" in _table_columns(conn, "assets"):
        for row in conn.execute("SELECT library_id, path FROM assets WHERE path IS NOT NULL"):
            owners = assigned_libraries(str(row["path"]))
            if owners and owners[0] != int(row["library_id"]):
                raise RuntimeError(
                    "Catalog v9 migration preflight failed: "
                    f"asset {row['path']} belongs to library {owners[0]}, not {row['library_id']}"
                )


def _rebuild_libraries_without_root_path(conn: sqlite3.Connection) -> None:
    if "root_path" not in _table_columns(conn, "libraries"):
        return
    conn.execute(
        """
        CREATE TABLE libraries_v9 (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'discovering',
          watch_enabled INTEGER NOT NULL DEFAULT 1,
          warm_enabled INTEGER NOT NULL DEFAULT 1,
          created_at REAL NOT NULL DEFAULT (julianday('now')),
          updated_at REAL NOT NULL DEFAULT (julianday('now')),
          last_scan_at REAL,
          last_error TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO libraries_v9 (
          id, name, state, watch_enabled, warm_enabled,
          created_at, updated_at, last_scan_at, last_error
        )
        SELECT id, name, state, watch_enabled, warm_enabled,
               created_at, updated_at, last_scan_at, last_error
        FROM libraries
        ORDER BY id
        """
    )
    conn.execute("DROP TABLE libraries")
    conn.execute("ALTER TABLE libraries_v9 RENAME TO libraries")


def _ensure_v9_catalog_schema(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "library_jobs", "scope_path", "TEXT")
    _ensure_column(conn, "library_jobs", "trigger", "TEXT NOT NULL DEFAULT 'manual'")
    _ensure_column(conn, "library_jobs", "priority", "INTEGER NOT NULL DEFAULT 50")
    _ensure_column(conn, "library_jobs", "discovered_assets", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "library_jobs", "created_assets", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "library_jobs", "updated_assets", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "library_jobs", "offline_assets", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "library_jobs", "metadata_queued_assets", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "file_index", "library_id", "INTEGER REFERENCES libraries(id) ON DELETE SET NULL")
    _ensure_column(conn, "file_index", "mtime_ns", "INTEGER")
    _ensure_column(conn, "file_index", "last_seen_scan_job_id", "INTEGER")
    _ensure_column(conn, "assets", "mime_type", "TEXT")
    _ensure_column(conn, "assets", "duration_ms", "INTEGER")
    _ensure_column(conn, "assets", "codec", "TEXT")
    _ensure_column(conn, "assets", "last_seen_scan_job_id", "INTEGER")
    _ensure_column(conn, "metadata_index_jobs", "mtime_ns", "INTEGER")
    _ensure_column(conn, "image_metadata", "mtime_ns", "INTEGER")
    statements = [
        """
        CREATE INDEX IF NOT EXISTS idx_library_jobs_catalog_pick
          ON library_jobs(library_id, type, state, scope_path)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_library_jobs_state_priority_created
          ON library_jobs(state, priority DESC, created_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_assets_reconcile_scan
          ON assets(library_id, parent_path, last_seen_scan_job_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_assets_library_seen
          ON assets(library_id, last_seen_scan_job_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_file_index_library_parent_seen
          ON file_index(library_id, parent_path, last_seen_scan_job_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS catalog_rebuild_entries (
          job_id INTEGER NOT NULL REFERENCES library_jobs(id) ON DELETE CASCADE,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          path TEXT NOT NULL,
          parent_path TEXT NOT NULL,
          name TEXT NOT NULL,
          type TEXT NOT NULL,
          mtime_ns INTEGER,
          size INTEGER,
          width INTEGER,
          height INTEGER,
          mime_type TEXT,
          duration_ms INTEGER,
          codec TEXT,
          created_at REAL NOT NULL,
          PRIMARY KEY(job_id, path)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_library_job
          ON catalog_rebuild_entries(library_id, job_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_parent
          ON catalog_rebuild_entries(library_id, parent_path)
        """,
    ]
    for statement in statements:
        conn.execute(statement)


def _populate_v9_file_index_library_ids(conn: sqlite3.Connection) -> None:
    import_paths = [(int(row["library_id"]), canonicalize_catalog_path(row["path"])) for row in _v9_import_paths(conn)]
    rows = conn.execute("SELECT path FROM file_index WHERE library_id IS NULL").fetchall()
    updates = []
    for row in rows:
        owners = [
            library_id
            for library_id, root_path in import_paths
            if catalog_path_contains(root_path, canonicalize_catalog_path(row["path"]))
        ]
        if len(owners) == 1:
            updates.append((owners[0], row["path"]))
    if updates:
        conn.executemany("UPDATE file_index SET library_id = ? WHERE path = ?", updates)


def _migrate_v8_to_v9(conn: sqlite3.Connection) -> None:
    _validate_v9_preflight(conn)
    backup_path = _backup_database_before_v9(conn)
    logger.info("Created catalog v8 backup before v9 migration: %s", backup_path)

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_v9_catalog_schema(conn)
        _populate_v9_file_index_library_ids(conn)
        now = time.time()
        conn.execute(
            """
            UPDATE library_jobs
            SET state = CASE WHEN state = 'running' THEN 'failed' ELSE 'cancelled' END,
                message = COALESCE(message, 'Closed by catalog v9 migration'),
                error = 'Closed by catalog v9 migration',
                updated_at = ?,
                finished_at = COALESCE(finished_at, ?)
            WHERE type IN ('repair', 'scan_all') AND state IN ('queued', 'running')
            """,
            (now, now),
        )
        _rebuild_libraries_without_root_path(conn)
        if "root_path" in _table_columns(conn, "libraries"):
            raise RuntimeError("Catalog v9 migration failed to remove libraries.root_path")
        conn.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
        if int(conn.execute("PRAGMA user_version").fetchone()[0]) != CATALOG_SCHEMA_VERSION:
            raise RuntimeError("Catalog v9 migration failed to advance schema version")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v9 migration: {violations}")


def initialize_database() -> None:
    """Create or migrate the SQLite metadata database once per configured DB path."""
    if _db._DB_INITIALIZED and _db._DB_INITIALIZED_PATH == GALLERY_METADATA_DB:
        return

    with _db._DB_LOCK:
        if _db._DB_INITIALIZED and _db._DB_INITIALIZED_PATH == GALLERY_METADATA_DB:
            return

        with _connect(set_journal_mode=True) as conn:
            _initialize_database_conn(conn)

        _db._DB_INITIALIZED = True
        _db._DB_INITIALIZED_PATH = GALLERY_METADATA_DB


def _initialize_database_conn(conn: sqlite3.Connection) -> None:
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_application_tables = _database_has_application_tables(conn)
    if current_version == 8:
        _migrate_v8_to_v9(conn)
        current_version = CATALOG_SCHEMA_VERSION
    elif current_version == 0 and has_application_tables:
        raise RuntimeError(
            "Catalog database has application tables but no schema version; "
            f"restore or migrate it to v8 before v{CATALOG_SCHEMA_VERSION}"
        )
    elif current_version not in (0, CATALOG_SCHEMA_VERSION):
        raise RuntimeError(
            "Catalog database must be a fresh database or an existing v8 database "
            f"to migrate to v{CATALOG_SCHEMA_VERSION}; found v{current_version}"
        )

    had_file_index_table = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'file_index'").fetchone() is not None
    )

    conn.executescript(
        """
            CREATE TABLE IF NOT EXISTS image_metadata (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              mtime REAL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              format TEXT,
              mode TEXT,
              has_alpha INTEGER,
              prompt TEXT,
              negative_prompt TEXT,
              model TEXT,
              sampler TEXT,
              seed TEXT,
              steps INTEGER,
              cfg_scale REAL,
              raw_metadata_text TEXT,
              metadata_json TEXT,
              updated_at REAL,
              indexed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_name
              ON image_metadata(mtime DESC, name);

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts_trigram USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='trigram'
            );

            CREATE TRIGGER IF NOT EXISTS image_metadata_ai AFTER INSERT ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_ad AFTER DELETE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_au AFTER UPDATE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TABLE IF NOT EXISTS file_index (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              type TEXT NOT NULL,
              mtime REAL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              indexed_at REAL,
              library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
              last_seen_scan_job_id INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_file_index_parent_path ON file_index(parent_path);
            CREATE INDEX IF NOT EXISTS idx_file_index_type ON file_index(type);
            CREATE INDEX IF NOT EXISTS idx_file_index_name ON file_index(name);
            CREATE INDEX IF NOT EXISTS idx_file_index_library_parent_seen
              ON file_index(library_id, parent_path, last_seen_scan_job_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS file_index_fts USING fts5(
              name,
              path UNINDEXED,
              type UNINDEXED,
              parent_path UNINDEXED,
              tokenize='unicode61'
            );

            CREATE TABLE IF NOT EXISTS metadata_index_jobs (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              folder_path TEXT NOT NULL,
              root_path TEXT NOT NULL,
              mtime REAL NOT NULL,
              mtime_ns INTEGER,
              size INTEGER NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              queued_at REAL,
              started_at REAL,
              finished_at REAL,
              updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_state
              ON metadata_index_jobs(state);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_folder_path
              ON metadata_index_jobs(folder_path);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_root_path
              ON metadata_index_jobs(root_path);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_updated_at
              ON metadata_index_jobs(updated_at);

            CREATE TABLE IF NOT EXISTS image_resources (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL,
              kind TEXT NOT NULL,
              name TEXT NOT NULL DEFAULT '',
              hash TEXT,
              resource_hash TEXT,
              weight TEXT,
              strength TEXT,
              raw_json TEXT,
              updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_image_resources_path
              ON image_resources(path);
            CREATE INDEX IF NOT EXISTS idx_image_resources_kind_name
              ON image_resources(kind, name);
            CREATE INDEX IF NOT EXISTS idx_image_resources_hash
              ON image_resources(resource_hash);
            CREATE INDEX IF NOT EXISTS idx_image_resources_hash_value
              ON image_resources(hash);

            CREATE TABLE IF NOT EXISTS folder_index_state (
              path TEXT PRIMARY KEY,
              dir_mtime_ns INTEGER NOT NULL,
              indexed_at REAL NOT NULL,
              complete INTEGER NOT NULL DEFAULT 0,
              child_count INTEGER NOT NULL DEFAULT 0,
              folder_count INTEGER NOT NULL DEFAULT 0,
              image_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS libraries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'discovering',
              watch_enabled INTEGER NOT NULL DEFAULT 1,
              warm_enabled INTEGER NOT NULL DEFAULT 1,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              last_scan_at REAL,
              last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS library_import_paths (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, path),
              UNIQUE(library_id, position)
            );
            CREATE INDEX IF NOT EXISTS idx_library_import_paths_path
              ON library_import_paths(path);

            CREATE TABLE IF NOT EXISTS library_exclusion_patterns (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              pattern TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, pattern),
              UNIQUE(library_id, position)
            );

            CREATE TABLE IF NOT EXISTS library_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
              parent_job_id INTEGER REFERENCES library_jobs(id) ON DELETE SET NULL,
              type TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'queued',
              scope_path TEXT,
              trigger TEXT NOT NULL DEFAULT 'manual',
              priority INTEGER NOT NULL DEFAULT 50,
              progress_current INTEGER NOT NULL DEFAULT 0,
              progress_total INTEGER,
              message TEXT,
              error TEXT,
              counters TEXT NOT NULL DEFAULT '{}',
              discovered_assets INTEGER NOT NULL DEFAULT 0,
              created_assets INTEGER NOT NULL DEFAULT 0,
              updated_assets INTEGER NOT NULL DEFAULT 0,
              offline_assets INTEGER NOT NULL DEFAULT 0,
              metadata_queued_assets INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              started_at REAL,
              finished_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_library_jobs_library_created
              ON library_jobs(library_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state
              ON library_jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_catalog_pick
              ON library_jobs(library_id, type, state, scope_path);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state_priority_created
              ON library_jobs(state, priority DESC, created_at);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_parent
              ON library_jobs(parent_job_id);

            CREATE TABLE IF NOT EXISTS assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id),
              path TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL DEFAULT 'image',
              mtime_ns REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              orientation INTEGER,
              indexed_at REAL,
              metadata_state TEXT DEFAULT 'pending',
              offline INTEGER NOT NULL DEFAULT 0,
              deleted_at REAL,
              mime_type TEXT,
              duration_ms INTEGER,
              codec TEXT,
              last_seen_scan_job_id INTEGER,
              UNIQUE(library_id, path)
            );
            CREATE INDEX IF NOT EXISTS idx_assets_library_path ON assets(library_id, path);
            CREATE INDEX IF NOT EXISTS idx_assets_library_parent ON assets(library_id, parent_path);
            CREATE INDEX IF NOT EXISTS idx_assets_reconcile_scan
              ON assets(library_id, parent_path, last_seen_scan_job_id);
            CREATE INDEX IF NOT EXISTS idx_assets_library_seen
              ON assets(library_id, last_seen_scan_job_id);

            CREATE TABLE IF NOT EXISTS asset_derivatives (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id INTEGER NOT NULL REFERENCES assets(id),
              kind TEXT NOT NULL,
              variant TEXT NOT NULL,
              source_mtime_ns REAL NOT NULL,
              source_size INTEGER NOT NULL,
              format TEXT NOT NULL DEFAULT 'webp',
              quality INTEGER NOT NULL DEFAULT 85,
              max_long_edge INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              cache_path TEXT,
              byte_size INTEGER,
              last_accessed_at REAL,
              attempts INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              UNIQUE(asset_id, kind, variant, source_mtime_ns, source_size)
            );
            CREATE INDEX IF NOT EXISTS idx_derivatives_status ON asset_derivatives(status);
            CREATE INDEX IF NOT EXISTS idx_derivatives_asset ON asset_derivatives(asset_id);

            CREATE TABLE IF NOT EXISTS derivative_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              derivative_id INTEGER NOT NULL REFERENCES asset_derivatives(id),
              priority INTEGER NOT NULL DEFAULT 3,
              state TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              started_at REAL,
              completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state ON derivative_jobs(state, priority);

            CREATE TABLE IF NOT EXISTS catalog_rebuild_entries (
              job_id INTEGER NOT NULL REFERENCES library_jobs(id) ON DELETE CASCADE,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              mime_type TEXT,
              duration_ms INTEGER,
              codec TEXT,
              created_at REAL NOT NULL,
              PRIMARY KEY(job_id, path)
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_library_job
              ON catalog_rebuild_entries(library_id, job_id);
            CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_parent
              ON catalog_rebuild_entries(library_id, parent_path);
            """
    )
    _ensure_column(conn, "image_metadata", "format", "TEXT")
    _ensure_column(conn, "image_metadata", "mode", "TEXT")
    _ensure_column(conn, "image_metadata", "has_alpha", "INTEGER")
    _ensure_column(conn, "image_metadata", "updated_at", "REAL")
    _ensure_column(conn, "image_metadata", "tool", "TEXT")
    _ensure_column(conn, "image_metadata", "scheduler", "TEXT")
    _ensure_column(conn, "image_metadata", "model_hash", "TEXT")
    _ensure_column(conn, "image_metadata", "lora_text", "TEXT")
    _ensure_column(conn, "image_metadata", "generation_time", "REAL")
    _ensure_column(conn, "image_metadata", "clip_skip", "INTEGER")
    _ensure_column(conn, "image_metadata", "hires_upscale", "REAL")
    _ensure_column(conn, "image_metadata", "hires_steps", "INTEGER")
    _ensure_column(conn, "image_metadata", "denoising_strength", "REAL")
    _ensure_column(conn, "image_metadata", "vae", "TEXT")
    _ensure_column(conn, "image_metadata", "ensd", "INTEGER")
    _ensure_column(conn, "image_metadata", "aesthetic_score", "REAL")
    _ensure_column(conn, "image_metadata", "date", "TEXT")
    _ensure_column(conn, "image_metadata", "aspect_ratio", "TEXT")
    conn.execute(
        """
            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_size
              ON image_metadata(path, mtime, size)
            """
    )
    _ensure_column(conn, "metadata_index_jobs", "folder_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "metadata_index_jobs", "root_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_v9_catalog_schema(conn)

    if not has_application_tables and current_version == 0:
        conn.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
        _cleanup_ignored_index_conn(conn)
        return

    if current_version == CATALOG_SCHEMA_VERSION:
        _cleanup_ignored_index_conn(conn)
        return

    if current_version < 1:
        conn.execute("UPDATE image_metadata SET width = NULL, height = NULL")
        conn.execute("UPDATE file_index SET width = NULL, height = NULL")
        conn.execute("PRAGMA user_version = 1")

    if current_version < 2:
        _backfill_image_resources_conn(conn)
        conn.execute("PRAGMA user_version = 2")

    if current_version < 3:
        conn.execute(
            """
            UPDATE file_index
            SET width = COALESCE(file_index.width, dimensions.width),
                height = COALESCE(file_index.height, dimensions.height)
            FROM (
              SELECT path, width, height
              FROM image_metadata
              WHERE width IS NOT NULL OR height IS NOT NULL
            ) AS dimensions
            WHERE file_index.path = dimensions.path
              AND (file_index.width IS NULL OR file_index.height IS NULL)
            """
        )
        conn.execute("PRAGMA user_version = 3")

    if current_version < 4:
        if had_file_index_table:
            default_library_id = _ensure_default_library_conn(conn)
            conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  width, height, indexed_at, metadata_state
                )
                SELECT ?, fi.path, fi.parent_path, fi.name,
                       CASE WHEN fi.type = 'photo' THEN 'image' ELSE 'folder' END,
                       fi.mtime, fi.size, fi.width, fi.height, fi.indexed_at,
                       CASE WHEN im.path IS NULL THEN 'pending' ELSE 'done' END
                FROM file_index AS fi
                LEFT JOIN image_metadata AS im ON im.path = fi.path
                WHERE 1
                ON CONFLICT(library_id, path) DO UPDATE SET
                  parent_path=excluded.parent_path,
                  name=excluded.name,
                  type=excluded.type,
                  mtime_ns=excluded.mtime_ns,
                  size=excluded.size,
                  width=COALESCE(excluded.width, assets.width),
                  height=COALESCE(excluded.height, assets.height),
                  indexed_at=excluded.indexed_at,
                  metadata_state=excluded.metadata_state
                """,
                (default_library_id,),
            )
        conn.execute("PRAGMA user_version = 4")

    if current_version < 5:
        _import_cached_derivatives_conn(conn)
        conn.execute("PRAGMA user_version = 5")

    if current_version < 6:
        unix_epoch_expression = "(value - 2440587.5) * 86400.0"
        for column in ("created_at", "updated_at", "last_scan_at"):
            conn.execute(
                f"""
                UPDATE libraries
                SET {column} = {unix_epoch_expression.replace("value", column)}
                WHERE {column} >= 2000000 AND {column} < 3000000
                """
            )
        now = time.time()
        conn.execute(
            """
            INSERT INTO library_import_paths (
              library_id, path, position, created_at, updated_at
            )
            SELECT l.id, l.root_path, 0, ?, ?
            FROM libraries AS l
            WHERE NOT EXISTS (
              SELECT 1 FROM library_import_paths AS lip WHERE lip.library_id = l.id
            )
            """,
            (now, now),
        )
        missing = conn.execute(
            """
            SELECT count(*)
            FROM libraries AS l
            WHERE NOT EXISTS (
              SELECT 1 FROM library_import_paths AS lip WHERE lip.library_id = l.id
            )
            """
        ).fetchone()[0]
        if missing:
            raise RuntimeError("Library import-path migration left libraries without import paths")
        conn.execute("PRAGMA user_version = 6")

    if current_version < 7:
        conn.execute("PRAGMA user_version = 7")
        current_version = 7

    if current_version == 7:
        conn.executescript(
            """
            ALTER TABLE assets ADD COLUMN mime_type TEXT;
            ALTER TABLE assets ADD COLUMN duration_ms INTEGER;
            ALTER TABLE assets ADD COLUMN codec TEXT;
            PRAGMA user_version = 8;
            """
        )

    _cleanup_ignored_index_conn(conn)


def _import_cached_derivatives_conn(conn: sqlite3.Connection) -> None:
    """Best-effort import of legacy persisted derivative files."""
    cache_dir = THUMBNAIL_CACHE_DIR / "files"
    cache_files = {path.stem: path for path in cache_dir.iterdir() if path.is_file()} if cache_dir.is_dir() else {}
    imported = 0
    variants = (
        ("thumbnail", "default", 512, 78),
        ("preview", "default", 1440, 86),
    )
    for asset in conn.execute("SELECT id, path FROM assets WHERE type = 'image' AND deleted_at IS NULL"):
        source = Path(asset["path"])
        try:
            stat = source.stat()
        except OSError:
            continue
        for kind, variant, max_long_edge, quality in variants:
            key = (
                f"{kind}:v2:{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:"
                f"edge={max_long_edge}:fmt=webp:q={quality}"
            )
            cached = cache_files.get(hashlib.sha256(key.encode("utf-8")).hexdigest())
            if cached is None:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO asset_derivatives (
                  asset_id, kind, variant, source_mtime_ns, source_size, format,
                  quality, max_long_edge, status, cache_path, byte_size, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, 'webp', ?, ?, 'ready', ?, ?, julianday('now'))
                """,
                (
                    asset["id"],
                    kind,
                    variant,
                    float(stat.st_mtime_ns),
                    stat.st_size,
                    quality,
                    max_long_edge,
                    str(cached),
                    cached.stat().st_size,
                ),
            )
            imported += int(conn.execute("SELECT changes()").fetchone()[0])
    logger.info("Imported %d of %d cached derivative files", imported, len(cache_files))


def _current_metadata_is_complete(conn: sqlite3.Connection, path: str, mtime: float, size: int) -> bool:
    row = conn.execute(
        """
        SELECT mtime, size, metadata_json
        FROM image_metadata
        WHERE path = ?
        """,
        (path,),
    ).fetchone()
    if row is None:
        return False
    return row["mtime"] == mtime and row["size"] == size and bool(row["metadata_json"])


def _metadata_job_from_path(path_value: str | Path, root_path: str | Path | None = None) -> MetadataIndexJob | None:
    path = Path(path_value)
    if is_index_excluded_path(path) or not is_image_path(path):
        return None
    try:
        stat = path.stat()
        resolved_path = path.resolve()
        parent = resolved_path.parent
    except OSError:
        return None
    resolved_root = str(Path(root_path).resolve()) if root_path is not None else str(parent)
    return MetadataIndexJob(
        path=str(resolved_path),
        name=resolved_path.name,
        parent_path=str(parent),
        folder_path=str(parent),
        root_path=resolved_root,
        mtime=stat.st_mtime,
        size=stat.st_size,
    )


def _mark_current_metadata_done(conn: sqlite3.Connection, job: MetadataIndexJob, now: float) -> None:
    conn.execute(
        """
        INSERT INTO metadata_index_jobs (
          path, name, parent_path, folder_path, root_path, mtime, size, state,
          attempts, error, queued_at, started_at, finished_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'done', 0, NULL, ?, NULL, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          name=excluded.name,
          parent_path=excluded.parent_path,
          folder_path=excluded.folder_path,
          root_path=excluded.root_path,
          mtime=excluded.mtime,
          size=excluded.size,
          state='done',
          error=NULL,
          finished_at=excluded.finished_at,
          updated_at=excluded.updated_at
        """,
        (
            job.path,
            job.name,
            job.parent_path,
            job.folder_path,
            job.root_path,
            job.mtime,
            job.size,
            now,
            now,
            now,
        ),
    )


def queue_metadata_index_paths(paths: Iterable[str | Path], root_path: str | Path | None = None) -> MetadataQueueResult:
    """Create/coalesce metadata index jobs for image paths without parsing files."""
    jobs = [job for path in paths if (job := _metadata_job_from_path(path, root_path))]
    if not jobs:
        return MetadataQueueResult(enqueued=[])

    initialize_database()
    enqueued: list[MetadataIndexJob] = []
    coalesced = 0
    skipped = 0
    failed = 0
    now = time.time()

    with _DB_LOCK, _connect() as conn:
        for job in jobs:
            if _current_metadata_is_complete(conn, job.path, job.mtime, job.size):
                _mark_current_metadata_done(conn, job, now)
                skipped += 1
                continue

            existing = conn.execute(
                """
                SELECT mtime, size, state, attempts
                FROM metadata_index_jobs
                WHERE path = ?
                """,
                (job.path,),
            ).fetchone()

            if existing and existing["mtime"] == job.mtime and existing["size"] == job.size:
                state = existing["state"]
                attempts = int(existing["attempts"] or 0)
                if state in {"queued", "running"}:
                    coalesced += 1
                    continue
                if state == "failed" and attempts >= MAX_METADATA_JOB_ATTEMPTS:
                    failed += 1
                    continue
                if state == "done" and _current_metadata_is_complete(conn, job.path, job.mtime, job.size):
                    skipped += 1
                    continue

            conn.execute(
                """
                INSERT INTO metadata_index_jobs (
                  path, name, parent_path, folder_path, root_path, mtime, size,
                  state, attempts, error, queued_at, started_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, ?, NULL, NULL, ?)
                ON CONFLICT(path) DO UPDATE SET
                  name=excluded.name,
                  parent_path=excluded.parent_path,
                  folder_path=excluded.folder_path,
                  root_path=excluded.root_path,
                  mtime=excluded.mtime,
                  size=excluded.size,
                  state='queued',
                  attempts=CASE
                    WHEN metadata_index_jobs.mtime = excluded.mtime
                     AND metadata_index_jobs.size = excluded.size
                    THEN metadata_index_jobs.attempts
                    ELSE 0
                  END,
                  error=NULL,
                  queued_at=excluded.queued_at,
                  started_at=NULL,
                  finished_at=NULL,
                  updated_at=excluded.updated_at
                """,
                (
                    job.path,
                    job.name,
                    job.parent_path,
                    job.folder_path,
                    job.root_path,
                    job.mtime,
                    job.size,
                    now,
                    now,
                ),
            )
            enqueued.append(job)

    return MetadataQueueResult(enqueued=enqueued, coalesced=coalesced, skipped=skipped, failed=failed)


def mark_metadata_jobs_running(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as running and increment their attempt counts."""
    rows = list(jobs)
    if not rows:
        return
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='running',
                attempts=attempts + 1,
                error=NULL,
                started_at=?,
                finished_at=NULL,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_done(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs as successfully completed."""
    rows = list(jobs)
    if not rows:
        return
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='done',
                error=NULL,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_stale(jobs: Iterable[MetadataIndexJob]) -> None:
    """Mark durable metadata jobs stale when the file version no longer matches."""
    rows = list(jobs)
    if not rows:
        return
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='stale',
                error=NULL,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((now, now, job.path, job.mtime, job.size) for job in rows),
        )


def mark_metadata_jobs_failed(errors: Iterable[tuple[MetadataIndexJob, str]]) -> None:
    """Mark durable metadata jobs failed with a bounded error message."""
    rows = [(job, error[:1000]) for job, error in errors]
    if not rows:
        return
    initialize_database()
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        conn.executemany(
            """
            UPDATE metadata_index_jobs
            SET state='failed',
                error=?,
                finished_at=?,
                updated_at=?
            WHERE path=? AND mtime=? AND size=?
            """,
            ((error, now, now, job.path, job.mtime, job.size) for job, error in rows),
        )


def get_metadata_index_status(path: str | Path | None = None) -> dict[str, Any]:
    """Return durable metadata job counts, optionally scoped to a path subtree."""
    initialize_database()
    counts = dict.fromkeys(METADATA_JOB_STATES, 0)
    where = ""
    params: list[Any] = []
    root = ""
    if path:
        resolved = str(Path(path).resolve())
        root = resolved
        prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
        where = "WHERE (path = ? OR path LIKE ? ESCAPE '\\')"
        params = [resolved, f"{_like_escape(prefix)}%"]

    with _DB_LOCK, _connect() as conn:
        for row in conn.execute(
            f"""
            SELECT state, count(*) AS total
            FROM metadata_index_jobs
            {where}
            GROUP BY state
            """,
            params,
        ):
            if row["state"] in counts:
                counts[row["state"]] = int(row["total"])

        last_error_row = conn.execute(
            f"""
            SELECT path, error, updated_at
            FROM metadata_index_jobs
            {where + (" AND" if where else "WHERE")} state = 'failed' AND error IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        oldest_queued_row = conn.execute(
            f"""
            SELECT min(queued_at) AS oldest_queued_at
            FROM metadata_index_jobs
            {where + (" AND" if where else "WHERE")} state = 'queued'
            """,
            params,
        ).fetchone()

        updated_row = conn.execute(
            f"""
            SELECT max(updated_at) AS updated_at
            FROM metadata_index_jobs
            {where}
            """,
            params,
        ).fetchone()

        indexed_photos_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM file_index
            {where + (" AND" if where else "WHERE")} type IN ('image', 'photo')
            """,
            params,
        ).fetchone()

        metadata_scope = ""
        metadata_params: list[Any] = []
        if path:
            resolved = str(Path(path).resolve())
            prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
            metadata_scope = "AND (fi.path = ? OR fi.path LIKE ? ESCAPE '\\')"
            metadata_params = [resolved, f"{_like_escape(prefix)}%"]
        metadata_records_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE fi.type IN ('image', 'photo')
            {metadata_scope}
            """,
            metadata_params,
        ).fetchone()

    now = time.time()
    oldest_queued_at = oldest_queued_row["oldest_queued_at"] if oldest_queued_row else None
    indexed_photos = int(indexed_photos_row["total"] if indexed_photos_row else 0)
    metadata_records = int(metadata_records_row["total"] if metadata_records_row else 0)
    return {
        "path": root,
        "total": sum(counts.values()),
        "indexed_photos": indexed_photos,
        "metadata_records": metadata_records,
        "missing_metadata_records": max(0, indexed_photos - metadata_records),
        "counts": counts,
        "queued": counts["queued"],
        "running": counts["running"],
        "done": counts["done"],
        "failed": counts["failed"],
        "stale": counts["stale"],
        "skipped": counts["skipped"],
        "oldest_queued_age_seconds": round(now - oldest_queued_at, 3) if oldest_queued_at else None,
        "last_error": {
            "path": last_error_row["path"],
            "message": last_error_row["error"],
            "updated_at": last_error_row["updated_at"],
        }
        if last_error_row
        else None,
        "updated_at": updated_row["updated_at"] if updated_row else None,
    }


def _needs_reindex(conn: sqlite3.Connection, path: Path, mtime: float, size: int) -> bool:
    row = conn.execute(
        "SELECT mtime, size, metadata_json FROM image_metadata WHERE path = ?", (str(path.resolve()),)
    ).fetchone()
    if row is None:
        return True
    return row["mtime"] != mtime or row["size"] != size or not row["metadata_json"]


def _upsert_extracted_metadata_conn(conn: sqlite3.Connection, metadata: ExtractedMetadata) -> None:
    conn.execute(
        """
        INSERT INTO image_metadata (
          path, name, mtime, size, width, height, prompt, negative_prompt,
          format, mode, has_alpha, model, sampler, seed, steps, cfg_scale,
          raw_metadata_text, metadata_json, updated_at, indexed_at,
          tool, scheduler, model_hash, lora_text, generation_time,
          clip_skip, hires_upscale, hires_steps, denoising_strength,
          vae, ensd, aesthetic_score, date, aspect_ratio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          name=excluded.name,
          mtime=excluded.mtime,
          size=excluded.size,
          width=excluded.width,
          height=excluded.height,
          format=excluded.format,
          mode=excluded.mode,
          has_alpha=excluded.has_alpha,
          prompt=excluded.prompt,
          negative_prompt=excluded.negative_prompt,
          model=excluded.model,
          sampler=excluded.sampler,
          seed=excluded.seed,
          steps=excluded.steps,
          cfg_scale=excluded.cfg_scale,
          raw_metadata_text=excluded.raw_metadata_text,
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at,
          indexed_at=excluded.indexed_at,
          tool=excluded.tool,
          scheduler=excluded.scheduler,
          model_hash=excluded.model_hash,
          lora_text=excluded.lora_text,
          generation_time=excluded.generation_time,
          clip_skip=excluded.clip_skip,
          hires_upscale=excluded.hires_upscale,
          hires_steps=excluded.hires_steps,
          denoising_strength=excluded.denoising_strength,
          vae=excluded.vae,
          ensd=excluded.ensd,
          aesthetic_score=excluded.aesthetic_score,
          date=excluded.date,
          aspect_ratio=excluded.aspect_ratio
        """,
        (
            metadata.path,
            metadata.name,
            metadata.mtime,
            metadata.size,
            metadata.width,
            metadata.height,
            metadata.prompt,
            metadata.negative_prompt,
            metadata.format,
            metadata.mode,
            metadata.has_alpha,
            metadata.model,
            metadata.sampler,
            metadata.seed,
            metadata.steps,
            metadata.cfg_scale,
            metadata.raw_metadata_text,
            metadata.metadata_json,
            metadata.indexed_at,
            metadata.indexed_at,
            metadata.tool,
            metadata.scheduler,
            metadata.model_hash,
            metadata.lora_text,
            metadata.generation_time,
            metadata.clip_skip,
            metadata.hires_upscale,
            metadata.hires_steps,
            metadata.denoising_strength,
            metadata.vae,
            metadata.ensd,
            metadata.aesthetic_score,
            metadata.date,
            metadata.aspect_ratio,
        ),
    )
    _upsert_asset_conn(
        conn,
        path=metadata.path,
        name=metadata.name,
        parent_path=Path(metadata.path).parent,
        type="image",
        mtime_ns=metadata.mtime,
        size=metadata.size,
        width=metadata.width,
        height=metadata.height,
        metadata_state="done",
        reactivate_existing=False,
    )
    _sync_dimensions_to_file_index(conn, metadata.path, metadata.width, metadata.height)
    _replace_image_resources_conn(conn, metadata.path, metadata.metadata_json, metadata.lora_text, metadata.indexed_at)


def _sync_dimensions_to_file_index(
    conn: sqlite3.Connection,
    path: str | Path,
    width: int | None,
    height: int | None,
) -> None:
    """Fill missing file-index dimensions inside the caller's transaction."""
    if width is None and height is None:
        return
    conn.execute(
        """
        UPDATE file_index
        SET width = COALESCE(?, width),
            height = COALESCE(?, height)
        WHERE path = ?
        """,
        (width, height, str(Path(path).resolve())),
    )
    conn.execute(
        """
        UPDATE assets
        SET width = COALESCE(?, width),
            height = COALESCE(?, height)
        WHERE path = ?
        """,
        (width, height, str(Path(path).resolve())),
    )


def upsert_extracted_metadata(metadata: ExtractedMetadata, *, mark_job_done: bool = False) -> bool:
    """Persist extracted metadata and optionally complete its matching current job."""
    if is_index_excluded_path(metadata.path):
        return False
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        _upsert_extracted_metadata_conn(conn, metadata)
        if mark_job_done:
            job = _metadata_job_from_path(metadata.path)
            if job is not None and job.mtime == metadata.mtime and job.size == metadata.size:
                _mark_current_metadata_done(conn, job, metadata.indexed_at)
    return True


def upsert_metadata_batch(metadata_items: Iterable[ExtractedMetadata]) -> int:
    """Write extracted metadata rows in one bounded SQLite transaction."""
    rows = list(metadata_items)
    if not rows:
        return 0
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        for metadata in rows:
            _upsert_extracted_metadata_conn(conn, metadata)
    return len(rows)


def index_image(path: Path) -> bool:
    """Extract and persist metadata for one image when its indexed file version is stale."""
    if is_index_excluded_path(path) or not is_image_path(path):
        return False
    try:
        stat = path.stat()
    except OSError:
        return False

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        if not _needs_reindex(conn, path, stat.st_mtime, stat.st_size):
            return False
        try:
            metadata = extract_metadata(path)
        except Exception:  # noqa: BLE001
            return False
        _upsert_extracted_metadata_conn(conn, metadata)
        return True


def index_images(paths: Iterable[str | Path]) -> int:
    """Index metadata for multiple image paths and return the number updated."""
    indexed = 0
    for path_value in paths:
        try:
            if index_image(Path(path_value)):
                indexed += 1
        except Exception:  # noqa: BLE001
            continue
    return indexed


def get_lightbox_metadata(path: str | Path) -> dict | None:
    """Read metadata from SQLite. Returns None if not cached or stale."""
    resolved = str(Path(path).resolve())
    try:
        stat = Path(path).stat()
    except OSError:
        return None

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM image_metadata
            WHERE path = ? AND mtime = ? AND size = ? AND metadata_json IS NOT NULL
            """,
            (resolved, stat.st_mtime, stat.st_size),
        ).fetchone()
        if row is None:
            return None

        metadata_json = row["metadata_json"]
        if not metadata_json:
            return None

        try:
            parsed = json.loads(metadata_json)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(parsed, dict):
            return None

        parsed.setdefault("tool", "Unknown")
        parsed.setdefault("prompt", row["prompt"] or "")
        parsed.setdefault("negative_prompt", row["negative_prompt"] or "")
        parsed.setdefault("params", {})
        parsed["width"] = row["width"]
        parsed["height"] = row["height"]
        parsed["name"] = row["name"]
        return parsed


def get_cached_dimensions_for_files(files: Iterable[tuple[str | Path, float, int]]) -> dict[str, CachedDimensions]:
    """Return cached dimensions for files whose mtime and size still match."""
    file_rows = [(str(Path(path).resolve()), mtime, size) for path, mtime, size in files]
    if not file_rows:
        return {}

    initialize_database()
    cached: dict[str, CachedDimensions] = {}
    expected = {path: (mtime, size) for path, mtime, size in file_rows}
    paths = list(expected)

    with _DB_LOCK, _connect() as conn:
        for start in range(0, len(paths), 900):
            chunk = paths[start : start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT path, mtime, size, width, height
                FROM image_metadata
                WHERE path IN ({placeholders})
                  AND width IS NOT NULL
                  AND height IS NOT NULL
                """,
                chunk,
            )
            for row in rows:
                expected_mtime, expected_size = expected[row["path"]]
                if row["mtime"] == expected_mtime and row["size"] == expected_size:
                    cached[row["path"]] = CachedDimensions(width=row["width"], height=row["height"])

    return cached


def update_folder_index_state(
    folder_path: str | Path,
    *,
    dir_mtime_ns: int | None = None,
    complete: bool = False,
    child_count: int = 0,
    folder_count: int = 0,
    image_count: int = 0,
    last_error: str | None = None,
) -> bool:
    """Upsert warm-listing state for a folder and return whether it was persisted."""
    initialize_database()
    now = time.time()
    try:
        resolved = str(Path(folder_path).resolve())
        if dir_mtime_ns is None:
            try:
                dir_mtime_ns = Path(folder_path).stat().st_mtime_ns
            except OSError:
                return False
        with _DB_LOCK, _connect() as conn:
            conn.execute(
                """
                INSERT INTO folder_index_state (
                  path, dir_mtime_ns, indexed_at, complete,
                  child_count, folder_count, image_count,
                  last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  dir_mtime_ns=excluded.dir_mtime_ns,
                  indexed_at=excluded.indexed_at,
                  complete=excluded.complete,
                  child_count=excluded.child_count,
                  folder_count=excluded.folder_count,
                  image_count=excluded.image_count,
                  last_error=excluded.last_error,
                  updated_at=excluded.updated_at
                """,
                (
                    resolved,
                    dir_mtime_ns,
                    now,
                    1 if complete else 0,
                    child_count,
                    folder_count,
                    image_count,
                    last_error,
                    now,
                ),
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def get_folder_index_state(folder_path: str | Path) -> dict | None:
    """Return persisted warm-listing state for a folder, or None on miss/error."""
    initialize_database()
    try:
        resolved = str(Path(folder_path).resolve())
        with _DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM folder_index_state WHERE path = ?",
                (resolved,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
    except Exception:  # noqa: BLE001
        return None


# TODO: Future optimization — add a persisted natural sort key column to file_index
# so very large warm folders can use DB-level ORDER BY + LIMIT without loading all
# direct child rows into Python.
def get_warm_folder_listing(
    folder_path: str | Path,
    *,
    limit: int | None = None,
    sort: str = "name",
    media_cursor: int | None = None,
) -> dict | None:
    """Return a folder listing from SQLite when the persisted folder state is current."""
    if not ENABLE_WARM_INDEXED_LISTING:
        return None

    try:
        resolved = str(Path(folder_path).resolve())
        resolved_path = Path(folder_path)
    except OSError:
        return None

    state = get_folder_index_state(resolved)
    if state is None:
        return None
    if not state["complete"]:
        return None

    try:
        current_stat = resolved_path.stat()
        current_mtime_ns = current_stat.st_mtime_ns
    except OSError:
        return None

    if state["dir_mtime_ns"] != current_mtime_ns:
        return None

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        f"{resolved.rstrip(os.sep)}{os.sep}"

        raw_folders = list(
            conn.execute(
                """
                SELECT path, name, mtime
                FROM file_index
                WHERE parent_path = ? AND type = 'folder'
                """,
                (resolved,),
            )
        )

        total_images_row = conn.execute(
            "SELECT count(*) AS total FROM file_index WHERE parent_path = ? AND type IN ('image', 'photo')",
            (resolved,),
        ).fetchone()
        total_images = int(total_images_row["total"])

        raw_images = list(
            conn.execute(
                """
                SELECT fi.path, fi.name, fi.mtime, fi.size,
                       COALESCE(fi.width, im.width) AS width,
                       COALESCE(fi.height, im.height) AS height
                FROM file_index AS fi
                LEFT JOIN image_metadata AS im ON im.path = fi.path
                WHERE fi.parent_path = ? AND fi.type IN ('image', 'photo')
                """,
                (resolved,),
            )
        )
        raw_videos = list(
            conn.execute(
                """
                SELECT fi.path, fi.name, fi.mtime, fi.width, fi.height,
                       a.duration_ms, a.mime_type
                FROM file_index AS fi
                LEFT JOIN assets AS a ON a.path = fi.path
                WHERE fi.parent_path = ? AND fi.type = 'video'
                """,
                (resolved,),
            )
        )

        # Sort in Python with natural_sort_key to match direct scan order
        from ..files import natural_sort_key

        raw_folders.sort(key=lambda x: natural_sort_key(x["name"]))
        raw_images.sort(key=lambda x: natural_sort_key(x["name"]))
        raw_videos.sort(key=lambda x: natural_sort_key(x["name"]))

        raw_media = sorted([*raw_images, *raw_videos], key=lambda row: natural_sort_key(row["name"]))
        media_start = media_cursor or 0
        media_end = media_start + limit if limit is not None else len(raw_media)
        media_page = raw_media[media_start:media_end]
        image_paths = {item["path"] for item in raw_images}
        warm_media = [
            FileNode(
                name=item["name"],
                path=item["path"],
                type="image",
                has_children=False,
                cover_images=[],
                mtime=item["mtime"] or 0,
                width=item["width"],
                height=item["height"],
            )
            if item["path"] in image_paths
            else VideoFileNode(
                name=item["name"],
                path=item["path"],
                type="video",
                has_children=False,
                cover_images=[],
                mtime=item["mtime"] or 0,
                width=item["width"],
                height=item["height"],
                duration_ms=item["duration_ms"],
                mime_type=item["mime_type"],
            )
            for item in media_page
        ]

        # Build DB-derived folder metadata — no filesystem access
        child_paths = [f["path"] for f in raw_folders]
        child_cover_images: dict[str, list[str]] = {}
        child_counts: dict[str, dict] = {}
        if child_paths:
            placeholders = ",".join("?" for _ in child_paths)
            cover_rows = conn.execute(
                f"""
                SELECT parent_path, path
                FROM file_index
                WHERE parent_path IN ({placeholders}) AND type IN ('image', 'photo')
                ORDER BY mtime DESC
                """,
                child_paths,
            ).fetchall()
            for r in cover_rows:
                pp = r["parent_path"]
                if pp not in child_cover_images:
                    child_cover_images[pp] = []
                if len(child_cover_images[pp]) < 3:
                    child_cover_images[pp].append(r["path"])

            count_rows = conn.execute(
                f"""
                SELECT parent_path,
                       count(*) AS total,
                       sum(CASE WHEN type = 'folder' THEN 1 ELSE 0 END) AS subfolder_count,
                       sum(CASE WHEN type IN ('image', 'photo') THEN 1 ELSE 0 END) AS photo_count
                FROM file_index
                WHERE parent_path IN ({placeholders})
                GROUP BY parent_path
                """,
                child_paths,
            ).fetchall()
            for r in count_rows:
                child_counts[r["parent_path"]] = {
                    "child_count": int(r["total"]),
                    "folder_count": int(r["subfolder_count"]),
                    "image_count": int(r["photo_count"]),
                }

        warm_folders: list[FileNode] = []
        for fld in raw_folders:
            fp = fld["path"]
            cc = child_counts.get(fp, {})
            warm_folders.append(
                FileNode(
                    name=fld["name"],
                    path=fp,
                    type="folder",
                    has_children=cc.get("child_count", 0) > 0,
                    cover_images=child_cover_images.get(fp, []),
                    mtime=fld["mtime"] or 0,
                    image_count=cc.get("image_count", 0),
                )
            )

    result = {
        "folders": warm_folders,
        "media": warm_media,
        "next_media_cursor": media_end if media_end < len(raw_media) else None,
        "total_images": total_images,
        "total_videos": len(raw_videos),
        "total_assets": total_images + len(raw_videos),
        "index_source": "warm_db",
    }
    return result


def get_folder_indexed_paths() -> list[dict]:
    """Return persisted folder index state rows ordered by most recent update."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT path, dir_mtime_ns, complete, image_count, updated_at FROM folder_index_state ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_folder_index_incomplete(folder_path: str | Path, last_error: str | None = None) -> bool:
    """Mark a folder's warm-listing state incomplete after a change or refresh failure."""
    return update_folder_index_state(folder_path, complete=False, last_error=last_error)


def upsert_image_dimensions(
    path: str | Path,
    width: int | None,
    height: int | None,
    *,
    image_format: str = "",
    mode: str = "",
    has_alpha: int | bool | None = None,
) -> bool:
    """Insert or update dimensions for an image opened by thumbnail/metadata paths."""
    if width is None or height is None:
        return False

    image_path = Path(path)
    if not is_image_path(image_path):
        return False

    try:
        stat = image_path.stat()
    except OSError:
        return False

    resolved_path = str(image_path.resolve())
    alpha_value = None if has_alpha is None else int(bool(has_alpha))
    now = time.time()
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, format, mode, has_alpha,
              prompt, negative_prompt, model, sampler, seed, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', '', '', '', ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              format=excluded.format,
              mode=excluded.mode,
              has_alpha=excluded.has_alpha,
              updated_at=excluded.updated_at
            """,
            (
                resolved_path,
                image_path.name,
                stat.st_mtime,
                stat.st_size,
                width,
                height,
                image_format,
                mode,
                alpha_value,
                now,
                now,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=image_path.name,
            parent_path=image_path.parent,
            type="image",
            mtime_ns=stat.st_mtime,
            size=stat.st_size,
            width=width,
            height=height,
            metadata_state="done",
            reactivate_existing=False,
        )
        _sync_dimensions_to_file_index(conn, resolved_path, width, height)
    return True


def _metadata_param(metadata: dict[str, Any], *names: str) -> Any:
    params = metadata.get("params")
    if not isinstance(params, dict):
        return None
    for name in names:
        if name in params:
            return params[name]
    return None


def upsert_metadata_result(path: str | Path, metadata: dict[str, Any]) -> bool:
    """Insert or update full metadata for an image opened by parse_metadata()."""
    image_path = Path(path)
    if not is_image_path(image_path):
        return False

    try:
        stat = image_path.stat()
    except OSError:
        return False

    sanitized_metadata = sanitize_metadata_for_json(metadata)
    if not isinstance(sanitized_metadata, dict):
        sanitized_metadata = {}
    metadata = sanitized_metadata

    width = metadata.get("width")
    height = metadata.get("height")
    prompt = safe_text(metadata.get("prompt"))
    negative_prompt = safe_text(metadata.get("negative_prompt"))
    model = safe_text(_metadata_param(metadata, "Model", "model"))
    sampler = safe_text(_metadata_param(metadata, "Sampler", "sampler"))
    seed = safe_text(_metadata_param(metadata, "Seed", "seed"))
    steps = parse_int(safe_text(_metadata_param(metadata, "Steps", "steps")))
    cfg_scale = parse_float(safe_text(_metadata_param(metadata, "CFG", "CFG scale", "cfg_scale", "cfg")))
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    raw_metadata_text = "\n".join(
        text for text in (prompt, negative_prompt, model, sampler, seed, metadata_json) if text
    )
    now = time.time()
    resolved_path = str(image_path.resolve())

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, prompt, negative_prompt,
              model, sampler, seed, steps, cfg_scale, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
              size=excluded.size,
              width=COALESCE(excluded.width, image_metadata.width),
              height=COALESCE(excluded.height, image_metadata.height),
              prompt=excluded.prompt,
              negative_prompt=excluded.negative_prompt,
              model=excluded.model,
              sampler=excluded.sampler,
              seed=excluded.seed,
              steps=excluded.steps,
              cfg_scale=excluded.cfg_scale,
              raw_metadata_text=excluded.raw_metadata_text,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at,
              indexed_at=excluded.indexed_at
            """,
            (
                resolved_path,
                image_path.name,
                stat.st_mtime,
                stat.st_size,
                width if isinstance(width, int) else None,
                height if isinstance(height, int) else None,
                prompt,
                negative_prompt,
                model,
                sampler,
                seed,
                steps,
                cfg_scale,
                raw_metadata_text,
                metadata_json,
                now,
                now,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=image_path.name,
            parent_path=image_path.parent,
            type="image",
            mtime_ns=stat.st_mtime,
            size=stat.st_size,
            width=width if isinstance(width, int) else None,
            height=height if isinstance(height, int) else None,
            metadata_state="done",
            reactivate_existing=False,
        )
        _sync_dimensions_to_file_index(
            conn,
            resolved_path,
            width if isinstance(width, int) else None,
            height if isinstance(height, int) else None,
        )
    return True


def _path_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_file_type(type_value: str) -> str:
    if type_value in {"image", "photo", "file"}:
        return "image"
    if type_value == "video":
        return "video"
    return "folder"


def index_file(
    path: str | Path,
    name: str,
    parent_path: str | Path,
    type: str,
    mtime: float | None,
    size: int | None,
    width: int | None,
    height: int | None,
    mime_type: str | None = None,
    duration_ms: int | None = None,
    codec: str | None = None,
) -> bool:
    """Upsert one folder or media row into the file index and asset catalog."""
    if is_index_excluded_path(path):
        return False
    resolved_path = str(Path(path).resolve())
    resolved_parent = str(Path(parent_path).resolve())
    normalized_type = _normalize_file_type(type)
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        library = _find_library_for_path_conn(conn, resolved_path)
        library_id = int(library["id"]) if library is not None else None
        if library is not None and is_index_excluded_path(
            resolved_path,
            library["matched_import_path"],
            _library_exclusion_patterns_conn(conn, int(library["id"])),
        ):
            return False
        mtime_ns = None
        with suppress(OSError):
            mtime_ns = Path(resolved_path).stat().st_mtime_ns
        conn.execute(
            """
            INSERT INTO file_index (
              path, name, parent_path, type, mtime, mtime_ns, size, width,
              height, indexed_at, library_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              parent_path=excluded.parent_path,
              type=excluded.type,
              mtime=excluded.mtime,
              mtime_ns=excluded.mtime_ns,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              indexed_at=excluded.indexed_at,
              library_id=excluded.library_id
            """,
            (
                resolved_path,
                name,
                resolved_parent,
                normalized_type,
                mtime,
                mtime_ns,
                size,
                width,
                height,
                time.time(),
                library_id,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=name,
            parent_path=resolved_parent,
            type=normalized_type,
            mtime_ns=mtime,
            size=size,
            width=width,
            height=height,
            mime_type=mime_type,
            duration_ms=duration_ms,
            codec=codec,
        )
        conn.execute("DELETE FROM file_index_fts WHERE path = ?", (resolved_path,))
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            (name, resolved_path, normalized_type, resolved_parent),
        )
    return True


def _cleanup_stale_index_conn(
    conn: sqlite3.Connection,
    root_path: str | Path | None = None,
    *,
    remove_outside_scope: bool = True,
) -> int:
    root = Path(root_path).resolve() if root_path is not None else None
    candidate_paths: set[str] = set()
    for table in ("file_index", "file_index_fts", "image_metadata", "metadata_index_jobs"):
        candidate_paths.update(row["path"] for row in conn.execute(f"SELECT path FROM {table}"))

    stale_paths: list[str] = []

    for path_value in candidate_paths:
        path = Path(path_value)
        if root is not None and not _is_inside_root(path, root):
            if remove_outside_scope:
                stale_paths.append(path_value)
            continue
        if not path.exists():
            stale_paths.append(path_value)

    if not stale_paths:
        return 0

    conn.executemany("DELETE FROM file_index_fts WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM file_index WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM image_metadata WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM metadata_index_jobs WHERE path = ?", ((path,) for path in stale_paths))
    return len(stale_paths)


def _cleanup_ignored_index_conn(conn: sqlite3.Connection, root_path: str | Path | None = None) -> int:
    root = Path(root_path).resolve() if root_path is not None else None
    candidate_paths: set[str] = set()
    for table in ("file_index", "file_index_fts", "image_metadata", "metadata_index_jobs", "folder_index_state"):
        candidate_paths.update(row["path"] for row in conn.execute(f"SELECT path FROM {table}"))

    ignored_paths = [
        path_value
        for path_value in candidate_paths
        if (root is None or _is_inside_root(Path(path_value), root)) and is_index_excluded_path(path_value)
    ]
    if not ignored_paths:
        return 0

    conn.executemany("DELETE FROM file_index_fts WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM file_index WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM image_metadata WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM metadata_index_jobs WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM folder_index_state WHERE path = ?", ((path,) for path in ignored_paths))
    return len(ignored_paths)


def cleanup_stale_index(
    state: Any,
    root_path: str | Path | None = None,
    *,
    remove_outside_scope: bool = True,
) -> int:
    """Remove stale database rows for missing or out-of-root paths.

    This only deletes index records. It never deletes filesystem entries.
    """
    initialize_database()
    if isinstance(state, sqlite3.Connection):
        return _cleanup_stale_index_conn(state, root_path, remove_outside_scope=remove_outside_scope)

    with _DB_LOCK, _connect() as conn:
        return _cleanup_stale_index_conn(conn, root_path, remove_outside_scope=remove_outside_scope)


def cleanup_ignored_index(root_path: str | Path | None = None) -> int:
    """Remove ignored dependency/cache/app-build paths from persisted index rows only."""
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        return _cleanup_ignored_index_conn(conn, root_path)


def _scoped_path_where(root: Path) -> tuple[str, list[Any]]:
    resolved = str(root.resolve())
    prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
    return "(path = ? OR path LIKE ? ESCAPE '\\')", [resolved, f"{_like_escape(prefix)}%"]


def clear_index_records(root_path: str | Path) -> dict[str, int]:
    """Delete persisted index/cache rows under root_path without touching files on disk."""
    initialize_database()
    root = Path(root_path).resolve()
    where, params = _scoped_path_where(root)
    tables = ("file_index_fts", "file_index", "image_metadata", "metadata_index_jobs", "folder_index_state")
    deleted: dict[str, int] = {}

    with _DB_LOCK, _connect() as conn:
        for table in tables:
            row = conn.execute(f"SELECT count(*) AS total FROM {table} WHERE {where}", params).fetchone()
            deleted[table] = int(row["total"] if row else 0)
            conn.execute(f"DELETE FROM {table} WHERE {where}", params)

    return deleted


def _scan_folder_counts(folder_path: Path) -> dict:
    folders = 0
    images = 0
    total = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.name.startswith("."):
                continue
            total += 1
            try:
                if entry.is_dir():
                    folders += 1
                elif entry.is_file() and is_image_path(Path(entry.path)):
                    images += 1
            except OSError:
                pass
    except OSError:
        pass
    return {"child_count": total, "folder_count": folders, "image_count": images}


def index_files_from_scan(folders: list[Any], media: list[Any], *, scan_folder_path: str | Path | None = None) -> int:
    """Persist file index rows produced by a scan response and update folder state."""
    indexed = 0
    for item in [*folders, *media]:
        raw_path = _path_value(item, "path")
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            stat = path.stat()
        except OSError:
            stat = None
        try:
            if index_file(
                path=path,
                name=_path_value(item, "name", path.name),
                parent_path=path.parent,
                type=_path_value(item, "type", "photo"),
                mtime=_path_value(item, "mtime", stat.st_mtime if stat else None),
                size=stat.st_size if stat and path.is_file() else None,
                width=_path_value(item, "width", None),
                height=_path_value(item, "height", None),
            ):
                indexed += 1
        except (OSError, sqlite3.Error):
            logger.exception("Failed to index file")
            continue

    if scan_folder_path is not None:
        image_count = sum(1 for item in media if _normalize_file_type(_path_value(item, "type", "image")) == "image")
        with suppress(Exception):
            update_folder_index_state(
                scan_folder_path,
                complete=True,
                child_count=len(folders) + len(media),
                folder_count=len(folders),
                image_count=image_count,
            )
    return indexed


def index_directory_tree(
    root: str | Path,
    include_metadata: bool = False,
    collected_image_paths: list[Path] | None = None,
    collected_asset_paths: set[str] | None = None,
) -> int:
    """Recreate file_index rows under root. Optionally extract metadata or collect image paths.

    Symlinked directories are skipped to avoid traversal loops. Hidden files and
    folders are ignored to match the existing scanner behavior.
    """
    root_path = Path(root).resolve()
    indexed = 0
    local_image_paths: list[Path] = [] if include_metadata else None  # type: ignore[assignment]
    library = get_library_for_path(root_path)
    import_root = library["matched_import_path"] if library is not None else None
    exclusion_patterns = library["exclusion_patterns"] if library is not None else []

    def visit(folder: Path, visited_inodes: set[tuple[int, int]]) -> None:
        nonlocal indexed
        if is_index_excluded_path(folder, import_root, exclusion_patterns):
            return
        try:
            stat = folder.stat()
            folder_inode = (stat.st_dev, stat.st_ino)
            if folder_inode in visited_inodes:
                return
            visited_inodes.add(folder_inode)
        except OSError:
            return

        try:
            if index_file(folder, folder.name or str(folder), folder.parent, "folder", stat.st_mtime, None, None, None):
                indexed += 1
            if collected_asset_paths is not None:
                collected_asset_paths.add(str(folder.resolve()))
        except OSError:
            return
        except Exception:  # noqa: BLE001
            pass

        try:
            entries = list(folder.iterdir())
        except (OSError, PermissionError):
            return

        for entry in entries:
            if entry.name.startswith(".") or is_index_excluded_path(entry, import_root, exclusion_patterns):
                continue
            try:
                # Skip symlinked directories to avoid loops; files are still followed.
                if entry.is_dir() and not entry.is_symlink():
                    visit(entry, visited_inodes)
                elif entry.is_file() and is_asset_path(entry):
                    stat = entry.stat()
                    asset_type = asset_type_for_path(entry)
                    width = None
                    height = None
                    duration_ms = None
                    codec = None
                    mime_type = mimetypes.guess_type(entry.name)[0]
                    if asset_type == "video":
                        try:
                            result = subprocess.run(
                                [
                                    "ffprobe",
                                    "-v",
                                    "quiet",
                                    "-print_format",
                                    "json",
                                    "-show_format",
                                    "-show_streams",
                                    str(entry),
                                ],
                                capture_output=True,
                                text=True,
                                timeout=5,
                                check=False,
                            )
                            if result.returncode == 0:
                                probe = json.loads(result.stdout)
                                duration = probe.get("format", {}).get("duration")
                                if duration is not None:
                                    duration_ms = int(float(duration) * 1000)
                                video_stream = next(
                                    (
                                        stream
                                        for stream in probe.get("streams", [])
                                        if stream.get("codec_type") == "video"
                                    ),
                                    None,
                                )
                                if video_stream is not None:
                                    codec = video_stream.get("codec_name")
                                    width = parse_int(video_stream.get("width"))
                                    height = parse_int(video_stream.get("height"))
                        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
                            logger.debug("Could not probe video metadata for %s", entry, exc_info=True)
                    if index_file(
                        entry,
                        entry.name,
                        entry.parent,
                        asset_type or "folder",
                        stat.st_mtime,
                        stat.st_size,
                        width,
                        height,
                        mime_type=mime_type,
                        duration_ms=duration_ms,
                        codec=codec,
                    ):
                        indexed += 1
                    if collected_asset_paths is not None:
                        collected_asset_paths.add(str(entry.resolve()))
                    if include_metadata and asset_type == "image":
                        local_image_paths.append(entry)
                    if collected_image_paths is not None and asset_type == "image":
                        collected_image_paths.append(entry)
            except (OSError, PermissionError):
                continue

    visit(root_path, set())
    if include_metadata and local_image_paths:
        indexed += index_images(local_image_paths)
    return indexed


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
    root_str, root_prefix = _path_prefix(root)
    return f" AND ({alias}.path = ? OR {alias}.path LIKE ? ESCAPE '\\')", [root_str, root_prefix], root


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
                meta = build_album_metadata(resolved_path)
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
                WHERE fts MATCH ? AND {type_sql} {scope_sql}
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
            WHERE fi.name LIKE ? ESCAPE '\\' AND {type_sql} {scope_sql}
            ORDER BY fi.mtime DESC, fi.name ASC
            LIMIT ?
            """,
            [pattern, *type_params, *scope_params, limit],
        )
    )
    return rows, root


def _search_prompt_rows(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    scope_sql, scope_params, root = _scope_clause(scope, root_path, "fi")
    rows: list[sqlite3.Row] = []
    try:
        if contains_cjk(query) and len(query) >= 3:
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts_trigram) AS rank
                    FROM image_metadata_fts_trigram fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts_trigram MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_trigram_match_query(query), *scope_params, limit],
                )
            )
        elif not contains_cjk(query):
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts) AS rank
                    FROM image_metadata_fts fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_unicode_match_query(query), *scope_params, limit],
                )
            )
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(query)
    where = " OR ".join(f"m.{field} LIKE ? ESCAPE '\\'" for field in PROMPT_SEARCH_FIELDS)
    rows = list(
        conn.execute(
            f"""
            SELECT m.*, fi.parent_path, fi.type AS file_type
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE ({where}) {scope_sql}
            ORDER BY m.mtime DESC, m.name ASC
            LIMIT ?
            """,
            [*([pattern] * len(PROMPT_SEARCH_FIELDS)), *scope_params, limit],
        )
    )
    return rows, root


def _format_prompt_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        results.append(
            {
                "name": row["name"],
                "path": row["path"],
                "type": "photo",
                "parent_path": row["parent_path"],
                "relative_path": _folder_relative_path(row["parent_path"], root),
                "mtime": row["mtime"],
                "width": row["width"],
                "height": row["height"],
                "match_type": "prompt",
                "prompt_snippet": _snippet(row),
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
        WHERE {table} MATCH ?
        ORDER BY rank ASC, m.mtime DESC, m.name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (match_query, limit, offset)))


def _count_fts(conn: sqlite3.Connection, table: str, match_query: str) -> int:
    row = conn.execute(f"SELECT count(*) AS total FROM {table} WHERE {table} MATCH ?", (match_query,)).fetchone()
    return int(row["total"] if row else 0)


def _search_like(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[sqlite3.Row]:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    sql = f"""
        SELECT *
        FROM image_metadata
        WHERE {where}
        ORDER BY mtime DESC, name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (*([pattern] * len(SEARCH_FIELDS)), limit, offset)))


def _count_like(conn: sqlite3.Connection, query: str) -> int:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    row = conn.execute(
        f"SELECT count(*) AS total FROM image_metadata WHERE {where}", [pattern] * len(SEARCH_FIELDS)
    ).fetchone()
    return int(row["total"] if row else 0)


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


def search_index(query: str, scope: str, root_path: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    """Search indexed albums, photos, and prompts using free-text query semantics."""
    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(display_root),
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    if normalized_scope == "current" and root is None:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": "",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    with _DB_LOCK, _connect() as conn:
        album_rows, root = _search_file_index_fts(conn, trimmed, "folder", normalized_scope, root_path, limit)
        photo_rows, root = _search_file_index_fts(conn, trimmed, "photo", normalized_scope, root_path, limit)
        video_rows, root = _search_file_index_fts(conn, trimmed, "video", normalized_scope, root_path, limit)
        prompt_rows, root = _search_prompt_rows(conn, trimmed, normalized_scope, root_path, limit)

    format_root = root if root is not None else Path(os.sep)
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": _format_file_index_rows(photo_rows, format_root, "filename"),
        "videos": _format_file_index_rows(video_rows, format_root, "filename"),
        "prompt": _format_prompt_rows(prompt_rows, format_root),
    }


def _build_scope_named(scope: str, root_path: str | Path | None, alias: str = "fi") -> tuple[str, dict[str, str]]:
    """Build scope WHERE fragment and named params dict."""
    if scope != "current" or not root_path:
        return "", {}
    root = Path(root_path).resolve()
    root_str, root_prefix = _path_prefix(root)
    cond = f" AND ({alias}.path = :scope_root OR {alias}.path LIKE :scope_prefix ESCAPE '\\')"
    return cond, {"scope_root": root_str, "scope_prefix": root_prefix}


def _search_fielded_photos(
    conn: sqlite3.Connection,
    parsed: Any,
    scope: str,
    root_path: str | Path | None,
    root: Path,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    """Intersect filename matches with field-filtered paths using a CTE.

    NOTE: This function is used ONLY for the Photos (and indirectly Prompt) result
    sections.  It applies field filters (seed:, model:, etc.) to narrow results.
    The Albums section does NOT call this function — albums are folder suggestions
    based solely on residual text and are intentionally not field-filtered.

    WITH field_paths AS (
      SELECT m.path FROM image_metadata m JOIN file_index fi ON fi.path = m.path
      WHERE <field conditions>
    )
    SELECT fi.*
    FROM file_index_fts fts
    JOIN file_index fi ON fi.path = fts.path
    JOIN field_paths fp ON fp.path = fi.path
    WHERE fts MATCH <residual> AND fi.type = 'photo' <scope>
    ORDER BY ...

    Falls back to LIKE on fi.name when FTS returns zero rows.
    """
    from ..fielded_search_parser import (
        ParsedQuery,
        build_fielded_conditions,
    )

    photo_query = (parsed.residual_text or "").strip()
    if not photo_query:
        return [], root

    scope_cond, scope_params = _build_scope_named(scope, root_path, "fi")

    field_parsed = ParsedQuery(residual_text="", fields=parsed.fields)
    field_conditions, field_params = build_fielded_conditions(field_parsed)
    field_where = " AND ".join(field_conditions) if field_conditions else "1=1"

    def _build_params(**extra: Any) -> dict[str, Any]:
        p = dict(scope_params)
        p.update(field_params)
        p.update(extra)
        return p

    try:
        fts_query = _unicode_match_query(photo_query)
        params = _build_params(fts_query=fts_query, limit=limit)
        sql = f"""
            WITH field_paths AS (
                SELECT m.path
                FROM image_metadata m
                JOIN file_index fi ON fi.path = m.path
                WHERE {field_where}
            )
            SELECT fi.*
            FROM file_index_fts fts
            JOIN file_index fi ON fi.path = fts.path
            JOIN field_paths fp ON fp.path = fi.path
            WHERE fts MATCH :fts_query
              AND fi.type IN ('image', 'photo')
              {scope_cond}
            ORDER BY bm25(file_index_fts), fi.mtime DESC, fi.name ASC
            LIMIT :limit
        """
        rows = list(conn.execute(sql, params))
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(photo_query)
    params = _build_params(like_pattern=pattern, limit=limit)
    sql = f"""
        WITH field_paths AS (
            SELECT m.path
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE {field_where}
        )
        SELECT fi.*
        FROM file_index fi
        JOIN field_paths fp ON fp.path = fi.path
        WHERE fi.name LIKE :like_pattern ESCAPE '\\'
          AND fi.type IN ('image', 'photo')
          {scope_cond}
        ORDER BY fi.mtime DESC, fi.name ASC
        LIMIT :limit
    """
    rows = list(conn.execute(sql, params))
    return rows, root


def search_index_fielded(
    query: str, scope: str, root_path: str | Path | None = None, limit: int = 50
) -> dict[str, Any]:
    """Search indexed albums and photos with structured field filters."""
    from ..fielded_search_parser import (
        build_fielded_search_sql,
        parse_fielded_query,
    )

    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    display_root = root if root is not None else Path(os.sep)

    if not trimmed:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(display_root),
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

    if normalized_scope == "current" and root is None:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": "",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
        }

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
        video_query = parsed.residual_text if parsed.residual_text else trimmed
        video_rows, root = _search_file_index_fts(conn, video_query, "video", normalized_scope, root_path, limit)
        if album_query:
            album_rows, root = _search_file_index_fts(conn, album_query, "folder", normalized_scope, root_path, limit)
        else:
            album_rows = []

        if parsed.fields:
            # ── Photos & Prompt sections (field-filtered) ──────────────
            # Photos intersect residual-text filename matches with
            # metadata field filters (seed:, model:, etc.) via a CTE.
            # Prompt/image-result rows are also narrowed by field filters.
            # These sections ARE guaranteed to satisfy metadata filters.
            # ───────────────────────────────────────────────────────────
            photo_rows, root = _search_fielded_photos(conn, parsed, normalized_scope, root_path, root, limit)

            if parsed.fields or parsed.residual_text:
                sql, sql_params = build_fielded_search_sql(parsed, limit)
                if normalized_scope == "current":
                    root_str, root_prefix = _path_prefix(root)
                    if "WHERE" in sql:
                        sql = sql.replace(
                            "WHERE ", "WHERE (fi.path = :scope_root OR fi.path LIKE :scope_prefix ESCAPE '\\') AND "
                        )
                    else:
                        sql = sql.replace(
                            "ORDER BY",
                            "WHERE (fi.path = :scope_root OR fi.path LIKE :scope_prefix ESCAPE '\\') ORDER BY",
                        )
                    sql_params["scope_root"] = root_str
                    sql_params["scope_prefix"] = root_prefix
                try:
                    prompt_rows = list(conn.execute(sql, sql_params))
                except Exception:  # noqa: BLE001
                    prompt_rows = []
            else:
                prompt_rows = []
        elif parsed.residual_text:
            # No fields, residual only — plain filename + metadata search
            photo_rows, root = _search_file_index_fts(
                conn, parsed.residual_text, "photo", normalized_scope, root_path, limit
            )
            prompt_rows, root = _search_prompt_rows(conn, parsed.residual_text, normalized_scope, root_path, limit)
        else:
            photo_rows = []
            prompt_rows = []

    format_root = root if root is not None else Path(os.sep)
    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(format_root),
        "albums": _format_file_index_rows(album_rows, format_root, "filename"),
        "photos": _format_file_index_rows(photo_rows, format_root, "filename"),
        "videos": _format_file_index_rows(video_rows, format_root, "filename"),
        "prompt": _format_prompt_rows(prompt_rows, format_root),
    }


def _truncate_preview(text: str | None, limit: int = 140) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _format_inspector_row(row: sqlite3.Row, root: Path) -> dict[str, Any]:
    has_lora, lora_count, lora_preview = _lora_summary(row)
    parent_path = row["parent_path"] or str(Path(row["path"]).parent)
    row_keys = set(row.keys())
    width = row["indexed_width"] if "indexed_width" in row_keys else row["width"]
    height = row["indexed_height"] if "indexed_height" in row_keys else row["height"]
    return {
        "path": row["path"],
        "name": row["name"],
        "folder": parent_path,
        "relative_path": _folder_relative_path(parent_path, root),
        "mtime": row["mtime"],
        "width": width,
        "height": height,
        "model": row["model"] or "",
        "tool": row["tool"] or "",
        "sampler": row["sampler"] or "",
        "seed": row["seed"] or "",
        "prompt_preview": _truncate_preview(row["prompt_preview"], 140),
        "has_prompt": bool(row["has_prompt"]),
        "has_negative": bool(row["has_negative"]),
        "has_lora": has_lora,
        "lora_count": lora_count,
        "lora_preview": lora_preview,
        "metadata_detail_available": bool(
            row["has_metadata_json"] or row["has_prompt"] or row["has_negative"] or row["lora_count"]
        ),
    }


def _encode_inspector_cursor(values: dict[str, Any] | sqlite3.Row) -> str:
    cursor_data = {
        "mtime": values["mtime"],
        "name": values["name"],
        "path": values["path"],
    }
    return base64.urlsafe_b64encode(json.dumps(cursor_data).encode()).decode()


def _build_library_inspector_keyset_where(sort: str, cursor_str: str | None) -> tuple[str, dict[str, Any]]:
    """Return SQL conditions and params for Library Inspector keyset pagination."""
    if not cursor_str:
        return "", {}

    try:
        cursor = json.loads(base64.urlsafe_b64decode(cursor_str.encode()))
        cursor_mtime = cursor["mtime"]
        cursor_name = cursor["name"]
        cursor_path = cursor["path"]
    except Exception as exc:
        raise ValueError("Invalid pagination cursor") from exc

    mtime_expr = "COALESCE(m.mtime, fi.mtime)"
    params: dict[str, Any] = {
        "ks_mtime": cursor_mtime,
        "ks_name": cursor_name,
        "ks_path": cursor_path,
    }

    if sort == "date_desc":
        cond = f"""
            ({mtime_expr} < :ks_mtime) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL = :ks_name AND m.path > :ks_path)
        """
    elif sort == "date_asc":
        cond = f"""
            ({mtime_expr} > :ks_mtime) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            ({mtime_expr} = :ks_mtime AND m.name COLLATE GALLERY_NATURAL = :ks_name AND m.path > :ks_path)
        """
    elif sort == "name_asc":
        cond = f"""
            (m.name COLLATE GALLERY_NATURAL > :ks_name) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} < :ks_mtime) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} = :ks_mtime AND m.path > :ks_path)
        """
    elif sort == "name_desc":
        cond = f"""
            (m.name COLLATE GALLERY_NATURAL < :ks_name) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} < :ks_mtime) OR
            (m.name COLLATE GALLERY_NATURAL = :ks_name AND {mtime_expr} = :ks_mtime AND m.path > :ks_path)
        """
    else:
        return "", {}

    return f"({cond})", params


def list_library_inspector_rows(
    query: str = "",
    scope: str = "current",
    root_path: str | Path | None = None,
    limit: int = 200,
    sort: str = "date_desc",
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return bounded DB/index-backed rows for the read-only Library Inspector."""
    from ..fielded_search_parser import build_fielded_conditions, parse_fielded_query

    initialize_database()
    trimmed = query.strip()
    normalized_scope = "current" if scope == "current" else "all"
    bounded_limit = max(1, min(limit, 1000))
    normalized_sort = sort if sort in {"name_asc", "name_desc", "date_asc", "date_desc"} else "date_desc"
    order_sql = {
        "name_asc": "m.name COLLATE GALLERY_NATURAL ASC, COALESCE(m.mtime, fi.mtime) DESC, m.path ASC",
        "name_desc": "m.name COLLATE GALLERY_NATURAL DESC, COALESCE(m.mtime, fi.mtime) DESC, m.path ASC",
        "date_asc": "COALESCE(m.mtime, fi.mtime) ASC, m.name COLLATE GALLERY_NATURAL ASC, m.path ASC",
        "date_desc": "COALESCE(m.mtime, fi.mtime) DESC, m.name COLLATE GALLERY_NATURAL ASC, m.path ASC",
    }[normalized_sort]
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else None
    if normalized_scope == "current" and root is None:
        return {
            "root": "",
            "scope": normalized_scope,
            "query": query,
            "limit": bounded_limit,
            "generated_at": time.time(),
            "total_indexed": 0,
            "returned": 0,
            "truncated": False,
            "next_cursor": None,
            "has_more": False,
            "sort": normalized_sort,
            "rows": [],
        }
    display_root = root if root is not None else Path(os.sep)
    scope_cond, scope_params = _build_scope_named(normalized_scope, root, "fi")

    with _DB_LOCK, _connect() as conn:
        parsed = parse_fielded_query(trimmed)
        field_conditions: list[str] = []
        field_params: dict[str, Any] = {}
        if trimmed:
            field_conditions, field_params = build_fielded_conditions(parsed)
        keyset_condition, keyset_params = _build_library_inspector_keyset_where(normalized_sort, cursor)

        where_parts = ["fi.type IN ('image', 'photo')"]
        if field_conditions:
            where_parts.extend(field_conditions)
        if keyset_condition:
            where_parts.append(keyset_condition)
        where_sql = " AND ".join(where_parts)

        params: dict[str, Any] = dict(scope_params)
        params.update(field_params)
        params.update(keyset_params)
        params["limit"] = bounded_limit + 1

        fetched_rows = list(
            conn.execute(
                f"""
                SELECT
                  m.path,
                  m.name,
                  COALESCE(m.mtime, fi.mtime) AS mtime,
                  m.width,
                  m.height,
                  m.model,
                  m.tool,
                  m.sampler,
                  m.seed,
                  substr(COALESCE(m.prompt, ''), 1, 141) AS prompt_preview,
                  CASE WHEN m.prompt IS NOT NULL AND m.prompt != '' THEN 1 ELSE 0 END AS has_prompt,
                  CASE WHEN m.negative_prompt IS NOT NULL AND m.negative_prompt != '' THEN 1 ELSE 0 END AS has_negative,
                  CASE WHEN m.metadata_json IS NOT NULL AND m.metadata_json != '' THEN 1 ELSE 0 END AS has_metadata_json,
                  COALESCE(lr.lora_count, 0) AS lora_count,
                  COALESCE(lr.lora_preview, '') AS lora_preview,
                  fi.parent_path,
                  fi.type AS file_type,
                  COALESCE(fi.width, m.width) AS indexed_width,
                  COALESCE(fi.height, m.height) AS indexed_height
                FROM image_metadata m
                JOIN file_index fi ON fi.path = m.path
                LEFT JOIN (
                  SELECT path, count(*) AS lora_count, group_concat(name, ', ') AS lora_preview
                  FROM image_resources
                  WHERE kind = 'lora'
                  GROUP BY path
                ) lr ON lr.path = m.path
                WHERE {where_sql}
                {scope_cond}
                ORDER BY {order_sql}
                LIMIT :limit
                """,
                params,
            )
        )
        rows = fetched_rows[:bounded_limit]
        next_cursor = _encode_inspector_cursor(rows[-1]) if len(fetched_rows) > bounded_limit and rows else None

        total_row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE fi.type IN ('image', 'photo')
            {scope_cond}
            """,
            scope_params,
        ).fetchone()

    return {
        "root": str(display_root),
        "scope": normalized_scope,
        "query": query,
        "limit": bounded_limit,
        "generated_at": time.time(),
        "total_indexed": int(total_row["total"] if total_row else 0),
        "returned": len(rows),
        "truncated": len(fetched_rows) > bounded_limit,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "sort": normalized_sort,
        "rows": _dedupe_inspector_rows(rows, display_root),
    }


def _dedupe_inspector_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        results.append(_format_inspector_row(row, root))
    return results


def get_library_inspector_metadata(path: str | Path) -> dict[str, Any] | None:
    """Read full inspector metadata from indexed DB rows only."""
    resolved = str(Path(path).resolve())
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT
              m.*,
              fi.parent_path,
              fi.type AS file_type,
              COALESCE(fi.width, m.width) AS indexed_width,
              COALESCE(fi.height, m.height) AS indexed_height
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE m.path = ? AND fi.type IN ('image', 'photo')
            """,
            (resolved,),
        ).fetchone()
        if row is None:
            return None

    metadata = _safe_json_loads(row["metadata_json"])
    loras = _iter_metadata_loras(metadata)
    if not loras:
        loras = [
            {"name": name, "hash": None, "resource_hash": None, "weight": None, "strength": None}
            for name in _split_lora_text(row["lora_text"])
        ]

    resources: list[dict[str, Any]] = []
    if isinstance(metadata, dict):
        for key in ("resources", "Resources"):
            value = metadata.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        resources.append(
                            {
                                "name": item.get("name") or item.get("resource_name") or "",
                                "hash": item.get("hash"),
                                "resource_hash": item.get("resource_hash") or item.get("hash"),
                                "weight": item.get("weight") or item.get("strength"),
                                "strength": item.get("strength") or item.get("weight"),
                            }
                        )

    return {
        "path": row["path"],
        "prompt": row["prompt"] or "",
        "negative_prompt": row["negative_prompt"] or "",
        "raw_metadata": metadata,
        "model": row["model"] or "",
        "tool": row["tool"] or "",
        "sampler": row["sampler"] or "",
        "seed": row["seed"] or "",
        "width": row["indexed_width"],
        "height": row["indexed_height"],
        "mtime": row["mtime"],
        "loras": loras,
        "resources": resources,
        "metadata_detail_available": bool(metadata or row["prompt"] or row["negative_prompt"] or loras or resources),
    }
