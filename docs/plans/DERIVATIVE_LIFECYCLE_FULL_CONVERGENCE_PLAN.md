# Derivative Lifecycle Full Convergence Plan

Status: Proposed

Last reviewed: 2026-07-10

## Summary

Close the remaining end-to-end thumbnail/preview lifecycle gaps exposed by the
`211/211` thumbnail and `207/211` preview production state. The fix must make
configured background warming a durable desired-state policy rather than a
manual API capability, while preserving Gallery's SQLite-first, single-process,
per-kind derivative architecture.

The completed `3da2d865` hardening remains the execution-safety foundation: a
claimed job is fenced, recoverable, and terminal or retryable. This plan adds
the missing layer before job execution: discovering which current derivatives
should exist, creating/coalescing their work, and repeatedly reconciling the
desired state until the library converges or reaches an explicit terminal or
capacity-deferred outcome.

The target contract is:

```text
active current image asset
+ library warm policy enabled
+ configured default derivative variant
=> one current derivative catalog row
=> one active job, ready file, terminal failure, or capacity-deferred outcome
=> no silent expected-count gap with an empty queue
```

## Source Of Truth And Audit Inputs

This is an active implementation plan. Current code, maintained documentation,
and tests remain the runtime source of truth. Archived plans are used only to
explain earlier decisions and contract drift.

Audit inputs:

- Live library 1 reported 211 current thumbnails, 207 current previews, zero
  queued/running/failed current jobs, and three healthy derivative workers.
- The four current preview gaps were generated test-report assets under
  `frontend/coverage/vitest`. Their historical previews were correctly marked
  `skipped/source_changed` after the coverage files were regenerated, but no
  current preview work was created.
- `warm_library(kind=None)` can create both default kinds, but its only
  production caller is the explicit warm API.
- `warm_enabled` exists in the library schema and frontend type but has no
  runtime owner.
- Scan, watcher, metadata completion, startup recovery, periodic integrity, and
  imported-data rebuild do not guarantee current thumbnail and preview work.
- Integrity repair starts from existing derivative/job rows. It cannot detect a
  completely absent current asset-kind-variant row.
- The Admin action is thumbnail-scoped and intentionally disappears when only
  previews are missing.
- Quota eviction currently writes `asset_derivatives.status='queued'` without
  creating a corresponding queued job.
- The HTTP derivative waiter recognizes `failed` but not `skipped`, which can
  turn a controlled lifecycle race into a ten-second timeout and HTTP 503.
- The current default index exclusions omit mutable test-output directories
  such as `frontend/coverage`, `frontend/test-results`, and
  `frontend/playwright-report`.

Historical contract drift to resolve:

- `IMMICH_DT_ADAPTATION_AUDIT_AND_ROADMAP.md` marked background warming after
  metadata completion as implemented.
- `FRONTEND_LIBRARY_HEALTH_GENERATED_FILES_PLAN.md` specified one action that
  queued both thumbnail and preview work.
- `IMMICH_DERIVATIVE_LIFECYCLE_HARDENING.md` later required a
  thumbnail-scoped action and explicitly excluded preview work from that action.
- Current tests prove worker behavior after explicit scheduling, but do not
  prove scan/index-to-derivative convergence.

## Immich Guarantee Being Adapted

The local Immich reference implements convergence through three coupled
mechanisms:

1. A queue-all query selects active assets missing either the thumbnail or
   preview file record.
2. One media-generation job creates and persists thumbnail and preview output
   together for an asset.
3. Import pipeline hooks and a default nightly missing-thumbnail task repeatedly
   create omitted work.

Gallery will adapt the behavioral guarantee without adopting PostgreSQL,
Redis/BullMQ, multiple service processes, or Immich's combined file model.
Gallery may continue using separate `thumbnail` and `preview` derivative rows and
jobs, provided one reconciler owns the full configured desired set.

## Goals

- Make `libraries.warm_enabled` an enforced runtime policy.
- Automatically create both configured default derivatives for new or changed
  active images when warming is enabled.
- Repair current expected derivatives that have no catalog row or no runnable
  job.
- Keep reconciliation idempotent, batched, bounded, and safe under concurrent
  HTTP requests, scans, watcher events, startup catch-up, and manual actions.
- Preserve source-version identity and historical rows without counting them as
  current readiness.
- Make status distinguish potential coverage, desired work, ready work, active
  work, terminal failures, and capacity-deferred work.
- Make Admin completion and actions reflect thumbnail and preview state rather
  than thumbnail state alone.
- Prevent mutable repository test artifacts from repeatedly entering the
  library catalog by default.
- Close the skipped-waiter, quota-without-job, lease-renewal, and scheduler
  stop/start gaps found during the lifecycle audit.
- Add end-to-end acceptance tests that begin with scan/source changes rather
  than direct calls to `warm_library()`.

