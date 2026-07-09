# Immich-Style Derivative Lifecycle Hardening

Status: Complete and archived

Last reviewed: 2026-07-09

## Implementation Progress

| Phase | Status | Evidence |
| --- | --- | --- |
| 1. Characterization and regression tests | Complete | Added missing-source-after-claim, worker-continuation, inactive-asset claim, and startup-recovery coverage in `backend/tests/test_derivative_scheduler.py`; expanded the test catalog entry. Tests intentionally fail against the pre-hardening scheduler and define the Phase 2/3 contract. |
| 2. Terminal state and containment | Complete | Added durable `result_code`, controlled `skipped` outcomes, post-claim source validation, cache-path/render containment, consistent job/derivative terminal writes, and a catch-all worker boundary. Focused suite: 7 passed; the two remaining failures require Phase 3 claim/recovery columns. |
| 3. Claim fencing and recovery | Complete | Added additive ownership/token/lease columns and recovery index; fenced completion/failure writes; added startup/expired/dead-worker recovery; added a 30-second supervisor that restores worker slots. Scheduler + schema suites: 15 passed. |
| 4. Integrity and scheduling alignment | Complete | Active/current-source predicates now gate scheduling, claiming, recovery, and integrity repair. Missing-cache repair skips inactive/missing/superseded sources, expired claims are recovered, and derivative writes use Julian timestamps. Scheduler/integrity/library suites: 125 passed. |
| 5. Diagnostics and admin UI | Complete | Library status and global runtime now expose queue/worker/failure/stale-claim diagnostics. Polling follows queued/running work, the thumbnail action sends `kind=thumbnail`, Library warns on unhealthy workers, and Maintenance shows generated-image runtime health. Backend API suite: 93 passed; full frontend unit suite: 1,046 passed; focused admin suite: 39 passed; `vue-tsc`: passed. |
| 6. Documentation and closeout | Complete | Updated maintained Architecture, Configuration, testing docs, shared API schema, and implementation status. `lint`, `docs`, `backend-api` (103 passed), `fast` (backend 925 passed at 90.58%; frontend 1,048 passed with coverage/build), and 9 relevant Playwright tests passed. |

Handoff checkpoint after Phase 1: production behavior is unchanged. The new
tests require `result_code`/claim columns and lifecycle containment, so the
focused scheduler suite is expected to fail until Phases 2 and 3 land.

Handoff checkpoint after Phase 2: the original missing-source race is contained
and the worker continues to later jobs. Claim fencing, leases, supervisor
replacement, and inactive-job reconciliation remain Phase 3 work.

Handoff checkpoint after Phase 3: claims are fenced and recoverable, startup
uses policy-based reconciliation, and dead worker slots are supervised. The
remaining backend consistency work is integrity/status predicate alignment and
timestamp normalization in Phase 4.

Handoff checkpoint after Phase 4: backend lifecycle, recovery, and integrity
paths share the same active/current-source contract. Remaining work is API
diagnostics, frontend polling/admin presentation, documentation, and the broad
verification matrix.

Handoff checkpoint after Phase 5: the implementation is feature-complete across
backend and admin UI. Phase 6 must update maintained docs, run lint/docs/fast
verification, record actual evidence, and only then close/archive this plan.

Final checkpoint after Phase 6: all definition-of-done implementation and
verification items are complete. The plan and implementation status are
archived; maintained behavior is documented in `docs/ARCHITECTURE.md`,
`docs/CONFIGURATION.md`, and `docs/testing/README.md`.

## Summary

Harden the SQLite-backed derivative scheduler so one missing, stale, corrupt, or
otherwise failing source can terminate only its own job. It must never terminate
a worker thread, strand jobs in `running`, or block later thumbnail and preview
work.

The design adapts the useful lifecycle invariants from Immich without adopting
Redis, BullMQ, or a separate microservice:

- filter invalid work before enqueue;
- validate the asset again after claim;
- contain every handler exception at the job boundary;
- always materialize a terminal or retryable durable state;
- recover abandoned claims;
- supervise worker availability;
- expose queue and worker health to administrators.

This plan closes the unresolved derivative-worker finding recorded in
`docs/archived/DB_REQUIRED_LIBRARY_DERIVATIVE_AUDIT.md`. Readiness, cache-file
existence, and offline-asset coverage fixes already landed, but the
missing-source worker-survival acceptance criterion did not.

## Current Failure

The current scheduler marks a job `running`, then calls
`derivative_cache_path()`. That helper stats the source before `_run_job()` enters
its exception handler. If the file disappears in this interval:

