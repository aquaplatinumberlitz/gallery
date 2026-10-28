# Worker Lifecycle Hardening Plan

Status: Active
Created: 2026-10-27
Source: worker audit WK-01..WK-06 (2026-10-27), reproduced against a
1,500-image fixture on branch `refactor/stack-cleanup` (`9a0270b`).

## Goal

Background workers (catalog scan, metadata, derivative) appear to "die midway"
because they are starved, not because they crash. Remove the starvation at its
root while keeping every current product behavior, API response shape, and UI
visual unchanged.

The work is split into four phases. Each phase is its own reviewable unit with
regression tests that fail before the fix and pass after it. A phase may start
only after the previous phase passed review.

| Phase | Theme | Closes | Risk |
| ----- | ----- | ------ | ---- |
| 0 | Contention harness + quick root-cause fixes | WK-01, WK-03 (WK-02 symptom) | Low |
| 1 | Unified durable job policy | WK-04, WK-05, WK-06 | Medium |
| 2 | Single database writer (DiffusionToolkit pattern) | WK-02 root cause, write contention | High |
| 3 | Retire the process-global `_DB_LOCK` | Lock convoy class of bugs | Medium |

## Architecture decision

Keep SQLite, the single-process deployment, and durable SQLite job tables.
Do not adopt PostgreSQL, Redis, BullMQ, or a separate worker process.

- From **Immich**, keep the job semantics: durable job states, claim tokens,
  leases, heartbeats, retry with backoff, stalled-job recovery, and O(1)
  queue counts for status.
- From **DiffusionToolkit**, adopt the storage pattern: workers do CPU and I/O
  work in parallel but never write SQLite directly; one database writer thread
  applies writes in short batched transactions.

Target shape after Phase 3:

```text
catalog / metadata / derivative workers (parallel, no direct DB writes)
   │ submit(write op) → Future
   ▼
DatabaseWriter (one thread, one write connection)
   - batch up to N ops or T ms, one short BEGIN IMMEDIATE per batch
   - SAVEPOINT per op so one failing op does not abort the batch
   - maintains runtime counters used by status reads
readers (HTTP status/browse/search, workers' reads)
   └─ plain WAL read connections, no Python lock
```

Non-goals:

- No in-memory job queue. Jobs stay in SQLite (`AGENTS.md` contract). The
  writer buffers pending *writes*, never the list of jobs to run.
- No multi-process support. The single-process ownership contract in
  `docs/ARCHITECTURE.md` stays.
- No visual or interaction change in the frontend.

## Frozen findings

| ID | Severity | Invariant violated | Evidence (audit) | Acceptance criteria |
| -- | -------- | ------------------ | ---------------- | ------------------- |
| WK-01 | Critical | Status reads must not stall workers | `/api/libraries/{id}/status`, `/api/libraries/status`, `/api/derivatives/status`, `/api/maintenance/runtime` took 33-45 s on 1,500 images / 36,000 `derivative_jobs` rows. The correlated `max(latest.id)` subquery in `status_store.build_global_runtime` (no index on `derivative_jobs.derivative_id`) ran under `_DB_LOCK`; 35.3 s → 0.028 s with an `(derivative_id, id)` index, same result. Metadata throughput fell from 455 to 1 job / 120 s while the UI polled every 2.5 s. | Status endpoints p95 ≤ 500 ms with ≥ 36,000 `derivative_jobs` rows; status reads do not acquire `_DB_LOCK`; metadata throughput while polling ≥ 90 % of throughput without polling. |
| WK-02 | High | Catalog lease renewal must not depend on unrelated readers | With `GALLERY_CATALOG_JOB_LEASE_SECONDS=30` and UI polling, two scans failed with "Catalog worker stopped before completing the job" and the library went to `error`. `renew_catalog_job_lease` (`job_store.py`) waits on `_DB_LOCK`. | Under the same polling load with a 30 s lease, zero scans fail by lease loss. |
| WK-03 | High | No write transaction may hold the SQLite write lock longer than `busy_timeout` | Write-lock probe measured continuous holds of 14.9 s and repeated 5-6 s holds during a rescan; 90 `database is locked` errors. `_coalesce_reconcile_candidates` runs `_capacity_available` (two full-table aggregates, 5.9 ms each) for every one of up to 750 coalesces inside one `BEGIN IMMEDIATE`. | Max continuous write-lock hold ≤ 1,000 ms during rescan + reconcile of the fixture; zero `database is locked` log lines; quota decisions unchanged. |
| WK-04 | High | A running metadata job must be recoverable without restart | During a normal rescan a metadata job failed and its failure write also hit `database is locked`, leaving it `running` forever. Integrity check and rescan did not recover it (`integrity_checker.py` preserves `running`; dispatch coalesces it). Status stuck at `needs_update` 99.93 %, runtime reported one phantom active job. | An orphaned `running` metadata job is reclaimed within one lease interval while the process keeps running, and a stale worker cannot overwrite the newer claim. |
| WK-05 | Medium | Transient storage errors must be retried | `perf_0028.png` ended `failed`, `attempts=1`, `error='database is locked'`. `fail_metadata_job` treats every exception as terminal. | `sqlite3.OperationalError` locked/busy and transient `OSError` are retried with backoff up to the attempt limit; parse/format errors still fail immediately. |
| WK-06 | Medium | Superseded derivatives must leave the ready set | After 7 rescans: 27,003 `ready` rows (files still on disk) for old source identities vs 2,136 current. They count toward quota and inflate tables used by WK-01/WK-03 queries. Integrity check did not retire them. | After a source identity changes, old-identity derivatives leave `ready`, their files are removed after commit, quota counts only current identities, and an integrity pass repairs pre-existing stale rows. |

