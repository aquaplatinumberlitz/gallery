# Architecture

Status: Maintained

Last reviewed: 2026-11-09

Historical Library Management V1 handoff context is retained in the
[archived implementation status](archived/CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_STATUS.md).

## Metadata Lifecycle

### Owner: `backend/indexer.py`

The metadata lifecycle owner is `MetadataLifecycleWorker` in `backend/indexer.py`,
modeled on `DerivativeScheduler` (`backend/derivative_scheduler/`). It owns
scheduling, dispatch, worker lifecycle, completion invariants, stale guards,
and startup recovery.

### DB-claim worker pattern

The worker claims jobs directly from SQLite — no in-memory queue bridges the
DB to the runtime. This mirrors how `DerivativeScheduler._claim_job()` claims
from `derivative_jobs`.

```
dispatch_metadata_index_paths(paths, priority)
  → _persist_metadata_index_jobs(paths, root_path, priority=priority)
    → INSERT/ON CONFLICT into metadata_index_jobs
  → metadata_worker.wake()

metadata_worker._worker_loop
  → claim_next_metadata_job()           [database writer, priority lane; one op]
    → SELECT metadata_index_jobs WHERE state='queued'
        AND (next_attempt_at IS NULL OR next_attempt_at <= now)
      ORDER BY priority ASC, queued_at ASC, path ASC LIMIT K
    → UPDATE state='running', attempts+1, started_at=now,
        claimed_by=<worker>, claim_token=<uuid>, lease_expires_at=now+lease
        (one token and lease per claimed job)
  → LeaseHeartbeat renews lease_expires_at while the job runs  [priority lane]
  → extract_metadata(path)  [outside any DB transaction]
  → ONE writer op per job, priority lane (atomic):
    → verify the claim token still owns the job (else write nothing)
    → upsert_metadata_batch([metadata])  [joins the op's transaction]
    → complete_metadata_job(conn, job)  [fenced by claim_token]
      → verify image_metadata current for job identity
      → verify matching asset row exists
      → UPDATE metadata_index_jobs state='done', claim cleared
      → UPDATE assets metadata_state='done'
  → after the op resolved: schedule derived-search backfills, reconcile derivatives
  → on failure: transient → requeue_metadata_job (backoff, next_attempt_at)
                otherwise → fail_metadata_job      [priority-lane writer ops]

metadata_worker supervisor (every GALLERY_METADATA_SUPERVISOR_INTERVAL_SECONDS)
  → restore dead worker threads
  → recover_abandoned_metadata_jobs(expired_only=True)
    → requeue (or fail, attempts exhausted) running jobs with an expired or missing lease
```

### Invariants

1. **SQLite is the runtime queue.** The worker claims from `metadata_index_jobs`,
   not from an in-memory `_job_queue`. Queued jobs survive process restart.

2. **Completion materializes both job and asset.** `complete_metadata_job` atomically
   marks the job `done` AND stamps `assets.metadata_state='done'`. If no asset
   row exists, the job is `skipped`. If the asset version differs, the job is `stale`.

3. **Extraction runs outside DB transactions.** Claim and complete are short
   writer transactions (see Database Writer). `extract_metadata`
   (PIL + JSON parsing) runs outside any transaction, matching
   `DerivativeScheduler._run_job`. Persisting `image_metadata` and completing the job
   are one writer op, so either both apply or neither (the no-active-writer path runs the
   same op in one direct transaction).

4. **Identity is the image plus its optional sidecar.** Image freshness uses
   `path + mtime_ns + size`; completion additionally requires the stored
   same-stem `.txt` identity (`path + mtime_ns + size`) to match. Sidecar create,
   replacement, modification, or deletion requeues extraction without requiring
   the image to change. Sidecars are opened with no-follow protection where
   supported, validated against the active image asset/import root/safety root,
   and read from one descriptor with a limit-plus-one bounded read. `library_id`
   is a secondary diagnostic field.

5. **A `running` job has a live claim or it is recoverable.** `claim_next_metadata_job`
   records `claimed_by`, a unique `claim_token`, and `lease_expires_at`
   (`GALLERY_METADATA_JOB_LEASE_SECONDS`, default 300). A heartbeat (the shared
   `LeaseHeartbeat` in `backend/lease_heartbeat.py`, also used by
   `DerivativeScheduler`) renews the lease at one third of its length while the
   job extracts; renewal is a priority-lane writer op.
   Completion, failure, stale, requeue, and renewal writes only change a row that
   is still `running` under the worker's claim token, so a worker whose claim was
   recovered and reissued writes zero rows (and neither stamps the asset nor
   rewrites the newer claim). A `running` row with no token, no lease, or an
   expired lease is an orphan, for example when the failure write itself hit
   `database is locked`.

6. **Transient errors retry, parse errors do not.** `sqlite3.OperationalError`
   locked/busy errors and `OSError` with `EAGAIN`/`EBUSY`/`EINTR` requeue the job
   with exponential backoff (`GALLERY_METADATA_RETRY_BASE_SECONDS` x 2^(attempts-1),
   capped at 60 s) stored in `next_attempt_at`; claims ignore rows that are not
   yet due, and a rescan that coalesces into the queued retry does not reset it.
   After `MAX_METADATA_JOB_ATTEMPTS` the job fails. Parse and format errors
   (unreadable image, oversized sidecar, vanished file) fail immediately. An unreadable
   image is `UnreadableImageError` from `extract_metadata` (also when a same-stem sidecar
   exists): the job ends `failed`, no `image_metadata` row is written, and the asset counts
   in `metadata.failed_assets`. `GET /api/metadata` answers `422 image_unreadable` for it
   and persists nothing; the lightbox panel shows "This file can't be read". The
   failure or requeue write is itself retried a bounded number of times (0.1, 0.5,
   1 s) so one locked write cannot orphan the job; if it still fails, the lease
   recovers the job.

7. **A supervisor recovers orphans without a restart.** `MetadataLifecycleWorker`
   owns a `gallery-metadata-supervisor` thread (30 s by default,
   `GALLERY_METADATA_SUPERVISOR_INTERVAL_SECONDS`) that restores dead worker
   threads (never starting a worker that was not started) and calls
   `recover_abandoned_metadata_jobs(expired_only=True)`: expired or ownerless
   `running` rows go back to `queued`, or to `failed` once their attempts are
   exhausted, while live unexpired claims are never touched. The supervisor is
   stopped by `MetadataLifecycleWorker.stop()` inside its existing bounded join, so
   the app lifespan needs no extra registration.

### Metadata writes through the database writer

Phase 2 of the worker lifecycle hardening plan moves the metadata worker's writes
onto the single database writer (next section). Every op below is fenced exactly as
before (claim token, identity):

