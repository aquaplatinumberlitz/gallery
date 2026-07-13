"""Database schema creation and migration helpers."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from . import _db as _db
from ._db import (
    _connect,
    _database_has_application_tables,
    _ensure_column,
    _gallery_metadata_db_path,
)
from .file_index import _cleanup_ignored_index_conn

logger = logging.getLogger(__name__)


def _gallery_metadata_db() -> Path:
    return _gallery_metadata_db_path()


CATALOG_SCHEMA_VERSION = 5


def _ensure_search_index_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create the additive durable search-index lifecycle tables and indexes."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS search_index_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          index_name TEXT NOT NULL,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          mode TEXT NOT NULL CHECK (mode IN ('missing', 'full')),
          state TEXT NOT NULL CHECK (
            state IN ('queued', 'running', 'cancel_requested', 'cancelled',
                      'succeeded', 'failed', 'interrupted')
          ),
          cursor_asset_id INTEGER,
          processed_count INTEGER NOT NULL DEFAULT 0,
          target_count INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0,
          requested_at REAL NOT NULL,
          started_at REAL,
          finished_at REAL,
          claimed_by TEXT,
          claim_token TEXT,
          lease_expires_at REAL,
          error_code TEXT,
          error_summary TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS search_index_states (
          index_name TEXT NOT NULL,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          state TEXT NOT NULL CHECK (state IN ('pending', 'building', 'ready', 'degraded', 'failed', 'disabled')),
          schema_version INTEGER NOT NULL,
          extractor_version INTEGER NOT NULL,
          indexed_count INTEGER NOT NULL DEFAULT 0,
          target_count INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0,
          active_job_id INTEGER REFERENCES search_index_jobs(id) ON DELETE SET NULL,
          started_at REAL,
          completed_at REAL,
          updated_at REAL NOT NULL,
          error_code TEXT,
          error_summary TEXT,
          PRIMARY KEY(index_name, library_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS asset_search_extractions (
          asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          index_name TEXT NOT NULL,
          source_fingerprint TEXT NOT NULL,
          extractor_version INTEGER NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('ready', 'not_applicable', 'skipped', 'failed')),
          error_code TEXT,
          indexed_at REAL NOT NULL,
          PRIMARY KEY(asset_id, index_name)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_search_index_jobs_pick
          ON search_index_jobs(state, requested_at, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_search_index_jobs_library
          ON search_index_jobs(library_id, index_name, requested_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_search_index_jobs_lease
          ON search_index_jobs(state, lease_expires_at)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_search_index_jobs_one_active
          ON search_index_jobs(index_name, library_id)
          WHERE state IN ('queued', 'running', 'cancel_requested', 'interrupted')
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_search_extractions_index_status
          ON asset_search_extractions(index_name, status, asset_id)
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


def _ensure_catalog_schema(conn: sqlite3.Connection) -> None:
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
        """
        CREATE TABLE IF NOT EXISTS integrity_check_runs (
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          trigger       TEXT NOT NULL CHECK (trigger IN ('manual', 'daemon')),
          started_at    REAL NOT NULL,
          finished_at   REAL,
          status        TEXT NOT NULL CHECK (status IN ('ok', 'error')),
          error         TEXT,
          issues_json   TEXT NOT NULL,
          repairs_json  TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_integrity_check_runs_finished
          ON integrity_check_runs(finished_at DESC)
        """,
    ]
    for statement in statements:
        conn.execute(statement)


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


def _ensure_post_v1_additive_columns(conn: sqlite3.Connection) -> None:
    """Run additive column/index migrations for post-v1 schemas.

    Safe to call on any database version — uses ALTER TABLE ADD COLUMN
    which is idempotent (``_ensure_column`` catches duplicate-column errors).
    Covers all columns and indexes that were added after the initial v1 schema.
    """
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
    _ensure_column(conn, "image_metadata", "source_path", "TEXT")
    _ensure_column(conn, "image_metadata", "source_mtime_ns", "INTEGER")
    _ensure_column(conn, "image_metadata", "source_size", "INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_size  ON image_metadata(path, mtime, size)")
    _ensure_column(conn, "metadata_index_jobs", "folder_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "metadata_index_jobs", "root_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "metadata_index_jobs", "library_id", "INTEGER")
    _ensure_column(conn, "metadata_index_jobs", "priority", "INTEGER NOT NULL DEFAULT 3")
    _ensure_catalog_schema(conn)
    _ensure_column(conn, "libraries", "config_revision", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "library_jobs", "config_revision", "INTEGER")
    _ensure_column(conn, "derivative_jobs", "result_code", "TEXT")
    _ensure_column(conn, "derivative_jobs", "claimed_by", "TEXT")
    _ensure_column(conn, "derivative_jobs", "claim_token", "TEXT")
    _ensure_column(conn, "derivative_jobs", "lease_expires_at", "REAL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state_lease ON derivative_jobs(state, lease_expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_claim  ON metadata_index_jobs(state, priority, queued_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_library_state  ON metadata_index_jobs(library_id, state)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_metadata_state  ON assets(metadata_state)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS catalog_job_dependencies (
          parent_job_id INTEGER NOT NULL REFERENCES library_jobs(id) ON DELETE CASCADE,
          child_job_id INTEGER NOT NULL REFERENCES library_jobs(id) ON DELETE CASCADE,
          created_at REAL NOT NULL,
          PRIMARY KEY(parent_job_id, child_job_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_job_dependencies_child ON catalog_job_dependencies(child_job_id)"
    )


def _ensure_v3_schema(conn: sqlite3.Connection) -> None:
    """Ensure catalog claim fencing and scheduled-attempt persistence."""
    _ensure_column(conn, "libraries", "last_scheduled_attempt_at", "REAL")
    _ensure_column(conn, "library_jobs", "claimed_by", "TEXT")
    _ensure_column(conn, "library_jobs", "claim_token", "TEXT")
    _ensure_column(conn, "library_jobs", "lease_expires_at", "REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_library_jobs_state_lease ON library_jobs(state, lease_expires_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_libraries_scheduled_attempt ON libraries(last_scheduled_attempt_at, id)"
    )


def _column_type(conn: sqlite3.Connection, table: str, column: str) -> str | None:
    row = next((item for item in conn.execute(f"PRAGMA table_info({table})") if item["name"] == column), None)
    return str(row["type"]).upper() if row is not None else None


def _execute_v2_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v1-to-v2 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v1_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before destructive v2 migration work."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v1.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_nanosecond_affinity_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Rebuild legacy REAL nanosecond columns inside the caller transaction."""
    if (
        _column_type(conn, "assets", "mtime_ns") == "INTEGER"
        and _column_type(conn, "asset_derivatives", "source_mtime_ns") == "INTEGER"
    ):
        return
    statements = [
        "ALTER TABLE asset_derivatives RENAME TO asset_derivatives_real_ns",
        "ALTER TABLE assets RENAME TO assets_real_ns",
        """CREATE TABLE assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id),
              path TEXT NOT NULL, parent_path TEXT NOT NULL, name TEXT NOT NULL,
              type TEXT NOT NULL DEFAULT 'image', mtime_ns INTEGER, size INTEGER,
              width INTEGER, height INTEGER, orientation INTEGER, indexed_at REAL,
              metadata_state TEXT DEFAULT 'pending', offline INTEGER NOT NULL DEFAULT 0,
              deleted_at REAL, mime_type TEXT, duration_ms INTEGER, codec TEXT,
              last_seen_scan_job_id INTEGER, UNIQUE(library_id, path)
            )""",
        """INSERT INTO assets SELECT id, library_id, path, parent_path, name, type,
              CAST(mtime_ns AS INTEGER), size, width, height, orientation, indexed_at,
              metadata_state, offline, deleted_at, mime_type, duration_ms, codec,
              last_seen_scan_job_id FROM assets_real_ns""",
        """CREATE TABLE asset_derivatives (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id INTEGER NOT NULL REFERENCES assets(id), kind TEXT NOT NULL,
              variant TEXT NOT NULL, source_mtime_ns INTEGER NOT NULL,
              source_size INTEGER NOT NULL, format TEXT NOT NULL DEFAULT 'webp',
              quality INTEGER NOT NULL DEFAULT 85, max_long_edge INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued', cache_path TEXT, byte_size INTEGER,
              last_accessed_at REAL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              UNIQUE(asset_id, kind, variant, source_mtime_ns, source_size)
            )""",
        """INSERT INTO asset_derivatives SELECT id, asset_id, kind, variant,
              CAST(source_mtime_ns AS INTEGER), source_size, format, quality,
              max_long_edge, status, cache_path, byte_size, last_accessed_at,
              attempts, last_error, created_at, updated_at FROM asset_derivatives_real_ns""",
        "DROP TABLE asset_derivatives_real_ns",
        "DROP TABLE assets_real_ns",
        "CREATE INDEX idx_assets_library_path ON assets(library_id, path)",
        "CREATE INDEX idx_assets_library_parent ON assets(library_id, parent_path)",
        "CREATE INDEX idx_assets_reconcile_scan ON assets(library_id, parent_path, last_seen_scan_job_id)",
        "CREATE INDEX idx_assets_library_seen ON assets(library_id, last_seen_scan_job_id)",
        "CREATE INDEX idx_assets_metadata_state ON assets(metadata_state)",
        "CREATE INDEX idx_derivatives_status ON asset_derivatives(status)",
        "CREATE INDEX idx_derivatives_asset ON asset_derivatives(asset_id)",
    ]
    for statement in statements:
        _execute_v2_migration_statement(conn, statement)


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Apply the versioned migration atomically and set user_version last."""
    conn.commit()
    _backup_v1_database(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA legacy_alter_table=ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_post_v1_additive_columns(conn)
        _migrate_nanosecond_affinity_v1_to_v2(conn)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v2 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.execute("PRAGMA foreign_keys=ON")


def _execute_v3_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v2-to-v3 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v2_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v3 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v2.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add durable catalog claims and scheduled-attempt recency atomically."""
    conn.commit()
    _backup_v2_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        statements: list[str] = []
        if "last_scheduled_attempt_at" not in _db._table_columns(conn, "libraries"):
            statements.append("ALTER TABLE libraries ADD COLUMN last_scheduled_attempt_at REAL")
        library_job_columns = _db._table_columns(conn, "library_jobs")
        if "claimed_by" not in library_job_columns:
            statements.append("ALTER TABLE library_jobs ADD COLUMN claimed_by TEXT")
        if "claim_token" not in library_job_columns:
            statements.append("ALTER TABLE library_jobs ADD COLUMN claim_token TEXT")
        if "lease_expires_at" not in library_job_columns:
            statements.append("ALTER TABLE library_jobs ADD COLUMN lease_expires_at REAL")
        statements.extend(
            [
                "CREATE INDEX IF NOT EXISTS idx_library_jobs_state_lease ON library_jobs(state, lease_expires_at)",
                "CREATE INDEX IF NOT EXISTS idx_libraries_scheduled_attempt "
                "ON libraries(last_scheduled_attempt_at, id)",
            ]
        )
        for statement in statements:
            _execute_v3_migration_statement(conn, statement)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v3 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v4_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v3-to-v4 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v3_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v4 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v3.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Backfill unambiguous file-index ownership atomically."""
    conn.commit()
    _backup_v3_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _execute_v4_migration_statement(
            conn,
            """
            UPDATE file_index AS fi
            SET library_id = (
                SELECT MIN(owner.library_id)
                FROM assets AS owner
                WHERE owner.path = fi.path
            )
            WHERE fi.library_id IS NULL
              AND 1 = (
                  SELECT COUNT(DISTINCT owner.library_id)
                  FROM assets AS owner
                  WHERE owner.path = fi.path
              )
            """,
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v4 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v5_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v4-to-v5 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v4_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v5 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v4.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add durable search-index lifecycle tables without running a backfill."""
    conn.commit()
    _backup_v4_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_search_index_schema(
            conn,
            execute_statement=lambda statement: _execute_v5_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v5 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _initialize_database_conn(conn: sqlite3.Connection) -> None:
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_application_tables = _database_has_application_tables(conn)

    if current_version == 9:
        conn.execute("PRAGMA user_version = 1")
        current_version = 1

    if current_version == 1:
        _migrate_v1_to_v2(conn)
        current_version = 2

    if current_version == 2:
        _migrate_v2_to_v3(conn)
        current_version = 3

    if current_version == 3:
        _migrate_v3_to_v4(conn)
        current_version = 4

    if current_version == 4:
        _migrate_v4_to_v5(conn)
        current_version = 5

    if current_version == 5:
        _cleanup_ignored_index_conn(conn)
        _ensure_post_v1_additive_columns(conn)
        _ensure_v3_schema(conn)
        _ensure_search_index_schema(conn)
        return

    if current_version == 0 and has_application_tables:
        raise RuntimeError("Catalog database has application tables but no schema version; delete it and start fresh")

    if current_version != 0:
        raise RuntimeError(f"Catalog database must be fresh (v0), v1, v2, v3, v4, or v5; found v{current_version}")

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
              last_error TEXT,
              last_scheduled_attempt_at REAL,
              config_revision INTEGER NOT NULL DEFAULT 1
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
              config_revision INTEGER,
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
              finished_at REAL,
              claimed_by TEXT,
              claim_token TEXT,
              lease_expires_at REAL
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
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state_lease
              ON library_jobs(state, lease_expires_at);
            CREATE INDEX IF NOT EXISTS idx_libraries_scheduled_attempt
              ON libraries(last_scheduled_attempt_at, id);

            CREATE TABLE IF NOT EXISTS assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id),
              path TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL DEFAULT 'image',
              mtime_ns INTEGER,
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
              source_mtime_ns INTEGER NOT NULL,
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
              result_code TEXT,
              claimed_by TEXT,
              claim_token TEXT,
              lease_expires_at REAL,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              started_at REAL,
              completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state ON derivative_jobs(state, priority);
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state_lease
              ON derivative_jobs(state, lease_expires_at);

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
    _ensure_post_v1_additive_columns(conn)
    _ensure_v3_schema(conn)
    _ensure_search_index_schema(conn)

    conn.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
    _cleanup_ignored_index_conn(conn)
