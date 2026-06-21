# Catalog Scan Pipeline and Unified Status Plan

Status: Proposed — awaiting approval; no implementation is authorized yet

Created: 2026-06-21

Last revised: 2026-06-21

## 1. Objective

Refactor gallery-repo into a registered-library, database-first architecture:

- one Catalog Scan Service is the only writer of the asset catalog;
- initial scan, filesystem watcher, scheduled reconciliation, startup catch-up,
  manual scan, and rebuild all invoke that service;
- filesystem discovery and metadata extraction remain separate pipeline stages;
- admin library status and sidebar folder status use one semantic contract;
- gallery browsing reads the catalog and never mutates it;
- legacy ad-hoc root-path and direct filesystem browse behavior is removed.

This adopts the useful external-library pattern documented in
[`IMMICH_PIPELINE_AUDIT.md`](../research/IMMICH_PIPELINE_AUDIT.md) without
copying Immich's BullMQ/Redis deployment model. gallery-repo keeps a bounded
in-process worker backed by durable SQLite job rows.

## 2. Locked architecture decisions

1. Registered libraries are the only supported source of gallery assets.
2. A library may contain multiple import paths. There is no public
   `root_path` compatibility field or unregistered-path mode.
3. Creating a library always queues an initial catalog scan. The UI no longer
   offers “Add without scan”.
4. Filesystem watcher and scheduled reconciliation are enabled by default.
   The watcher provides low latency; scheduled reconciliation repairs missed
   events and downtime gaps.
5. Startup asynchronously queues a low-priority catch-up scan for every
   registered library. Startup never blocks on scanning or metadata.
6. Manual full or scoped scan uses `POST /api/libraries/{id}/scan`.
   `/api/index/rescan` will not be introduced.
7. Rebuild remains a distinct destructive operation and uses
   `POST /api/libraries/{id}/rebuild`.
8. The standalone Repair workflow and endpoint are removed. Normal catalog
   scan performs discovery and reconciliation in one canonical operation.
9. `GET /api/scan` is replaced by read-only `GET /api/browse`. There is no
   compatibility alias and no filesystem fallback.
10. `GALLERY_DB_REQUIRED` and its conditional behavior are removed; DB-first
    behavior is unconditional.
11. Scan completion does not wait for metadata extraction. Discovered assets
    become browseable from catalog rows while metadata continues in the
    background.
12. Backend and frontend ship atomically because API and status schemas are
    intentionally breaking.

## 3. Target system boundaries

### 3.1 Catalog Scan Service

The Catalog Scan Service owns filesystem-to-catalog synchronization. No router,
watcher, scheduler, or metadata worker may independently upsert, reconcile, or
delete catalog rows.

One scan run performs these stages:

1. Resolve the library and canonical scope.
2. Validate that the requested scope belongs to one configured import path.
3. Mark the durable job `running` and publish a status invalidation event.
4. Enumerate supported files and directories without decoding media.
5. Upsert `file_index` and `assets` rows from path/stat data.
6. Mark discovered rows with the current scan generation/job ID.
7. After successful enumeration, reconcile rows not seen in that generation:
   mark missing assets offline and remove obsolete folder-listing rows.
8. Queue metadata jobs only for new or changed supported assets, coalesced by
   canonical path, mtime, and size.
9. Persist counters and complete the catalog job.
10. Let the metadata worker update per-asset metadata state independently.

If enumeration fails, reconciliation is not run. Previously valid catalog rows
remain available and the failed scan is exposed as an issue.

### 3.2 Metadata Indexer

The metadata indexer remains a separate bounded worker:

- input is a durable job created by the Catalog Scan Service;
- identity is canonical path + mtime + size;
- unchanged current metadata is not re-read;
- stale or changed files transition back to pending;
- success writes current metadata and marks the asset ready;
- failure is attached to the current file version and contributes an issue;
- metadata activity never changes `last_scan_at`.

Direct `/api/metadata` reads may return cached metadata or request an existing
metadata job, but may not create or reconcile asset catalog rows.

