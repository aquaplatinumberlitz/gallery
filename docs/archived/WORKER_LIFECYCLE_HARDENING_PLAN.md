# Worker Lifecycle Hardening Plan

Status: Completed (2026-11-01; archived)
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
| `max_write_lock_hold_ms` (external probe, `BEGIN IMMEDIATE` with `timeout=0` every 20 ms, during touch + rescan) | ≤ 250 since Phase 3 (≤ 1,000 through Phase 2) |
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
| 2 | 2.1 | Done 2026-10-28 (uncommitted on `fix/worker-lifecycle`, base `e544398`) | New `backend/metadata_store/db_writer.py`: `DatabaseWriter` (one `gallery-db-writer` thread, one autocommit write connection opened like `_connect()`, reopened when the configured DB path changes). `submit(op, *, lane)` returns a Future; `run(op)` submits and waits. One `BEGIN IMMEDIATE` per batch (`GALLERY_DB_WRITER_BATCH_MAX` 50 / `GALLERY_DB_WRITER_BATCH_MS` 100, never lingering for ops that are not queued), one `SAVEPOINT` per op (a failing op rolls back only itself and surfaces its own exception), Futures resolve after the commit, transient `BEGIN`/`COMMIT` failures re-run the whole batch (0.05/0.25/1 s) and exhausted ones fail every op of it, `priority` lane drained before `normal` (FIFO per lane), per-lane bounded queues with a timing-out `submit`, `stop()` drains within `GALLERY_DB_WRITER_SHUTDOWN_TIMEOUT_SECONDS` and later submits raise at once. Registered in `_LifecycleRegistry` before catalog/metadata/derivative (stops last). Deadlock guard: `_DB_LOCK` is now a thin `RLock` wrapper that raises `WriterThreadLockError` on the writer thread (its first run found a real hidden use: the sidecar check inside `complete_metadata_job` reaches `get_library_for_path`/`get_asset_state_for_path`, which now read through the op's connection), `submit`/`run` from the writer thread run inline, `run` from a `_DB_LOCK` holder raises `DatabaseWriterDeadlock`, and `get_active_writer()` routes such callers (and the flag-off and post-shutdown cases) to the direct path. Flag `GALLERY_DB_WRITER_ENABLED` (default true). **Fail-before** (`test_db_writer.py` on the unmodified code, `scratchpad/phase2a/fail_before.txt`): 37 failed / 0 passed (`ModuleNotFoundError: backend.metadata_store.db_writer`). **Pass-after**: 37/37, repeated 5x on Python 3.11 plus once on 3.13 with no flake; 8 mutations of the writer (reversed lanes, no savepoint rollback, no commit retry, no batch time budget, no lock guard, no producer gate, ...) each fail a test. |
| 2 | 2.2 | Done 2026-10-28 | Metadata writes through the writer: `claim_next_metadata_job` / new `claim_next_metadata_jobs(limit)` (one priority op claims up to K due jobs in single-claim order, own token and lease each; worker `GALLERY_METADATA_CLAIM_BATCH_SIZE`, default 1, buffers extra claims, renews them in the heartbeat and releases them on stop via `release_metadata_job_claims`), lease renewal (priority), **one op per job** (`MetadataLifecycleWorker._persist_and_complete`: claim fence + `upsert_metadata_batch` + `complete_metadata_job` + asset lookup, atomic), `fail`/`requeue`/`stale` through `_persist` (priority), supervisor `recover_abandoned_metadata_jobs` (normal). `run_write` holds the producer gate while submitting, so destructive maintenance still quiesces metadata producers. `upsert_metadata_batch` is writer-routed and joins the op's transaction when called on the writer thread; backfill scheduling and derivative reconciliation stay in the caller after the Future resolved. `DatabaseWriterUnavailable` counts as a transient job error (requeue, not fail). Flag off restores every previous direct path. **Fail-before** (`test_worker_contention_phase2_metadata.py` on the unmodified code): 13 failed / 1 passed / 16 errors; behavioural assertions: `saw 2 commits` per job (want 1) and `an upsert must not survive a failed completion`; the rest fail on the missing writer module / `claim_next_metadata_jobs`. **Pass-after**: 30/30 (flag on; 12 writer-only tests skip when `GALLERY_DB_WRITER_ENABLED=false`, the on/off parametrized ones run in both). Full Python 3.11 backend suite, flag on with coverage: 1,495 passed / 1 skipped / 1 failed (`test_validate_settings_unreadable_path`, pre-existing, sandbox user is root), coverage 90.86 %; flag off (`GALLERY_DB_WRITER_ENABLED=false`): 1,483 passed / 13 skipped / the same 1 failed. Existing test edited: `test_indexer_coverage.py::test_worker_run_job_raises_exception` also patches `db_writer._connect` (the writer opens its own connection); assertion unchanged. **H2** (`worker_contention_bench.py --phase 1`, flag on, 1,500 images, 36,000 `derivative_jobs`, exit 0): `status_p95_ms` 135.6, `polling_throughput_ratio` 0.937 (726 vs 775 jobs/120 s), `max_write_lock_hold_ms` 567.8 (5 spans over 250 ms, 0 over 1 s; Phase 1: 587.7), `database_locked_log_lines` 0, `lease_loss_failed_scans` 0, `orphan_running_metadata_jobs` 0, `superseded_ready_derivatives` 0. Metadata throughput without polling 775 jobs/120 s vs 560 in Phase 1 (+38 %). The Phase 2 write-lock target (<= 250 ms) is not met yet: derivative and catalog writes are still direct (2.3, 2.4). |
| 2 | 2.3 | Done 2026-11-01 (uncommitted on `fix/worker-lifecycle`, base `815d422`) | Derivative writes through the writer: claim (priority, one op), lease renewal (`_LeaseHeartbeat`, priority, no `_DB_LOCK` also flag off), completion and failure/retry/skip (priority, claim-fenced: a stale claim changes 0 rows inside the op), `schedule_derivative` (priority for job priority 0-1, i.e. the interactive HTTP request, which awaits the id; normal otherwise), `repair_derivative_consistency`, reconcile (normal; `reconcile_desired_derivatives` cuts its batches to `RECONCILE_OP_ASSETS`=25 assets per op, each op one transaction with its own `CapacityLedger`; superseded rows retired in the op and their files unlinked only after the Future resolved), `retire_superseded_derivatives`, `_reserve_capacity` (two ops with the unlink between), supervisor/startup recovery and queued-job reconciliation (candidates and file stats read outside the op), the render's `upsert_image_dimensions` (a hidden direct `_DB_LOCK` write on every render, found by the new tests) and `visual_fingerprints.notify_derivative_ready` (found by a transaction trace of the bench: the last direct write in the derivative worker). **HTTP path:** reads stay on plain connections; the only write of a warm hit, the `last_accessed_at` touch, is `db_writer.post_write` (normal lane, fire-and-forget, errors logged, dropped under maintenance/backpressure, inline with the flag off) and `release_serving` (a background task after the response) flushes the queued touch (<= 2 s). **Fail-before** (`scratchpad/phase2b/fail_before.txt`, unmodified `815d422` production code + the new modules): derivative 15 failed (e.g. `claim never reached the writer`, `a 130-asset pass must be split into several ops; saw []`, `a warm lookup must not wait for the writer`, `DID NOT RAISE OperationalError` for the failed-commit retirement, `a derivative claim must wait while maintenance holds the gate`), 6 guards pass. **Pass-after:** 21/21 flag on (also repeated 3x), 8 pass + 13 skipped flag off. |
| 2 | 2.4 | Done 2026-11-01 | Catalog writes through the writer, each store function split into `op(conn)` (no transaction control) + `run_write(op, lane, fallback)`; `_DB_LOCK` is taken only inside the flag-off fallback (`_db.run_direct_immediate`), never while waiting for the writer: `claim_next_catalog_job`, `update_job_state`, `renew_catalog_job_lease` (priority; the fallback no longer takes `_DB_LOCK`), `fail_abandoned_catalog_job_claim`, `update_parent_aggregate_job`, `create_or_coalesce_catalog_job` (priority; cancellation events published after the commit), `_bulk_index_records` (normal, claim assertion + upserts + claim refresh per op, <= 100 rows per op), `reconcile_library_assets`, metadata-job persistence of a scan (<= 100 paths per op), rebuild staging flush/delete, `recover_stale_jobs` (normal; candidates read on a plain connection, fenced failure writes one op); `activate_rebuild_staging` stays one atomic op by contract. `assert_catalog_job_claim` is a plain read. **Fail-before:** catalog 14 failed (e.g. a scan wrote outside the writer: `[('MainThread', 'INSERT INTO library_jobs '), ...]`, `enqueue never reached the writer`, `the claim's lease lapsed while _DB_LOCK was held elsewhere` in both modes, `a catalog claim must wait while maintenance holds the gate`). **Pass-after:** 21/21 flag on, writer-only tests skipped flag off. **WK-02 regression:** a heartbeat renews a 1 s lease while another thread holds `_DB_LOCK` past it. |
| 2 | 2.5 | Done 2026-11-01 | `runtime_counters(name, value)` (`metadata_jobs.<state>` x6, `derivative_ready_bytes`) maintained by **triggers** on `metadata_index_jobs` / `asset_derivatives` (chosen over writer ops: the counted rows change from dozens of sites incl. the flag-off paths, recovery, the integrity checker, destructive maintenance and raw SQL; a trigger is part of the statement and rolls back with a failed op). Additive: table + triggers in `_schema_ddl.py` (fresh DB) and `_schema_ensure._ensure_runtime_counters` (existing DB, backfilled when the table, a counter row or a trigger is missing; no version bump), `schema_check` reports a missing table/trigger. Unscoped `get_indexer_runtime_status`, `get_metadata_lifecycle_status` and `library_status.quota_used_bytes` read them inside their `_read_snapshot` (fallback to the aggregate if a counter is missing/negative); scoped reads and the pinned WK-01 queries in `build_global_runtime` (derivative/catalog counts) keep their aggregates. Integrity: `run_all_checks()["runtime_counters_repaired"]` recomputes, snapshot detection then a repair op only on drift. Tests: seeded randomized transitions (incl. rollbacks) == aggregates, real scan/metadata/derivative/integrity flows flag on and off, rolled-back writer op, destructive clear + catalog reset, tampered counter shows in status / scoped read aggregates, status identical from counters vs aggregates, one-snapshot read, integrity repair of drift and missing rows. `test_status_counters_equal_values_from_the_pre_change_implementation` passes unchanged. **Fail-before:** counters 12 failed (`runtime_counters is missing from a freshly initialized database`, `no such table`). **Pass-after:** 12/12. |
| 2 | Exit gate | Passed 2026-11-01 (with one writer-core addition) | `worker_contention_bench.py --phase 1`, flag on, 1,500 images + 36,000 `derivative_jobs`, exit 0 (two full runs, run 1 / run 2): `max_write_lock_hold_ms` 238.6 / 181.8 (<= 250; 0 spans over 250 ms in both; Phase 2A: 567.8), `status_p95_ms` 107.6 / 105.2, `polling_throughput_ratio` 0.927 / 0.986, metadata jobs/120 s without pollers 1,152 / 1,047 (Phase 2A: 775), `database_locked_log_lines` 0, `lease_loss_failed_scans` 0, `orphan_running_metadata_jobs` 0, `superseded_ready_derivatives` 0. Reaching 250 ms needed the **writer fairness yield** (`GALLERY_DB_WRITER_YIELD_MS`, 25 ms): a transaction trace of the bench showed the writer alone held the lock for 500-660 ms because a saturated writer commits and re-begins within microseconds, so an external poller never saw a gap although no single transaction exceeded ~150 ms; after >= `GALLERY_DB_WRITER_BATCH_MS` of back-to-back batches it now sleeps 25 ms (sparse traffic is never delayed). The same trace found the two last direct derivative-path writers (`upsert_image_dimensions`, `notify_derivative_ready`). Still direct and outside Phase 2.3-2.5 (Phase 3): the search-index worker (`search-index-writer`), library management, startup recovery and the integrity repair passes. Perf budgets (`scripts/internal/test-perf.sh`, baseline `815d422` -> after): thumbnail cold p95 153.0 -> 131.5 ms (<= 1000), warm 20.2 -> 14.0 (<= 50); preview cold 175.1 -> 165.7 (<= 1500), warm 30.8 -> 28.8 (<= 100); album_open scan p95 176 -> 98 (<= 2000), first thumbnail 243 -> 187 (<= 3000), warm batch 273 -> 180 (<= 800); lightbox open 69 -> 68 (<= 200), visual ready 960 -> 978 (<= 1000), transition 81 -> 109 (<= 200). The suite's search `album_heavy` (385-387 vs 300) and facets (3.2-3.5 s vs 3.0 s) fail identically on the baseline tree. Python 3.11 full backend suite, flag on with coverage: 1,549+ passed / 1 skipped / 1 failed (`test_validate_settings_unreadable_path`, pre-existing root), coverage 90.9 %; flag off: 1,514 passed / 36 skipped / the same failure. Ruff check/format, `./test.sh docs`, `./test.sh backend-api` (106 passed) pass. Multi-format equivalence (60 per format, 556 assets, flag on vs off, touch half + sidecar edits + rescan): `metadata_index_jobs`, `image_metadata`, `assets`, `asset_derivatives` status counts, latest `derivative_jobs` states, derivative files on disk (1,623), `library_jobs`, `runtime_counters` and the four status endpoints are IDENTICAL after both the first settle and the rescan. Existing tests edited: `test_catalog_claim_fencing.py` (3 tests) and `test_library_cleanup_audit.py` (1 test) pin `DB_WRITER_ENABLED=False` because they assert direct-transaction internals (connection per batch, patched `_connect`); their assertions are unchanged and the writer-path equivalents live in `test_worker_contention_phase2_catalog.py`; `test_integrity_checker_contract.py` lists the new `runtime_counters_repaired` key. |
| 3 | 3.1 Inventory | Done 2026-11-01 | 165 `_DB_LOCK` grep hits at `a0a7a97` (136 real sites in 121 functions): 63 READ → `_connect_read` / `_read_snapshot` / `_connect_readonly` (mode=ro, TEMP-table readers); 42 WRITE → `run_write` (priority: claims, leases, job transitions, `create_library`, `update_library_state`, search-index jobs, `upsert_image_dimensions`; normal: bulk, recovery, integrity, maintenance); 6 MIXED → plain read, then an op that re-checks inside. Guarantees beyond serialization: `create_or_get_active_scan_job`, the `create_library` overlap check and metadata upsert + completion are one op each; `cleanup_stale_index` re-checks inside its op; `_INIT_LOCK` serializes schema init only. |
| 3 | 3.2 Lock and flag removal | Done 2026-11-01 | `_DB_LOCK`, `_DatabaseLock`, `WriterThreadLockError`, `DatabaseWriterDeadlock`, `run_direct_immediate` and `GALLERY_DB_WRITER_ENABLED` deleted from production. `run_write` submits whenever a writer is active and never falls back (writer errors propagate); the only other write path is `db_writer.run_direct` (one `BEGIN IMMEDIATE`, no Python lock, refused with `DatabaseWriterActive` while a writer runs) for `init_db`, migrations, scripts and writer-less unit tests. The lifespan starts the writer first and stops it last. Startup recovery reads its repair plan on a snapshot and applies it in fenced ops of ≤ 250 rows (one op held the lock ~900 ms before). `SCAN_OP_ROWS` 100 → 50. |
| 3 | 3.3 Ownership check | Done 2026-11-01 | `scripts/check_db_write_ownership.py` in `./test.sh lint`: no writable connection, `BEGIN`/`COMMIT`/`ROLLBACK` statement, `.commit()`/`.rollback()`/`executescript` outside the writer, schema/migration and direct-path modules; write SQL (incl. f-strings and concatenation) only inside functions that take a connection. Flags 262 sites at `a0a7a97`, passes on the Phase 3 tree. `./test.sh unit` runs the backend suite twice (no writer, and `GALLERY_TEST_DB_WRITER=1`). New tests: `test_worker_contention_phase3.py` (15; 14 fail at `a0a7a97`, 1 at the 3.2 WIP) and `test_check_db_write_ownership.py` (45). |
| 3 | Exit gate | Passed 2026-11-01 | No `_DB_LOCK` in `backend/` outside tests; ownership check passes. Full backend suite (Python 3.11): 1,606 passed, 1 skipped in both modes, coverage 91.16 % / 91.13 % (only the root-sandbox `test_validate_settings_unreadable_path` deselected). `./test.sh lint`, `docs`, `backend-api` (106) pass. `./test.sh e2e`: 197 passed, 1 failed (`lightbox-loading-policy.spec.ts` "normal lightbox open uses thumbnail and preview without original", API fully stubbed; fails identically on `a0a7a97`, frontend unchanged since `main`). Perf budgets: 10/10 reports pass (search `album_heavy` 216 ms and `facets` 1.69 s now inside budget). H2 `worker_contention_bench.py --phase 1`: `max_write_lock_hold_ms` 181.4 / 161.7 / 161.3 (traced runs) and 181.6 (plain run, enforced budget now 250), 0 spans over 250 ms, `status_p95_ms` ≤ 102, `polling_throughput_ratio` ≥ 0.95, 1,238-1,497 metadata jobs/120 s, all zero-count budgets 0. Multi-format equivalence `a0a7a97` vs Phase 3: identical at both snapshots, 0 locked lines, 0 tracebacks. `scripts/perf_budgets.toml` `max_write_lock_hold_ms` tightened 1000 → 250. Residual risk: set-based ops (`activate_rebuild_staging`, `_unregister_library`, integrity repair op A) hold the write lock during their reads on very large libraries. |
