"""DDL for a brand-new catalog database (executed once before additive ensures run)."""

from __future__ import annotations

FRESH_DATABASE_DDL = """
            CREATE TABLE IF NOT EXISTS image_metadata (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              mtime REAL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              format TEXT,
              mode TEXT,
              has_alpha INTEGER,
              prompt TEXT,
              negative_prompt TEXT,
              model TEXT,
              sampler TEXT,
              seed TEXT,
              steps INTEGER,
              cfg_scale REAL,
              raw_metadata_text TEXT,
              metadata_json TEXT,
              updated_at REAL,
              indexed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_name
              ON image_metadata(mtime DESC, name);
            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_ns_name
              ON image_metadata(mtime_ns DESC, name, path);
            CREATE INDEX IF NOT EXISTS idx_image_metadata_inspector_date
              ON image_metadata(COALESCE(mtime_ns, CAST(mtime * 1000000000 AS INTEGER)) DESC, name, path);

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts_trigram USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='trigram'
            );

            CREATE TRIGGER IF NOT EXISTS image_metadata_ai AFTER INSERT ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_ad AFTER DELETE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_au AFTER UPDATE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TABLE IF NOT EXISTS file_index (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              type TEXT NOT NULL,
              mtime REAL,
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              indexed_at REAL,
              library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
              last_seen_scan_job_id INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_file_index_parent_path ON file_index(parent_path);
            CREATE INDEX IF NOT EXISTS idx_file_index_type ON file_index(type);
            CREATE INDEX IF NOT EXISTS idx_file_index_name ON file_index(name);
            CREATE INDEX IF NOT EXISTS idx_file_index_library_parent_seen
              ON file_index(library_id, parent_path, last_seen_scan_job_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS file_index_fts USING fts5(
              name,
              path UNINDEXED,
              type UNINDEXED,
              parent_path UNINDEXED,
              tokenize='unicode61'
            );

            CREATE TABLE IF NOT EXISTS metadata_index_jobs (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              folder_path TEXT NOT NULL,
              root_path TEXT NOT NULL,
              mtime REAL NOT NULL,
              mtime_ns INTEGER,
              size INTEGER NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              queued_at REAL,
              started_at REAL,
              finished_at REAL,
              updated_at REAL NOT NULL,
              claimed_by TEXT,
              claim_token TEXT,
              lease_expires_at REAL,
              next_attempt_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_state
              ON metadata_index_jobs(state);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_state_lease
              ON metadata_index_jobs(state, lease_expires_at);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_folder_path
              ON metadata_index_jobs(folder_path);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_root_path
              ON metadata_index_jobs(root_path);
            CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_updated_at
              ON metadata_index_jobs(updated_at);

            CREATE TABLE IF NOT EXISTS image_resources (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL,
              kind TEXT NOT NULL,
              name TEXT NOT NULL DEFAULT '',
              hash TEXT,
              resource_hash TEXT,
              weight TEXT,
              strength TEXT,
              raw_json TEXT,
              updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_image_resources_path
              ON image_resources(path);
            CREATE INDEX IF NOT EXISTS idx_image_resources_kind_name
              ON image_resources(kind, name);
            CREATE INDEX IF NOT EXISTS idx_image_resources_hash
              ON image_resources(resource_hash);
            CREATE INDEX IF NOT EXISTS idx_image_resources_hash_value
              ON image_resources(hash);

            CREATE TABLE IF NOT EXISTS folder_index_state (
              path TEXT PRIMARY KEY,
              dir_mtime_ns INTEGER NOT NULL,
              indexed_at REAL NOT NULL,
              complete INTEGER NOT NULL DEFAULT 0,
              child_count INTEGER NOT NULL DEFAULT 0,
              folder_count INTEGER NOT NULL DEFAULT 0,
              image_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS libraries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'discovering',
              watch_enabled INTEGER NOT NULL DEFAULT 1,
              warm_enabled INTEGER NOT NULL DEFAULT 1,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              last_scan_at REAL,
              last_error TEXT,
              last_scheduled_attempt_at REAL,
              config_revision INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS library_import_paths (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, path),
              UNIQUE(library_id, position)
            );
            CREATE INDEX IF NOT EXISTS idx_library_import_paths_path
              ON library_import_paths(path);

            CREATE TABLE IF NOT EXISTS library_exclusion_patterns (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
              pattern TEXT NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(library_id, pattern),
              UNIQUE(library_id, position)
            );

            CREATE TABLE IF NOT EXISTS library_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
              parent_job_id INTEGER REFERENCES library_jobs(id) ON DELETE SET NULL,
              config_revision INTEGER,
              type TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'queued',
              scope_path TEXT,
              trigger TEXT NOT NULL DEFAULT 'manual',
              priority INTEGER NOT NULL DEFAULT 50,
              progress_current INTEGER NOT NULL DEFAULT 0,
              progress_total INTEGER,
              message TEXT,
              error TEXT,
              counters TEXT NOT NULL DEFAULT '{}',
              discovered_assets INTEGER NOT NULL DEFAULT 0,
              created_assets INTEGER NOT NULL DEFAULT 0,
              updated_assets INTEGER NOT NULL DEFAULT 0,
              offline_assets INTEGER NOT NULL DEFAULT 0,
              metadata_queued_assets INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              started_at REAL,
              finished_at REAL,
              claimed_by TEXT,
              claim_token TEXT,
              lease_expires_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_library_jobs_library_created
              ON library_jobs(library_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state
              ON library_jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_catalog_pick
              ON library_jobs(library_id, type, state, scope_path);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state_priority_created
              ON library_jobs(state, priority DESC, created_at);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_parent
              ON library_jobs(parent_job_id);
            CREATE INDEX IF NOT EXISTS idx_library_jobs_state_lease
              ON library_jobs(state, lease_expires_at);
            CREATE INDEX IF NOT EXISTS idx_libraries_scheduled_attempt
              ON libraries(last_scheduled_attempt_at, id);

            CREATE TABLE IF NOT EXISTS assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES libraries(id),
              path TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL DEFAULT 'image',
              mtime_ns INTEGER,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              orientation INTEGER,
              indexed_at REAL,
              metadata_state TEXT DEFAULT 'pending',
              offline INTEGER NOT NULL DEFAULT 0,
              deleted_at REAL,
              mime_type TEXT,
              duration_ms INTEGER,
              codec TEXT,
              last_seen_scan_job_id INTEGER,
              UNIQUE(library_id, path)
            );
            CREATE INDEX IF NOT EXISTS idx_assets_library_path ON assets(library_id, path);
            CREATE INDEX IF NOT EXISTS idx_assets_library_parent ON assets(library_id, parent_path);
            CREATE INDEX IF NOT EXISTS idx_assets_reconcile_scan
              ON assets(library_id, parent_path, last_seen_scan_job_id);
            CREATE INDEX IF NOT EXISTS idx_assets_library_seen
              ON assets(library_id, last_seen_scan_job_id);

            CREATE TABLE IF NOT EXISTS asset_derivatives (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id INTEGER NOT NULL REFERENCES assets(id),
              kind TEXT NOT NULL,
              variant TEXT NOT NULL,
              source_mtime_ns INTEGER NOT NULL,
              source_size INTEGER NOT NULL,
              format TEXT NOT NULL DEFAULT 'webp',
              quality INTEGER NOT NULL DEFAULT 85,
              max_long_edge INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              cache_path TEXT,
              byte_size INTEGER,
              last_accessed_at REAL,
              attempts INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              UNIQUE(asset_id, kind, variant, source_mtime_ns, source_size)
            );
            CREATE INDEX IF NOT EXISTS idx_derivatives_status ON asset_derivatives(status);
            CREATE INDEX IF NOT EXISTS idx_derivatives_asset ON asset_derivatives(asset_id);

            CREATE TABLE IF NOT EXISTS derivative_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              derivative_id INTEGER NOT NULL REFERENCES asset_derivatives(id),
              priority INTEGER NOT NULL DEFAULT 3,
              state TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              result_code TEXT,
              claimed_by TEXT,
              claim_token TEXT,
              lease_expires_at REAL,
              created_at REAL NOT NULL DEFAULT (julianday('now')),
              updated_at REAL NOT NULL DEFAULT (julianday('now')),
              started_at REAL,
              completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state ON derivative_jobs(state, priority);
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state_lease
              ON derivative_jobs(state, lease_expires_at);
            CREATE INDEX IF NOT EXISTS idx_derivative_jobs_derivative_id
              ON derivative_jobs(derivative_id, id);

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
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_library_job
              ON catalog_rebuild_entries(library_id, job_id);
            CREATE INDEX IF NOT EXISTS idx_catalog_rebuild_entries_parent
              ON catalog_rebuild_entries(library_id, parent_path);
            """
