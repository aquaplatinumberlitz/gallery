# Metadata Lifecycle D·Full Clean Refactor Plan

Status: Proposed (plan only — not implemented yet)
Last reviewed: 2026-06-25
Target architecture: **D full clean** — `metadata_index_jobs` is the durable runtime queue; the metadata worker claims jobs directly from SQLite.
Local reference: `backend/derivative_scheduler.py` (`DerivativeScheduler`)
Scope: `backend/indexer.py`, `backend/scan_worker.py`, `backend/metadata_store/metadata_queue.py`, and related store modules

## 0. Implementation clarifications before Phase 0

Six clarifications are adopted before implementation begins. They define the
target architecture and remove ambiguity that caused the original bug family.

1. **Target architecture: D full clean.**
   This plan is no longer just D full bounded. The final architecture
   eliminates the in-memory queue as the source of metadata work.
   `metadata_index_jobs` becomes the durable runtime queue. The metadata
   worker claims queued jobs directly from SQLite — the same pattern
   `DerivativeScheduler` uses for `derivative_jobs`
   (`backend/derivative_scheduler.py:392-420`).

2. **Runtime owner boundary.**
   `recover_metadata_index_jobs()` and the metadata worker lifecycle live in
   `indexer.py` (or a new `metadata_lifecycle.py` if `indexer.py` grows too
   large). The store layer (`metadata_queue.py`) remains DB-only: it provides
   `claim_next_metadata_job()`, `complete_metadata_job()`, `fail_metadata_job()`,
   `mark_metadata_job_stale()`, and `list_recoverable_metadata_jobs()` but
   never imports the runtime layer.

3. **Completion terminal states.**
   `complete_metadata_job()` marks a job `'done'` **only** when the asset row
   matches and `assets.metadata_state` is materialised to `'done'` in the same
   transaction. If no library owns the path or the path is excluded, the job is
   marked `'skipped'`. If `(mtime, size)` differs from the current asset, the
   job is marked `'stale'`.

4. **Stale guard identity.**
   Job identity is `path + mtime_ns + size`. `library_id` is a secondary
   diagnostic field (backfilled from the assets row at queue time), not a
   required key component. Since `assets` uses `UNIQUE(library_id, path)` but
   `metadata_index_jobs` is keyed by `path TEXT PK`, the completion guard
   matches on `(path, mtime_ns, size)` and then checks `library_id` for
   diagnostic logging when a cross-library mismatch is found.

5. **In-memory queue bridge is transitional.**
   The existing `_job_queue` / `_queued_keys` / `_enqueue_metadata_jobs_from_result`
   (`indexer.py:51-69,397-423`) may remain during Phases 1–4 as a transitional
   compatibility bridge. Phase 5 removes or isolates it once the DB-claim
   worker is authoritative. The plan states clearly: **the in-memory queue must
   not be the source of metadata work in the final D full clean design.**

6. **Path-centric metadata job model.**
   `metadata_index_jobs` is keyed by `path TEXT PRIMARY KEY` — one job per
   absolute path. `library_id` is an additive column for the stale guard, not
   part of the job key. Completion updates all `assets` rows matching
   `(path, mtime_ns, size)` regardless of library_id. This keeps the
   path-centric model consistent with the current schema (`path PK`) and
   avoids a table-rebuild migration. The `derivative_jobs` pattern (one job per
   `asset_id`, many jobs per path) is not replicated; the metadata lifecycle
   is path-scoped, not asset-scoped, because metadata extraction is per-path
   and the result is shared across libraries that import the same file.

## 1. Problem statement

The metadata indexing pipeline has a lifecycle bug family rooted in the absence
of a single owner for the metadata lifecycle. Five symptoms:

1. **A DB job can exist without runtime worker dispatch.**
   `execute_rebuild_job` (`backend/scan_worker.py:242-345`) calls
   `queue_metadata_index_paths(scoped_paths, root)` directly at
   `scan_worker.py:312`. This persists rows in `metadata_index_jobs` with
   `state='queued'` but does not push any job into the in-memory `_job_queue`
   (`backend/indexer.py:51`), does not call `_enqueue_metadata_jobs_from_result`
   (`indexer.py:397-423`), and does not call `_start_worker_if_needed()`
   (`indexer.py:232-244`). The scan path does all of those. The two catalog
   operations diverge in how they schedule metadata work.

2. **A metadata job can be `done` while the asset remains `pending`/`reset`.**
   The "metadata is already current" shortcut in `queue_metadata_index_paths`
   (`metadata_queue.py:114-116`) calls `_mark_current_metadata_done`
   (`metadata_queue.py:65-96`), which only writes `metadata_index_jobs.state`
   to `'done'`. After a rebuild that has reset `assets.metadata_state` to
   `'pending'`/`'reset'` (`rebuild_store.py:208-229`), the job is marked done
   while the asset row is still pending.

3. **`image_metadata` can exist while API/progress does not see the asset as
   indexed.** Library progress, status, and ready-asset counts depend on
   `assets.metadata_state='done'`:
   - `status_store.py:480-494` and `529-543` (ready/failed aggregates keyed on
     `a.metadata_state = 'done'`)
   - `status_store.py:585` and `:607` (ready-asset scope queries require
     `a.metadata_state = 'done'`)
   - `library_store.py:468` (inspector coverage filters by
     `metadata_state = 'done'`)

4. **The in-memory metadata queue can be lost after restart while durable
   SQLite jobs persist.** `_job_queue` and `_pending_path_queue`
   (`indexer.py:51,59`) are pure RAM. On restart, `app.py:98-104` runs
   `recover_stale_jobs()`, but `job_store.py:439-463` only recovers *catalog*
   jobs (`library_jobs` rows with `type IN ('scan','rebuild')`). Nothing
   re-enqueues `metadata_index_jobs.state IN ('queued','running')`. Queued
   metadata jobs stay stranded; running jobs are never re-claimed.

5. **Scan and rebuild diverge in how they schedule metadata work.** The scan
   path goes through the staging helper `stage_metadata_paths_from_scan` /
   `_flush_staged_paths_to_job_queue` (`indexer.py:426-598`); the rebuild path
   calls the DB-only `queue_metadata_index_paths` and stops. There is no single
   entrypoint.

**Root cause:** the current design uses an in-memory `_job_queue` as the
runtime source of work. The metadata worker pulls from RAM, not from SQLite. A
`metadata_index_jobs` row can exist in SQLite without a matching in-memory
entry, so the worker never processes it. This is the entire bug class.

**D full clean eliminates this bug class** by making the SQLite table the
runtime queue: the worker claims directly from `metadata_index_jobs`, exactly
as `DerivativeScheduler._claim_job()` claims from `derivative_jobs`
(`derivative_scheduler.py:392-420`).

## 2. Current lifecycle map