| Call path                                                                        | Writer op                                              | Lane       |
| -------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------- |
| `claim_next_metadata_job` / `claim_next_metadata_jobs(limit)`                    | claim up to K due jobs, one token and lease each       | `priority` |
| `MetadataLifecycleWorker._renew_lease` (heartbeat)                               | fenced lease renewal of the job and of unstarted claims | `priority` |
| `MetadataLifecycleWorker._run_job`                                               | claim fence + `upsert_metadata_batch` + `complete_metadata_job` + asset lookup | `priority` |
| `_persist` for `fail_metadata_job`, `requeue_metadata_job`, `mark_metadata_job_stale` | the fenced terminal write                          | `priority` |
| `release_metadata_job_claims` (a stopping worker's unstarted batch claims)       | requeue without consuming an attempt                   | `priority` |
| `recover_abandoned_metadata_jobs` (supervisor)                                   | `recover_running_metadata_jobs(expired_only=True)`     | `normal`   |

Startup recovery (`recover_metadata_index_jobs`), the integrity checker's repair
passes, library management, the search-index and fingerprint stores and destructive
maintenance are writer ops as well (Phase 3, see Write ownership below), as are the
derivative and catalog writes (including the metadata job creation a scan performs
through `dispatch_metadata_index_paths`).

`GALLERY_METADATA_CLAIM_BATCH_SIZE` (default 1) lets one claim op take several jobs
in single-claim order. The extra jobs wait in the claiming worker's buffer; the
running job's heartbeat renews their leases, and a stopping worker releases them
(`release_metadata_job_claims`) without consuming an attempt.

Inside a writer op, `upsert_metadata_batch` joins the op's transaction and does not
schedule derived-search backfills (scheduling submits writes of its own and must not
run inside an op); the worker schedules them after the op resolved. `get_library_for_path` and
`get_asset_state_for_path` (reached from the sidecar identity check inside
`complete_metadata_job`) read through the writer connection when called from an op.

### Legacy fallback

For rows created before `mtime_ns` was populated, the system falls back to
comparing `mtime` (float seconds) with `assets.mtime_ns / 1e9` using a 1 ms
tolerance.

### Startup recovery

`recover_metadata_index_jobs()` resets interrupted `running` jobs to `queued`,
fails jobs whose attempts have been exhausted, and repairs `done` jobs whose
asset state never materialised. It also demotes `done` jobs whose sidecar
identity changed. Queued jobs are left claimable — they survive restart because
SQLite is the queue. The `running` reset is the same function the supervisor uses
(`recover_running_metadata_jobs`), called with `expired_only=False` because after a
restart no worker can own a claim; claim columns are cleared by every recovery.

Recovery keeps the write lock short: the running reset is one normal-lane op, while what
decides the two repairs (one `image_metadata` lookup plus a sidecar stat per `done` job, a
file stat per asset with a legacy seconds-valued mtime) is read on a snapshot
(`plan_inconsistent_asset_repairs`, `plan_legacy_asset_mtime_repairs`) and only the
identity-fenced UPDATEs run as normal-lane ops of at most `RECOVERY_OP_ROWS` (250) rows
(`apply_inconsistent_asset_repairs`, `apply_legacy_asset_mtime_repairs`). The old single
transaction held the write lock for ~900 ms on the 1,500-job benchmark database once the
writer wrapped it in `BEGIN IMMEDIATE`; the repairs are idempotent, so chunks that
commit independently only leave the remainder to the next start.

### Diagnostics

`get_metadata_lifecycle_status(scope_path)` returns 15 counters covering job
queue depth, inconsistency detection, worker health, and throughput. These are
included in the status API envelope as `metadata_lifecycle`.

### Status reads take no lock

Status is read-only and must never stall a worker. `build_catalog_status`,
`build_library_status_batch`, `build_global_runtime`,
`get_indexer_runtime_status`, `get_metadata_lifecycle_status`,
`DerivativeScheduler.library_status`, and the watcher-root lookup behind
`get_watcher_status` read through `_read_snapshot()`
(`backend/metadata_store/_db.py`): a dedicated `query_only` WAL connection with
one explicit deferred read transaction, rolled back and closed on exit. The
process-wide lock that used to serialize reads and writes (`_DB_LOCK`) was retired in
Phase 3, so a slow status query can neither queue behind nor block a writer, and every counter in one response (including
the `global_runtime` and `metadata_lifecycle` blocks of the same envelope) comes
from one consistent snapshot. Counter semantics are unchanged: only the
connection and transaction handling differ from the previous locked reads.

`derivative_jobs` carries `idx_derivative_jobs_derivative_id (derivative_id, id)`
(fresh DDL plus the additive ensure path, no catalog version bump). The global
runtime and per-library derivative counters pick the latest job per derivative
with `max(id)`, and reconcile coalescing reads the latest job per derivative;
without this index each lookup scanned the whole job table (35 s for the
global runtime query at 36,000 rows). Maintenance runtime reuses one snapshot
for `global_runtime` and `metadata_lifecycle`.

### Integrity checker

`backend/integrity_checker.py` runs a periodic background consistency pass when
`GALLERY_INTEGRITY_CHECK_ENABLED` is true. It repairs, re-queues, or marks failed
mismatches between `assets`, `image_metadata`, `metadata_index_jobs`,
`asset_derivatives`, and `derivative_jobs`, including missing derivative cache
files, active metadata jobs whose source file or asset row disappeared, and
ownerless/mismatched media rows in `file_index` that search cannot safely
authorize. Each daemon or manual run persists a summary into
`integrity_check_runs`, which backs the Maintenance file-health API.

The metadata checks do not preserve `running` rows forever: a pass first requeues
(attempt-aware) every `running` metadata job whose claim is expired or ownerless,
and metadata dispatch does the same for the path it is about to coalesce. A live,
unexpired claim stays protected and is coalesced as before. Changing a file while
its job runs requeues the row and clears the claim, which fences the old worker.
The same pass retires superseded `ready` derivatives (see Derivative Lifecycle) and
recomputes the runtime counters, repairing any drift (see Database Writer).

Repairs run as bounded writer ops. `run_all_checks()` is one normal-lane op for the
metadata/catalog row repairs, then reads the derivative candidates on one snapshot and
applies each derivative repair family in chunks of at most `_REPAIR_CHUNK_ROWS` (250)
rows per op (`_apply_in_chunks`); every repair write is fenced on its row's own state, so a
row that changed between the snapshot and the op is skipped rather than overwritten.
`run_and_persist` writes its summary row as one op. The reconcile pass that follows is
the derivative scheduler's own chunked ops.

Destructive imported-data maintenance holds a shared producer gate across the
operation. Metadata dispatch, metadata workers, derivative scheduling and
reconciliation, integrity repair, and catalog queue producers cannot create new
work while the gate is held. After in-flight producers are quiescent, durable
active work is rechecked; derivative and catalog database rows are then deleted
in one transaction, and cache files are removed only after commit. Releasing the
gate resumes paused producers.

## Database Writer

### Owner: `backend/metadata_store/db_writer.py`

`DatabaseWriter` is the storage pattern of the single-process deployment: workers do
their CPU and I/O in parallel, but SQLite writes are handed to one thread that owns
one write connection (opened like `_connect()`: WAL, `synchronous=NORMAL`,
`busy_timeout=5000`, `foreign_keys=ON`, in autocommit mode so transactions are
explicit). Jobs themselves stay in SQLite; the writer buffers pending *writes* only.

```
worker thread                          gallery-db-writer thread
  run_write(op, lane=...)  ── Future ──▶  BEGIN IMMEDIATE            (one per batch)
  (waits for the result)                    SAVEPOINT gw_op; op(conn); RELEASE   (one per op)
                                            ... more ops while queued, < batch size / time budget
                                          COMMIT
                         ◀── result ───   resolve every Future after the commit
```

* **API.** `submit(op, *, lane="normal") -> Future`; `run(op, ...)` submits and waits;
  `op(conn)` runs inside the batch transaction under its own savepoint. A failing op
  rolls back only its savepoint and its exception object is set on its own Future; the
  other ops of the batch commit. A Future resolves only after its batch committed.
* **Lanes and order.** `priority` (claims, lease renewals, terminal job writes) is
  drained before `normal`; FIFO inside a lane. A batch pulls ops in that order and can
  mix both lanes.
* **Batching.** A batch holds at most `GALLERY_DB_WRITER_BATCH_MAX` ops (50) and stops
  taking ops once its transaction has been open `GALLERY_DB_WRITER_BATCH_MS` (100 ms).
  The writer never waits for more ops when its queue is empty, so batching adds no
  latency: ops batch up only while the previous batch is committing.
* **Commit failure.** `database is locked`/`busy` at `BEGIN IMMEDIATE` or `COMMIT`
  rolls the batch back and re-runs it from scratch after short pauses (0.05, 0.25,
  1 s); when the retries are exhausted, or the error is not transient, every op of the
  batch fails with that error. No Future is ever left unresolved, including for a
  `BaseException` raised by an op (the writer then closes).
* **Fairness yield.** A saturated writer commits a batch and starts the next within
  microseconds because producers keep the queue filled, so the write lock would be held
  continuously for seconds although every transaction is short, and a writer outside it
  (an external connection, a script or a database tool) polls the lock with SQLite's
  sleeping busy handler and starves. After a stretch of at least
  `GALLERY_DB_WRITER_BATCH_MS` of back-to-back batches the writer sleeps
  `GALLERY_DB_WRITER_YIELD_MS` (25 ms) with the lock released, so the longest continuous
  hold is about one batch. A writer that was idle for a full yield starts a fresh stretch,
  so sparse traffic never waits; the pause is skipped while stopping.
* **Backpressure.** Each lane is bounded (`GALLERY_DB_WRITER_QUEUE_MAX`); `submit`
  blocks up to `GALLERY_DB_WRITER_SUBMIT_TIMEOUT_SECONDS` and then raises
  `DatabaseWriterBackpressure`. The priority lane has its own capacity, so a full
  normal lane never blocks a lease renewal.
* **Lifecycle.** `_lifespan` registers the writer in `_LifecycleRegistry` before startup
  recovery and before the catalog, metadata, search, integrity and derivative services,
  so it starts first and, by the registry's reverse unwind, stops after all of them.
  `stop()` rejects new ops immediately (`DatabaseWriterClosed`), drains queued ops until
  `GALLERY_DB_WRITER_SHUTDOWN_TIMEOUT_SECONDS`, then fails what is left. Nothing starts
  the shared writer implicitly: `get_active_writer()` never auto-starts it.
* **Crash safety.** The writer holds no durable state. A writer that dies between
  batches leaves jobs `running` under their Phase 1 leases; the metadata supervisor
  requeues them after expiry, and the atomic upsert + completion op means no job is
  ever `done` without its `image_metadata`.

**The only write paths.** Every SQLite write in `backend/` is an *op*: a function of a
connection with no transaction control. `run_write(op, *, lane)` (`db_writer.py`) is the
one entry point:

* **A writer is active** (`database_writer.state` is `running` or `stopping`): the op is
  submitted and `run_write` waits for its Future. It never falls back to another path;
  `DatabaseWriterClosed`, `DatabaseWriterBackpressure`, `DatabaseWriterTimeout` and the
  op's own exceptions propagate to the caller. On the writer thread the op runs inline in
  the current transaction under a nested savepoint.
* **No writer is active** (`idle` or `stopped`: `init_db` and migrations before the
  lifespan starts the writer, the CLI scripts under `scripts/`, plain unit tests):
  `run_direct` runs the op in one direct `BEGIN IMMEDIATE` transaction on a fresh
  connection configured like the writer's, with no Python lock; it commits on success and
  rolls back on any exception, and a nested op joins the outer transaction under a
  savepoint. `run_direct` raises `DatabaseWriterActive` when a writer is active, so the
  direct path is impossible next to the writer. The path lives only in `db_writer.py`
  (and `_db.py`'s connection factories).
* **Reads** never go through either: `_connect_read()` / `_read_snapshot()` open
  `query_only` WAL connections (`_connect_readonly()` is a `mode=ro` one for the facet
  and raw-workflow queries that need TEMP tables). From inside an op, code that must see
  the op's own uncommitted rows reads through `writer_connection()`.

**Connection lifecycle rule (BL-14).** Every SQLite connection is closed
deterministically by the code that opens it; nothing is left to garbage collection.
`with sqlite3.connect(...) as conn:` only commits or rolls back and never closes, so it
is not used. Instead:

* Every connection opened through `_db.py` (`_connect`, `_connect_read`,
  `_connect_readonly`, `open_connection`) is a `ClosingConnection`: `with` commits (or
  rolls back on error) and then closes it. A failure while configuring a new connection
  closes it before the error escapes. Do not use `with conn:` on a connection you mean to
  keep using.
* Long-lived connections are closed explicitly and never used as context managers: the
  writer thread's connection (`DatabaseWriter._drop_connection` on stop, abort, a path
  change or a failed rollback) and the direct write path's per-op connection
  (`run_direct`, closed in `finally`).
* One-off files (the `*.bak` migration backups) use `contextlib.closing`.
* The thumbnail `diskcache` index opens one connection per thread and its own `close()`
  only closes the caller's; `backend/disk_cache.py` (`ThreadClosingCache`) closes each
  thread's connection when that thread ends, and at interpreter exit for the main thread.
* Tests follow the same rule. `backend/tests/test_connection_lifecycle.py` repeats the
  migration backups, read helpers, search, browse and status stores, derivative and
  metadata-job paths and the writer start/stop cycle, and asserts zero open connections
  and a stable `/proc/self/fd` count. The pytest config turns
  `ResourceWarning: unclosed database` into an error (see `docs/testing/README.md`).

There is no process-wide Python lock around SQLite: `_DB_LOCK`, `_DatabaseLock`,
`WriterThreadLockError`, `DatabaseWriterDeadlock` and the `GALLERY_DB_WRITER_ENABLED` flag
were removed in Phase 3. Guarantees that the lock used to give beyond serializing writes
live in the op itself (a read-then-write that must be atomic is one op that re-checks
inside it; for example `cleanup_stale_index` re-validates its candidates in the op and
`upsert_metadata_batch` plus `complete_metadata_job` are one op) or in a dedicated lock
for Python state (`_INIT_LOCK` serializes schema initialization). Anything that
submits writes of its own (scheduling backfills, derivative reconciliation) runs in the
caller after the Future resolved, never inside an op.

**Maintenance gate.** `run_write` submits and waits while holding the shared producer
gate (`producer_gate()`), so destructive maintenance quiesces writer-backed producers:
an op in flight keeps `maintenance_gate()` from starting (`MaintenanceGateBusy`), active
maintenance holds new ops back, and the maintenance owner may still write.

**Ownership check.** `scripts/check_db_write_ownership.py` (run by `./test.sh lint`)
walks the syntax tree of every production module under `backend/` and fails when code
outside `metadata_store/db_writer.py`, `_db.py` and the schema/migration modules
(`_schema.py`, `_schema_ddl.py`, `_schema_ensure.py`, `_migrations.py`) opens a writable
connection (`_connect`, `sqlite3.connect`), calls `.commit()`/`.rollback()`/`executescript`,
spells out `BEGIN IMMEDIATE` (or a bare `BEGIN`/`COMMIT`/`ROLLBACK`/`END`), or contains
write SQL (`INSERT`/`REPLACE`/`UPDATE ... SET`/`DELETE FROM`/DDL, also in f-strings and
`+` concatenations) outside a function that takes a connection parameter. Run against the
Phase 2B tree it flagged 262 sites; it passes on the Phase 3 tree.

The writer thread and the SQLite write lock still serialize writes; `busy_timeout`
plus the batch retry cover contention from an external connection.

### Derivative writes through the writer

Every write of `backend/derivative_scheduler/` is a writer op (each used to be its own
`BEGIN IMMEDIATE`). The bodies are functions of a connection, so the no-active-writer path
runs the same code in a direct transaction.

| Call path                                                                 | Lane       | Notes |
| ------------------------------------------------------------------------- | ---------- | ----- |
| `_claim_job` (one op per claim)                                           | `priority` | the idle queued-job reconciliation reads first and only writes when it finds work |
| `_renew_lease` (the `_LeaseHeartbeat`)                                    | `priority` | |
| completion (`_run_job`) and failure/retry/skip (`_handle_failure`)        | `priority` | fenced by claim token: a stale claim changes 0 rows inside the op |
| `schedule_derivative` with job priority 0-1 (interactive HTTP request)    | `priority` | awaited: the request needs the derivative id |
| `schedule_derivative` with job priority 2-3, `repair_derivative_consistency` | `normal` | |
| `reconcile_desired_derivatives` batches, capacity-deferred coalesce       | `normal`   | one op per batch of at most 25 assets (`RECONCILE_OP_ASSETS`), each with its own `CapacityLedger`; superseded rows retired in the same op, their files unlinked only after the Future resolved |
| `retire_superseded_derivatives` (500 rows per op)                         | `normal`   | unlink after the op resolved; serving protection unchanged |
| `_reserve_capacity` / quota enforcement                                   | caller's lane | two ops (select + evict, finalize) with the unlink between them |
| `_recover_running_jobs`, `_reconcile_queued_jobs` (supervisor, startup)   | `normal`   | candidates and file stats are read outside the op; the fenced updates are one op |
| `thumbnails._record_image_dimensions` -> `upsert_image_dimensions`        | `priority` | awaited; skipped when `image_dimensions_unchanged` finds the catalog already holds the values (one read, no op) |
| sibling claim (inside the worker's `_claim_job(batch=True)` op, or `_claim_siblings`) | `priority` | each sibling gets its own `claim_token` and lease, see "Sibling batching" |
| `_release_claims` (a preempted background batch)                          | `priority` | fenced by claim token; clears token and lease, hands the attempt back, see "Preemption" |
| coalesced `last_accessed_at` touches (`flush_touches`)                    | `normal`, fire-and-forget | one op per window, see below |

**HTTP request path.** Thumbnail, preview and image requests keep their reads on plain
connections and never wait for a batch to commit: the only write of a warm hit, the
`last_accessed_at` touch (at most once per 60 s per file), is queued with
`db_writer.post_write` (normal lane, no `.result()`, errors logged, dropped while
maintenance holds the gate or the lane is full, applied inline on the no-active-writer path). It
only orders LRU eviction. Touches are coalesced: they collect in memory (newest time per
derivative) and are written as one `executemany` op per 5 s window
(`LookupMixin._TOUCH_COALESCE_SECONDS`). The first touch after a quiet period is written at
once; later ones are flushed by the next touch after the window, the supervisor tick,
`flush_touches()`, an eviction pass (applied inside the `select_and_evict` op, so a file that was
just served is never picked as least recently used) and `DerivativeScheduler.stop()` (which runs
before the writer stops). A touch whose op was dropped goes back to the pending set. The queued
Future of the op that carried a file's touch is remembered per cache path and
`release_serving` (a background task after the response completed) waits up to 2 s for
it, so the touch is durable before the serving lease is released. A cold request's
interactive `schedule_derivative` is the one awaited priority op.

### Image pipeline: generation, versioned URLs, serving fast path

`docs/archived/IMAGE_PIPELINE_PLAN.md` (Track B) added four backend behaviours.

**Sibling batching (B1).** `_run_job` first calls `_claim_siblings`: one priority-lane writer op
that claims the other still-`queued` jobs of the same asset and the same source identity
(`source_mtime_ns`/`source_size`, up to 8), each with its own `claim_token`, attempt count and
lease. `_run_batch` then decodes the source once (`thumbnails.render_derivatives`) and renders the
variants as a cascade: the requested variant first (a waiting HTTP request is not held back), the
rest largest to smallest, each resized from the smallest image already produced that is large
enough (preview -> `thumb_512` -> `thumb_256` -> `thumb_128`) and otherwise from the decoded
source. Every variant is then handled exactly like a single job: its source identity is
revalidated, its completion is the same `_complete_claim` writer op fenced by its own claim token
(a claim recovery took away changes 0 rows), and a failure goes through `_handle_failure` for that
claim only. One `_LeaseHeartbeatGroup` renews every still-open claim. No new queue exists; a job
with no queued sibling takes the previous single-variant path unchanged. Workers claim the leader
and its siblings in one writer op (`_claim_job(worker_id, batch=True)`), so workers that wake
together cannot each take one variant of the same asset and decode it separately; the siblings are
handed to `_run_job` through `_prefetched_siblings`, and a job claimed without `batch` (tests,
`_claim_job()` callers) finds its siblings in `_run_job` instead. An interactive leader (priority
0-1) only takes interactive siblings.

**Preemption and interactive headroom.** A background batch (leader priority 2-3) holds a worker
for a whole cascade, seconds under load, so the claim order alone did not keep interactive work
from waiting behind it. After every variant `_batch_should_yield` does one plain read (no write
lock): is a runnable priority 0-1 job queued, or did a request raise the priority of a variant
this batch has claimed but not rendered (with other claims still open)? If so the batch stops
after the variant it was rendering, `_release_claims` returns the unrendered siblings to
`queued` in one fenced writer op (`state='running'` and the batch's own claim token required;
token, lease and `started_at` cleared; the attempt the claim counted is handed back on both the job
and derivative row, status back to `queued`), and `_run_job` returns, so the worker's next claim is
the interactive job. A released claim has no token any more, so the preempted worker cannot complete
it, and its next owner gets a fresh token. A request for a variant that a running batch already
claimed is covered by the same rule (the batch yields, the requested variant is then claimed at
priority 0 on its own). Headroom is therefore a bound, not a reserved worker: every worker is back
at the claim query after at most the variant it is encoding (a single non-batched background job is
one variant long too), whatever `DERIVATIVE_WORKER_COUNT` is. A reserved worker that never takes
background work was rejected because it cuts background throughput by 1/N (a third with the default
three workers) for a case the bound already covers. Waiting HTTP requests poll the catalog with a
growing interval (30 ms up to 0.4 s) rather than every 50 ms, because dozens of pollers starved the
render workers of the GIL. All WebP derivatives use
libwebp `method=4` (about 2x faster than `method=6` for about 7 % more bytes). The bytes behind an
existing derivative URL are interchangeable (same dimensions and quality setting), so
`DERIVATIVE_CACHE_VERSION` stays `v3`: bumping it would only change ETags and file names without
regenerating anything. A render also skips the source-dimension upsert when the catalog already
holds the values (`image_dimensions_unchanged`).

**`thumb_256` (B2).** `DERIVATIVE_VARIANTS["thumbnail"]` is `thumb_128`, `thumb_512`, `thumb_256`
(the first entry remains the scheduling default); `/api/thumbnail` accepts `max_long_edge` 128, 256
and 512. Reconcile, warm-up, integrity and status treat it like any other configured variant.

**Versioned URLs (B3).** Browse (`FileNode`), search (`SearchMediaResult`, also the related
results) expose `content_version` (`"<mtime_ns>-<size>"` of the asset, `null` for folders or
unknown identities) and folders (`FileNode`, `SearchAlbumResult`, the browse virtual root) expose
`cover_versions`, aligned index-for-index with `cover_images` (`""` for a cover without a recorded
identity). `/api/thumbnail` and `/api/preview` accept an optional `v`. When `v` equals the source's
`"<st_mtime_ns>-<st_size>"` on disk at request time the response (200 and 304) carries
`Cache-Control: public, max-age=31536000, immutable`; with the same ETag, an absent, malformed or
stale `v` keeps `public, max-age=0, must-revalidate`.

**Browse covers (MD-01, UX-3).** A folder in `/api/browse` carries up to 3 `cover_images` with aligned
`cover_versions`, ranked `mtime_ns DESC, path ASC` and read by `_browse_folder_counts_batch_conn` (one
aggregated direct-child query plus, for the folder listing only, one ranged descendant query per batch of up
to 300 folders; no per-folder queries).

- A cover is a readable image. An asset is skipped when `assets.metadata_state = 'failed'`, when a `failed`
  `metadata_index_jobs` row exists for its current `mtime_ns`/`size` (the outcome of `fail_metadata_job` for an
  undecodable file), or when a `thumbnail` derivative of the current identity ended `failed` with the terminal
  `invalid_source` result code. Retryable failures (`attempts_exhausted`, `internal_error`) do not hide a
  cover; a changed file has a new identity and is judged again. The failed sets are read once per query
  (`cover_unreadable` CTE), so the check costs the same on a large subtree. A fresh scan has no failure signal
  yet: a corrupt file can be a cover until its metadata job has run.
- A folder whose direct images are all unreadable has no covers (the placeholder is shown). `image_count`
  still counts every direct image.
- A folder with no direct images (only subfolders) takes its covers from its descendants (any depth), under
  the same readability rule and ordering. The range is `path >= '<folder>/' AND path < '<folder>0'` on
  `assets(library_id, path)`, so the cost is bounded by the subtree size of the folders on the page. The
  virtual root (import roots) and search albums do not use descendant covers, so their latency is unchanged.

**Serving fast path (B4).** `backend/derivative_fastpath.py` holds a bounded in-process LRU
(`GALLERY_DERIVATIVE_FASTPATH_ENTRIES`, default 4096) from (metadata database, requested path or
asset id, kind, variant) to (source path, source identity, asset id, derivative id, cache file,
ETag). A hit skips the authorization read, `find_asset_id` and the ready-derivative read. It is
validated on every hit by the `stat()` of the source (a different `st_mtime_ns`/`st_size` or a
missing file drops the entry, so a superseded source can never be answered with its old derivative)
and by `scheduler.try_acquire_serving`, which checks that the cache file still exists and takes the
serving lease under the same lock eviction and supersession use. What a stat cannot see is a
catalog-side deactivation (library removed, asset marked offline/deleted) that leaves the file in
place: entries therefore expire after `GALLERY_DERIVATIVE_FASTPATH_TTL_SECONDS` (default 5), so such a
change is honoured within that bound. Setting either variable to 0 disables the fast path.

### Catalog writes through the writer

The catalog scan and rebuild pipeline (`backend/scan_worker.py` and the store modules
it calls) writes only through writer ops. Each store function is split into a body
`op(conn)` without transaction control and a `run_write(op, lane=)` call.

| Call path                                                                    | Lane       | Notes |
| ---------------------------------------------------------------------------- | ---------- | ----- |
| `claim_next_catalog_job`                                                      | `priority` | one op |
| `update_job_state` (progress, terminal state, library state)                  | `priority` | claim-fenced |
| `renew_catalog_job_lease` (`_CatalogLeaseHeartbeat`)                           | `priority` | WK-02 root cause: no longer queues behind unrelated readers or writers |
| `fail_abandoned_catalog_job_claim`, `update_parent_aggregate_job`              | `priority` | |
| `create_or_coalesce_catalog_job` (queue scan/rebuild)                          | `priority` | cancellation events are published after the op committed |
| `_bulk_index_records` (scan upserts: `file_index`, FTS, `assets`)              | `normal`   | claim assertion + upserts + claim refresh per op, at most 50 rows (`db_writer.SCAN_OP_ROWS`); the upsert is `upsert_catalog_records_conn`, shared with rebuild activation |
| `reconcile_library_assets`                                                    | `normal`   | |
| `_persist_metadata_index_job_batch` (metadata jobs of a scan)                  | `normal`   | at most 50 paths per op |
| `enumerate_to_rebuild_staging` flushes, `delete_rebuild_staging*`              | `normal`   | |
| `activate_rebuild_staging`                                                    | `normal`   | one atomic op by contract (a failed activation leaves the canonical generation and staging untouched), so a very large library holds the write lock for the whole merge; upserts through the same `upsert_catalog_records_conn` as a scan |
| `recover_stale_jobs` (supervisor, startup)                                     | `normal`   | candidates read on a plain connection; fenced failure writes are one op |

`assert_catalog_job_claim` and reads such as `get_library` are plain WAL reads.

Scan and rebuild build and persist catalog records through one shared path in
`metadata_store/file_index.py`, so a rebuilt catalog serves the same contracts as a scanned one:

- `build_folder_record` and `build_asset_record` turn a `stat` result into a `CatalogRecord`
  (`file_index` and `assets` columns, including `mtime`, `mime_type` and, for videos, the ffprobe
  `width`, `height`, `duration_ms` and `codec` from `probe_video_metadata`). The scan walker
  (`index_directory_tree`) and the rebuild staging walker (`enumerate_to_rebuild_staging`) both call them;
  the rebuild probes videos during enumeration, outside any write transaction.
- `upsert_catalog_records_conn` is the only SQL that writes catalog rows (`file_index`,
  `file_index_fts`, `assets`). The scan calls it per bounded batch; rebuild activation calls it once, inside
  its single atomic transaction, with `last_seen_scan_job_id` set to the rebuild job.
- `catalog_rebuild_entries` stages the full record (it carries `mtime` as well as `mtime_ns`).
  `backend/tests/test_rebuild_scan_parity.py` asserts that scan and rebuild leave equal rows.

### Write ownership (Phase 3)

Phase 3 moved the remaining writers onto the same path and made every read a plain WAL
read. The write lanes: `priority` for anything a request, a lease or a claim waits on,
`normal` for bulk and maintenance work.

| Area (module)                                                                                 | Lane | Notes |
| --------------------------------------------------------------------------------------------- | ---- | ----- |
| search-index store (`search_index_store`): create job, claim, lease renewal, finish, cancel   | `priority` | |
| search-index state, batch extraction records, `recover_search_index_jobs`                     | `normal`   | one op per extracted asset; the worker walks keyset batches of at most 200 assets |
| library management (`library_store`): `create_library`, `update_library_state`                | `priority` | |
| `update_library` (scope/rename), `unregister_library`, `forget_offline_library_assets`       | `normal`   | cache files are unlinked after the op resolved |
| startup recovery: `recover_stale_jobs`, `recover_metadata_index_jobs`, `recover_search_index_jobs` | `normal` | the lifespan starts the writer first |
| integrity checker repair passes                                                               | `normal`   | bounded ops, see Integrity checker |
| metadata persistence (`metadata_persist`), folder index state, `index_file`, ignored/stale index cleanup | `normal` (`upsert_image_dimensions` `priority`) | `cleanup_stale_index` re-checks inside the op |
| scheduled-refresh bookkeeping (`mark_scheduled_refresh_attempt`)                              | `normal`   | |
| destructive imported-data maintenance, catalog reset                                          | `normal`   | under the maintenance gate |
| visual-fingerprint invalidation (`notify_derivative_ready`)                                   | `normal`   | the backfill is scheduled after the op |

Facet queries and raw workflow search read through `_connect_readonly()`; every other
read path (browse, folder index, library listing, inspector, search, related assets,
prompt and workflow discovery, health) uses `_connect_read()` or `_read_snapshot()`.

### Runtime counters

`runtime_counters(name, value)` holds the status counts that used to be recomputed by
aggregate queries on every poll: `metadata_jobs.<state>` for the six metadata job states
and `derivative_ready_bytes`. They are maintained by **SQLite triggers** on
`metadata_index_jobs` and `asset_derivatives` (`_schema_ddl.RUNTIME_COUNTERS_STATEMENTS`)
rather than by writer ops: the counted rows are changed from dozens of sites (writer ops,
the no-active-writer direct transactions, recovery, the integrity checker, destructive
maintenance, migrations), and a trigger is part of the changing statement, so it is exact
for all of them and rolls back with a failed op's savepoint. `INSERT OR REPLACE` with
recursive triggers off would bypass them (no production code uses it), a database
written by an older release has no triggers, and a bug could drift a value, so
`runtime_counters.verify_runtime_counters` recomputes them from the source tables: the
additive ensure backfills a database that lacks the table, a counter row or a trigger
(no catalog version bump), and every integrity pass repairs drift
(`run_all_checks()["runtime_counters_repaired"]`; detection reads a snapshot, only a
drifted database runs a repair op). Readers (`get_indexer_runtime_status` and
`get_metadata_lifecycle_status` for an unscoped read, `DerivativeScheduler.library_status`
for `quota_used_bytes`) read the counters inside their existing `_read_snapshot` and fall
back to the aggregate query when a counter is missing or negative, so status responses
are identical for the same database state. Scoped reads, per-library coverage joins, the
diagnostic mismatch counters, and the `build_global_runtime` derivative/catalog queries
keep their aggregates (the latter are pinned by the WK-01 regression tests and are index
backed).

## Derivative Lifecycle

### Owner: `backend/derivative_scheduler/`

`backend.derivative_scheduler` is a package whose `__init__.py` re-exports
`DerivativeScheduler`, the process-wide `scheduler` singleton, `derivative_variant`, and the
reconcile/repair summary dataclasses, so existing import paths are unchanged. `core.py` composes
`DerivativeScheduler` from cohesive mixins, each owning one concern:

| Module          | Responsibility                                                                         |
| --------------- | -------------------------------------------------------------------------------------- |
| `lifecycle.py`  | `start()`/`stop()` generations, bounded shutdown, reconciler thread, runtime status    |
| `capacity.py`   | Quota estimates, two-phase eviction reservation, post-render quota enforcement         |
| `scheduling.py` | Identity coalescing, `schedule_derivative`, consistency repair                         |
| `lookup.py`     | Ready-file lookup/touch, serving protection, outcome and asset lookups                 |
| `reconcile.py`  | Desired-state reconciliation for a library, scope, or asset set; `warm_library`        |
| `supersede.py`  | Retiring `ready` rows of superseded source identities; unlink-after-commit with serving protection |
| `status.py`     | Per-library coverage and quota read model (`library_status`)                           |
| `maintenance.py` | Clearing derivative rows and cache files                                               |
| `recovery.py`   | Worker/supervisor loops, abandoned-claim recovery, queued-job reconciliation           |
| `execution.py`  | Claim, lease renewal, render, failure handling, `_LeaseHeartbeat`                      |
| `_common.py`    | Shared constants, `_lease_days`, `_ensure_database`, `derivative_variant`              |
| `models.py`     | `DerivativeReconcileSummary`, `DerivativeRepairSummary`, type aliases                  |

Tests that patch module-level settings (for example `DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS`) must patch
the module that reads them, not the package namespace.

Thumbnail and preview work is a durable SQLite state machine. A queued job is
claimed with a process/worker owner, unique claim token, and a configurable lease
(default 900 seconds). Rendering runs outside database transactions. Completion,
retry, skip, and failure writes are fenced by the claim token so an expired
worker cannot overwrite a newer claim.

While a worker renders, a fenced lease heartbeat owned by the job ID and claim
token renews `lease_expires_at` at most once per heartbeat interval (clamped to
one third of the lease). The heartbeat only updates a row that is still `running`
with the same claim token, stops before the worker persists its terminal outcome,
and never overwrites render state on a failed renewal. A healthy heartbeat keeps
a long render from being duplicated by supervisor or startup recovery when the
original lease would otherwise expire.

Derivative catalog rows use the full state machine `queued` → `running` →
`ready`, with terminal or policy states `failed`, `skipped`, `evicted`, and
`deferred_capacity`. `ready` means the cache path was published after a fenced
job completion. Inactive, missing, or superseded sources become `skipped` with
a machine-readable result code. Invalid sources and exhausted or internal
failures become `failed`; transient SQLite/I/O failures retry at most three
attempts. A permanent decode failure (`is_permanent_decode_error` in
`backend/files.py`: Pillow's `UnidentifiedImageError`, a decompression bomb, an
errno-less `OSError` such as "image file is truncated", or `SyntaxError`,
`ValueError`, `EOFError` from a decoder) while rendering becomes `failed` with
`invalid_source` on the first attempt, with no retry and no backoff; `/api/thumbnail`
answers it as `400 invalid_file`. An `OSError` with an errno (EAGAIN, EBUSY,
EINTR, EIO, ...), `sqlite3.OperationalError`, and `DatabaseWriterUnavailable`
keep the transient retry. Quota eviction changes a replaceable `ready` row to `evicted` and
unlinks its cache file. Automatic work that cannot reserve enough quota becomes
`deferred_capacity` without a runnable job. Derivative job rows separately use
`queued`, `running`, `done`, `skipped`, and `failed`.

Quota decisions inside a reconcile batch use a `CapacityLedger`
(`derivative_scheduler/capacity.py`). `_coalesce_reconcile_candidates` holds one
`BEGIN IMMEDIATE` for up to `GALLERY_DERIVATIVE_RECONCILE_BATCH_SIZE` assets,
and evaluating `ready bytes + active-job reservations` with two full-table
aggregates for every identity kept the SQLite write lock for seconds. The
ledger loads both aggregates once per batch transaction (lazily, at the first
capacity check) and then follows the only writes that change them (a `ready`
row leaving `ready`, an `evicted` row returning to `ready`, a new queued job).
The batch owns the write lock, so the result is identical to re-aggregating after
every coalesce: quota, eviction, and `deferred_capacity` outcomes are unchanged.
Callers outside a batch (`schedule_derivative`, the per-identity capacity
phase, post-render enforcement) keep evaluating the aggregates directly.

Superseded derivatives leave the ready set. A `ready` row whose source identity
(`source_mtime_ns`/`source_size`) no longer equals its active asset's `mtime_ns`/
`size` can never be served again, yet it used to stay `ready`: it counted toward
the quota and its file stayed on disk. `SupersedeMixin`
(`derivative_scheduler/supersede.py`) moves such rows to `skipped`, clears
`cache_path`/`byte_size`, and marks their jobs (queued, running, and `done`
history) `skipped` with `result_code='source_superseded'` (a row without such a
latest job gets one). A source that later returns to the old identity is
recognized as retriable through that code and regenerated instead of staying
terminally skipped. Retirement runs (1) at the start of every reconcile batch
transaction, before the batch's capacity estimate, and reports each retired row to
that batch's `CapacityLedger` (`ready_row_left`) so quota decisions later in the
batch see the bytes gone and equal an oracle that retires first; (2) after every
successful catalog scan or rebuild commit, independent of the library warm policy,
through `retire_superseded_derivatives`, which works in bounded transactions of
500 rows; and (3) at the start of every integrity pass for pre-existing rows. Only
assets that are active and have a known identity are considered. Cache files are
unlinked only after the retiring transaction commits (a rolled-back batch keeps
rows and files). A file under a serving lease (`_served_paths`) is not unlinked:
its path is remembered and `release_serving` removes it once the lease is
released; a file that is being generated, or that any row references again, is
never removed.

Every source-dependent operation, including cache-path calculation, is inside
the job exception boundary. The worker loop has an additional catch-all, so one
bad source cannot terminate a worker. A supervisor runs every 30 seconds,
recovers claims owned by dead workers or expired leases, and restores the
configured worker count. Startup applies the same recovery policy before
workers claim new jobs.

`stop()` sets the stop event, wakes all workers, and gives all workers plus the
supervisor/reconciler one shared absolute shutdown deadline. Each join receives
only the time remaining before that deadline, so total shutdown time is bounded
by `GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS`, not multiplied by the thread
count. Overlapping stop calls keep startup blocked until every stop caller has
finished. A timeout records an incomplete shutdown and leaves in-flight renders
running rather than abandoning them. `start()` prunes stale dead worker thread
objects left by an incomplete stop before restoring the configured worker count,
so a prior incomplete stop never permanently refuses to restart.

This lifecycle assumes the maintained single-process deployment: one backend
process owns the derivative workers, the SQLite queue, and all claim leases. It
does not support multiple Uvicorn/Gunicorn processes sharing one derivative
queue; claim fencing and the lease heartbeat are correct only within one process.

Scheduling, claiming, status, and integrity repair all require an active image
asset whose `mtime_ns` and size match the derivative source identity. The
integrity checker requeues missing cache files only for current sources;
inactive, missing, and superseded sources are skipped instead.

HTTP thumbnail requests accept only `128`, `256`, or `512`; preview requests
accept only `1440`. Both always resolve an active catalog asset and always pass
through the durable scheduler. Capacity is reserved before runnable work exists;
interactive refusal returns `507`, while automatic work remains
`deferred_capacity`. The WebP file cache is authoritative and quota-counted;
the 64 MiB diskcache stores only key-to-path metadata. Integrity checks skip
and remove legacy unsupported variants after committing their terminal state.

Video posters use a separate 1 GiB default LRU quota plus a global bounded
ffmpeg semaphore. A reference-counted serving lease is acquired before quota
protection is released and remains held through response stat/revalidation and
stream completion. The response itself releases the lease in an ASGI-level
`finally`, including file-open, send, disconnect, and cancellation failures;
cleanup does not depend on a Starlette background task running. Duplicate
requests wait on the per-video lock before using an ffmpeg slot. Queue
saturation returns `503`, subprocess output is discarded, and temporary files
and leases are cleaned on every exit path.

Desired-state reconciliation has explicit trigger ownership:

- The catalog worker reconciles the committed library or path scope after a
  successful scan or rebuild. These automatic passes create missing identities
  but preserve existing capacity-deferred/evicted identities.
- Metadata completion reconciles that asset as a safety net after its durable
  metadata state is committed; it also preserves existing capacity deferrals.
- Scheduler startup reconciles all warm-enabled libraries; its periodic loop
  later fills missing configured identities but does not reconsider existing
  `deferred_capacity` or fully unlinked `evicted` rows, preventing quota-driven
  thumbnail/preview rotation on every pass.
- Integrity checks own repair of missing expected rows, queued rows without an
  active job, and explicit reconsideration of capacity-deferred/evicted rows.
- Enabling warm policy reconciles that library immediately. The admin
  `Generate missing images` action is an explicit library-scoped trigger and may
  retry failed or capacity-deferred work even when warm policy is off.
- Cache clear deletes derivative jobs and catalog rows; later startup,
  catalog, policy, integrity, or explicit generation triggers rebuild desired
  state. A process restart after a configured quota increase uses startup
  reconciliation to reconsider deferred work.

`GET /api/derivatives/status` reports current configured coverage for one
library both as aggregate `by_kind` counters and ordered per-variant counters
for `thumb_128`, `thumb_512`, `thumb_256`, and `preview_1440`. It also reports that
library's ready bytes as `library_used_bytes`, and global quota accounting as
`quota_used_bytes`, `quota_bytes`, and `quota_utilization`.

## Overview

AI Art Gallery is a local-first mixed-media browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans folders, serves original images, generates cached WebP derivatives, extracts AI generation metadata, indexes folders/photos/metadata in SQLite FTS5, and exposes read-only inspection/search APIs.
- Frontend: uses Vue Router for the gallery and metadata inspector routes, Pinia for UI/navigation state, TanStack Query for API state, TanStack Virtual for large grids and the Library Inspector table body, PhotoSwipe for the lightbox, TanStack Form for advanced search, and TanStack Table for the Library Inspector.
- Startup: `start.py` creates/repairs the Python virtualenv, installs Python and pnpm frontend dependencies when needed, and starts the backend on fixed port `4701` and frontend on fixed port `4702`. It exits with an error if either port is occupied.
- Tooling: Ruff, ESLint, and Prettier scan the full codebase. Vitest/V8 covers frontend units; Playwright runs sharded functional E2E and isolated performance suites against deterministic FastAPI fixtures.

Major external library integrations are documented in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).
Environment variables and parser behavior are documented in
[Configuration](CONFIGURATION.md) and [Metadata Parsing](METADATA_PARSING.md).

## Backend

Backend modules are mostly flat, with selected domain packages.

| File                       | Purpose                                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `app.py`                   | FastAPI app creation, CORS, optional Prometheus metrics, optional pyinstrument middleware, router composition, startup background services |
| `main.py`                  | Import-compatible `app` shim and uvicorn fallback block                                                                                    |
| `config.py`                | Environment flags, cache paths, derivative limits, image limits, indexer/catalog tuning, production/static config                           |
| `errors.py`                | `APIError`, `ErrorType`, and FastAPI error shaping                                                                                         |
| `models.py`                | Shared Pydantic DTOs, including `FileNode`                                                                                                 |
| `paths.py`                 | `resolve_path`, `is_path_safe`, and `PATH_SAFETY_ROOT` boundary checks                                                                     |
| `files.py`                 | Image/video classification, exclusion checks, natural sort, and image safety limits                                                        |
| `albums.py`                | Album cover/count/child-folder metadata                                                                                                    |
| `scan.py`                  | Routes removed (Phase 9); scan.py still exports `require_media_path_allowed` and the router included by app.py                            |
| `browse.py`                | DB-only read-only browse via `/api/browse`; virtual import-root listing, path-scoped asset/folder pagination                              |
| `maintenance.py`           | `/api/maintenance/file-health` latest-run report and `/api/maintenance/file-health/check` manual integrity run                             |
| `folders.py`               | `/api/folders` folder-tree endpoint and `/api/open-folder` OS explorer hook                                                                |
| `images.py`                | `/api/image` original file serving                                                                                                         |
| `thumbnails.py`            | `/api/thumbnail`, `/api/preview`, WebP derivative generation, persistent disk cache                                                        |
| `metadata_extract.py`      | Raw metadata extraction/parsing helpers for A1111, SwarmUI, ComfyUI, NovelAI, EasyDiffusion, and generic EXIF/text fields                  |
| `metadata_parse.py`        | `/api/metadata`, in-memory metadata cache, response shaping                                                                                |
| `fielded_search_parser.py` | Parser for `prompt:`, `seed:`, `model:`, numeric operators, quoted values, and related fielded search syntax                               |
| `search.py`                | `/api/search/query`, legacy `/api/search`, `/api/search-metadata`, `/api/library/inspector`, `/api/library/inspector/metadata`              |
| `related_assets.py`        | `/api/search/related` reference authorization and persisted relation-readiness contract                                                      |
| `search_indexes.py`        | Search capabilities plus derived-index state, rebuild-job, and cancellation APIs                                                          |
| `search_indexer.py`        | Fixed index registry and supervised single-writer durable derived-index worker                                                             |
| `facets.py`                | `/api/facets` aggregation over indexed metadata                                                                                            |
| `indexer.py`               | DB-claim metadata lifecycle worker, durable scheduling, startup recovery, diagnostics, and scan worker rebuild helpers                      |
| `integrity_checker.py`     | Periodic cross-table consistency checker for metadata jobs, assets, image metadata, derivatives, and derivative jobs                       |
| `refresh.py`               | Optional scheduled refresh loop                                                                                                            |
| `watcher.py`               | Optional filesystem watcher loop                                                                                                           |
| `libraries.py`             | Registered-library CRUD/validation, multi-import-path scan, unregister flows, status endpoints                                             |
| `library_events.py`        | Best-effort single-process SSE fan-out for library/job progress                                                                            |
| `video.py`                 | Range-capable original video streaming and cached poster generation                                                                        |
| `health.py`                | `/api/health`, favicon, git commit reporting                                                                                               |
| `static_files.py`          | `/`, `/api/landing-pages`, and production SPA fallback                                                                                     |
| `scan_worker.py`           | Background catalog scan/rebuild worker, durable job queue, startup stale-job recovery, queue_scan/queue_rebuild/run_once/start/stop        |

### Domain Packages

| Package / Module                     | Purpose                                                   |
| ------------------------------------ | --------------------------------------------------------- |
| `metadata_store/`                    | SQLite data access layer: schema, search, CRUD, job queue |
| `metadata_store/_db.py`              | SQLite connections (`ClosingConnection`, `open_connection`), init flags, shared constants |
| `metadata_store/_schema.py`          | `initialize_database` entry point and `CATALOG_SCHEMA_VERSION`; orchestrates fresh creation and upgrades |
| `metadata_store/_schema_ddl.py`      | Fresh-database DDL (`FRESH_DATABASE_DDL`)                 |
| `metadata_store/_schema_ensure.py`   | Additive post-v1 columns, indexes, and feature-table ensure helpers |
| `metadata_store/_migrations.py`      | v1 compatibility handling, v1→v12 migrations, and pre-migration backups |
| `metadata_store/types.py`            | Shared dataclasses and exceptions                         |
| `metadata_store/path_utils.py`       | Path normalization and overlap helpers                    |
| `metadata_store/library_store.py`    | Library CRUD                                              |
| `metadata_store/job_store.py`        | Catalog job queue management                              |
| `metadata_store/rebuild_store.py`    | Staging area for rebuild operations                       |
| `metadata_store/browse_store.py`     | Browse listing queries                                    |
| `metadata_store/file_index.py`       | File index operations; `CatalogRecord`, the record builders (`build_folder_record`, `build_asset_record`, `probe_video_metadata`) and `upsert_catalog_records_conn`, shared by scan and rebuild |
| `metadata_store/folder_index.py`     | Folder index operations                                   |
| `metadata_store/metadata_queue.py`   | Durable metadata index job queue primitives, completion invariants, and stale guards |
| `metadata_store/metadata_persist.py` | Metadata persistence helpers                              |
| `metadata_store/search_store.py`     | FTS5 search queries                                       |
| `metadata_store/ranked_search.py`    | Tiered search candidates and opaque keyset cursors        |
| `metadata_store/cjk_index.py`        | CJK bigram prompt index maintenance and short-query plan  |
| `text_fold.py`                       | `fold_text`: the one query/index normalization function   |
| `metadata_store/search_text_index.py`| Folded prompt/model/sampler/file-name index sync and rebuild |
| `metadata_store/search_index_store.py` | Derived-index states, fenced jobs, keyset asset batches, and extraction fingerprints |
| `metadata_store/inspector_store.py`  | Library Inspector data access                             |
| `metadata_store/_asset_store.py`     | Shared asset upsert helper                                |
| `metadata_store/_resources.py`       | Image resource parsing helpers                            |
| `metadata_store/status_store.py`     | Unified catalog status query builder                      |
| `tests/`                             | Backend test suite (pytest)                               |

### Route Reference

| Endpoint                                  | Purpose                                                               | Module              |
| ----------------------------------------- | --------------------------------------------------------------------- | ------------------- |
| `GET /api/browse`                         | Return folders and paginated mixed-media rows from catalog rows for a library | `browse.py`         |
| `GET /api/folders`                        | Return direct non-hidden child folders for sidebar expansion          | `folders.py`        |
| `GET /api/image`                          | Serve an original image file                                          | `images.py`         |
| `GET /api/thumbnail`                      | Serve a cached WebP thumbnail, default max long edge 512px (128, 256 and 512 allowed); optional `v` = item `content_version` | `thumbnails.py`     |
| `GET /api/preview`                        | Serve a cached WebP preview, default max long edge 1440px; optional `v` = item `content_version` | `thumbnails.py`     |
| `GET /api/video`                          | Stream an original video with HTTP Range support                      | `video.py`          |
| `GET /api/video/poster`                   | Serve a cached WebP poster generated with ffmpeg                      | `video.py`          |
| `GET /api/metadata`                       | Extract and normalize AI generation metadata for one image            | `metadata_parse.py` |
| `GET /api/search`                         | Cursor-paginated unified search media stream plus first-page album suggestions, including fielded metadata queries | `search.py`         |
| `POST /api/search/query`                  | Canonical Search V2 body with versioned ID-based scope, structured filters, and opaque cursor paging    | `search.py`         |
| `POST /api/search/related`                | Bounded reference-asset relation request with explicit profile, reason, score, and index-status models   | `related_assets.py` |
| `POST /api/search/prompt-usage/query`     | Normalized prompt-group usage within an authorized canonical scope                                      | `search.py`         |
| `POST /api/search/workflow/raw`           | Opt-in literal trigram search over size/budget-bounded canonical workflow JSON                           | `search.py`         |
| `GET /api/search/capabilities`            | Enabled modes, scopes, fixed limits/registries, and required derived indexes                            | `search_indexes.py` |
| `GET /api/search/indexes`                 | Per-library derived-index state with separate usability and active job progress                         | `search_indexes.py` |
| `POST /api/search/indexes/{name}/rebuild` | Queue one durable missing/full rebuild; duplicate active work returns 409                               | `search_indexes.py` |
| `GET /api/search/index-jobs/{id}`         | Inspect one durable derived-index job                                                                    | `search_indexes.py` |
| `POST /api/search/index-jobs/{id}/cancel` | Idempotently request or finish cancellation                                                              | `search_indexes.py` |
| `GET /api/search-metadata`                | Legacy metadata-only search endpoint                                  | `search.py`         |
| `GET /api/library/inspector`              | Bounded read-only rows for the desktop metadata inspector             | `search.py`         |
| `GET /api/library/inspector/metadata`     | DB-first full metadata detail for one inspector row                   | `search.py`         |
| `GET /api/facets`                         | DB-derived model/tool/sampler/etc. aggregation counts                 | `facets.py`         |
| `POST /api/open-folder`                   | Open a folder in the OS file explorer when enabled                    | `folders.py`        |
| `GET /api/health`                         | Return service health and commit metadata                             | `health.py`         |
| `GET /api/landing-pages`                  | List intro page HTML templates from `frontend/public/landpage/` (theme folders only; no archives or `sample_test`) | `static_files.py`   |
| `GET /api/maintenance/runtime`            | Return global runtime diagnostics and metadata lifecycle counters     | `maintenance.py`    |
| `GET /api/libraries`                      | List libraries with ordered import paths and exclusions               | `libraries.py`      |
| `GET /api/libraries/status`               | Return admin batch status for all libraries                           | `libraries.py`      |
| `POST /api/libraries`                     | Register a library using import_paths                                 | `libraries.py`      |
| `POST /api/libraries/validate`            | Validate create settings without writing                              | `libraries.py`      |
| `POST /api/libraries/scan-all`            | Queue one update job per registered library                           | `libraries.py`      |
| `GET /api/stats`                          | Return aggregate statistics across registered libraries               | `libraries.py`      |
| `GET /api/jobs`                           | Return recent library-management jobs                                 | `libraries.py`      |
| `GET /api/jobs/{job_id}`                  | Return one library-management job                                     | `libraries.py`      |
| `GET /api/events`                         | Stream best-effort library job and progress events over SSE           | `libraries.py`      |
| `PATCH/PUT /api/libraries/{id}`           | Replace supplied library settings                                     | `libraries.py`      |
| `GET /api/libraries/{id}`                 | Return library details                                                | `libraries.py`      |
| `POST /api/libraries/{id}/validate`       | Validate update settings without writing                              | `libraries.py`      |
| `GET /api/libraries/{id}/progress`        | Return progressive discovery and metadata coverage                    | `libraries.py`      |
| `POST /api/libraries/{id}/scan`           | Update every import path in one library                               | `libraries.py`      |
| `GET /api/libraries/{id}/status`          | Return unified status envelope for a library or path scope            | `libraries.py`      |
| `GET /api/libraries/{id}/stats`           | Return aggregate media statistics for one library                     | `libraries.py`      |
| `GET /api/libraries/{id}/offline-assets`  | List exact unavailable image/video catalog rows                       | `libraries.py`      |
| `DELETE /api/libraries/{id}/offline-assets?confirm=true` | Forget unavailable media rows and dependent derivative jobs without deleting source files | `libraries.py` |
| `GET /api/libraries/{id}/jobs`            | Return recent jobs for one library                                    | `libraries.py`      |
| `DELETE /api/libraries/{id}?confirm=true` | Unregister catalog data without deleting source files                 | `libraries.py`      |
| `GET /api/derivatives/status`             | Return policy-aware thumbnail/preview coverage, convergence, quota, job counts, and worker health | `libraries.py`      |
| `POST /api/derivatives/warm`              | Explicitly queue missing configured images for one library; optional `kind=thumbnail\|preview` limits scope | `libraries.py`      |
| `POST /api/maintenance/imported-data/clear` | Clear imported catalog, metadata, search-index lifecycle data, and generated-image data while preserving library settings and source files | `maintenance.py` |
| `POST /api/maintenance/imported-data/rebuild` | Clear imported data and queue whole-library rebuild jobs          | `maintenance.py`    |
| `POST /api/maintenance/catalog/reset`     | Reset catalog database data, including registered libraries           | `maintenance.py`    |
| `GET /` and `GET /{path:path}`            | Serve the built SPA in production mode                                | `static_files.py`   |

### Backend Behavior

- `PATH_SAFETY_ROOT` is the outer filesystem safety boundary. Media routes additionally require an active registered-library catalog asset of the expected type; registered folder scopes must be owned and non-excluded. Safety-root escapes return `403`, while catalog-invisible paths return `404`.
- In production nginx owns browser Basic Auth and injects a secret header. FastAPI validates that header on every `/api` router and refuses production startup unless the shared secret is at least 32 characters.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- `ENABLE_METRICS` defaults to enabled outside production and exposes `/metrics` with route-level labels.
- `ENABLE_PROFILER=0` by default. When enabled, selected endpoints are profiled with pyinstrument and HTML reports are written to `backend/profiles/`.
- Original images are served only by `/api/image`; thumbnails and previews are generated derivatives.
- Original media and generated derivatives use ETags with `Cache-Control: public, max-age=0, must-revalidate`, so source identity changes are visible on the next request instead of being hidden by immutable browser caching. The one exception is a thumbnail or preview URL whose `v` equals the source's current `"<mtime_ns>-<size>"` (the `content_version` the listing returned): its identity is part of the URL, so it is served `public, max-age=31536000, immutable` and a changed source simply produces a new URL.
- Video streaming supports one byte range, clamps a satisfiable end at EOF, returns `416` for malformed/empty/multi-ranges or invalid starts, and honors strong-ETag and HTTP-date `If-Range`; a mismatched validator receives the full `200` representation.
- Derivative cache keys include kind, cache version, resolved path, mtime, size, long-edge target, format, and quality. WebP files persist under `backend/.cache/thumbnails/`.
- Derivative claims use fenced tokens and 15-minute leases. Missing/inactive/current-source races terminate only their job; the supervisor replaces dead workers and recovers abandoned claims.
- The metadata DB defaults to `backend/.cache/gallery_metadata.db` and can be overridden with `GALLERY_METADATA_DB`.
- SQLite uses WAL mode and stores both file index rows and normalized metadata rows. FTS5 tables cover folder/photo names and metadata text.
- Catalog-only search/facet predicates correlate assets by `(library_id, path)`,
  matching the catalog's composite index instead of performing a per-file asset
  table scan.
- Catalog schema version 15 adds one partial index, `idx_assets_folder_images` on
  `assets(library_id, parent_path, mtime_ns DESC, path) WHERE type IN ('image', 'photo')
  AND offline = 0 AND deleted_at IS NULL` (BL-13). It holds the visible image children of
  every folder, newest first, so a folder's image count is an index-only scan of its range
  and its three covers are the first readable rows of that range. It is derived from
  `assets` alone: the `.v14.bak` migration backs the database up, builds the index and sets
  `user_version` last, and there is nothing else to backfill. On the 100k perf fixture it
  adds 34.6 MiB (743.8 to 778.4 MiB in use, +4.7%). Folder aggregates for owned folders
  (`browse_store._browse_folder_counts_batch_conn`, used by browse folder cards, the browse
  virtual root and search album suggestions) read it; every other case (offline-inclusive
  aggregates, folders outside an import path, a database that has no index yet) keeps the
  general scans, which return identical values.
- Catalog schema version 14 adds the folded search text index (SE-03/SE-04 of the
  search-typing plan). `text_fold.fold_text` is the single
  normalization function for indexed text and queries: NFKC (full-width and
  half-width forms), `casefold`, removal of every Combining Diacritical Mark
  (including Vietnamese stacked marks; kana voicing marks are kept), `đ`/`Đ` to `d`,
  and katakana to hiragana. It is pure Python, so behaviour does not depend on the
  SQLite version (the trigram tokenizer only gained `remove_diacritics` in 3.45).
  `image_metadata_fold` (folded prompt, negative prompt, model, sampler; one row per
  metadata row with any folded text) and `file_index_fold` (folded file name keyed
  by the `file_index` rowid) are compact content tables for external-content FTS5
  tables: `image_metadata_fold_fts` / `file_index_fold_fts` (`unicode61`, word
  prefix) and `image_metadata_fold_fts_trigram` / `file_index_fold_fts_trigram`
  (substring). FTS follows the content tables through triggers and the parents'
  delete triggers (`image_metadata_fold_cleanup`, `file_index_fold_cleanup`) remove
  rows, so reused ids never inherit stale text. Writers call
  `search_text_index.sync_search_text_path` (prompt/model/sampler, which also syncs the
  CJK rows) and `sync_file_name_fold` (file names) in the same transaction; code that
  writes those columns with raw SQL (perf fixtures, tests) must call
  `rebuild_search_text_index`. The `.v13.bak` migration streams keyset batches over
  stored text only (no media decoding, no `fetchall` over all rows), rebuilds the CJK
  bigram rows from folded text, runs `foreign_key_check` and sets `user_version`
  last. The older `image_metadata_fts*` and `file_index_fts*` tables stay for the
  legacy readers (`related_ranking`, the legacy `search_store` queries).
  Display text (names, prompts, snippets) is never folded.
- Catalog schema version 13 adds the CJK bigram prompt index: `image_metadata_cjk`
  (one row per prompt or negative prompt that contains CJK text, holding the
  space-joined overlapping bigrams of each CJK run plus a one-character run-end
  token) and its external-content `unicode61` FTS5 table `image_metadata_fts_cjk`,
  kept in step by insert/update/delete triggers; an `image_metadata` delete
  trigger removes the row. Its `.v12.bak` migration backfills from stored prompt
  text only (no media decoding) with `cjk_index.rebuild_cjk_index`. Prompt writes
  in `metadata_persist.py` call `cjk_index.sync_cjk_path`; any code that writes
  `image_metadata.prompt` with raw SQL must call `rebuild_cjk_index` afterwards.
- Catalog schema version 12 rebuilds `asset_visual_hash_bands` and
  `asset_search_extractions` as `WITHOUT ROWID` tables through a rollback-safe
  `.v11.bak` migration, reducing the storage cost of their composite primary
  keys. Version 11 creates
  `asset_visual_fingerprints`, eight per-asset `asset_visual_hash_bands`, and
  the `(hash_kind, band_no, band_value, library_id, asset_id)` candidate index.
  Its `.v10.bak` migration creates storage only and never decodes or backfills
  media inline. Version 10 creates
  `asset_generation_signatures` and its library/hash candidate indexes. The
  `.v8.bak` migration performs no inline backfill, checks foreign keys, and
  publishes version 10 last; version 9 remains a historical reset sentinel.
  Version 8 creates `workflow_raw_documents`, its
  external-content trigram FTS table, and visible skipped-index counters; its
  `.v7.bak` migration performs no backfill. Version 7 creates typed `workflow_nodes` and
  `workflow_property_values` with fixed per-type lookup indexes; its `.v6.bak`
  migration creates storage only and leaves extraction to the durable
  `workflow_properties` index. Version 6 creates normalized
  `asset_prompt_values`, per-asset observed model identities, and
  `model_identity_aliases`; its `.v5.bak` migration creates storage only and
  leaves backfill to the durable `prompt_values` search-index job. Version 5
  creates `search_index_states`, `search_index_jobs`, and
  `asset_search_extractions`; it never backfills inline.
  The migration creates `.v4.bak`, runs under one `BEGIN IMMEDIATE`, checks
  foreign keys, and publishes `user_version=5` last. Version 4 still owns the
  unambiguous `file_index.library_id` backfill and `.v3.bak`; earlier versions
  retain their `.v2.bak` and `.v1.bak` rollback behavior.
- Registered libraries store ordered roots in `library_import_paths`. Relative globstar exclusions live in `library_exclusion_patterns`.
- `/api/browse` is the read-only catalog query endpoint. It accepts `library_id`, `path`, `cursor`, `limit`, and `include_offline`. The response contains `folders`, `media`, `next_cursor`, legacy alias `next_media_cursor`, `total_images`, `total_videos`, `total_assets`, `request_path`, `index_source`, `library_id`, and `path`. Image media rows also include `derivative_ready` for thumbnail/preview readiness; the frontend treats this as a loading/preload hint, not visible user-facing status. Catalog update and status are managed through library endpoints; imported-data clear, rebuild, and catalog reset are managed through maintenance endpoints.
- Catalog scan workers, the DB-claim metadata lifecycle worker, the single
  derived-search-index writer, the derivative scheduler, and the integrity
  checker run as background services. The catalog watcher and scheduled
  reconciliation are enabled by default for registered libraries.
- During a catalog scan, each video is probed once with `ffprobe` (`-show_format
  -show_streams`, 5 s timeout, in `backend/metadata_store/file_index.py`) to
  record `width`, `height`, `duration_ms`, and `codec`. A missing binary, a
  timeout, or unreadable output leaves those fields NULL and the scan continues.
- The enabled `prompt_values` derived index reads only persisted
  `image_metadata`/checkpoint-resource rows. It NFKC-normalizes and casefolds
  prompt identities, keeps positive and negative values distinct, and updates
  observed model-name/hash aliases without reopening source media.
- The enabled `generation_signatures` index reads only current persisted image
  metadata and normalized resources. Its versioned prompt atoms are NFKC,
  whitespace-collapsed, casefolded identities with bounded supported emphasis;
  positive/negative prompts cap at 64 atoms and candidate queries cap at 16.
  Compact SHA-256 layers separate prompt, generation family, recorded recipe,
  and exact deterministic settings. Hash identities win over name fallbacks,
  missing inputs are explicit, numeric values use canonical finite decimals,
  and only bounded registry-typed workflow properties participate. A common
  model, sampler, or seed without prompt evidence cannot form a strong family.
  Metadata persistence invalidates stale rows transactionally and coalesces a
  durable missing backfill; active assets are processed in the existing
  200-row single-writer batches and failures degrade only this optional index.
- Related metadata requests collect at most 600 distinct candidates from
  bounded signature, observed-model-identity, resource, optional
  typed-workflow, and prompt-FTS branches. Each branch performs its own direct
  indexed active/current-source/scope join and applies its cap before candidate
  IDs are united; the request does not materialize a catalog-wide eligibility
  CTE. Prompt FTS uses at most 16 versioned distinctive atoms and excludes
  common boilerplate from candidate lookup. The `recipe` profile executes only
  exact/recipe signature branches. Metadata rows are loaded only for the
  bounded union, and the SQLite read closes before deterministic
  weighted prompt/resource/workflow/settings scoring. Fixed tiers 100/90/80/
  70/60/40 and stable evidence codes determine ordering before mtime and
  `asset_id` tie-breakers. Same model, sampler, seed, folder, orientation, or
  common boilerplate alone never creates a result. The `recipe` profile keeps
  only exact-signature and same-recipe tiers; missing workflow-property rows
  safely reduce candidate evidence without disabling metadata ranking.
- The optional `visual_fingerprints` index uses only current persisted
  thumbnail/preview derivatives. Its background extractor applies EXIF
  transpose, composites alpha onto white, computes horizontal and vertical
  64-bit dHash plus a 4x4 RGB grid, and persists the fingerprint and eight
  16-bit bands atomically. Missing derivatives queue the normal `thumb_512`
  variant at low priority; successful derivative completion invalidates a
  pending extraction and coalesces durable retry work. Decode/hash work occurs
  outside SQLite writes, and related HTTP handlers never open an image.
- Visual requests probe exact and one-bit alternatives for each indexed
  16-bit band, cap the candidate pool at 500, then use Python `int.bit_count()`
  for exact Hamming distance. Color-grid and aspect-ratio distances only reject
  or order weak dHash matches; they are not semantic features. Resize and
  re-encode matches use tier 80, light modifications use tier 60, and every
  result carries `visual_variant`. Large crops, mirrors, rotations, and
  generative composition changes are documented limitations; a visual match
  does not prove prompt, recipe, lineage, or common source.
- A relation index in `building` state remains queryable when its persisted
  coverage is marked usable; unusable building coverage returns the typed
  retryable readiness error. Combined requests keep available metadata results
  when visual coverage is missing, building, degraded, failed, or disabled.
- The enabled `workflow_properties` index accepts only the code-owned ComfyUI
  registry advertised by search capabilities. API prompt graphs provide named
  inputs; supported UI graph widgets use a versioned positional map. Search
  predicates compile to fixed same-node `EXISTS` SQL with bound values, while
  links, containers, non-finite numbers, and unsupported identifiers are not indexed.
- Raw workflow search is disabled by default and owns a separate durable index.
  Enabled extraction compacts supported JSON without truncation, skips per-file
  or total-budget overflow into degraded status, and queries only trigram FTS.
  Reads use a dedicated query-only SQLite connection with a 250 ms progress
  deadline; timeout returns a typed complete failure rather than partial rows.
  Legacy `param:`/`advanced:` keys are limited to
  `[A-Za-z_][A-Za-z0-9_]{0,127}` and JSON paths and values remain bound parameters.
- FastAPI lifespan startup registers each stop callback immediately after its service starts. Startup failures and normal shutdown unwind callbacks in reverse order, attempt every cleanup, and log incomplete stops without masking the initiating failure.
- Unexpected exceptions are logged server-side with tracebacks. Public `500` responses use a generic message; durable background-job error fields retain bounded operational detail.
- The catalog service owns a supervisor thread. Each running job has a durable
  worker owner, unique claim token, and renewable lease; progress/completion is
  fenced by the token and unexpired lease. Scan writes are split into bounded
  transactions so the heartbeat can run between batches. Each scan batch,
  rebuild staging flush, rebuild activation, and reconciliation transaction
  validates the claim at entry and refreshes the same token immediately before
  commit; this remains safe if wall-clock expiry passes while its `BEGIN
  IMMEDIATE` prevents any recovery write from interleaving. Terminal job and
  library state commit atomically. Metadata job enqueueing also receives the
  catalog claim, splits its path list into bounded transactions, and refreshes
  before every commit rather than relying on a pre-dispatch assertion.
  In-process heartbeats register their active `(job_id, claim_token)` while work
  runs. Runtime recovery does not fence an expired claim whose owner thread and
  exact heartbeat token are both still live; after a global SQLite writer
  releases the lock, that token may renew even if its prior deadline passed.
  Claiming and active-token registration are serialized with the runtime
  supervisor, and heartbeat setup/event publication are inside the executor's
  cleanup boundary. When an executor returns, `run_once()` stops and
  unregisters the heartbeat, then token-fence-fails any row that is still
  `running` with that same claim. If that close transaction is temporarily
  blocked, runtime recovery treats a live worker's unregistered token as
  abandoned regardless of its renewed lease. Both close paths clear claim
  fields, remove rebuild staging, and move an indexing library to `error` in
  the same transaction. Dead owners and startup claims have no live-token
  protection and remain recoverable.
  Recovery deletes the recovered rebuild's staging rows in the same transaction
  and recomputes aggregate parents from both direct and dependency-table links
  only at startup or when a child actually recovered. Startup and runtime
  recovery otherwise restore the configured worker count independently of
  status traffic. Library and maintenance GET endpoints only observe state.
- Scheduled reconciliation records durable attempt time before queueing, even
  when work coalesces or maintenance is busy. Eligible libraries are ordered by
  oldest attempt, with never-attempted libraries first, so bounded ticks remain
  fair. Watcher drains are deterministic and bounded; overflow stays pending
  for the next tick.

## Frontend

Key paths:

| Path                                                      | Role                                                                                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `frontend/src/main.ts`                                    | Vue entry, global styles, Pinia, Vue Router, TanStack Query installation, dev debug utilities                                  |
| `frontend/src/router/index.ts`                            | Routes: `/` gallery, `/metadata` Library Inspector, `/admin/libraries`, `/admin/libraries/:id`, `/admin/maintenance`, fallback redirect |
| `frontend/src/App.vue`                                    | Root shell, layout dispatch, lightbox/settings/toast mounting, Query Devtools in dev                                           |
| `frontend/src/layouts/`                                   | Desktop, tablet, and mobile layout shells                                                                                      |
| `frontend/src/components/GalleryGrid.vue`                 | Main gallery renderer, browse album/photo sections, and search-query orchestration                                             |
| `frontend/src/components/Lightbox.vue`                    | Device-dispatch lightbox orchestrator with the image-level Related Assets action                                               |
| `frontend/src/components/RelatedAssetsPanel.vue`          | Canonical metadata/visual relation sheet, profile filters, coverage states, evidence, and lightbox handoff                     |
| `frontend/src/components/LibraryInspector.vue`            | Desktop metadata inspection table at `/metadata`; TanStack Table for returned-row sorting plus TanStack Virtual for table rows |
| `frontend/src/components/admin/LibraryListPage.vue`       | Admin registered-library list, update-all entrypoint, status summaries, and navigation to library detail pages                  |
| `frontend/src/components/admin/LibraryDetailPage.vue`     | Admin library detail with status/progress, generated-image coverage, live watcher/refresh state, problems, jobs, and dialogs   |
| `frontend/src/components/admin/MaintenancePage.vue`       | Admin maintenance page with file-health sections, global generated-file actions, and active job visibility                      |
| `frontend/src/components/SortSelect.vue`                  | shadcn-vue Select sort control used by gallery desktop/tablet toolbars and the Library Inspector                               |
| `frontend/src/components/SortDropdown.vue`                | Dropdown-menu sort control still used by the mobile header                                                                     |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | Shared metadata/discovery composition sheet and canonical-request emitter                                                     |
| `frontend/src/components/search/RecentSearchesPanel.vue`  | Browser-local automatic recent-search list and direct replay actions                                                           |
| `frontend/src/components/search/PromptUsagePanel.vue`     | Query-backed positive/negative prompt groups and exact-group action                                                            |
| `frontend/src/components/search/WorkflowFilterBuilder.vue` | Capability-driven typed same-node predicate drafts                                                                             |
| `frontend/src/components/search/RawWorkflowSearch.vue`    | Optional acknowledged Apply-only raw workflow query                                                                            |
| `frontend/src/components/search/SearchIndexStatusPanel.vue` | Query-backed derived-index readiness, rebuild, and cancellation                                                               |
| `frontend/src/components/search/SearchResultsPanel.vue`   | Dynamically measured virtualized album/media search rows, page loading, and typed open/retry actions                           |
| `frontend/src/components/search/SearchFeedback.vue`       | Pending, blocking-error, stale-warning, pagination-error, and successful-empty search states                                   |
| `frontend/src/components/search/SearchResultMetadata.vue` | Escaped match/snippet/generation/library context for one search result                                                         |
| `frontend/src/components/ui/`                             | shadcn-vue/Reka-inspired local UI primitives                                                                                   |
| `frontend/src/composables/`                               | Query wrappers including Related Assets, device detection, PhotoSwipe lifecycle, metadata/comparison helpers, theme, haptics  |
| `frontend/src/query/`                                     | TanStack Query client, normalized query keys, browse prefetch helpers                                                          |
| `frontend/src/stores/`                                    | Pinia stores for gallery UI/navigation, lightbox, Related Assets session UI, and toasts                                        |
| `frontend/src/services/api.ts`                            | `fetch` client instance, endpoint wrappers, URL helpers, API error mapping                                                     |
| `frontend/src/services/http.ts`                           | Small `fetch` JSON client that replaced Axios: Axios-compatible query encoding, errors, timeout, abort                         |
| `frontend/src/styles/`                                    | Tailwind 4 entry, shadcn token bridge, SCSS tokens, breakpoints, lightbox styles                                               |

### State Ownership

| Layer                | Responsibilities                                                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| TanStack Query       | `/api/browse`, `/api/folders`, `/api/search/query`, `/api/search/related`, `/api/metadata`, `/api/facets`, library status/jobs/stats, generated-image status/actions, Library Inspector rows/details, landing page fetches |
| Pinia gallery store  | Root/current path, selected path, history, expanded folders, search text/scope, sort, loaded flags, settings UI state                                 |
| Pinia lightbox store | Open image, current index, visible item list, navigation                                                                                              |
| Pinia related store  | Ephemeral open/reference/scope UI state; no match-type selection, related result payloads, or saved/recent-search persistence                      |
| Pinia toast store    | Toast API adapter (Gallery API → Sonner): IDs, variants, durations, dismiss, clear, actions, visible-toast limit; Sonner owns render/dismiss mechanics |

Status polling (`frontend/src/lib/catalog/polling.ts`) uses a 2.5 s active
interval and a 60 s stable interval. The active interval never drops below
twice the duration of that query's last completed fetch (capped at the stable
interval): the interval callback observes each query's fetch start and end, so
a slow status endpoint is re-requested no faster than it can answer. Rendered
output is unaffected.

