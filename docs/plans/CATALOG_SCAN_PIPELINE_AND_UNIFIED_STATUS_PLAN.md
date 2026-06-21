# Catalog Scan Pipeline and Unified Status Plan

Status: Active — audit revision 2 approved; Phase 1 complete; Phase 2 next

Created: 2026-06-21

Last revised: 2026-06-21

Implementation status:
[`CATALOG_SCAN_PIPELINE_AND_UNIFIED_STATUS_IMPLEMENTATION_STATUS.md`](CATALOG_SCAN_PIPELINE_AND_UNIFIED_STATUS_IMPLEMENTATION_STATUS.md)

Phase 1 completion note, 2026-06-21:

- Implemented the required shared contract fixtures, schema fixture,
  backend/frontend status contract types, shared precedence implementations, and
  backend/frontend tests for the contract-v1 summary precedence rules.
- Latest pushed Phase 1 implementation/format commit before this plan update:
  `38563d4 style: format catalog status phase 1`.
- Verification run: `./test.sh fast` passed on 2026-06-21 with 648 backend
  tests, backend coverage 86.25%, 396 frontend unit tests, frontend typecheck,
  and production build passing. Existing FastAPI lifecycle, Sass import,
  Rollup annotation, eval, and chunk-size warnings remain non-blocking.
- No Phase 2 migration, job schema, catalog pipeline, API hard-cut, browse, or
  frontend data-ownership behavior is implemented by Phase 1.

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
13. A library with multiple import paths has a virtual browse root. A null
    browse path lists its configured import paths; it does not represent a real
    filesystem directory.
14. Import paths must be pairwise disjoint, both inside one library and across
    libraries. Duplicate, ancestor, descendant, and online resolved-symlink
    aliases are rejected at create/update time.
15. Normal browsing and metadata totals include online active assets only.
    Missing-file tombstones are retained but hidden by default and do not count
    as issues.

## 3. Target system boundaries

### 3.1 Catalog Scan Service

The Catalog Scan Service owns filesystem discovery and reconciliation. No
router, watcher, scheduler, or metadata worker may independently create/delete
asset identity, change filesystem-version fields, mark assets online/offline,
or mutate folder membership.

Writer ownership is field-level, not an inaccurate whole-table lock:

| Data | Authorized writer |
| --- | --- |
| `assets.library_id/path/parent_path/name/type/mtime_ns/size/offline/deleted_at/last_seen_scan_job_id` | Catalog Scan Service only |
| `assets.metadata_state/width/height/duration_ms/mime_type/codec` | Metadata Indexer after current-version guard |
| `file_index` identity/folder-membership fields | Catalog Scan Service only |
| `file_index.width/height` cached projection | Metadata Indexer after current-version guard |
| `image_metadata`, metadata-resource rows, metadata jobs | Metadata Indexer only; catalog service may request/coalesce jobs through its queue API |
| Catalog job creation/coalescing/recovery | Catalog Job Coordinator |
| Catalog job running/progress/terminal transitions | Catalog worker |

Routers and library creation call the Catalog Job Coordinator; they do not
write job rows directly. Startup recovery is also a coordinator operation.
This control-plane boundary allows atomic library + initial-job creation while
keeping execution ownership inside the catalog subsystem.

One scan run performs these stages:

1. Resolve the library and canonical scope.
2. Validate that the requested scope belongs to one configured import path.
3. Mark the durable job `running` and publish a status invalidation event.
4. Enumerate supported files and directories without decoding media.
5. Upsert `file_index` and `assets` rows from path/stat data in bounded batches,
   without holding a database transaction during filesystem enumeration.
6. Mark discovered rows with the current scan job ID.
7. After successful enumeration, reconcile rows not seen in that generation:
   mark missing assets offline and remove obsolete folder-listing rows.
8. Queue metadata jobs only for new or changed supported assets, coalesced by
   canonical path, integer `mtime_ns`, and size.
9. Persist counters and complete the catalog job.
10. Let the metadata worker update per-asset metadata state independently.

If enumeration fails, reconciliation is not run. Previously valid catalog rows
remain available, partial newly discovered rows may remain usable, and the
failed scan is exposed as an issue.

Rebuild uses a stricter path: enumeration writes to a job-scoped staging table.
Browse continues serving the canonical generation while rebuild runs. After
successful enumeration, one short activation transaction merges the staged
generation, reconciles missing rows, resets affected metadata state, and
removes staging data. A crash or failure leaves the canonical generation
untouched; abandoned staging rows are safe to retry or clean up.

