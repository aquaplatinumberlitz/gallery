# Codex Library Management Implementation Status

Last updated: 2026-06-20  
Current milestone: Phase 1 complete  
Next milestone: Phase 2 — backend jobs, stats, scan-all, and SSE  
SQLite schema version currently implemented: `PRAGMA user_version = 6`

This is the primary handoff document for the library-management work. Start
here before changing code.

Related documents:

- Binding contract:
  [`CODEX_LIBRARY_MANAGEMENT_PHASE_0_CONTRACT.md`](CODEX_LIBRARY_MANAGEMENT_PHASE_0_CONTRACT.md)
- Full product and implementation plan:
  [`CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_PLAN.md`](CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_PLAN.md)
- Repository architecture:
  [`../ARCHITECTURE.md`](../ARCHITECTURE.md)

When documents differ:

1. This status document describes what is implemented now.
2. The Phase 0 contract describes the required final behavior.
3. The implementation plan describes sequencing, UX, and acceptance criteria.

## 1. Executive Summary

The backend can now create, validate, list, read, edit, scan, repair, and
unregister registered libraries with:

- one or more ordered import paths;
- per-library exclusion patterns;
- a compatibility `root_path` alias pointing to the first import path;
- cross-library overlap prevention;
- same-library overlap warnings;
- immediate catalog scope reconciliation when paths/patterns change;
- path lookup, viewer fallback, scanner, folder listing, search cleanup, and
  watcher behavior based on import paths.

Phase 1 is backend-only. The frontend has not been migrated and still uses the
legacy arbitrary `gallery-root-path` state/UI. The final jobs, stats, SSE,
video, admin UI, active-library selector, and mixed-media work do not exist yet.

The most important boundary for the next developer:

```text
Implemented now:
  SQLite v6 + multi-import-path CRUD/validation/exclusions

Not implemented yet:
  SQLite v7 jobs + stats + scan-all + SSE
  SQLite v8 video metadata + streaming/posters
  all new frontend data/UI/state phases
```

## 2. Phase Progress

| Phase | Status | Delivered | Next dependency |
| --- | --- | --- | --- |
| 0. Contract lock | Complete | API, migration, state, jobs/SSE, video, dependency contract | Keep contract tests aligned with changes |
| 1. Schema, validation, CRUD | Complete | SQLite v6, import paths, exclusions, CRUD/validate, multi-root lookup/scan/repair | Phase 2 builds on v6 |
| 2. Jobs, stats, scan-all, SSE | Not started | Nothing from this phase is present | Implement SQLite v7 and job manager |
| 3. Video backend | Not started | No video indexing/streaming/posters | Implement SQLite v8 after Phase 2 |
| 4. Frontend data layer | Not started | No new library types/API/query composables | Requires stable Phase 2/3 backend |
| 5. Admin management UI | Not started | No `/admin/libraries` routes/pages | Requires Phase 4 |
| 6. Active library selection | Not started | Legacy root-path UI/store still active | Requires library query/data layer |
| 7. Mixed-media UI | Not started | Viewer remains image-only | Requires Phase 3 and Phase 4 |
| 8. Final verification | Not started | Phase 1 backend verification only | Run after all feature phases |

Overall plan completion is not “2/9 of functionality.” Phase 0 is a design
gate, and Phase 1 is only the backend foundation. User-visible library
management is still absent.

## 3. Phase 1 Implementation Snapshot

### 3.1 Database migration

Current database baseline before this work was version 5. Initialization now
migrates to version 6.

Added tables:

```sql
library_import_paths (
  id,
  library_id,
  path,
  position,
  created_at,
  updated_at
)

library_exclusion_patterns (
  id,
  library_id,
  pattern,
  position,
  created_at,
  updated_at
)
```

Important constraints:

- `UNIQUE(library_id, path)`
- `UNIQUE(library_id, position)` for import paths
- `UNIQUE(library_id, pattern)`
- `UNIQUE(library_id, position)` for exclusion patterns
- both child tables use `ON DELETE CASCADE`

Migration behavior:

1. Existing `libraries.root_path` is inserted as import-path position `0`.
2. Existing library timestamps stored as SQLite Julian days are converted to
   Unix epoch seconds.