Query keys are centralized in `frontend/src/query/keys.ts`. Paths are normalized by trimming, converting backslashes to forward slashes, collapsing duplicate slashes, and removing a trailing slash except for `/`.

Core keys:

```text
["landing-pages"]
["libraries"]
["libraries", "list"]
["libraries", "detail", id]
["libraries", "stats", id]
["libraries", "jobs", id]
["generated-images"]
["generated-images", "status", libraryId]
["stats", "gallery"]
["jobs"]
["jobs", "list"]
["jobs", id]
["browse"]
["browse", libraryId]
["browse", libraryId, normalizedPath, limit, includeOffline]
["browse-infinite"]
["browse-infinite", libraryId]
["browse-infinite", libraryId, normalizedPath, limit, includeOffline]
["folder-children", normalizedPath]
["search-v2", persistableSearchRequest(request), request.limit]
["search-count", persistableSearchRequest(request)]
["metadata", normalizedPath, contentVersion ?? null]
["facets", canonicalScope, libraryId, normalizedPath]
["related-assets", request]
["search-capabilities"]
["prompt-usage", request]
["search-indexes"]
["search-indexes", libraryId ?? null]
["status"]
["status", "libraries", "batch"]
["status", "library", libraryId]
["status", "path", libraryId]
["status", "path", libraryId, normalizedPath]
["library-inspector"]
["library-inspector", query.trim(), scope, normalizedPath, limit, sort, model.trim(), prompt]
["library-inspector-metadata", normalizedPath]
["maintenance"]
["maintenance", "file-health"]
```

