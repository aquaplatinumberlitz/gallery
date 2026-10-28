"""SQLite connection and database state helpers."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from .path_utils import _compare_natural_sql

_WRITER_THREAD = threading.local()
_T = TypeVar("_T")


class WriterThreadLockError(RuntimeError):
    """Raised when the database writer thread tries to take ``_DB_LOCK``.

    Code running on the writer thread (inside a writer op) must never wait for the global lock: a
    thread that holds it may itself be waiting for the writer, and the two would deadlock. The error
    turns that hang into an immediate, attributable failure of the one op.
    """


def mark_writer_thread(active: bool) -> None:
    """Flag the calling thread as the database writer thread (set once, when the thread starts)."""
    _WRITER_THREAD.active = active


class _DatabaseLock:
    """The process-wide reentrant write lock, refusing to be taken by the database writer thread."""

    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if getattr(_WRITER_THREAD, "active", False):
            raise WriterThreadLockError("the database writer thread must not acquire _DB_LOCK")
        return self._lock.acquire(blocking, timeout)

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self._lock.release()

    def is_owned(self) -> bool:
        """Return whether the calling thread currently holds the lock."""
        return bool(self._lock._is_owned())  # type: ignore[attr-defined]


_DB_LOCK = _DatabaseLock()
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


def _connect(*, set_journal_mode: bool = False) -> sqlite3.Connection:
    db_path = _gallery_metadata_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
    if set_journal_mode:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _connect_read() -> sqlite3.Connection:
    """Open a read-only connection for status snapshots.

    The connection never takes ``_DB_LOCK`` and refuses writes (``query_only``), so a
    status read cannot queue behind, or block, any worker. Transactions are explicit
    (``isolation_level=None``) so callers choose exactly when a snapshot starts.
    """
    db_path = _gallery_metadata_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.create_collation("GALLERY_NATURAL", _compare_natural_sql)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA query_only=ON")
    return conn


@contextmanager
def _read_snapshot(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection whose reads all come from one consistent WAL snapshot.

    Opens a read connection, starts one deferred read transaction (the snapshot is
    fixed by the first read), and always rolls back and closes it. ``_DB_LOCK`` is not
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


def run_direct_immediate(
    op: Callable[[sqlite3.Connection], _T], *, connect: Callable[[], sqlite3.Connection] | None = None
) -> _T:
    """Run ``op(conn)`` in one direct ``BEGIN IMMEDIATE`` transaction under ``_DB_LOCK`` (the flag-off path).

    Every catalog write below is a function of a connection (so it can run as a database writer op) plus
    this wrapper as its ``run_write`` fallback; ``_DB_LOCK`` is only ever taken here, never while waiting
    for the writer.
    """
    with _DB_LOCK, (connect or _connect)() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = op(conn)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        return result
