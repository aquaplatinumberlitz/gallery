"""Versioned catalog schema migrations (v1 through v12) and their pre-migration backups."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import _db as _db
from ._db import _gallery_metadata_db_path
from ._schema_ensure import (
    _ensure_generation_signature_schema,
    _ensure_post_v1_additive_columns,
    _ensure_prompt_discovery_schema,
    _ensure_raw_workflow_schema,
    _ensure_search_index_schema,
    _ensure_visual_fingerprint_schema,
    _ensure_workflow_property_schema,
)


def _gallery_metadata_db() -> Path:
    return _gallery_metadata_db_path()


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


def _execute_v6_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v5-to-v6 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v5_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v6 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v5.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Add prompt discovery tables without performing an inline backfill."""
    conn.commit()
    _backup_v5_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_prompt_discovery_schema(
            conn,
            execute_statement=lambda statement: _execute_v6_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v6 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v7_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v6-to-v7 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v6_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v7 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v6.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add typed workflow-property tables without performing a backfill."""
    conn.commit()
    _backup_v6_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_workflow_property_schema(
            conn,
            execute_statement=lambda statement: _execute_v7_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v7 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 7")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v8_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v7-to-v8 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v7_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v8 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v7.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v7_to_v8(conn: sqlite3.Connection) -> None:
    """Add bounded raw-workflow FTS and visible skipped-index counts."""
    conn.commit()
    _backup_v7_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if "skipped_count" not in _db._table_columns(conn, "search_index_jobs"):
            _execute_v8_migration_statement(
                conn,
                "ALTER TABLE search_index_jobs ADD COLUMN skipped_count INTEGER NOT NULL DEFAULT 0",
            )
        if "skipped_count" not in _db._table_columns(conn, "search_index_states"):
            _execute_v8_migration_statement(
                conn,
                "ALTER TABLE search_index_states ADD COLUMN skipped_count INTEGER NOT NULL DEFAULT 0",
            )
        _ensure_raw_workflow_schema(
            conn,
            execute_statement=lambda statement: _execute_v8_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v8 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 8")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v10_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v8-to-v10 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v8_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v10 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v8.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v8_to_v10(conn: sqlite3.Connection) -> None:
    """Add generation signatures without performing an inline backfill.

    Version 9 was used by a historical pre-versioned catalog and remains a
    legacy reset sentinel, so the next maintained schema version is 10.
    """
    conn.commit()
    _backup_v8_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_generation_signature_schema(
            conn,
            execute_statement=lambda statement: _execute_v10_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v10 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v11_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v10-to-v11 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v10_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v11 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v10.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v10_to_v11(conn: sqlite3.Connection) -> None:
    """Add visual fingerprints and band indexes without inline decoding."""
    conn.commit()
    _backup_v10_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _ensure_visual_fingerprint_schema(
            conn,
            execute_statement=lambda statement: _execute_v11_migration_statement(conn, statement),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v11 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 11")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _execute_v12_migration_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Execute one v11-to-v12 migration statement (test injection seam)."""
    conn.execute(statement)


def _backup_v11_database(conn: sqlite3.Connection) -> Path:
    """Create a SQLite-consistent backup before the v12 migration."""
    source = _gallery_metadata_db()
    backup = source.with_suffix(f"{source.suffix}.v11.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
    return backup


def _migrate_v11_to_v12(conn: sqlite3.Connection) -> None:
    """Rebuild composite-key relation tables as compact WITHOUT ROWID tables."""
    conn.commit()
    _backup_v11_database(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in (
            "DROP INDEX IF EXISTS idx_visual_hash_bands_lookup",
            "ALTER TABLE asset_visual_hash_bands RENAME TO asset_visual_hash_bands_v11",
            """
            CREATE TABLE asset_visual_hash_bands (
              asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              hash_kind INTEGER NOT NULL CHECK(hash_kind IN (0, 1)),
              band_no INTEGER NOT NULL CHECK(band_no BETWEEN 0 AND 3),
              band_value INTEGER NOT NULL CHECK(band_value BETWEEN 0 AND 65535),
              PRIMARY KEY(asset_id, hash_kind, band_no)
            ) WITHOUT ROWID
            """,
            """
            INSERT INTO asset_visual_hash_bands (asset_id, library_id, hash_kind, band_no, band_value)
            SELECT asset_id, library_id, hash_kind, band_no, band_value
            FROM asset_visual_hash_bands_v11
            """,
            "DROP TABLE asset_visual_hash_bands_v11",
            """
            CREATE INDEX idx_visual_hash_bands_lookup
              ON asset_visual_hash_bands(hash_kind, band_no, band_value, library_id, asset_id)
            """,
            "ALTER TABLE asset_search_extractions RENAME TO asset_search_extractions_v11",
            """
            CREATE TABLE asset_search_extractions (
              asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
              index_name TEXT NOT NULL,
              source_fingerprint TEXT NOT NULL,
              extractor_version INTEGER NOT NULL,
              status TEXT NOT NULL CHECK (status IN ('ready', 'not_applicable', 'skipped', 'failed')),
              error_code TEXT,
              indexed_at REAL NOT NULL,
              PRIMARY KEY(asset_id, index_name)
            ) WITHOUT ROWID
            """,
            """
            INSERT INTO asset_search_extractions (
              asset_id, index_name, source_fingerprint, extractor_version,
              status, error_code, indexed_at
            )
            SELECT asset_id, index_name, source_fingerprint, extractor_version,
                   status, error_code, indexed_at
            FROM asset_search_extractions_v11
            """,
            "DROP TABLE asset_search_extractions_v11",
        ):
            _execute_v12_migration_statement(conn, statement)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"v12 migration foreign key check failed: {len(violations)} violation(s)")
        conn.execute("PRAGMA user_version = 12")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
