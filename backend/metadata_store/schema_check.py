"""Schema-check helper for the catalog metadata database."""

from __future__ import annotations

import sqlite3

_TABLES: tuple[str, ...] = (
    "assets",
    "image_metadata",
    "metadata_index_jobs",
    "asset_derivatives",
    "derivative_jobs",
    "libraries",
    "library_import_paths",
    "catalog_rebuild_entries",
    "integrity_check_runs",
    "search_index_states",
    "search_index_jobs",
    "asset_search_extractions",
    "asset_visual_fingerprints",
    "asset_visual_hash_bands",
)

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "assets": (
        "id",
        "library_id",
        "path",
        "parent_path",
        "name",
        "type",
        "mtime_ns",
        "size",
        "metadata_state",
        "deleted_at",
        "offline",
        "indexed_at",
    ),
    "image_metadata": (
        "path",
        "mtime",
        "mtime_ns",
        "size",
        "width",
        "height",
    ),
    "metadata_index_jobs": (
        "path",
        "mtime_ns",
        "size",
        "state",
        "library_id",
        "queued_at",
        "finished_at",
        "updated_at",
    ),
    "asset_derivatives": (
        "id",
        "asset_id",
        "kind",
        "status",
        "cache_path",
        "byte_size",
        "updated_at",
    ),
    "derivative_jobs": (
        "id",
        "derivative_id",
        "state",
        "updated_at",
    ),
    "search_index_states": (
        "index_name",
        "library_id",
        "state",
        "schema_version",
        "extractor_version",
        "active_job_id",
    ),
    "search_index_jobs": (
        "id",
        "index_name",
        "library_id",
        "mode",
        "state",
        "cursor_asset_id",
        "claim_token",
        "lease_expires_at",
    ),
    "asset_search_extractions": (
        "asset_id",
        "index_name",
        "source_fingerprint",
        "extractor_version",
        "status",
    ),
    "asset_visual_fingerprints": (
        "asset_id",
        "library_id",
        "source_mtime_ns",
        "source_size",
        "derivative_role",
        "derivative_version",
        "algorithm_version",
        "dhash_horizontal",
        "dhash_vertical",
        "color_grid",
    ),
    "asset_visual_hash_bands": (
        "asset_id",
        "library_id",
        "hash_kind",
        "band_no",
        "band_value",
    ),
}

_INDEXES: tuple[str, ...] = (
    "idx_metadata_index_jobs_claim",
    "idx_metadata_index_jobs_library_state",
    "idx_image_metadata_mtime_size",
    "idx_image_metadata_mtime_ns_name",
    "idx_image_metadata_inspector_date",
    "idx_integrity_check_runs_finished",
    "idx_search_index_jobs_pick",
    "idx_search_index_jobs_one_active",
    "idx_asset_search_extractions_index_status",
    "idx_visual_hash_bands_lookup",
)


def check_catalog_schema(conn: sqlite3.Connection) -> list[str]:
    """Check that the catalog DB has all required lifecycle tables, columns, and indexes.

    Returns a list of issue strings (empty list = all good).
    """
    issues: list[str] = []

    for table in _TABLES:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            issues.append(f"Missing table: {table}")
            continue

        existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        expected_cols = _TABLE_COLUMNS.get(table, ())
        for col in expected_cols:
            if col not in existing_cols:
                issues.append(f"Table '{table}' missing column: {col}")

    for index in _INDEXES:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index,),
        ).fetchone()
        if not exists:
            issues.append(f"Missing index: {index}")

    return issues