All file/line references are to the current revision.

### 2.1 Scan path (correct half of the pipeline)

```
POST /api/libraries/{id}/scan or scan-all
  -> scan_worker.queue_scan(...)                              [scan_worker.py:74-95]
  -> catalog worker -> execute_scan_job                       [scan_worker.py:170-239]
     for each online scan_path:
       result = rebuild_index_scope(scan_path)                [indexer.py:688-720]
         index_directory_tree(...)                            [writes file_index]
         reconcile_library_assets(...)                        [marks assets offline]
         queued_result = queue_metadata_index_paths(...)      [metadata_queue.py:99-181]
           - 'queued' rows persisted/coalesced in SQLite
           - 'metadata already current' shortcut calls _mark_current_metadata_done  <-- BUG 2
         metadata = _enqueue_metadata_jobs_from_result(...)   [indexer.py:397-423]
           - pushes result.enqueued into in-memory _job_queue  <-- RAM is source of work
           - coalesces by job.key against _queued_keys
           - _start_worker_if_needed()                        [indexer.py:232-244]
       counters aggregated
  -> _transition_job(succeeded)
```

### 2.2 Rebuild path (half of the pipeline)

```
POST /api/libraries/{id}/rebuild
  -> scan_worker.queue_rebuild(...)                            [scan_worker.py:98-118]
  -> catalog worker -> execute_rebuild_job                     [scan_worker.py:242-345]
     enumerate_to_rebuild_staging(...)                         [rebuild_store.py:31-...]
     activate_rebuild_staging(...)                             [rebuild_store.py:~180-330]
       - resets assets.metadata_state='pending'/'reset'  [rebuild_store.py:208-229]
     for each (root, scoped_paths):
       result = queue_metadata_index_paths(scoped_paths, root)  [scan_worker.py:312]  <-- BUG 1
         - persists metadata_index_jobs.state='queued'
         - 'already current' shortcut may _mark_current_metadata_done (marks job, not asset) <-- BUG 2
       # NO _enqueue_metadata_jobs_from_result, NO _start_worker_if_needed
       # Bug 1: DB job exists but in-memory queue is empty → worker never processes
  -> _transition_job(succeeded, counters)
```

### 2.3 On-demand / "already current" shortcut path

a. **`/api/metadata` on-demand parse** (`metadata_parse.py:37-44`) calls
   `upsert_extracted_metadata(extracted, mark_job_done=True)`
   (`metadata_persist.py:178-189`). Inside the same transaction:
   - `_upsert_extracted_metadata_conn` writes `image_metadata` AND upserts
     `assets.metadata_state='done'` via `_upsert_asset_conn`
     (`metadata_persist.py:48-145`, `_asset_store.py:44-88`).
   - then `_mark_current_metadata_done` marks the job done.
   This path keeps job + asset transitionally consistent. It is NOT buggy.

b. **`queue_metadata_index_paths` "already current" shortcut**
   (`metadata_queue.py:114-116`): when `image_metadata` already exists for the
   path and `(mtime, size)` matches, it calls `_mark_current_metadata_done`
   and counts the job as `skipped`. It does NOT upsert the asset. This is
   Bug 2.

### 2.4 Worker success path

```
_worker_loop -> _process_batch                                   [indexer.py:283-395]
  mark_metadata_jobs_running(jobs)                              [metadata_queue.py:184-204]
  for job: if not _is_job_current(job): stale_jobs.append(job)   [indexer.py:224-229]
  extract_metadata(Path(job.path))                              [indexer.py:346-354]
  upsert_metadata_batch(success.metadata)                       [indexer.py:356-364]
    -> writes image_metadata + assets.metadata_state='done'      [metadata_persist.py:48-145]
  mark_metadata_jobs_done(done_jobs)                            [indexer.py:365-368]
    -> writes metadata_index_jobs.state='done' only             [metadata_queue.py:207-225]
```

Two gaps:

1. **Two transactions, two writers, no shared invariant.** Asset state and job
   state are written in separate SQLite transactions. No shared completion
   transition asserts "metadata is current AND job is done AND asset is done".

2. **Asset transition silently no-ops.** `_upsert_asset_conn`
   (`_asset_store.py:33-42`) returns `0` and writes nothing when no library owns
   the path or it is exclusion-matched.

### 2.5 Asset progress / API path

Reads depending on `assets.metadata_state='done'`:

- `status_store.py:480-494`, `:529-543` — `ready_assets` aggregation
- `status_store.py:585`, `:607` — scope-level ready-asset queries
- `status_store.py:759` — derived `active_metadata_state` from job aggregates
- `library_store.py:468` — Library Inspector coverage counts

### 2.6 Startup / recovery path

```
app.startup()                                                   [app.py:98-104]
  recover_stale_jobs()                                          [job_store.py:439-463]
    SELECT id FROM library_jobs WHERE state='running' AND type IN ('scan','rebuild')
    -> update_job_state(job_id, 'failed', ...)  [catalog jobs only]
  if GALLERY_CATALOG_SERVICE_ENABLED:
    scan_worker.start()                                         [scan_worker.py:375-397]
    queue_startup_scans()
  scheduler.start()  [DerivativeScheduler — recovers its own running jobs]
  _start_refresh(); _start_watcher()
```

**NOT done at startup:**
- No recovery of `metadata_index_jobs.state IN ('queued','running')`.
- No repair of inconsistent `done`-job + current-metadata + pending-asset rows.
- `DerivativeScheduler.start()` (`derivative_scheduler.py:65-87`) does recover
  its own running jobs by resetting `derivative_jobs.state='running'` to
  `'queued'` and `asset_derivatives.status='running'` to `'queued'`. The
  metadata worker should follow the same pattern.

### 2.7 Where the lifecycle splits today

- **Scheduling** is split between `scan_worker.execute_rebuild_job`
  (DB-only) and `indexer.rebuild_index_scope` + staging (full flow).
- **Dispatch** is owned by `_enqueue_metadata_jobs_from_result`
  (`indexer.py:397`), which the rebuild path skips.
- **Worker start** is owned by `_start_worker_if_needed` (`indexer.py:232`).
- **Completion (job-side)** is in `metadata_queue.py`.
- **Completion (asset-side)** is a side effect of `metadata_persist._upsert_extracted_metadata_conn`.
- **Recovery** exists for catalog jobs only.

## 3. Immich lessons applicable to Gallery

From `docs/research/IMMICH_PIPELINE_AUDIT.md` (principles, *not*
infrastructure):

1. **DB-first lifecycle.** Immich creates an `asset` row before any background
   job runs. The `assets` row is the durable record; jobs derivative from it.
2. **Asset row as source of truth.** Timeline/count surfaces read `asset` rows,
   not job tables. Gallery analogue: `assets.metadata_state='done'` is the
   authoritative answer; API/progress already reads it.
