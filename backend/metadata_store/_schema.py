"""Database schema creation and migration entry points.

Idempotent ensure helpers live in ``_schema_ensure``, versioned migrations in ``_migrations``,
and the fresh-database DDL in ``_schema_ddl``.
"""

from __future__ import annotations

import logging
import sqlite3

from . import _db as _db
from ._db import _connect, _database_has_application_tables
from ._migrations import (
    _gallery_metadata_db,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
    _migrate_v4_to_v5,
    _migrate_v5_to_v6,
    _migrate_v6_to_v7,
    _migrate_v7_to_v8,
    _migrate_v8_to_v10,
    _migrate_v10_to_v11,
    _migrate_v11_to_v12,
)
from ._schema_ddl import FRESH_DATABASE_DDL
from ._schema_ensure import (
    _ensure_file_index_trigram_schema,
    _ensure_generation_signature_schema,
    _ensure_post_v1_additive_columns,
    _ensure_prompt_discovery_schema,
    _ensure_raw_workflow_schema,
    _ensure_runtime_counters,
    _ensure_search_index_schema,
    _ensure_v3_schema,
    _ensure_visual_fingerprint_schema,
    _ensure_workflow_property_schema,
)
from .file_index import _cleanup_ignored_index_conn

logger = logging.getLogger(__name__)

CATALOG_SCHEMA_VERSION = 12


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
        _migrate_v5_to_v6(conn)
        current_version = 6

    if current_version == 6:
        _migrate_v6_to_v7(conn)
        current_version = 7

    if current_version == 7:
        _migrate_v7_to_v8(conn)
        current_version = 8

    if current_version == 8:
        _migrate_v8_to_v10(conn)
        current_version = 10

    if current_version == 10:
        _migrate_v10_to_v11(conn)
        current_version = 11

    if current_version == 11:
        _migrate_v11_to_v12(conn)
        current_version = 12

    if current_version == 12:
        _cleanup_ignored_index_conn(conn)
        _ensure_post_v1_additive_columns(conn)
        _ensure_v3_schema(conn)
        _ensure_search_index_schema(conn)
        _ensure_prompt_discovery_schema(conn)
        _ensure_workflow_property_schema(conn)
        _ensure_raw_workflow_schema(conn)
        _ensure_file_index_trigram_schema(conn)
        _ensure_generation_signature_schema(conn)
        _ensure_visual_fingerprint_schema(conn)
        _ensure_runtime_counters(conn)
        return

    if current_version == 0 and has_application_tables:
        raise RuntimeError("Catalog database has application tables but no schema version; delete it and start fresh")

    if current_version != 0:
        raise RuntimeError(f"Catalog database must be fresh (v0-v12); found v{current_version}")

    conn.executescript(FRESH_DATABASE_DDL)
    _ensure_post_v1_additive_columns(conn)
    _ensure_v3_schema(conn)
    _ensure_search_index_schema(conn)
    _ensure_prompt_discovery_schema(conn)
    _ensure_workflow_property_schema(conn)
    _ensure_raw_workflow_schema(conn)
    _ensure_file_index_trigram_schema(conn)
    _ensure_generation_signature_schema(conn)
    _ensure_visual_fingerprint_schema(conn)
    _ensure_runtime_counters(conn)

    conn.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
    _cleanup_ignored_index_conn(conn)