### 3.3 Read-only Browse Service

`GET /api/browse` only queries catalog rows. It may paginate, sort, filter, and
batch-read cached dimensions, but it must not:

- call `os.scandir` or walk the filesystem;
- upsert `assets`, `file_index`, or metadata rows;
- enqueue catalog or metadata work;
- silently accept paths outside registered import paths.

Required query fields:

```text
GET /api/browse?library_id={id}&path={canonical-absolute-path}&cursor=...&limit=...
```

The requested path must be inside an import path owned by `library_id`.
Initial scans may legitimately return an empty or partially populated page;
the status contract tells the UI whether discovery is still running.

## 4. Trigger flows

Every trigger creates or coalesces a durable catalog job and then uses the same
service. `trigger` records why the work exists; it does not select a different
scan implementation.

| Trigger | Scope | Default priority | Behavior |
| --- | --- | ---: | --- |
| `initial` | whole library | 100 | Automatically queued in the library-create transaction |
| `manual` | whole library or validated folder | 100 | User-requested refresh; returns HTTP 202 |
| `rebuild` | whole library or validated folder | 100 | Explicit destructive regeneration |
| `watcher` | smallest safe changed scope | 50 | Debounced and merged by library/common ancestor |
| `startup` | whole library | 10 | Async catch-up after stale-job recovery |
| `scheduled` | whole library | 10 | Periodic authoritative reconciliation |

### 4.1 New library / cold start

1. Create the library and its import paths.
2. In the same transaction, create one queued `initial` catalog job.
3. Return the library plus `initial_scan_job_id`; do not wait for scanning.
4. Admin shows `Scanning`; browse may show discovered rows progressively.
5. Catalog completion changes the semantic phase to `Indexing` while metadata
   remains active, then to `Ready` or `Ready with issues`.

This removes the need for a blocking pre-scan while ensuring a new library can
never remain permanently uninitialized by accident.

### 4.2 New, changed, moved, or deleted files

- Watcher add/change events request a scan of the containing directory.
- Watcher delete events request reconciliation of the nearest existing parent.
- Move events reconcile both source and destination scopes; overlapping scopes
  are merged.
- Directory-level bursts are debounced per library and collapsed to their
  nearest common ancestor, never outside an import path.
- A scheduled whole-library scan eventually corrects dropped watcher events,
  watcher downtime, network-mount behavior, and unsupported filesystem events.

The watcher observes all current import paths. Library create/update/delete
must refresh watcher registrations dynamically; an application restart is not
required.

### 4.3 Startup recovery

Startup order:

1. initialize/migrate SQLite;
2. mark interrupted running jobs failed with a restart-specific reason;
3. start the catalog and metadata workers;
4. synchronize watcher roots with registered import paths;
5. start the scheduled reconciler;
6. enqueue/coalesce one low-priority `startup` scan per library;
7. begin serving requests without waiting for those jobs.

### 4.4 Scheduled reconciliation defaults

- Enabled by default.
- Default interval: 6 hours (`21600` seconds), configurable.
- Add deterministic jitter so multiple instances do not all begin together.
- Skip/coalesce a library already covered by a queued or running scan.
- A schedule tick never executes filesystem work in the scheduler thread.

## 5. Durable jobs, concurrency, and idempotency

Increase SQLite `user_version` from 7 to 8.

### 5.1 Schema changes

Add to `library_jobs`:

- `scope_path TEXT NULL`: null means the whole library;
- `trigger TEXT NOT NULL DEFAULT 'manual'`;
- `priority INTEGER NOT NULL DEFAULT 50`;
- `scan_generation INTEGER NULL`;
- counters for discovered, created, updated, offline, and metadata-queued assets
  if equivalent existing counters cannot represent them clearly.

Add `last_seen_scan_job_id INTEGER NULL` to catalog rows that participate in
reconciliation. Add indexes for:

