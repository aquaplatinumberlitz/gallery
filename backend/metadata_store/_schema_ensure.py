"""Idempotent ``CREATE ... IF NOT EXISTS`` / additive-column helpers for the catalog schema."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ._db import _ensure_column


def _ensure_generation_signature_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create compact versioned generation-intent signatures."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS asset_generation_signatures (
          asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          prompt_hash BLOB,
          family_hash BLOB,
          recipe_hash BLOB,
          exact_hash BLOB,
          normalizer_version INTEGER NOT NULL,
          extractor_version INTEGER NOT NULL,
          source_mtime_ns INTEGER NOT NULL,
          source_size INTEGER NOT NULL,
          indexed_at REAL NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_generation_signatures_prompt
          ON asset_generation_signatures(library_id, prompt_hash, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_generation_signatures_family
          ON asset_generation_signatures(library_id, family_hash, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_generation_signatures_recipe
          ON asset_generation_signatures(library_id, recipe_hash, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_generation_signatures_exact
          ON asset_generation_signatures(library_id, exact_hash, asset_id)
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


def _ensure_visual_fingerprint_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create Pillow-only visual fingerprints and indexed hash bands."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS asset_visual_fingerprints (
          asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          source_mtime_ns INTEGER NOT NULL,
          source_size INTEGER NOT NULL,
          derivative_role TEXT NOT NULL,
          derivative_version INTEGER NOT NULL,
          algorithm_version INTEGER NOT NULL,
          dhash_horizontal BLOB NOT NULL CHECK(length(dhash_horizontal) = 8),
          dhash_vertical BLOB NOT NULL CHECK(length(dhash_vertical) = 8),
          color_grid BLOB NOT NULL CHECK(length(color_grid) = 48),
          indexed_at REAL NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS asset_visual_hash_bands (
          asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          hash_kind INTEGER NOT NULL CHECK(hash_kind IN (0, 1)),
          band_no INTEGER NOT NULL CHECK(band_no BETWEEN 0 AND 3),
          band_value INTEGER NOT NULL CHECK(band_value BETWEEN 0 AND 65535),
          PRIMARY KEY(asset_id, hash_kind, band_no)
        ) WITHOUT ROWID
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_visual_hash_bands_lookup
          ON asset_visual_hash_bands(hash_kind, band_no, band_value, library_id, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_visual_fingerprints_library_asset
          ON asset_visual_fingerprints(library_id, asset_id)
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


def _ensure_raw_workflow_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create bounded canonical raw-workflow documents and trigram FTS."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS workflow_raw_documents (
          asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
          library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
          canonical_text TEXT NOT NULL,
          byte_length INTEGER NOT NULL,
          source_fingerprint TEXT NOT NULL,
          extractor_version INTEGER NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_raw_library_asset
          ON workflow_raw_documents(library_id, asset_id)
        """,
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS workflow_raw_fts USING fts5(
          canonical_text,
          content='workflow_raw_documents',
          content_rowid='asset_id',
          tokenize='trigram'
        )
        """,
        """
        CREATE TRIGGER IF NOT EXISTS workflow_raw_documents_ai
        AFTER INSERT ON workflow_raw_documents BEGIN
          INSERT INTO workflow_raw_fts(rowid, canonical_text)
          VALUES (new.asset_id, new.canonical_text);
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS workflow_raw_documents_ad
        AFTER DELETE ON workflow_raw_documents BEGIN
          INSERT INTO workflow_raw_fts(workflow_raw_fts, rowid, canonical_text)
          VALUES ('delete', old.asset_id, old.canonical_text);
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS workflow_raw_documents_au
        AFTER UPDATE ON workflow_raw_documents BEGIN
          INSERT INTO workflow_raw_fts(workflow_raw_fts, rowid, canonical_text)
          VALUES ('delete', old.asset_id, old.canonical_text);
          INSERT INTO workflow_raw_fts(rowid, canonical_text)
          VALUES (new.asset_id, new.canonical_text);
        END
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