### Admin Library Health

```text
/admin/libraries
-> LibraryListPage.vue
-> library list, batch status, update-all, and per-library navigation

/admin/libraries/:id
-> LibraryDetailPage.vue
-> GET /api/libraries/{id}/status
-> GET /api/derivatives/status?library_id=...
-> Generated image cache, Live status, Problems, jobs, stats, update/edit/delete

/admin/maintenance
-> MaintenancePage.vue
-> image-cache summary by querying registered libraries
-> POST /api/maintenance/imported-data/rebuild for all-library imported-data rebuild
-> POST /api/maintenance/imported-data/clear for all-library imported-data clearing
-> POST /api/maintenance/catalog/reset from Settings Danger Zone
-> GET /api/maintenance/file-health for latest File issues and Repair results
-> POST /api/maintenance/file-health/check from Check files
-> GET /api/maintenance/runtime for catalog, metadata, and image-cache worker/queue health
```

Primary admin UI labels intentionally avoid backend terms such as derivatives,
runtime, diagnostics, and integrity. User-facing labels are `Generated image cache`,
`Live status`, `Problems`, `File issues`, `Check files`, and `Repair results`.
Library Detail presents one cache progress row per configured image size so the
number of generated files is never mistaken for the number of source images.

## Data Flow

### Folder Load