- `(library_id, type, state, scope_path)`;
- `(state, priority, created_at)`;
- catalog reconciliation by library, scope, and last-seen job.

Remove public and application dependencies on `libraries.root_path`. The v8
migration rebuilds the SQLite `libraries` table without that column after
copying canonical values into `library_import_paths`. Migration runs in one
transaction; `user_version` advances only after all checks pass.

### 5.2 Job types and states

Catalog operations:

- `scan`: non-destructive discovery and reconciliation;
- `rebuild`: regenerate catalog and metadata state for the requested scope.

States:

- `queued`, `running`, `succeeded`, `failed`, `cancelled`.

`trigger` is orthogonal to operation. For example, an initial library job is
`type=scan, trigger=initial`.

### 5.3 Writer rules

- At most one catalog writer runs per library.
- Different libraries may run concurrently up to configured worker limits.
- The metadata worker may run while catalog scanning, using versioned file
  identity to reject stale results.
- Active or queued work whose scope covers a new scan request is reused and its
  job ID returned.
- A broader queued scan supersedes/cancels narrower queued scans for the same
  library.
- A broader request arriving while a narrower scan is running is queued after
  it; the running job is not interrupted.
- Watcher/startup/scheduled requests always coalesce or defer; they never
  surface user-facing conflicts.
- Rebuild is never silently merged with scan. A manual rebuild that conflicts
  with active catalog work returns HTTP 409 `library_busy`.

Job selection is priority-descending and FIFO within a priority. Starvation is
prevented by aging low-priority jobs.

### 5.4 Crash consistency

- Job creation and wake-up use recoverable-outbox semantics: queued DB rows are
  the source of truth, so a process crash before worker notification loses no
  work.
- A scan only reconciles missing rows after enumeration succeeds.
- Rebuild first marks the target generation stale/rebuilding, writes the new
  generation, and prunes old rows only after success.
- Failed rebuild preserves the previous usable generation, marks status as an
  issue, and can be retried idempotently.
- Worker results update a row only if path, mtime, and size still match.

## 6. API contract changes

### 6.1 Library commands

```text
POST /api/libraries
POST /api/libraries/{id}/scan
POST /api/libraries/{id}/rebuild
```

Scan request:

```json
{
  "scope_path": "/photos/2026"
}
```

`scope_path` is optional; omitted means all import paths in the library. The
server sets `trigger=manual`; clients cannot forge trigger or priority.

Accepted response (HTTP 202):

```json
{
  "job_id": 123,
  "library_id": 7,
  "scope_path": "/photos/2026",
  "operation": "scan",
  "trigger": "manual",
  "state": "queued",
  "coalesced": false
}
```

Rebuild requires `confirm=true` in the request body. Invalid/out-of-library
scope returns 400/404; an explicit conflicting rebuild returns:

```json
{
  "error": "library_busy",
  "active_job_id": 122,
  "operation": "scan",
  "scope_path": null,
  "message": "Catalog work is already active for this library."
}
```

### 6.2 Status endpoints

Use one builder and one response schema:

```text
GET /api/libraries/{id}/status
GET /api/libraries/{id}/status?scope_path={path}
GET /api/libraries/status
```

The batch endpoint returns library-wide summaries for the admin table and
avoids N+1 requests. The scoped endpoint powers the sidebar. Remove legacy
`/api/libraries/{id}/progress` and `/api/index/status` after frontend migration
in the same release.

### 6.3 Removed endpoints and behavior

- remove `GET /api/scan`;
- remove `POST /api/libraries/{id}/repair`;
- remove legacy `/api/index/rebuild` and do not add `/api/index/rescan`;
- remove direct-scan fallback and safe-unregistered-path behavior;
- remove `GALLERY_DB_REQUIRED` configuration;
- reject browse, scan, rebuild, and status scopes outside registered libraries.

## 7. Unified status contract

Filesystem scan and metadata extraction remain different states but share one
contract and one precedence function.