3. Migration verifies that every library has at least one import path.
4. `user_version` becomes `6`.

`libraries.root_path` has not been removed. It is updated transactionally to the
path at position `0` and remains the compatibility alias through V1.

Only library timestamps were normalized in this phase. Other pre-existing
tables may still use their historical timestamp conventions.

### 3.2 Current serialized library shape

`GET /api/libraries` and `GET /api/libraries/{id}` now return:

```ts
interface RegisteredLibrary {
  id: number;
  root_path: string;
  import_paths: Array<{
    id: number;
    library_id: number;
    path: string;
    position: number;
    created_at: number;
    updated_at: number;
  }>;
  exclusion_patterns: string[];
  name: string;
  state: string;
  watch_enabled: 0 | 1;
  warm_enabled: 0 | 1;
  asset_count: number;
  created_at: number;
  updated_at: number;
  last_scan_at: number | null;
  last_error: string | null;
}
```

`asset_count` currently counts active image/video asset rows and excludes
folders, offline rows, and deleted rows. Video rows are supported by the count
expression for forward compatibility, but Phase 3 video discovery does not
exist yet.

### 3.3 API endpoints implemented now

| Method | Endpoint | Current status |
| --- | --- | --- |
| `GET` | `/api/libraries` | Implemented with import paths, exclusions, asset count |
| `POST` | `/api/libraries` | Implemented; accepts `import_paths` or legacy `root_path` |
| `POST` | `/api/libraries/validate` | Implemented; read-only validation |
| `GET` | `/api/libraries/{id}` | Implemented with expanded serialization |
| `PATCH` | `/api/libraries/{id}` | Implemented with replacement semantics |
| `PUT` | `/api/libraries/{id}` | Implemented as PATCH-compatible alias |
| `POST` | `/api/libraries/{id}/validate` | Implemented; excludes current library from overlap checks |
| `GET` | `/api/libraries/{id}/progress` | Existing implementation retained; not yet job-aware |
| `POST` | `/api/libraries/{id}/scan` | Multi-import-path support added; still old BackgroundTasks flow |
| `POST` | `/api/libraries/{id}/repair` | Multi-import-path/exclusion support added; still synchronous |
| `DELETE` | `/api/libraries/{id}?confirm=true` | Existing source-file-safe behavior retained |

The following target endpoints are not implemented:

- `GET /api/libraries/{id}/stats`
- `GET /api/libraries/{id}/jobs`
- `POST /api/libraries/scan-all`
- `GET /api/stats`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `GET /api/events`
- `GET /api/video`
- `GET /api/video/poster`

Static `/api/libraries/validate` is declared before the dynamic numeric library
route. When adding `/api/libraries/scan-all`, keep it before
`/api/libraries/{library_id}` as required by the contract.

### 3.4 Create/update semantics

Create:

- accepts a non-empty `import_paths` list; or
- accepts legacy `root_path` as shorthand for one import path;
- rejects supplying both;
- derives a name from the first path when name is absent/blank;
- stores request order as zero-based `position`.

Update:

- supplied fields replace their current values;
- omitted fields remain unchanged;
- `import_paths: []` is rejected;
- explicit `null` update fields are rejected;
- an empty update body is rejected;
- import-path reorder updates `root_path` to the new first path.

Validation:

- trims whitespace and matching surrounding quotes;
- requires absolute paths;
- canonicalizes through `Path.resolve()`;
- enforces `PATH_SAFETY_ROOT`;
- checks existence, directory type, and readable/scannable access;
- rejects duplicate canonical paths;
- rejects exact/ancestor/descendant overlap with another library;
- allows same-library overlap but returns warnings;
- limits exclusions to 128 unique, non-empty, relative patterns;
- rejects `..` traversal in exclusion patterns;
- compiles patterns through `wcmatch`.

Create/update repeats validation and the storage layer repeats cross-library
overlap checks under the existing database/process lock.

### 3.5 Import-path lookup and fallback

Path-to-library lookup now joins `library_import_paths` and chooses the most
specific containing import root.

No-path viewer fallback now resolves:

```text
lowest library ID
  -> lowest import-path position
  -> lowest import-path ID
```

The viewer APIs remain path-based. No library ID was added to scan, folder,
search, image, thumbnail, preview, or metadata URLs.

