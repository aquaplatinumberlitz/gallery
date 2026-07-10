# Derivative Lifecycle Full Convergence — Implementation Status

Status: Active

Last reviewed: 2026-07-10

This is the execution record for
`DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_PLAN.md`. Phases are deliberately
completed in order. A later phase must not change production behavior before
the prior phase's tests and exit criteria are recorded here.

## Phase 0 — Characterization and Contract Lock

Status: Complete

Completed deliverables:

- Added `backend/tests/test_derivative_lifecycle_phase0.py`.
- Recorded the baseline preview-only expected-count gap: status can report two
  expected derivatives while the current preview has neither a row nor a job.
- Recorded the source-change gap: historical variants become terminal while no
  current variant is created.
- Added strict expected-failure contracts for the Phase 1 reconciler, Phase 2
  scan completion and startup catch-up, and Phase 4 quota/request outcomes.
- Added a strict expected-failure frontend contract for a preview-only Admin
  gap becoming actionable in Phase 3.
- Updated `docs/testing/TEST_CATALOG.md` with the characterization suite.

Verification:

```text
backend/.venv_linux/bin/python -m pytest backend/tests/test_derivative_lifecycle_phase0.py -q
2 passed, 5 xfailed

cd frontend && corepack pnpm exec vitest run src/components/admin/__tests__/LibraryDetailPage.test.ts
23 passed, 1 expected fail

cd frontend && corepack pnpm run typecheck
passed
```

Phase 0 exit criteria are met: the baseline gaps are reproducible, desired
contracts are explicit, and no production lifecycle behavior has changed.

## Phase 1 — Scheduler Reconciliation Core

Status: Complete

Completed deliverables:

- Added `DerivativeReconcileSummary` and the scheduler-owned
  `reconcile_desired_derivatives()` entrypoint.
- Enforced one primary scope (`library_id`, `scope_path`, or `asset_ids`) and
  configured-kind validation before writes.
- Reused one transactional insert/coalesce helper from interactive scheduling
  and reconciliation.
- Batched candidate writes, statted sources before the write transaction, and
  retained the existing derivative identity unique constraint as the
  concurrency boundary.
- Covered new rows/jobs, idempotency, ready-file loss, queued-without-job
  repair, and terminal failure behavior.

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_lifecycle_phase0.py \
  backend/tests/test_derivative_scheduler.py -q
22 passed, 4 xfailed

backend/.venv_linux/bin/python -m ruff check \
  backend/derivative_scheduler.py \
  backend/tests/test_derivative_lifecycle_phase0.py \
  backend/tests/test_derivative_scheduler.py
All checks passed
```

Phase 1 exit criteria are met: one active image creates exactly one configured
thumbnail and preview row/job, and the second pass creates no duplicate work.

## Phase 2 — Runtime Producers and Warm Policy

Status: Complete

Completed deliverables:

- Added scan/rebuild completion reconciliation; watcher work uses the same scan
  completion hook.
- Added metadata-completion asset safety-net scheduling.
- Added non-blocking startup catch-up and six-hour configurable periodic
  reconciliation after derivative workers start.
- Made `warm_enabled` a backend create/update API field and persisted policy;
  changing it from off to on reconciles after the settings transaction commits.
- Added periodic reconciliation diagnostics to Maintenance global runtime.

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_lifecycle_phase0.py \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_catalog_trigger_routing.py \
  backend/tests/test_libraries_coverage.py \
  backend/tests/test_maintenance_runtime_api.py \
  backend/tests/test_catalog_status_contract.py -q
131 passed, 2 xfailed

backend/.venv_linux/bin/python -m ruff check backend
All checks passed
```

Phase 2 exit criteria are met: warm-library catalog paths automatically queue
both configured variants, warm-disabled policy blocks automatic work, and
startup/periodic reconciliation can repair an absent-row gap.

## Phase 3 — Status and Admin Truthfulness

Status: Complete

Completed deliverables:

- Extended generated-image status with warm/on-demand policy, convergence,
  desired/actionable/deferred/terminal totals, and per-kind lifecycle counts.
- Made warm-library completion require both configured thumbnail and preview
  coverage; preview-only gaps are visible and actionable.
- Changed the Admin action and toast copy to generated images and retained
  polling only for real queued/running jobs.
- Added the background preparation policy control to the library form and its
  typed create/update payloads.

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_lifecycle_phase0.py \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_libraries_coverage.py -q
90 passed, 2 xfailed

cd frontend && corepack pnpm run typecheck
passed

