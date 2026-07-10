# Derivative Lifecycle `d98c741` Re-audit Fix — OpenCode Handoff Prompt

Status: Implemented in the worktree; corrective commit pending

Last reviewed: 2026-07-10

## Purpose

This document is a copy-ready OpenCode prompt for the remaining defects found
while re-auditing commit `d98c741`. The next pass must preserve the fixes that
are already correct while closing three P1 runtime races, one P2 integrity
reporting defect, and the incomplete test/documentation evidence.

## Copy-Ready Prompt

```text
You are working in /home/ubuntu/gallery-repo at or after commit d98c741.

Fix every remaining finding from the d98c741 re-audit. Do not rewrite the full
derivative lifecycle and do not regress the fixes that are already correct. The
task is complete only when the deterministic reproductions below pass through
production-shaped entrypoints, the added tests would fail on d98c741 for the
audited reason, documentation matches committed reality, and all required
repository gates are green.

READ FIRST

1. AGENTS.md
2. README.md
3. docs/README.md
4. docs/ARCHITECTURE.md
5. docs/CONFIGURATION.md
6. docs/testing/README.md
7. docs/testing/TEST_CATALOG.md
8. docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_PLAN.md
9. docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_IMPLEMENTATION_STATUS.md
10. docs/plans/DERIVATIVE_LIFECYCLE_D98C741_REAUDIT_FIX_HANDOFF_PROMPT.md

STARTING STATE AND WORKTREE SAFETY

- Run `git status --short`, `git rev-parse HEAD`, and
  `git show --stat d98c741` before editing.
- Preserve unrelated modified/untracked work. Do not reset, checkout, stash,
  delete, resolve, stage, or format unrelated files.
- Use current maintained code/tests as runtime truth and d98c741 as the audited
  failure baseline.
- Keep Gallery's single-process FastAPI + SQLite architecture, separate
  thumbnail/preview identities, existing cache keys, durable derivative jobs,
  fenced claims, and bounded worker count.
- Do not add Redis, Celery, a second service, or a new infrastructure
  dependency.
- Do not weaken schemas/assertions, increase arbitrary sleeps, skip tests, mark
  tests xfail, or change test prose without implementing the claimed test.
- Use Events, Conditions, Barriers, and explicit deadlines in concurrency
  tests. Do not rely on scheduler luck or `sleep()` for ordering.
- Use production entrypoints and the singleton scheduler where production does.
  A direct helper-only test is not sufficient when the bug occurs through
  reconcile, integrity, start/stop, or persistence orchestration.
- Keep Phase 7 open unless every Phase 7 exit criterion is genuinely complete.

PRESERVE THESE CORRECT d98c741 FIXES

- A rolled-back capacity transaction no longer leaves scheduler-global pending
  unlinks; the old `_pending_unlinks` list is gone.
- Insufficient eligible bytes return not-reservable without partial eviction.
- `IntegrityChecker.run_all_checks()` routes exact derivative IDs to exact
  consistency repair, so a valid custom derivative in an on-demand library
  receives one job without changing `warm_enabled`.
- Startup exceptions still clear `_start_in_progress`, notify waiters, and
  re-raise.
- Cancellation during the reconciliation yield prevents the next batch.
- Public reconciliation timestamps remain millisecond integers.
- On-demand Admin coverage continues to expose manual Generate missing.
- Existing cumulative active reservation accounting, lease fencing, stable HTTP
  result codes, exact configured variants, and metadata error containment remain
  intact.

AUDIT REPRODUCTIONS TO RUN BEFORE FIXING

1. Unlink failure after job commit:

       quota_bytes=150
       existing ready bytes=100
       proposed estimate=100
       unlink raises OSError

   Observed on d98c741:

       created_jobs=1
       existing row restored to ready (100 bytes, file exists)
       new derivative remains queued with one active job

   Committed ready + reserved usage becomes 200 > quota 150.

2. Serving protection lost between selection and unlink:

       scheduler.acquire_serving(cache_path)
       _unlink_evictions([(cache_path, derivative_id, byte_size)])

   Observed:

       file_exists=False

3. Bounded shutdown:

       GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS=0.05
       block cold-start recovery indefinitely
       call stop() in another thread

   Observed after 0.25 seconds:

       stop thread is still alive

4. Two start callers plus stop:

       start A blocks in recovery
       start B waits behind A
       stop increments generation
       release A

   Observed:

       all API threads return
       one worker is actually alive
       scheduler.alive_worker_count() == 0
       last_shutdown_clean() is True

5. Historical phantom integrity summary:

       current active asset
       historical queued derivative without a job
       run IntegrityChecker.run_and_persist(trigger="manual")

   Observed:

       durable derivative status=skipped
       generated_image_queued_without_job=1
       repairs.requeued=1
       repairs.skipped=0

GLOBAL INVARIANTS

1. Capacity is not freed until the corresponding file deletion really succeeds.
2. A failed/protected eviction cannot leave a new runnable job consuming
   fictional capacity.
3. No stale eviction may delete a file that is served, generating, or newly
   regenerated at the same deterministic path.
4. Once `stop()` returns, no start invocation that existed before or during
   that stop may create a worker, supervisor, or reconciler.
5. Shutdown remains bounded even if database recovery never returns.
6. `last_shutdown_clean=True` implies all threads in the stopped lifecycle
   generation are known and stopped; no live thread reference was discarded.
7. Integrity issue counters describe detected anomalies; repair counters
   describe actual durable outcomes, not assumed outcomes.
8. Tests must assert both database state and filesystem/thread state after the
   full production operation finishes.

IMPLEMENT THE FOLLOWING WORKSTREAMS IN ORDER

## Workstream 1 — Make capacity finalization depend on successful eviction

Severity: P1
Primary file: `backend/derivative_scheduler.py`

Current defect:

- `_coalesce_derivative_job()` writes the new queued job in the same transaction
  that marks eviction candidates `evicted`.
- The transaction commits before `_unlink_evictions()` executes.
- On unlink failure, `_unlink_evictions()` restores the old ready row but does
  not cancel/defer the already-committed target job.
- Workers are woken before unlink processing, so a worker can claim work while
  the reservation is still only hypothetical.

Required behavior:

- A target job must not become runnable until enough real filesystem bytes were
  successfully released and capacity was recomputed from committed state.
- Hold one scheduler-owned capacity/eviction coordination lock across the full
  prepare/finalize sequence, not only the SQL candidate query.
- Choose one explicit two-phase design and document it:

  Option A — prepare capacity before job insertion:
  1. select/revalidate candidates and transition them out of `ready` in a short
     transaction;
  2. commit;
  3. perform protected filesystem deletion;
  4. compensate failed/protected candidates;
  5. recompute committed ready + active reservation usage;
  6. only then insert/coalesce the target job in a new short transaction.

  Option B — durable non-runnable capacity state:
  1. persist target/eviction intent in a state workers cannot claim;
  2. delete and compensate;
  3. atomically promote to `queued` only when real capacity is available;
  4. otherwise move the target to `deferred_capacity` with no active job.

- An alternative is acceptable only if workers cannot claim before capacity is
  final and unlink failure cannot leave ready bytes plus reservations above the
  quota.
- If an eviction fails after target intent exists, atomically remove/cancel the
  newly created active job or move the target to `deferred_capacity` before
  releasing the capacity lock.
- Wake workers only after final capacity validation and runnable job commit.
- Recompute capacity after compensation and after concurrent state changes; do
  not trust the original estimate snapshot.
- Preserve the rule that insufficient eligible bytes do not partially evict
  useful ready files.
- Preserve cumulative reservations when multiple variants are considered in
  one reconciliation pass.

Required deterministic tests:

- Production `reconcile_desired_derivatives()`: unlink raises; existing row/file
  remains ready, target is deferred/no active job, and the quota equation holds.
- Production `schedule_derivative()` path for an evicted/deferred identity:
  unlink raises; no excess runnable job survives.
- Unlink succeeds: exact required candidates are evicted, target gets exactly
  one job, and the second pass coalesces.
- Mixed success/failure across multiple candidates: only successfully deleted
  bytes count as freed; compensate the others and queue only work that fits.
- Proposed derivative larger than total quota remains deferred with no job.
- Two concurrent reconcilers cannot both spend the same successful eviction.

## Workstream 2 — Protect served, generating, and regenerated paths at unlink time

Severity: P1
Primary file: `backend/derivative_scheduler.py`

Current defect:

- Serving/generation protection is checked when candidates are selected.
- `_unlink_evictions()` is a module-level helper with no scheduler/file-lock
  access and performs no protection recheck after the transaction commits.
- A path can become served or generating between selection and unlink.

Required behavior:

- Make eviction finalization scheduler-owned so it can coordinate with
  `_file_lock`, `_served_paths`, and `_generating_paths`.
- Immediately before unlinking each path, revalidate under `_file_lock` that it
  is still neither served nor generating.
- Keep the exclusion and unlink decision in one critical section so
  `acquire_serving()` or generation cannot enter between the final check and
  unlink.
- If a path is protected, do not unlink it and do not count its bytes as freed;
  compensate its database state truthfully.
- Guard compensation by derivative ID, expected state, original cache path,
  source identity, and/or version so compensation cannot overwrite a newer
  queue/render/ready state.
- Prevent an old eviction plan from deleting a freshly regenerated file at the
  same deterministic cache path. Use a version/fence or equivalent identity
  validation, not path equality alone.

Required deterministic tests:

- Acquire serving after candidate selection but before final unlink; file stays
  present, row is restored/truthful, and target is not overcommitted.
- Mark the path generating in the same window; identical guarantee.
- Regenerate the deterministic path before an old eviction finalizes; the new
  file survives.
- Release serving and retry later; eviction then succeeds exactly once.
- Concurrent serve/reconcile loops never expose `ready` with a missing file.

## Workstream 3 — Make start/stop linearizable and strictly bounded

Severity: P1
Primary file: `backend/derivative_scheduler.py`

Current defects:

- `stop()` uses `while self._start_in_progress` with repeated timeout waits but
  no absolute deadline, so a hung recovery makes shutdown unbounded.
- `stop()` snapshots worker/supervisor/reconciler references before waiting for
  startup cancellation.
- A second start caller waiting behind the cancelled first start captures the
  post-stop generation and can launch threads before or after `stop()` returns.
- Final stop bookkeeping filters the stale pre-wait snapshot, dropping
  references to those newly launched threads while reporting clean shutdown.

Required behavior:

- Give every `start()` invocation a request generation/epoch captured at method
  entry before it waits behind another start.
- Introduce an explicit stop-in-progress lifecycle state or equivalent. A start
  invocation that began before/during a stop must not silently become a fresh
  post-stop start.
- Only a new explicit `start()` invoked after stop has completed may clear stop
  events and create a new lifecycle generation.
- Stop increments/cancels the generation, then waits for startup acknowledgment
  using an absolute monotonic deadline:

      deadline = time.monotonic() + shutdown_timeout
      remaining = deadline - time.monotonic()

  Exit when remaining <= 0, set `clean=False`, and return without waiting
  forever.
- Recovery may remain outside the lifecycle lock. When it eventually returns,
  the cancelled generation must observe its stale epoch and exit without
  launching anything.
- After startup acknowledgment, take a fresh snapshot of all lifecycle threads
  and join/bookkeep that snapshot. Never overwrite `_threads` from a stale
  pre-wait list.
- If any worker/supervisor/reconciler/start transition remains alive beyond the
  bound, report `last_shutdown_clean=False` and retain accurate references.
- Preserve restart after a clean or incomplete stop without recovering live
  fenced claims twice.

Required deterministic tests:

- Block `_ensure_database()` indefinitely with an Event that has no timeout.
  `stop()` returns within the configured bound, reports unclean, and no worker
  can launch after recovery is later released.
- Repeat for `_reconcile_queued_jobs()` and `_recover_running_jobs()`.
- Two simultaneous start callers plus one stop: both old invocations exit,
  zero actual lifecycle threads remain, scheduler count is zero, and clean
  status is truthful.
- Start caller enters while stop is in progress: it cannot launch; a separate
  call after stop returns can start exactly once.
- Force worker/supervisor/reconciler start failures; latch is released, waiters
  wake, and all already-created threads remain tracked/stopped.
- Incomplete stop retains live thread references and a later restart restores
  only missing worker slots.
- Tests assert Event wait results and thread termination; no 5-second timeout
  is used as the mechanism that makes the test pass.

## Workstream 4 — Report exact integrity repair outcomes

Severity: P2
Primary files:

- `backend/derivative_scheduler.py`
- `backend/integrity_checker.py`
- integrity/file-health tests

Current defect:

- `repair_derivative_consistency()` returns only the number of jobs created.
- `run_and_persist()` adds every detected
  `derivative_queued_without_job` issue to `repairs.requeued`, even when exact
  repair terminalized the derivative as skipped or made no change.
- Historical phantom rows therefore persist as `skipped` while the public
  summary says `requeued`.

Required behavior:

- Return a bounded structured result from exact consistency repair, for example:

      issues_considered
      jobs_created
      already_active
      terminal_skipped
      terminal_failed
      unchanged

- `run_all_checks()` must expose distinct exact-repair outcome counters.
- `run_and_persist()` must derive `repairs.requeued`, `skipped`, `failed`, and
  `unchanged` from actual outcomes, never from issue discovery counts.
- A current valid custom/on-demand phantom remains one issue + one requeue.
- A historical/source-changed phantom becomes one issue + one skip, zero
  requeues.
- Missing/inactive identities receive their documented stable result codes and
  are counted under the actual terminal outcome.
- An active job appearing concurrently is not counted as a newly created job.
- Persisted summaries and maintenance API schemas remain bounded and contain no
  raw paths.

Required tests:

- Production `run_and_persist()` for current configured warm phantom.
- Production `run_and_persist()` for current custom on-demand phantom with
  deliberately different asset and derivative IDs.
- Historical phantom => durable `skipped/source_changed`, repairs.skipped=1,
  repairs.requeued=0.
- Missing/inactive phantom => truthful terminal counter and result code.
- Concurrent repair/HTTP scheduling => one active job and no double repair
  count.
- Maintenance file-health endpoint returns the persisted actual outcome.

## Workstream 5 — Complete tests, formatting, and truthful documentation

Severity: P2
Primary files:

- `backend/tests/test_derivative_scheduler.py`
- `backend/tests/test_integrity_checker.py`
- `backend/tests/test_integrity_checker_contract.py`
- `backend/tests/test_derivative_lifecycle_phase4.py`
- `backend/tests/test_derivative_lifecycle_phase5.py`
- `backend/tests/test_maintenance_file_health_api.py`
- relevant frontend/status tests for the preserved d98c741 guarantees
- `docs/testing/TEST_CATALOG.md`
- `docs/plans/DERIVATIVE_LIFECYCLE_FULL_CONVERGENCE_IMPLEMENTATION_STATUS.md`

Current defects:

- Existing focused suites pass while all P1 reproductions above still fail.
- The two new start/stop tests depend on a five-second blocker timeout and do
  not cover two start callers or a genuinely bounded stop.
- No new integrity test proves the custom/on-demand exact production route even
  though TEST_CATALOG claims it.
- No acceptance tests were added for unlink failure, served/generating races,
  cancel-during-yield, non-null millisecond timestamps, or the on-demand UI.
- `backend/tests/test_derivative_scheduler.py` is not Ruff-format clean, causing
  `./test.sh lint` to fail.
- Implementation status duplicates the Phase 7 heading, says the implementation
  commit is pending although d98c741 exists, records `107+ passed` instead of an
  exact count, and claims changed-file gates pass while lint fails.

Required behavior:

- Add every deterministic regression listed in Workstreams 1-4. Demonstrate
  that each fails against d98c741 for the audited reason.
- Add/retain acceptance tests for already-correct prior fixes:
  - cancel arriving inside inter-batch Event.wait starts no next batch;
  - actual reconciliation exposes integer millisecond timestamps through the
    real schema on ok/stopped/error paths;
  - partial on-demand coverage shows Generate missing and fully cached/empty
    coverage hides it;
  - custom on-demand exact phantom gets one job without policy mutation.
- Format every touched Python test/source file with the configured Ruff
  formatter, then use format `--check` to prove idempotence.
- Update TEST_CATALOG only with guarantees actually exercised by named tests.
- Rewrite implementation status truthfully:
  - remove the duplicate Phase 7 heading;
  - record d98c741 as the audited implementation commit;
  - record the corrective commit only after it exists, otherwise say pending;
  - use exact commands and exact pass counts;
  - do not claim lint/docs/fast/full passed unless each command was run and
    passed;
  - keep Phase 7 open while full/E2E/performance evidence remains incomplete.

MANDATORY VALIDATION

Run focused suites first:

    backend/.venv_linux/bin/python -m pytest -q \
      backend/tests/test_derivative_scheduler.py \
      backend/tests/test_integrity_checker.py \
      backend/tests/test_integrity_checker_contract.py \
      backend/tests/test_derivative_lifecycle_phase4.py \
      backend/tests/test_derivative_lifecycle_phase5.py \
      backend/tests/test_maintenance_runtime_api.py \
      backend/tests/test_maintenance_file_health_api.py \
      backend/tests/test_api_integration_derivatives.py

    cd frontend
    corepack pnpm run typecheck
    corepack pnpm exec vitest run \
      src/components/admin/__tests__/LibraryDetailPage.test.ts \
      src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts \
      src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts \
      src/contracts/__tests__/catalogStatusContract.test.ts
    cd ..

Run non-mutating format/lint checks for touched files, then repository gates:

    backend/.venv_linux/bin/python -m ruff check \
      backend/derivative_scheduler.py \
      backend/integrity_checker.py \
      backend/tests/test_derivative_scheduler.py \
      backend/tests/test_integrity_checker.py \
      backend/tests/test_integrity_checker_contract.py

    backend/.venv_linux/bin/python -m ruff format --check \
      backend/derivative_scheduler.py \
      backend/integrity_checker.py \
      backend/tests/test_derivative_scheduler.py \
      backend/tests/test_integrity_checker.py \
      backend/tests/test_integrity_checker_contract.py

    ./test.sh backend-api
    ./test.sh lint
    ./test.sh docs
    ./test.sh fast

Run `./test.sh full` before Phase 7 closeout if the documented environment is
available. If a gate is blocked externally, report the command, exit code, and
blocker; never report an unrun/blocked gate as passing.

After all validation, run:

    git status --short

Tests and format checks must not leave unexpected source changes.

ACCEPTANCE CHECKLIST

- [ ] Unlink failure cannot leave ready bytes plus runnable reservations above
      quota.
- [ ] Workers cannot claim target work until capacity deletion is finalized.
- [ ] Served, generating, and freshly regenerated paths survive stale eviction.
- [ ] Successful eviction frees real bytes and creates exactly one target job.
- [ ] Insufficient capacity still performs no partial eviction.
- [ ] Stop returns within its configured bound even when recovery never returns.
- [ ] Two old start callers cannot launch after/during stop.
- [ ] `last_shutdown_clean` and thread references match actual live threads.
- [ ] A new explicit start after stop works exactly once.
- [ ] Integrity persisted repair counters match actual requeued/skipped/failed
      outcomes.
- [ ] Custom on-demand exact repair remains fixed without policy mutation.
- [ ] Every audited race has a deterministic regression test.
- [ ] Ruff format check and `./test.sh lint` pass.
- [ ] TEST_CATALOG and implementation status match real tests, commits, and
      exact gate results.
- [ ] No unrelated worktree changes are included.

FINAL HANDOFF FORMAT

Report:

1. Root cause and implementation summary for each workstream.
2. Exact files changed.
3. Tests added and why each fails on d98c741.
4. Exact validation commands, pass counts, failures, and external blockers.
5. Final `git status --short` and corrective commit hash if created.
6. Residual risks. Do not claim Phase 7 complete while required evidence is
   missing.
```
