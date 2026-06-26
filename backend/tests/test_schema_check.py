"""Tests for the schema-check helper.

Purpose:
Validate lifecycle-required catalog schema checks for tables, columns, and
indexes.

Guarantees:
A fresh catalog DB passes, and missing lifecycle tables, columns, or indexes are
reported with stable issue strings.

Run when:
Changing catalog lifecycle schema requirements, additive migrations, or
schema_check reporting.
"""

from __future__ import annotations

import sqlite3

from backend.metadata_store._schema import initialize_database
from backend.metadata_store._db import _connect
from backend.metadata_store.schema_check import check_catalog_schema


def test_all_good_on_fresh_db(isolated_metadata_db) -> None:
    initialize_database()
    with _connect() as conn:
        issues = check_catalog_schema(conn)
    assert issues == []


def test_missing_table_reported() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            parent_path TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            mtime_ns REAL,
            size INTEGER,
            metadata_state TEXT,
            deleted_at REAL,
            offline INTEGER NOT NULL DEFAULT 0,
            indexed_at REAL
        );
        CREATE TABLE image_metadata (
            path TEXT NOT NULL,
            mtime REAL,
            mtime_ns INTEGER,
            size INTEGER,
            width INTEGER,
            height INTEGER
        );
        CREATE TABLE metadata_index_jobs (
            path TEXT NOT NULL,
            mtime_ns INTEGER,
            size INTEGER,
            state TEXT NOT NULL,
            library_id INTEGER,
            queued_at REAL,
            finished_at REAL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE asset_derivatives (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            cache_path TEXT,
            byte_size INTEGER,
            updated_at REAL NOT NULL
        );
        CREATE TABLE derivative_jobs (
            id INTEGER PRIMARY KEY,
            derivative_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE libraries (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE library_import_paths (
            id INTEGER PRIMARY KEY,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL
        );
        CREATE TABLE catalog_rebuild_entries (
            job_id INTEGER NOT NULL,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            PRIMARY KEY(job_id, path)
        );
    """)
    issues = check_catalog_schema(conn)
    assert "Missing table: integrity_check_runs" in issues


def test_missing_column_reported() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            parent_path TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            mtime_ns REAL,
            size INTEGER,
            metadata_state TEXT,
            deleted_at REAL,
            offline INTEGER NOT NULL DEFAULT 0
        )
    """)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()]
    assert "indexed_at" not in cols
    issues = check_catalog_schema(conn)
    assert "Table 'assets' missing column: indexed_at" in issues


def test_missing_index_reported() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            parent_path TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            mtime_ns REAL,
            size INTEGER,
            metadata_state TEXT,
            deleted_at REAL,
            offline INTEGER NOT NULL DEFAULT 0,
            indexed_at REAL
        );
        CREATE TABLE image_metadata (
            path TEXT NOT NULL UNIQUE,
            mtime REAL,
            mtime_ns INTEGER,
            size INTEGER,
            width INTEGER,
            height INTEGER
        );
        CREATE TABLE metadata_index_jobs (
            path TEXT NOT NULL,
            mtime_ns INTEGER,
            size INTEGER,
            state TEXT NOT NULL,
            library_id INTEGER,
            queued_at REAL,
            finished_at REAL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE asset_derivatives (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            cache_path TEXT,
            byte_size INTEGER,
            updated_at REAL NOT NULL
        );
        CREATE TABLE derivative_jobs (
            id INTEGER PRIMARY KEY,
            derivative_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE libraries (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE library_import_paths (
            id INTEGER PRIMARY KEY,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL
        );
        CREATE TABLE catalog_rebuild_entries (
            job_id INTEGER NOT NULL,
            library_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            PRIMARY KEY(job_id, path)
        );
        CREATE TABLE integrity_check_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger TEXT NOT NULL,
            started_at REAL NOT NULL,
            status TEXT NOT NULL,
            issues_json TEXT NOT NULL,
            repairs_json TEXT NOT NULL
        );
    """)
    issues = check_catalog_schema(conn)
    assert "Missing index: idx_metadata_index_jobs_claim" in issues