## Non-Goals

- Do not introduce Redis, BullMQ, Celery, PostgreSQL, or a derivative
  microservice.
- Do not support multiple Uvicorn/Gunicorn backend processes sharing one
  derivative queue. The maintained deployment remains one backend process with
  multiple in-process derivative workers.
- Do not change default thumbnail or preview dimensions, quality, format, cache
  key identity, or PhotoSwipe source policy.
- Do not delete source images or historical derivative rows as part of normal
  reconciliation.
- Do not make gallery browsing wait for full-library warming.
- Do not turn a terminal corrupt/unsupported source into an unbounded retry
  loop.
- Do not regenerate arbitrary compatibility variants requested with custom
  dimensions; desired-state reconciliation covers only configured variants.

## Terminology

| Term | Meaning |
| --- | --- |
| Potential derivative | One active image multiplied by one configured derivative variant. Preserves the existing expected-count concept. |
| Desired derivative | A potential derivative that policy says should be prepared in the background. |
| Current derivative | A derivative whose asset, source mtime, source size, kind, and variant match the current active asset row. |
| Coverage gap | A desired current derivative that is not ready. |
| Actionable gap | A coverage gap that should have work created now. |
| Deferred gap | Desired work intentionally not queued because capacity or policy prevents progress. |
| Converged library | Every desired derivative is ready, actively progressing, terminal with a visible failure, or explicitly deferred; there is no silent absent work. |
| Warm policy | `libraries.warm_enabled=1`; configured default thumbnail and preview variants are desired. |
| On-demand policy | `libraries.warm_enabled=0`; coverage is informational and missing previews are created only by requests or explicit actions. |

## Required Invariants

### Desired-state ownership

1. `DerivativeScheduler` owns configured variant identity and derivative job
   creation.
2. Exactly one public backend entrypoint reconciles desired derivatives. Scan,
   startup, periodic maintenance, metadata completion, and manual APIs call that
   entrypoint rather than duplicating SQL.
3. A warm-enabled active image must not remain without current work for a
   configured variant after a successful reconciliation pass.
4. A warm-disabled library may remain partially cached without being labeled
   incomplete or unhealthy.

### Identity and coalescing

1. Desired identity remains:

   ```text
   asset_id + kind + variant + source_mtime_ns + source_size
   ```

2. The unique derivative constraint remains the database coalescing boundary.
3. Repeated reconciliation must not duplicate derivative rows or active jobs.
4. Interactive P0 scheduling may promote background P3 work but may not create a
   second active render for the same identity.
5. Historical source versions remain terminal history and never satisfy current
   coverage.

### State and job consistency

1. `queued` means a latest queued job exists or is created in the same
   transaction.
2. `running` means a fenced, non-expired claim exists.
3. `ready` means the current cache path exists and is serveable.
4. `failed` is terminal until source identity changes, an explicit retry is
   requested, or a documented retry policy makes it eligible.
5. `skipped` is terminal for the represented source version.
6. Intentional quota eviction must not masquerade as queued work.
7. Every transition that changes both derivative and job state is atomic or
   fenced so a stale worker cannot overwrite a newer claim.

### UI truthfulness

1. `Complete` for a warm-enabled library means both configured thumbnail and
   preview coverage are complete.
2. A preview-only gap is visible and actionable.
3. A warm-disabled library displays `On demand`, not `Complete` or `Missing`.
4. Worker-health warnings depend on actionable gaps, not only thumbnail gaps.
5. Queue polling follows active work; it must not fast-poll forever for terminal
   or capacity-deferred gaps.

## Target Architecture

### 1. Desired derivative reconciler

Add a scheduler-owned API with a stable result type:

```python
reconcile_desired_derivatives(
    *,
    library_id: int | None = None,
    scope_path: str | None = None,
    asset_ids: Sequence[int] | None = None,
    kinds: Sequence[str] | None = None,
    priority: int = 3,
    retry_failed: bool = False,
    reason: str,
) -> DerivativeReconcileSummary
```

Validation rules:

- Exactly one of `library_id`, `scope_path`, or `asset_ids` supplies the primary
  scope. A scope path resolves to its registered library and uses path-boundary
  safe matching.
- Automatic callers return without scheduling when the owning library has
  `warm_enabled=0`.
- Explicit Admin/API callers may override on-demand policy for the requested
  kinds without changing the stored policy.
- `kinds=None` means all configured default kinds.
- Unknown kinds or variants fail before any rows are written.

`DerivativeReconcileSummary` reports bounded counters only:

```text
assets_considered
desired_derivatives
already_ready
already_active
created_derivative_rows
created_jobs
requeued_without_job
terminal_failed
terminal_skipped
deferred_capacity
source_unavailable
```

The summary must not include raw paths in API or metric labels.

### 2. Candidate classification

