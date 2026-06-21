# Unified Scan and Metadata Status Contract Plan

Status: Proposed

Created: 2026-06-21

## 1. Goal and locked decisions

Keep filesystem scanning and metadata indexing as separate workflows, but make
them expose one status contract and use one set of presentation rules.

- `/api/libraries/{id}/progress` aggregates every import path in a library.
- `/api/index/status?path=...` covers the selected folder and its descendants.
- Both endpoints switch directly to the new response. There is no compatibility
  adapter for their old response shapes.
- `Ready` means the scan is complete and all current metadata is ready.
- A usable scope with individual failures is `Ready with issues`.
- A library with only some unavailable import paths is `degraded`; available
  paths remain usable.
- `issue_count` counts actual failures, not pending or stale work.
- Scoped Rescan and Rebuild actions are persisted as jobs so status, SSE, and
  timestamps converge after navigation and process restarts.
- Frontend and backend changes ship atomically because this is a breaking API
  response change.

## 2. Unified status contract

Replace `LibraryProgress` and `IndexStatusResponse` with one public type:

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
type MetadataState = "disabled" | "queued" | "indexing" | "needs_update" | "complete" | "failed";

interface UnifiedStatusResponse {
  contract_version: 1;
  generated_at: number;
  summary_state: SummaryState;

  scope: {
    kind: "global" | "library" | "path";
    library_id: number | null;
    path: string | null;
    include_subfolders: boolean;
    import_path_count: number;
  };

  availability: {
    state: AvailabilityState;
    available_paths: number;
    total_paths: number;
  };

  scan: {
    state: ScanState;
    operation: "scan" | "scope_scan" | "rebuild" | null;
    active_job_id: number | null;
    completed_units: number | null;
    total_units: number | null;
    progress_percent: number | null;
  };