Out of scope (backlog, do not fix in this plan): `MetadataLifecycleWorker.stop()`
1-second join followed by `start()` returning early in an in-process restart;
the VPS has no process supervisor for the backend.

## Ground rules

- Work on branch `fix/worker-lifecycle`. One commit per task is preferred.
- **Test first.** Every finding gets a focused regression test that fails on the
  pre-fix code. Record the failing output (command + assertion) in the
  phase progress log below before writing the fix.
- Never weaken, skip, or delete an existing assertion. Updating a monkeypatch
  target because a symbol moved is allowed.
- Keep `scripts/check_metadata_lifecycle_ownership.py` passing. Lifecycle helpers
  stay owned by `backend/indexer.py`.
- Keep claim-token fencing semantics for catalog, metadata, and derivative jobs.
- Keep API response shapes. Status counters must equal the values the current
  aggregate queries return for the same database state.
- New schema columns and indexes follow the existing additive pattern
  (`metadata_store/_schema_ensure.py` + fresh DDL in `_schema_ddl.py`), not a
  catalog version bump, unless a non-additive change is unavoidable.
- New env vars go into `backend/config.py` and `docs/CONFIGURATION.md`.
- New or changed tests are listed in `docs/testing/TEST_CATALOG.md`. Test files
  keep the repository header format checked by `scripts/check_test_docs.py`.
- Update `docs/ARCHITECTURE.md` (Metadata Lifecycle, Derivative Lifecycle, and a
  new Database Writer section in Phase 2) whenever ownership or runtime behavior
  changes.

Verification commands used by every task:

```bash
backend/.venv_linux/bin/python -m pytest backend/tests/<targeted files> -q
./test.sh backend-api
./test.sh lint
./test.sh docs
backend/.venv_linux/bin/python -m pytest backend/tests/ -q --cov=backend --cov-fail-under=90
```

Frontend tasks additionally run `cd frontend && corepack pnpm run test:unit` and
the relevant Playwright specs.

## Regression harness (built in Phase 0, used by every phase)

### H1. Focused pytest regressions

One test module per finding, named `backend/tests/test_worker_contention_<id>.py`
(for example `test_worker_contention_wk01.py`). Each module must be fast
(< 30 s), deterministic, and independent of wall-clock races: drive contention
with explicit locks, events, and injected failures rather than sleeps.

### H2. Contention benchmark

`scripts/worker_contention_bench.py`, with a `[worker_contention]` section in
`scripts/perf_budgets.toml` (mirrored in `frontend/tests/e2e/perf/perf-budgets.json`
only if `scripts/check_perf_budgets.py` requires it). The benchmark:

1. Builds a 1,500-image fixture with `scripts/create_perf_fixture.py` in a temp dir.
2. Seeds synthetic `assets`/`asset_derivatives`/`derivative_jobs` rows until
   `derivative_jobs` has ≥ 36,000 rows. The synthetic rows are documented in the
   report and used only for status and capacity measurements.
3. Starts the backend as a subprocess on a free port with an isolated DB and
   cache, scans the library, and waits for metadata and derivatives to settle.
4. Measures, then reports JSON and exits non-zero on any budget failure:

| Metric | Budget |
| ------ | ------ |
| `status_p95_ms` (4 status endpoints, 20 samples each) | ≤ 500 |
| `polling_throughput_ratio` (metadata jobs/120 s with three status pollers every 2.5 s ÷ without) | ≥ 0.90 |
| `max_write_lock_hold_ms` (external probe, `BEGIN IMMEDIATE` with `timeout=0` every 20 ms, during touch + rescan) | ≤ 1,000 (Phase 2 target ≤ 250) |
| `database_locked_log_lines` during the run | 0 |
| `orphan_running_metadata_jobs` 60 s after the queue drains | 0 |
| `lease_loss_failed_scans` (second run with `GALLERY_CATALOG_JOB_LEASE_SECONDS=30` while polling) | 0 |
| `superseded_ready_derivatives` after two touch + rescan cycles | 0 |

The benchmark must fail loudly when a workload did not run (for example zero
metadata jobs processed), never report an empty workload as success. Add it to
`docs/testing/PERFORMANCE_TESTING.md` and as an opt-in step of
`scripts/internal/test-perf.sh`.

## Phase 0 — Harness and quick root-cause fixes

### 0.1 Harness and baseline

- Build H2 and the H1 modules for WK-01 and WK-03.
- Run them on unmodified code; record the failing baseline numbers in the
  progress log.

### 0.2 Index for the runtime status query (WK-01)

- Add `idx_derivative_jobs_derivative_id ON derivative_jobs(derivative_id, id)`
  to fresh DDL and to the additive ensure path.
- Regression: `EXPLAIN QUERY PLAN` of the `build_global_runtime` derivative
  count query uses the new index; the query finishes in < 500 ms over 36,000
  seeded rows and returns the same rows as before the index.

### 0.3 Status reads without `_DB_LOCK` (WK-01, WK-02 symptom)

- `status_store.build_global_runtime`, `build_catalog_status`,
  `build_library_status_batch`, derivative `library_status`, and
  `maintenance` runtime reads use a read connection that does not take
  `_DB_LOCK`. Wrap each status build in one read transaction so all counters
  come from one consistent WAL snapshot.
- Regression: with `_DB_LOCK` held by another thread, each status function
  returns within 2 s; counters equal the values computed under the lock for
  the same seeded state.

### 0.4 Capacity accounting once per reconcile batch (WK-03)

- Compute ready bytes and active-job reservations once per reconcile batch
  transaction and update the running total in memory as coalesces create or
  requeue jobs. Quota decisions must be identical to the per-coalesce query.
- Regression: count capacity aggregate statements per batch with
  `sqlite3.Connection.set_trace_callback`; at most one pair per batch. Existing
  capacity, eviction, and deferred-capacity tests pass unchanged. A boundary
  test where the quota is exhausted midway through one batch produces the same
  per-identity outcomes as the old code.

### 0.5 Polling backoff (frontend, no visual change)

- `frontend/src/lib/catalog/polling.ts`: the active interval never drops below
  2× the last observed fetch duration for that query (cap at the stable
  interval). Do not change any rendered output.
- Regression: Vitest for the interval function; existing status-panel tests
  unchanged.

### Phase 0 exit gate

H1 WK-01/WK-03 pass; H2 `status_p95_ms`, `polling_throughput_ratio`,
`max_write_lock_hold_ms` (≤ 1,000), `database_locked_log_lines`, and
`lease_loss_failed_scans` pass. Full backend suite, lint, docs, and
`./test.sh backend-api` pass.

## Phase 1 — Unified durable job policy

### 1.1 Metadata job leases and runtime recovery (WK-04)

- Add `claimed_by`, `claim_token`, `lease_expires_at` to `metadata_index_jobs`.
- `claim_next_metadata_job` sets owner, token, and lease. Complete, fail,
  stale, and requeue writes are fenced by the claim token.