1. `FileNotFoundError` escapes `_run_job()`;
2. `_worker_loop()` does not catch it;
3. the worker thread exits;
4. both `derivative_jobs` and `asset_derivatives` remain `running`;
5. repeated warm requests only add or coalesce queued work;
6. after all configured workers exit, generated-image coverage never advances.

The integrity checker can amplify this failure. It requeues derivatives whose
cache file is missing without first proving that the asset is still active and
the source still exists. Catalog reconciliation may mark the asset offline
later, but the derivative claim query does not currently exclude offline or
deleted assets.

The observed production case had all three derivative workers stranded on
deleted `frontend/test-results` images while valid missing thumbnails waited
behind them.

## Immich Pattern Being Adapted

Immich separates four responsibilities:

1. Its thumbnail queue-all query excludes deleted and hidden assets and selects
   assets that actually need generated files.
2. The thumbnail handler fetches the asset again and returns a controlled
   `Failed` or `Skipped` result when the asset is no longer processable.
3. A shared job dispatcher wraps every handler in `try/catch/finally`, emitting
   error and completion events without terminating the worker.
4. BullMQ supplies claim ownership, stalled-job recovery, worker discovery, and
   queue diagnostics.

Gallery should preserve these invariants using SQLite rows and in-process
threads. It should not copy Immich's deployment topology.

## Goals

- A claimed derivative job always becomes `done`, `skipped`, `failed`, or a
  bounded `queued` retry.
- Missing or inactive assets never terminate a worker.
- Deleted/offline assets are not scheduled or claimed.
- Dead workers are replaced without restarting the backend.
- Abandoned `running` jobs are recovered without allowing stale workers to
  overwrite newer results.
- Admin status distinguishes missing generated files from an unhealthy queue.
- Existing derivative cache identity, quota enforcement, and on-demand serving
  behavior remain compatible.

## Non-Goals

- Introducing Redis, BullMQ, Celery, or another external queue.
- Moving derivative rendering into a separate service.
- Redesigning the complete Admin UI.
- Guaranteeing hard cancellation of a native image decoder stuck inside a
  Python thread. Lease recovery may safely duplicate idempotent rendering, but
  Python threads cannot be forcibly terminated.
- Changing thumbnail or preview dimensions, quality, format, or quota policy.

## Lifecycle Contract

### Job states

`derivative_jobs.state` supports:

```text
queued -> running -> done
                  -> skipped
                  -> failed
running -> queued
```

`running -> queued` is allowed only for a bounded transient retry, startup
recovery, dead-worker recovery, or expired-lease recovery.

Terminal meanings:

| State | Meaning |
| --- | --- |
| `done` | The current derivative file was generated and its catalog row was materialized as `ready`. |
| `skipped` | Work is no longer applicable because the asset/source identity is inactive, missing, or superseded. |
| `failed` | The current applicable source could not be processed, or transient attempts were exhausted. |

`asset_derivatives.status` mirrors active execution state with
`queued`, `running`, `ready`, `skipped`, and `failed`.

### Result codes

Persist a machine-readable `result_code` on derivative jobs:

| Result code | Terminal state | Use |
| --- | --- | --- |
| `asset_inactive` | `skipped` | Asset is deleted or offline after enqueue. |
| `source_missing` | `skipped` | Source no longer exists when execution validates it. |
| `source_changed` | `skipped` | Asset/source mtime or size no longer matches the claimed derivative version. |
| `invalid_source` | `failed` | Unsupported, corrupt, oversized, or otherwise permanently invalid image. |
| `attempts_exhausted` | `failed` | A transient error reached the existing three-attempt limit. |
| `internal_error` | `failed` | An unexpected non-retryable implementation failure occurred. |

Keep human-readable detail in `error` and `last_error`. UI logic must use states
and result codes rather than parsing error strings.

### Error policy

- Missing, inactive, or changed sources are normal lifecycle races and become
  `skipped`; they are not retried.
- Invalid/corrupt sources become `failed`; they are not retried automatically.
- SQLite contention and transient I/O errors retain bounded exponential retry,
  with a maximum of three attempts.
- Unexpected exceptions are caught at the job boundary, persisted as `failed`,
  logged with a stack trace, and followed by the next queued job.
- Failure persistence itself is guarded. If it fails, the outer worker boundary
  logs the secondary error and continues; lease recovery repairs the abandoned
  row.

## Persistence Changes

Extend `derivative_jobs` additively:

```sql
claimed_by       TEXT
claim_token      TEXT
lease_expires_at REAL
result_code      TEXT
```

Add an index supporting recovery:

```sql
CREATE INDEX IF NOT EXISTS idx_derivative_jobs_state_lease
ON derivative_jobs(state, lease_expires_at);
```