### 3.2 Metadata Indexer

The metadata indexer remains a separate bounded worker:

- input is a durable job created by the Catalog Scan Service;
- identity is canonical path + integer `mtime_ns` + size;
- unchanged current metadata is not re-read;
- stale or changed files transition back to pending;
- success writes current metadata and marks the asset ready;
- failure is attached to the current file version and contributes an issue;
- metadata activity never changes `last_scan_at`.

Every durable metadata job stores the filesystem version observed when queued.
The worker stats the file before and after extraction, then performs a
conditional write that also checks the current `assets.mtime_ns` and
`assets.size`. Any mismatch marks/supersedes the job as stale and discards its
result. A newer job for the same path replaces obsolete queued work. Content
hashes and inode/device identity are explicitly outside v1; equal
`mtime_ns + size` collisions are an accepted limitation.

Direct `/api/metadata` reads may return cached metadata or request an existing
metadata job, but may not create or reconcile asset catalog rows.

### 3.3 Read-only Browse Service

`GET /api/browse` only queries catalog rows. It may paginate, sort, filter, and
batch-read cached dimensions, but it must not:

- call `os.scandir` or walk the filesystem;
- upsert `assets`, `file_index`, or metadata rows;
- enqueue catalog or metadata work;
- silently accept paths outside registered import paths.

Request shape:

```text
GET /api/browse?library_id={id}&path={canonical-absolute-path-or-null}&cursor=...&limit=...
```

When `path` is omitted/null, the response is a virtual library root containing
one synthetic `import_root` folder entry per configured import path, ordered by
its configured position. Each entry includes path, display label, and
availability. Duplicate leaf names are disambiguated with their full path.
Breadcrumbs render `Library name` at the virtual root, then the selected import
root and real descendants. Status at the virtual root is library-wide; after an
import root is selected it is path-scoped.

A non-null requested path must be inside an import path owned by `library_id`.
Normal browse excludes offline tombstones. `include_offline=true` is reserved
for an admin/diagnostic view; unavailable import roots remain visible at the
virtual root. Initial scans may legitimately return an empty or partially
populated real folder page; status tells the UI whether discovery is running.

## 4. Trigger flows

Every trigger creates or coalesces a durable catalog job and then uses the same
service. `trigger` records why the work exists; it does not select a different
scan implementation.

| Trigger | Scope | Default priority | Behavior |
| --- | --- | ---: | --- |
| `initial` | whole library | 100 | Automatically queued in the library-create transaction |
| `manual` | whole library or validated folder | 100 | User-requested refresh; returns HTTP 202 |
| `watcher` | smallest safe changed scope | 50 | Debounced and merged by library/common ancestor |
| `startup` | whole library | 10 | Async catch-up after stale-job recovery |
| `scheduled` | whole library | 10 | Periodic authoritative reconciliation |

Valid operation/trigger pairs are explicit:

- `scan × initial|manual|watcher|startup|scheduled`;
- `rebuild × manual` only;
- `scan_all × manual` is an orchestration parent whose child jobs are normal
  `scan × manual` jobs and do not write catalog data themselves.

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

The current direct watcher writes (`mark_folder_index_incomplete` and direct
metadata staging) are deleted during implementation. The watcher only submits
canonical scan requests to the coordinator.

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
- Skip/coalesce only when a queued/running scan's scope contains the requested
  whole-library scope. A narrow watcher scan never suppresses a scheduled full
  scan.
- A full scheduled reconciliation may not be delayed beyond the configured
  maximum queue wait, even under continuous watcher traffic.
- A schedule tick never executes filesystem work in the scheduler thread.

## 5. Durable jobs, concurrency, and idempotency

The current schema is already SQLite `user_version=8`. This refactor migrates
**v8 to v9**. Reusing v8 is a release blocker.

### 5.1 Schema changes

Add to `library_jobs`:

- `scope_path TEXT NULL`: null means the whole library;
- `trigger TEXT NOT NULL DEFAULT 'manual'`;
- `priority INTEGER NOT NULL DEFAULT 50`;
- counters for discovered, created, updated, offline, and metadata-queued assets
  if equivalent existing counters cannot represent them clearly.

Add `library_id` and `last_seen_scan_job_id` to `file_index`, and
`last_seen_scan_job_id` to `assets`. Add a job-scoped
`catalog_rebuild_entries` staging table keyed by `(job_id, path)` for atomic
rebuild activation. Add indexes for:

