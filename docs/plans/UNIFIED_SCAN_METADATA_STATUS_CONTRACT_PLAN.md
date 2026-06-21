# Unified Scan and Metadata Status Contract Plan

Status: Proposed (reviewed 2026-06-21 — see §7 for audit findings and revisions)

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

- `metadata.total_assets` is the count of active **image and video** assets in the scope.
- `ready_assets` requires an `image_metadata` row whose path, mtime, and size
  match the current asset.
- `failed_assets` counts failed metadata jobs for the current file version.
- `not_ready_assets = total_assets - ready_assets - failed_assets`. This is the
  total of assets that are neither ready nor failed; it is NOT displayed directly
  on its own.
- `queued_assets`, `running_assets`, `stale_assets` are breakdowns of
  `not_ready_assets`. A fourth sub-field `idle_pending_assets` fills the
  remainder:
  `idle_pending_assets = not_ready_assets - queued_assets - running_assets - stale_assets`.
- **UI must never render `not_ready_assets + queued + running + stale` in one
  view — that would double-count.**
- Progress is `ready_assets / total_assets`. A scanned scope with no images is
  100%; an unscanned scope reports `null`.
- Rebuild counts as a scan because it traverses the filesystem again.

### Summary-state precedence

Derive `summary_state` centrally in this order:

1. Scope cannot be resolved: `unknown`.
2. The entire scope is unavailable: `offline`.
3. Scan, scope_scan, or rebuild work is queued or running: `scanning`.
4. Metadata work is queued or running: `indexing`.
5. The latest covering scan failed: `error`.
6. The scope has never been scanned: `needs_scan`.
7. Pending or stale work remains without an active worker: `needs_update`.
8. Every metadata asset failed and none is usable: `error`.
9. Metadata is settled but failures exist, or availability is degraded:
   `ready_with_issues`.
10. Scan and metadata are complete without issues: `ready`.

**Why rules 3-5 are ordered this way:** Active scan/rebuild always takes
priority over a historical failure. If a scan failed and the user clicked
Rescan, the badge must switch to `scanning`, not stay stuck at `error`. The
`error` state for a failed covering scan is only shown when no newer active
work exists.

`issue_count` is the sum of unavailable import paths, one issue for a failed
covering scan, and current-version metadata failures. Pending and stale work
change the state to `needs_update` but do not increase the issue count.

### Timestamp rules

- All public timestamps in the contract are **Unix epoch milliseconds UTC**
  (JavaScript `Date.now()` compatible).
- `latest_issue` is selected as the issue with the greatest `updated_at`.
  Tie-break order: `scan` > `availability` > `metadata` (scan issues reported
  before metadata issues for the same timestamp).
- `last_scan_at` is the completion time of the latest successful scan or
  rebuild that covers the whole requested scope.
- `last_index_at` is the latest successful write time of current metadata. It
  never uses failed or queued job timestamps.
- Rebuild counts as a scan because it traverses the filesystem again.

## 3. Backend and persistence

### Metadata disabled behavior

When the metadata feature is disabled (e.g., `GALLERY_METADATA_ENABLED=false`):

- `scan.state` is unaffected — scanning still runs.
- `metadata.state = "disabled"`.
- `metadata.total_assets`, `ready_assets`, and progress fields are set to
  `null` (not rendered in UI).
- `summary_state` derivation treats metadata as always-complete — a scanned
  scope with disabled metadata can reach `ready`.
- **UI must show a secondary indicator** next to the status badge when
  metadata is disabled: `File scan ready, metadata disabled`.

### Scope and path canonicalization

- `total_assets` covers **both image and video assets** in the scope. The field
  name is unchanged but the semantics include video files.
