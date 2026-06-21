# Catalog Scan Pipeline and Unified Status Implementation Status

Last updated: 2026-06-21

Current milestone: Phase 7 complete

Next milestone: Phase 8 — admin/sidebar actions, labels, polling, and SSE
invalidation migration

SQLite schema version currently implemented: `PRAGMA user_version = 9`

## Verified Git Baseline

Phase 7 implementation commit:

```text
8b3270d feat: add catalog browse endpoint
```

Latest verification before the Phase 7 implementation commit:

```text
./test.sh fast passed
backend ruff check and ruff format --check passed
679 backend tests passed; backend coverage 85.63%
frontend ESLint and Prettier checks passed
399 frontend unit tests passed
frontend typecheck and production build passed
```

Existing FastAPI lifecycle deprecation, Sass import, Rollup annotation, eval,
and chunk-size warnings remain non-blocking.

## Phase Progress

| Phase | Status | Delivered |
| --- | --- | --- |
| 1. Contract fixtures and precedence tests | Complete | Shared v1 fixtures for all four required statuses; shared precedence vectors covering every summary state and locked edge cases; backend and frontend contract tests |
| 2. v9 migration and path/job schema | Complete | v8→v9 migration with exact-version preflight, SQLite backup, transactional schema changes, root_path removal, catalog job scope/trigger/priority/counter fields, file_index library ownership and scan-generation fields, asset scan-generation fields, metadata mtime_ns columns, rebuild staging table, reconciliation/job-selection indexes, shared lexical catalog path containment helpers, and migration coverage |
| 3. Durable Catalog Scan Service and one-library writer lock | Complete | Durable catalog coordinator/worker claiming queued scan/rebuild rows by priority/FIFO, enforcing one running catalog writer per library, preserving queued jobs across restart recovery, and executing scan jobs through the existing discovery/reconciliation pipeline |
| 4. Route triggers through the Catalog Scan Service | Complete | Library creation atomically queues an initial scan job and returns initial_scan_job_id; manual scan, Scan All child jobs, watcher events, startup catch-up, and scheduled reconciliation all submit/coalesce durable catalog scan jobs with documented trigger priorities; watcher and scheduled reconciliation no longer write catalog data directly |
| 5. Rebuild staging/atomic activation and repair removal | Complete | Rebuild enumeration writes to catalog_rebuild_entries staging in bounded batches; one short activation transaction merges staged rows, reconciles missing rows, resets affected metadata state, and removes staging data; POST /api/libraries/{id}/rebuild with confirm=true; rebuild conflict rules from plan §5.3; standalone repair_library_assets function and POST /api/libraries/{id}/repair endpoint removed |
| 6. Shared status builder and status endpoints | Complete | Contract-v1 status builder backed by grouped catalog/metadata/runtime facts; `GET /api/libraries/{id}/status` with optional `scope_path`; `GET /api/libraries/status` admin batch endpoint; global runtime envelope; schema/endpoint coverage for initial queued scan, batch envelope, scoped prefix isolation, out-of-library scope rejection, degraded availability, and Scan All zero-library terminal behavior |
| 7. Read-only `/api/browse` and gallery query migration | Complete | DB-only catalog browse route with virtual import-root listing, path-scoped asset/folder pagination, offline tombstones hidden by default, out-of-library scope rejection, no scan/write side effects, and gallery infinite query migration from `/api/scan` to `/api/browse` keyed by library ID |
| 8–10. Admin/sidebar migration, old-route hard cut, docs | Not started | Follow the master plan sequence |

## Phase 7 Delivered

Read-only browse API (`backend/browse.py`, `backend/metadata_store.py`):

- Added `GET /api/browse` with required `library_id`, optional `path`,
  `cursor`, `limit`, and reserved `include_offline` query params.
- Null/omitted `path` returns the library virtual root as ordered synthetic
  `import_root` folder entries from `library_import_paths`; duplicate leaf
  names are disambiguated with the full path and entries expose
  `display_label` plus catalog-derived availability.
- Non-null paths are validated with the component-aware catalog path helpers
  against the selected library's import paths; cross-library or
  out-of-library scopes return the standard `bad_request` envelope.
- Real folder pages read only persisted catalog rows from `assets`, cached
  dimensions from `image_metadata`, and derivative readiness from
  `asset_derivatives`; normal browse hides offline/deleted tombstones.
- Empty or partially populated catalog pages return empty browse results
  without invoking filesystem scan, metadata queueing, catalog jobs, or direct
  writes.

Frontend gallery migration:

- Added `browseDirectory`, `BrowseResponse`, browse query keys, and
  `useInfiniteBrowseQuery`.
- `GalleryGrid` now fetches gallery folders/media through `/api/browse` using
  the active library ID and current browse path.
- Library job/progress SSE handling invalidates browse query prefixes for the
  affected library.
- Removed the unused `useInfiniteScanQuery` composable and `query/scan.ts`
  helper so the gallery infinite query no longer targets `/api/scan`.

Phase 7 coverage added:

- backend route tests for virtual roots, real folder pagination, offline
  filtering, cross-library scope rejection, unknown query rejection, and
  empty-catalog no-scan/no-write behavior;
- frontend unit tests for browse API params and browse query keys.

Remaining by design for later phases:

- Legacy `/api/scan`, old index-status/repair/rebuild UI actions, old global
  index status routes, config cleanup, and documentation hard-cut work remain
  in Phase 8 through Phase 10.

## Phase 6 Delivered

Unified status builder (`backend/catalog/status_builder.py`):

- Builds contract-v1 `UnifiedStatus` envelopes from persisted libraries,
  import paths, catalog jobs, active assets, metadata jobs, metadata records,
  watcher health, scheduled reconciliation, catalog worker state, and metadata
  worker runtime.
- Applies the shared contract precedence function to the same normalized facts
  used by the Phase 1 fixture tests.
- Supports library-wide and path-scoped status with component-aware path
  containment; similar path prefixes do not leak sibling data.
- Computes availability, scan/rebuild state, metadata state and progress,
  issue counts/latest issue, `last_scan_at`, `last_index_at`, and one
  `global_runtime` object per envelope.
- Batch library status uses grouped SQL queries for library/import-path/job,
  asset/metadata-count, last-index, and metadata-issue data instead of issuing
  one status request per row.

API surface (`backend/libraries.py`):

- Added `GET /api/libraries/{id}/status` with optional `scope_path`.
- Added `GET /api/libraries/status` for admin batch status.
- Status scopes outside the registered library return the standard
  `bad_request` envelope.

Related catalog availability behavior:

- Whole-library scan/rebuild now proceeds when at least one import path is
  online, skips offline roots, records degraded library state, and exposes
  degraded availability through unified status.
- Scan All with zero libraries now completes the parent job immediately as
  `succeeded` with message `No libraries to scan`.

Phase 6 coverage added (`backend/tests/`):

- contract schema validation for single and batch status envelopes;
- initial queued scan status and metadata queued semantics;
- admin batch status route shape and route ordering;
- scoped status descendant counts without sibling prefix leakage;
- out-of-library status scope rejection;
- degraded availability after a successful covering scan;
- zero-library Scan All parent terminal state.

## Phase 5 Delivered

Rebuild staging and activation (`backend/metadata_store.py`):

- `enumerate_to_rebuild_staging` walks scope paths and writes discovered
  entries to `catalog_rebuild_entries` in bounded batches
  (`GALLERY_CATALOG_WRITE_BATCH_SIZE`, default 500) without holding a write
  transaction during filesystem enumeration; returns discovery counters and
  the list of supported asset paths for later metadata queueing.
- `activate_rebuild_staging` runs one short `BEGIN IMMEDIATE` transaction
  that upserts staged rows into `file_index` and `assets`, marks missing
  rows in scope as offline, resets `metadata_state` to `pending` for assets
  whose `mtime_ns`/`size` changed, updates `last_seen_scan_job_id`, deletes
  staging rows for the job only after commit, and rolls back on any error.
- `delete_rebuild_staging` removes orphaned staging rows for a failed or
  cancelled rebuild job.

Catalog rebuild worker (`backend/catalog/service.py`):

- `execute_rebuild_job` runs a claimed rebuild job through enumeration,
  activation, and metadata queueing; on failure it cleans up staging rows
  and marks the job failed with the plan's "previous catalog remains
  active" message, leaving the canonical generation untouched.
- `queue_rebuild` creates a durable rebuild job via the coordinator and
  wakes the worker.

Rebuild conflict rules (`backend/metadata_store.py`):

- `create_or_coalesce_catalog_job` now enforces plan §5.3 rebuild rules:
  manual rebuild raises `CatalogJobConflict` (409) when any catalog work is
  already running or another rebuild is queued/running for a covering scope;
  manual rebuild cancels queued non-rebuild scans it covers; manual scan
  while rebuild is queued/running raises `CatalogJobConflict`; automated
  scans during rebuild defer as queued follow-ups.

API surface (`backend/libraries.py`):

- `POST /api/libraries/{id}/rebuild` accepts a confirmed
  `LibraryRebuildRequest` with optional `scope_path`, validates the scope
  belongs to a configured import path, and returns the documented
  `library_busy` 409 envelope with `requested_operation` and `active_job`
  on conflict.
- `POST /api/libraries/{id}/repair` and the `repair_library_assets`
  function are removed; normal catalog scan performs discovery and
  reconciliation in one canonical operation.
- `APIError` now accepts an optional `extra` dict for structured 409
  payloads.

Configuration (`backend/config.py`):

- `GALLERY_CATALOG_WRITE_BATCH_SIZE` (default 500) controls the staging
  batch size.

Phase 5 coverage added (`backend/tests/`):

- rebuild job executes through the catalog pipeline and discovers assets;
- staging rows are cleared after successful activation;
- rebuild marks missing assets offline;
- rebuild failure preserves the canonical catalog and cleans up staging;
- manual scan while rebuild is queued raises `CatalogJobConflict`;
- manual rebuild cancels queued scans;
- manual rebuild while scan is running raises `CatalogJobConflict`;
- rebuild API returns the documented job envelope, requires confirmation,
  and rejects out-of-library scope;
- scan respects exclusion patterns across import paths;
- scan reconciles assets without deleting derivatives.

Legacy repair tests were replaced with equivalent scan/rebuild coverage.

## Working Tree Note

At Phase 7 handoff, `_codex_phase7_prompt.txt` remains an untracked local
prompt file. It was intentionally excluded from the Phase 7 commits.