- `(library_id, type, state, scope_path)`;
- `(state, priority, created_at)`;
- catalog reconciliation by library, scope, and last-seen job.

Standardize current-version identity on integer nanoseconds: `assets`,
`file_index`, `metadata_index_jobs`, and current metadata records expose/use
`mtime_ns` rather than float-second `mtime`. Legacy float timestamps are not
trusted as current after migration; the startup scan records exact stat values
and queues metadata only as needed. Migration itself does not parse media.

Remove public and application dependencies on `libraries.root_path`. The v9
migration rebuilds the SQLite `libraries` table without that column after
verifying every library has canonical rows in `library_import_paths`.

Migration preflight, before any mutation:

1. for an existing database, verify the migration chain has reached exactly
   v8; a fresh empty database is created directly at v9;
2. verify every library maps to at least one import path;
3. reject duplicate or ancestor/descendant import-path overlap, including
   cross-library overlap, and report the conflicting library/path pairs;
4. verify every existing catalog row can be assigned to exactly one library;
5. checkpoint WAL and create a timestamped backup with SQLite's backup API;
6. abort if preflight or backup fails.

Schema mutation runs in one transaction and advances `user_version` only after
all post-migration checks pass. Queued/running legacy `repair` or `scan_all`
execution rows are closed with a migration reason; historical rows remain for
audit but never count as covering scans. Rollback after a successful deployment
means restoring the automatic v8 backup, not attempting a fragile manual
down-migration. Migration tests cover clean v8, failed preflight, transactional
rollback, and retry after an aborted attempt.

### 5.2 Job types and states

Catalog operations:

- `scan`: non-destructive discovery and reconciliation;
- `rebuild`: regenerate catalog and metadata state for the requested scope.

States:

- `queued`, `running`, `succeeded`, `failed`, `cancelled`.

`trigger` is orthogonal to operation. For example, an initial library job is
`type=scan, trigger=initial`. `rebuild` is not a trigger value.

### 5.3 Writer rules

- A library-wide job (`scope_path=NULL`) covers every import path in that
  library. A scoped job covers only the same canonical path or descendants
  inside the same import root; it never covers a parent or sibling import root.
- At most one catalog writer runs per library.
- Different libraries may run concurrently up to configured worker limits.
- The metadata worker may run while catalog scanning, using versioned file
  identity to reject stale results.
- Coalescing lookup, priority/trigger promotion, queued-job cancellation, and
  insertion execute under one `BEGIN IMMEDIATE` coordinator transaction.
- A queued scan whose scope covers a new request is reused. Its priority is
  promoted to the maximum of old/new priority; when the incoming request has a
  higher priority its trigger becomes the incoming trigger.
- A manual scan covered by a running scan returns that active job with
  `coalesced=true`; a broader manual request is queued after the narrower run.
- Watcher changes arriving during a running scan create/coalesce a durable
  follow-up dirty-scope scan, because the running enumerator may already have
  passed that folder.
- A broader queued scan supersedes/cancels narrower queued scans for the same
  library.
- A broader request arriving while a narrower scan is running is queued after
  it; the running job is not interrupted.
- Watcher/startup/scheduled requests always coalesce or defer; they never
  surface user-facing conflicts.
- A confirmed manual rebuild cancels/supersedes queued non-rebuild scans for
  the same library/scope. It returns 409 only when catalog work is already
  running or another rebuild is queued/running.
- A manual scan requested while rebuild is queued/running returns 409; it is
  never silently treated as a rebuild.
- Automated changes during rebuild are stored as dirty scopes and scanned after
  rebuild activation.

Job selection is priority-descending and FIFO within a priority. Starvation is
bounded: a queued job waiting longer than
`GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS` (default 600) is promoted to
effective priority 100. Whole-library scheduled work is considered covered only
by a queued/running whole-library scan, never by narrower jobs.

`cancelled` is an internal terminal state for queued work superseded before it
starts. It does not affect summary state, timestamps, or issue count. Running
jobs are not cancelled; restart/interruption marks them failed with an explicit
reason.

### 5.4 SQLite execution rules

- Keep WAL mode and `busy_timeout=5000` on all connections.
- Each catalog/metadata worker owns its connection; connections are not shared
  across threads.
- Filesystem enumeration and metadata parsing never occur inside a SQLite write
  transaction.
- Discovery/staging writes use bounded batches (default at most 500 rows per
  transaction) and yield between batches.
- Reconciliation and rebuild activation are short transactions after
  successful enumeration.
- Read endpoints use short read transactions and never wait for a complete
  filesystem walk.