For each active current image and configured variant, classify one outcome:

| Current state | Reconcile action |
| --- | --- |
| No current derivative row | Create current row and queued job. |
| `ready` with existing file | No-op and count ready. |
| `ready` with missing file | Clear cache fields and create/coalesce queued job. |
| `queued` with latest queued/running job | No-op; promote priority if required. |
| `queued` without active job | Create one queued job in the same transaction. |
| `running` with live fenced lease | No-op and count active. |
| `running` with expired/abandoned claim | Apply existing recovery policy before classification. |
| `failed/invalid_source` for current identity | Keep terminal unless explicit retry is requested. |
| `failed/attempts_exhausted` or `failed/internal_error` | Keep terminal automatically; allow bounded explicit retry. |
| `skipped` for current active identity | Treat as an integrity anomaly; create a fresh job only when current filesystem identity is valid and the skip reason no longer applies. |
| `evicted` | Queue only when capacity policy permits. |
| `deferred_capacity` | Retry only after capacity, quota, policy, or explicit manual state changes. |

The implementation must not resurrect old-version rows. A source change creates
or reuses the row for the new identity.

### 3. Batched scheduling

Do not implement full-library reconciliation as one SQLite transaction per
asset-kind pair.

- Read candidates in deterministic asset-id/kind/variant order.
- Default reconcile batch size: 250 assets, bounded by configuration between 25
  and 2,000.
- Stat source files outside write transactions.
- Insert/coalesce derivative rows and jobs in one short `BEGIN IMMEDIATE`
  transaction per batch.
- Wake workers once per committed batch.
- Yield between background batches so P0 HTTP work remains responsive.
- Reuse the same internal insert/coalesce helper from `schedule_derivative()` so
  interactive and background paths cannot drift.
- A process stop request ends after the current committed batch; already queued
  work remains durable.

### 4. Reconciliation triggers

| Trigger | Scope | Priority | Required behavior |
| --- | --- | ---: | --- |
| Successful whole-library scan/rebuild | Library | P3 | Queue both configured kinds when warm policy is enabled. |
| Successful watcher-scoped scan | Changed scope/assets | P3 | Create current work for newly added or changed active images. |
| Metadata completion | Asset IDs completed in the batch | P3 | Idempotent safety net for paths entering through metadata/index flows. |
| Backend startup catch-up | All warm-enabled libraries | P3 | Repair absent current work left by downtime or older versions. |
| Periodic derivative reconciliation | All warm-enabled libraries, paged | P3 | Immich-style missing-work convergence without relying on user browsing. |
| Imported-data rebuild completion | Rebuilt libraries | P3 | Recreate both variants after derivative data was cleared. |
| Admin Generate missing | Selected library/kinds | P3 | Queue requested missing work even if policy is on-demand. |
| HTTP thumbnail/preview miss | One asset/kind/variant | P0 | Preserve interactive generation and priority promotion. |

Automatic trigger ownership:

- Catalog scan completion schedules reconciliation only after asset reconciliation
  commits successfully.
- Watcher events continue to queue catalog scans; the scan completion hook owns
  derivative reconciliation so watcher and manual scan cannot diverge.
- Metadata completion supplies an idempotent safety net, not a second rendering
  pipeline.
- Startup catch-up is queued after schema initialization and derivative worker
  startup; it must not block FastAPI readiness.
- Periodic reconciliation uses a dedicated interval and must not perform a full
  scan every supervisor tick.

New configuration:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `GALLERY_DERIVATIVE_RECONCILE_ENABLED` | `true` | Enable startup, scan-completion, and periodic desired-state reconciliation. |
| `GALLERY_DERIVATIVE_RECONCILE_INTERVAL_SECONDS` | `21600` | Six-hour catch-up interval; minimum 300 seconds. |
| `GALLERY_DERIVATIVE_RECONCILE_BATCH_SIZE` | `250` | Assets classified per background batch. |
| `GALLERY_DERIVATIVE_RECONCILE_YIELD_SECONDS` | `0.02` | Cooperative pause between background batches. |

### 5. Warm policy lifecycle

Make `libraries.warm_enabled` a real product setting.

- Registration keeps the current default `1`.
- Library create/update DTOs accept `warm_enabled` using a boolean API shape.
- Admin forms expose a user-facing `Prepare generated images in background`
  toggle with concise storage/CPU copy.
- Turning the policy on queues a library reconciliation after the settings
  transaction commits.
- Turning it off prevents new automatic warm work but does not cancel running
  jobs, delete cache files, or disable interactive generation.
- Manual `Generate missing` remains available when policy is off.
- The API returns the effective warm policy in generated-image status.

### 6. Status contract

Extend `GET /api/derivatives/status?library_id=...` without removing existing
fields:

