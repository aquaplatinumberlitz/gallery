# Derivative Lifecycle Audit Fix — OpenCode Handoff Prompt

Status: Active

Last reviewed: 2026-07-10

## Purpose

This document is a copy-ready implementation prompt for fixing the eleven
findings discovered while auditing these derivative-lifecycle commits:

- `f9d8eae6c7fe7ec69ecabf5436ab8080197e8aad`
- `2297cb1c847327cf59e3fa1fd975d177b2b9a4ec`
- `a40e3765dd55e951e15412b1052ccf4470f3e797`
- `46a4ea6e047959006a7cff457b2137be76aafae2`

The fixes are follow-up work for
`DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_PLAN.md`. They do not constitute Phase 7
verification or authorize archiving the convergence plan.

## Copy-Ready Prompt

```text
You are working in /home/ubuntu/gallery-repo.

Your task is to fix all eleven findings from the audit of the derivative
lifecycle convergence implementation. Work until the code, regression tests,
maintained documentation, and implementation-status evidence are consistent.
Do not stop after making the existing tests pass: several existing tests pass
while the audited failure modes remain reproducible.

READ FIRST, IN THIS ORDER

1. AGENTS.md
2. README.md
3. docs/README.md
4. docs/ARCHITECTURE.md, especially Metadata Lifecycle, Derivative Lifecycle,
   runtime ownership, and frontend state ownership
5. docs/CONFIGURATION.md
6. docs/testing/README.md
7. docs/testing/TEST_CATALOG.md
8. docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_PLAN.md
9. docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_IMPLEMENTATION_STATUS.md
10. docs/plans/DERIVATIVE_LIFECYCLE_AUDIT_FIX_HANDOFF_PROMPT.md

REPOSITORY AND SCOPE RULES

- Inspect `git status` before editing. The worktree may already contain user
  changes. Preserve all unrelated and overlapping user work; never reset,
  checkout, stash, or revert it.
- Use current code and maintained docs as source of truth. Use the audited
  commits only to understand when a regression was introduced.
- Keep the existing SQLite-first, one-backend-process architecture. Do not add
  Redis, Celery, BullMQ, PostgreSQL, another service process, or a new runtime
  dependency.
- Keep separate thumbnail and preview derivative identities and configured
  variants. Do not change dimensions, quality, format, cache-key identity,
  PhotoSwipe source policy, or source-file preservation.
- Preserve claim-token fencing and the invariant that one current derivative
  identity has at most one active job/render.
- Use the existing global scheduler/runtime owners. Do not create throwaway
  `DerivativeScheduler()` instances in production repair paths when workers,
  wake events, quota configuration, or runtime counters belong to the singleton.
- Do not update implementation status to claim success until every required
  regression test and verification command has actually passed.
- Add tests before or together with each fix. Every audited reproduction below
  must fail against the audited implementation and pass after the fix.

GLOBAL INVARIANTS THAT ALL FIXES MUST PRESERVE

1. Desired identity is exactly:

       asset_id + kind + variant + source_mtime_ns + source_size

2. `queued` always has a latest queued/running job created atomically with the
   row transition.
3. `running` always has a live fenced claim; a stale worker cannot commit after
   recovery changes its token.
4. `ready` means its cache file exists and can be served.
5. `failed`, `skipped`, `evicted`, and `deferred_capacity` remain distinct,
   result-code-aware outcomes.
6. Automatic warm work respects `libraries.warm_enabled`; explicit manual
   generation may override that policy without changing the stored setting.
7. One scheduler-owned reconciliation path performs configured desired-state
   classification and job coalescing for startup, scan, metadata, integrity,
   periodic, and manual producers.
8. Filesystem stat/render/delete work must not occur while an unrelated long
   SQLite write transaction is held.
9. A stop request completes the current committed reconciliation batch and does
   not begin another batch.
10. UI labels must describe actual lifecycle state, not infer readiness from an
    actionable-gap count.

IMPLEMENT THE FIXES IN THE ORDER BELOW

## Fix 1 — Prevent startup recovery from reclaiming newly claimed jobs

Severity: P1
Introduced by: `a40e376`
Primary file: `backend/derivative_scheduler.py`

Current failure:

- `start()` starts replacement workers, supervisor, and reconciler first.
- On a cold start it then calls `_recover_running_jobs()` with no owner or
  expiry restriction.
- A new worker can claim a durable queued job in the interval between those
  steps. Startup recovery then treats that new claim as abandoned, clears its
  token, and requeues it. A second worker can claim the same derivative while
  the first worker is already rendering.

Required behavior:

- On a genuine cold start, initialize the database, reconcile stale queued
  work, and recover pre-existing running claims before any new derivative
  worker, supervisor, or reconciler thread can claim or recover jobs.
- Preserve incomplete-stop restart behavior: if old workers are still alive,
  do not globally recover their live claims. Prune dead thread objects and add
  only missing worker slots.
- Make concurrent/repeated `start()` calls idempotent. Do not create duplicate
  supervisors, reconcilers, or worker slot names.
- Do not hold `_lifecycle_lock` across operations that can deadlock with a
  worker needing that lock. If a two-phase start is needed, add an explicit
  lifecycle state guarded by the lock so two callers cannot both perform cold
  startup.
- Start background desired-state reconciliation only after workers and startup
  recovery are in a consistent state.

Required regression tests:

- Seed one queued derivative before `start()`. Force the first new worker to
  claim and block in render. Assert startup recovery does not transition that
  claim, the claim token remains unchanged, attempts remain one, and only one
  render occurs.
- Seed one abandoned running claim from a prior process. Assert cold startup
  recovers it before a new worker claims it.
- Repeat the incomplete-stop restart test with a surviving live worker and a
  missing slot. Assert no live claim is recovered and configured capacity is
  restored without duplicate rendering.
- Call `start()` concurrently or twice and assert exactly the configured number
  of worker slots plus one supervisor and at most one reconciler exist.

## Fix 2 — Remove nested integrity write transactions and self-locking

Severity: P1
Introduced by: `2297cb1`
Primary files:

- `backend/integrity_checker.py`
- `backend/derivative_scheduler.py` if a focused reconcile input/result helper
  is required

Current failure:

- `run_all_checks()` holds `_DB_LOCK` and one `_connect()` context across all
  checks.
- Earlier checks can write repairs into that transaction.
- `_check_derivative_expected_row_missing()`,
  `_check_derivative_queued_without_job()`, and
  `_check_derivative_policy_deferred()` call a new scheduler/reconciler that
  opens another connection and executes `BEGIN IMMEDIATE`.
- The process blocks on its own uncommitted write and returns
  `database is locked`.

Required behavior:

- Split integrity work into bounded phases:
  1. read/classify candidates and perform only repairs owned by the current
     connection;
  2. commit and release `_DB_LOCK`/the connection;
  3. perform filesystem validation and scheduler reconciliation outside that
     write transaction;
  4. combine discovered-issue and actual-repair counters truthfully.
- Never invoke `reconcile_desired_derivatives()` while an integrity connection
  with pending writes is open.
- Use the runtime scheduler singleton for repair work so the correct quota,
  worker wake event, and diagnostics are used.
- Preserve bounded summaries and do not persist raw paths or asset IDs in
  maintenance results.
- A failure in one reconciliation scope should be reported without discarding
  already committed, correctly counted repairs from unrelated checks.

Required regression tests:

- In one integrity run, seed a `ready` derivative whose cache file is missing
  and also omit the configured preview row. Assert the run finishes `ok`, the
  missing file is repaired/requeued, the preview identity is created or
  capacity-deferred, and no `database is locked` error occurs.
- Combine queued-without-job and deferred/evicted candidates in the same run.
  Assert both use the common reconciler after the integrity transaction closes.
- Assert the persisted integrity summary distinguishes issues found from work
  actually repaired, requeued, deferred, skipped, failed, or unchanged.

## Fix 3 — Make quota reservations cumulative, transactional, and no-thrash

Severity: P1
Introduced by: `2297cb1`
Primary files:

- `backend/derivative_scheduler.py`
- schema/store code only if a durable reservation field is genuinely needed

Current failure:

- `_reserve_capacity()` sums only byte sizes of `ready` rows.
- It does not count capacity already reserved by queued/running background
  work. Every candidate in a batch therefore sees the same free space.
- With a 64 KiB quota, a 64 KiB fallback estimate, and one image requiring a
  thumbnail plus preview, the current implementation creates two jobs and zero
  deferred rows.

Required behavior:

- Define one explicit reservation model and document it in code:
  - either persist reserved bytes per active job/derivative; or
  - transactionally derive outstanding reservation pressure from current
    queued/running jobs using the same bounded estimate.
- Within one reconciliation transaction, each newly created active job must be
  visible to the capacity calculation for the next candidate. Concurrent
  reconciliations must serialize at the SQLite write boundary and cannot both
  reserve the same bytes.
- Account for ready bytes plus outstanding queued/running reservations without
  double-counting a ready derivative.
- If capacity cannot be reserved after eligible eviction, write
  `deferred_capacity` and create no active job.
- Preserve P0 behavior: interactive requests may evict eligible cache entries
  and generate only when the quota policy permits it; otherwise they return the
  stable capacity outcome.
- Do not perform irreversible file deletion inside a larger transaction that
  can later roll back and restore a `ready` row pointing at the deleted file.
  Use a committed eviction phase, a safe compensation strategy, or another
  design that preserves `ready => file exists` after exceptions.
- Only count bytes as freed when the file is absent or deletion succeeded.
  Permission failures must not create fictional capacity.
- A quota increase, cache clear, explicit generate action, and periodic or
  integrity reconciliation must reconsider deferred work without hot-looping.

Required regression tests:

- Quota equals one estimate; one asset needs two configured variants. Assert
  exactly one active job and one `deferred_capacity` row.
- Multiple assets in one batch cumulatively consume the quota and defer the
  remainder deterministically by asset/kind/variant order.
- Two concurrent reconcilers cannot over-reserve the same capacity.
- A queued/running job from a prior transaction counts against the next
  reconciliation pass.
- Failed file deletion does not reduce accounted usage or queue work beyond
  quota.
- Force an exception after an eviction decision and assert no committed
  `ready` row points to a deleted cache file.
- Increasing quota queues previously deferred identities exactly once.

## Fix 4 — Isolate metadata completion from derivative safety-net failures

Severity: P2
Introduced by: `f9d8eae`
Primary file: `backend/indexer.py`

Current failure:

- Metadata extraction, metadata completion, and the post-completion derivative
  reconcile call share one outer `try`.
- `complete_metadata_job()` commits the job and asset metadata state.
- If derivative reconciliation then raises, the outer exception handler calls
  `fail_metadata_job()` and overwrites the successful metadata job as failed.

Required behavior:

- Keep metadata extraction/upsert/completion in its existing lifecycle error
  boundary.
- After successful metadata completion commits, invoke derivative
  reconciliation in a separate best-effort boundary.
- A derivative reconcile error must be logged with bounded context and recorded
  in derivative/reconcile diagnostics, but must not change metadata job or
  `assets.metadata_state` results.
- Do not hold the metadata `_DB_LOCK` or completion connection while calling
  the scheduler.
- Wake/schedule only when the completed asset is still an active current image.

Required regression tests:

- Monkeypatch the derivative reconciler to raise after metadata completion.
  Assert the metadata job remains `done`, asset metadata remains `done`, and
  indexed metadata remains present.
- Assert a normal completion still schedules both configured derivative kinds
  for a warm library and schedules none automatically for an on-demand library.

## Fix 5 — Recover eligible current skipped identities without retry loops

Severity: P2
Introduced by: `f9d8eae`
Primary file: `backend/derivative_scheduler.py`

Current failure:

- `_coalesce_derivative_job()` sees `skipped` and returns terminal whenever
  `retry_failed=False`.
- Automatic scan/startup/periodic/integrity reconciliation therefore leaves a
  current `skipped/source_missing` or reactivated current identity with no
  active job even after the source becomes valid again.

Required behavior:

- Include the latest job `result_code` and applicability facts in candidate
  classification.
- For a current active identity whose filesystem stat and catalog identity are
  valid, automatically requeue only when the recorded skip reason no longer
  applies, including recovered `source_missing` and `asset_inactive` cases.
- Handle `source_changed` by reconciling the new current identity; never
  resurrect an old source-version row.
- Unknown or still-applicable skip reasons remain terminal unless an explicit,
  bounded retry policy permits them.
- Repeated reconciliation after a repaired skipped row must coalesce to one
  active job. A source that becomes unavailable again must not create an
  unbounded job loop.
- Counters must distinguish a terminal skipped row from a skipped row that was
  requeued.

Required regression tests:

- Seed a current `skipped/source_missing` derivative, restore a valid file with
  the same current catalog identity, reconcile, and assert one active job.
- Seed a still-missing source and assert repeated automatic passes create no
  jobs.
- Seed a historical `skipped/source_changed` identity and assert it remains
  history while the new current configured identity is created.
- Run the repair twice and assert the second pass is a no-op/active coalesce.

## Fix 6 — Make Admin generated-image state truthful for every lifecycle outcome

Severity: P2
Introduced by: `f9d8eae`
Primary files:

- `frontend/src/components/admin/LibraryDetailPage.vue`
- generated-image status/mutation composables and types if needed
- their focused Vitest files

Current failure:

- `derivativeCacheState` uses only `actionable_missing_derivatives` after the
  on-demand check.
- Active, terminal-failed, and deferred outcomes are intentionally excluded
  from that counter, so the UI can display `Complete` while jobs are running,
  failures need attention, or capacity blocks progress.
- On-demand libraries can also lose the manual action because desired/actionable
  automatic work is zero.

Required state precedence:

1. No loaded status: loading/error behavior remains owned by the query state.
2. `policy === "on_demand"`: show `On demand`, including when the library has
   zero assets. Cached coverage is informational. Keep an explicit Generate
   missing action whenever configured expected coverage exceeds ready coverage.
3. Warm policy with deferred work: show `Storage limited` and the deferred
   count.
4. Warm policy with terminal failures, or unhealthy workers blocking existing
   desired work: show `Needs attention`.
5. Warm policy with queued/running work: show `Preparing` and active counts.
6. Warm policy with actionable silent gaps: show `Needs generation` and the
   Generate missing action.
7. Show `Complete` only when both configured kinds are fully ready, there is no
   active/deferred/terminal work, and ready coverage equals expected coverage.
8. A genuinely unmeasured warm library may show the existing scan/unknown
   message, but it must not override the on-demand policy label.

Additional UI requirements:

- Preserve separate thumbnail and preview rows.
- Add compact per-kind missing/queued/running/failed/deferred detail using the
  existing card hierarchy; do not create nested-card clutter.
- Worker warnings must reflect work that cannot progress, including queued work
  with no healthy worker, without warning for a fully cached on-demand library.
- Poll only while queued/running work exists. Terminal/deferred gaps must not
  fast-poll forever.
- Manual Generate missing calls the all-kinds API and remains available under
  on-demand policy when cache coverage is incomplete.

Required frontend tests:

- Warm 211/211 thumbnail and preview coverage => `Complete`.
- Warm missing work with queued/running jobs => `Preparing`, not `Complete`.
- Terminal failure => `Needs attention`, not `Complete`.
- Deferred capacity => `Storage limited`, not `Complete`.
- Preview-only silent gap => `Needs generation` and actionable control.
- Partially cached on-demand library => `On demand` plus manual Generate
  missing.
- Empty on-demand library => `On demand`, not `Unknown` or `Complete`.
- Queued work plus unhealthy worker => visible warning.

## Fix 7 — Map HTTP derivative failures by result code

Severity: P2
Introduced by: `2297cb1`
Primary files:

- `backend/thumbnails.py`
- `backend/errors.py` only if an existing stable error type cannot represent a
  required outcome
- `backend/tests/test_api_integration_derivatives.py`

Current failure:

- The waiter reads `result_code`, but every derivative state `failed` becomes
  HTTP 400 invalid file.
- `internal_error` and `attempts_exhausted` are therefore misreported as bad
  source files.

Required mapping:

- `ready` with an existing file => serve the derivative and expected headers.
- `failed/invalid_source` => HTTP 400 using the stable invalid-file error shape.
- `skipped/source_missing` and `skipped/asset_inactive` => HTTP 404.
- `skipped/source_changed` => resolve and schedule the new current identity at
  most once, then continue inside the original total timeout budget.
- `deferred_capacity` => HTTP 507 with the stable capacity error type.
- `failed/attempts_exhausted` and `failed/internal_error` => a stable 5xx
  generated-image/server outcome, never HTTP 400.
- A genuinely still-active job that exceeds the deadline => HTTP 503 timeout.
- A second source-change race or an unknown terminal code must return an
  explicit bounded server outcome; do not label an immediate terminal result as
  a ten-second timeout.
- Never parse human-readable error strings to select a branch.

Required API tests:

- Exercise each mapping above through the actual thumbnail/preview request
  endpoint, not only `get_derivative_outcome()` unit tests.
- Prove source-changed rescheduling uses one total timeout and at most one
  reschedule.
- Prove thumbnail and preview variants/cache keys remain separated.

## Fix 8 — Detect missing configured identities exactly in integrity checks

Severity: P2
Introduced by: `2297cb1`
Primary file: `backend/integrity_checker.py`

Current failure:

- `_check_derivative_expected_row_missing()` compares the total number of all
  current derivative rows with the number of configured variants.
- Custom compatibility variants count toward that total. Two thumbnail rows can
  therefore hide a missing configured preview.

Required behavior:

- Compare exact configured `(kind, variant)` pairs for the current source
  identity. Custom dimensions/variants must neither satisfy nor block default
  desired coverage.
- Prefer a bounded SQL `VALUES`/CTE, exact `NOT EXISTS`, or equivalent query
  rather than counting unrelated rows.
- Preserve one candidate per asset and let the common reconciler create only
  the missing configured identity.
- Apply current asset/type/offline/deleted/source-version guards.
- Discover candidates inside a read phase, then invoke the singleton scheduler
  outside the integrity write transaction as required by Fix 2.

Required regression tests:

- One default thumbnail plus one custom thumbnail, no preview: integrity must
  detect and create/defer the configured preview.
- A custom preview must not satisfy the configured default preview.
- All configured default identities present plus arbitrary custom variants:
  integrity reports no expected-row gap.

## Fix 9 — Route manual Generate missing through the common reconciler

Severity: P2 architecture/behavior gap
Introduced by: `f9d8eae`
Primary files:

- `backend/derivative_scheduler.py`
- `backend/libraries.py`
- frontend mutation tests if the response shape changes additively

Current failure:

- `/api/derivatives/warm` calls `warm_library()`.
- `warm_library()` loops over every asset/variant and calls
  `schedule_derivative()` one at a time.
- It bypasses reconciler batching, result classification, cumulative capacity
  handling, summary counters, and the single-entrypoint invariant.

Required behavior:

- Make manual all-kinds and kind-scoped generation call
  `reconcile_desired_derivatives()` with library scope, P3 priority, and an
  explicit policy override so on-demand libraries can generate without changing
  `warm_enabled`.
- Use configured kinds only. Validate kind before any write.
- Define result-code-aware explicit retry semantics. One manual action may retry
  an eligible current terminal failure once/coalesced, but must not create
  duplicate active jobs or an unbounded invalid-source retry loop.
- Preserve the existing public response fields where clients depend on them;
  add bounded reconcile counters if useful. Keep raw paths out of the response.
- Remove the duplicate loop or reduce `warm_library()` to a compatibility
  wrapper over the reconciler so implementation paths cannot drift again.

Required regression tests:

- Spy/monkeypatch the common reconciler and prove the route uses it for all
  kinds and for `kind=preview`.
- On-demand manual generation overrides policy but does not toggle the stored
  setting.
- Manual generation obeys cumulative capacity and produces deferred outcomes
  instead of queueing an unbounded P3 backlog.
- Repeated manual clicks coalesce to one active job per identity.

## Fix 10 — Make reconciliation cooperatively stop after the current batch

Severity: P2 lifecycle gap
Introduced by: `f9d8eae`, still present after `a40e376`
Primary file: `backend/derivative_scheduler.py`

Current failure:

- `reconcile_desired_derivatives()` processes every batch and uses
  `time.sleep()` between batches without observing the reconciler or scheduler
  stop event.
- `stop()` can time out while one large library continues statting and writing
  all remaining batches.

Required behavior:

- Automatic startup/periodic/scan reconciliation must check a cooperative stop
  signal after the current batch commits and before the next batch begins.
- Never roll back already committed durable work solely because shutdown was
  requested.
- Replace the blind inter-batch sleep with an interruptible event wait for
  background reconciliation.
- Do not make interactive P0 scheduling depend on the background stop event.
  If needed, accept an optional cancellation callback/event only for automatic
  callers.
- Runtime reconciliation status must distinguish successful completion,
  stopped/cancelled completion, and error. Do not record a partial stopped pass
  as a full `ok` run.
- A restart must not clear a stop event out from under a still-alive old
  reconciler thread; coordinate this with Fix 1.

Required regression tests:

- Use more than one small configured batch. Request stop while the first batch
  is committed. Assert no second batch begins, first-batch jobs remain durable,
  and the reconciler thread exits within the shutdown bound.
- Restart afterward and assert the remaining desired work is reconciled exactly
  once.
- Assert a manual one-asset P0 request remains usable independently of the
  background reconciliation stop state.

## Fix 11 — Test and normalize Windows-style default exclusion paths through the public helper

Severity: P3 portability/test-contract gap
Introduced by: `46a4ea6`
Primary files:

- `backend/files.py`
- `backend/tests/test_catalog_hygiene_phase6.py`

Current failure:

- The Phase 6 test named `test_windows_style_separator_normalization` calls
  `_contains_segment()` with an already split tuple. It never passes a
  backslash path through `is_index_excluded_path()` or `_path_parts()`.
- On a POSIX test host, `Path(r"C:\\repo\\frontend\\coverage\\asset.png")`
  does not split backslashes, so the public helper's host-independent behavior
  is not proven.

Required behavior:

- Normalize both `/` and `\\` separators for default segment matching without
  breaking absolute POSIX paths, Windows drive paths, or UNC-style inputs.
- Keep exclusions exact to the known sequences:
  `frontend/coverage`, `frontend/test-results`, and
  `frontend/playwright-report`.
- Do not globally exclude an unrelated directory merely because its basename is
  `coverage`, `test-results`, or `playwright-report`.
- Preserve configured and per-library exclusion behavior and source files.

Required regression tests:

- Call `is_index_excluded_path()` directly with POSIX and Windows-style strings
  for all three default segments.
- Include drive-letter and, where supported, UNC-style examples.
- Assert `/photos/coverage/image.png` and
  `frontend/src/coverage/image.png` remain allowed.
- Run a normal production-shaped catalog scan/rebuild entrypoint, not only
  helper functions, and assert existing excluded assets become offline while
  source files remain on disk.

CROSS-FIX TEST DESIGN REQUIREMENTS

- Extend focused existing suites instead of creating one oversized test module
  when ownership is clear:
  - scheduler/start/stop/quota/skipped/manual reconcile:
    `backend/tests/test_derivative_scheduler.py` and phase-specific lifecycle
    files;
  - integrity transaction and exact configured identity:
    `backend/tests/test_integrity_checker.py` and
    `backend/tests/test_derivative_lifecycle_phase4.py`;
  - metadata safety net: the focused metadata lifecycle/indexer suite;
  - HTTP outcome mapping:
    `backend/tests/test_api_integration_derivatives.py`;
  - Admin truthfulness: `LibraryDetailPage.test.ts` plus generated-image query
    and mutation tests;
  - catalog exclusions: `test_catalog_hygiene_phase6.py`.
- Avoid tests that only inspect source text or call a lower-level helper while
  claiming an endpoint/runtime guarantee.
- Use deterministic events/barriers for thread races. Do not use long production
  sleeps. Short polling with a bounded deadline is acceptable when waiting for
  an actual DB state transition.
- Verify database state, job count, claim token, attempts, result code, and file
  existence where relevant; UI text alone is not enough for backend guarantees.
- Update `docs/testing/TEST_CATALOG.md` whenever a test's guarantees change.

REQUIRED VERIFICATION

Run focused checks while implementing, then run this combined backend set:

    backend/.venv_linux/bin/python -m pytest -q \
      backend/tests/test_derivative_lifecycle_phase0.py \
      backend/tests/test_derivative_lifecycle_phase4.py \
      backend/tests/test_derivative_lifecycle_phase5.py \
      backend/tests/test_catalog_hygiene_phase6.py \
      backend/tests/test_derivative_scheduler.py \
      backend/tests/test_integrity_checker.py \
      backend/tests/test_libraries_coverage.py \
      backend/tests/test_api_integration_derivatives.py \
      backend/tests/test_catalog_trigger_routing.py \
      backend/tests/test_imported_data_maintenance_api.py \
      backend/tests/test_maintenance_runtime_api.py

Run the frontend generated-image checks:

    cd frontend
    corepack pnpm run typecheck
    corepack pnpm exec vitest run \
      src/components/admin/__tests__/LibraryDetailPage.test.ts \
      src/components/admin/dialogs/__tests__/LibraryForm.test.ts \
      src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts \
      src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts
    cd ..

Then run repository gates:

    ./test.sh backend-api
    ./test.sh lint
    ./test.sh docs
    ./test.sh fast

Because these fixes cross scheduler concurrency, SQLite repair, HTTP contracts,
and frontend truthfulness, run `./test.sh full` before declaring the audit
follow-up complete. If the full suite cannot be run, record the exact reason and
do not claim full closeout or Phase 7 completion.

DOCUMENTATION AND HANDOFF REQUIREMENTS

- Update maintained architecture/configuration documentation only where the
  corrected runtime contract differs from current prose.
- Update `docs/testing/TEST_CATALOG.md` for all new or strengthened guarantees.
- Add an "Audit follow-up" section to
  `docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_IMPLEMENTATION_STATUS.md`
  containing:
  - all eleven issue IDs/titles;
  - implementation commit(s);
  - exact test commands and real results;
  - remaining known gaps, if any.
- Correct Phase 0–6 status claims if any exit criterion remains unverified.
- Do not mark Phase 7 complete and do not archive the plan as part of this work
  unless every original Phase 7 deliverable, performance budget, E2E test, and
  full validation requirement is independently completed.

DEFINITION OF DONE

- A cold start cannot recover a claim created by its own newly started workers.
- Integrity can repair multiple derivative issue types in one run without
  nested-write locking or incorrect summary counters.
- Capacity reservation includes outstanding active work and cannot over-admit a
  batch or concurrent pass.
- Derivative reconciliation failure cannot rewrite successful metadata state.
- Eligible current skipped work converges exactly once; still-invalid or
  historical work does not retry-loop.
- Admin renders On demand, Storage limited, Needs attention, Preparing, Needs
  generation, and Complete according to the actual lifecycle.
- HTTP failed/skipped/deferred outcomes map by stable result code.
- Custom variants cannot hide a missing configured thumbnail or preview.
- Manual Generate missing uses the common reconciler and remains available for
  incomplete on-demand coverage.
- Background reconciliation exits after the current committed batch on stop.
- Public exclusion helpers and production-shaped scan tests cover both slash
  styles without hiding legitimate unrelated folders.
- All focused tests, backend API checks, lint, docs, fast, and full validation
  pass, or any unrun full validation is explicitly recorded without claiming
  completion.

FINAL RESPONSE FORMAT

Lead with whether all eleven findings are fixed. Then report:

1. fixes grouped by issue number;
2. files changed;
3. regression tests added/strengthened;
4. exact verification commands and results;
5. any remaining risks or unverified Phase 7 work;
6. confirmation that unrelated pre-existing worktree changes were preserved.
```

## Audit Reproduction Summary

The prompt above is based on direct code review plus deterministic temporary-DB
reproductions. Before the fixes, the following outcomes were observed:

```text
startup recovery race:
  startup_recovered=1
  post_start=('queued', attempts=1, claim_token=None)

capacity over-admission:
  quota=65536
  created_jobs=2
  deferred_capacity=0

current skipped gap:
  terminal_skipped=1
  created_jobs=0
  active_jobs=0

integrity nested write:
  status=error
  error=database is locked

configured identity false negative:
  current rows=two thumbnail variants, zero preview variants
  derivative_expected_row_missing=0
  preview_rows=0
```

Existing focused suites were green while these reproductions still failed, so
the new tests must exercise the concrete state transitions and concurrency
interleavings rather than duplicating the old assertions.