cd frontend && corepack pnpm exec vitest run \
  src/components/admin/__tests__/LibraryDetailPage.test.ts \
  src/components/admin/dialogs/__tests__/LibraryForm.test.ts \
  src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts \
  src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts
45 passed
```

Phase 3 exit criteria are met. Phase 4 contracts remain strict xfails and have
not been implemented.

## Phase 4 — Integrity, Quota, and Request Lifecycle

Status: Complete

Completed deliverables:

- Added `evicted` and `deferred_capacity` derivative states; quota eviction now
  writes `evicted` and clears cache fields instead of a false `queued` row, so a
  quota eviction never leaves `queued` status without a corresponding job
  (`_enforce_quota`, `_reserve_capacity`).
- Background reconciliation reserves estimated capacity before creating work;
  when capacity cannot be reserved the identity is written as `deferred_capacity`
  with no runnable job. A quota increase, cache clear, or periodic/integrity
  reconciliation reconsiders deferred/evicted work through the same reconciler.
- Replaced derivative HTTP polling with an ID/outcome-based wait: request
  waiters use `get_derivative_outcome(derivative_id)` and branch on
  `ready`/`failed`/`skipped`(source_missing→404, source_changed→reschedule
  once within the timeout budget)/`deferred_capacity`(→507 capacity error)
  without parsing human-readable error text. `ErrorType.CAPACITY_EXCEEDED` added.
- Extended integrity with desired-state checks through the common reconciler:
  `derivative_expected_row_missing` (closes absent current rows),
  `derivative_queued_without_job` (repairs phantom queued states), and
  `derivative_policy_deferred` (reconsiders deferred/evicted work).
- Removed the dead, duplicative `rebuild_stale()` path so no unused lifecycle
  API remains; the reconciler now owns source-change repair.
- Fixed a latent priority-promotion bug in `_coalesce_derivative_job` (the
  `WHERE id` clause was bound to `job["priority"]` instead of `job["id"]`, so
  P0 promotion never persisted).

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_lifecycle_phase0.py \
  backend/tests/test_derivative_lifecycle_phase4.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_libraries_coverage.py \
  backend/tests/test_api_integration_derivatives.py -q
142 passed

backend/.venv_linux/bin/python -m ruff check \
  backend/derivative_scheduler.py backend/integrity_checker.py \
  backend/thumbnails.py backend/errors.py
All checks passed
```

Phase 4 exit criteria are met: integrity closes an absent current preview row
without direct `warm_library()` calls; quota eviction leaves no phantom `queued`
row; source-change request races reschedule the current identity within the
original timeout budget instead of waiting ten seconds for an unrelated 503.

## Phase 5 — Lease, Shutdown, and Worker Resilience

Status: Complete

Completed deliverables:

- Added a fenced lease heartbeat (`_LeaseHeartbeat`) owned by job ID and claim
  token. It renews `lease_expires_at` at most once per
  `GALLERY_DERIVATIVE_LEASE_HEARTBEAT_SECONDS` (clamped to one third of
  `GALLERY_DERIVATIVE_JOB_LEASE_SECONDS`, default 900s) and only updates a row
  that is still `running` with the same claim token.
- The heartbeat starts before the blocking render and stops in `finally` before
  terminal persistence (`done`/`failed`/`skipped`/retry). A failed renewal is
  logged and recorded as `lease_renewal_failures_total`; it never overwrites the
  worker's render outcome.
- A healthy heartbeat keeps a long render from being duplicated by supervisor or
  startup expired-claim recovery.
- Hardened `stop()` to set the stop event, wake workers, join each worker (and
  supervisor/reconciler) with a per-worker bounded
  `GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS` timeout, and record whether
  shutdown completed cleanly (`last_shutdown_clean()`).
- Hardened `start()` to prune stale dead worker thread objects left by an
  incomplete stop before restoring the configured worker count, so a prior
  incomplete stop never permanently refuses to restart; it recovers interrupted
  jobs only on a cold start.
- Added configuration: `GALLERY_DERIVATIVE_JOB_LEASE_SECONDS`,
  `GALLERY_DERIVATIVE_LEASE_HEARTBEAT_SECONDS`,
  `GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS`.
- Documented the lease heartbeat, bounded shutdown, and single-process
  constraint in `docs/ARCHITECTURE.md` and `docs/CONFIGURATION.md`.

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_lifecycle_phase5.py -q
8 passed

backend/.venv_linux/bin/python -m ruff check \
  backend/derivative_scheduler.py backend/config.py \
  backend/tests/test_derivative_lifecycle_phase5.py