```json
{
  "library_id": 1,
  "warm_enabled": true,
  "policy": "warm",
  "converged": false,
  "total_assets": 211,
  "ready_derivatives": 418,
  "expected_derivatives": 422,
  "desired_derivatives": 422,
  "actionable_missing_derivatives": 4,
  "deferred_derivatives": 0,
  "terminal_failed_derivatives": 0,
  "by_kind": {
    "thumbnail": {
      "ready_derivatives": 211,
      "expected_derivatives": 211,
      "desired_derivatives": 211,
      "missing_derivatives": 0,
      "queued_derivatives": 0,
      "running_derivatives": 0,
      "failed_derivatives": 0,
      "deferred_derivatives": 0
    },
    "preview": {
      "ready_derivatives": 207,
      "expected_derivatives": 211,
      "desired_derivatives": 211,
      "missing_derivatives": 4,
      "queued_derivatives": 0,
      "running_derivatives": 0,
      "failed_derivatives": 0,
      "deferred_derivatives": 0
    }
  }
}
```

Semantics:

- `expected_derivatives` remains active assets multiplied by configured variants
  for backward compatibility.
- `desired_derivatives` equals expected for warm policy and zero for automatic
  work under on-demand policy.
- `actionable_missing_derivatives` counts desired current variants that are
  absent, have a missing ready file, or are queued without runnable work.
- `converged` is true only when no desired variant is silently absent or
  inconsistent. Terminal failures and deferred capacity remain visible even
  when no jobs are active.
- Job counts continue to describe actual latest current jobs, not mathematical
  expectations or historical versions.

### 7. Admin Generated Images behavior

Replace thumbnail-only completion logic with policy-aware generated-image state.

- Preserve separate Thumbnail and Preview coverage rows.
- Show per-kind missing/active/failed/deferred detail.
- Warm policy states:
  - `Complete`: both configured kinds ready.
  - `Preparing`: queued or running desired work exists.
  - `Needs generation`: actionable gaps exist with no active work.
  - `Needs attention`: terminal failures or unhealthy workers block progress.
  - `Storage limited`: work is deferred by quota.
- On-demand policy state: `On demand`, with cached coverage shown as
  informational.
- Replace `Build missing thumbnails` with `Generate missing images`, calling warm
  without a kind.
- Add optional row actions `Generate thumbnails` and `Generate previews` only if
  the existing compact card can preserve clear hierarchy.
- Worker warning depends on actionable desired gaps plus `worker_healthy=false`.
- Success/error toast copy uses `generated images`, not backend terms.
- Query polling remains active only for queued/running work. Scan completion,
  mutation success, SSE/job completion, and library setting changes invalidate
  the status query so a non-active gap does not remain stale in the UI.

### 8. Integrity and periodic repair

Expand integrity from existing-row repair to desired-state consistency.

New checks and result counters:

```text
derivative_expected_row_missing
derivative_queued_without_job
derivative_ready_no_file
derivative_abandoned_jobs
derivative_done_not_ready
derivative_policy_deferred
```

Rules:

- Candidate discovery may run while holding a read transaction, but filesystem
  stat and scheduler calls run outside the integrity checker's write lock.
- The checker calls the same reconciler used by scan/startup; it does not insert
  derivative/job rows with duplicate SQL.
- Current invalid sources remain terminal and visible instead of being retried
  every interval.
- Repair summaries distinguish created, requeued, skipped, failed, deferred,
  and unchanged outcomes.
- Periodic reconciliation persists a bounded run summary for Maintenance without
  storing raw per-asset path lists.

### 9. Quota lifecycle

Remove the false `queued` state produced by eviction without a job.

- Add derivative states `evicted` and `deferred_capacity`; no schema migration is
  required because status is stored as text, but schema fixtures, models,
  maintained docs, and tests must enumerate them.
- LRU eviction deletes the file and writes `evicted`, clears cache fields, and
  records a bounded reason.
- An evicted derivative is not automatically requeued when doing so would
  immediately exceed quota.
- Before background generation, reserve estimated capacity using the best
  available historical size or a bounded conservative estimate.
- When capacity cannot be reserved after eligible eviction, write
  `deferred_capacity` and do not create an active job.
- Interactive P0 requests may generate after enforcing quota and evicting
  eligible files, but must not exceed the configured quota without recording a
  diagnostic.
- A quota increase, cache clear, explicit generate action, or periodic
  reconciliation reconsiders deferred work.

### 10. HTTP derivative wait lifecycle

Wait on the scheduled derivative ID and its latest fenced job outcome rather
than repeatedly resolving only by the current source identity.

- Add a bounded scheduler read model containing derivative ID, derivative state,
  latest job state, result code, error, and whether the identity is still
  current.
- `ready` returns the generated file.
- `failed/invalid_source` returns HTTP 400 with the existing invalid-file shape.
- `skipped/source_missing` or `skipped/asset_inactive` returns HTTP 404.
- `skipped/source_changed` re-resolves and schedules the new current identity at
  most once for the request, then continues waiting within the original total
  timeout budget.