- A heartbeat renews the lease during extraction (reuse the derivative
  `_LeaseHeartbeat` design; extract a shared helper only if it stays small).
- `MetadataLifecycleWorker` gains a supervisor (30 s) that requeues expired or
  ownerless `running` jobs (attempt-aware) and restores the configured worker
  count. Startup recovery uses the same function.
- Integrity checker and dispatch stop preserving expired `running` rows forever;
  live, unexpired claims stay protected.
- Regressions: (a) failure write raises `database is locked` once → job is
  reclaimed after lease expiry and completes; (b) a stale worker's completion
  after reclaim is rejected; (c) a slow extraction with a live heartbeat is not
  reclaimed; (d) the runtime `metadata_active_jobs` counter returns to 0.

### 1.2 Transient error retry (WK-05)

- Classify `sqlite3.OperationalError` messages containing `locked` or `busy`
  and transient `OSError` (`EAGAIN`, `EBUSY`, `EINTR`) as transient. Transient
  failures requeue with exponential backoff (store the earliest next attempt;
  claim ignores rows not yet due) until `MAX_METADATA_JOB_ATTEMPTS`, then fail.
  Parse/format errors fail immediately as today.
- The failure/requeue write itself retries a bounded number of times so a
  locked database cannot orphan the job.
- Regressions: injected `database is locked` during upsert → job ends `done`
  with attempts 2; invalid image → `failed` after one attempt; backoff respects
  the due time.

### 1.3 Retire superseded derivatives (WK-06)

- When a source identity changes (scan updates `mtime_ns`/`size`) or a
  reconcile sees an old identity, move old-identity `ready` rows to `skipped`
  with `result_code='source_superseded'`, clear their quota accounting, and
  unlink their files only after the transaction commits.
- Add an integrity repair for pre-existing superseded rows.
- Serving protection: a file currently being served (lookup lease) is not
  unlinked until its lease is released.
- Regressions: touch + rescan retires old rows and files; quota equals current
  identities only; integrity repair cleans seeded stale rows; serving
  protection holds.

### Phase 1 exit gate

H1 WK-04/WK-05/WK-06 pass; H2 `orphan_running_metadata_jobs` and
`superseded_ready_derivatives` pass; Phase 0 budgets still pass.

## Phase 2 — Single database writer

### 2.1 Writer core

- New `backend/metadata_store/db_writer.py`: `DatabaseWriter` owns one write
  connection on one thread. `submit(op, *, lane="normal") -> Future`, where
  `op(conn)` runs inside the batch transaction under its own `SAVEPOINT`.
- Batching: up to `GALLERY_DB_WRITER_BATCH_MAX` ops (default 50) or
  `GALLERY_DB_WRITER_BATCH_MS` (default 100). A `priority` lane (lease
  renewals, claim, terminal writes) is drained before the `normal` lane.
- Bounded queue with backpressure; `submit` from the writer thread itself runs
  inline to avoid self-deadlock.
- Lifecycle: started in the app lifespan before any worker and stopped after
  all workers, draining within a shared deadline. Registered in
  `_LifecycleRegistry`.
- Feature flag `GALLERY_DB_WRITER_ENABLED` (default `true` once 2.2 lands),
  kept until Phase 3 so each migrated path can fall back.
- Regressions: FIFO order within a lane; priority lane preempts; a failing op
  rolls back only its savepoint and surfaces its exception on its Future; drain
  on stop; a crash between batches leaves jobs recoverable by leases.

### 2.2 Metadata writes through the writer

- Upsert metadata + complete job become one writer op per job. Claims may be
  batched (claim up to K jobs per op) without changing priority order.

### 2.3 Derivative writes through the writer

- Claim, heartbeat renewals, completion, failure, and reconcile batches go
  through the writer. Reconcile batches are split so no op exceeds the write
  budget.

### 2.4 Catalog writes through the writer

- Scan batch upserts, job transitions, and lease renewals (priority lane).

### 2.5 O(1) runtime counters

- A `runtime_counters` table maintained by writer ops (or triggers) for the
  counts the status endpoints return. An integrity step recomputes them from
  the source tables and repairs drift.
