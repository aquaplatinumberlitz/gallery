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

Status: Not started

## Phase 5 — Lease, Shutdown, and Worker Resilience

Status: Not started

## Phase 6 — Catalog Hygiene and Existing-Data Convergence

Status: Not started

## Phase 7 — Verification, Rollout, and Closeout

Status: Not started