- `deferred_capacity` returns HTTP 507 with a stable generated-image capacity
  error type.
- A genuine timeout remains HTTP 503 and includes a bounded server diagnostic.
- No branch parses human-readable error text to decide behavior.

### 11. Lease renewal and scheduler shutdown

Keep claim fencing and add lifecycle guarantees for long-running renders and
in-process restart.

- A claimed render starts a lightweight lease heartbeat owned by job ID and
  claim token.
- Heartbeat interval is at most one third of the lease duration and updates only
  a still-running row with the same token.
- Heartbeat stops in `finally` before terminal persistence completes.
- A failed heartbeat does not overwrite render outcome; it logs and lets fenced
  recovery arbitrate.
- `stop()` stops new claims, wakes all workers, waits a bounded timeout per
  worker, and records whether shutdown completed cleanly.
- `start()` may recover after a prior incomplete stop once surviving old workers
  have exited; it must not permanently refuse to restore missing slots because
  one stale thread object remains in `_threads`.
- Tests use short configurable leases/heartbeat intervals without sleeping for
  production durations.

### 12. Catalog hygiene

Add repository-specific default excluded segments:

```text
frontend/coverage
frontend/test-results
frontend/playwright-report
```

Behavior:

- Existing per-library exclusion patterns continue to apply.
- A normal scan after upgrade reconciles already indexed matching artifacts to
  offline/inactive catalog rows without deleting source files.
- Excluded assets do not contribute to expected/desired derivative counts.
- Default exclusions are path segments, not a global ban on every directory
  named `coverage`, `test-results`, or `playwright-report` outside the known
  repository layout.
- Tests cover POSIX and Windows-style path normalization.

## Implementation Phases

### Phase 0: Characterization and contract lock

Deliverables:

- Add a deterministic fixture reproducing current thumbnail-complete,
  preview-current-row-missing, queue-empty state.
- Add a source-change fixture with historical ready derivatives becoming
  `skipped/source_changed` and no current preview work.
- Add failing tests for scan completion, watcher source change, imported-data
  rebuild, startup catch-up, quota eviction, skipped HTTP wait, and preview-only
  Admin actionability.
- Record the policy/state/API additions in backend fixtures and frontend JSON
  schema before implementation.
- Update `docs/testing/TEST_CATALOG.md` with the new guarantees.

Exit criteria:

- Tests demonstrate that current code can report expected preview gaps with no
  rows/jobs and that no automatic production caller closes them.
- The exact warm/on-demand semantics and new state names are fixed before
  scheduler changes begin.

### Phase 1: Scheduler reconciliation core

Deliverables:

- Add desired candidate classification and batched insert/coalesce helpers.
- Implement `reconcile_desired_derivatives()` and summary typing.
- Make `schedule_derivative()` reuse the same transaction helper.
- Repair queued-without-job and ready-without-file states idempotently.
- Add current source/version, active asset, configured variant, and explicit
  retry guards.
- Add scheduler unit tests for every candidate classification row.

Exit criteria:

- Reconciliation of one new active image creates exactly one thumbnail row/job
  and one preview row/job.
- Running reconciliation twice produces no duplicate current rows/jobs.
- Interactive promotion and existing claim fencing tests remain green.

### Phase 2: Runtime producers and warm policy

Deliverables:

- Wire library create/update DTOs and persistence to `warm_enabled`.
- Add scan/rebuild completion reconciliation.
- Make watcher-driven scans use the same completion hook.
- Add metadata-completion asset safety-net scheduling.
- Add non-blocking startup catch-up and six-hour periodic reconciliation.
- Make imported-data rebuild completion enqueue both configured variants.
- Add lifecycle status for the periodic reconciler to Maintenance runtime.

Exit criteria:

- New and changed warm-library assets automatically receive both current jobs
  without gallery/lightbox requests.
- Warm-disabled libraries receive no automatic jobs.
- Startup and periodic passes close an intentionally seeded absent-row gap.

### Phase 3: Status and Admin truthfulness

Deliverables:

- Extend generated-image status fields and per-kind counters.
- Add policy-aware `converged` and actionable/deferred/terminal counts.
- Replace thumbnail-only Admin completion/action logic.
- Expose and persist the background preparation toggle.
- Update polling, invalidation, toasts, tests, fixtures, and schemas.
- Remove tests that require preview-only gaps to remain actionless and replace
  them with full generated-image behavior tests.

Exit criteria:

- A 211/207 warm library displays `Needs generation`, four missing previews, and
  an action that queues preview work.
- A 211/211 warm library displays `Complete`.
- A partially cached warm-disabled library displays `On demand`.

### Phase 4: Integrity, quota, and request lifecycle

