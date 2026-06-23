# Metadata Store Split Plan

Status: Archived — plan is complete, current architecture is in docs/ARCHITECTURE.md

Created: 2026-06-22

## Objective

Split `backend/metadata_store.py` (5,542 lines, 165 definitions) into a subpackage `backend/metadata_store/` with ~13 focused modules, while maintaining full backward compatibility via `__init__.py` re-export shim.

## Target Structure

```
backend/metadata_store/
├── __init__.py           # Shim: re-export ALL symbols consumers import
├── _db.py                # _DB_LOCK, _DB_INITIALIZED, _DB_INITIALIZED_PATH, _connect
├── _schema.py            # _initialize_database_conn, _migrate_v8_to_v9, _v9_*
├── types.py              # CachedDimensions, MetadataIndexJob, MetadataQueueResult,
│                         # CatalogJobConflict, LibraryOverlapError, CatalogBrowseScopeError
├── path_utils.py         # canonicalize_catalog_path, catalog_path_contains, 
│                         # _catalog_paths_overlap, _natural_sort_parts, _compare_natural_sql
├── _asset_store.py       # _upsert_asset_conn (shared between file_index + metadata_persist)
├── _resources.py         # _iter_metadata_loras, _iter_metadata_resources, 
│                         # _replace_image_resources_conn, _backfill_image_resources_conn
├── library_store.py      # create/update/register/unregister_library, get_library,
│                         # list_libraries, get_library_for_path, get_library_progress,
│                         # get_library_stats, get_gallery_stats, update_library_state,
│                         # get_first_library_root, get_asset_state_for_path,
│                         # _serialize_library_conn, _find_library_for_path_conn,
│                         # _assert_no_import_path_overlap_conn, _replace_library_paths_conn,
│                         # _replace_library_patterns_conn, _reconcile_library_configuration_conn
├── job_store.py          # create_job, create_or_coalesce_catalog_job, claim_next_catalog_job,
│                         # update_job_state, get_job, get_library_jobs, list_jobs,
│                         # list_active_jobs, create_or_get_active_scan_job, recover_stale_jobs,
│                         # enqueue_startup_catalog_scans, _job_scope_covers,
│                         # _serialize_catalog_enqueue_result, _serialize_library_job
├── rebuild_store.py      # enumerate_to_rebuild_staging, activate_rebuild_staging,
│                         # delete_rebuild_staging, _reconcile_assets_conn, reconcile_library_assets
├── browse_store.py       # get_catalog_browse_listing, get_asset_folder_listing,
│                         # _browse_import_paths_conn, _validate_browse_scope,
│                         # _browse_visibility_sql, _browse_availability_from_library_state,
│                         # _browse_import_root_name, _import_root_availability,
│                         # _browse_folder_counts_conn, _browse_folder_counts_batch_conn,
│                         # _catalog_browse_virtual_root_conn, _catalog_browse_path_conn
├── metadata_queue.py     # queue_metadata_index_paths, mark_metadata_jobs_running/done/stale/failed,
│                         # get_metadata_index_status, _current_metadata_is_complete,
│                         # _metadata_job_from_path, _mark_current_metadata_done
├── metadata_persist.py   # upsert_extracted_metadata, upsert_metadata_batch,
│                         # upsert_metadata_result, index_image, index_images,
│                         # get_lightbox_metadata, get_cached_dimensions_for_files,
│                         # upsert_image_dimensions, _needs_reindex,
│                         # _upsert_extracted_metadata_conn, _sync_dimensions_to_file_index,
│                         # _metadata_param
├── folder_index.py       # update_folder_index_state, get_folder_index_state,
│                         # get_warm_folder_listing, get_folder_indexed_paths,
│                         # mark_folder_index_incomplete, _scan_folder_counts,
│                         # index_files_from_scan
├── file_index.py         # index_file, index_directory_tree, cleanup_stale_index,
│                         # cleanup_ignored_index, clear_index_records,
│                         # _cleanup_stale_index_conn, _cleanup_ignored_index_conn,
│                         # _scoped_path_where, _normalize_file_type, _path_value
├── search_store.py       # search_metadata, search_index, search_index_fielded,
│                         # _search_fts, _search_like, _search_file_index_fts,
│                         # _search_prompt_rows, _search_fielded_photos,
│                         # _format_file_index_rows, _format_prompt_rows, _format_rows,
│                         # _snippet, _count_fts, _count_like, _escape_fts_token,
│                         # _unicode_match_query, _trigram_match_query, _like_pattern,
│                         # _like_escape, _folder_relative_path, _is_inside_root,
│                         # _path_prefix, _scope_clause, _build_scope_named,
│                         # _optional_row_value
└── inspector_store.py    # list_library_inspector_rows, get_library_inspector_metadata,
                          # _dedupe_inspector_rows, _encode_inspector_cursor,
                          # _build_library_inspector_keyset_where, _format_inspector_row,
                          # _lora_summary, _truncate_preview, _safe_json_loads,
                          # _clean_resource_text, _normalize_resource_kind,
                          # _resource_raw_json, _split_lora_text,
                          # _resource_rows_from_metadata
```