```ts
type SummaryState =
  | "unknown"
  | "offline"
  | "needs_scan"
  | "scanning"
  | "indexing"
  | "needs_update"
  | "ready_with_issues"
  | "ready"
  | "error";

type AvailabilityState = "unknown" | "available" | "degraded" | "unavailable";
type ScanState = "never" | "queued" | "scanning" | "complete" | "failed";
type MetadataState =
  | "disabled"
  | "queued"
  | "indexing"
  | "needs_update"
  | "complete"
  | "failed";

interface UnifiedStatusResponse {
  contract_version: 1;
  generated_at: number; // Unix epoch milliseconds UTC
  summary_state: SummaryState;

  scope: {
    kind: "library" | "path";
    library_id: number;
    path: string | null;
    include_subfolders: true;
    import_path_count: number;
  };

  availability: {
    state: AvailabilityState;
    available_paths: number;
    total_paths: number;
  };

  scan: {
    state: ScanState;
    operation: "scan" | "rebuild" | null;
    trigger: "initial" | "manual" | "watcher" | "scheduled" | "startup" | "rebuild" | null;
    active_job_id: number | null;
    completed_units: number | null;
    total_units: number | null;
    progress_percent: number | null;
  };

  metadata: {
    state: MetadataState;
    total_assets: number | null;
    ready_assets: number | null;
    not_ready_assets: number | null;
    queued_assets: number | null;
    running_assets: number | null;
    stale_assets: number | null;
    idle_pending_assets: number | null;
    failed_assets: number | null;
    progress_percent: number | null;
    global_active_outside_scope: boolean;
  };

  issue_count: number;
  issues: {
    availability: number;
    scan: number;
    metadata: number;
  };

  latest_issue: {
    source: "availability" | "scan" | "metadata";
    path: string | null;
    message: string;
    updated_at: number;
  } | null;

  last_scan_at: number | null;
  last_index_at: number | null;

  runtime: {
    catalog_active_jobs: number;
    catalog_queue_depth: number;
    metadata_worker_count: number;
    metadata_active_jobs: number;
    metadata_queue_depth: number;
    metadata_staged_queue_depth: number;
  };
}
```

### 7.1 Scope rules

- Library status aggregates all configured import paths.
- Path status includes that folder and descendants only.
- Containment is path-component based, never raw string prefix matching.
- Normalize trailing separators, `.`/`..`, Unicode NFC, separators, and drive
  letter case where applicable. Do not resolve symlinks: configured import-path
  identity remains stable even when a target is offline.
- `total_assets` counts active supported image and video assets in scope.
- Current metadata requires matching path, mtime, and size.

### 7.2 Progress and issues

- `not_ready_assets = total_assets - ready_assets - failed_assets`.
- `queued + running + stale + idle_pending = not_ready_assets`.
- UI never adds `not_ready_assets` to its breakdown fields.
- Metadata progress is `ready_assets / total_assets`.
- A successfully scanned empty scope is 100%; a never-scanned scope is null.
- `issue_count` includes unavailable import paths, the latest unresolved
  covering scan failure, and current-version metadata failures.
- Pending/stale work changes state but is not an issue.
- With metadata disabled, all metadata counts/progress are null and a completed
  scan can reach Ready. UI shows `File scan ready, metadata disabled`.

### 7.3 Summary precedence

Derive centrally in this order:

1. unresolved library/scope: `unknown`;
2. entire scope unavailable: `offline`;
3. covering scan/rebuild queued or running: `scanning`;
4. metadata queued or running: `indexing`;
5. never successfully scanned: `needs_scan`, unless its first scan failed and
   no usable catalog exists, then `error`;
6. current pending/stale metadata without active work: `needs_update`;
7. no usable metadata and all current assets failed: `error`;
8. usable catalog plus scan/metadata failures, or degraded availability:
   `ready_with_issues`;
9. completed scan and settled metadata without issues: `ready`.

An active retry outranks a historical failure, so status changes from Error to
Scanning immediately after retry is accepted.

### 7.4 Timestamps