Deliverables:

- Add missing-row and queued-without-job integrity checks through the common
  reconciler.
- Add `evicted` and `deferred_capacity` semantics.
- Add background capacity reservation and no-thrash retry rules.
- Replace derivative HTTP polling with ID/outcome-based waiting and controlled
  skipped/deferred responses.
- Wire or remove the currently unused `rebuild_stale()` path so no dead lifecycle
  API remains.

Exit criteria:

- Integrity closes a missing current preview row without direct test calls to
  `warm_library()`.
- Quota eviction never leaves `queued` status without a job.
- Source-change request races do not wait ten seconds and return an unrelated
  503.

### Phase 5: Lease, shutdown, and worker resilience

Deliverables:

- Add fenced lease heartbeat.
- Harden stop/start thread bookkeeping and supervisor restoration.
- Add deterministic long-render lease and incomplete-stop tests.
- Preserve single-process deployment constraints in maintained docs.

Exit criteria:

- A render longer than the original lease cannot be duplicated by expired-claim
  recovery while heartbeat remains healthy.
- Stop/start restores the configured worker count without abandoning current
  jobs or permanently refusing restart.

### Phase 6: Catalog hygiene and existing-data convergence

Deliverables:

- Add default repository test-artifact exclusions.
- Add scan reconciliation tests for existing indexed artifacts.
- Run a normal scoped/library scan in the isolated acceptance fixture and prove
  excluded artifacts leave active coverage counts.
- Document per-library exclusion overrides and source-file preservation.

Exit criteria:

- `frontend/coverage`, `frontend/test-results`, and
  `frontend/playwright-report` cannot re-enter a default gallery-repo library.
- Re-running frontend tests no longer changes library 1 expected derivative
  coverage.

### Phase 7: Verification, rollout, and closeout

Deliverables:

- Run the full backend derivative/integrity/catalog/API suites.
- Run frontend generated-image, library form, status contract, and maintenance
  suites.
- Run functional E2E for scan-to-both-derivatives and source-change convergence.
- Run deterministic perf tests for reconcile batching and interactive P0
  responsiveness during a large P3 warm.
- Update maintained Architecture, Configuration, README, Third-Party Libraries
  if integration roles change, testing docs, fixtures, and test catalog.
- Add an implementation status document with actual commands/results and archive
  this plan only after every Definition of Done item is verified.

Exit criteria:

- Feature defaults are enabled after verification.
- No maintained document claims background warming without a production call
  path and acceptance test.

## Expected File Impact

| Area | Expected files |
| --- | --- |
| Scheduler/reconciler | `backend/derivative_scheduler.py`, optional focused helper under `backend/derivatives/` only if the scheduler would otherwise become unreviewable |
| Configuration | `backend/config.py`, `docs/CONFIGURATION.md` |
| Catalog triggers | `backend/scan_worker.py`, `backend/indexer.py`, relevant `backend/metadata_store/` completion helpers |
| Startup/runtime | `backend/app.py`, `backend/metadata_store/status_store.py`, `backend/maintenance.py` |
| Integrity | `backend/integrity_checker.py`, maintenance file-health fixtures/models |
| Serving | `backend/thumbnails.py`, `backend/errors.py` or existing error enum/model location |
| Library policy/API | `backend/libraries.py`, `backend/metadata_store/library_store.py`, shared request/response models |
| Catalog exclusions | `backend/files.py`, scan/catalog tests |
| Admin UI | `frontend/src/components/admin/LibraryDetailPage.vue`, library form/dialog components |
| Frontend data/contracts | `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, generated-image composables, query keys/polling, JSON schemas/fixtures |
| Tests | derivative scheduler, integrity, libraries coverage, scan worker, watcher, imported-data maintenance, app startup, frontend admin/composable/contract tests, relevant Playwright specs |
| Maintained docs | `README.md`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`, `docs/testing/README.md`, `docs/testing/TEST_CATALOG.md`, `docs/plans/README.md` |

## Test Matrix

### Reconciler unit tests

1. New current asset with no derivative rows creates both configured rows/jobs.
2. Second pass is a no-op apart from counters.
3. Current ready files remain untouched.
4. Current ready row with a deleted cache file queues one replacement job.
5. Current queued row without an active job receives one job.
6. Current queued/running row with an active latest job is not duplicated.
7. Failed invalid source is not automatically retried.
8. Explicit retry creates one bounded new job for an eligible failed current row.
9. Historical source versions never satisfy or block current scheduling.
10. Offline, deleted, excluded, video, and missing-source assets are omitted.
11. Kind-scoped manual reconciliation creates only the requested configured kind.
12. Background warm respects `warm_enabled=0`; explicit manual generation may
    override it.
13. Concurrent reconcile and HTTP scheduling coalesce to one active job.
14. Scoped path reconciliation cannot escape its registered import root.