### 3.6 Exclusion behavior

`wcmatch>=10.1,<11` is now a backend runtime dependency.

Patterns:

- are relative to each import path;
- use globstar behavior;
- match normalized `/` separators;
- are case-insensitive on Windows;
- are ORed with existing default dependency/cache/build exclusions.

Per-library exclusions are currently applied to:

- direct gallery scan;
- folder child listing and album metadata;
- recursive index-tree discovery;
- asset upsert safety checks;
- library repair;
- direct requests for excluded browse/search folders;
- configuration reconciliation after edit.

Direct requests to an excluded folder through `/api/scan`, `/api/folders`, or
current-scope `/api/search` return `404`.

The legacy `/api/search-metadata` endpoint is still a global metadata-table
search and was not redesigned in Phase 1. The main viewer uses `/api/search`.

### 3.7 Configuration reconciliation

When import paths are removed or exclusions become stricter:

- existing affected asset rows are marked `offline = 1`;
- source files are never deleted;
- derivative files/catalog rows are preserved;
- stale path rows are removed from `file_index`, `file_index_fts`,
  `metadata_index_jobs`, and `folder_index_state`;
- image metadata rows are preserved.

When scope is re-added or exclusions are relaxed:

- existing asset rows are immediately reactivated only when the source still
  exists and remains non-deleted;
- no new files are discovered by the configuration update itself;
- a scan is required to discover new files and rebuild missing legacy
  `file_index`/search rows.

This distinction matters: asset-backed browse state may recover immediately,
while legacy search-index coverage converges after the next scan.

### 3.8 Scan and repair behavior during the Phase 1/2 boundary

Scan currently:

- verifies every import path is an available directory;
- sets library state to `discovering`;
- uses FastAPI `BackgroundTasks`;
- rebuilds each import path sequentially;
- sets state to `ready` or `error`;
- returns the legacy shape:

```json
{ "library_id": 1, "state": "discovering" }
```

It does not return `job_id`, queue work in SQLite, coalesce duplicate requests,
or emit SSE. Phase 2 replaces this lifecycle.

Repair currently:

- is synchronous;
- traverses every import path;
- deduplicates traversal by visited directory inode and asset path;
- applies default and per-library exclusions;
- returns `added`, `removed`, and `modified`;
- records no job row and returns no `job_id`.

`GET /api/libraries/{id}/progress` still returns only:

```text
indexed_assets
estimated_assets
discovery_complete
library_state
```

`active_job_id` is a Phase 2 addition.

## 4. Files Changed and Ownership

### Database and catalog

- `backend/metadata_store.py`
  - migration v6;
  - serialization;
  - import-path lookup;
  - create/update helpers;
  - scope reconciliation;
  - multi-root repair;
  - compatibility fallback.

### HTTP API and validation

- `backend/libraries.py`
  - create/update DTOs;
  - validation response construction;
  - create/edit/validate endpoints;
  - multi-root scan and repair entry points.

### Exclusion propagation

- `backend/files.py`
  - `wcmatch` matching;
  - extended `is_index_excluded_path`.
- `backend/albums.py`
  - exclusion-aware child/cover/count metadata.
- `backend/scan.py`
  - exclusion-aware direct scan and excluded-folder guard.
- `backend/folders.py`
  - exclusion-aware folder tree and excluded-folder guard.
- `backend/search.py`
  - current-scope excluded-folder guard and multi-root stale cleanup.
- `backend/watcher.py`
  - watches all enabled import paths.

### Dependency, tests, and documentation

- `backend/requirements.txt`
  - adds `wcmatch>=10.1,<11`.
- `backend/tests/test_libraries_catalog.py`
  - migration, API, overlap, reorder, offline/reactivation, exclusion, and
    scan/folder/search coverage.
- `docs/ARCHITECTURE.md`
- `docs/THIRD_PARTY_LIBRARIES.md`
- Phase 0 contract, implementation plan, and this status document.

## 5. Verification Evidence

Latest Phase 1 verification:

```text
Backend full suite: 606 passed, 48 warnings
Ruff check: passed
Ruff format check: passed
git diff --check: passed
```

The warnings are existing FastAPI `on_event` deprecation warnings.