3. **Background job completion materializes state into DB.** Metadata extraction
   updates `asset` + `asset_exif` in the DB. The DB writes are the completion
   event.
4. **UI/API read materialized DB-backed state.** Gallery already does this on
   the read side. The fix is on the write/completion side.
5. **Workers/queues have explicit lifecycle ownership.** One Python module
   owns scheduling + dispatch + worker start + completion + stale guards +
   restart recovery for metadata.
6. **Durable state recovers runtime work after restart.** Recovery re-reads DB
   state and re-queues work.

**What must NOT be copied from Immich:**
- Redis / Valkey, BullMQ, or any cross-process queue broker.
- PostgreSQL or its indexes/extensions.
- Distributed workers, microservices, or process splits.
- Immich's `asset_job_status`, `asset_file`, `smart_search`, mobile sync, etc.
- Any new runtime dependency.

## 4. Existing Gallery precedent: DerivativeScheduler

`backend/derivative_scheduler.py` is the concrete local reference
implementation for D full clean. It already solves the exact bug class the
metadata pipeline has: a durable SQLite job table that the worker claims from
directly, with no in-memory queue as source of work.

### 4.1 How DerivativeScheduler works

```
schedule_derivative(asset_id, kind, variant, priority)
  → BEGIN IMMEDIATE
  → INSERT/ON CONFLICT DO NOTHING into asset_derivatives (catalog row)
  → INSERT into derivative_jobs (state='queued') if no active job exists
  → UPDATE asset_derivatives.status='queued'
  → COMMIT
  → self._wake_event.set()  [wake worker, no in-memory queue]

_worker_loop
  → _claim_job()
    → BEGIN IMMEDIATE
    → SELECT derivative_jobs WHERE state='queued' ORDER BY priority, created_at LIMIT 1
    → UPDATE derivative_jobs SET state='running', attempts=attempts+1
    → UPDATE asset_derivatives SET status='running'
    → COMMIT  [short transaction]
  → _run_job(job)
    → generate_derivative(source)  [OUTSIDE any DB transaction]
    → BEGIN
    → UPDATE asset_derivatives SET status='ready', cache_path, byte_size
    → UPDATE derivative_jobs SET state='done', completed_at
    → COMMIT  [short transaction]
  → _handle_failure on exception
    → UPDATE derivative_jobs SET state='queued' (retry) or 'failed'
    → UPDATE asset_derivatives SET status accordingly

start()
  → UPDATE derivative_jobs SET state='queued' WHERE state='running'  [recovery]
  → UPDATE asset_derivatives SET status='queued' WHERE status='running'
  → spawn worker threads
  → wake
```

### 4.2 Explicit comparison

| DerivativeScheduler | Metadata lifecycle (proposed) |
| --- | --- |
| `derivative_jobs` table (id, derivative_id, priority, state, attempts, created_at, started_at, completed_at) | `metadata_index_jobs` table (path PK, mtime, size, state, attempts, queued_at, started_at, finished_at) — needs `library_id`, `priority` |
| `asset_derivatives` catalog row (asset_id, kind, variant, source_mtime_ns, source_size, status) | `image_metadata` row (path, mtime, size, metadata_json) + `assets.metadata_state` |
| `asset_derivatives.status` ∈ queued/running/ready/failed | `assets.metadata_state` ∈ pending/running/done/failed/skipped |
| `source_mtime_ns` + `source_size` for stale detection | `metadata_index_jobs.mtime` + `metadata_index_jobs.size` for stale detection |
| `_claim_job()` — BEGIN IMMEDIATE, SELECT queued, UPDATE running, COMMIT | Proposed `claim_next_metadata_job()` — same pattern |
| `_run_job()` — generate derivative outside DB tx, then complete in short tx | Proposed metadata worker — extract metadata outside DB tx, then complete in short tx |
| `start()` — recover running → queued | Proposed `recover_metadata_index_jobs()` — same pattern |
| `_wake_event.set()` to wake worker after scheduling | Same pattern; no in-memory queue |
| `DerivativeScheduler` class owns the full lifecycle | Proposed `MetadataLifecycleWorker` / `metadata_lifecycle.py` owns the full lifecycle |

### 4.3 Key differences from DerivativeScheduler

- `metadata_index_jobs` currently uses `path TEXT PRIMARY KEY` (one row per
  path). `derivative_jobs` uses `id INTEGER PRIMARY KEY AUTOINCREMENT` (one row
  per job, many jobs per derivative). The plan keeps `path TEXT PK` for
  Phase 1–5; the claim query uses `(state, priority, queued_at)` ordering
  without needing an auto-increment id. Phase 5 may optionally migrate to
  `id INTEGER PRIMARY KEY AUTOINCREMENT` if multi-version jobs are needed.
- `metadata_index_jobs` does not currently carry `priority`. `derivative_jobs`
  does. The plan adds a `priority` column for parity, allowing scan-time jobs
  to be higher priority than recovery-queue-all jobs.
- Metadata extraction is CPU-bound (PIL + JSON parsing), while derivative
  generation is also CPU-bound (PIL/sharp). Both must run outside long DB
  transactions. The pattern is identical.

## 5. Proposed D full clean architecture

### 5.1 Scheduling owner (durable DB queue + wake worker)

```python
def dispatch_metadata_index_paths(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    priority: int = 3,
    start_worker: bool = True,
) -> dict[str, int]:
    """Persist/coalesce metadata_index_jobs in SQLite, wake the DB-claim worker."""
```

Responsibilities:

1. **Stat/filter paths.** Reject non-image/excluded paths.
2. **Durable job creation/coalescing.** Delegate to the store-layer
   `_persist_metadata_index_jobs(paths, root_path, priority)` (renamed from
   `queue_metadata_index_paths`, privatized). The "already current" shortcut
   still calls `_mark_current_metadata_done` to mark the job done in SQLite.
3. **Wake/ensure metadata worker.** Call `wake_metadata_worker()` which sets a
   `_wake_event` and calls `start_metadata_worker()` if not already running.
   **No in-memory queue push.** The worker will claim from SQLite.
4. **Counters/result reporting.** Return `{queued, coalesced, skipped, failed}`.

**Critical invariant:** The scheduling owner does NOT push jobs into an
in-memory `_job_queue`. It only writes to SQLite and wakes the worker. The
worker claims from SQLite.

**Transitional bridge — mutual exclusion rule:**

The old in-memory worker and the new DB-claim worker must NOT both process
metadata jobs in the same process.

Rule:

```text
Phase 1:  DB-claim worker introduced but not authoritative.
          Old _worker_loop processes _job_queue as today.
Phase 2:  DB-claim worker becomes authoritative.
          Old _worker_loop is disabled (returns immediately or is replaced).
          No production path pushes real work into _job_queue after this phase.
          The old queue APIs (`_enqueue_metadata_jobs_from_result`, `_job_queue.put`)
          become no-op/compatibility stubs until their removal in Phase 5.
Phase 5:  Old _job_queue and _worker_loop code are removed entirely.
```

### 5.2 Metadata worker (claims directly from SQLite)

New module or class in `backend/indexer.py` (or `metadata_lifecycle.py`):

```python
class MetadataLifecycleWorker:
    """DB-claim metadata worker, modeled on DerivativeScheduler."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
    def wake(self) -> None: ...

    def _worker_loop(self) -> None: ...
    def _claim_job(self) -> MetadataIndexJob | None: ...
    def _run_job(self, job: MetadataIndexJob) -> None: ...
    def _complete_job(self, job: MetadataIndexJob, metadata: ExtractedMetadata) -> None: ...
    def _fail_job(self, job: MetadataIndexJob, error: str) -> None: ...
    def _mark_job_stale(self, job: MetadataIndexJob) -> None: ...
```

Worker loop pattern (mirrors `DerivativeScheduler._worker_loop`,
`derivative_scheduler.py:422-434`):

```text
1. claim one queued job from SQLite in a short BEGIN IMMEDIATE transaction
   (set state='running', attempts+1, started_at=now)
2. optionally set assets.metadata_state='running' or 'processing'
3. release DB transaction
4. extract metadata outside any DB transaction
5. upsert image_metadata + complete job + materialize assets.metadata_state='done'
   in a short completion transaction (§5.3)
6. on failure: retry or mark failed in a short transaction
7. repeat until no queued jobs remain, then wait on _wake_event
```

**Guarantee:** The worker never holds a long SQLite write transaction during
metadata extraction (step 4). This matches `DerivativeScheduler._run_job`
which calls `generate_derivative()` outside the DB and then completes in a
short transaction (`derivative_scheduler.py:451-476`).

### 5.3 Completion owner (single invariant)

```python
def complete_metadata_job(
    conn: sqlite3.Connection,
    job: MetadataIndexJob,
    *,
    metadata_is_current: bool = True,
) -> None:
    """Atomically: metadata current + metadata_index_jobs.done + assets.metadata_state='done'."""
```

Invariant enforced (single SQLite transaction):

```text
PRE: image_metadata row exists for job.path with matching (mtime, size)
      job identity must match the current asset row (path, mtime_ns, size) —
      see §5.4 stale guard (primary: job.mtime_ns vs a.mtime_ns; legacy
      fallback: job.mtime vs a.mtime_ns / 1e9)
POST:
  - metadata_index_jobs.state='done', finished_at, updated_at
  - assets.metadata_state='done' for the matching asset row
  - if no library/excluded: job.state='skipped', no asset transition, log WARNING
  - if (mtime,size) mismatch: job.state='stale', no asset transition
```

Routing rules:

| Existing helper | Current behavior | New behavior |
| --- | --- | --- |
| `_mark_current_metadata_done` (`metadata_queue.py:65`) | writes job only | Delegate to `complete_metadata_job` so asset is also materialized when the row matches |
| `mark_metadata_jobs_done` (`metadata_queue.py:207`) | writes job only | Replace with `complete_metadata_job` (per-job) in the worker success path |
| Worker success batch | `upsert_metadata_batch` + `mark_metadata_jobs_done` (two transactions) | `upsert_metadata_batch` then `complete_metadata_job` per job (each short transaction) |

**Side-effect note:** `_upsert_extracted_metadata_conn` continues to call
`_upsert_asset_conn(metadata_state="done")` during Phase 2–3 as a safety
double-write. Phase 5 removes this side-effect once the completion helper is
proven to always run via tests.

### 5.4 Stale / race guards

Identity guard rule:

> A job created for an old version of a file must not mark the current asset
> done if the file changed, was deleted, was replaced, or moved.

Minimum identity: `path + mtime_ns + size`. `library_id` is a secondary
diagnostic field, not a required key component. The `mtime_ns` comparison
uses `metadata_index_jobs.mtime_ns` (INTEGER ns) vs `assets.mtime_ns`
(REAL ns, `float(stat.st_mtime_ns)`) with a 1000 ns tolerance (REAL
precision at ~1.7e18); legacy rows lacking `job.mtime_ns` fall back to
`job.mtime` (float seconds) vs `assets.mtime_ns / 1e9` (see §5.4 step 3).

Implementation:

1. **Schema migration** (§6): add `metadata_index_jobs.library_id INTEGER`
   (nullable/backfilled) and `metadata_index_jobs.priority INTEGER DEFAULT 3`.
   This mirrors how `asset_derivatives` carries `asset_id`
   (`_schema.py:394`) and `derivative_jobs` carries `priority`
   (`_schema.py:418`).
