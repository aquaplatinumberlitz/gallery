"""Database schema creation and migration helpers."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from . import _db as _db
from ._db import _connect, _database_has_application_tables, _ensure_column, _table_columns, _table_exists
from ._resources import _backfill_image_resources_conn
from .file_index import _cleanup_ignored_index_conn
from .library_store import _ensure_default_library_conn
from .path_utils import _catalog_paths_overlap, canonicalize_catalog_path, catalog_path_contains

logger = logging.getLogger(__name__)


def _gallery_metadata_db() -> Path:
    from . import GALLERY_METADATA_DB

    return GALLERY_METADATA_DB


def _shim_backup_database_before_v9(conn: sqlite3.Connection) -> Path:
    from . import _backup_database_before_v9

    return _backup_database_before_v9(conn)


def _shim_rebuild_libraries_without_root_path(conn: sqlite3.Connection) -> None:
    from . import _rebuild_libraries_without_root_path

    _rebuild_libraries_without_root_path(conn)


CATALOG_SCHEMA_VERSION = 9


def _v9_backup_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _gallery_metadata_db().with_name(
        f"{_gallery_metadata_db().stem}.v8-backup-{timestamp}{_gallery_metadata_db().suffix}"
    )


def _backup_database_before_v9(conn: sqlite3.Connection) -> Path:
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    backup_path = _v9_backup_path()
    suffix = 1
    while backup_path.exists():
        backup_path = backup_path.with_name(
            f"{_gallery_metadata_db().stem}.v8-backup-"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{suffix}{_gallery_metadata_db().suffix}"
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
    backup_path = _shim_backup_database_before_v9(conn)
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
        _shim_rebuild_libraries_without_root_path(conn)
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
    if _db._DB_INITIALIZED and _gallery_metadata_db() == _db._DB_INITIALIZED_PATH:
        return

    with _db._DB_LOCK:
        if _db._DB_INITIALIZED and _gallery_metadata_db() == _db._DB_INITIALIZED_PATH:
            return

        with _connect(set_journal_mode=True) as conn:
            _initialize_database_conn(conn)

        _db._DB_INITIALIZED = True
        _db._DB_INITIALIZED_PATH = _gallery_metadata_db()


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
    cache_dir = config.THUMBNAIL_CACHE_DIR / "files"
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