Commands used:

```bash
backend/.venv_linux/bin/ruff check backend
backend/.venv_linux/bin/ruff format --check backend

GALLERY_METADATA_DB=/tmp/gallery-phase1-release.db \
  backend/.venv_linux/bin/python -m pytest backend/tests -q

git diff --check
```

Use an isolated `GALLERY_METADATA_DB` for the full backend suite. Some legacy
module-level tests use shared process state; isolation prevents a developer's
real cache/database contents from affecting test cleanup or stale-index scans.

No frontend command was required for Phase 1 because frontend source code was
not changed.

## 6. Current Known Gaps and Temporary Behavior

These are expected incomplete areas, not hidden Phase 1 deliverables:

1. No durable library job table or runner exists.
2. Scan uses FastAPI in-process `BackgroundTasks`, not the final queue.
3. Repair is synchronous and has no job history.
4. No stats endpoints exist.
5. No scan-all endpoint exists.
6. No SSE event stream exists.
7. No startup stale-job recovery exists.
8. No video detection, metadata, stream, or poster support exists.
9. Frontend types/API/query keys/composables for library management do not
   exist.
10. `/admin/libraries` and `/admin/libraries/:id` do not exist.
11. `frontend/src/stores/gallery.ts` still persists `gallery-root-path`.
12. `RootPathSidebarHeader.vue` and `RootPathSheet.vue` still expose arbitrary
    path entry.
13. Mobile/tablet admin availability and registered-library selection are not
    implemented.
14. Existing frontend error mapping does not yet include all new Phase 1/2
    typed errors.

Do not “fix” these piecemeal inside unrelated Phase 2 backend work. Follow the
phase boundaries unless a change is required for the next phase's contract.

## 7. Phase 2 Starting Point

Phase 2 should begin from SQLite `user_version = 6`.

Recommended implementation order:

1. Add migration v7 with `library_jobs` and indexes exactly as locked in the
   Phase 0 contract.
2. Add job serialization and guarded state-transition helpers in
   `metadata_store.py` or a focused library-job repository module.
3. Add startup recovery:
   - `running -> failed`;
   - message/error `Interrupted by server restart`;
   - queued jobs remain queued.
4. Add the single-process job runner and atomic queued-job claim.
5. Convert scan to a durable job:
   - discover/import;
   - reconcile;
   - progress and counters;
   - duplicate active scan coalescing.
6. Record synchronous repair as a durable job before considering async repair.
7. Add per-library and global stats using active/offline image/video asset
   definitions from the contract.
8. Add scan-all parent/child/coalesced tracking.
9. Add jobs list/detail endpoints.
10. Add SSE after SQLite polling endpoints are correct.
11. Extend progress with `active_job_id`.
12. Run full backend regression before marking Phase 2 complete.

### Phase 2 invariants

- `library_jobs` is the source of truth; SSE is best effort.
- Do not introduce Redis, BullMQ, Celery, Socket.IO, or multi-user ownership.
- Keep viewer APIs path-based.
- Keep `libraries.root_path` synchronized as a compatibility alias.
- Do not start Phase 3 video columns in the v7 migration.
- Declare `/api/libraries/scan-all` before `/{library_id}` routes.
- Existing Phase 1 create/update/validate behavior must remain backward
  compatible.

### Minimum Phase 2 tests

- v6 to v7 migration and idempotent reopen;
- job create/read/list and JSON counters;
- allowed/forbidden state transitions;
- startup recovery;
- scan coalescing;
- scan success/failure counters;
- repair job recording;
- per-library/global stats;
- scan-all parent/child and coalesced child behavior;
- jobs endpoint bounds/order;
- progress `active_job_id`;
- SSE frame payload and heartbeat;
- polling recovery when no SSE event is received;
- full existing backend suite.

## 8. Definition of “Current Progress”

The project should currently be described as:

> Backend library registration has been migrated to ordered multi-import-path
> libraries with exclusion patterns and editable CRUD. The database is at v6
> and Phase 1 is verified. Durable jobs, stats, scan-all, SSE, video, and all
> frontend library-management work remain to be implemented, starting with
> Phase 2.

Do not describe the full Library Management feature as complete or
frontend-ready.

