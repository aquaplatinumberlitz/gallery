# Catalog Scan Pipeline and Unified Status Implementation Status

Last updated: 2026-06-21

Current milestone: Phase 5 complete

Next milestone: Phase 6 — shared status builder, scoped status endpoint, and
admin batch status endpoint

SQLite schema version currently implemented: `PRAGMA user_version = 9`

## Verified Git Baseline

Phase 5 implementation commit:

```text
f70dd8d feat: implement catalog rebuild staging and atomic activation
```

Latest local verification before the Phase 5 implementation commit:

```text
backend ruff check and ruff format --check passed
664 backend tests passed; backend coverage 85.23%
396 frontend unit tests passed
frontend typecheck and production build passed
frontend ESLint and Prettier checks passed
```

Existing FastAPI lifecycle deprecation warnings remain non-blocking.

## Phase Progress

| Phase | Status | Delivered |
| --- | --- | --- |
| 1. Contract fixtures and precedence tests | Complete | Shared v1 fixtures for all four required statuses; shared precedence vectors covering every summary state and locked edge cases; backend and frontend contract tests |
| 2. v9 migration and path/job schema | Complete | v8→v9 migration with exact-version preflight, SQLite backup, transactional schema changes, root_path removal, catalog job scope/trigger/priority/counter fields, file_index library ownership and scan-generation fields, asset scan-generation fields, metadata mtime_ns columns, rebuild staging table, reconciliation/job-selection indexes, shared lexical catalog path containment helpers, and migration coverage |
| 3. Durable Catalog Scan Service and one-library writer lock | Complete | Durable catalog coordinator/worker claiming queued scan/rebuild rows by priority/FIFO, enforcing one running catalog writer per library, preserving queued jobs across restart recovery, and executing scan jobs through the existing discovery/reconciliation pipeline |
| 4. Route triggers through the Catalog Scan Service | Complete | Library creation atomically queues an initial scan job and returns initial_scan_job_id; manual scan, Scan All child jobs, watcher events, startup catch-up, and scheduled reconciliation all submit/coalesce durable catalog scan jobs with documented trigger priorities; watcher and scheduled reconciliation no longer write catalog data directly |
| 5. Rebuild staging/atomic activation and repair removal | Complete | Rebuild enumeration writes to catalog_rebuild_entries staging in bounded batches; one short activation transaction merges staged rows, reconciles missing rows, resets affected metadata state, and removes staging data; POST /api/libraries/{id}/rebuild with confirm=true; rebuild conflict rules from plan §5.3; standalone repair_library_assets function and POST /api/libraries/{id}/repair endpoint removed |
| 6. Shared status builder and status endpoints | Not started | Next milestone |
| 7–10. Browse, frontend migration, old-route hard cut, docs | Not started | Follow the master plan sequence |

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

At handoff, `frontend/src/lib/tanstack/README.md` has an unrelated pre-existing
user modification. It was intentionally excluded from the Phase 1 and status
commits.
