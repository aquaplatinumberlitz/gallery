"""SQLite connection and database state helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .path_utils import _compare_natural_sql

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


def _gallery_metadata_db_path() -> Path:
    """Single source of truth for the metadata database path."""
    from ..config import GALLERY_METADATA_DB

    return GALLERY_METADATA_DB


class ClosingConnection(sqlite3.Connection):
    """A ``sqlite3.Connection`` whose ``with`` block always closes it.

    The stdlib ``with conn:`` only commits or rolls back and leaves the connection open until it is
    garbage collected (a ``ResourceWarning`` at best, an exhausted descriptor table at worst when a
    traceback or cycle keeps it alive). Every connection this package opens is a ``ClosingConnection``,
    so ``with _connect_read() as conn:`` commits (or rolls back) and then closes it. Long-lived
    connections (the database writer, the direct write path) are closed explicitly and never used as a
    context manager. Do not use ``with conn:`` on a connection you intend to keep using.
    """

    def __exit__(self, exc_type, exc_value, traceback):  # noqa: ANN001, ANN204
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def open_connection(
    target: str | Path,
    *,
    timeout: float = 30.0,
    isolation_level: str | None = "",
    uri: bool = False,
) -> ClosingConnection:
    """Open a ``ClosingConnection`` and close it again if the caller never receives it.

    Every production ``sqlite3.connect`` goes through here (or ``contextlib.closing`` for one-off
    backup files) so that a failure while configuring the connection cannot leak a descriptor.
    """
    kwargs: dict = {"timeout": timeout, "uri": uri, "factory": ClosingConnection}
    if isolation_level != "":
        kwargs["isolation_level"] = isolation_level
    return sqlite3.connect(target, **kwargs)


def _configure_or_close(conn: sqlite3.Connection, configure) -> sqlite3.Connection:  # noqa: ANN001
    """Run ``configure(conn)``; on any failure close ``conn`` before re-raising."""
    try:
        configure(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def _connect(*, set_journal_mode: bool = False) -> sqlite3.Connection:
    """Open the read-write connection (default isolation). The caller owns it and must close it.

    Use it as ``with _connect() as conn:`` for a one-shot transaction (commit or rollback, then close) or
    close it explicitly when it is long-lived.
    """
    db_path = _gallery_metadata_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def configure(conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
        if set_journal_mode:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")

    return _configure_or_close(open_connection(db_path, timeout=30), configure)


def _connect_read() -> sqlite3.Connection:
    """Open a read-only connection for status snapshots. The caller owns it: ``with`` closes it.

    The connection takes no Python lock and refuses writes (``query_only``), so a
    status read cannot queue behind, or block, any worker. Transactions are explicit
    (``isolation_level=None``) so callers choose exactly when a snapshot starts.
    """
    db_path = _gallery_metadata_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def configure(conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA query_only=ON")

    return _configure_or_close(open_connection(db_path, timeout=30, isolation_level=None), configure)


def _connect_readonly(*, timeout: float = 30.0) -> sqlite3.Connection:
    """Open an OS-level read-only connection (``mode=ro``) that may still create TEMP tables.

    For read paths that stage intermediate rows in a temp table (facets) or need a short busy timeout
    (raw workflow search). Writes to the database fail at the file level; TEMP objects live in a private
    temp store, which ``PRAGMA query_only`` would forbid.
    """
    db_path = _gallery_metadata_db_path()

    def configure(conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")

    conn = open_connection(f"file:{db_path}?mode=ro", timeout=timeout, isolation_level=None, uri=True)
    return _configure_or_close(conn, configure)


@contextmanager
def _read_snapshot(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection whose reads all come from one consistent WAL snapshot.

    Opens a read connection, starts one deferred read transaction (the snapshot is
    fixed by the first read), and always rolls back and closes it. No Python lock is
    taken: WAL readers do not block the writer and the writer does not block them.
    Pass ``conn`` to join a snapshot owned by an outer status build; it is yielded
    unchanged and left open for its owner.
    """
    if conn is not None:
        yield conn
        return
    owned = _connect_read()
    try:
        owned.execute("BEGIN")
        yield owned
    finally:
        try:
            if owned.in_transaction:
                owned.execute("ROLLBACK")
        finally:
            owned.close()


def init_db() -> None:
    from ._schema import initialize_database

    initialize_database()
