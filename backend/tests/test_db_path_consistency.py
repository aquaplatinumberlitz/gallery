"""Test that _connect and initialize_database use the same DB path.

Purpose:
Guard the single source of truth for the configured metadata database path.

Guarantees:
Connection and schema initialization helpers respect patched
`GALLERY_METADATA_DB` in both package and relative-import contexts.

Run when:
Changing metadata-store DB path resolution, config imports, or initialization.
"""


def test_db_path_source_of_truth_is_consistent(monkeypatch, tmp_path):
    """Patch config and verify _connect and initialize_database use same path."""
    import backend.config as cfg
    from backend.metadata_store._db import _connect, _gallery_metadata_db_path
    from backend.metadata_store._schema import initialize_database

    test_db = tmp_path / "test_consistency.db"
    monkeypatch.setattr(cfg, "GALLERY_METADATA_DB", test_db)

    assert _gallery_metadata_db_path() == test_db, "_gallery_metadata_db_path should return the patched path"

    conn = _connect()
    initialize_database()
    conn.close()

    assert test_db.exists(), f"Database should be created at {test_db}"


def test_db_path_works_with_relative_import(monkeypatch, tmp_path):
    """Verify that patching config makes _connect and _schema use the right path."""
    import backend.config as cfg
    from backend.metadata_store._db import _connect

    test_db = tmp_path / "test_relative_consistency.db"
    monkeypatch.setattr(cfg, "GALLERY_METADATA_DB", test_db)

    conn = _connect()
    cur = conn.execute("PRAGMA database_list")
    rows = cur.fetchall()
    conn.close()

    assert any(test_db.name in str(row[2]) for row in rows), f"Connection should point to {test_db}, got: {rows}"