- All public timestamps are Unix epoch milliseconds UTC.
- `last_scan_at` is the completion time of the latest successful scan/rebuild
  covering the whole requested scope.
- A child scan does not update its parent's `last_scan_at`.
- `last_index_at` is the latest successful current metadata write in scope.
- Metadata-only work never changes `last_scan_at`.
- `latest_issue` uses greatest `updated_at`; ties resolve scan, availability,
  then metadata.

## 8. Events and frontend data ownership

Every catalog job transition publishes a status invalidation event:

```ts
interface CatalogStatusInvalidationEvent {
  contract_version: 1;
  event: "job_queued" | "job_running" | "job_succeeded" | "job_failed";
  job_id: number;
  library_id: number;
  scope_path: string | null;
  operation: "scan" | "rebuild";
  trigger: "initial" | "manual" | "watcher" | "scheduled" | "startup" | "rebuild";
  updated_at: number;
}
```

Frontend rules:

- TanStack Query owns browse and status server state.
- Status keys are `['status', 'library', id]` and
  `['status', 'path', id, normalizedPath]`.
- Browse keys include library ID, normalized path, sort/filter, and cursor.
- Poll status every 2.5 seconds while active and every 60 seconds when stable.
- SSE invalidates the affected library and overlapping path status plus browse
  queries after catalog changes.
- Mutation success immediately seeds/invalidates status using the returned job.
- Unknown `contract_version` or missing required fields shows
  `App updated, please reload` instead of rendering partial status.
- No component derives semantics from `RegisteredLibrary.state`, old
  `LibraryProgress`, old `IndexStatusResponse`, or raw worker counters.

Shared labels:

| State | Label |
| --- | --- |
| `needs_scan` | Needs scan |
| `scanning` | Scanning |
| `indexing` | Updating |
| `needs_update` | Needs update |
| `ready` | Ready |
| `ready_with_issues` | Ready with issues |
| `offline` | Offline |
| `error` | Error |
| `unknown` | Unknown |

Admin uses batch library status. Sidebar uses scoped status for the selected
folder. Both use the same label/color/precedence utility while showing different
counts because their scopes differ. Both display Availability, File scan,
Metadata, issue count, Last scan, and Last index separately.

## 9. Configuration changes

Introduce/standardize:

```text
GALLERY_CATALOG_WORKERS=1
GALLERY_CATALOG_WATCHER_ENABLED=true
GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS=2
GALLERY_CATALOG_RECONCILE_ENABLED=true
GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS=21600
GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=true
```

Production dependencies must include the supported watcher package. If watcher
initialization fails, startup continues with scheduled reconciliation active,
status/logging exposes the degradation, and no direct alternate catalog writer
is used.

Remove `GALLERY_DB_REQUIRED` and superseded refresh/index watcher names after
configuration migration documentation is updated.

## 10. Implementation sequence

Each phase must leave tests passing; the API hard cut occurs atomically in the
final integration phase.

1. Add contract fixtures and state-precedence tests before production changes.
2. Add migration v8, path helpers, job fields/indexes, and migration tests.
3. Implement the durable Catalog Scan Service and one-library writer lock.
4. Route initial, manual, watcher, startup, and scheduled triggers through it.
5. Implement rebuild generations and remove independent repair logic.
6. Implement the shared status builder, scoped endpoint, and admin batch
   endpoint.
7. Add read-only `/api/browse`; migrate gallery queries from `/api/scan`.
8. Migrate admin/sidebar actions, composables, labels, polling, and SSE
   invalidation.
9. Remove old routes, fallback branches, config, types, and dead code.
10. Update architecture/API/config documentation and run release gates.
11. After implementation is accepted, mark this plan Complete and move it to
    `docs/archived/`.

## 11. Verification and acceptance criteria

### 11.1 Backend contract

- Library and path endpoints return the same `contract_version=1` schema.
- Batch status is computed without per-library/per-asset N+1 queries.
- Similar path prefixes never leak sibling data.
- Multi-import libraries aggregate available/degraded/unavailable correctly.
- Current metadata checks path + mtime + size.
- Scan and index timestamps obey separate covering-scope rules.
- Warm status aggregation meets 50 ms p95 on the deterministic fixture.