```text
Folder selection
-> Pinia gallery store updates current path/history
-> useInfiniteBrowseQuery(libraryId, path)
-> GET /api/browse?library_id=...
-> TanStack Query stores pages under ["browse-infinite", libraryId, normalizedPath, IMAGE_PAGE_SIZE]
-> GalleryGrid renders folders and mixed-media rows
```

First uncached folder loads can show a skeleton. Cached revisits render immediately and show only subtle refresh state while Query refetches in the background.

### Folder Tree Expansion

```text
FolderTreeItem toggle
-> Pinia stores expanded/collapsed path state
-> useFolderChildrenQuery(path, enabled)
-> GET /api/folders when cache policy requires it
-> FolderTreeItem renders Query-owned child folder rows
```

Folder expansion state is UI state. Query-owned `FileNode` results should not be mutated to store expansion state.

### Infinite Scroll

```text
IntersectionObserver sees load-more sentinel
-> guard hasNextPage and fetch-in-progress flags
-> fetchNextPage()
-> GET /api/browse?library_id=...&cursor=...
-> TanStack Query appends page
-> grid rows recompute
```

### Search, Advanced Search, and Facets

```text
Header search or AdvancedSearchDrawer
-> Pinia stores search text/scope
-> useSearchUrlSync() encodes versioned shareable state after library hydration
-> useSearchCapabilitiesQuery()/usePromptUsageQuery()/useSearchIndexStatusQuery() own discovery server state
-> useUnifiedSearchQuery()
-> POST /api/search/query with a canonical ID-scoped request
-> SearchResultsPanel renders first-page Album suggestions and an appended Media stream
```