All checks passed
```

Phase 5 exit criteria are met: a render longer than the original lease cannot be
duplicated by expired-claim recovery while the heartbeat is healthy, and
stop/start restores the configured worker count without abandoning current jobs
or permanently refusing restart.

## Phase 6 — Catalog Hygiene and Existing-Data Convergence

Status: Complete

Completed deliverables:

- Added repository-specific default excluded index segments
  `frontend/coverage`, `frontend/test-results`, and `frontend/playwright-report`
  to `DEFAULT_INDEX_EXCLUDED_SEGMENTS` in `backend/files.py`.
- The segments are exact `frontend/<segment>` path sequences, not a global ban
  on any directory with those names outside the known repository layout; both
  POSIX and Windows-style (backslash) path normalization are covered by the
  existing `_path_parts`/`_contains_segment`/`_configured_excluded_segments`
  helpers.
- A normal scan reconciles already-indexed matching artifacts to offline
  (inactive) catalog rows without deleting the source files on disk, so they
  no longer contribute to expected or desired derivative coverage.
- Documented the default repository exclusions and per-library exclusion
  override behavior in `docs/CONFIGURATION.md`, including that source files are
  preserved during reconciliation.

Verification:

```text
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_catalog_hygiene_phase6.py -q
11 passed

backend/.venv_linux/bin/python -m ruff check \
  backend/files.py backend/metadata_store/rebuild_store.py \
  backend/tests/test_catalog_hygiene_phase6.py
All checks passed
```

Phase 6 exit criteria are met: `frontend/coverage`, `frontend/test-results`, and
`frontend/playwright-report` cannot re-enter a default gallery-repo library, and
re-running frontend tests no longer changes library 1 expected derivative
coverage because the generated artifacts are excluded and pre-existing artifact
rows are reconciled offline.

## Phase 7 — Verification, Rollout, and Closeout

Status: Not started

## Audit Follow-up — 6366ae9 Re-audit (Five Workstreams)

Status: Implemented and verified against the 6366ae9 re-audit.  Five workstreams
were addressed; repository gates for the changed files pass.  Phase 7 final
closeout (full repository verification, E2E/performance gates) remains open.

The following five workstreams from the 6366ae9 re-audit have been addressed:

### Workstream 1 — Eviction transaction-owned and rollback-safe

Changed `_reserve_capacity` to return eviction plans to the caller instead of
appending to a scheduler-global `_pending_unlinks` list.  The global list and
`_process_pending_unlinks` method were removed.  Callers (`schedule_derivative`,
`reconcile_desired_derivatives`) now receive a local list of evicted files and
call `_unlink_evictions()` after their own transaction commits.  If a rollback
restores evicted rows to `ready`, the caller never unlinks because the plan was
discarded with the rolled-back transaction.

Added `_eviction_lock` to serialize capacity planning, and `_evictions`
parameter to `_coalesce_derivative_job` for threading eviction plans through
the call chain.

### Workstream 2 — Reject partial/insufficient capacity eviction

Added a sufficiency check before committing eviction: `if not evict_ids or
sum(evict_bytes) < needed: return False, []`.  If eligible ready bytes are
insufficient to satisfy the quota equation, no eviction is performed and
`deferred_capacity` is returned for deferrable work.

### Workstream 3 — Route phantom repair by exact derivative identity

Changed `IntegrityChecker.run_all_checks()` to pass derivative IDs from
`_find_queued_without_job` directly to
`scheduler.repair_derivative_consistency()` instead of
`reconcile_desired_derivatives(asset_ids=...)`, fixing the ID-domain confusion
that previously treated derivative IDs as asset IDs with warm-policy filtering.

### Workstream 4 — Make concurrent start/stop linearizable

Added a generation counter (`_generation`, `_start_generation`) to the
scheduler.  `start()` captures the current generation before recovery;
`stop()` increments the generation and sets cancellation events.  After
recovery, `start()` rechecks the generation — if `stop()` ran during
recovery, the generation mismatch causes `start()` to bail out without
creating threads.  `stop()` also waits for an in-progress `start()` to
acknowledge cancellation before reporting clean shutdown.

### Workstream 5 — Acceptance evidence

Added regression tests:

- `test_rollback_after_eviction_does_not_cause_stale_unlink` — force
  rollback after eviction decision; asserts ready rows and cache files are
  preserved (fails if any stale unlink occurs)
- `test_insufficient_eligible_bytes_returns_not_reservable` — need 250 bytes
  with only 100 eligible; asserts `False` return with no eviction
- `TestStartStopLinearizability.test_stop_during_cold_start_launches_no_workers`
  — block recovery, stop, release; asserts zero alive workers
- `TestStartStopLinearizability.test_fresh_start_after_cancelled_generation_works`
  — cancel via stop, then fresh start; asserts exactly one worker

All tests fail on 6366ae9 and pass after the fix.

Verification:

```text
backend/.venv_linux/bin/python -m pytest -q \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_integrity_checker_contract.py \
  backend/tests/test_derivative_lifecycle_phase4.py \
  backend/tests/test_derivative_lifecycle_phase5.py \
  backend/tests/test_maintenance_runtime_api.py \
  backend/tests/test_maintenance_file_health_api.py \
  backend/tests/test_api_integration_derivatives.py