### 11.2 Pipeline behavior

- Creating a library atomically creates an initial scan job.
- The API and app startup do not block on catalog or metadata completion.
- Assets become browseable after catalog discovery, before metadata completes.
- Watcher events and scheduled scans invoke the same service and produce the
  same catalog result as manual scan.
- Watcher roots update after library/import-path CRUD without restart.
- Dropped watcher events are repaired by scheduled reconciliation.
- Duplicate/overlapping triggers coalesce according to §5.3.
- Restart recovers queued jobs and fails interrupted running jobs visibly.
- Failed enumeration does not mark unseen assets offline.
- Rebuild failure preserves the previous usable catalog generation.
- New/changed assets queue metadata once; unchanged assets do not.
- Removed assets become offline only after a successful covering scan.

### 11.3 API hard-cut checks

- `/api/browse` performs no filesystem calls and no writes.
- `/api/scan`, library repair, `/api/index/rebuild`, and `/api/index/status`
  return 404 after migration.
- Unregistered and cross-library scopes are rejected.
- No runtime/API/frontend source references `root_path` or
  `GALLERY_DB_REQUIRED`; only the v8 migration and its fixture may mention the
  removed schema/config names.
- Rescan is only `POST /api/libraries/{id}/scan`.

### 11.4 Frontend behavior

- Admin and sidebar render identical semantics for the same status fixture.
- Their counts differ correctly between whole-library and folder scope.
- Add Library has one submit path and immediately shows Scanning.
- Opening a newly created library handles empty/partial catalog pages cleanly.
- New files appear after watcher catalog completion without reopening folder.
- Scan action is a POST mutation and never invokes browse as a side effect.
- Repair UI is removed; rebuild remains explicitly confirmed.
- Last scan and Last index are separately labeled.
- No UI reports Ready while current work is pending, stale, queued, or running.

### 11.5 Release gates

- migration upgrade test from a real v7 fixture;
- focused catalog worker, coalescing, watcher, scheduler, browse, status, and
  library API tests;
- frontend unit tests for contract guard, query keys, polling, invalidation,
  and shared status presentation;
- Playwright flows for create library, initial scan, manual scoped scan,
  new-file watcher update, scheduled reconciliation, offline path, and rebuild
  failure;
- `./test.sh fast` and the repository's full release suite;
- atomic frontend/backend deployment with a documented breaking-change note.

## 12. Explicit non-goals

- Do not merge filesystem scan and metadata extraction into one synchronous
  workflow.
- Do not add Redis/BullMQ or a distributed queue in this refactor.
- Do not parse metadata or probe image dimensions during filesystem discovery.
- Do not add a second catalog writer as fallback when watcher or scheduler
  fails.
- Do not preserve legacy ad-hoc path browsing or compatibility aliases.
- Do not implement filesystem write/import/upload semantics; this plan covers
  discovery of externally managed library paths.

## 13. Decisions superseded by this revision

This master plan intentionally replaces the earlier status-only proposal:

- `/api/index/rescan` is replaced by library-scoped
  `POST /api/libraries/{id}/scan`;
- optional unregistered paths and `GALLERY_DB_REQUIRED=false` fallback are
  removed;
- Repair is folded into canonical scan reconciliation and removed as a public
  workflow;
- library creation always queues initial scan;
- watcher, startup catch-up, schedule, and manual commands no longer contain
  separate catalog-update implementations;
- `/api/index/status` and library progress responses are replaced by one
  library/scoped status family;
- the plan now covers pipeline ownership, persistence, API hard cut, and UI
  semantics together so they cannot be implemented inconsistently.

## 14. Approval gate

No production code, migration, API, frontend, or configuration change described
by this plan may be implemented until the user explicitly approves this revised
document. Documentation-only review edits remain allowed before approval.