- One execution lock per library prevents concurrent catalog writers, while
  different disjoint libraries may run up to the configured worker limit.

### 5.5 Crash consistency

- Job creation and wake-up use recoverable-outbox semantics: queued DB rows are
  the source of truth, so a process crash before worker notification loses no
  work.
- A scan only reconciles missing rows after enumeration succeeds.
- Rebuild writes only staging rows while running. Canonical rows remain
  browseable until successful activation.
- Rebuild activation is idempotent: staged rows are keyed by job/path, merge is
  upsert-based, and staging cleanup occurs only after commit.
- Failed rebuild preserves the previous usable catalog, marks status as an
  issue, and leaves staging safe for retry/cleanup.
- Metadata results update metadata-owned fields only when canonical path,
  integer `mtime_ns`, and size still match in the write transaction.

## 6. API contract changes

### 6.1 Library commands

```text
POST /api/libraries
POST /api/libraries/scan-all
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

`POST /api/libraries/scan-all` remains a bulk admin command, but its current
direct `BackgroundTasks` implementation is replaced. The coordinator creates
one orchestration parent and one coalesced `scan × manual` child per library.
Only child jobs affect library status or write catalog data.

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
  "requested_operation": "rebuild",
  "active_job": {
    "job_id": 122,
    "operation": "scan",
    "trigger": "scheduled",
    "state": "running",
    "scope_path": null
  },
  "message": "Catalog work is already active for this library."
}
```

### 6.2 Status endpoints

Use one status builder and one scope-status schema:

```text
GET /api/libraries/{id}/status
GET /api/libraries/{id}/status?scope_path={path}
GET /api/libraries/status
```

Single-scope response:

```ts
interface StatusResponseEnvelope {
  contract_version: 1;
  status: UnifiedStatus;
  global_runtime: GlobalRuntime;
}
```

Batch response:

```ts
interface LibraryStatusBatchResponse {
  contract_version: 1;
  generated_at: number;
  items: Array<{ library_id: number; status: UnifiedStatus }>;
  global_runtime: GlobalRuntime;
}
```

The admin performs one library-list query and one status-batch query, then joins
by `library_id`; status does not duplicate library names/configuration. Batch
aggregation uses grouped SQL in a bounded number of queries independent of the
number of libraries/assets. Acceptance budget: warm p95 at most 100 ms for 50
libraries on the deterministic fixture. Global runtime appears once in the
batch envelope, not once per library.

The scoped endpoint powers the sidebar. No global semantic summary endpoint is
introduced; removal of old global `/api/index/status` is intentional, and the
frontend must not derive a synthetic global `summary_state`. Remove legacy
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

interface UnifiedStatus {
  contract_version: 1;
  generated_at: number; // Unix epoch milliseconds UTC
  summary_state: SummaryState;