## Shim Strategy

`__init__.py` uses plain re-export:

```python
# backend/metadata_store/__init__.py
from ._db import _DB_LOCK, _DB_INITIALIZED, _DB_INITIALIZED_PATH, _connect, init_db
from ._schema import initialize_database, CATALOG_SCHEMA_VERSION, ...
# ... etc for all modules
```

**DO NOT** use PEP 562 `__setattr__` (not supported for module-level assignment forwarding).

### Critical: Mutable State Handling

`_DB_INITIALIZED`, `_DB_LOCK`, `_DB_INITIALIZED_PATH` must live in one file (`_db.py`) and be the **single source of truth**. Tests currently patch `metadata_store._DB_INITIALIZED`. After split:

- **Option A (recommended):** Update tests to patch `backend.metadata_store._db._DB_INITIALIZED` instead.
- **Option B:** Add a test-only `_reset_database_state_for_tests(db_path)` helper in `_db.py`.

Either way, the shim `__init__.py` re-exports `_DB_INITIALIZED` as a read reference — assignment to it in tests will NOT propagate to `_db.py`. Tests MUST be updated.

### Files affected by test patch migration (~6 files)

| File | Current patch | New patch |
|------|--------------|-----------|
| `backend/tests/conftest.py:176-177` | `ms._DB_INITIALIZED` / `ms._DB_INITIALIZED_PATH` | `ms._db._DB_INITIALIZED` / `ms._db._DB_INITIALIZED_PATH` |
| `backend/tests/test_libraries_catalog.py:271` | `metadata_store._DB_INITIALIZED` | `metadata_store._db._DB_INITIALIZED` |
| `backend/tests/test_derivatives.py:142` | `ms._DB_INITIALIZED` | `ms._db._DB_INITIALIZED` |
| `backend/tests/test_facets.py:199` | `ms._DB_INITIALIZED` | `ms._db._DB_INITIALIZED` |
| `backend/tests/test_search_coverage.py:176` | (indirect via import) | N/A (already fresh import) |
| Others with `from backend.metadata_store import _connect` | Fine — `_connect` is a function, rebinding-safe | N/A |

## Incremental Steps (ordered by risk, lowest first)

### Step 1: Package shell — `git mv`
```
git mv backend/metadata_store.py backend/metadata_store/__init__.py
```
- Creates `backend/metadata_store/__init__.py` with ALL original content
- All imports (`from backend.metadata_store import X`) continue working
- **Verify:** `pytest -q backend/tests/ && ruff check`

### Step 2: `path_utils.py` — pure helpers, no DB
- Move: `canonicalize_catalog_path`, `catalog_path_contains`, `_catalog_paths_overlap`, `_natural_sort_parts`, `_compare_natural_sql`, `_path_is_within`
- `from . import path_utils` in `__init__.py`, then `from .path_utils import ...`
- **Risk:** None — pure functions
- **Verify:** `pytest -q backend/tests/ && ruff check`

### Step 3: `_db.py` + fix test patches — CRITICAL
- Move: `_DB_LOCK`, `_DB_INITIALIZED`, `_DB_INITIALIZED_PATH`, `_connect`, `_table_columns`, `_ensure_column`, `_table_exists`, `_database_has_application_tables`, `_active_asset_where`, `ACTIVE_ASSET_WHERE`, `METADATA_JOB_STATES`, `LIBRARY_JOB_ACTIVE_STATES`, `LIBRARY_JOB_TERMINAL_STATES`, `MAX_METADATA_JOB_ATTEMPTS`, `init_db`
- Update `__init__.py` to `from ._db import _DB_LOCK, ...`
- **THIS IS WHERE TEST PATCHES BREAK:** Update ~5-6 test files (see table above)
- **Risk:** **HIGH** — shared singleton. Must verify all tests pass after.
- **Verify:** `pytest -q backend/tests/ --tb=short`

