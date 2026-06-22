# Catalog Scan Pipeline and Unified Status Implementation Status

Last updated: 2026-06-22

Current milestone: Phase 8 complete

Next milestone: Phase 9 — remove old routes, fallback branches, config, types,
and dead code

SQLite schema version currently implemented: `PRAGMA user_version = 9`

## Verified Git Baseline

Phase 8 implementation commit:

```text
8cb976e feat: migrate admin and sidebar to unified catalog status
```

Latest verification before the Phase 8 implementation commit:

```text
./test.sh fast passed
backend ruff check and ruff format --check passed
683 backend tests passed; backend coverage 85.56%
frontend ESLint and Prettier checks passed
426 frontend unit tests passed
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
| 8. Admin/sidebar migration to unified status | Complete | useCatalogStatusQuery and useLibraryStatusBatchQuery composables with 2.5s/60s polling and contract-v1 guard; shared catalog labels utility; admin list joins batch status by ID with Last index column; admin detail shows Availability/File scan/Metadata/Issues/Last scan/Last index separately; sidebar IndexStatusPanel/Card/DetailsPopover migrated to UnifiedStatus with scope copy, Photos found/Photo details ready mapping, library-scoped scan/rebuild actions, and updated rebuild wording; Repair UI removed; SSE invalidates status keys; scan/rebuild mutations seed/invalidate status; LibraryInspector rebuild tracking migrated to UnifiedStatus |
| 9–10. Old-route hard cut and documentation | Not started | Follow the master plan sequence |

## Phase 8 Delivered

Unified status composables (`frontend/src/composables/`):

- Added `useCatalogStatusQuery(libraryId, scopePath?, enabled?)` returning the
  contract-v1 `StatusResponseEnvelope` for a library-wide or path-scoped
  status. Polls every 2.5 seconds while scan/metadata work is active and every
  60 seconds when stable; pauses when the document is hidden; refetches on
  window focus with a 300 ms debounce.
- Added `useLibraryStatusBatchQuery()` returning the admin batch envelope and
  a `statusByLibrary` map keyed by library ID for O(1) row joins. Uses the
  same active/stable polling intervals.
- Both composables run every response through `assertStatusEnvelope` /
  `assertLibraryStatusBatch` and expose a `contractError` computed so the UI
  can surface the plan's "App updated, please reload" message instead of
  rendering partial status.

Contract guard and labels (`frontend/src/lib/catalog/`):

- Added `contractGuard.ts` with `StatusContractError`,
  `assertStatusEnvelope`, `assertLibraryStatusBatch`, and
  `STATUS_CONTRACT_ERROR_MESSAGE`. The guard rejects unknown
  `contract_version`, non-object envelopes, missing required `UnifiedStatus`
  fields, and invalid batch item shapes.
- Added `labels.ts` with `getCatalogStatusPresentation`,
  `CATALOG_STATUS_LABELS`, and `getCatalogStatusLabel` keyed by
  `SummaryState`. The presentation map locks the plan's label/variant/tone/
  pulse table for `unknown`, `offline`, `needs_scan`, `scanning`, `indexing`,
  `needs_update`, `ready_with_issues`, `ready`, and `error`.

API client and query keys (`frontend/src/services/api.ts`,
`frontend/src/query/keys.ts`):

- Added `fetchCatalogStatus(libraryId, scopePath?)` calling
  `GET /api/libraries/{id}/status`.
- Added `fetchLibraryStatusBatch()` calling `GET /api/libraries/status`.
- Added `rebuildLibrary(libraryId, scopePath?)` calling
  `POST /api/libraries/{id}/rebuild` with `confirm=true` and optional
  `scope_path`.
- Extended `scanLibrary` to accept an optional `scopePath` sent as the
  `scope_path` body field.
- Added query keys `statusRoot()`, `statusBatch()`, `statusLibrary(id)`,
  `statusPathRoot(id)`, and `statusPath(id, path)` matching the plan's
  `['status','library',id]` and `['status','path',id,normalizedPath]`
  conventions.

Admin list migration (`frontend/src/components/admin/LibraryListPage.vue`,
`LibraryStatusBadge.vue`, `LibrarySummaryPanel.vue`, `LibraryProgressBar.vue`,
`LibraryActionMenu.vue`):

- The list joins `useLibrariesQuery()` with `useLibraryStatusBatchQuery()` by
  library ID; it no longer issues a per-row status/progress request.
- `LibraryStatusBadge` and `LibrarySummaryPanel` accept a `UnifiedStatus`
  prop and derive labels, counts, and progress exclusively from it. No
  component reads `RegisteredLibrary.state` or `LibraryProgress` for
  semantics.
- Replaced the list's `Updated` column with a `Last index` column sourced
  from `status.last_index_at`; the `Last scan` column now prefers
  `status.last_scan_at`.
- `LibraryActionMenu` no longer emits or renders a Repair action.
- Scan calls use the new `scanMutation.mutate({ id })` shape; the
  `repairMutation` remains as dead code for Phase 9 cleanup.

Admin detail migration (`frontend/src/components/admin/LibraryDetailPage.vue`):

- Uses `useCatalogStatusQuery(libraryId)` for the library-wide status and
  renders Availability, File scan, Metadata progress, issue breakdown, Last
  scan, and Last index in separate sections.
- Removed the Repair button; retained the configuration `Updated` field on
  the detail page per plan §8.1.
- The delete dialog's estimated assets now falls back to
  `status.metadata.total_assets` then `library.asset_count`.

Sidebar migration (`frontend/src/components/IndexStatusPanel.vue`,
`IndexStatusCard.vue`, `IndexStatusDetailsPopover.vue`,
`IndexStatusBadge.vue`):

- `IndexStatusPanel` resolves the active library via
  `useActiveLibrarySelection` and calls `useCatalogStatusQuery` with the
  current browse path. Null/empty path yields library-wide status; a real
  path yields path-scoped status.
- Scope copy is `Entire library · All import paths` at the virtual root and
  `Current folder · Including subfolders` for real folders.
- `Photos found` maps to `metadata.total_assets`; `Photo details ready` maps
  to `metadata.ready_assets`. Last scan and Last index are shown separately.
- `Indexer working in another folder` is preserved through
  `metadata.global_active_outside_scope`.
- Scan invokes `POST /api/libraries/{id}/scan` via `scanLibrary`; Rebuild
  invokes the confirmed library-scoped rebuild endpoint via `rebuildLibrary`.
  The rebuild confirm dialog and tooltip use the plan's "rebuild indexed
  files and extracted metadata" wording instead of "clear index cache".
- `IndexStatusBadge` now accepts the shared `CatalogStatusPresentation`
  type so admin and sidebar share one label/color/precedence utility.
- Contract errors surface the "App updated, please reload" message inline.

SSE invalidation and mutations (`frontend/src/composables/admin/`):

- `useLibraryEvents` now invalidates `statusRoot`, `statusLibrary(id)`, and
  `statusPathRoot(id)` for every catalog job transition so active status
  queries refetch immediately.
- `useLibraryMutations` scan and rebuild mutations accept `{ id, scopePath? }`
  and invalidate status library/path/batch keys plus browse keys on success.
  A new `rebuildMutation` wraps `rebuildLibrary` with the same invalidation.
  Create/update/scan-all/unregister also invalidate the relevant status keys.

LibraryInspector rebuild tracking (`frontend/src/components/LibraryInspector.vue`):

- Replaced `useIndexStatusQuery` with `useCatalogStatusQuery` keyed by the
  active library ID and current path.
- Rebuild tracking now watches `metadata.ready_assets` and unified
  scan/metadata states instead of `IndexStatusResponse.metadata_records` and
  `hasActiveIndexWork`/`hasQueuedIndexWork`.

Phase 8 coverage added (`frontend/src/`):

- query keys test for `statusRoot`, `statusBatch`, `statusLibrary`,
  `statusPathRoot`, and `statusPath`;
- API client tests for `fetchCatalogStatus`, `fetchLibraryStatusBatch`,
  `rebuildLibrary`, and scoped `scanLibrary`;
- mutation invalidation tests for scan (status keys), rebuild, and scan-all
  (status root);
- contract guard tests for valid/invalid envelopes and batch responses;
- catalog labels tests locking the plan's label table, pulse behavior, and
  variant/tone mapping.

Remaining by design for later phases:

- Legacy `/api/scan`, `/api/index/status`, `/api/index/rebuild`,
  `useIndexStatusQuery`, `useLibraryProgressQuery`, `fetchIndexStatus`,
  `rebuildIndex`, `scanDirectory`, `repairLibrary`, old `IndexStatusResponse`
  and `LibraryProgress` types, `utils/indexStatus.ts`, `utils/indexStatusCopy.ts`,
  `utils/libraryStatus.ts` presentation helpers, and `GALLERY_DB_REQUIRED`
  configuration remain as dead code for Phase 9 removal.
- Architecture/API/config documentation updates and the final release gate
  remain in Phase 10.

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

At Phase 8 handoff, `_opencode_phase8_prompt.txt` remains an untracked local
prompt file. It was intentionally excluded from the Phase 8 commits. The
earlier `_codex_phase7_prompt.txt` from Phase 7 also remains untracked.

## Follow-up Audit Fixes

Applied after Phase 8 against audit findings on the unified status contract
and pipeline edge cases.

### Fix 1: backend ready_assets current-metadata guard

Commit `c3042a1 fix: require current image_metadata row for ready_assets in
status builder`. `status_builder.py` now joins `image_metadata` on
`path + mtime_ns + size` when counting `ready_assets`, so stale metadata rows
no longer inflate the ready count. Coverage added in
`backend/tests/test_catalog_status_ready_assets.py`.

### Fix 2: frontend contract guard nested field validation

Commit `4c5a3f7 fix: add nested field validation to status contract guard`.
`contractGuard.ts` now rejects missing `metadata.total_assets`, invalid
`summary_state` strings, missing `scan.state`, and missing `scope.library_id`.
Negative coverage added in `frontend/src/lib/catalog/__tests__/contractGuard.test.ts`.

### Fix 3: dead repair mutation and types cleanup

Commit `7c5ce11 cleanup: remove dead repair mutation and types`. Removed the
orphaned `repairLibrary` mutation, `LibraryRepair*` types, and the matching
API client surface that were left behind when Phase 5 deleted the backend
repair endpoint.

### Fix 4: component-level tests for catalog status edge states

Commit `test: add component-level tests for catalog status edge states`.
Added `frontend/src/components/__tests__/IndexStatusDetailsPopover.test.ts`
covering `ready`, `ready_with_issues` with `issue_count > 0`, `offline` when
availability is unavailable, `metadata.global_active_outside_scope = true`,
non-null `latest_issue` message render, and the
`STATUS_CONTRACT_ERROR_MESSAGE` ("App updated, please reload") contract error
branch. Extended `useLibraryMutations.test.ts` to assert that `scanMutation`
also invalidates `browseRoot` and `browseInfiniteRoot`, matching the
implementation.

### Fix 5: reactive visibility handling for batch status polling

Commit `fix: add reactive visibility handling to batch status polling`.
`useLibraryStatusBatchQuery` now mirrors `useCatalogStatusQuery`: it owns a
reactive `isDocumentHidden` ref, registers `visibilitychange`/`focus`
listeners, sets `enabled: !isDocumentHidden.value` to pause polling while the
tab is hidden, and triggers a 300 ms debounced refetch when the tab becomes
visible again. The previous `document.visibilityState` check inside
`refetchInterval` is now backed by a reactive listener so the query pauses and
resumes immediately instead of relying on the next interval tick.

### Fix 6: shared catalog status polling helpers

Commit `refactor: extract shared catalog status polling helpers`. Added
`frontend/src/lib/catalog/polling.ts` exporting
`isUnifiedStatusActive(status)` (true when `scan.state` is `queued`/`scanning`
or `metadata.state` is `queued`/`indexing`) and
`statusRefetchInterval(status, enabled)` (returns `false` when disabled or no
status, `ACTIVE_POLL_INTERVAL` 2500 ms while active, `STABLE_POLL_INTERVAL`
60000 ms when settled). `useCatalogStatusQuery` and `useLibraryStatusBatchQuery`
now consume these helpers instead of redefining the constants and active
detection. Coverage added in
`frontend/src/lib/catalog/__tests__/polling.test.ts`.

### Fix 7: legacy query keys and invalidation cleanup

Commit `cleanup: remove legacy query keys and invalidation paths`. Removed
the `queryKeys.libraryProgress(id)` and `queryKeys.indexStatus(path)` keys
from `frontend/src/query/keys.ts` (no remaining component consumers). Removed
the dead `useLibraryProgressQuery` and `useIndexStatusQuery` composables plus
the orphaned `fetchLibraryProgress` and `fetchIndexStatus` API client
functions. Removed `libraryProgress` invalidations from `useLibraryMutations`
(`scanMutation`, `updateMutation`, `rebuildMutation`, `unregisterMutation`)
and `useLibraryEvents`. Kept `queryKeys.libraryStats` and its invalidations
with a `cleanup: remove after migration to unified status` TODO because it is
still consumed by `useLibraryStatsQuery` / `LibraryDetailPage` for storage
usage stats. Updated `keys.test.ts` and `useLibraryMutations.test.ts` to drop
the removed-key assertions.
