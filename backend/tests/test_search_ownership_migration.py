"""Search ownership migration and cross-library isolation regressions.

Purpose:
Verify schema v4 backfills only unambiguous file-index owners and preserves the
composite library/path authorization boundary used by search and facets.

Guarantees:
* one catalog owner backfills a null file_index.library_id
* ambiguous, ownerless, and already-owned rows are never guessed or overwritten
* v4 migration failure rolls back data/version changes and keeps a v3 backup
* another library's same-path asset cannot authorize a file-index row

Run when:
* changing schema v4, file-index ownership, active catalog predicates, search,
  metadata search, inspector, or facets
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.metadata_store import _connect
from backend.metadata_store import _schema as schema_module
from backend.metadata_store.identity import active_catalog_file_sql


def _insert_library(conn: sqlite3.Connection, name: str) -> int:
    cursor = conn.execute("INSERT INTO libraries(name) VALUES (?)", (name,))
    return int(cursor.lastrowid)


def _insert_asset(conn: sqlite3.Connection, library_id: int, path: str) -> None:
    conn.execute(
        """
        INSERT INTO assets(library_id, path, parent_path, name, type, mtime_ns, size, offline)
        VALUES (?, ?, '/catalog', ?, 'image', 1000000000, 8, 0)
        """,
        (library_id, path, Path(path).name),
    )


def _insert_file_index(conn: sqlite3.Connection, path: str, library_id: int | None) -> None:
    conn.execute(
        """
        INSERT INTO file_index(path, name, parent_path, type, mtime, mtime_ns, size, library_id)
        VALUES (?, ?, '/catalog', 'image', 1.0, 1000000000, 8, ?)
        """,
        (path, Path(path).name, library_id),
    )


def _database_dump(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return "\n".join(conn.iterdump())


def test_v4_backfills_only_exactly_one_catalog_owner(isolated_metadata_db: Path) -> None:
    with _connect() as conn:
        library_a = _insert_library(conn, "A")
        library_b = _insert_library(conn, "B")

        unique_path = "/catalog/unique.png"
        ambiguous_path = "/catalog/ambiguous.png"
        ownerless_path = "/catalog/ownerless.png"
        mismatched_path = "/catalog/mismatched.png"

        _insert_asset(conn, library_a, unique_path)
        _insert_asset(conn, library_a, ambiguous_path)
        _insert_asset(conn, library_b, ambiguous_path)
        _insert_asset(conn, library_a, mismatched_path)

        _insert_file_index(conn, unique_path, None)
        _insert_file_index(conn, ambiguous_path, None)
        _insert_file_index(conn, ownerless_path, None)
        _insert_file_index(conn, mismatched_path, library_b)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()

        schema_module._migrate_v3_to_v4(conn)

        owners = {
            str(row["path"]): row["library_id"]
            for row in conn.execute(
                "SELECT path, library_id FROM file_index WHERE path LIKE '/catalog/%' ORDER BY path"
            )
        }
        assert owners == {
            ambiguous_path: None,
            mismatched_path: library_b,
            ownerless_path: None,
            unique_path: library_a,
        }
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    backup = isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v3.bak")
    assert backup.exists()


def test_v4_migration_failure_rolls_back_and_keeps_v3_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        library_id = _insert_library(conn, "rollback")
        path = "/catalog/rollback.png"
        _insert_asset(conn, library_id, path)
        _insert_file_index(conn, path, None)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()

    before = _database_dump(isolated_metadata_db)
    original = schema_module._execute_v4_migration_statement

    def fail_after_update(conn: sqlite3.Connection, statement: str) -> None:
        original(conn, statement)
        raise RuntimeError("v4 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v4_migration_statement", fail_after_update)
    with _connect() as conn, pytest.raises(RuntimeError, match="v4 injected failure"):
        schema_module._migrate_v3_to_v4(conn)

    assert _database_dump(isolated_metadata_db) == before
    backup = isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v3.bak")
    assert backup.exists()
    assert _database_dump(backup) == before


def test_same_path_asset_from_another_library_cannot_authorize_row(isolated_metadata_db: Path) -> None:
    with _connect() as conn:
        library_a = _insert_library(conn, "owner")
        library_b = _insert_library(conn, "other")
        shared_path = "/catalog/shared.png"
        _insert_file_index(conn, shared_path, library_a)
        _insert_asset(conn, library_b, shared_path)

        predicate = active_catalog_file_sql(fi_alias="fi")
        count = conn.execute(f"SELECT COUNT(*) FROM file_index AS fi WHERE {predicate}").fetchone()[0]
        assert count == 0

        _insert_asset(conn, library_a, shared_path)
        count = conn.execute(f"SELECT COUNT(*) FROM file_index AS fi WHERE {predicate}").fetchone()[0]
        assert count == 1

        plan = [
            str(row["detail"])
            for row in conn.execute(f"EXPLAIN QUERY PLAN SELECT fi.path FROM file_index AS fi WHERE {predicate}")
        ]
        owner_steps = [detail for detail in plan if "catalog_asset" in detail]
        assert owner_steps
        assert all("SCAN catalog_asset" not in detail for detail in owner_steps)
        assert any("library_id" in detail and "path" in detail for detail in owner_steps)