No destructive migration or database reset is allowed. Use the existing
additive schema-ensure mechanism.

Derivative-table timestamps remain SQLite Julian-day values. All scheduler and
integrity-checker writes to derivative rows must use `julianday('now')`; do not
mix Unix epoch seconds into these columns.

### Claim fencing

Each scheduler process owns a generated instance ID. Each worker slot has a
stable worker ID. A claim:

1. selects one queued job joined to an active image asset;
2. verifies the derivative row still represents the asset's current mtime and
   size;
3. assigns `claimed_by`, a unique `claim_token`, and a 15-minute lease;
4. marks both job and derivative `running` in one short transaction.

Completion, skip, failure, and retry updates include both job ID and
`claim_token`. A late worker whose lease was recovered therefore cannot
overwrite the state produced by a newer claim.

## Backend Implementation

### Scheduling and claiming

- `warm_library()` continues selecting only active image assets and must skip
  files that fail a current filesystem stat.
- `_claim_job()` joins `assets` with
  `deleted_at IS NULL AND offline = 0`, current source identity, and configured
  variants.
- Before selecting normal work, reconcile queued jobs that already reference an
  inactive or superseded asset to `skipped`.
- Repeated warm requests may requeue a previously failed current derivative,
  but must not revive `skipped` work for a missing or inactive source.
- Restoring/reappearing files is handled by catalog reconciliation and a new
  derivative identity; old skipped version rows remain historical.

### Execution containment

Refactor `_run_job()` so every source-dependent operation, including cache-path
calculation, is inside one owned `try/except/finally` boundary.

The worker loop also has a final catch-all around claim and execution. It must
log unexpected errors and continue polling. No ordinary `Exception` may escape
the thread target.

Rendering remains outside database transactions. Completion updates the
derivative row and job row in short transactions, fenced by `claim_token`.

### Supervisor and recovery

Add one scheduler supervisor thread:

- starts and stops with the derivative scheduler;
- runs every 30 seconds;
- prunes dead worker threads and restores the configured worker count;
- immediately recovers jobs owned by a worker that died;
- reaps `running` jobs whose 15-minute lease expired;
- records/logs worker-count transitions without emitting repetitive warnings.

Recovery policy:

| Condition | Recovery |
| --- | --- |
| Asset inactive or source missing | Mark job and derivative `skipped`. |
| Source identity changed | Mark old job and derivative `skipped`; current work is scheduled independently. |
| Attempts below three and source is current | Clear claim fields and return job/derivative to `queued`. |
| Attempts exhausted | Mark job/derivative `failed`. |

Startup runs the same reconciliation before workers begin claiming. It replaces
the current unconditional `running -> queued` reset.

### Integrity checker

- `derivative_ready_no_file` checks the joined asset state and current source
  identity before requeueing.
- Missing cache for an active/current derivative is requeued.
- Inactive, missing-source, and superseded derivatives are marked `skipped`.
- Add a check for expired or abandoned derivative jobs.
- Never treat a `skipped` derivative as a done/ready mismatch.
- Return separate issue/repair counters for requeued, skipped, failed, and
  recovered derivative jobs while preserving the existing file-health envelope
  compatibility.

## API and Frontend Contract

### Library generated-image status

Extend `GET /api/derivatives/status?library_id=...` with:

```json
{
  "queued_jobs": 0,
  "running_jobs": 0,
  "failed_jobs": 0,
  "skipped_jobs": 0,
  "configured_worker_count": 3,
  "alive_worker_count": 3,
  "worker_healthy": true,
  "oldest_running_age_seconds": null
}
```

Library job counts include only configured variants for active assets and their
current source identity. Historical derivative versions do not make the current
library appear failed.

Existing response fields remain unchanged.

### Global runtime diagnostics

Extend `GET /api/maintenance/runtime` `global_runtime` with:

```text
derivative_configured_worker_count
derivative_worker_count
derivative_active_jobs
derivative_queue_depth
derivative_failed_jobs
derivative_skipped_jobs
derivative_stale_running_jobs
derivative_oldest_running_age_seconds
```

These fields are diagnostics, not mutation controls.

### Admin behavior

- Generated-image status polls at the active interval while `queued_jobs` or
  `running_jobs` is nonzero. A mere ready/expected mismatch does not cause
  endless fast polling when work is failed or workers are unhealthy.
- The library Generated Images card shows:
  - coverage by thumbnail and preview;
  - queued/running/failed counts;
  - an actionable warning when files are missing but no derivative worker is
    healthy.
- “Build missing thumbnails” calls warm with `kind=thumbnail`.
- Maintenance adds a compact “Generated images” runtime section showing workers,
  active jobs, queue depth, failures, and stale jobs.