- The typed query settles on one 250 ms debounce (`GALLERY_SEARCH_DEBOUNCE_MS`,
  shared with the drawer match preview). Enter settles the submitted text at once.
  `useUnifiedSearchQuery()` keeps the last settled pages as placeholder data while
  newer text settles, so results stay on screen between keystrokes; it sends no
  request for empty text, and `/api/search/count` runs only for settled, non-empty
  text. Composition text is not part of the query: `components/ui/Input.vue`
  and the header/mobile inputs apply the committed text on `compositionend`.
- Canonical scopes are `folder` (one authorized folder recursively), `library`
  (one registered library across all import paths), and `all`. Legacy GET
  `current` resolves through the same folder context and responses report the
  canonical `folder` value.
- Search and facets share one registered-ID/path resolver. A folder outside the
  selected library, a media-file path used as a folder, or a descendant with no
  catalog folder/active descendants returns `404`; invalid/missing scope values
  are `422`.
- `/api/search/query` is the active frontend contract. It accepts schema version
  1, lexical/workflow modes, a discriminated folder/library/all scope, and
  never accepts an absolute client path. Persisted/URL forms omit cursor and
  limit; query keys omit only cursor. Legacy `GET /api/search` authorizes its
  absolute-path inputs and adapts them into the same lexical executor.
- `/api/search/related` is a separate, non-persistable reference request. It
  reuses the canonical folder/library/all scope union, authorizes an active
  image reference before reading relation data, excludes the reference from
  results, and returns independent metadata/visual readiness. Generation
  signatures supply bounded metadata candidates and visual fingerprints supply
  indexed near-duplicate candidates. The combined `related` profile queries
  every usable stream, merges by stable asset identity, retains all typed
  evidence, and returns partial or empty results with readiness instead of
  failing when either stream is unavailable. Legacy `recipe` and `visual`
  profile consumers retain their single-index 409/503 readiness errors.
- Derived discovery indexes use durable per-library states and jobs. Claims
  carry worker ID, opaque token, and lease; completion is fenced. Workers read
  active assets by `asset_id` keyset in batches of at most 200, extract outside
  write transactions, and atomically persist one asset's derived rows plus its
  fingerprint/status. Metadata changes atomically invalidate initialized
  prompt/workflow/raw rows and coalesce a durable missing rebuild. Expired claims are recovered in
  the next claim transaction, while startup recovery remains the process-crash
  safety net. Optional index failure never disables lexical search.