  metadata: {
    state: MetadataState;
    total_assets: number;
    ready_assets: number;
    pending_assets: number;
    queued_assets: number;
    running_assets: number;
    stale_assets: number;
    failed_assets: number;
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
    worker_count: number;
    active_jobs: number;
    queue_depth: number;
    staged_queue_depth: number;
    active_scan_requests: number;
  };
}
```

### Data rules

- `metadata.total_assets` is the count of active image assets in the scope.
- `ready_assets` requires an `image_metadata` row whose path, mtime, and size
  match the current asset.
- `failed_assets` counts failed metadata jobs for the current file version.
- `pending_assets = total_assets - ready_assets - failed_assets`.
- Queued, running, and stale counts are breakdowns of work that is not ready.
- Progress is `ready_assets / total_assets`. A scanned scope with no images is
  100%; an unscanned scope reports `null`.
- `last_scan_at` is the completion time of the latest successful scan or
  rebuild that covers the whole requested scope.
- `last_index_at` is the latest successful write time of current metadata. It
  never uses failed or queued job timestamps.
- Rebuild counts as a scan because it traverses the filesystem again.

### Summary-state precedence

Derive `summary_state` centrally in this order:

1. Scope cannot be resolved: `unknown`.
2. The entire scope is unavailable: `offline`.
3. The latest covering scan failed: `error`.
4. The scope has never been scanned: `needs_scan`.
5. Scan work is queued or running: `scanning`.
6. Metadata work is queued or running: `indexing`.
7. Pending or stale work remains without an active worker: `needs_update`.
8. Every metadata asset failed and none is usable: `error`.
9. Metadata is settled but failures exist, or availability is degraded:
   `ready_with_issues`.
10. Scan and metadata are complete without issues: `ready`.

`issue_count` is the sum of unavailable import paths, one issue for a failed
covering scan, and current-version metadata failures. Pending and stale work
change the state to `needs_update` but do not increase the issue count.

## 3. Backend and persistence

### Shared status builder

- Add one status service used by both endpoints. Routers and frontend code must
  not independently derive semantic states.
- Query library scope from `assets.library_id`. Query path scope with
  path-component containment, never a raw string-prefix test.
- Check current mtime and size when counting metadata or failed jobs so stale
  rows cannot report a false Ready state.
- Merge persisted aggregates with the in-memory indexer snapshot to include
  staged and running work.
- Keep `/api/index/status` without a `path` as a global scope, but return the
  new contract.
- Continue supporting a safe, unregistered path when `GALLERY_DB_REQUIRED` is
  disabled. Use `library_id=null`. Preserve DB-required rejection behavior.

### Database migration and job scope

Increase SQLite `user_version` from 7 to 8:

- Add nullable `library_jobs.scope_path TEXT`.
- Add an index covering `library_id`, `type`, `state`, and `scope_path`.
- Interpret old `scan` jobs with `scope_path=NULL` as library-wide.
- Include `scope_path` in job responses and SSE payloads.
- Recover interrupted `scope_scan` and `rebuild` jobs through the existing
  stale-job recovery mechanism.

Operation semantics:

- `scan`: all import paths in one library; `scope_path=NULL`.
- `scope_scan`: non-destructive scan of one path.
- `rebuild`: clear and regenerate index/metadata records for one path.
- `repair`: catalog reconciliation only; it does not determine Scan state.

A job covers a path when it is library-wide or its `scope_path` equals or is
an ancestor of that path. Scanning a child does not update the parent's
`last_scan_at` because it did not cover the parent scope.

### Scoped actions

- Add `POST /api/index/rescan?path=...` returning HTTP 202 with
  `{job_id, library_id, scope_path, operation, state}`.
- Convert `/api/index/rebuild` to a persisted background job returning the same
  response shape; keep `confirm=true` mandatory.
- Rescan traverses and queues metadata without deleting valid records.
- Rebuild clears scoped index/metadata records, traverses, then queues metadata.
- Emit queued, running, succeeded, and failed SSE events for both actions.
- Permit one active scan, repair, scope-scan, or rebuild operation per library.
  A conflicting request returns `409 library_busy`.
- For safe unregistered paths, persist a job with `library_id=NULL` and detect
  conflicts by overlapping scope paths.
- Queueing or clearing metadata sets affected `assets.metadata_state` to
  `pending`; successful extraction returns it to `done`.

## 4. Frontend and UI semantics

### Query ownership

- Replace the index-status and library-progress composables with one shared
  status composable and these keys:
  - `["status", "library", libraryId]`
  - `["status", "path", normalizedPath]`
- Poll every 2.5 seconds while scan or metadata work is queued/running and every
  60 seconds when stable.
- Invalidate the status root for relevant SSE events and all Scan, Rescan,
  Rebuild, and Repair mutations.
- Remove frontend derivation from `RegisteredLibrary.state`, legacy
  `LibraryProgress`, and legacy index runtime fields.
- Keep `RegisteredLibrary.state` in the library record for backend
  compatibility, but do not use it for UI badges.

### Shared presentation

Create one presentation utility used by admin and sidebar:

| State                 | Label               |
| --------------------- | ------------------- |
| `needs_scan`          | Needs scan          |
| `scanning`            | Scanning            |
| `indexing`            | Updating            |
| `needs_update`        | Needs update        |
| `ready`               | Ready               |
| `ready_with_issues`   | Ready with issues   |
| `offline`             | Offline             |
| `error`               | Error               |
| `unknown`             | Unknown             |

Admin and sidebar must not keep separate status-precedence tables.

### Admin libraries

- Build badges from unified status rather than `library.state`.
- Show metadata progress as `ready_assets / total_assets`.
- Replace the list's `Updated` column with `Last index`; keep configuration
  `Updated` on the detail page.
- Show Availability, File scan, Metadata, issue breakdown, Last scan, and Last
  index as separate fields on the detail page.
- Keep online import paths browsable when a multi-path library is degraded.

### Sidebar and metadata inspector

- Use the same badge and progress rules as admin.
- Label scope as `Current folder · Including subfolders`.
- Map `Photos found` to `metadata.total_assets` and `Photo details ready` to
  `metadata.ready_assets`.
- Show Last scan and Last index separately.
- Call the new POST Rescan endpoint instead of `GET /api/scan`.
- Replace “clear index cache” copy with “clear indexed file and extracted
  metadata records”; do not imply thumbnail/preview disk cache is cleared.
- Preserve “Indexer working in another folder” through
  `global_active_outside_scope`.

## 5. Implementation sequence

1. Lock response schema and summary precedence with backend and frontend
   contract tests.
2. Add migration v8 and persisted scoped jobs.
3. Implement the shared status builder and change both API responses together.
4. Convert Rescan/Rebuild to persisted jobs with SSE and conflict guards.
5. Replace frontend types, composables, polling, and invalidation rules.
6. Move admin and sidebar components to the shared presentation layer.
7. Update README, architecture, UI/UX guidelines, and test catalog.
8. Run all release gates. Once implemented, mark this plan complete and move
   it to `docs/archived/`.

## 6. Test plan and acceptance criteria

### Backend

- Both endpoints return identical top-level schemas with `contract_version=1`.
- Library scope aggregates multiple import paths correctly.
- Path scope does not include a sibling with a similar string prefix.
- Availability covers available, degraded, and unavailable states.
- Scan covers never, queued, scanning, complete, and failed states.
- Metadata covers disabled, queued, indexing, needs-update, complete, partial
  failure, and total failure.
- Metadata or jobs with old mtime/size do not count as current.
- Pending/stale work does not increase issue count.
- An empty scanned library is Ready with 100% metadata progress.
- Last scan and Last index follow their separate timestamp definitions.
- Scoped jobs are visible through polling and are failed by restart recovery.
- Rebuild resets metadata state; Rescan preserves valid records.
- Conflicting operations return HTTP 409.
- Global scope and safe unregistered paths retain configured behavior.
- Status aggregation avoids per-asset N+1 queries and remains at or below a
  50 ms warm p95 on the existing deterministic fixture.

### Frontend unit tests

- One matrix covers every summary-state presentation.
- Library/path query keys cannot collide.
- Polling switches between 60 seconds and 2.5 seconds correctly.
- SSE and mutations invalidate both status scopes as required.
- Admin and sidebar render the same label for the same status fixture.
- Progress, issue count, degraded availability, and both timestamps render
  correctly.
- No source imports or uses `LibraryProgress`, `IndexStatusResponse`, or legacy
  status helpers.

### End-to-end scenarios

- Admin Scan transitions `Scanning -> Updating -> Ready`; the sidebar at the
  import root follows the same semantic sequence.
- Sidebar Rebuild makes both sidebar and owning library show Updating instead
  of leaving admin at Ready/100%.
- Individual metadata failures produce Ready with issues in both views.
- Complete metadata failure produces Error in both views.
- One offline import path produces Ready with issues while online paths remain
  browsable and the offline path reports Offline.
- Nested-folder and whole-library counts differ by scope, but status semantics
  remain identical.
- Metadata-only work changes Last index without changing Last scan.
- No UI reports Ready while current metadata remains queued, running, pending,
  or stale.

### Release gates

- Run `./test.sh fast`.
- Run focused backend status and library API integration suites.
- Run functional Playwright coverage for admin libraries and metadata
  inspector.
- Run status/index performance smoke checks.
- Deploy frontend and backend atomically; old frontend clients are not supported
  against the new response shape.