2. **DB-side guard in `complete_metadata_job`**: before writing, compare
   `job.(path, mtime_ns, size)` against the current `assets.(path, mtime_ns, size)`.
   Legacy fallback: if `job.mtime_ns IS NULL`, use `job.mtime` (seconds)
   against `assets.mtime_ns / 1e9` with a 1 ms tolerance.
   If they differ, mark the job `'stale'` and skip the asset transition.
   `library_id` is cross-checked separately for diagnostic logging (WARNING
   if the job's path maps to a different library than expected).
3. **`mtime` vs `mtime_ns` normalisation:**
   - `metadata_index_jobs.mtime_ns INTEGER` — set at queue time from
     `stat.st_mtime_ns` (integer nanoseconds). Column exists via
     `_schema.py:44`.
   - `assets.mtime_ns REAL` — set at asset upsert time from
     `float(stat.st_mtime_ns)` (`_asset_store.py:74`). Same unit (nanoseconds)
     as the job's `mtime_ns`.
   - The primary guard comparison is between
     `metadata_index_jobs.mtime_ns` (INTEGER ns) and `assets.mtime_ns`
     (REAL ns, `float(stat.st_mtime_ns)`, `_asset_store.py:74`). Because
     `REAL` at epoch nanosecond scale (~1.7e18) loses integer precision,
     use a safe nanosecond tolerance: `abs(a.mtime_ns - j.mtime_ns) < 1000`
     (within 1 microsecond).
   - **Fallback for legacy rows** where `job.mtime_ns IS NULL` (rows created
     before the column existed): compare `job.mtime` (float seconds) with
     `assets.mtime_ns / 1_000_000_000.0` using a 1 ms tolerance
     (`abs(a.mtime_ns/1e9 - j.mtime) < 1e-3`).
3. **Filesystem guard**: preserved by the existing `_is_job_current` pre-check
   in `_process_batch` (`indexer.py:224-229`).
4. **Deleted / moved files**: if `Path(job.path).stat()` fails, mark the job
   `'stale'` and leave the asset untouched.
5. **Multiple asset rows for same path**: `assets` uses
   `UNIQUE(library_id, path)`; `metadata_index_jobs` uses `path TEXT PK`. If
   the same path exists under multiple libraries (misconfiguration), completion
   updates all matching asset rows and logs a WARNING, or explicitly skips.
6. **Future `asset_id` FK**: if `metadata_index_jobs.asset_id` is added later,
   the guard should switch to joining on `asset_id`.

### 5.5 Startup recovery (DB-native)

Recovery does NOT mean "re-dispatch DB jobs into memory queue." It means "make
SQLite job state claimable and consistent."

```python
def recover_metadata_index_jobs() -> dict[str, int]:
    """Recover interrupted metadata jobs from SQLite. Does not use in-memory queue."""
```

Recovery cases:

| Case | Detection | Action |
| --- | --- | --- |
| `state='running'` (interrupted by crash) | `SELECT WHERE state='running'` | Reset to `'queued'` (preserve `attempts`/`queued_at`), unless `attempts >= MAX_METADATA_JOB_ATTEMPTS` → `'failed'`. Mirror `DerivativeScheduler.start()` (`derivative_scheduler.py:71-79`). |
| `state='queued'` | `SELECT WHERE state='queued'` | Leave claimable. The DB-claim worker will pick them up on wake. No action needed. |
| `state='done'` + current `image_metadata` + `assets.metadata_state` pending/reset | JOIN query | Repair: `complete_metadata_job` stamps asset done. |
| `state='done'` + missing/stale `image_metadata` | JOIN query | Demote to `'queued'` and let the worker re-process. |
| `state='done'` + no asset row | JOIN query | Mark `'skipped'`. |
| Stale job `(mtime,size)` no longer matches `Path.stat()` | stat check | Mark `'stale'`. |
| Missing file | `Path.stat()` raises `OSError` | Mark `'stale'`. |
| Asset moved/rebuilt with new content | asset row has different `(mtime_ns,size)` | Mark `'stale'`; next scan/rebuild will re-queue. |

**Key point:** Queued jobs survive process restart because SQLite IS the
runtime queue. Recovery only needs to reset interrupted `running` jobs and
repair inconsistent `done` rows. It does not rebuild an in-memory
source-of-truth queue.

### 5.6 Production caller guard

No production flow should call a DB-only helper in a way that schedules only
half of the pipeline.

- Rename `queue_metadata_index_paths` → `_persist_metadata_index_jobs` and
  remove its public re-export from `backend/metadata_store/__init__.py:227`.
  Only `indexer.dispatch_metadata_index_paths` and tests may call it.
- `_mark_current_metadata_done` and `mark_metadata_jobs_done` route through
  `complete_metadata_job`; privatize or remove their public re-exports if no
  external caller remains.
- Add a static check script (`scripts/check_metadata_lifecycle_ownership.py`)
  to enforce: no production module outside the lifecycle owner imports the
  DB-only helpers.

### 5.7 Status / debug mismatch counters

The DB-claim design eliminates the "queued DB jobs not in runtime queue" bug
class. But diagnostics must still prove queue state, asset state, and metadata
rows are consistent.

Proposed metadata lifecycle diagnostics (exposed via
`get_metadata_lifecycle_status(scope_path=None)`):

| Counter | Query | Purpose |
| --- | --- | --- |
| `queued_metadata_jobs` | `SELECT count(*) FROM metadata_index_jobs WHERE state='queued'` | Pending durable jobs |
| `running_metadata_jobs` | `SELECT count(*) FROM metadata_index_jobs WHERE state='running'` | In-flight jobs |
| `done_metadata_jobs` | `SELECT count(*) WHERE state='done'` | Completed jobs |
| `stale_metadata_jobs` | `SELECT count(*) WHERE state='stale'` | Stale jobs |
| `failed_metadata_jobs` | `SELECT count(*) WHERE state='failed'` | Failed jobs |
| `skipped_metadata_jobs` | `SELECT count(*) WHERE state='skipped'` | Skipped (no library) |
| `done_jobs_with_pending_assets` | JOIN `metadata_index_jobs` (done) + `assets` (metadata_state != done) | Inconsistency counter; should be 0 after repair |
| `current_image_metadata_with_pending_assets` | JOIN `image_metadata` (current) + `assets` (metadata_state != done) | Another inconsistency counter |
| `metadata_jobs_without_matching_assets` | LEFT JOIN `metadata_index_jobs` + `assets` WHERE asset IS NULL | Orphan jobs |
| `assets_done_but_metadata_missing_or_stale` | LEFT JOIN `assets` (done) + `image_metadata` (missing/stale) | Orphan assets |
| `repairable_metadata_assets` | Count of done-job + current-metadata + pending-asset rows | Work repair needs to do |
| `oldest_queued_metadata_job_age` | `min(queued_at)` from queued jobs | Queue freshness |
| `metadata_worker_alive` | `MetadataLifecycleWorker.is_running()` | Worker health |
| `metadata_worker_last_claimed_at` | `max(started_at)` from running/done jobs | Worker activity |
| `metadata_worker_last_completed_at` | `max(finished_at)` from done jobs | Worker throughput |

## 6. Migration / compatibility strategy

A small additive migration is required for D full clean. It mirrors
`derivative_jobs` / `asset_derivatives` schema.

### 6.1 Required migration

```sql
-- Add priority for queue ordering (mirrors derivative_jobs.priority)
ALTER TABLE metadata_index_jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 3;

-- Add library_id for stale guard identity (mirrors asset_derivatives.asset_id)
ALTER TABLE metadata_index_jobs ADD COLUMN library_id INTEGER;

-- Index for claim ordering and recovery queries
-- The claim query uses state + priority + queued_at; no auto-increment id is
-- needed because metadata_index_jobs uses path TEXT PRIMARY KEY.
CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_claim
  ON metadata_index_jobs(state, priority, queued_at);
CREATE INDEX IF NOT EXISTS idx_metadata_index_jobs_library_state
  ON metadata_index_jobs(library_id, state);
CREATE INDEX IF NOT EXISTS idx_assets_metadata_state
  ON assets(metadata_state);
```

### 6.2 Backfill

```sql
-- Backfill library_id from assets for existing rows
UPDATE metadata_index_jobs
SET library_id = (
  SELECT a.library_id FROM assets a
  WHERE a.path = metadata_index_jobs.path
  LIMIT 1
)
WHERE library_id IS NULL;
```

### 6.3 PK migration (optional, Phase 5)

The current `path TEXT PRIMARY KEY` means only one row per path. The Phase 1–5
claim query works correctly with `path PK` + `ORDER BY priority, queued_at`.
For full parity with `derivative_jobs` (one job per file version, multiple
versions for the same path), Phase 5 may optionally migrate to
`id INTEGER PRIMARY KEY AUTOINCREMENT` with `UNIQUE(library_id, path,
mtime_ns, size)`. This requires creating a new table and dropping the old one;
it is deferred to Phase 5 to avoid destructive DDL in the main refactor.

### 6.4 Safety

All additions are purely additive (`_ensure_column` / `CREATE INDEX IF NOT
EXISTS` already used in `_schema.py:32-36, 476-477`).

## 7. Broader integrity checker (P2 follow-up)

After D full clean is implemented, a broader integrity checker should cover
cross-system consistency. This is listed as a P2 follow-up, not implemented in
the first refactor.

Checks:

```text
metadata_index_jobs.done + image_metadata current + asset pending/reset
  → repair asset done  (covered by §5.5 recovery)

asset metadata_state='done' but image_metadata missing/stale
  → demote asset to pending, re-queue metadata job

metadata job queued/running for missing asset/file
  → mark job stale/failed

derivative job done but asset_derivatives.status != 'ready'
  → reconcile derivative status

asset_derivatives ready but derivative file missing on disk
  → re-queue derivative job

asset missing/offline but jobs still running (metadata or derivative)
  → fail/requeue the job

library/job/asset progress mismatch
  → report mismatch in status endpoint
```

This checker should be run as a scheduled background task (similar to
`refresh.py`) or triggered on demand. It is explicitly scoped as P2.

## 8. Test plan

Each test gives: name, target file, setup, action, expected assertions, and the
bug/invariant it protects. New tests must include the `Purpose / Guarantees /
Run when` docstring header per existing convention.

### P0 — Bug family regression

1. **Rebuild path persists metadata jobs and the DB-claim worker processes them
   without in-memory dispatch.**
   - Setup: seed a rebuild job; monkeypatch `MetadataLifecycleWorker.wake()`
     to record calls; drain `_job_queue` to empty.
   - Action: run `execute_rebuild_job`.
   - Assert: `metadata_index_jobs.state='queued'` rows exist; worker was
     woken; `_job_queue` was not used as the source of work.
   - Protects: Bug 1.

2. **Scan and rebuild share the same durable scheduling entrypoint.**
   - Setup: monkeypatch `dispatch_metadata_index_paths` to record calls.
   - Action: drive both `execute_scan_job` and `execute_rebuild_job`.
   - Assert: both invoke `dispatch_metadata_index_paths`; neither calls
     `_persist_metadata_index_jobs` directly.
   - Protects: single-owner invariant.

3. **Metadata worker claims queued jobs directly from SQLite.**
   - Setup: seed `metadata_index_jobs` rows with `state='queued'`; RAM
     `_job_queue` is empty.
   - Action: wake the metadata worker.
   - Assert: worker claims rows from SQLite, transitions `queued → running →
     done`; `_job_queue` remains empty.
   - Protects: D full clean invariant — SQLite is the runtime queue.

4. **Claimed jobs move `queued → running`.**
   - Setup: seed queued jobs.
   - Action: call `claim_next_metadata_job()`.
   - Assert: returned job has `state='running'`; no other worker can claim
     the same job (atomicity).
   - Protects: claim atomicity; `DerivativeScheduler._claim_job` pattern.

5. **Worker success moves `running → done` and materializes
   `assets.metadata_state='done'`.**
   - Setup: stage a job whose stat matches; provide `assets` row with
     `metadata_state='pending'`; monkeypatch `extract_metadata` with a toy
     extractor.
   - Action: run `_run_job(job)`.
   - Assert: `metadata_index_jobs.state='done'`,
     `assets.metadata_state='done'` in one completion transaction.
   - Protects: completion invariant (Bug 3 corrected).

6. **Current metadata shortcut also materializes `assets.metadata_state='done'`.**
   - Setup: `assets` row with `metadata_state='reset'`; `image_metadata` row
     with matching `(mtime, size)`.
   - Action: call `dispatch_metadata_index_paths([path], root)`.
   - Assert: `metadata_index_jobs.state='done'` AND
     `assets.metadata_state='done'`.
   - Protects: Bug 2.

7. **Progress/API indexed count increases after metadata completion.**
   - Setup: seed `assets` with `metadata_state='pending'` + matching
     `image_metadata` + `metadata_index_jobs` row `state='running'`.
   - Action: call `complete_metadata_job`, then query `status_store` readiness.
   - Assert: `ready_assets` increases by 1.
   - Protects: API/progress sees indexed assets after completion.

8. **Stale job with old `mtime`/`size` cannot mark a changed asset done.**
   - Setup: `assets` row with new `(mtime_ns, size)`; job with old `(mtime,
     size)`; `image_metadata` matching the asset's new values.
   - Action: call `complete_metadata_job([stale_job])`.
   - Assert: `metadata_index_jobs.state='stale'` (NOT `'done'`),
     `assets.metadata_state` unchanged.
   - Protects: stale/race guard.

9. **Startup recovery converts interrupted `running` jobs to queued/stale/failed
   according to identity.**
   - Setup: seed `metadata_index_jobs` with `state='running'`; RAM queue empty.
   - Action: call `recover_metadata_index_jobs()`.
   - Assert: `running` rows reset to `'queued'` (unless exhausted → `'failed'`);
     worker is started; no in-memory queue rebuilt.
   - Protects: §5.5 recovery.

10. **Queued jobs survive process restart because SQLite is the runtime queue.**
    - Setup: seed `metadata_index_jobs` with `state='queued'`; simulate restart
      by draining RAM queue and calling `recover_metadata_index_jobs()`.
    - Action: wake the worker.
    - Assert: worker claims and processes the queued rows from SQLite.
    - Protects: D full clean — SQLite is the durable runtime queue.

11. **Done job + current image metadata + pending/reset asset is repaired.**
    - Setup: seed the inconsistent triple.
    - Action: run `recover_metadata_index_jobs()`.
    - Assert: `assets.metadata_state='done'`; job stays `'done'`.
    - Protects: §5.5 repair.

12. **No production caller uses DB-only metadata queue helper directly.**
    - Setup: static check script.
    - Action: scan `backend/` excluding `tests/`.
    - Assert: only the lifecycle owner imports `_persist_metadata_index_jobs`
      and `complete_metadata_job`; no production caller bypasses the owners.
    - Protects: prevents regression.

13. **Old in-memory metadata queue bridge is not used as final source of work.**
    - Setup: seed jobs in SQLite; ensure `_job_queue` is empty.
    - Action: wake the DB-claim worker.
    - Assert: worker processes all SQLite jobs; `_job_queue` stays empty.
    - Protects: D full clean.

14. **Double scheduling is idempotent and does not create duplicate work.**
    - Setup: call `dispatch_metadata_index_paths` for the same path 3 times.
    - Assert: exactly one durable job row; counters report `coalesced >= 2`.
    - Protects: idempotency.

15. **Worker does not hold long write transactions during extraction.**
    - Setup: monkeypatch `extract_metadata` to record whether a DB write
      transaction is open during the call.
    - Action: run `_run_job`.
    - Assert: no write transaction is held during `extract_metadata`; the
      claim and complete transactions are short.
    - Protects: SQLite concurrency / WAL performance.

## 9. Implementation phases

Phases are intentionally small and reviewable. Phase 0 must precede Phase 1.

### Phase 0A — Characterization tests (existing API, reproduce real bugs)

Add tests that reproduce the lifecycle gaps *before* changing production code.
These tests use only the existing public API and store primitives; they do not
reference `MetadataLifecycleWorker` or other symbols that do not yet exist.

Files:

- `backend/tests/test_metadata_store_coverage.py` — add Tests 6, 8 (shortcut
  state gap, stale guard) as initially failing.
- `backend/tests/test_catalog_status_ready_assets.py` — add Test 7 (progress
  after completion).
- `backend/tests/test_indexer_staging.py` — add Tests 2, 14 (shared
  entrypoint, idempotency) as initially failing.
- `backend/tests/test_scan_worker.py` — new file, add Test 1 (rebuild
  persist-only bug) as initially failing.
- `docs/testing/TEST_CATALOG.md` — append new test rows.

### Phase 0B — Contract tests for DB-claim worker

Add tests for the DB-claim worker primitives AFTER the schema migration and
store-layer stubs exist. These tests reference `claim_next_metadata_job`,
`MetadataLifecycleWorker`, and other Phase 1 symbols. They fail until Phase 1
provides the implementation.

Files:

- `backend/tests/test_metadata_lifecycle.py` (new) — Tests 3, 9, 10, 13, 15
  (DB-claim, recovery, restart, no bridge, no long tx).

### Phase 1 — Introduce DB-claim metadata worker

Add SQLite claim/recover/complete/fail/stale primitives for
`metadata_index_jobs`, modeled on `DerivativeScheduler`.

Files:

- `backend/metadata_store/metadata_queue.py` — add
  `claim_next_metadata_job()`, `complete_metadata_job(conn, job)`,
  `fail_metadata_job(conn, job, error)`, `mark_metadata_job_stale(conn, job)`,
  `list_recoverable_metadata_jobs(conn, states)`,
  `reset_running_jobs_to_queued(conn, job_ids)`.
- `backend/metadata_store/_schema.py` — additive migration:
  `metadata_index_jobs.library_id`, `priority`, `id`; indexes
  `idx_metadata_index_jobs_claim`, `idx_metadata_index_jobs_library_state`,
  `idx_assets_metadata_state`.
- `backend/metadata_store/__init__.py` — export new primitives.
- `backend/indexer.py` — add `MetadataLifecycleWorker` class with
  `_worker_loop`, `_claim_job`, `_run_job`, `_complete_job`, `_fail_job`,
  `_mark_job_stale`, `start`, `stop`, `wake`, `is_running`.
- `backend/app.py` — instantiate and start the worker on startup.
- Tests: flip Tests 3, 4, 15 to passing.

### Phase 2 — Convert scheduling to durable DB queue + wake worker

Change scan/rebuild/manual/startup scheduling so they persist/coalesce jobs
and wake the DB-claim worker. Do not use in-memory queue as source of work.

Files:

- `backend/indexer.py` — add `dispatch_metadata_index_paths(...)` which
  persists via `_persist_metadata_index_jobs` and wakes the worker.
  No real work is pushed into `_job_queue`; the old queue APIs are
  disabled or replaced with no-op stubs.
- `backend/scan_worker.py` — in `execute_rebuild_job` (`:311-315`), replace
  `queue_metadata_index_paths` with `dispatch_metadata_index_paths`.
- `backend/indexer.py` — in `rebuild_index_scope` (`:688-720`) and
  `_flush_staged_paths_to_job_queue` (`:564-598`), route through
  `dispatch_metadata_index_paths`.
- Tests: flip Tests 1, 2, 14 to passing.

### Phase 3 — Completion invariant and stale guards

Unify current-metadata shortcut and worker success through one completion
owner. Materialize `assets.metadata_state='done'`. Guard by `library_id` +
normalised path + `mtime` + `size`.

Files:

- `backend/metadata_store/metadata_queue.py` — implement full
  `complete_metadata_job` with stale guard, mismatch → `'stale'`,
  no-library → `'skipped'`, match → `'done'` + asset `'done'`.
- `backend/metadata_store/metadata_queue.py` — refactor
  `_mark_current_metadata_done` and `mark_metadata_jobs_done` to delegate to
  `complete_metadata_job`.
- `backend/indexer.py` — in `_run_job`, replace separate
  `upsert_metadata_batch` + `mark_metadata_jobs_done` with
  `upsert_metadata_batch` + `complete_metadata_job`.
- `backend/metadata_store/metadata_persist.py` — route on-demand
  `upsert_extracted_metadata(mark_job_done=True)` through
  `complete_metadata_job`.
- Tests: flip Tests 5, 6, 7, 8 to passing.

### Phase 4 — Startup recovery and repair

Recover interrupted/running jobs, leave queued jobs claimable from DB, repair
done-job/current-metadata/pending-asset mismatch, demote/requeue/stale invalid
jobs.

Files:

- `backend/metadata_store/metadata_queue.py` — add
  `repair_inconsistent_asset_states(conn, scope_path)` store helper.
- `backend/indexer.py` — add `recover_metadata_index_jobs()` which calls
  store helpers (`reset_running_jobs_to_queued`, `repair_inconsistent_asset_states`),
  then wakes the worker. Does not rebuild in-memory queue.
- `backend/app.py` — call `recover_metadata_index_jobs()` in
  `_startup_background_services` after `recover_stale_jobs()`.
- Tests: flip Tests 9, 10, 11 to passing; add "durable done was lying" demote
  companion test.

### Phase 5 — Remove/deprecate old in-memory metadata queue bridge

Remove or isolate `_enqueue_metadata_jobs_from_result`, `_job_queue`,
`_queued_keys`, `_pending_path_queue`, `_path_stager_*`, and any old
memory-queue-based scheduling once DB-claim worker is authoritative.

Files:

- `backend/indexer.py` — remove `_job_queue`, `_queued_keys`,
  `_enqueue_metadata_jobs_from_result`, `_pending_path_queue`,
  `_path_stager_thread`, `_start_worker_if_needed` (replaced by
  `MetadataLifecycleWorker.start/wake`). Keep `stage_metadata_paths_from_scan`
  only if it still serves the `/api/scan` hot-path RAM staging before DB
  persist; otherwise remove.
- `backend/metadata_store/metadata_queue.py` — rename
  `queue_metadata_index_paths` → `_persist_metadata_index_jobs`; remove public
  re-export from `__init__.py`. Privatize `_mark_current_metadata_done` and
  `mark_metadata_jobs_done`.
- `backend/metadata_store/metadata_persist.py` — remove
  `metadata_state="done"` side-effect from `_upsert_extracted_metadata_conn`
  now that `complete_metadata_job` is proven to always run.
  **Guard:** the on-demand `/api/metadata` path (`metadata_parse.py:37-44`)
  routes through `complete_metadata_job` (Phase 3). Only remove the side-effect
  if explicit tests (`test_metadata_parse_coverage.py`) confirm that on-demand
  parsing still materialises `assets.metadata_state='done'` correctly. If not,
  keep the side-effect and document it as the compatibility path.
- `backend/tests/test_indexer_staging.py` — retarget existing monkeypatches to
  the new owner boundaries; remove mocks that test the old in-memory queue.
- `scripts/check_metadata_lifecycle_ownership.py` (new) — static check for
  Test 12.
- Tests: flip Tests 12, 13 to passing.

### Phase 6 — Status/debug diagnostics and docs

Add mismatch counters and update architecture/testing docs.

Files:

- `backend/indexer.py` — add `get_metadata_lifecycle_status(scope_path)` with
  the counters from §5.7.
- `backend/metadata_store/status_store.py` — wire metadata lifecycle
  diagnostics into the existing status envelope where appropriate.
- `docs/ARCHITECTURE.md` — describe the new metadata lifecycle owner, the
  DB-claim worker, the invariants, and the `DerivativeScheduler` precedent.
- `docs/testing/TEST_CATALOG.md` — finalize new test rows.

### Phase 7 — Broader integrity checker (P2 follow-up)

Plan broader asset/job/metadata/derivative consistency checks per §7.

Files:

- `backend/integrity_checker.py` (new, P2) — scheduled background task that
  runs the checks from §7.
- `backend/config.py` — `INTEGRITY_CHECK_ENABLED`, `INTEGRITY_CHECK_INTERVAL`.
- `docs/plans/` — new follow-up plan for the integrity checker.

## 10. Risk assessment

| Risk | Mitigation |
| --- | --- |
| **Double enqueue** | `metadata_index_jobs.path PK` prevents duplicate rows for the same path. `dispatch_metadata_index_paths` coalesces both in SQLite (ON CONFLICT path) and in `_queued_keys`. Test 14. |
| **Starting multiple worker threads** | `MetadataLifecycleWorker.start()` guarded by `_lifecycle_lock` + `is_alive()` check, same as `DerivativeScheduler.start()` (`derivative_scheduler.py:65-87`). |
| **Long SQLite transactions** | Claim and complete are short `BEGIN IMMEDIATE` transactions. Extraction runs outside any DB transaction, same as `DerivativeScheduler._run_job` (`derivative_scheduler.py:451-476`). Test 15. |
| **Scan/rebuild concurrency** | Catalog service serializes via `claim_next_catalog_job`. Metadata worker claims independently from SQLite with `BEGIN IMMEDIATE`, same as derivative worker. No new cross-catalog locking. |
| **Old job marking a new asset done** | §5.4 DB-side guard: `job.(library_id, path, mtime, size)` must match `assets` row. Test 8. |
| **Repair marking the wrong asset done** | Repair requires `image_metadata` row's `(mtime, size)` to match the job; otherwise demote/requeue. Never bulk-updates `metadata_state='done'`. |
| **Current tests mocking too low-level** | Phase 5 privatizes/renames DB-only helpers and retargets existing tests to owner boundaries. Test 12. |
| **Performance regression for large libraries** | `idx_metadata_index_jobs_claim` index covers the claim query. No full table scans. Worker claims one row at a time, same as derivative worker. |
| **Startup recovery doing too much work** | Recovery only resets `running → queued` (one UPDATE) and repairs `done` mismatches (bounded by row count). Queued jobs need no recovery — they are claimable from SQLite. |
| **Behavior changes for existing partially indexed DBs** | Repair pass is read-then-reconcile, never destructive. Legacy DBs get their stranded `queued` jobs processed by the new DB-claim worker for the first time — this is the intended behavior change. |
| **Transitional bridge double-process** | Mutual-exclusion rule in §5.1: Phase 1 old worker runs alone; Phase 2+ DB-claim worker is authoritative and old worker disabled. After Phase 2, no production path pushes real work into `_job_queue`; old queue APIs are no-op/compat stubs until Phase 5 removal. |
| **PK migration (path → id)** | Deferred to Phase 5 if needed. The Phase 1–5 claim query uses `(state, priority, queued_at)` ordering on the existing `path PK` — no auto-increment id required. |

## 11. Acceptance criteria

- [ ] This plan targets **D full clean**: `metadata_index_jobs` is the durable
  runtime queue; the metadata worker claims jobs directly from SQLite.
- [ ] The in-memory queue bridge is transitional: Phase 1 old worker runs
  alone; Phase 2+ DB-claim worker authoritative, old worker disabled; removed
  in Phase 5.
- [ ] `DerivativeScheduler` is the local reference implementation; the metadata
  worker follows the same claim/complete/recover pattern.
- [ ] Scan and rebuild use the same scheduling entrypoint
  (`dispatch_metadata_index_paths`).
- [ ] No production caller schedules DB-only metadata jobs without waking the
  DB-claim worker.
- [ ] Metadata job completion always materializes `assets.metadata_state='done'`
  when metadata is current and an asset row exists, via one owned completion
  transition (`complete_metadata_job`).
- [ ] Stale jobs (old `mtime`/`size`, missing file, replaced asset) cannot
  mark a changed asset done.
- [ ] `queued`/`running` metadata jobs do not get stuck after restart; the
  worker claims them from SQLite.
- [ ] Inconsistent `done`-job + current-metadata + pending-asset states are
  repaired during DB-native recovery.
- [ ] API/progress sees indexed assets after metadata completion.
- [ ] Status/debug mismatch counters are planned and implemented in Phase 6.
- [ ] Broader integrity checker is explicitly listed as P2 follow-up (Phase 7).
- [ ] Regression tests cover the known bug family and the DB-claim invariants
  (Tests 1–15).
- [ ] All existing backend tests still pass (Phase 5 retargets mocks, does not
  delete them).
- [ ] Frontend tests are unaffected; `./test.sh e2e` remains green.
- [ ] `docs/ARCHITECTURE.md` explains the new metadata lifecycle owner, the
  DB-claim worker, the invariants, and the `DerivativeScheduler` precedent.
- [ ] No new runtime dependency added; refactor stays on local SQLite +
  in-process workers and does not introduce Redis/BullMQ/PostgreSQL or any
  cross-process architecture.