- `prompt_values` and `workflow_properties` build automatically (IM-4). After a
  metadata commit, `_schedule_derived_search_backfills` calls
  `schedule_auto_built_search_indexes(library_id)`, which coalesces one `missing`
  job per index once the library has no `queued` or `running` metadata job
  (`library_has_active_metadata_jobs`), so a new library gets both without
  pressing Rebuild and a partly extracted library does not start early. At
  startup, after the search-index worker starts, `schedule_startup_search_index_backfills`
  does the same for libraries that predate auto-building (no state, stale
  versions, `failed`, `degraded`, `pending`); a library whose index is already
  `ready` at the current versions gets no new job, and one that still has metadata
  work waits for the commit hook. A failure there is logged and never blocks
  startup. `workflow_raw` stays opt-in (own storage budget): it is scheduled only
  after it has been initialized, and the single derived-index writer and job
  coalescing are unchanged. Measured on a 10,000-image library (A1111 and ComfyUI
  metadata, this machine, isolated server): about 45 s and +16 MB of database per
  index, +5 to 47 MB peak RSS, 15 to 19 % writer occupancy; with a back-to-back
  `/api/browse` load running, each backfill takes 65 to 70 s and browse p95 rises from about
  35 ms to about 130 ms for that minute, the same as the already automatic
  `generation_signatures` backfill (75 s, p95 143 ms). The Maintenance pipeline shows the
  state of both as an unnumbered note ("Search indexes: prompt groups ready,
  workflow fields building 40 %") from `GET /api/search/indexes`.
- Capabilities distinguish disabled features (`409 FEATURE_DISABLED`) from an
  enabled but unusable required index (`503 SEARCH_INDEX_NOT_READY` with
  `Retry-After`). Index status exposes `state` separately from `usable`; an old
  usable index remains available with a warning during rebuild or degradation.
- Search returns bounded `media` pages with opaque string `next_cursor`, `has_more`,
  `returned`, and `limit`. Legacy `albums`, `photos`, `videos`, and `prompt`
  fields remain for compatibility; the active gallery search UI renders
  `media`.
- TanStack Query passes its `AbortSignal` through the HTTP client. Canonical media pages
  deduplicate by `(library_id, asset_id)` and use the exact case-preserved path
  only for compatibility rows that lack IDs; legacy arrays are consumed only
  when canonical `media` is absent.
- Ranked search folds the query with `fold_text` and reads only the folded FTS tables.
  Word-prefix matching is the primary relevance tier at every query length: filename
  exact 100, filename prefix 90, filename word prefix 70, prompt phrase 80, prompt word
  prefix 65, model/sampler word prefix 65, negative prompt word prefix 40. Latin queries
  whose tokens all have three or more characters add a secondary substring (trigram)
  tier that ranks below every prefix match (prompt phrase 39, filename 38, prompt 37,
  model/sampler 36, negative prompt 35), so for a Latin query q and q+c the prefix-tier
  results of q+c are a subset of those of q (typing `mi`, `mik`, `mika` keeps `mika` and
  `mikan` ahead of `kamikaze`). Queries with CJK text keep substring semantics as the
  primary tier. Any query with a token shorter than three characters uses the prefix
  tier only: Latin terms prefix-match tokens (`ch` matches `cherry`), and CJK runs match through the CJK bigram
  index (a 1-character CJK term is a prefix on bigrams and run-end tokens, a longer
  CJK run is a bigram phrase, so `少女` matches inside `桜の下の少女`). All terms are
  ANDed; a mixed Latin and CJK query matches the Latin terms on the Unicode table
  and constrains rows with `rowid IN` the CJK table. Tiers, bounded preselection
  and keyset cursors are unchanged. Hangul is space-delimited and uses Unicode token
  prefixes. Full-table LIKE is reserved for the FTS-unavailable degraded path. Metadata trigram queries retain AND-token
  semantics, and unscoped FTS plus structured-filter-only sources use bounded,
  cursor-aware preselection before strict catalog authorization. The candidate union also includes
  positive-prompt phrase tiers, negative prompts, and structured-filter-only rows. It
  deduplicates by stable asset ID and orders by relevance tier, a
  bounded/rounded FTS rank, source `mtime_ns`, then `asset_id`.
- Search planning (BL-13: every query, including dense one-character queries such as `a`,
  `m`, `c`, `prompt:c` and `name:a`, stays within the 300 ms p95 budget on the 100k fixture).
  Unscoped free-text pages run as a tier-ordered plan in `ranked_search._run_page_plan`
  instead of one statement over every source. Each candidate SELECT is a `_Source` that
  knows its tier range; the planner reads sources from the highest tier down, merges their
  rows exactly as the old statement did (best row per asset, cursor, relevance order) and
  stops once a full page outranks every source left. A one-character query is therefore
  served from the prompt-phrase tier without ranking every filename and model match, and a
  source whose tiers all precede the cursor is never run. Each source still yields its
  complete bounded candidate set (not just a page), so a row shadowed by a better row of the
  same asset never costs the page a slot and the merged page equals the old statement's page.
  A filename source whose FTS match set is large (more than `FILE_SOURCE_SMALL_LIMIT`, probed
  with a rank-free early-exit count) is read through bounded `hi` (exact and prefix filename
  matches, found by scanning the compact folded names with the FTS table as a membership
  test) and `lo` (everything else, bm25-ranked) variants that keep the best
  `fts_candidate_limit` rows after the cursor before the strict ownership joins run; a small
  one is read whole so cross-source shadowing stays exact. The bounded preselects sort an
  integer bm25 key in millionths (the page rank is that value / 1e6, equal to
  `round(bm25, 6)`; sorting `round(rank, 6)` on every match cost about 50 ms per 100k
  matches), and the cursor test reads each key once through a row-value comparison whose
  asset-id tie-break only runs on an exact key tie, so paging advances through more tied rows
  than the preselect holds. Structured-filter-only queries (`prompt:c`) probe
  `image_metadata` newest first through `idx_image_metadata_inspector_date` and stop at the
  candidate limit; a filter too sparse for the probe's row budget uses the sorting plan.
  Legacy offset cursors and the LIKE fallback keep the single-statement plan. `GET /api/search`
  and the v2 endpoints resolve `scope=all` without listing libraries (the listing counts every
  asset and is not needed); library and folder scopes list them without the asset count.
  Scoped (`folder`, `library`) and field-filtered text queries (SC-01) run the same tier-ordered
  plan in its exact mode. The scope (`ranked_search._ScopeFilter`: a sargable path range
  `[root/, root0)` that only matches whole path components, plus the library id) and the field
  conditions are applied *inside* each bounded preselect, before it cuts to the best
  `fts_candidate_limit` rows, so the bound keeps the best rows inside the scope and equals the
  unbounded statement's top rows. A library predicate that every file row satisfies is dropped from
  the preselect (the strict statement still applies it). Each bounded source runs as two statements
  (preselect, then the strict ownership joins on exactly those rows), so the plan knows when a
  preselect was cut short and the joins dropped rows (offline, mismatched or unowned assets): it
  retries that source with an active-asset join in the preselect, and if rows are still lost, or a
  cut-short source does not cover the whole page, it runs the exact single statement. A cut-short
  source covers only the rows strictly before the (tier, rank, mtime) of its last row: the preselect
  breaks ties by its own row id, not the page's asset id, so the boundary tie group is never trusted. On keyset
  pages an asset that also has a row at or before the cursor in another source is dropped (the
  unbounded statements of the sources that can hold such a row are read for the candidate paths
  only). A scoped or fielded page therefore equals the exact statement's page, with none of the
  cross-source repeats described below. Album suggestions read folders by type (`INDEXED BY
  idx_file_index_type`) under a scope, and the scoped count keeps the capped distinct streaming
  statements with the sargable scope. `backend/tests/test_search_scoped_pins.py` pins and
  cross-checks all of it.
  The unscoped plan has the same cover rule without the two-statement split (BL-16): a bounded source is read in
  one statement, and when it returns a full `fts_candidate_limit` rows it may have been cut short, so its cover is the
  (tier, rank, mtime) of its last row. The page must end strictly before every cover, otherwise the plan gives up and
  the caller runs the exact statement. This costs no extra query. Known limit: a cut-short preselect that loses rows
  to the strict ownership joins (offline or deleted assets) returns fewer than the bound and is not seen as cut
  short; the unscoped plan has never retried those, and detecting them would need the preselect row count (a second
  statement per source), so it is documented rather than paid for.
  Ranked-window cache (BL-15): a dense query ranks the whole FTS match set of each bounded source (about 100k
  rows) to keep its best `fts_candidate_limit` rows after the cursor, and a keyset chain used to repeat that on
  every page. `search_window_cache.SEARCH_WINDOW_CACHE` now keeps, per request (the cursor fingerprint, the
  candidate limit, the video and exact-plan flags) and bounded source, the rows that source returned after the
  cursor of the page that read it. Page 1 always reads its sources and refreshes the entries. A keyset page whose
  cursor is at or after an entry's bound filters the cached rows after its own cursor instead of running the source;
  the cached source's cover is the cache's (the last cached row's tier, rank and mtime), so a page that reaches it,
  or a cursor past the cached list, makes the plan give up and `search_ranked_media_page` runs the plan again
  with the cache off (and refreshes the entries from the new cursor). Pages are therefore the pages of the
  uncached plan. Not cached: fielded and filtered queries (they read the metadata filter tables), whole-read
  small filename sources, and, in the unscoped plan, a source that returned fewer than the bound (it is either a
  tiny match set or a cut-short preselect that lost rows to the strict joins, and the single statement cannot
  tell which, so a lossy list must not be served as complete). The scoped (exact) plan caches the strict
  survivors of a preselect together with whether the preselect was cut short, and its shadow checks still run per
  page. Measured: keyset pages 2-3 of the dense classes fall from about 210-230 ms to 8-25 ms p50 on the 100k
  fixture, scoped or not; page 1 is unchanged.
  Invalidation is a database row, not an in-process hook: `search_generation(id, value, epoch)` is bumped by
  triggers (`_schema_ddl.SEARCH_GENERATION_TRIGGERS`, created by the additive `_ensure_search_generation`, no
  catalog version bump) in the transaction of every insert, delete and relevant update of `image_metadata`,
  `image_metadata_fold`, `image_metadata_cjk`, `file_index`, `file_index_fold`, `assets` (path, name, type, mtime,
  size, dimensions, `offline`, `deleted_at`, library, mime type and duration; not `metadata_state`, `indexed_at`
  or scan stamps), `libraries` (id, name) and `library_import_paths` (library, path). Triggers cover every
  writer (the database writer thread, direct write paths, other processes, maintenance and migrations) and
  commit atomically with the data they describe, which an in-process hook at the writer layer cannot promise
  (a bump before commit lets a reader cache the old data under the new generation) and could miss any path
  that does not go through it. Each request reads `(epoch, value)` before any data, so an entry written under
  that value is at worst too old to serve, never newer than its data; an entry of another value is dropped on its
  next lookup, and `epoch` (random per database file) keeps a database re-created at the same path from matching
  older entries. The FTS virtual tables cannot carry triggers; their writers (`file_index.py`) always change
  `file_index` or the fold tables in the same transaction. Bounded: `GALLERY_SEARCH_WINDOW_CACHE_ENTRIES`
  (128) entries and `GALLERY_SEARCH_WINDOW_CACHE_MB` (32) MiB of estimated row memory, least recently used
  first; 0 turns it off. One lock guards the table and the cached rows are read-only. Cost: one extra row update
  per write of a watched row, skipped where the old and new values of the relevant columns are equal.
  Known behaviour of the unscoped, unfiltered plan only: a row that matches in two sources of different tiers can be returned once
  per source across keyset pages (the per-source cursor pre-filter runs before the
  cross-source dedup; this predates the plan). The bounded filename variants of a large match
  set pre-filter by the cursor too, so on pages after the first an asset whose filename match
  was already returned can come back through its prompt or model match. A small filename
  match set keeps the exact old shadowing. Clients deduplicate by asset id.
- `POST /api/search/count` counts distinct matching assets up to `COUNT_CAP` (4096) and
  stops there: it streams rank-free candidates through `DISTINCT ... LIMIT`, so a dense query
  costs about the cap in strict-ownership probes instead of one per match, and the total is
  the `+` convention above the cap. Below the cap it equals the paged total of distinct
  assets; a plain-text count includes video rows like the plain search. A field-only count
  probes the first `COUNT_PROBE_ROWS` metadata rows row by row and only builds the match set
  when the filter is too sparse for that.
- Active pagination is keyset-only. The versioned base64url JSON cursor is bound
  to the canonical query/scope/root fingerprint and stores the complete final
  ordering tuple. Malformed, wrong-version, or wrong-request cursors return
  `400`. Decimal cursors are accepted only by legacy `GET /api/search`, use the
  old offset path for that request, and emit `Deprecation`/`Warning` headers;
  responses always return opaque cursors.
- Media rows are joined to their active asset, registered library, and import
  path ownership in SQLite and include `asset_id`, `library_id`, and
  `library_name`. Search does not perform per-result path resolution or
  existence checks.
- Album suggestions are returned only on the first search page. Their direct
  image count, three newest direct covers, and child visibility reuse the same
  bounded catalog aggregation as DB-first browse (schema v15's
  `idx_assets_folder_images` for owned folders); search never enumerates the
  source directory.
- Watcher, scan, offline-asset, and integrity workflows reconcile stale catalog
  state. Search reflects the current catalog snapshot and never schedules
  cleanup from a response.
- Fielded queries are parsed server-side, for example `prompt:"blue hair"`, `seed:12345`, `model:pony`, `steps:>25`, `width:>=1024`. A shared JSON grammar contract covers single/double quotes, escaping, operators, repeated fields, aliases, pass-through tokens, and Unicode in pytest and Vitest.
- Recognized field filters fail closed: malformed numeric comparisons, numeric
  equalities, or
  dimensions return `422` rather than silently dropping the predicate.
- Library Inspector cursors validate JSON types, finite values, and SQLite
  integer bounds before binding. Its keyset uses nanosecond mtime ordering and
  bounded DB preselection; the managed suite separately measures the API and
  the 100k-row DB-only store path. Facets materialize authorized active/current
  rows once per request instead of repeating the ownership predicate for every
  aggregation.
- Fielded search keeps metadata filters scoped to filterable image/prompt
  media; filename-only videos are not returned for fielded queries unless a
  future video metadata index supports the same predicates.
- The shared Advanced Search drawer is owned by `App.vue`, uses TanStack Form
  for fielded metadata drafts, and composes separate automatic recent-search, prompt,
  indexed-facet summary, workflow, raw, and index-status children. Children keep local drafts and emit
  typed canonical requests; `App.vue` applies library/import-path navigation
  and Pinia session state. It renders as a right sheet on tablet/desktop and a
  full-width sheet on compact mobile viewports.
- TanStack Query owns capabilities, prompt usage pages, index states/jobs, raw
  search mutations, facets, and canonical result pages. Pinia owns only the
  active query/scope/mode/filters and navigation/UI state. Filter-only prompt
  or workflow requests are active searches even when their lexical text is empty.
- Active search replaces browse sorting with a visible `Relevance` label. Search feedback distinguishes initial pending, blocking error, stale-data warning, next-page error, and successful empty states on desktop, tablet, and mobile.
- Search result rows register their rendered elements with TanStack Virtual so
  hydrated URL searches with long filenames, paths, match badges, snippets, or
  library labels use measured heights. Absolute virtual rows must never rely on
  estimates alone or allow the next thumbnail row to overlap result metadata.
- Image-card and lightbox overflow actions open the global Related Assets
  sheet with the current canonical scope. The sheet always sends the combined
  `related` profile and has no match-type tab, selector, or persisted selection.
  TanStack Query owns each complete reference/scope response and forwards cancellation through the HTTP client.
  Reference changes use a new key and do not show the prior reference's data;
  a failed background refresh retains the last successful response with a
  visible retry action. The ephemeral Pinia store owns only sheet state.
- Related results reuse `PhotoCard` and the existing lightbox item list. Stable
  reason codes map to concise evidence chips and fixed tier labels. Backend
  merging deduplicates and unions metadata/visual evidence; frontend response
  normalization defensively does the same while preserving first-seen server
  order. The modal does not fetch or render candidate generation metadata;
  ranking and evidence calculation remain backend-owned.
- Smart-collection descriptors contain either a canonical Search V2 request or
  a persisted relation/fact descriptor. They do not persist materialized asset
  membership and Related Assets sessions never enter saved/recent search state.
- Search URL state uses `search_v=1` plus bounded base64url structured groups.
  Debounced edits replace browser history; committed actions push; guarded
  hydration applies Back/Forward without a write loop. Up to 20 successful
  searches are deduplicated automatically in versioned browser-local history
  while preserving case-sensitive values. The UI does not require naming,
  saving, pinning, or managing reusable queries.
- `GET /api/search-metadata` remains available for older callers, returns the
  catalog-filtered global total, and follows the same DB-only response policy;
  the main gallery UI uses `POST /api/search/query`.
- Search, legacy metadata search, and facets use regular Pydantic response
  models and explicit synchronous FastAPI path operations. OpenAPI documents
  canonical media/album rows, legacy projections, facet values, opaque cursor
  types, sanitized 400/404/503/500 envelopes, and the `422` union of public API
  errors plus FastAPI validation errors.
- Desktop search surfaces show a fixed Relevance indicator while lexical or
  structured search is active; ordinary browsing uses `SortSelect.vue`.
  `MobileHeader.vue` still uses `SortDropdown.vue` outside search.

### Library Inspector

```text
/metadata route
-> LibraryInspector.vue
-> useLibraryInspectorFilters + useInfiniteLibraryInspectorQuery
-> GET /api/library/inspector
-> model/prompt filters and name/date sort are applied by SQLite before cursor pagination
-> LibraryInspectorToolbar.vue owns typed filter/sort/column controls
-> TanStack Table uses the server order and owns column visibility/header state
-> TanStack Virtual renders the table body rows
-> popovers/copy actions fetch GET /api/library/inspector/metadata
```

The inspector is read-only. It is backed by indexed SQLite metadata and opens images in the same lightbox store used by the gallery. Model and prompt-presence predicates are applied before the SQL limit/cursor, so an empty visible page means the filtered result is exhausted rather than merely absent from already-loaded client pages. The table uses cursor-based infinite pagination plus body virtualization, so the DOM only contains the visible row window plus small overscan/spacer rows rather than every loaded row.

### Open Image

```text
PhotoCard or inspector row click
-> lightboxStore.open({ path, name }, visibleImages)
-> PhotoSwipe wrapper opens derivative-first item
-> usePhotoMetadataQuery(path, content_version)
-> GET /api/metadata
-> active device panel/sheet renders metadata
```

The metadata query key is `["metadata", path, content_version]`. A rescanned file
has a new `content_version`, so its open lightbox refetches instead of showing
metadata cached before the change; the same version keeps the 10 minute cache.
PhotoSwipe's dimension reads use the same key for the same item, so they share
one entry with the metadata panel. The request URL carries no version.

PhotoSwipe normal `src` is `/api/preview`. The original `/api/image` is used for explicit original-load paths such as zoom/fullscreen/download settings or animated images.

## Lightbox Design

`Lightbox.vue` dispatches by device:

```text
Desktop/Wide -> PhotoSwipeViewer.vue + LightboxDesktopPanel.vue
Tablet       -> TabletPhotoSwipe.vue + LightboxTabletPanel.vue
Mobile       -> MobilePhotoSwipe.vue + LightboxMobileSheet.vue
```

- All PhotoSwipe wrappers share `usePhotoSwipe.ts` for lifecycle, item creation, index sync, and destroy guards.
- Lightbox item URL construction lives in `frontend/src/utils/lightbox.ts`.
- `usePhotoSwipe.ts` hands PhotoSwipe a lazily built data source (`utils/lightboxLazyList.ts`, a `Proxy` over an
  array): `buildPhotoSwipeItem` runs the first time an index is read, so opening a lightbox over a 200-item
  album builds the opening item and its neighbours instead of all 200 (about 15 ms of the click task at 4x CPU).
  `Array.isArray`, `length`, indexing, `map` and mutation behave as on a plain array.
- Desktop reserves `DESKTOP_METADATA_WIDTH` through PhotoSwipe padding so the image is not hidden under the metadata sidebar.
- Tablet uses custom top/bottom controls and a bottom metadata panel.
- Mobile uses `@douxcode/vue-spring-bottom-sheet` as a non-modal metadata sheet inside PhotoSwipe.

Mobile sheet contract:

- PhotoSwipe owns image rendering, swipe, pan/zoom, keyboard/focus context, and lightbox lifecycle.
- VSBS owns mobile sheet drag, snap, scroll, and animation only.
- Gallery glue owns the info button, outside-tap sheet close, tab content, copy actions, prompt expansion, and protections that preserve PhotoSwipe gestures.
- Keep VSBS `blocking=false`; do not add a second focus trap inside PhotoSwipe.

## Layout Dispatch

`App.vue` selects the layout from `useDevice()`:

```vue
<MobileLayout v-if="isMobile" />
<TabletLayout v-else-if="isTablet" />
<DesktopLayout v-else />
```

| Device                  | Layout              | Sidebar                        | Grid                      |
| ----------------------- | ------------------- | ------------------------------ | ------------------------- |
| Mobile `<768px`         | `MobileLayout.vue`  | Overlay/mobile shell           | TanStack Virtual row grid |
| Tablet `768-1199px`     | `TabletLayout.vue`  | Drawer/sidebar shell           | TanStack Virtual row grid |
| Desktop/Wide `>=1200px` | `DesktopLayout.vue` | Persistent/collapsible sidebar | TanStack Virtual row grid |

## Initial Load Path

The cold-load critical path (measured on the Lighthouse slow-4G mobile profile) is
kept short by these rules; keep them when moving components between chunks:

- `vite.config.ts` `earlyChunkPreload()` injects an inline `<head>` script into the
  built `index.html` that adds `modulepreload` (JS) and `preload as=style` (CSS)
  links for the static chunk graph of `GalleryRoute.vue` (only on `/`) and of the
  layout for the current viewport. `router.isReady()` waits for the route chunk
  before `main.ts` mounts the app, so without this the route graph only started
  downloading after the entry had executed. The layout widths in the plugin mirror
  `BREAKPOINTS` in `useDevice.ts`.
- `main.ts` prefetches the library list (`queryKeys.libraries()` +
  `fetchLibraries`, deduplicated by TanStack Query) and imports the viewport's
  layout module before `router.isReady()` resolves. The reload black box
  (`src/debug/reloadBlackBox.ts`) is a dynamic import, downloaded only when
  `?debugReload` or `GALLERY_DEBUG_RELOAD` is set.
- `main.ts` also calls `startHomeBrowsePrefetch` (`utils/homeBrowsePrefetch.ts`) as soon as the library
  list settles. On `/` without a query string it resolves the library the gallery will open (the persisted
  selection, else the only library with an import path; the same choice `hydrateActiveLibrary` makes, without its
  side effects) and runs `queryClient.prefetchInfiniteQuery` for that library's root folder with the exact key and
  function of `useInfiniteBrowseQuery` (`browseInfiniteQueryKey`, `fetchBrowsePage`, `getNextBrowsePageParam`,
  `BROWSE_STALE_TIME_MS`, exported from that composable so the two cannot drift). The mounted query finds the page
  cached, or joins the request still in flight, instead of starting it after the route chunks and mount. Once the
  page is cached it requests the cover of the first folder in the user's sort order (`sortByPreference`, the
  grid's own ordering) with `new Image()` at `fetchPriority = "high"` and the card's exact thumbnail URL, so the
  likely LCP image is already loading when the card renders; skipped when the album strip is collapsed
  (`gallery-albums-collapsed-v2`). Every step is best effort: no stored library, an unknown library, a failed
  request, throwing storage or a non-home URL end silently and the mounted app loads as before. Do not add
  covers beyond the first here: each extra one competes with the route chunks that gate mount.
- The early chunk preload script in `index.html` sits after the render-blocking stylesheet, so the browser only
  runs it once the main CSS has loaded. Do not move it earlier: on the HTTP/2 + gzip lab setup (fair-share
  streams) 45 preloads started at t = 0 delayed the entry module from 1.0 s to 2.0 s, and with it the library and
  browse requests, which made LCP worse (3.2 s against 2.75 s on slow 4G). Mount is bandwidth-bound: the entry, Vue,
  icons, CSS and the gallery route graph must arrive before the app mounts (about 308 KB gzip before the payload
  work below, about 284 KB gzip / 251 KB Brotli after it, at 1.6 Mbps each ~20 KB is ~0.1 s).
- **Mount-critical payload (Track P).** Keep these when adding code to the home graph:
  - `vite.config.ts` `precompressAssets()` (`src/build/precompressAssets.ts`) writes `.br` (q11) and `.gz` (9)
    siblings of every text asset; nginx serves them with `brotli_static` / `gzip_static` (see
    `docs/CONFIGURATION.md`). Without the Brotli module the `.gz` files and dynamic gzip still work.
  - `motion-v` runs through `LazyMotion` with the synchronous `domAnimation` bundle (`MotionProvider.vue`), and every
    animated element is an `m.*` component. The full `motion.*` component bundles layout projection, drag and pan
    code (about 36 KB raw) that the app never uses; `src/components/__tests__/MotionProvider.test.ts` fails if a
    file imports `motion` again. `MotionProvider` is its own chunk (`loadMotionProvider.ts`, in the early preload
    list, awaited by `main.ts` before the first mount) because everything in the entry chunk delays the first API
    requests, which start when the entry executes. The feature bundle is passed as an object, not a loader, so the
    first render and every animation are the same as with `motion.*`; do not make it asynchronous.
  - fuse.js and the search results panel are not in the home graph. `utils/fuzzySearch.ts` is a synchronous facade
    over `utils/fuzzySearchEngine.ts` (the only importer of fuse.js; until the engine has loaded it returns the list
    unfiltered and re-evaluates dependent computeds when it arrives), and `components/search/SearchResultsPanel.vue`
    is a lazy wrapper over `SearchResultsPanelImpl.vue`. `utils/searchChunks.ts` (started by `GalleryRoute.vue`)
    loads both when the URL carries a search, on the first text-field focus, and after `load` + idle.
  - Tooltip and popover content cannot leave the home graph by themselves: reka-ui's `PopperContent` and
    floating-ui are also imported by the dropdown menus and the selects on the home route (the select must render
    its items to show its value), so making only `TooltipContent` / `PopoverContent` lazy removed 0.9 KB gzip and was
    dropped.
- **Layout stability (CLS).** Two things moved the desktop layout on cold loads (0.03–0.2 at 1440 px) and are
  fixed; keep them when touching the header, sidebar or start-up:
  - The brand title (`.brand-title`, Cinzel 600, 42 px) sits in a width-limited header box. Cinzel is ~23% wider
    than a Times-style fallback, so when it swapped in (`font-display: swap`) the title wrapped to a second line
    (+63 px) and pushed the toolbar, sidebar and content down. `fonts.css` declares `"Cinzel Fallback"`, a
    `local()`-only face (Times New Roman / Liberation Serif / Tinos / Times, bold) with `size-adjust: 123%`, and
    `.brand-title` uses `"Cinzel", "Cinzel Fallback", serif`, so the stand-in wraps like Cinzel. It downloads
    nothing and the settled rendering is Cinzel as before. Re-measure `size-adjust` if the title text, weight or
    letter-spacing change.
  - `LibrarySidebarHeader`, the breadcrumb and the toolbar render differently before the active library is
    hydrated (sidebar +81 px, breadcrumb and action buttons move). `App.vue` hydrates synchronously in setup when
    the library list is already cached, so `main.ts` holds the first mount for the list prefetch for at most
    `LIBRARIES_MOUNT_WAIT_MS` (300 ms, `utils/settleWithin.ts`). On slow links the list arrives long before the
    route chunks, so the wait costs nothing there; if the list is slower than 300 ms the app mounts anyway and
    shows the pre-hydration state as before.
  Guard: `tests/e2e/perf/home-layout-shift.spec.ts` (production build only; CLS < 0.01 at 1440×900 and 390×844).
- `App.vue` mounts `Lightbox` and `RelatedAssetsPanel` lazily: as soon as their
  store opens, otherwise after `load` + a settle delay + an idle period
  (`utils/idleAfterLoad.ts`). `MobileLayout.vue` loads `GallerySidebarContent`
  the same way (its sheet content only renders when opened). Their chunks no
  longer compete with the first thumbnails. `Lightbox.vue` watches its open state
  with `immediate: true` because it can mount already open.
- `manualChunks` puts `lucide-vue-next` icons into one `icons` chunk and Vue
  into a `vue` chunk (both preloaded by `index.html`) instead of ~20 sub-1 KB
  icon chunks per route.
- Above-the-fold album covers (`priority` prop on `AlbumCard*.vue`, set for the
  first covers by `AlbumCarouselDesktop.vue` / `AlbumScrollerNative.vue`) and the
  first photo row (`fetchPriority="high"` on `PhotoCard.vue` from
  `GalleryGrid.vue`) load eagerly at high fetch priority and skip the visibility
  gate below; everything else stays `loading="lazy"` and is gated.
- Cinzel, Inter and JetBrains Mono are self-hosted from
  `frontend/src/assets/fonts/` (`fonts.css`, SIL OFL 1.1 license files beside
  them). The files and `@font-face` rules are the ones Google Fonts served, so
  rendering is unchanged, but there is no third-party render-blocking stylesheet.
- nginx must serve the build with HTTP/2, gzip and immutable `/assets/` caching
  (see `docs/CONFIGURATION.md`, "Server runtime topology").

## Grid Image Loading

Grid thumbnails and album covers are loaded on demand so a fast scroll only
downloads what the user rests on:

- `composables/useVisibleLoadGate.ts` observes each `PhotoCard` / `AlbumCard*`
  with an `IntersectionObserver` whose root is the nearest scroll container
  (`findScrollRoot`; a `rootMargin` only grows the root, so the viewport would
  never see cards just outside the scroller). A card that comes into range while
  its scroll root is at rest (no scroll event for 150 ms, `SCROLL_IDLE_MS`: album
  open, settling after a scroll, tab switch, resize) sets `shouldLoad` at once.
  While the root is actively scrolling the card must stay in range for 120 ms
  (`VISIBLE_LOAD_DWELL_MS`), and a card still pending when scrolling stops starts
  immediately. One scroll listener per root is shared by all cards. Photo cards
  use a 200 px vertical margin, album covers a 400 px horizontal one.
- The card binds `src` to `shouldLoad ? url : undefined`. When the card leaves
  before the image settled, `shouldLoad` goes back to false and the cleared `src`
  makes the browser cancel the request; unmounting an unfinished `PhotoCard`
  (virtual rows) removes `src` explicitly because a detached `<img>` keeps
  downloading. Loaded images are never cancelled, and an `error` event from a
  cleared `src` is ignored (`PhotoCard.onImageError`, `useCoverImageLoad`).
- Skipped by the gate: first-row cards (`fetchPriority="high"`), `priority` album
  covers, and thumbnails that already loaded once this session
  (`seenThumbnailUrls` in `PhotoCard.vue`, so a virtual row scrolled back into
  range does not wait again). The shimmer/skeleton is unchanged: it shows until
  `load`.
- **Versioned URLs.** Browse, search and related items carry `content_version` and folders carry
  `cover_versions` (see "Versioned URLs (B3)"). `getThumbnailUrl(path, edge, version)` and
  `getPreviewUrl(path, edge, version)` in `services/api.ts` append `&v=<version>` after `max_long_edge`
  when a non-empty version is given, so the backend answers `immutable` and a revisit costs no request.
  Every call site passes the version it has: `PhotoCard` (`version` prop from `GalleryGrid`,
  `SearchResultsPanel`, `RelatedAssetsPanel`), the album cards (`cover_versions[i]` of the cover they
  show; the search and gallery mappers copy `content_version` / `cover_versions` into `FileNode`), and
  the lightbox (`buildPhotoSwipeItem` for `src`, `previewSrc` and the `msrc` placeholder, and the
  preview dimension probe in `usePhotoSwipe.ts`, all from `FileNode.content_version`). An item without a
  version (inspector rows, prompt-usage samples, older responses, an empty `cover_versions` entry) keeps
  today's unversioned URL.
- **`srcset` / `sizes` (`PhotoCard`).** The thumbnail offers
  `srcset="<256 url> 256w, <512 url> 512w"`; `src` stays the 512 px URL (browsers that ignore `srcset`
  and the unmeasured case behave as before). `sizes` is the card's rendered width, measured in
  `onMounted` and kept current by one shared `ResizeObserver` (`useRenderedWidth`), multiplied by the
  image's long/short edge ratio (`utils/thumbnailSizes.ts`; `imageWidth` / `imageHeight` props, a wide
  default when unknown). The ratio matters because the card shows the image with `object-fit: cover`:
  the 256 px derivative of a 3:2 photo is only 171 px high, so it must not be picked for a 230 px card.
  The result: desktop DPR 1 square-ish cards pick 256, mobile DPR 2+ and 3:2 photos in wide cards keep
  512, and the picture is never upscaled. `srcset` follows `src` through the F1 gate (set only when the
  gate allows loading, cleared on cancel and unmount), only applies to the default 512 `thumbnailSize`,
  and is left out while the card has no measured width (jsdom, `display: none`). The `dimensions`
  event may therefore report the 256 px natural size; `lightboxStore.rememberDimensions` ignores
  `source: "thumbnail"` dimensions, so nothing depends on it.
- **Album covers have no `srcset`.** The browse API gives a cover's path and version but not its dimensions,
  so `thumbnailSizes` can only use the unknown-aspect ratio (2), under which a card wider than 128 px at DPR 1
  keeps the 512 px derivative. The covers' rendered widths (390 px phone 140 px at DPR 2, 1024 px tablet 198 px,
  1440 px desktop 165 px) therefore all resolve to 512, and a 256 px candidate would only change bytes by
  upscaling tall images. A cover `srcset` needs cover dimensions in `cover_images` metadata first. Covers keep
  one URL per cover (`getThumbnailUrl(path, 512, version)`), which the pre-mount cover request in "Initial
  Load Path" relies on: `homeBrowsePrefetch.test.ts` asserts that all three album cards ask for the same URL.
