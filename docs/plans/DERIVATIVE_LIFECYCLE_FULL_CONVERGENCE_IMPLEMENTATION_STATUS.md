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

## Audit Follow-up — Eleven Findings

Status: Implemented in the current worktree; final closeout is pending the
required full repository verification and deterministic audit regression suite.

The current implementation addresses the eleven handoff findings as follows:

1. Startup recovery runs before newly started workers can claim jobs, while
   incomplete-stop restarts preserve live claims and restore missing slots.
2. Integrity discovery commits before invoking the singleton scheduler.
3. Quota accounting includes queued/running reservations and only counts
   successful evictions.
4. Metadata completion remains successful when the derivative safety net fails.
5. Eligible current `source_missing`/`asset_inactive` skips are requeued once
   the source is valid; historical identities remain terminal.
6. Admin generated-image state distinguishes on-demand, preparing, attention,
   storage-limited, actionable, and complete outcomes.
7. HTTP derivative outcomes branch on stable result codes.
8. Integrity checks exact configured kind/variant identities, excluding custom
   variants from coverage satisfaction.
9. Manual Generate missing delegates to the common reconciler.
10. Background reconciliation observes stop after the current committed batch.
11. Public catalog exclusion checks normalize POSIX, Windows, and UNC-style
    separators without globally excluding unrelated directories.

Implementation commits: none yet; these changes are currently uncommitted in
the shared worktree and preserve the pre-existing worktree modifications.

Verification completed so far:

```text
backend/.venv_linux/bin/python -m pytest -q \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_integrity_checker.py
47 passed

backend/.venv_linux/bin/python -m pytest -q \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_derivative_lifecycle_phase4.py \
  backend/tests/test_derivative_lifecycle_phase5.py \
  backend/tests/test_catalog_hygiene_phase6.py \
  backend/tests/test_libraries_coverage.py \
  backend/tests/test_api_integration_derivatives.py
152 passed

frontend: typecheck passed; focused generated-image Vitest suites: 35 passed.
ruff: all touched backend files passed.
```

Remaining verification: the eleven dedicated concurrency/outcome regression
scenarios, repository gates, E2E acceptance, performance checks, and
`./test.sh full` have not yet been recorded; Phase 7 therefore remains open.
