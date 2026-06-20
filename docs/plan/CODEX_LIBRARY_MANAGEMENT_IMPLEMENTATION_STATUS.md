# Codex Library Management Implementation Status

Last updated: 2026-06-20  
Current milestone: Phase 3 complete  
Next milestone: Phase 4 — frontend data layer  
SQLite schema version currently implemented: `PRAGMA user_version = 8`

## Verified Git Baseline

Phase 0/1 implementation commit:

```text
e0fb89ef4479ea026848ce90b71f1eebff3c598c
feat: implement library management phase 1
```

Future developers should compare their working branch against this commit before
using the implementation details or verification counts in this document:

```bash
git merge-base --is-ancestor e0fb89ef4479ea026848ce90b71f1eebff3c598c HEAD
git diff --stat e0fb89ef4479ea026848ce90b71f1eebff3c598c..HEAD
```

The commit containing this status annotation is documentation-only and comes
immediately after the implementation baseline.

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

Phase 1-3 are backend-only. The frontend has not been migrated and still uses the
legacy arbitrary `gallery-root-path` state/UI. The admin UI,
active-library selector, and mixed-media work do not exist yet.

The most important boundary for the next developer:

```text
Implemented now:
  SQLite v6 + multi-import-path CRUD/validation/exclusions
  SQLite v7 + library_jobs + stats + scan-all + SSE
  SQLite v8 + video metadata + streaming/posters

Not implemented yet:
  all new frontend data/UI/state phases
```

## 2. Phase Progress

| Phase | Status | Delivered | Next dependency |
| --- | --- | --- | --- |
| 0. Contract lock | Complete | API, migration, state, jobs/SSE, video, dependency contract | Keep contract tests aligned with changes |
| 1. Schema, validation, CRUD | Complete | SQLite v6, import paths, exclusions, CRUD/validate, multi-root lookup/scan/repair | Phase 2 builds on v6 |
| 2. Jobs, stats, scan-all, SSE | Complete | library_jobs table, job tracking, scan-all, per-library/global stats, jobs endpoints, SSE events | Phase 3 builds on v7 |
| 3. Video backend | Complete | v8 migration, ffprobe indexing, /api/video streaming, /api/video/poster | Phase 4 builds on v8 |
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
| `GET` | `/api/libraries/{id}/progress` | Implemented; returns `active_job_id` |
| `POST` | `/api/libraries/{id}/scan` | Implemented; job-tracked lifecycle |
| `POST` | `/api/libraries/{id}/repair` | Implemented; job-recorded synchronous operation |
| `DELETE` | `/api/libraries/{id}?confirm=true` | Existing source-file-safe behavior retained |
| `GET` | `/api/libraries/{id}/stats` | Implemented with per-library counts |
| `GET` | `/api/libraries/{id}/jobs` | Implemented |
| `POST` | `/api/libraries/scan-all` | Implemented; parent/child job flow |
| `GET` | `/api/stats` | Implemented with global gallery counts |
| `GET` | `/api/jobs` | Implemented |
| `GET` | `/api/jobs/{id}` | Implemented |
| `GET` | `/api/events` | Implemented; SSE stream with keep-alive |
| `GET` | `/api/video` | Implemented; HTTP Range streaming |
| `GET` | `/api/video/poster` | Implemented; ffmpeg WebP caching |

All target endpoints from Phase 2 and Phase 3 are now implemented.

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

### 3.8 Scan and repair behavior

Scan currently:
- verifies every import path is an available directory;
- queues a `library_jobs` row and returns a `job_id` (202 Accepted);
- uses FastAPI `BackgroundTasks` for the async scan runner;
- rebuilds each import path sequentially;
- updates job progress counters per import path;
- sets job state to `succeeded` or `failed`;
- emits SSE events on job transitions.

The job system uses a single-process in-memory runner (`BackgroundTasks`)
with SQLite-tracked state. There is a known non-atomic window between
`list_active_jobs` and `create_job` that can allow duplicate scan jobs under
concurrent requests. This is acceptable for V1; a follow-up could introduce
`create_or_get_active_scan_job` under a single `_DB_LOCK` critical section.

Repair currently:
- is a job-recorded synchronous operation;
- creates a job row, runs `repair_library_assets`, then sets succeeded/failed;
- returns the result in the same HTTP response (no polling needed);
- returns a `job_id` for audit-trail reference.

`GET /api/libraries/{id}/progress` returns:
- `active_job_id` — the current queued/running job id, or null
- `indexed_assets`, `estimated_assets`, `discovery_complete`, `library_state`

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

1. Frontend types/API/query keys/composables for library management do not
   exist.
2. `/admin/libraries` and `/admin/libraries/:id` do not exist.
3. `frontend/src/stores/gallery.ts` still persists `gallery-root-path`.
4. `RootPathSidebarHeader.vue` and `RootPathSheet.vue` still expose arbitrary
    path entry.
5. Mobile/tablet admin availability and registered-library selection are not
    implemented.
6. Existing frontend error mapping does not yet include all new Phase 1/2/3
    typed errors.

Do not “fix” these piecemeal outside their planned phases. Follow the
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

### Minimum Phase 3 tests

- v7 to v8 migration and idempotent reopen;
- video indexing with `type = 'video'`, ffprobe metadata (duration, codec, dimensions);
- `/api/video` full response (200);
- `/api/video` byte range (206 + Content-Range);
- `/api/video` unsatisfiable range (416);
- `/api/video` rejection of non-video file (400);
- `/api/video/poster` ffmpeg generation (200 + WebP);
- `/api/video/poster` missing ffmpeg fallback (503);
- video asset counting in per-library stats (photos vs videos);
- full existing backend suite.

## 8. Definition of “Current Progress”

The project should currently be described as:

> Backend library registration has been migrated to ordered multi-import-path
> libraries with exclusion patterns and editable CRUD. Durable jobs, stats,
> scan-all, and SSE are implemented. Video assets are indexed with ffprobe
> metadata, streamed via HTTP Range, and served with cached ffmpeg posters.
> The database is at v8 and Phases 0-3 are verified. All frontend
> library-management work remains to be implemented starting with Phase 4.

Do not describe the full Library Management feature as complete or
frontend-ready.