### Step 4: `types.py` — dataclasses + exceptions
- Move: `CachedDimensions`, `MetadataIndexJob`, `MetadataQueueResult`, `CatalogJobConflict`, `LibraryOverlapError`, `CatalogBrowseScopeError`
- **Risk:** Low
- **Verify:** `pytest -q backend/tests/ && ruff check`

### Step 5: `_asset_store.py` + `_resources.py` — shared helpers
- `_asset_store.py`: `_upsert_asset_conn`
- `_resources.py`: `_iter_metadata_loras`, `_iter_metadata_resources`, `_replace_image_resources_conn`, `_backfill_image_resources_conn`, `_resource_rows_from_metadata`, `_clean_resource_text`, `_normalize_resource_kind`, `_resource_raw_json`, `_split_lora_text`, `_lora_summary`
- **Risk:** Low — both are internal helpers with known consumers
- **Verify:** `pytest -q backend/tests/`

### Step 6: `_schema.py` — schema + migration
- Move: `_initialize_database_conn`, `initialize_database`, `_migrate_v8_to_v9`, `_ensure_v9_catalog_schema`, `_validate_v9_preflight`, `_v9_backup_path`, `_backup_database_before_v9`, `_v9_import_paths`, `_format_path_conflict`, `_rebuild_libraries_without_root_path`, `_populate_v9_file_index_library_ids`, `_import_cached_derivatives_conn`, `_ensure_default_library_conn`, `CATALOG_SCHEMA_VERSION`
- **Import cross-dependencies:** `_schema.py` imports `_cleanup_ignored_index_conn` (→ `file_index.py`), `_backfill_image_resources_conn` (→ `_resources.py`), `_ensure_default_library_conn` (→ `library_store.py`). These must already be extracted.
- **Risk:** Medium — schema initialization is critical for DB startup
- **Verify:** `pytest -q backend/tests/ && ./test.sh lint`

### Step 7: `library_store.py` + `job_store.py` + `rebuild_store.py`
- Move library CRUD (lines ~1700–2055), job management (lines ~1190–1700), rebuild staging (lines ~2055–2417)
- **Risk:** Medium — many consumers in `libraries.py`, `catalog/service.py`
- **Verify:** `pytest -q backend/tests/`

### Step 8: `browse_store.py`
- Move browse DTO functions (lines ~2417–2910)
- **Risk:** Medium — used by `backend/browse.py` route
- **Verify:** `pytest -q backend/tests/`

### Step 9: `metadata_queue.py` + `metadata_persist.py`
- Move metadata job queue (lines ~2910–3260) and persistence (lines ~3260–3460, ~3884–3994)
- **Risk:** Medium — `_upsert_asset_conn` dependency already extracted in Step 5
- **Verify:** `pytest -q backend/tests/`

### Step 10: `folder_index.py` + `file_index.py`
- Move folder index (lines ~3460–3884, ~4196–4258) and file index (lines ~3994–4385)
- **Risk:** Low-Medium — self-contained
- **Verify:** `pytest -q backend/tests/`

### Step 11: `search_store.py` + `inspector_store.py`
- Move FTS/search (lines ~4385–5020) and inspector (lines ~5017–5542)
- **Risk:** Low — mostly read-only consumers in `backend/search.py`
- **Verify:** `pytest -q backend/tests/`

### Step 12: Cleanup
- Remove dead re-exports from `__init__.py` if any symbols are no longer imported by consumers
- Run `pytest -q backend/tests/ --tb=long --cov=backend --cov-fail-under=85`
- Run `./test.sh lint`

## Verification Checklist (per step)

```bash
cd backend
python -m pytest -q tests/ --tb=short 2>&1 | tail -3
ruff check metadata_store/
ruff format --check metadata_store/
```

After Step 3:
```bash
# Focus on DB tests
python -m pytest -q tests/test_app.py tests/test_libraries_catalog.py tests/test_derivatives.py tests/test_facets.py --tb=long
```

Full test suite after Step 12:
```bash
cd backend && python -m pytest -q tests/ --cov=backend --cov-fail-under=85
cd frontend && pnpm run typecheck && pnpm run build
```

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| `_DB_INITIALIZED` monkeypatch breaks | **HIGH** | Update test patch targets in Step 3 (see table above) |
| `initialize_database` calls helpers not yet extracted | MEDIUM | Don't move `_schema.py` until its dependencies are extracted |
| Cross-module import cycle | MEDIUM | Check with `python -c "import backend.metadata_store"` after each step |
| Log name changes (`__name__`) | LOW | Update log filter config if any |
| Git blame history loss | LOW | `git mv` preserves history via rename detection |