- Regression: after randomized job transitions, counters equal the aggregate
  queries.

### Phase 2 exit gate

H2 `max_write_lock_hold_ms` ≤ 250 and all earlier budgets pass; metadata and
derivative throughput without polling ≥ the Phase 1 baseline; full suites pass.

## Phase 3 — Retire `_DB_LOCK`

- Inventory every `_DB_LOCK` use (≈150 sites). Reads move to plain WAL read
  connections; writes move to the writer.
- Remove `_DB_LOCK` from production code and remove the Phase 2 feature flag.
- Add `scripts/check_db_write_ownership.py` (run from `./test.sh docs` or
  `./test.sh lint`): fails when production code outside the writer, schema,
  and migration modules executes `INSERT`, `UPDATE`, `DELETE`, `REPLACE`, or
  `BEGIN IMMEDIATE`.
- Exit gate: no `_DB_LOCK` in `backend/` outside tests; ownership check passes;
  H1, H2, full backend suite, `./test.sh e2e` relevant specs, and
  `./test.sh fast` pass.

## Progress log

Record per task: date, commit, failing-before evidence, passing-after
evidence, and H2 numbers.

| Phase | Task | Status | Evidence |
| ----- | ---- | ------ | -------- |
| 0 | 0.1 | Done 2026-10-27 (base `cce87f7`, uncommitted work on `fix/worker-lifecycle`) | Built `scripts/worker_contention_bench.py` (H2; `[worker_contention]` budgets, `diagnostic` manifest workload, opt-in `GALLERY_PERF_WORKER_CONTENTION=1` step in `test-perf.sh`, `--phase 0/1` budget selection), `backend/tests/test_worker_contention_wk01.py` (19 tests), `test_worker_contention_wk03.py` (8 tests), and `worker_contention_support.py`. **Fail-before** (unmodified code, only the new tests present): `pytest test_worker_contention_wk01.py test_worker_contention_wk03.py` = 18 failed / 8 passed (the 8 are equivalence guards that must stay green), e.g. 36,000-row runtime count query interrupted after 10 s (budget 0.5 s), `ready-bytes aggregate ran 180 times in one reconcile batch`, status build opened 5 connections. **H2 baseline** (unmodified code, 1,500 images, 36,000 `derivative_jobs`): `status_p95_ms` 22,776, `polling_throughput_ratio` 0.00 (414 jobs/120 s without pollers, 0 with), `max_write_lock_hold_ms` 6,868 (18 spans over 1 s), `database_locked_log_lines` 43, `lease_loss_failed_scans` 1 (library went to `error`); also `orphan_running_metadata_jobs` 0 and `superseded_ready_derivatives` 36,000 (Phase 1 targets, not enforced). Exit code 1. |
| 0 | 0.2 | Done 2026-10-27 | `idx_derivative_jobs_derivative_id ON derivative_jobs(derivative_id, id)` in fresh DDL, the additive ensure path, and `schema_check`. Regressions (`wk01`): index exists on fresh and re-initialized existing databases; `EXPLAIN QUERY PLAN` of the global-runtime and `library_status` job queries uses it; the 36,000-row runtime query finishes < 0.5 s (was > 10 s, interrupted); counts equal a Python oracle with and without the index. |
| 0 | 0.3 | Done 2026-10-27 | `_read_snapshot()` (`metadata_store/_db.py`): `query_only` WAL connection, one deferred read transaction, no `_DB_LOCK`. Used by `build_global_runtime`, `build_catalog_status`, `build_library_status_batch`, `get_indexer_runtime_status`, `get_metadata_lifecycle_status`, `DerivativeScheduler.library_status`, `/api/maintenance/runtime`, and the watcher-root lookup (`list_libraries(conn=...)`, which was the last `_DB_LOCK` use on the status path). Each status build shares one snapshot connection. Regressions (`wk01`): 6 status functions + 4 endpoints return within 2 s while another thread holds `_DB_LOCK` (8 of 10 failed before); a writer commit between two queries of one build is invisible to it; one connection per build; counters equal `fixtures/worker_contention/status_golden_wk01.json`, generated from the unmodified code (passes before and after). |
| 0 | 0.4 | Done 2026-10-27 | `CapacityLedger` (`derivative_scheduler/capacity.py`) loads ready bytes and active-job reservations once per reconcile batch transaction (lazily) and follows ready/evicted/queued transitions in memory; `_coalesce_derivative_job(..., ledger=)`. Regressions (`wk03`): at most one aggregate pair per batch, also when the quota is exhausted midway and across the public `reconcile_desired_derivatives` (180/120/225 aggregates before); per-identity outcomes, pending-capacity work, and resulting rows equal an independent oracle of the old per-coalesce algorithm across a 32-point quota sweep (13 identity states, `retry_failed` x reason) and 24 seeded random trials. Mutation checks on the ledger (dropping any of its four updates) fail the equivalence tests. |
| 0 | 0.5 | Done 2026-10-27 | `frontend/src/lib/catalog/polling.ts`: `observeFetchDuration`/`backoffInterval`/`activePollInterval`; `statusRefetchInterval(status, enabled, query?)` and the three admin pollers (+ generated-images) pass the query so the active interval is `min(60 s, max(2.5 s, 2 x last fetch duration))`. `polling.test.ts` 24 tests (12 new fail on the old file, including a real `QueryObserver` check that the next poll is never sooner than 2x the previous fetch); `useLibraryStatusBatchQuery.test.ts` only gained one mock export. Vitest: 119 files / 1,265 tests pass. |
| 0 | Exit gate | Passed 2026-10-27 (two clean H2 runs) | `worker_contention_bench.py --phase 0` on the fixed tree, 1,500 images + 36,000 `derivative_jobs`: run 1 / run 2 — `status_p95_ms` 145.7 / 118.4 (was 22,776), `polling_throughput_ratio` 0.913 / 0.934 (541 and 575 jobs/120 s without pollers, 494 and 537 with; was 0.00), `max_write_lock_hold_ms` 788 / 667 (was 6,868; 0 spans over 1 s), `database_locked_log_lines` 0 / 0 (was 43), `lease_loss_failed_scans` 0 / 0 (was 1). Phase 1 targets, reported but not enforced: `orphan_running_metadata_jobs` 0 / 0 and `superseded_ready_derivatives` 36,000 / 36,000 (27,000 seeded + 9,000 from two rescans). Remaining Phase 2 work: the longest write-lock holds are now 667-788 ms (6-9 spans over 250 ms), well inside the 1,000 ms Phase 0 budget but above the 250 ms Phase 2 target; the ratio's 6-9 % loss comes from status CPU in the shared process, not from locks. |
| 1 | 1.1 | Done 2026-10-28 (uncommitted on `fix/worker-lifecycle`, base `1385c62`) | `metadata_index_jobs` gained `claimed_by`, `claim_token`, `lease_expires_at`, `next_attempt_at` (fresh DDL, additive ensure path, `schema_check`) and `idx_metadata_index_jobs_state_lease (state, lease_expires_at)`; no catalog version bump. `claim_next_metadata_job` records owner/token/lease (`GALLERY_METADATA_JOB_LEASE_SECONDS`, default 300); `complete`/`fail`/`stale`/`requeue`/`renew` writes are fenced by the claim token and return whether they applied (a stale worker's write after a reclaim changes 0 rows and does not stamp the asset). The shared `LeaseHeartbeat` (`backend/lease_heartbeat.py`, ~45 lines) now backs both the metadata worker and the derivative `_LeaseHeartbeat`. `MetadataLifecycleWorker` gained a supervisor thread (`GALLERY_METADATA_SUPERVISOR_INTERVAL_SECONDS`, default 30 s; stopped inside the existing 1 s bounded `stop()` join, so no lifespan change) that restores dead worker threads (never an unstarted worker) and calls `recover_abandoned_metadata_jobs(expired_only=True)`; startup recovery calls the same `recover_running_metadata_jobs` with `expired_only=False`. The integrity pass and metadata dispatch now requeue (attempt-aware) expired/ownerless `running` rows and still protect live claims. **Fail-before** (`wk04`, unmodified production code of `1385c62`, `scratchpad/phase1/fail_before.txt`): 20 failed / 0 passed; most fail on the missing API (`claim_next_metadata_job(worker_id=)`, `MetadataLifecycleWorker(lease_seconds=)`, `metadata_now`), the behavioural ones on assertions (claim columns/index absent on fresh and existing DBs, ownerless `running` row stays `running` after an integrity pass, app lifespan starts no supervisor). **Pass-after**: 20/20, repeated 5x with no flake. |
| 1 | 1.2 | Done 2026-10-28 | `indexer.is_transient_metadata_error` (`sqlite3.OperationalError` containing `locked`/`busy`; `OSError` EAGAIN/EBUSY/EINTR) and `metadata_retry_delay_seconds` (`GALLERY_METADATA_RETRY_BASE_SECONDS` x 2^(attempts-1), capped at 60 s). A transient failure calls `requeue_metadata_job` (state `queued`, `next_attempt_at` = now + backoff, claim released, attempts and `queued_at` kept) until `MAX_METADATA_JOB_ATTEMPTS`, then `fail_metadata_job`; claims skip rows whose `next_attempt_at` is in the future and still order the due rows by priority; a rescan coalescing into a queued retry does not reset its backoff. Parse/format errors (`UnidentifiedImageError`, oversized sidecar, vanished file) fail after one attempt. The failure/requeue write is retried through `_persist` (delays 0.1/0.5/1.0 s, transient errors only), then the lease recovers the job. **Fail-before** (`wk05`): 34 failed / 0 passed (missing `is_transient_metadata_error`, `requeue_metadata_job`, `write_retry_delays`, `next_attempt_at`). **Pass-after**: 34/34. |
| 1 | 1.3 | Done 2026-10-28 | New `derivative_scheduler/supersede.py` (`SupersedeMixin`): `ready` rows of an active asset whose `source_mtime_ns`/`source_size` differ from the asset's identity move to `skipped` (cache fields cleared) and their jobs (queued/running/`done` history) to `skipped` with `result_code='source_superseded'`; a derivative without such a latest job gets one, and `_coalesce_derivative_job` treats `source_superseded` like `source_missing`/`asset_inactive`, so a source that returns to an old identity is regenerated. Retirement runs at the start of each reconcile batch transaction (before the capacity estimate; every retired row is reported to the batch `CapacityLedger.ready_row_left`; measured 132 ms for a 250-asset batch retiring 4,500 rows plus 750 coalesces), after each catalog scan/rebuild commit regardless of warm policy (bounded 500-row transactions), and at the start of each integrity pass (`run_all_checks` gained `metadata_running_recovered` and `derivative_superseded_retired`; API shapes unchanged). Files are unlinked only after the retiring transaction commits; a served path (`_served_paths`) is deferred and removed by `release_serving`; a generating or still-referenced path is never removed. **Fail-before** (`wk06`): 13 failed / 2 passed (the two passes are guards: a rolled-back batch keeps rows and files; a retiring batch still runs one capacity aggregate pair). **Pass-after**: 15/15. wk03 oracle equivalence tests unchanged and green. |
| 1 | Exit gate | Passed 2026-10-28 | `worker_contention_bench.py --phase 1` (1,500 images, 36,000 `derivative_jobs`, exit 0, `scratchpad/phase1/bench_after.json`): `status_p95_ms` 146.7, `polling_throughput_ratio` 0.95 (560 vs 532 jobs/120 s), `max_write_lock_hold_ms` 587.7 (6 spans over 250 ms, 0 over 1 s), `database_locked_log_lines` 0, `lease_loss_failed_scans` 0, `orphan_running_metadata_jobs` 0, `superseded_ready_derivatives` 0 (was 36,000 in the Phase 0 runs). Python 3.11 full backend suite with coverage: 1,428 passed / 1 skipped / 1 failed (`test_libraries_coverage.py::test_validate_settings_unreadable_path`, pre-existing: the sandbox user is root, so `chmod 000` does not make the path unreadable), coverage 90.70 %. Ruff check/format, `./test.sh docs`, `./test.sh backend-api` (106 passed) pass. Existing tests edited: `test_integrity_checker_contract.py` (`test_unaffected_row_left_alone` now gives each ready row the current identity of its own asset, because an old-identity ready row is exactly what WK-06 retires; its assertions are unchanged; `test_returns_all_twenty_keys_with_int_values` lists the two new `run_all_checks` keys). |