def _ensure_file_index_trigram_schema(conn: sqlite3.Connection) -> None:
    """Create and backfill the trigger-maintained filename substring index."""
    existed = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'file_index_fts_trigram'").fetchone()
        is not None
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS file_index_fts_trigram USING fts5(
          name,
          path UNINDEXED,
          type UNINDEXED,
          parent_path UNINDEXED,
          content='file_index',
          content_rowid='rowid',
          tokenize='trigram'
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS file_index_trigram_ai
        AFTER INSERT ON file_index BEGIN
          INSERT INTO file_index_fts_trigram(rowid, name, path, type, parent_path)
          VALUES (new.rowid, new.name, new.path, new.type, new.parent_path);
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS file_index_trigram_ad
        AFTER DELETE ON file_index BEGIN
          INSERT INTO file_index_fts_trigram(
            file_index_fts_trigram, rowid, name, path, type, parent_path
          ) VALUES ('delete', old.rowid, old.name, old.path, old.type, old.parent_path);
        END
        """
    )
    conn.execute("DROP TRIGGER IF EXISTS file_index_trigram_au")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS file_index_trigram_au
        AFTER UPDATE OF name, path, type, parent_path ON file_index BEGIN
          INSERT INTO file_index_fts_trigram(
            file_index_fts_trigram, rowid, name, path, type, parent_path
          ) VALUES ('delete', old.rowid, old.name, old.path, old.type, old.parent_path);
          INSERT INTO file_index_fts_trigram(rowid, name, path, type, parent_path)
          VALUES (new.rowid, new.name, new.path, new.type, new.parent_path);
        END
        """
    )
    if not existed:
        conn.execute("INSERT INTO file_index_fts_trigram(file_index_fts_trigram) VALUES ('rebuild')")