  scope: {
    kind: "library" | "path";
    library_id: number;
    path: string | null;
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
    trigger: "initial" | "manual" | "watcher" | "scheduled" | "startup" | null;
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
}

interface GlobalRuntime {
  catalog_worker_count: number;
  catalog_active_jobs: number;
  catalog_queue_depth: number;
  metadata_worker_count: number;
  metadata_active_jobs: number;
  metadata_queue_depth: number;
  metadata_staged_queue_depth: number;
  watcher_enabled: boolean;
  watcher_healthy: boolean;
  watcher_issue: string | null;
  scheduled_reconciliation_enabled: boolean;
}
```

### 7.1 Scope rules

- Library status aggregates all configured import paths.
- Path status includes that folder and descendants only.
- Containment is path-component based, never raw string prefix matching.
- Canonical identity uses lexical normalization: strip trailing separators,
  collapse `.`/`..`, normalize Unicode NFC and platform separators, lowercase
  Windows drive letters, and preserve UNC roots. Comparison follows the source
  volume's case behavior where detectable, otherwise the host default.
- Configured import-path identity does not resolve symlinks, so it remains
  stable while offline. When online, validation also compares resolved targets
  to prevent alias overlap.
- Enumeration does not follow nested symlinked files/directories by default.
  No symlink may escape scope for discovery, reconciliation, or pruning.
- `total_assets` counts online active supported image and video assets in scope;
  offline tombstones are excluded.
- Current metadata requires matching canonical path, integer `mtime_ns`, and
  size.

### 7.2 Offline and tombstone lifecycle

- A missing asset becomes `offline=1` only after a successful covering scan.
- Failure/unavailability of an import root does not mass-mark its assets
  offline; the previous catalog remains usable and availability reports the
  root issue.
- Normal browse excludes offline assets and folders. The virtual root still
  shows unavailable import roots with an Offline label.
- Offline tombstones are retained indefinitely in v1 to preserve identity and
  reusable metadata if the same path/version returns. They are removed only by
  library deletion or a future explicit purge/retention workflow.
- An expected missing-file tombstone does not increment `issue_count`.
- If a path returns, catalog scan restores it online and reuses metadata only
  when `mtime_ns + size` still match.

### 7.3 Progress and issues

- `not_ready_assets = total_assets - ready_assets - failed_assets`.
- `queued + running + stale + idle_pending = not_ready_assets`.
- UI never adds `not_ready_assets` to its breakdown fields.
- All `progress_percent` fields use the inclusive 0–100 scale.
- Metadata progress is `100 * ready_assets / total_assets`.
- If `total_assets == 0` and scan is complete, metadata progress is exactly
  `100`; a never-scanned scope reports null.
- `issue_count` includes unavailable import paths, the latest unresolved
  covering scan failure, and current-version metadata failures.
- Pending/stale work changes state but is not an issue.
- With metadata disabled, all metadata counts/progress are null and a completed
  scan can reach Ready. UI shows `File scan ready, metadata disabled`.

### 7.4 Summary precedence

Derive centrally in this order:

1. unresolved library/scope: `unknown`;
2. entire scope unavailable: `offline`;
3. covering scan/rebuild queued or running: `scanning`;
4. metadata queued or running: `indexing`;
5. latest covering scan failed and no prior successful covering scan exists:
   `error`;
6. never successfully scanned and no failed attempt exists: `needs_scan`;
7. no usable metadata and all current assets failed: `error`;
8. current pending/stale metadata without active work: `needs_update`;
9. usable catalog plus a later scan/rebuild failure, metadata failures, or
   degraded availability:
   `ready_with_issues`;
10. completed scan and settled metadata without issues: `ready`.

An active retry outranks a historical failure, so status changes from Error to
Scanning immediately after retry is accepted.

Cancelled queued jobs are ignored by precedence. Metadata-disabled plus
scan-never is normally unreachable because initial/startup jobs are durable; if
encountered after migration or operator intervention it resolves to
`needs_scan`, not `ready`.

### 7.5 Timestamps

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
  event: "job_queued" | "job_running" | "job_succeeded" | "job_failed" | "job_cancelled";
  job_id: number;
  library_id: number;
  scope_path: string | null;
  operation: "scan" | "rebuild";
  trigger: "initial" | "manual" | "watcher" | "scheduled" | "startup";
  updated_at: number;
}
```

Metadata completion also invalidates status and metadata-derived browse fields,
but never emits one SSE event per asset. The backend coalesces changes for at
least 250 ms and at most 500 ms per library:

```ts
interface MetadataStatusInvalidationEvent {
  contract_version: 1;
  event: "metadata_progress" | "metadata_settled";
  library_id: number;
  scope_paths: string[] | null; // null means invalidate the whole library
  succeeded: number;
  failed: number;
  updated_at: number;
}
```

The path list is bounded; overflow degrades to library-wide invalidation.

Frontend rules:

- TanStack Query owns browse and status server state.
- Replace `useInfiniteScanQuery`/`scanDirectory` with
  `useInfiniteBrowseQuery`/`browseDirectory`; browse query functions are reads
  and never reused as scan mutations.
- Replace `useLibraryProgressQuery` and `useIndexStatusQuery` with one shared
  `useCatalogStatusQuery` plus `useLibraryStatusBatchQuery` for admin lists.
- Status keys are `['status', 'library', id]` and
  `['status', 'path', id, normalizedPath]`.
- Browse keys include library ID, normalized path/null virtual root,
  sort/filter, offline flag, and cursor.
- Poll status every 2.5 seconds while active and every 60 seconds when stable.
- Catalog SSE invalidates affected library/overlapping path status and browse;
  throttled metadata SSE invalidates status and only browse fields whose cached
  dimensions/metadata can change.
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

### 8.1 Admin libraries

- The list joins `GET /api/libraries` with `GET /api/libraries/status` by ID;
  it does not issue one status request per row.
- Badges come only from unified status, never `RegisteredLibrary.state`.
- Replace the list's `Updated` column with `Last index`; retain configuration
  Updated on the detail page.
- Detail shows Availability, File scan, Metadata progress, issue breakdown,
  Last scan, and Last index separately.
- Online import roots remain browseable when another root is unavailable.
- Add Library has one submit action. Success immediately navigates/renders the
  durable initial Scan state.
- Scan All continues as one bulk mutation backed by coordinator child jobs.

### 8.2 Gallery, sidebar, and metadata inspector

- Opening a multi-import library first renders its virtual root. Breadcrumb and
  status are library-wide there, then path-scoped after selecting an import
  root.
- Scope copy is `Current folder · Including subfolders` for real folders and
  `Entire library · All import paths` at the virtual root.
- `Photos found` maps to online `metadata.total_assets`; `Photo details ready`
  maps to `metadata.ready_assets`.
- Show Last scan and Last index separately.
- Scan invokes `POST /api/libraries/{id}/scan`; Rebuild invokes the confirmed
  library-scoped rebuild endpoint. Remove Repair UI.
- Replace “clear index cache” wording with “rebuild indexed files and extracted
  metadata”; do not imply thumbnail/preview disk caches are cleared.
- Preserve `Indexer working in another folder` through
  `metadata.global_active_outside_scope`.
- An unavailable virtual import-root entry remains visible and labeled Offline;
  ordinary offline asset tombstones remain hidden.

## 9. Configuration changes

Introduce/standardize:

```text
GALLERY_CATALOG_WORKERS=1
GALLERY_CATALOG_WATCHER_ENABLED=true
GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS=2
GALLERY_CATALOG_RECONCILE_ENABLED=true
GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS=21600
GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=true
GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS=600
GALLERY_CATALOG_WRITE_BATCH_SIZE=500
GALLERY_METADATA_EVENT_THROTTLE_MS=500
```

Production dependencies must include the supported watcher package. If watcher
initialization fails, startup continues with scheduled reconciliation active,
status/logging exposes the degradation, and no direct alternate catalog writer
is used. Watcher health is operational runtime information: it does not add a
library issue or change `summary_state` while scheduled reconciliation remains
available.

Remove `GALLERY_DB_REQUIRED` and superseded refresh/index watcher names after
configuration migration documentation is updated.

## 10. Implementation sequence

Each phase must leave tests passing; the API hard cut occurs atomically in the
final integration phase.

1. Add contract fixtures and state-precedence tests before production changes.
2. Add v8→v9 preflight/backup migration, path helpers, job fields/indexes,
   rebuild staging, and migration tests.
3. Implement the durable Catalog Scan Service and one-library writer lock.
4. Route initial, manual, watcher, startup, and scheduled triggers through it.
5. Implement rebuild staging/atomic activation and remove independent repair
   logic.
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

- Library and path endpoints return the same `UnifiedStatus` schema inside the
  documented envelope.
- Batch status uses a bounded number of grouped queries with no
  per-library/per-asset N+1 queries.
- Similar path prefixes never leak sibling data.
- Null browse path returns ordered virtual import-root entries and library-wide
  status; real descendants return path-scoped status.
- Same-library and cross-library duplicate/ancestor/descendant/resolved-alias
  import paths are rejected.
- Multi-import libraries aggregate available/degraded/unavailable correctly.
- Current metadata checks path + integer `mtime_ns` + size.
- Scan and index timestamps obey separate covering-scope rules.
- Progress is 0–100; a complete empty scope is 100 and an unscanned scope is
  null.
- Warm single-scope status meets 50 ms p95 and the 50-library batch meets
  100 ms p95 on the deterministic fixture.
- Global runtime appears once per envelope/batch and reports catalog workers,
  metadata workers, watcher health, and scheduled-reconciliation state.

### 11.2 Pipeline behavior

- Creating a library atomically creates an initial scan job.
- The API and app startup do not block on catalog or metadata completion.
- Assets become browseable after catalog discovery, before metadata completes.
- Watcher events and scheduled scans invoke the same service and produce the
  same catalog result as manual scan.
- Watcher roots update after library/import-path CRUD without restart.
- Dropped watcher events are repaired by scheduled reconciliation.
- Direct watcher folder/metadata writes no longer exist.
- Duplicate/overlapping triggers coalesce according to §5.3.
- Atomic concurrent requests cannot create duplicate equivalent jobs.
- Continuous watcher traffic cannot delay scheduled full reconciliation beyond
  the configured maximum wait.
- Manual rebuild supersedes queued background scans, conflicts with running
  work, and manual scan never silently coalesces into rebuild.
- Cancelled queued jobs do not change semantic status or issue count.
- Restart recovers queued jobs and fails interrupted running jobs visibly.
- Failed enumeration does not mark unseen assets offline.
- Browse serves the canonical generation throughout rebuild; failed/mid-crash
  rebuild preserves it and leaves only recoverable staging rows.
- New/changed assets queue metadata once; unchanged assets do not.
- File mutation before/during extraction fails the pre/post/conditional version
  guard and cannot write stale metadata.
- Removed assets become offline only after a successful covering scan.
- Offline tombstones are hidden/excluded from totals, do not create issues, and
  restore correctly when the same current version returns.

### 11.3 API hard-cut checks

- `/api/browse` performs no filesystem calls and no writes.
- `/api/scan`, library repair, `/api/index/rebuild`, and `/api/index/status`
  return 404 after migration.
- `/api/libraries/scan-all` remains available but creates only coordinator
  parent/child jobs and performs no direct scan work.
- Unregistered and cross-library scopes are rejected.
- No runtime/API/frontend source references `root_path` or
  `GALLERY_DB_REQUIRED`; only the v9 migration and its v8 fixture may mention the
  removed schema/config names.
- Rescan is only `POST /api/libraries/{id}/scan`.

### 11.4 Frontend behavior

- Admin and sidebar render identical semantics for the same status fixture.
- Their counts differ correctly between whole-library and folder scope.
- Add Library has one submit path and immediately shows Scanning.
- Multi-import virtual root, breadcrumbs, path picker entries, and library-wide
  status follow §3.3.
- Opening a newly created library handles empty/partial catalog pages cleanly.
- New files appear after watcher catalog completion without reopening folder.
- Scan action is a POST mutation and never invokes browse as a side effect.
- Repair UI is removed; rebuild remains explicitly confirmed.
- Last scan and Last index are separately labeled.
- Metadata progress events refresh affected status/browse without per-asset SSE
  floods.
- Watcher degradation is visible while scheduled reconciliation remains active.
- No UI reports Ready while current work is pending, stale, queued, or running.

### 11.5 Release gates

- migration/preflight/backup/rollback tests from a real v8 fixture;
- verify migration aborts before mutation for missing import-path mappings,
  overlap, ambiguous catalog ownership, or backup failure;
- focused catalog worker, coalescing, watcher, scheduler, browse, status, and
  library API tests;
- frontend unit tests for contract guard, query keys, polling, invalidation,
  and shared status presentation;
- Playwright flows for create library, initial scan, manual scoped scan,
  multi-import virtual root, new-file watcher update, scheduled reconciliation,
  offline tombstone/root, and rebuild failure;
- `./test.sh fast` and the repository's full release suite;
- atomic frontend/backend deployment with a documented breaking-change note.

## 12. Required contract fixtures

These representative `UnifiedStatus` objects become shared backend/frontend
fixtures. Timestamps are epoch milliseconds and progress uses 0–100.

### 12.1 New library, initial scan queued

```json
{
  "contract_version": 1,
  "generated_at": 1782036000000,
  "summary_state": "scanning",
  "scope": {"kind": "library", "library_id": 7, "path": null, "import_path_count": 2},
  "availability": {"state": "available", "available_paths": 2, "total_paths": 2},
  "scan": {"state": "queued", "operation": "scan", "trigger": "initial", "active_job_id": 101, "completed_units": 0, "total_units": null, "progress_percent": null},
  "metadata": {"state": "queued", "total_assets": 0, "ready_assets": 0, "not_ready_assets": 0, "queued_assets": 0, "running_assets": 0, "stale_assets": 0, "idle_pending_assets": 0, "failed_assets": 0, "progress_percent": null, "global_active_outside_scope": false},
  "issue_count": 0,
  "issues": {"availability": 0, "scan": 0, "metadata": 0},
  "latest_issue": null,
  "last_scan_at": null,
  "last_index_at": null
}
```

`metadata.state=queued` while an initial covering scan is queued/running means
metadata discovery is waiting on catalog output; zero assets are not treated as
a completed empty library until scan succeeds.

### 12.2 Scan complete, metadata indexing

```json
{
  "contract_version": 1,
  "generated_at": 1782036060000,
  "summary_state": "indexing",
  "scope": {"kind": "path", "library_id": 7, "path": "/photos/2026", "import_path_count": 1},
  "availability": {"state": "available", "available_paths": 1, "total_paths": 1},
  "scan": {"state": "complete", "operation": "scan", "trigger": "manual", "active_job_id": null, "completed_units": 120, "total_units": 120, "progress_percent": 100},
  "metadata": {"state": "indexing", "total_assets": 100, "ready_assets": 60, "not_ready_assets": 38, "queued_assets": 30, "running_assets": 8, "stale_assets": 0, "idle_pending_assets": 0, "failed_assets": 2, "progress_percent": 60, "global_active_outside_scope": false},
  "issue_count": 2,
  "issues": {"availability": 0, "scan": 0, "metadata": 2},
  "latest_issue": {"source": "metadata", "path": "/photos/2026/bad.jpg", "message": "Metadata extraction failed", "updated_at": 1782036055000},
  "last_scan_at": 1782036040000,
  "last_index_at": 1782036059000
}
```

### 12.3 Ready with one unavailable import path

```json
{
  "contract_version": 1,
  "generated_at": 1782037000000,
  "summary_state": "ready_with_issues",
  "scope": {"kind": "library", "library_id": 7, "path": null, "import_path_count": 2},
  "availability": {"state": "degraded", "available_paths": 1, "total_paths": 2},
  "scan": {"state": "complete", "operation": "scan", "trigger": "scheduled", "active_job_id": null, "completed_units": 100, "total_units": 100, "progress_percent": 100},
  "metadata": {"state": "complete", "total_assets": 100, "ready_assets": 100, "not_ready_assets": 0, "queued_assets": 0, "running_assets": 0, "stale_assets": 0, "idle_pending_assets": 0, "failed_assets": 0, "progress_percent": 100, "global_active_outside_scope": false},
  "issue_count": 1,
  "issues": {"availability": 1, "scan": 0, "metadata": 0},
  "latest_issue": {"source": "availability", "path": "/mnt/archive", "message": "Import path is unavailable", "updated_at": 1782036990000},
  "last_scan_at": 1782036900000,
  "last_index_at": 1782036950000
}
```

### 12.4 Rebuild failed, previous catalog still usable

```json
{
  "contract_version": 1,
  "generated_at": 1782038000000,
  "summary_state": "ready_with_issues",
  "scope": {"kind": "path", "library_id": 7, "path": "/photos/2026", "import_path_count": 1},
  "availability": {"state": "available", "available_paths": 1, "total_paths": 1},
  "scan": {"state": "failed", "operation": "rebuild", "trigger": "manual", "active_job_id": null, "completed_units": 42, "total_units": null, "progress_percent": null},
  "metadata": {"state": "complete", "total_assets": 100, "ready_assets": 100, "not_ready_assets": 0, "queued_assets": 0, "running_assets": 0, "stale_assets": 0, "idle_pending_assets": 0, "failed_assets": 0, "progress_percent": 100, "global_active_outside_scope": false},
  "issue_count": 1,
  "issues": {"availability": 0, "scan": 1, "metadata": 0},
  "latest_issue": {"source": "scan", "path": "/photos/2026", "message": "Rebuild failed; previous catalog remains active", "updated_at": 1782037990000},
  "last_scan_at": 1782036900000,
  "last_index_at": 1782036950000
}
```

## 13. Explicit non-goals

- Do not merge filesystem scan and metadata extraction into one synchronous
  workflow.
- Do not add Redis/BullMQ or a distributed queue in this refactor.
- Do not parse metadata or probe image dimensions during filesystem discovery.
- Do not add a second catalog writer as fallback when watcher or scheduler
  fails.
- Do not preserve legacy ad-hoc path browsing or compatibility aliases.
- Do not retain a lightweight DB-only Repair command; canonical reconciliation
  requires a filesystem scan.
- Do not provide or derive one global semantic summary state; scope is library
  or registered path.
- Do not follow nested symlinks during discovery in v1.
- Do not add content hashing, inode/device move tracking, or automatic offline
  tombstone expiry in v1.
- Do not implement filesystem write/import/upload semantics; this plan covers
  discovery of externally managed library paths.

## 14. Decisions superseded by this revision

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

## 15. Audit resolution and approval gate

Revision 2 incorporates the required findings from the GPT and OpenCode audits:
v9 migration correction, virtual multi-root browse, overlap rejection,
field-level ownership, SQLite execution constraints, tombstone lifecycle,
throttled metadata invalidation, conflict/cancellation/starvation rules,
rebuild staging, batch/runtime schemas, Scan All ownership, detailed frontend
migration, progress scale, fixtures, and migration backup/preflight.

No production code, migration, API, frontend, or configuration change described
by this plan may be implemented until the user explicitly approves this revised
document. Documentation-only review edits remain allowed before approval.