107+ passed

ruff: 2 files checked, all checks passed.
ruff format --check: 2 files already formatted.
```

Implementation commit: pending; changes are in the worktree and preserve
pre-existing modifications (unrelated conflict files are not touched).

Remaining verification: frontend typecheck and Vitest suites, full repository
gates (`backend-api`, `lint`, `docs`, `fast`), E2E/performance checks, and
`./test.sh full`; Phase 7 therefore remains open.

## Audit Follow-up — 8ad509f Re-audit

Status: Implemented and verified in the worktree on 2026-07-10. The corrective
commit is pending. Phase 7 remains open because functional E2E, performance,
and `./test.sh full` were not run in this pass.

### Capacity and eviction finalization

Automatic reconciliation now uses a two-phase capacity protocol under one
scheduler-owned eviction lock. The first scheduling transaction records a
non-runnable `deferred_capacity` target when capacity is needed. A separate
committed transaction moves eligible LRU rows out of `ready` while preserving
their path/size fence; unlink then runs while `_file_lock` excludes serving and
generation. Successful deletes clear catalog file fields, failed deletes restore
the exact ready row, committed capacity is recomputed, and only then may a new
transaction publish the target job. Workers are woken only after that runnable
job commit.

The same two-phase primitive now backs post-render quota enforcement. Worker
completion and capacity reservation are serialized so a completed render cannot
silently replace an estimated reservation while another reconciliation spends
the same bytes. An interrupted eviction that still has its original file is
restored to `ready` on the next exact coalesce instead of orphaning that file.

### Serving and lifecycle linearizability

HTTP derivative lookup now calls `acquire_ready_derivative()`, which holds the
file lock across ready-row/file validation and insertion into `_served_paths`.
There is no lookup-to-protection window in which eviction can remove a file that
is about to be streamed.

`start()` rejects calls that enter while stop is in progress and retains the
request generation captured before waiting behind another start. `stop()` uses
one absolute monotonic deadline for joins and startup acknowledgement, reports
unclean when startup or any lifecycle thread survives the bound, preserves live
references, and releases the stop state only after final bookkeeping. A
cancelled cold start cannot later launch workers; a distinct post-stop start can
restore the configured slots.

### Regression evidence

`backend/tests/test_derivative_scheduler.py` now proves:

- committed evictions cannot be resurrected as `ready` rows pointing to deleted
  files by a later rollback;
- insufficient eligible bytes do no partial eviction;
- unlink failure restores the ready victim and leaves both background and
  interactive targets deferred with no active job;
- a serving-acquired file is not selected for eviction;
- successful capacity finalization removes the real file and coalesces repeated
  scheduling to exactly one active job;
- an interrupted post-commit/pre-unlink eviction restores the original existing
  file to `ready` without adding a job;
- an indefinitely blocked cold start makes bounded stop return unclean without
  launching workers later;
- two pre-stop start callers are cancelled together; a start invoked during stop
  cannot create a replacement slot, while a new explicit post-stop start works.

Validation completed:

```text
backend/.venv_linux/bin/pytest -q backend/tests/test_derivative_scheduler.py
40 passed

Focused derivative/integrity/API regression command
183 passed

./test.sh backend-api
103 passed

./test.sh lint
passed (Ruff, Ruff format check, ESLint, and Prettier)

./test.sh docs
passed (staleness, headers, matrix catalog, and lifecycle ownership)

./test.sh fast
exit 0; backend 992 passed, frontend 1050 passed, frontend coverage thresholds
passed, and the production frontend build completed. The backend coverage tool
reported 89.95%, which is accepted as 90% at the command's configured precision.
```

Implementation baseline: `8ad509f`. Corrective implementation commit: pending;
changes remain in the worktree and preserve unrelated pre-existing modifications.
