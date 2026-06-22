"""SQLite connection and database state helpers."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .. import config
from .path_utils import _compare_natural_sql

_DB_LOCK = threading.RLock()
_DB_INITIALIZED = False
_DB_INITIALIZED_PATH: Path | None = None
METADATA_JOB_STATES = ("queued", "running", "done", "failed", "stale", "skipped")
LIBRARY_JOB_ACTIVE_STATES = ("queued", "running")
LIBRARY_JOB_TERMINAL_STATES = ("succeeded", "failed", "cancelled")
MAX_METADATA_JOB_ATTEMPTS = 3
ACTIVE_ASSET_WHERE = "deleted_at IS NULL AND offline = 0"


def _active_asset_where(alias: str | None = None) -> str:
    if alias is None:
        return ACTIVE_ASSET_WHERE
    return f"{alias}.deleted_at IS NULL AND {alias}.offline = 0"


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _database_has_application_tables(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type IN ('table', 'virtual table') AND name NOT LIKE 'sqlite_%'
            LIMIT 1
            """
        ).fetchone()
        is not None
    )


def _connect(*, set_journal_mode: bool = False) -> sqlite3.Connection:
    config.GALLERY_METADATA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.GALLERY_METADATA_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
    if set_journal_mode:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    from . import initialize_database

    initialize_database()