### Pipeline integration tests

1. Register and scan a warm library; both configured derivatives become queued
   and then ready.
2. Modify an indexed image; old rows become historical/skipped and current rows
   for both kinds are created.
3. Watcher modification follows the same scan completion path.
4. Imported-data rebuild clears generated data, rebuilds assets, and prepares
   both kinds.
5. Startup catch-up repairs a current preview row intentionally removed before
   process startup.
6. Periodic reconciliation repairs an absent row introduced after startup.
7. Warm-disabled scan produces no automatic derivatives but interactive routes
   still work.
8. Policy transition off-to-on queues desired work after settings commit.
9. Policy transition on-to-off leaves existing queued/running/cache state intact.

### Integrity and quota tests

1. Missing current derivative row is counted and repaired.
2. Queued derivative without a job is counted and repaired.
3. Ready derivative without a file retains existing active/current guards.
4. Abandoned claims retain fencing and attempt limits.
5. Eviction writes `evicted`, not `queued`.
6. Insufficient capacity writes `deferred_capacity` without a runnable job.
7. Quota increase allows deferred work to become queued.
8. Periodic reconciliation does not thrash terminal invalid or deferred work.

### HTTP tests

1. Interactive miss schedules P0 and waits on derivative ID.
2. Ready outcome returns the expected media and headers.
3. Invalid source returns HTTP 400.
4. Missing/inactive source returns HTTP 404.
5. One source-change race reschedules the current identity within the original
   timeout budget.
6. Capacity deferral returns HTTP 507 with a stable error type.
7. Genuine worker timeout returns HTTP 503.
8. Thumbnail and preview cache keys and variants remain separated.

### Worker lifecycle tests

1. Lease heartbeat prevents premature expired-claim recovery.
2. Obsolete heartbeat token updates zero rows.
3. Heartbeat cleanup runs on done, skipped, failed, retry, and unexpected errors.
4. Stop while rendering prevents new claims and preserves durable state.
5. Start after incomplete stop restores configured slots when old threads exit.
6. Supervisor and startup recovery remain idempotent.

### Frontend tests

1. Separate thumbnail/preview coverage renders with per-kind gaps.
2. Preview-only gap displays an actionable generate control.
3. Generate missing calls warm without `kind`.
4. Per-kind action, if retained, sends the selected kind.
5. Warm complete requires both configured kinds.
6. On-demand policy displays informational coverage without a false warning.
7. Active jobs poll; terminal/deferred gaps do not fast-poll forever.
8. Worker warning uses actionable desired gaps.
9. Library form persists the background preparation toggle.
10. Backend/frontend generated-image JSON contracts accept the extended shape
    and reject missing required lifecycle fields.

### End-to-end regression

Use a deterministic registered library containing normal images plus mutable
test-output fixtures:

1. Scan with warm policy enabled.
2. Wait for both kinds to reach full ready coverage.
3. Regenerate one included normal source and create excluded coverage artifacts.
4. Let watcher/catalog reconciliation run.
5. Assert the normal source receives current thumbnail and preview work.
6. Assert excluded artifacts do not become active assets.
7. Assert workers remain healthy and no current job is stranded.
8. Assert Admin reaches `Complete` only after both kinds are ready.

## Performance And Resource Budgets

- Reconcile candidate discovery for 5,000 active images and two variants: warm
  SQLite p95 at or below 250 ms before filesystem validation.
- Reconcile write transaction: p95 at or below 100 ms per 250-asset batch on the
  documented reference fixture.
- Startup HTTP health/readiness must not wait for full reconciliation.
- P0 interactive job start p95 must remain within the existing derivative queue
  performance budget while P3 full-library work is queued.
- Reconciliation must not open/decode source images; rendering remains worker
  work.
- No raw path or asset ID appears in metric labels.
- Periodic reconciliation must not create jobs for already-ready current
  derivatives.
- Warm-disabled libraries must incur no periodic filesystem stat/render load
  beyond bounded status/integrity reads.

## Observability

Add bounded metrics and runtime counters:

```text
gallery_derivative_reconcile_runs_total{trigger,status}
gallery_derivative_reconcile_candidates_total{kind,outcome}
gallery_derivative_reconcile_duration_seconds{trigger}
gallery_derivative_reconcile_jobs_created_total{kind,trigger}
gallery_derivative_policy_libraries{policy}
gallery_derivative_deferred_total{kind,reason}
gallery_derivative_lease_renewal_failures_total
```

Maintenance runtime should report:

```text
derivative_reconcile_enabled
derivative_reconcile_running
derivative_last_reconcile_started_at
derivative_last_reconcile_completed_at
derivative_last_reconcile_status
derivative_last_reconcile_created_jobs
derivative_actionable_gaps
derivative_deferred_capacity
```

## Migration And Rollout

### Data compatibility