- Keep primary UI labels user-facing; backend terms such as lease and claim
  token stay in diagnostics/tooltips only.

## Implementation Phases

### Phase 1: Characterization and regression tests

- Add failing tests for the exact missing-source race.
- Add a worker-continues-to-next-job test.
- Add inactive asset schedule/claim tests.
- Add startup recovery and stale-running characterization.
- Record the new tests in the test catalog before changing behavior.

### Phase 2: Terminal state and containment

- Add `skipped` and result-code semantics.
- Move cache-path calculation and all filesystem access inside `_run_job()`'s
  handler.
- Add the outer worker-loop containment boundary.
- Make job/derivative terminal updates consistent.

This phase alone must prevent the observed queue outage.

### Phase 3: Claim fencing and recovery

- Add claim ownership, tokens, lease fields, and recovery index.
- Fence every post-claim update.
- Implement startup reconciliation, expired-lease recovery, and dead-worker
  recovery.
- Add the supervisor lifecycle and worker replacement.

### Phase 4: Integrity and scheduling alignment

- Apply active/current predicates consistently to warm, claim, integrity, and
  status queries.
- Prevent integrity repair from reintroducing invalid work.
- Correct derivative timestamp writes.

### Phase 5: Diagnostics and admin UI

- Extend backend response models and TypeScript contracts.
- Update polling policy and the two admin surfaces.
- Keep old API fields backward compatible.

### Phase 6: Documentation and closeout

- Update maintained Architecture, Configuration, and testing documentation.
- Run the full verification matrix.
- Create an implementation-status document containing actual commit/test
  evidence.
- Archive this plan only after every definition-of-done item passes.

## Test Matrix

### Scheduler unit tests

1. Claim a job, delete its source, run it, and assert:
   - job and derivative become `skipped`;
   - result code is `source_missing`;
   - no exception escapes;
   - worker processes the next valid job.
2. Delete the source before cache-path calculation and protect the exact
   historical regression.
3. Mark an asset offline/deleted before warm and before claim; no runnable work
   is created or claimed.
4. Change mtime/size after enqueue; old job becomes `skipped/source_changed` and
   cannot mark the new derivative ready.
5. Corrupt source becomes `failed/invalid_source`.
6. Transient error retries three times with backoff, then fails.
7. A late completion with an obsolete claim token updates zero current rows.
8. Dead worker is replaced and only its owned job is recovered.
9. Expired lease requeues current work and terminalizes inactive/exhausted work.
10. Startup applies the same recovery policy idempotently.

### Integrity tests

- Missing cache + active/current source creates or reuses one queued job.
- Missing cache + offline/deleted asset becomes skipped and creates no job.
- Running job with missing source is terminalized.
- Skipped jobs are not reported as done-not-ready mismatches.
- Derivative timestamps remain in one unit.

### API and frontend tests

- Status contracts include lifecycle/worker fields and preserve existing fields.
- Library-scoped counts exclude historical/offline versions.
- Active polling occurs only for queued/running work.
- Missing coverage plus zero workers shows the unhealthy-worker warning.
- Thumbnail action sends `kind=thumbnail`; preview work is not queued.
- Maintenance displays generated-image worker and queue health.

### End-to-end regression

Seed a deleted transient artifact ahead of two valid missing thumbnails, start
three workers, invoke “Build missing thumbnails,” and assert:

- the stale artifact does not terminate a worker;
- both valid thumbnails become ready;
- coverage reaches expected;
- worker count remains configured;
- no job remains indefinitely `running`.

## Verification Commands

Run, at minimum:

```bash
backend/.venv_linux/bin/python -m pytest \
  backend/tests/test_derivative_scheduler.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_libraries_coverage.py \
  backend/tests/test_maintenance_runtime_api.py

./test.sh backend-api

cd frontend
corepack pnpm run test:unit

cd ..
./test.sh lint
./test.sh docs
```

Run the relevant Library Admin Playwright spec after the frontend diagnostics
changes. Run `./test.sh fast` before handoff.

## Definition of Done

- Missing-source races cannot terminate derivative workers.
- Every claimed job has a durable terminal/retry transition.
- No active job remains `running` after its owner dies or lease expires.
- Offline/deleted assets are excluded from warm, claim, integrity requeue, and
  current status.
- Worker count self-recovers without backend restart.
- Admin status distinguishes queue health from generated-file coverage.
- The original 209/211 reproduction advances to 211/211 after valid missing
  thumbnails are queued.
- All lifecycle, API, frontend, lint, and documentation checks pass.
- Maintained docs describe the implemented behavior, and archive status contains
  verification evidence rather than a broad unverified “completed” claim.