- **Retry of failed thumbnails and covers.** A cold album can answer `/api/thumbnail` with a 503 after
  its 10 s generation wait, and the derivative is ready a few seconds later. `<img>` does not expose the
  status, so every real `error` event (not the one a cleared `src` raises) is retryable:
  `composables/useImageRetry.ts` retries the same thumbnail up to 3 times after 1.5 s, 4 s and 10 s.
  A retry adds a throwaway `&r=<n>` to `src` and to every `srcset` candidate (`getThumbnailUrl(..., retry)`;
  the backend ignores unknown query parameters) so the browser requests again. While a retry is pending
  `PhotoCard` keeps the shimmer and the album covers keep their skeleton; the error placeholder (and the
  covers' settled state) only appears after the last retry failed. Leaving the viewport (the F1 gate turning
  `shouldLoad` off), unmounting or changing the image cancels the pending retry and resets the budget, so
  a card that comes back starts again from the plain URL. `useCoverImageLoad` exposes the same behaviour as
  `onCoverError` / `retryAttempt` / `resetRetry` for `AlbumCard*`.
- **Album-open thumbnail warm-up.** Album open is request-bound: the grid mounts about 150 ms (4x CPU)
  after the browse response lands, and until then no `<img>` exists. `useInfiniteBrowseQuery` takes an
  `onFirstPageFetched` hook that runs in the query function with each fresh first page, before Vue sees the
  data. `GalleryGrid.vue` uses it while the skeleton is on screen: the skeleton cell gives the card width, the
  row pitch and the grid top, `utils/thumbnailWarmup.ts` plans the thumbnails of the rows that start above the
  viewport bottom (after a 64 px header allowance, and 170 px more when the folder has subfolders; at most 24;
  videos and images whose 256/512 choice depends on the exact card width are skipped) and adds one
  `<link rel="preload" as="image">` each, with the same `href`, `imagesrcset` and `imagesizes`
  (`thumbnailSizes()`) as the `PhotoCard` `<img>`, `fetchpriority=high` for the first row. The browser picks the
  candidate exactly as it does for the `<img>`, and the card later claims the in-flight or finished response, so
  nothing is downloaded twice. The hook returns a promise that resolves in the next task, so the render that
  mounts the grid is not queued behind the request setup. The links leave `<head>` after 15 s. Without a
  skeleton (revisit, cache hit) nothing is warmed. Search results are not warmed.
- **Staged row mount.** Mounting every row in range at once was the album-open long task (about 120-170 ms at
  4x CPU). `useVirtualGridRows` takes a `rowBudget` ref (a `rangeExtractor` that keeps at most that many rows,
  counted from the first row of the range). `GalleryGrid.vue` starts a newly populated grid at budget 0 (the
  container and page chrome only), then 1 row, then `ceil(cards / columns)` rows per task (4 cards per step,
  doubled each time a step finished within 20 ms, up to 48), until the budget no longer limits the range. The
  steps are `setTimeout(0)` ticks, so the browser can paint and handle input between them. A scroll, or the
  grid unmounting, ends the staging at once (budget `Infinity`). Settled DOM and pixels are identical; the
  virtualizer's range (viewport plus `overscan: 5`) is unchanged.
- `GalleryGrid.vue` virtualizes all three layouts with the same
  `useVirtualGridRows` (`mediaRows`, `overscan: 5`). Mobile differs only in
  geometry: its rows are `top`-positioned (a fractional `translateY` would
  anti-alias the 1 px card border) and have no vertical gap, and the row height
  and the list offset below the album strip are measured from the DOM
  (`useUniformRowSize`, `useVirtualScrollMargin` in `useVirtualGridMetrics.ts`)
  instead of derived from `rowHeight`, because the rows are fractionally tall
  (e.g. 184.5 px) and `measureElement` rounds. The album strip and section header
  sit in `.mobile-grid-leading`, the load-more sentinel in `.scroller-footer`,
  both inside the same `.scroller` container that is provided to
  `galleryScrollContainerRefKey` (header/bottom-bar visibility).
- The lightbox starts the current slide's preview first:
  `utils/lightboxPreviewOrder.ts` (installed by `usePhotoSwipe.ts`) cancels
  PhotoSwipe's `contentLoadImage` for every non-current slide until the current
  slide's image has loaded or failed, then re-issues them. Navigating to a held
  slide loads it immediately; neighbours that finished loading make navigation
  instant. `preload: [1, 1]` is unchanged.

## Fragile Contracts

- Keep `useDevice.ts`, `_breakpoints.scss`, and `useColumnResize.ts` synchronized when changing breakpoints.
- Keep desktop lightbox `DESKTOP_METADATA_WIDTH`, `--lightbox-sidebar-width`, PhotoSwipe `paddingFn`, counter positioning, and next-arrow offset synchronized.
- Keep mobile sheet drag/snap/scroll delegated to VSBS; do not restore the old custom pointer-drag sheet implementation.
- Keep mobile outside-tap close non-blocking: no `stopPropagation()`, track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the movement threshold, and handle `pointercancel`.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep Query as the owner of server/API data and Pinia as the owner of UI/navigation state.
- Keep shadcn-vue Select controls as the metadata toolbar contract for model, prompt, and sort filters. `toolbarTrigger.ts` is a shared dropdown/button trigger class, but `SortSelect.vue` uses the local `SelectTrigger` styling directly.