- Existing derivative and job rows remain valid.
- New textual derivative states require no destructive schema migration.
- Additive response fields preserve existing API fields during rollout.
- Existing libraries retain `warm_enabled=1`; startup reconciliation therefore
  queues missing configured work after the feature is enabled.
- Historical failed/skipped jobs remain history and are excluded from current
  status unless their derivative identity is current.

### Rollout sequence

1. Land Phase 0 tests and response fixtures with implementation flags disabled
   in production defaults only for the characterization commit.
2. Land reconciler and manual Admin action; validate idempotency against an
   isolated copy of the current catalog.
3. Enable scan-completion and startup catch-up with bounded batches.
4. Enable periodic reconciliation after startup/scan metrics show no queue or
   SQLite contention regression.
5. Enable capacity-deferred semantics and lease heartbeat.
6. Add default test-artifact exclusions and run normal catalog reconciliation.
7. Make the final documented defaults active and remove temporary rollout-only
   compatibility branches.

### Rollback

- Set `GALLERY_DERIVATIVE_RECONCILE_ENABLED=false` to stop automatic producers.
- Existing manual warm and interactive generation remain available.
- Do not delete newly created ready files or catalog rows during rollback.
- Reverting Admin policy-aware rendering must preserve additive API fields until
  all deployed frontend clients are compatible.
- `evicted` and `deferred_capacity` rows remain safe non-ready states; older code
  must not interpret unknown states as ready.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Full warming spikes CPU/disk after upgrade | P3 priority, bounded batches, cooperative yield, startup non-blocking, per-library policy toggle. |
| SQLite write contention | Batch inserts, short transactions, one wake per batch, existing WAL/busy retry policy. |
| Periodic invalid-source retry loop | Result-code-aware terminal classification and explicit retry controls. |
| Quota eviction/reconciliation thrash | `evicted`/`deferred_capacity` states and retry only after capacity/policy change. |
| Scan latency regression | Enqueue after scan commit; never render or wait inside scan completion. |
| Duplicate render from concurrent triggers | Unique derivative identity, latest active-job coalescing, claim token fencing. |
| Large startup backlog delays service | Background catch-up after readiness, configurable batches/yield, no startup wait. |
| UI calls a global warm unintentionally | Library-scoped API requirement and contract tests. |
| Default exclusions hide legitimate user content | Restrict exclusions to repository-specific path segments and retain explicit per-library patterns. |
| Lease heartbeat introduces thread leaks | Fenced heartbeat lifecycle, `finally` cleanup, deterministic stop/start tests. |
| Archived docs again overstate completion | Maintained docs plus scan-to-convergence acceptance tests are required before archival. |

## Verification Commands

Run focused checks during implementation:

```bash
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_libraries_coverage.py \
  backend/tests/test_scan_worker.py \
  backend/tests/test_watcher.py \
  backend/tests/test_imported_data_maintenance_api.py \
  backend/tests/test_api_integration_derivatives.py

cd frontend
corepack pnpm exec vitest run \
  src/components/admin/__tests__/LibraryDetailPage.test.ts \
  src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts \
  src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts \
  src/services/__tests__/api.test.ts
cd ..

./test.sh backend-api
./test.sh lint
./test.sh docs
./test.sh fast
```

Run the dedicated scan-to-derivative and library-management Playwright specs,
then run `./test.sh full` before final closeout.

## Definition Of Done

- A warm-enabled new asset automatically gets current configured thumbnail and
  preview jobs without being browsed or opened.
- A source-version change automatically creates both current variants and leaves
  old rows as non-current history.
- An expected current variant cannot remain absent with zero work after startup,
  scan completion, periodic reconciliation, or a successful manual generate
  action.
- `warm_enabled` changes runtime behavior and is represented truthfully in the
  API and Admin UI.
- Preview-only gaps are visible and actionable.
- `Complete` requires both configured kinds under warm policy.
- On-demand policy is not mislabeled incomplete.
- Integrity detects absent rows and queued-without-job inconsistencies.
- Quota eviction never creates a phantom queued state.
- Deferred capacity is explicit and cannot hot-loop.
- HTTP requests map ready, failed, skipped, source-changed, deferred, and timeout
  outcomes without parsing error strings or waiting unnecessarily.
- Long-running claims renew leases; stop/start restores worker capacity safely.
- Mutable frontend test artifacts are excluded from the gallery-repo library by
  default and no longer change derivative expectations.
- End-to-end tests begin with scan/source mutation and prove both-kind
  convergence.
- Focused backend/frontend suites, API contracts, E2E, lint, docs, fast, and full
  release validation pass.
- Maintained docs describe actual trigger ownership, policy semantics, status
  fields, quota states, and single-process constraints.
- An implementation-status document records actual commits and verification
  evidence before this plan moves to `docs/archived/`.