def _ensure_workflow_property_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create typed, registry-backed ComfyUI node/property storage."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS workflow_nodes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          node_key TEXT NOT NULL,
          node_type TEXT NOT NULL,
          title TEXT,
          extractor_version INTEGER NOT NULL,
          source_fingerprint TEXT NOT NULL,
          UNIQUE(asset_id, node_key)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_nodes_type_asset
          ON workflow_nodes(node_type, asset_id, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_nodes_asset
          ON workflow_nodes(asset_id, id)
        """,
        """
        CREATE TABLE IF NOT EXISTS workflow_property_values (
          node_id INTEGER NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
          property_key TEXT NOT NULL,
          ordinal INTEGER NOT NULL DEFAULT 0,
          value_type TEXT NOT NULL CHECK (
            value_type IN ('text', 'integer', 'real', 'boolean', 'uint64_token')
          ),
          value_text TEXT,
          value_text_folded TEXT,
          value_integer INTEGER,
          value_real REAL,
          value_boolean INTEGER,
          PRIMARY KEY(node_id, property_key, ordinal),
          CHECK (
            (value_type = 'text' AND value_text IS NOT NULL AND value_text_folded IS NOT NULL
              AND value_integer IS NULL AND value_real IS NULL AND value_boolean IS NULL)
            OR (value_type = 'integer' AND value_text IS NULL AND value_text_folded IS NULL
              AND value_integer IS NOT NULL AND value_real IS NULL AND value_boolean IS NULL)
            OR (value_type = 'real' AND value_text IS NULL AND value_text_folded IS NULL
              AND value_integer IS NULL AND value_real IS NOT NULL AND value_boolean IS NULL)
            OR (value_type = 'boolean' AND value_text IS NULL AND value_text_folded IS NULL
              AND value_integer IS NULL AND value_real IS NULL AND value_boolean IN (0, 1))
            OR (value_type = 'uint64_token' AND value_text IS NOT NULL AND value_text_folded IS NULL
              AND value_integer IS NULL AND value_real IS NULL AND value_boolean IS NULL)
          )
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_text
          ON workflow_property_values(property_key, value_text_folded, node_id)
          WHERE value_type = 'text'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_integer
          ON workflow_property_values(property_key, value_integer, node_id)
          WHERE value_type = 'integer'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_real
          ON workflow_property_values(property_key, value_real, node_id)
          WHERE value_type = 'real'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_boolean
          ON workflow_property_values(property_key, value_boolean, node_id)
          WHERE value_type = 'boolean'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_uint64
          ON workflow_property_values(property_key, value_text, node_id)
          WHERE value_type = 'uint64_token'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_node_text
          ON workflow_property_values(node_id, property_key, value_text_folded)
          WHERE value_type = 'text'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_node_integer
          ON workflow_property_values(node_id, property_key, value_integer)
          WHERE value_type = 'integer'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_node_real
          ON workflow_property_values(node_id, property_key, value_real)
          WHERE value_type = 'real'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_node_boolean
          ON workflow_property_values(node_id, property_key, value_boolean)
          WHERE value_type = 'boolean'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_property_node_uint64
          ON workflow_property_values(node_id, property_key, value_text)
          WHERE value_type = 'uint64_token'
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


def _ensure_prompt_discovery_schema(
    conn: sqlite3.Connection,
    *,
    execute_statement: Callable[[str], object] | None = None,
) -> None:
    """Create normalized prompt values and observed model-alias storage."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS asset_prompt_values (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          kind TEXT NOT NULL CHECK (kind IN ('positive', 'negative')),
          display_text TEXT NOT NULL,
          normalized_text TEXT NOT NULL,
          search_text TEXT NOT NULL,
          value_hash BLOB NOT NULL,
          extractor_version INTEGER NOT NULL,
          source_fingerprint TEXT NOT NULL,
          UNIQUE(asset_id, kind)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_prompt_values_kind_hash_asset
          ON asset_prompt_values(kind, value_hash, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_prompt_values_kind_search_asset
          ON asset_prompt_values(kind, search_text, asset_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_prompt_values_asset
          ON asset_prompt_values(asset_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS asset_model_identity_values (
          asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          normalized_name TEXT NOT NULL,
          normalized_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          display_hash TEXT NOT NULL,
          source_fingerprint TEXT NOT NULL,
          PRIMARY KEY(asset_id, normalized_name, normalized_hash)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_model_identity_pair
          ON asset_model_identity_values(normalized_name, normalized_hash, asset_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS model_identity_aliases (
          normalized_name TEXT NOT NULL,
          normalized_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          display_hash TEXT NOT NULL,
          asset_count INTEGER NOT NULL,
          last_seen_mtime_ns INTEGER NOT NULL,
          PRIMARY KEY(normalized_name, normalized_hash)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_model_identity_aliases_name
          ON model_identity_aliases(normalized_name, normalized_hash)
        """,
    ]
    execute = execute_statement or conn.execute
    for statement in statements:
        execute(statement)


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
          skipped_count INTEGER NOT NULL DEFAULT 0,
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
          skipped_count INTEGER NOT NULL DEFAULT 0,
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
        ) WITHOUT ROWID
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
    conn.execute("DROP INDEX IF EXISTS idx_image_metadata_mtime_ns_natural")
    conn.execute("DROP INDEX IF EXISTS idx_image_metadata_name_natural_ns")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_ns_name ON image_metadata(mtime_ns DESC, name, path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_metadata_inspector_date "
        "ON image_metadata(COALESCE(mtime_ns, CAST(mtime * 1000000000 AS INTEGER)) DESC, name, path)"
    )
    _ensure_column(conn, "metadata_index_jobs", "folder_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "metadata_index_jobs", "root_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "metadata_index_jobs", "library_id", "INTEGER")
    _ensure_column(conn, "metadata_index_jobs", "priority", "INTEGER NOT NULL DEFAULT 3")
    # Claim fencing, lease, and retry-backoff columns for the DB-claim metadata worker.
    _ensure_column(conn, "metadata_index_jobs", "claimed_by", "TEXT")
    _ensure_column(conn, "metadata_index_jobs", "claim_token", "TEXT")
    _ensure_column(conn, "metadata_index_jobs", "lease_expires_at", "REAL")
    _ensure_column(conn, "metadata_index_jobs", "next_attempt_at", "REAL")
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
    # Latest-job-per-derivative lookups (status aggregates, reconcile coalescing) must seek, not scan.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derivative_jobs_derivative_id ON derivative_jobs(derivative_id, id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_claim  ON metadata_index_jobs(state, priority, queued_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_library_state  ON metadata_index_jobs(library_id, state)"
    )
    # Supervisor recovery looks up expired or ownerless ``running`` rows by (state, lease).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_state_lease ON metadata_index_jobs(state, lease_expires_at)"
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