- Path canonicalization rules applied by the status builder:
  - Normalize trailing slashes (strip).
  - Resolve `.` and `..` components.
  - Normalize backslashes to forward slashes on Windows.
  - Drive letter case is lowered on Windows (`C:\` → `c:/`).
  - Case sensitivity follows the host filesystem (case-insensitive on Windows
    and macOS APFS by default).
  - Symlinks and junctions are **not** resolved — the user-configured import
    path is the canonical identity.
  - UNC paths (`\\server\share`) are kept as-is.
  - Unicode NFC normalization is applied for cross-platform path comparisons.
  - An offline path cannot be canonicalized; its raw import path is used.
- The DB index `(library_id, type, state, scope_path)` must handle the
  canonical form.

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
- **Migration rollback:** The migration runs inside a transaction. On failure,
  `user_version` is not incremented and the DB atomically reverts. For manual
  rollback after a successful migration, restore from backup or run a schema
  downgrade script that drops the added column and index, then sets
  `user_version = 7`.

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
- **Idempotency:** If an equivalent active job already exists for the same scope
  (same library + same operation + same scope_path + same or narrower path),
  return 202 with the existing `job_id`. If a conflicting wider/narrower job
  exists for the same library, return 409 `library_busy`.
- Rescan traverses and queues metadata without deleting valid records.
- Rebuild marks current index/metadata records as **stale/rebuilding first**,
  then traverses. Only delete old records after the new scan succeeds.
  - **Crash recovery:** If the process crashes after marking stale but before
    the new scan completes, stale records remain visible with an `error` state
    and the status derivation includes them in `issue_count`. A follow-up
    rebuild reuses the stale marker.
  - Acceptance test: Crash during rebuild after marking stale does not leave
    status permanently `ready` or inconsistent.
- Emit queued, running, succeeded, and failed SSE events for both actions.
  - **SSE event payload contract:**
    ```ts
    interface StatusInvalidationEvent {
      contract_version: 1;
      event: "job_queued" | "job_running" | "job_succeeded" | "job_failed";
      job_id: number;
      library_id: number | null;
      scope_path: string | null;
      operation: "scan" | "scope_scan" | "rebuild" | "repair";
      updated_at: number; // Unix epoch ms
    }
    ```
- **409 response schema:**
  ```json
  {
    "error": "library_busy",
    "active_job_id": 123,
    "operation": "rebuild",
    "scope_path": "/photos/anime",
    "message": "A rebuild is already running for this library."
  }
  ```
- Permit one active scan, repair, scope-scan, or rebuild operation per library.
  A conflicting request returns `409 library_busy`.
- For safe unregistered paths, persist a job with `library_id=NULL` and detect
  conflicts by overlapping scope paths — treat the path itself as the conflict
  key (after canonicalization) when `library_id` is null.
- **Job creation transaction:** Creating the job row, setting affected
  `assets.metadata_state = pending`, and enqueuing the async worker must happen
  in a single transaction or with recoverable outbox semantics. If the process
  crashes after the DB write but before enqueue, the stale-job recovery
  mechanism catches it.
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
- **Frontend schema guard:** If a status response has an unknown
  `contract_version` or is missing required fields, show a banner
  `App updated, please reload` instead of rendering a broken UI. This protects
  against old tabs hitting a deployed backend.
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
- **Admin list N+1 guard:** The admin libraries page displays all libraries in a
  table. Calling the per-library status endpoint for each library would create
  N+1 network requests. Either (a) add a batch endpoint
  `GET /api/libraries/status` returning status for all libraries, or (b) embed a
  `unified_status_summary` field directly in the library list API response.
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

---

## 7. Review findings and revisions

> Reviewed 2026-06-21. Two independent audits (OpenCode CLI, GPT) informed the
> revisions in this section. All changes above in §1–§6 have already been applied.

### P0 — Incorporated (must fix before implementation)

| # | Finding | Source | Resolution |
|---|---------|--------|------------|
| 1 | `pending_assets` caused double-count — frontend could sum `pending + queued + running + stale` | GPT | Replaced with `not_ready_assets` + explicit `idle_pending_assets` breakdown + UI guard against double-count (§2 Data rules) |
| 2 | Summary-state precedence left `error` blocking retry — failed scan ranked before active scan work | GPT | Reordered: active scan/rebuild jobs (`scanning`) now beat historical failure (`error`). Documented rationale. (§2 Summary-state precedence) |
| 3 | `metadata.disabled` state undefined — no rule for what `summary_state` or progress shows when metadata is off | Both | Added explicit disabled behavior: scan remains unaffected, progress fields `null`, `summary_state` can reach `ready` with secondary indicator. (§3 Metadata disabled behavior) |
| 4 | Path canonicalization underspecified — only said "path-component containment, never raw string prefix" | GPT | Added full rules: trailing slash, `.` and `..`, backslash normalization, drive letter case, filesystem case-sensitivity, symlinks/junctions preserved, UNC paths, Unicode NFC, offline-path fallback. (§3 Scope and path canonicalization) |
| 5 | `total_assets` only mentioned images — videos excluded | OpenCode | Changed to "active **image and video** assets in the scope" (§2 Data rules) |
| 6 | Rebuild destructive — clear then recreate; crash after clear loses data | GPT | Changed to mark-stale-first, delete-after-success pattern. Added crash recovery spec and acceptance test. (§3 Scoped actions) |

### P1 — Incorporated (should fix to avoid production bugs)

| # | Finding | Source | Resolution |
|---|---------|--------|------------|
| 7 | Migration v7→v8 no rollback strategy | OpenCode | Added transactional rollback and manual schema-downgrade procedure. (§3 Database migration) |
| 8 | `library_id=NULL` conflict detection underspecified | OpenCode | Clarified: path itself is conflict key (canonicalized) when `library_id` is null. (§3 Scoped actions) |
| 9 | Rescan/Rebuild idempotency missing | GPT | Added: equivalent active job → 202 with existing `job_id`; conflicting wider/narrower → 409. (§3 Scoped actions) |
| 10 | 409 `library_busy` response schema undefined | GPT | Added full JSON schema with `active_job_id`, `operation`, `scope_path`, `message`. (§3 Scoped actions) |
| 11 | Job creation not transactional — crash-risk between DB write and enqueue | GPT | Added: single transaction or recoverable outbox; stale-job recovery catches partial writes. (§3 Scoped actions) |
| 12 | SSE event payload contract undefined | GPT | Added `StatusInvalidationEvent` interface with `contract_version`, `event`, `job_id`, `library_id`, `scope_path`, `operation`, `updated_at`. (§3 Scoped actions) |
| 13 | Timestamp unit ambiguous — `number` could be seconds or ms | GPT | All public timestamps are **Unix epoch ms UTC**. (§2 Timestamp rules) |
| 14 | Admin list N+1 — 50 libraries = 50 HTTP calls | GPT | Added guard: batch endpoint or embed summary in list API. (§4 Admin libraries) |
| 15 | `latest_issue` selection rule undefined | GPT | Added: greatest `updated_at`; tie-break `scan > availability > metadata`. (§2 Timestamp rules) |
| 16 | No frontend schema guard for breaking API change | GPT | Added: check `contract_version` + required fields → show "App updated, please reload" banner. (§4 Query ownership) |

### P2 — Noted (nice to have, non-blocking)

| # | Finding | Source | Note |
|---|---------|--------|------|
| 17 | Example JSON responses would help frontend implementation | GPT | Add during implementation when building contract tests. |
| 18 | Summary-state matrix for test mapping | GPT | Add alongside acceptance criteria — useful for integration test parameterization. |
| 19 | `repair` operation UI behavior unclear — no badge change, but buttons disabled | GPT | Active repair does not change `summary_state` unless it queues scan or metadata work. UI may show secondary text "Repairing catalog". |
| 20 | `mtime_ns` preferred over `mtime` for cross-filesystem precision | GPT | Future improvement — not required for initial implementation. `mtime + size` is sufficient. |
| 21 | Polling gap without optimistic update | OpenCode | Present plan uses SSE invalidate + 2.5s poll, acceptable for MVP. Optimistic update can be added later. |
