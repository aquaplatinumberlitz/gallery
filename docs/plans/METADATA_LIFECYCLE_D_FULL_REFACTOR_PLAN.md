# Metadata Lifecycle D·Full Refactor Plan

Status: Proposed (plan only — not implemented yet)
Last reviewed: 2026-06-25
Scope: `backend/indexer.py`, `backend/scan_worker.py`, `backend/metadata_store/metadata_queue.py`, and related store modules

## 0. Implementation clarifications before Phase 0

Based on the external audit of this plan (2026-06-25), four clarifications
are adopted before implementation begins. They do not change the D·full
direction; they remove ambiguity that could cause circular imports, semantic
drift, or scoping disputes during implementation.

1. **Runtime owner boundary.**
   `recover_metadata_index_jobs()` lives in `indexer.py` (or a new
   `metadata_lifecycle.py` if `indexer.py` grows too large), not in
   `metadata_queue.py`. The store layer (`metadata_queue.py`) remains DB-only:
   it provides `list_recoverable_metadata_jobs()`, `reset_running_jobs_to_queued()`,
   and `complete_metadata_jobs_conn()` but never imports the runtime layer.
   All sections below have been updated to reflect this enforcement.

2. **Completion terminal states.**
   `complete_metadata_jobs()` marks a job `'done'` **only** when the asset row
   matches and `assets.metadata_state` is materialised to `'done'` in the same
   transaction. If no library owns the path or the path is excluded, the job is
   marked `'skipped'` (a terminal no-op, clearly distinguishable from `'done'`).
   If `(mtime, size)` differs from the current asset, the job is marked
   `'stale'`. This prevents the "job done but asset pending" ambiguity that
   caused Bug 2 and Bug 3.

3. **Migration decision.**
   No schema migration is required for Phases 1–3. Existing columns
   (`metadata_index_jobs.path`, `mtime`, `size`, `state`, `root_path`;
   `assets.metadata_state`, `mtime_ns`, `size`, `library_id`) are sufficient.
   `metadata_index_jobs.library_id` and the
   `idx_assets_metadata_state` index are optional follow-ups deferred until
   large-library profiling proves they are needed.

4. **Asset-state side-effect strategy.**
   Phase 2 re-asserts `assets.metadata_state='done'` inside
   `complete_metadata_jobs()` even though `_upsert_extracted_metadata_conn`
   already sets it. This is a safety double-write — the canonical state
   transition moves to the completion helper. Phase 4 may trim the redundant
   side-effect from `_upsert_asset_conn` after the regression tests prove the
   completion helper is always called.

## 1. Summary of corrections to the task prompt

The task brief assumes three bugs verbatim. After reading the code, two are
confirmed exactly as described, and one (Bug 3) is partially inaccurate. The
plan proceeds against the corrected understanding so that the refactor targets
the real invariant gap and not a phantom bug.

| Prompt claim | Code reality | Correction in this plan |
| --- | --- | --- |
| Bug 1: `execute_rebuild_job` calls `queue_metadata_index_paths(...)` directly and never dispatches runtime metadata work nor starts the worker. | Confirmed. `backend/scan_worker.py:312-314` calls `queue_metadata_index_paths(scoped_paths, root)` and only sums `result.enqueued` / `result.failed` into counters. It never calls `_enqueue_metadata_jobs_from_result(...)` nor `_start_worker_if_needed()`. By contrast the scan path at `backend/scan_worker.py:203` delegates to `indexer.rebuild_index_scope(...)`, which at `backend/indexer.py:688-713` does call both. | No correction; treat as the primary scheduling-divergence bug. |
| Bug 2: `_mark_current_metadata_done(...)` marks `metadata_index_jobs.state='done'` but never `assets.metadata_state='done'`. | Confirmed. `backend/metadata_store/metadata_queue.py:65-96` only INSERTs/UPDATEs `metadata_index_jobs`. It is invoked from the "already current" shortcut inside `queue_metadata_index_paths` at `metadata_queue.py:114-116`. | No correction. |
| Bug 3: "the metadata worker can successfully extract metadata and write `image_metadata`, but the asset remains not materialized as metadata-done". | Partially wrong. `indexer._process_batch` calls `upsert_metadata_batch` (`backend/indexer.py:356-368`), which calls `_upsert_extracted_metadata_conn` (`backend/metadata_store/metadata_persist.py:48-145`), which calls `_upsert_asset_conn(..., metadata_state="done", ...)` (`_asset_store.py:44-88`). In the happy path (asset row exists, library resolves, no exclusion) the asset IS transitioned to `done`. `mark_metadata_jobs_done` itself (`metadata_queue.py:207-225`) still only writes `metadata_index_jobs` — so completion is *divergent/sequencing-coupled*, not absent. | The real Bug 3 is the divergence and lack of single-ownership: the job-state transition and the asset-state transition live in two separate helpers that run in two separate SQLite transactions, and the asset transition silently no-ops when `_upsert_asset_conn` returns 0 (no library match / excluded path). The plan therefore treats Bug 3 as "completion transition is not an owned invariant" rather than "worker never marks the asset done". |

## 1. Problem statement

The metadata indexing pipeline has a lifecycle bug family rooted in the absence
of a single owner for the metadata lifecycle. The symptoms described in the
prompt are reproduced (with the Bug 3 correction above) as follows:

1. **A DB job can exist without runtime worker dispatch.**
   `execute_rebuild_job` (`backend/scan_worker.py:242-345`) calls
   `queue_metadata_index_paths(scoped_paths, root)` directly at
   `scan_worker.py:312`. This persists/coalesces rows in
   `metadata_index_jobs` with `state='queued'` (`metadata_queue.py:99-181`)
   but does not push any job into the in-memory `_job_queue`
   (`backend/indexer.py:51`), does not call `_enqueue_metadata_jobs_from_result`
   (`indexer.py:397-423`), and does not call `_start_worker_if_needed()`
   (`indexer.py:232-244`). The scan path does all of those — through
   `rebuild_index_scope` (`indexer.py:688-720`) which is itself called from
   `execute_scan_job` (`scan_worker.py:203`). The two catalog operations
   therefore diverge in how they schedule metadata work.

2. **A metadata job can be `done` while the asset remains `pending`/`reset`.**
   The "metadata is already current" shortcut in `queue_metadata_index_paths`
   (`metadata_queue.py:114-116`) calls `_mark_current_metadata_done`
   (`metadata_queue.py:65-96`), which only writes `metadata_index_jobs.state`
   to `'done'`. After a rebuild that has reset
   `assets.metadata_state` to `'pending'`/`'reset'`
   (`backend/metadata_store/rebuild_store.py:208-229`), the job can be marked
   done while the asset row is still pending. This is Bug 2.

3. **`image_metadata` can exist while API/progress does not see the asset as
   indexed.** Library progress, status, and ready-asset counts depend on
   `assets.metadata_state='done'`, not on the presence of `image_metadata`
   rows. See:
   - `backend/metadata_store/status_store.py:480-494` and `529-543`
     (ready/failed aggregates keyed on `a.metadata_state = 'done'`)
   - `backend/metadata_store/status_store.py:585` and `:607` (ready-asset
     scope queries require `a.metadata_state = 'done'`)
   - `backend/metadata_store/library_store.py:468` (inspector coverage
     filters by `metadata_state = 'done'`)
   Whenever the job is `done` but the asset is `pending`/`reset`, these
   surfaces under-report indexed assets even though `image_metadata` exists.

4. **The in-memory metadata queue can be lost after restart while durable
   SQLite jobs persist.** `_job_queue` and `_pending_path_queue`
   (`indexer.py:51,59`) are pure RAM. On restart, `app.py:98-104` runs
   `recover_stale_jobs()`, but `backend/metadata_store/job_store.py:439-463`
   only recovers *catalog* jobs (`library_jobs` rows with
   `type IN ('scan','rebuild')`). Nothing re-enqueues
   `metadata_index_jobs.state IN ('queued','running')`. So:
   - `queued` metadata jobs created by a rebuild before a crash stay `queued`
     forever (Bug 1 + no recovery).
   - `running` metadata jobs orphaned by a crash are never failed or
     re-claimed; they will be silently bypassed.

5. **Scan and rebuild diverge in how they schedule metadata work.** Already
   shown above. The scan path goes through the staging helper
   `stage_metadata_paths_from_scan` / `_flush_staged_paths_to_job_queue`
   (`indexer.py:426-598`); the rebuild path calls the DB-only
   `queue_metadata_index_paths` and stops. There is no single entrypoint,
   which is exactly what "D full" is meant to fix.

The deeper cause is structural: scheduling, runtime dispatch, worker startup,
job completion, asset state transition, stale guards, and restart recovery are
spread across `scan_worker.py`, `indexer.py`, `metadata_queue.py`,
`metadata_persist.py`, and `rebuild_store.py` with no single lifecycle owner.

## 2. Current lifecycle map

All file/line references below are to the current revision. This is the
"current state" the refactor is grounded in.

### 2.1 Scan path (correct half of the pipeline)

```
POST /api/libraries/{id}/scan or scan-all
  -> libraries.queue_scan_job
  -> scan_worker.queue_scan(...)                              [backend/scan_worker.py:74-95]
     persist/coalesce library_jobs(scan) row, notify_workers
  -> catalog worker (_worker_loop)                            [backend/scan_worker.py:362-371]
  -> run_once -> claim_next_catalog_job                        [backend/scan_worker.py:347-359]
  -> execute_scan_job                                         [backend/scan_worker.py:170-239]
     for each online scan_path:
       result = rebuild_index_scope(scan_path)                [backend/indexer.py:688-720]
         index_directory_tree(...)                            [writes file_index, folder rows]
         reconcile_library_assets(...)                        [marks assets offline]
         queued_result = queue_metadata_index_paths(...)      [backend/metadata_store/metadata_queue.py:99-181]
           - 'queued' rows persisted/coalesced
           - 'metadata already current' shortcut calls _mark_current_metadata_done  <-- BUG 2 lives here
         metadata = _enqueue_metadata_jobs_from_result(queued_result, start_worker=True)  [indexer.py:397-423]
           - pushes result.enqueued into in-memory _job_queue
           - coalesces by job.key against _queued_keys
           - _start_worker_if_needed()                        [indexer.py:232-244]
       counters aggregated
  -> _transition_job(succeeded)
```

Note: scan does NOT use `stage_metadata_paths_from_scan` directly. The staging
flow (`indexer.py:426-598`) is used by the `/api/scan` hot path and by
`scan.py`'s route helper that feeds `enqueue_metadata_jobs_from_scan`
(`indexer.py:601-614`). Both staging and `rebuild_index_scope` route through
`_enqueue_metadata_jobs_from_result`, so scan-side flows are consistent.

### 2.2 Rebuild path (half of the pipeline)

```
POST /api/libraries/{id}/rebuild
  -> libraries.queue_rebuild_job
  -> scan_worker.queue_rebuild(...)                            [backend/scan_worker.py:98-118]
     persist/coalesce library_jobs(rebuild) row, notify_workers
  -> catalog worker -> run_once -> execute_rebuild_job         [backend/scan_worker.py:242-345]
     enumerate_to_rebuild_staging(...)                        [backend/metadata_store/rebuild_store.py:31-...]
       - writes catalog_rebuild_entries only
     activate_rebuild_staging(...)                             [rebuild_store.py:~180-330]
       - atomic merge into file_index/assets
       - resets assets.metadata_state='pending'/'reset'  [rebuild_store.py:208-229]  <-- creates Bug-2-prone state
     for each (root, scoped_paths):
       result = queue_metadata_index_paths(scoped_paths, root)  [backend/scan_worker.py:312]  <-- BUG 1
         - persists metadata_index_jobs.state='queued'
         - 'already current' shortcut may _mark_current_metadata_done (marks job, not asset) <-- BUG 2
       # NO _enqueue_metadata_jobs_from_result, NO _start_worker_if_needed
       enqueued_total += len(result.enqueued)
  -> _transition_job(succeeded, counters)
```

Consequences of Bug 1 in the rebuild path:
- `metadata_index_jobs.state='queued'` rows exist but nothing populates the
  in-memory `_job_queue`, so the metadata worker thread (if not already
  running from a previous scan) never picks them up.
- Even if the worker is already running, it pulls only from `_job_queue`, not
  from `metadata_index_jobs`. The queued rebuild jobs are stranded in SQLite.
- The library status surface (`/api/libraries/{id}/status`) reports them as
  `queued_assets`/running metadata forever, and `ready_assets` stays stuck
  below the real count.

### 2.3 On-demand / "already current" shortcut path

Two distinct "shortcut" flows exist; only one is buggy:

a. **`/api/metadata` on-demand parse** (`backend/metadata_parse.py:37-44`)
   calls `upsert_extracted_metadata(extracted, mark_job_done=True)`
   (`backend/metadata_store/metadata_persist.py:178-189`). Inside the same
   transaction:
   - `_upsert_extracted_metadata_conn` writes `image_metadata` AND upserts
     `assets.metadata_state='done'` via `_upsert_asset_conn`
     (`metadata_persist.py:48-145`, `_asset_store.py:44-88`).
   - then `_mark_current_metadata_done` marks the job done.
   This path keeps job + asset transitionally consistent. It is NOT buggy.

b. **`queue_metadata_index_paths` "already current" shortcut**
   (`metadata_queue.py:114-116`): when `image_metadata` already exists for
   the path and `(mtime, size)` matches, it calls
   `_mark_current_metadata_done` and counts the job as `skipped`. It does
   NOT upsert the asset. This is Bug 2. After a rebuild that reset
   `assets.metadata_state` to `'pending'`, this shortcut makes
   `metadata_index_jobs.state='done'` while `assets.metadata_state` is still
   `'pending'`. The status/progress surfaces then under-count.

### 2.4 Worker success path

```
_worker_loop -> _process_batch                                   [backend/indexer.py:283-395]
  mark_metadata_jobs_running(jobs)                              [metadata_queue.py:184-204]
  for job: if not _is_job_current(job): stale_jobs.append(job)   [indexer.py:224-229, 343-352]
  extract_metadata(Path(job.path))                              [indexer.py:346-354]
  if _is_job_current(job): successes.append((job, metadata))
  upsert_metadata_batch(success.metadata)                       [indexer.py:356-364]  -> writes image_metadata + assets.metadata_state='done'
  mark_metadata_jobs_done(done_jobs)                            [indexer.py:365-368]  -> writes metadata_index_jobs.state='done' only
  mark_metadata_jobs_stale(stale_jobs)                          [metadata_queue.py:228-246]
  mark_metadata_jobs_failed(failed_jobs)                        [metadata_queue.py:249-267]
```

Two real gaps here even though the happy-path asset transition does occur:

1. **Two transactions, two writers, no shared invariant.**
   `upsert_metadata_batch` and `mark_metadata_jobs_done` are independent
   SQLite transactions (`_run_sqlite_write` wrappers,
   `indexer.py:356-368`). If the process dies between the two commits, the
   asset is `'done'` but the job is still `'running'` — or, on the rerun path,
   the worker may re-extract. There is no shared completion transition that
   asserts "metadata is current AND job is done AND asset is done" atomically
   or even in one transaction.

2. **Asset transition silently no-ops.** `_upsert_asset_conn`
   (`_asset_store.py:33-42`) returns `0` and writes nothing when
   `_find_library_for_path_conn` returns `None` (no library owns the path)
   or the path is exclusion-matched. In those cases `image_metadata` is
   written and the job is later marked done, but `assets` is unchanged. The
   status surfaces then treat the asset as not-yet-indexed. This is the
   genuine, narrow form of Bug 3.

### 2.5 Asset progress / API path

Reads that depend on `assets.metadata_state='done'`:

- `status_store.py:480-494` and `:529-543` — `ready_assets` is computed as
  `sum(CASE WHEN a.metadata_state='done' AND im.path IS NOT NULL THEN 1 ...)`.
  `not_ready_assets`, `queued_assets`, `running_assets`, `failed_assets`
  all derive from `a.metadata_state != 'done'`.
- `status_store.py:585`, `:607` — scope-level ready-asset queries require
  `a.metadata_state='done'`.
- `status_store.py:759` — derived `active_metadata_state` is built from the
  `metadata_index_jobs` aggregates (independent of asset), so it can show
  `'running'`/`'queued'`/`None` while assets stay pending — i.e., the two
  surfaces can disagree.
- `library_store.py:468` — Library Inspector coverage counts only
  `type='image' AND _active_asset_where AND metadata_state='done'`.
- `backend/metadata_store/types.py` and `backend/models.py:21` expose
  `metadata_state` to API DTOs (`FileNode.metadata_state`,
  `browse_store.py:233,303,317,...`).

### 2.6 Startup / recovery path

```
app.startup()                                                   [backend/app.py:98-104]
  recover_stale_jobs()                                          [job_store.py:439-463]
    SELECT id FROM library_jobs WHERE state='running' AND type IN ('scan','rebuild')
    -> update_job_state(job_id, 'failed', ...)  [catalog jobs only]
  if GALLERY_CATALOG_SERVICE_ENABLED:
    scan_worker.start()
      recover_stale_jobs() again inside start()                  [scan_worker.py:375-397]
      spawn GALLERY_CATALOG_WORKERS catalog workers
    if GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED:
      queue_startup_scans()
  scheduler.start(); _start_refresh(); _start_watcher()
```

What is **NOT** done at startup:

- No call to `_start_worker_if_needed()` for the metadata worker unless
  catalog work later calls `_enqueue_metadata_jobs_from_result`.
- No query over `metadata_index_jobs.state IN ('queued','running')`. So
  stranded `queued` rebuild jobs are never re-enqueued to RAM, and orphaned
  `running` metadata jobs are never failed or retried.
- No repair of inconsistent rows (`metadata_index_jobs.state='done'` +
  current `image_metadata` + `assets.metadata_state` still `pending`/`reset`).
  Such DBs (which any user who triggered a rebuild before this fix ships
  will have) remain silently wrong.

### 2.7 Where the lifecycle splits today

- **Scheduling** is split between `scan_worker.execute_rebuild_job`
  (`queue_metadata_index_paths` only) and `indexer.rebuild_index_scope` +
  `_flush_staged_paths_to_job_queue` (full flow).
- **Dispatch** is owned only by `_enqueue_metadata_jobs_from_result`
  (`indexer.py:397`), which the rebuild path skips.
- **Worker start** is owned by `_start_worker_if_needed`
  (`indexer.py:232`), driven only by the dispatch path.
- **Completion (job-side)** is in `metadata_queue.py`:
  `_mark_current_metadata_done`, `mark_metadata_jobs_done`,
  `mark_metadata_jobs_stale`, `mark_metadata_jobs_failed`.
- **Completion (asset-side)** is a side effect of `metadata_persist._upsert_extracted_metadata_conn`
  → `_upsert_asset_conn`, *plus* the on-demand
  `upsert_metadata_result` → `_upsert_asset_conn` path. None of these are
  invoked by `_mark_current_metadata_done` or `mark_metadata_jobs_done`.
- **Stale/race guard** exists only inside `_process_batch` via
  `_is_job_current` (`indexer.py:224-229`) which compares `Path(path).stat()`
  against `job.mtime`/`job.size`. No guard at completion time and no guard for
  moved/deleted/replaced files when an old job row re-runs after restart.
- **Recovery** exists for catalog jobs only (`recover_stale_jobs`).

## 3. Immich lessons applicable to Gallery

From `docs/research/IMMICH_PIPELINE_AUDIT.md` (principles, *not*
infrastructure):

1. **DB-first lifecycle.** Immich creates an `asset` row before any
   background job runs (`IMMICH_PIPELINE_AUDIT.md` §1, §2). The row is the
   durable record of the asset's existence; jobs derivative from the row.
   Gallery analogue: the `assets` row is the source of truth for "the asset
   exists"; `metadata_index_jobs` should be a *transient* representation of
   pending metadata work, and its `done` state is meaningful only when
   reconciled against `assets.metadata_state`.

2. **Asset row as source of truth.** In Immich the timeline/count surfaces
   read `asset` + `asset_exif` rows, not job tables; job status rows
   (`asset_job_status`) record *timestamps* of completion, not the
   authoritative "is this asset indexed?" answer (§5, §13, §15). Gallery
   analogue: `assets.metadata_state='done'` is the authoritative answer, and
   API/progress already reads it (`status_store.py`, `library_store.py`).
   Therefore completion transitions must materialize into `assets`, not just
   `metadata_index_jobs`.

3. **Background job completion materializes state into DB.** Immich
   `MetadataService.handleMetadataExtraction` updates `asset` and upserts
   `asset_exif` and sets `metadataExtractedAt` (§2). The DB writes are the
   completion event, not a side note. Gallery analogue: the worker's
   `upsert_metadata_batch` already does this, but the *complete* transition
   (job done + asset done) is split across two helpers/two transactions with
   no shared owner.

4. **UI/API read materialized DB-backed state.** Immich `'/'` and detail
   routes read DTOs backed by PostgreSQL; there is no "is it done?" polling
   of the job queue (§5, §6, §7). Gallery already follows this for the read
   side (TanStack Query reads `/api/libraries/{id}/status` etc., which read
   `assets.metadata_state`). The fix is therefore on the write/completion
   side, not the read side.

5. **Workers/queues have explicit lifecycle ownership.** Immich owns each
   queue lifecycle in a dedicated BullMQ worker with one handler per
   `JobName` and verification that every `JobName` maps to exactly one
   handler (§8, §9). The Gallery application is local SQLite + in-process
   workers, so the analogue is not BullMQ — it is one Python module that
   owns **scheduling + dispatch + worker start + completion transitions +
   stale guards + restart recovery** for metadata. Today that ownership is
   scattered; the refactor consolidates it.

6. **Durable state recovers runtime work after restart.** Immich recovers by
   re-reading DB state and re-queuing work; BullMQ's durable Redis streams
   are infrastructure-specific. The Gallery analogue is to recover from
   SQLite: on startup, scan `metadata_index_jobs` for work that should be
   re-dispatched and for inconsistent completion rows that should be
   repaired. This pattern already exists for `library_jobs`
   (`recover_stale_jobs`); it should be mirrored, separately, for
   `metadata_index_jobs`.

**What must NOT be copied from Immich (explicit non-goals):**

- Redis / Valkey, BullMQ, or any cross-process queue broker.
- PostgreSQL or any subset of its indexes/extensions (`pgvector`,
  `pg_trgm`, etc.). Gallery stays on SQLite + FTS5.
- Distributed / multi-process workers, microservices, or the supervisor/API/
  microservices process split (`IMMICH_PIPELINE_AUDIT.md` §9).
- Immich's `asset_job_status`, `asset_file`, `smart_search`, `asset_ocr`,
  plugin/workflow, mobile sync, or admin/queue controller surfaces. They do
  not map to a local single-user gallery.
- Any new runtime dependency. The refactor must use only what is already in
  `pyproject.toml` / `uv.lock`.

The intended design is **D·full** in spirit: full lifecycle ownership in one
module boundary, not a port of Immich's infrastructure.

## 4. Proposed D·full architecture

The owner boundary is the `backend/indexer.py` runtime layer together with a
new completion helper in `backend/metadata_store/`. The store layer stays the
DB-access boundary; the indexer layer stays the runtime/dispatch boundary.
The two new public functions below are the only production entrypoints for
scheduling and completion. The principle is: every producer of metadata work
calls one scheduling entrypoint; every consumer that finishes work calls one
completion entrypoint; both enforce the full lifecycle invariant.

### 4.1 Scheduling owner

Introduce one public scheduling entrypoint in `backend/indexer.py`:

```python
def dispatch_metadata_index_paths(
    paths: Iterable[str | Path],
    root_path: str | Path | None = None,
    *,
    start_worker: bool = True,
) -> dict[str, int]:
    """Full metadata lifecycle scheduling: durable jobs + in-memory dispatch + worker start."""
```

Responsibilities (enforced in this order, under the existing `_DB_LOCK`):

1. **Durable job creation/coalescing.** Delegate the DB-only row writes to the
   existing `queue_metadata_index_paths(...)` in `metadata_queue.py`
   (renamed/privatized per §5 and §Phase 4). Its skip/short-circuit behavior
   stays, but it must report which jobs it short-circuited so the asset
   transition can be applied here (see §4.2).
2. **In-memory queue enqueue** via the existing
   `_enqueue_metadata_jobs_from_result(...)` logic (`indexer.py:397-423`):
   push `result.enqueued` to `_job_queue`, coalesce via `_queued_keys`, bump
   counters.
3. **Worker ensure/start** via `_start_worker_if_needed()` (`indexer.py:232`).
4. **Asset completion for short-circuited jobs.** For every job
   `result.skipped`/short-circuited as "already current", invoke the shared
   completion transition (§4.2) so `assets.metadata_state` is reconciled to
   `'done'`. This repairs Bug 2 at its source.
5. **Idempotency/deduplication** is preserved by `_queued_keys` for the
   in-memory queue and by `metadata_index_jobs.path PRIMARY KEY`
   (`_schema.py:231-247`) for the durable queue. Repeated calls for the same
   path/mtime/size produce no new work and no double-dispatch.
6. **Counters/result reporting.** Return the same `{queued, coalesced,
   skipped, failed}` shape the callers already parse
   (`scan_worker.py:204-207`, `indexer.py:688-720`).

Callers to migrate:

| Caller | File:line | Current call | New call |
| --- | --- | --- | --- |
| Scan/catalog scan path | `indexer.py:703` (`rebuild_index_scope`) and `indexer.py:594` (`_flush_staged_paths_to_job_queue`) | `queue_metadata_index_paths` then `_enqueue_metadata_jobs_from_result` (manual two-step) | `dispatch_metadata_index_paths` (single call) — but keep the staging loop's "stage in RAM, flush later" behavior for the `/api/scan` hot path. Staging stays; only the *flush* needs to call the unified entrypoint. |
| Rebuild path | `scan_worker.py:312` | `queue_metadata_index_paths` | `dispatch_metadata_index_paths` (the core Bug 1 fix) |
| Manual/scheduled staging flush | `indexer.py:564-598` | as above | as above |
| Startup recovery (§4.4) | new | new | `dispatch_metadata_index_paths` per recovered batch |

Fate of `queue_metadata_index_paths(...)`:

- Keep it as the DB-only helper, but **rename** it to
  `persist_metadata_index_jobs(...)` (or keep the name if §Phase 4 prefers
  minimal churn) and **make it underscore-private** from the store's public
  surface (`backend/metadata_store/__init__.py:227`). Production callers must
  not import it directly; only `indexer.dispatch_metadata_index_paths` and
  tests may. This prevents future half-pipeline callers like the rebuild bug.
- It must return enough information for the scheduling owner to know which
  paths were short-circuited, so the owner can run the asset completion
  transition. The current `MetadataQueueResult` already returns
  `skipped`/`failed` counts; the extension is to also return the *paths* that
  were short-circuited (new `short_circuited: list[MetadataIndexJob]` field on
  `MetadataQueueResult`).

This guarantees "A DB job can exist without runtime worker dispatch" cannot
recur: every producer goes through one entrypoint that always dispatches and
always starts the worker.

### 4.2 Completion owner

Introduce one shared completion transition in
`backend/metadata_store/metadata_queue.py` (the store layer is the right
home because completion needs a single SQLite transaction over both
`metadata_index_jobs` and `assets`):

```python
def complete_metadata_jobs(
    jobs: Iterable[MetadataIndexJob],
    *,
    metadata_is_current: bool = True,
) -> None:
    """Atomically transition: metadata current + metadata_index_jobs.done + assets.metadata_state='done'."""
```

Invariant enforced (single SQLite transaction, under `_DB_LOCK`):

```
PRE: for each job,
     - optionally the caller asserts image_metadata.path exists with
       matching (mtime, size) — passed as metadata_is_current
     - job identity must match the *current* asset row
       (path, mtime, size) — see §4.3 stale guard
POST: for each job,
     - metadata_index_jobs.state='done', finished_at, updated_at
     - assets.metadata_state='done' for the matching asset row
     - if no matching asset row exists (no library/excluded), the job is
       marked 'skipped' but no asset transition is attempted; that is logged
       and is the contract for "asset row not under any library".
       This prevents the "job done but asset pending" ambiguity that the
       original bug family exploited.
     - if (mtime, size) differ from the current asset row, the job is
       marked 'stale' instead of 'done' (see §4.3 stale guard).
```

Routing rules (the divergence fix):

| Existing helper | Current behavior | New behavior |
| --- | --- | --- |
| `_mark_current_metadata_done(conn, job, now)` (`metadata_queue.py:65`) | writes `metadata_index_jobs.state='done'` only. | Internally call the same per-job transition as `complete_metadata_jobs` so `assets.metadata_state='done'` is also set when the asset row matches. Used by the §4.1 shortcut path. |
| `mark_metadata_jobs_done(jobs)` (`metadata_queue.py:207`) | writes `metadata_index_jobs.state='done'` only. | Delegate to a per-job `complete_metadata_jobs` helper. Used by the worker success path (`indexer.py:365-368`). |
| Worker success batch | `upsert_metadata_batch` (writes `image_metadata` + `assets.metadata_state='done'`) then `mark_metadata_jobs_done` (writes job only) — two transactions. | Keep `upsert_metadata_batch` for the `image_metadata` write, then call `complete_metadata_jobs(done_jobs)` in its own transaction. The asset transition is now *owned by the completion helper*, not by a side effect of the metadata upsert. This removes the silent no-op hazard of `_upsert_asset_conn` returning 0. |
| On-demand `/api/metadata` | `upsert_extracted_metadata(mark_job_done=True)` already upserts asset and then `_mark_current_metadata_done`. | Keep, but route `_mark_current_metadata_done` through the shared transition so the invariant is asserted once. |

Transaction scope / SQLite practical constraints:

- The completion transition is a single SQLite transaction and short (two
  `UPDATE`/`executemany` statements plus one existence check). SQLite WAL
  mode is already enabled (`docs/ARCHITECTURE.md`), so a short write
  transaction does not block readers.
- The metadata upsert (`image_metadata`) should remain in its own transaction
  *before* completion (as today), because it can be large and parsing-bound.
  The completion transaction is then small and fast. This keeps long SQLite
  transactions bounded (see §8) while still asserting the invariant that
  completion = "metadata is current AND job is done AND asset is done".
- If the caller already wrote `image_metadata` in the same connection
  (on-demand path), the completion helper may share the caller's transaction
  through an internal `complete_metadata_jobs_conn(conn, jobs)` variant;
  otherwise it opens its own connection.

### 4.3 Stale / race guards

Identity guard rule (enforced inside `complete_metadata_jobs` before any
write):

> A job created for an old version of a file must not mark the current asset
> done if the file changed, was deleted, was replaced, or moved.

Implementation:

1. **Path + mtime + size** is the current job-asset identity. The schema has
   no `asset_id`, `fingerprint`, or `generation` columns today
   (`_schema.py:231-247` for jobs, `:363-384` for assets), so the guard must
   use what exists. The job stores `mtime` + `size`; the asset stores
   `mtime_ns` + `size`. Compare:
   - `assets.mtime_ns == job.mtime` (with the existing float/integer
     comparison care already used by `_is_job_current`, `indexer.py:224-229`)
   - `assets.size == job.size`
   Note: `assets.mtime_ns` is declared `REAL` in the schema
   (`_schema.py:370`) despite its name; the comparison must tolerate that.
   This is called out so the implementation does not assume integer ns.
2. **Library-owned path** is enforced by matching the asset row via
   `_find_library_for_path_conn` (`_asset_store.py:33`), the same resolver
   already used for upserts. If no library owns `job.path`, the job is marked
   `'skipped'` (it had nowhere to materialise) but no asset transition is
   attempted — and this is logged at WARNING. Using `'skipped'` instead of
   `'done'` signals "intentional terminal no-op" rather than "job done but
   asset not done," avoiding the ambiguity that caused the original Bug 2/3.
3. **Filesystem guard** is preserved by the existing `_is_job_current`
   pre-check in `_process_batch` (`indexer.py:224-229`, `343-352`); the
   completion guard adds a *DB-side* check: job's `(mtime, size)` must equal
   the asset's `(mtime_ns, size)` before the asset transition is written.
   If they differ, the completion must mark the job `'stale'`
   (`mark_metadata_jobs_stale`) instead of `'done'` and skip the asset
   update. This prevents an old job row re-evaluated after a restart from
   stamping a newer asset done.
4. **Deleted / moved files.** If `Path(job.path).stat()` raises or returns
   different `(mtime, size)`, the completion treats the job as stale and
   leaves the asset row untouched (which is itself moved/replaced handling).
   The asset's `offline` flag is handled by catalog reconciliation
   (`reconcile_library_assets`) and is out of scope for the metadata
   completion transition.
5. **`library_id` scope.** `metadata_index_jobs` does not currently carry a
   `library_id` column; identity is path-only. The job's `root_path` is a
   hint, but the authoritative library is the asset row's `library_id`
   (enforced via `UNIQUE(library_id, path)` on `assets`, `_schema.py:383`).
   The completion helper joins `assets` by path and re-derives the library
   from the asset row, which removes the window where a stale `root_path`
   could mismatch.
6. **Evaluation of better identity fields.** This plan does **not** add
   `asset_id`/`fingerprint`/`generation` columns (see §5: minimal/no migration).
   If a later phase adds a `metadata_index_jobs.asset_id` FK, the guard
   should switch to joining on `asset_id`. That is documented in §7 Phase 4
   as a follow-up, not part of this refactor.

### 4.4 Startup recovery / rehydration

Add `recover_metadata_index_jobs()` in `backend/indexer.py` (the runtime
owner — see §0 clarification 1) and call it from `app.startup()`
(`app.py:98-104`) alongside, but distinct from, `recover_stale_jobs()`.
`backend/metadata_store/metadata_queue.py` exposes only the DB primitives it
needs:
- `list_recoverable_metadata_jobs()` — returns `metadata_index_jobs` rows
  matching recovery criteria.
- `reset_running_metadata_jobs_to_queued(job_ids)` — atomically resets
  `'running'` → `'queued'` (preserving `attempts`, `queued_at`).
- `complete_metadata_jobs(...)` — already shared with the completion owner.

`indexer.recover_metadata_index_jobs()` calls these store helpers, then uses
`dispatch_metadata_index_paths` (§4.1) to re-enqueue rows. The store layer
never imports the runtime layer, preventing the circular hazard.

Recovery must own *metadata* recovery only, not catalog recovery. Cases:

| Case | Detection query | Recovery action |
| --- | --- | --- |
| `metadata_index_jobs.state='queued'` | `SELECT ... WHERE state='queued'` | Re-dispatch each path through `dispatch_metadata_index_paths([path], root_path)` (owner from §4.1), which re-populates the in-memory `_job_queue` and ensures the worker is started. Coalesce via `_queued_keys` and `metadata_index_jobs.path PK` so a job already re-queued is not double-dispatched. |
| `metadata_index_jobs.state='running'` | `SELECT ... WHERE state='running'` | The in-memory worker is gone (RAM queue lost). Reset to `'queued'` (preserving `attempts` and `queued_at`) and re-dispatch via the owner. This differs from the catalog `recover_stale_jobs` policy (which *fails* catalog jobs); metadata jobs are cheap and idempotent, so re-queue is correct. Add `MAX_METADATA_JOB_ATTEMPTS` check (already in `_db.py`) so exhausted jobs are marked `'failed'` instead of re-queued. |
| `metadata_index_jobs.state='done'` + current `image_metadata` + `assets.metadata_state IN ('pending','reset')` | `SELECT mij.path, mij.mtime, mij.size FROM metadata_index_jobs mij JOIN image_metadata im ON im.path=mij.path AND im.mtime=mij.mtime AND im.size=mij.size JOIN assets a ON a.path=mij.path WHERE mij.state='done' AND a.metadata_state != 'done'` | Run `complete_metadata_jobs` on each such job. This is the §4.5 repair. |
| `metadata_index_jobs.state='done'` + missing `image_metadata` or `(mtime,size)` mismatch | as above with inverted join condition | Demote the job to `'queued'` and re-dispatch, because the durable "done" was lying — metadata was not actually current. |
| Stale / outdated jobs whose `(path,mtime,size)` no longer match `Path.stat()` | `Path(path).stat()` mismatch | `mark_metadata_jobs_stale` and skip. The asset is left untouched. |
| Missing files | `Path(path).stat()` raises `OSError` | `mark_metadata_jobs_stale`; leave asset to the catalog offline path. |
| Assets no longer matching job identity (asset moved/rebuilt with new content) | asset row exists with different `(mtime_ns,size)` than the job | `mark_metadata_jobs_stale`; the newer asset will be re-queue-owned by the next scan/rebuild. |

Recovery design constraints (compare with catalog recovery
`job_store.py:439-463` and `test_catalog_recovery.py`, but keep metadata
recovery scoped):

- **Bounded.** Recovery runs once at startup. It must not loop forever: a row
  re-dispatched through the owner is either coalesced (no-op) or re-entered.
  Idempotency (§4.1 step 5) guarantees a single recovery pass sets all
  states correctly.
- **Out of scope:** it must not touch `library_jobs`, `library_import_paths`,
  `catalog_rebuild_entries`, or `file_index`. Catalog recovery stays the
  catalog recovery owner.
- **Ordering:** metadata recovery should run *after* `recover_stale_jobs()` so
  catalog rows are coherent first; then `dispatch_metadata_index_paths` is
  safe to call.

`recover_metadata_index_jobs()` returns a small diagnostics dict
(`{requeued, refailed, repaired, stale, deleted}`) that startup can log.

### 4.5 Repair strategy for existing inconsistent DBs

The same repair as §4.4's `done` + current-metadata + pending-asset case is
the maintenance repair for already-inconsistent DBs. Decision:

- **Location:** run **inside the startup recovery pass** by default. There is
  no separate maintenance API added in this plan — owners are the only
  production paths now, so the inconsistent window is closed both for *future*
  writes and for *legacy* writes by a single startup pass. (See §5 for why a
  one-off migration is not preferred.)
- **Optional explicit maintenance function:** expose
  `repair_inconsistent_asset_states(conn, scope_path=None)` as a store-layer
  helper in `backend/metadata_store/metadata_queue.py`. The runtime owner
  (`indexer.recover_metadata_index_jobs`) calls it; it can also be wired
  into a future `/api/libraries/{id}/repair`-style endpoint (see existing
  `/api/derivatives/warm|rebuild|clear` patterns in `libraries.py`) without
  importing the runtime layer.
- **What not to do.** Do not sweep `assets.metadata_state='pending'` →
  `'done'` blindly. The repair MUST verify `image_metadata` row exists and
  its `(mtime, size)` matches the asset, otherwise it demotes the job and
  re-dispatches (the "durable done was lying" case above). This is the safe
  inverse of the completion transition.

Repair rule, written out:

```
For each job j where j.state='done':
    im = image_metadata.row_for(j.path)
    asset = assets.row_for(j.path)
    if im exists and im.(mtime,size) == j.(mtime,size) and asset exists:
        if asset.metadata_state != 'done':
            complete_metadata_jobs([j])    # repair: stamp asset done + keep job done
    elif asset is None or no library owns j.path:
        mark j.state='skipped'             # terminal no-op, not 'done'
    elif im missing or im.(mtime,size) != j.(mtime,size):
        # durable "done" was lying; demote and re-dispatch
        set j.state='queued' (preserve queued_at, attempts)
        dispatch_metadata_index_paths([j.path], j.root_path)
    elif asset.(mtime_ns,size) != j.(mtime,size):
        mark j.state='stale'               # asset moved on; old job is stale
```

## 5. Migration / compatibility strategy

No schema migration is required for Phases 1–3. All new logic operates on
existing columns. No new columns, no new tables, no destructive DDL. The
refactor is therefore safe to ship without a schema version bump.

Existing columns used:

- `metadata_index_jobs`: `path (PK)`, `mtime`, `size`, `state`, `attempts`,
  `root_path`, `queued_at`, `started_at`, `finished_at`, `updated_at`.
- `assets`: `metadata_state`, `mtime_ns`, `size`, `library_id`, `path`
  (with `UNIQUE(library_id, path)`).
- `image_metadata`: `path (PK)`, `mtime`, `size`, `metadata_json`.

**Deferred (follow-up, not part of this refactor):**

1. `metadata_index_jobs.library_id INTEGER` (NULLABLE) — would let the stale
   guard join on `library_id` instead of re-deriving from `path`. Deferred
   because the path→library lookup already exists (`_find_library_for_path_conn`)
   and is cheap.
2. `idx_assets_metadata_state` — would speed the repair/recovery scan on
   libraries with 100k+ assets. Deferred until large-library profiling proves
   the full scan is a bottleneck; the existing
   `idx_metadata_index_jobs_state` (`_schema.py:249`) already covers the
   metadata-jobs-side scan.
3. `metadata_index_jobs.asset_id` — natural FK if a future phase adds it.
   Not needed for the current stale guard, which uses `(path, mtime, size)`.

These are purely additive (`_ensure_column` / `CREATE INDEX IF NOT EXISTS`
already used in `_schema.py:32-36, 476-477`), so they are safe to add later
without a heavyweight migration step if profiling justifies them.

## 6. Test plan

Each test gives: name, target file, setup, action, expected assertions, and
the bug/invariant it protects. New tests live under
`backend/tests/`. The codebase convention requires the `Purpose / Guarantees /
Run when` docstring header used by existing tests (see
`test_indexer_staging.py:1-13`, `test_catalog_recovery.py`); new tests must
include it. New rows must be appended to `docs/testing/TEST_CATALOG.md`.

1. **Rebuild path uses the full metadata scheduler, not DB-only queue.**
   - Target: `backend/tests/test_indexer_staging.py`
   - Setup: monkeypatch `indexer._enqueue_metadata_jobs_from_result` to
     record calls and `indexer.queue_metadata_index_paths` (renamed per
     §Phase 4) to return a `MetadataQueueResult(enqueued=[job])`. Driver
     `scan_worker.execute_rebuild_job` against a fake job over
     `tmp_path` online import path.
   - Action: run `execute_rebuild_job(job)`.
   - Assert: `dispatch_metadata_index_paths` was invoked (or, equivalently,
     `_enqueue_metadata_jobs_from_result` was invoked with the rebuild's
     paths) and `_job_queue.qsize() > 0`; previously
     `scan_worker.py:312` invoked `queue_metadata_index_paths` only.
   - Protects: Bug 1.

2. **Current-metadata shortcut marks both job done and asset metadata done.**
   - Target: `backend/tests/test_metadata_store_coverage.py`
   - Setup: an `assets` row with `metadata_state='reset'`/`'pending'` for an
     image whose `image_metadata` row already has matching `(mtime, size)`.
   - Action: call `dispatch_metadata_index_paths([image_path], root)`.
   - Assert: `metadata_index_jobs.state='done'` AND
     `assets.metadata_state='done'` for that path.
   - Protects: Bug 2.

3. **Worker success marks both job done and asset metadata done through one
   completion owner.**
   - Target: `backend/tests/test_indexer_staging.py`
   - Setup: stage an `image_path` whose stat matches a job; don't mock
     `upsert_metadata_batch` (use a real toy extractor monkeypatched into
     `indexer.extract_metadata` so we don't depend on PIL/A1111 parsing).
     Provide an `assets` row for the path with `metadata_state='pending'`.
   - Action: run `indexer._process_batch([job])`.
   - Assert: `metadata_index_jobs.state='done'`,
     `assets.metadata_state='done'`, and `complete_metadata_jobs` (the new
     owner) — or the shared per-job transition — is the code path that wrote
     both, not the divergent two-helper sequence. Also assert that if
     `_upsert_asset_conn` would no-op (asset row removed), completion still
     marks the job done and logs the missing asset rather than leaving the
     job `running`.
   - Protects: Bug 3 (corrected form: completion is an owned invariant, not
     a sequencing side effect).

4. **Library progress / API indexed count increases after metadata
   completion.**
   - Target: `backend/tests/test_catalog_status_ready_assets.py`
   - Setup: extend an existing fixture to seed an `assets` row with
     `metadata_state='pending'` plus a matching `image_metadata` row plus
     a `metadata_index_jobs` row `state='running'`.
   - Action: call `complete_metadata_jobs([job])`, then call
     `status_store` readiness aggregation (the same APIs used by
     `/api/libraries/{id}/status`).
   - Assert: `ready_assets` increases by 1 and `not_ready_assets`
     decreases by 1.
   - Protects: invariant "API/progress sees indexed assets after metadata
     completion" (Bug 2/3 symptom regression).

5. **Stale job with old `mtime`/`size` cannot mark a changed asset done.**
   - Target: `backend/tests/test_metadata_store_coverage.py` (or a new
     `test_metadata_completion_guards.py`)
   - Setup: `assets` row with new `(mtime_ns, size)` for `path`; a job with
     old `(mtime, size)`; `image_metadata` row matching the *asset's* new
     values (the asset was re-indexed by a later scan).
   - Action: call `complete_metadata_jobs([stale_job])`.
   - Assert: `metadata_index_jobs.state='stale'` (NOT `'done'`),
     `assets.metadata_state` is unchanged.
   - Protects: §4.3 stale/race guard; "old job marking a new asset done".

6. **Startup recovery requeues queued/running metadata jobs after in-memory
   queue loss.**
   - Target: `backend/tests/test_metadata_recovery.py` (new — parallel to
     `test_catalog_recovery.py`)
   - Setup: trick `recover_metadata_index_jobs` with `metadata_index_jobs`
     rows in `'queued'` and `'running'` states. RAM `_job_queue` is empty.
   - Action: call `recover_metadata_index_jobs()`.
   - Assert: ex-`running` rows are reset to `'queued'` (unless
     `attempts >= MAX_METADATA_JOB_ATTEMPTS`), `'queued'` rows are
     re-dispatched (the in-memory `_job_queue` now contains them and the
     worker thread is ensured started). Idempotency: a second recovery pass
     is a no-op.
   - Protects: §4.4 recovery cases 1 + 2.

7. **Repair case: job done + current image metadata + asset pending/reset
   should repair asset done.**
   - Target: `backend/tests/test_metadata_recovery.py`
   - Setup: seed the inconsistent triple (`mij.state='done'`, current
     `image_metadata`, `assets.metadata_state='pending'`).
   - Action: run `recover_metadata_index_jobs()` (which performs the repair
     in §4.4/§4.5).
   - Assert: `assets.metadata_state='done'` after recovery; job stays
     `'done'`.
   - Protects: §4.5 repair.

   Optional companion test (same file): seed the "durable done was lying"
   case (`mij.state='done'` but missing `image_metadata`) and assert recovery
   demotes the job to `'queued'` and re-dispatches rather than blindly
   stamping the asset done.

8. **Scan and rebuild share the same scheduling entrypoint.**
   - Target: `backend/tests/test_indexer_staging.py`
   - Setup: monkeypatch `indexer.dispatch_metadata_index_paths` to record
     every invocation.
   - Action: drive both `scan_worker.execute_scan_job` (through
     `rebuild_index_scope`) and `scan_worker.execute_rebuild_job` once each.
   - Assert: both flows invoke `dispatch_metadata_index_paths` exactly the
     expected number of times; neither invokes `queue_metadata_index_paths`
     (or its renamed private form) directly from production code.
   - Protects: §4.1 single-owner invariant.

9. **No production caller directly uses the DB-only metadata queue helper.**
   - Target: `scripts/audit_test_matrix.py` extension or a new
     `scripts/check_metadata_lifecycle_ownership.py`
   - Setup: scan `backend/` excluding `tests/` for imports/calls of
     `queue_metadata_index_paths`/`persist_metadata_index_jobs` and
     `_mark_current_metadata_done`/`mark_metadata_jobs_done`.
   - Action: run the audit.
   - Assert: the only modules that call the renamed DB-only helper or the
     renamed completion primitives are `indexer.py` (the owner) and
     `metadata_persist.py`'s on-demand path; no production caller in
     `scan_worker.py` calls them directly anymore.
   - Protects: prevents regression to Bug 1-style half-pipeline callers.

10. **Double enqueue / repeated dispatch is idempotent.**
    - Target: `backend/tests/test_indexer_staging.py`
    - Setup: stage one path, then call `dispatch_metadata_index_paths` for
      the same path three times.
    - Action: inspect `_job_queue`, `_queued_keys`, and
      `metadata_index_jobs` rows for that path.
    - Assert: exactly one in-memory job entry after dedup; the durable row's
      `state` and `attempts` do not regress; counters report
      `coalesced >= 2` on repeat calls.
    - Protects: §4.1 step 5 + §8 first risk.

Existing tests that must still pass without modification unless intentionally
updated (cross-check against `docs/testing/TEST_CATALOG.md` rows):

- `test_indexer_staging.py` (staging/yield/retry) — will need new tests but
  existing ones must keep passing; `monkeypatch` of
  `indexer.queue_metadata_index_paths` in 5 existing cases must be retargeted
  to the renamed helper.
- `test_catalog_recovery.py` — unaffected; metadata recovery is a separate
  test and a separate function.
- `test_libraries_catalog.py:366,372` (`rebuild_index_scope` end-to-end) —
  must keep passing; this is the test that would already catch part of Bug 1
  if the rebuild path went through `rebuild_index_scope`, confirming the
  rebuild path is currently NOT going through it.
- `test_metadata_store_coverage.py` — coalesce/skip/fail tests must keep
  passing against the renamed helper.

## 7. Implementation phases

Phases are intentionally small and reviewable. Each phase lists expected files
to change. The phases are described relative to the current revision and are
expected to land in this order; Phase 0 must precede Phase 1 so that the
refactor fixes observable, test-reproduced bugs.

### Phase 0 — Characterization and failing regression tests

Add tests that reproduce the lifecycle gaps *before* changing production code.
This locks the bug family so the refactor is verifiable.

Files expected to change:

- `backend/tests/test_indexer_staging.py` — add Test 1 (rebuild dispatch
  currently missing) and Test 10 (idempotency) as `xfail`/assertion-against-
  current-buggy-behavior, flipped to passing in Phase 1.
- `backend/tests/test_metadata_recovery.py` — new file, Tests 6 + 7.
- `backend/tests/test_metadata_store_coverage.py` — add Test 2 (shortcut
  asset transition gap) and Test 5 (stale guard), initially failing.
- `backend/tests/test_catalog_status_ready_assets.py` — add Test 4.
- `docs/testing/TEST_CATALOG.md` — append new test rows.

### Phase 1 — Scheduling owner

Introduce `dispatch_metadata_index_paths(...)` in `backend/indexer.py` and
migrate both producers (scan/rebuild) to it.

Files expected to change:

- `backend/indexer.py` — add the public entrypoint; refactor
  `rebuild_index_scope` (`:688-720`) and `_flush_staged_paths_to_job_queue`
  (`:564-598`) to call it; keep `stage_metadata_paths_from_scan` staging
  behavior intact.
- `backend/scan_worker.py` — in `execute_rebuild_job` (`:242-345`), replace
  the inline `queue_metadata_index_paths` loop at `:311-315` with a single
  `dispatch_metadata_index_paths` call (or one call per `(root, paths)`
  grouping, matching the existing grouping at `:303-310`). This is the
  core Bug 1 fix.
- `backend/metadata_store/metadata_queue.py` — extend `MetadataQueueResult`
  (and `backend/metadata_store/types.py`) with `short_circuited:
  list[MetadataIndexJob]` populated by the "already current" branch at
  `:114-116`, so the scheduling owner can run the asset completion transition.
- Tests: flip Phase 0 Tests 1, 8, 10 to passing.
- `docs/ARCHITECTURE.md` — note `dispatch_metadata_index_paths` as the
  single scheduling entrypoint in the Backend Behavior / domain mapping
  sections (and update `docs/archived/METADATA_STORE_SPLIT_PLAN.md` cross-link
  only if needed; do not edit archived content per repo policy).

### Phase 2 — Completion owner

Introduce `complete_metadata_jobs(...)` and route both `_mark_current_metadata_done`
and `mark_metadata_jobs_done` through it. This is the Bug 2 + Bug 3 (corrected)
fix.

Files expected to change:

- `backend/metadata_store/metadata_queue.py` — add `complete_metadata_jobs`
  and `complete_metadata_jobs_conn(conn, jobs)` variants; refactor
  `_mark_current_metadata_done` (`:65-96`) and `mark_metadata_jobs_done`
  (`:207-225`) to delegate to it; the §4.3 stale guard lives in this helper.
- `backend/metadata_store/__init__.py` — export `complete_metadata_jobs`.
- `backend/indexer.py` — in `_process_batch` (`:311-395`), replace the
  separate `upsert_metadata_batch` + `mark_metadata_jobs_done` two-step
  (`:356-368`) with `upsert_metadata_batch` + `complete_metadata_jobs`.
- `backend/metadata_store/metadata_persist.py` — in
  `upsert_extracted_metadata` (`:178-189`), ensure
  `mark_job_done=True` routes through the completion helper (asset + job
  transition in one go).
- **Side-effect note:** `_upsert_extracted_metadata_conn` continues to call
  `_upsert_asset_conn(metadata_state="done")` during this phase. The
  completion helper re-asserts the same state in its own transaction. This
  double-write is a temporary safety net. Phase 4 may remove the
  `metadata_state="done"` side-effect from `_upsert_extracted_metadata_conn`
  after tests prove the completion helper always runs.
- Tests: flip Phase 0 Tests 2, 3, 4, 5 to passing.

### Phase 3 — Stale guards and startup recovery

Add the §4.3 DB-side guard checks (path + mtime + size + library ownership,
plus the `"done was lying"` demote-and-re-dispatch case) inside
`complete_metadata_jobs`, and add `recover_metadata_index_jobs(...)` wired
into `app.py` startup.

Files expected to change:

- `backend/metadata_store/metadata_queue.py` — add DB primitives:
  `list_recoverable_metadata_jobs(connection, states, limit)`,
  `reset_running_metadata_jobs_to_queued(connection, job_ids)`.
  These are called by the runtime owner, not by app.py directly.
- `backend/indexer.py` — add `recover_metadata_index_jobs()`. This function
  calls the store primitives above, then uses `dispatch_metadata_index_paths`
  (§4.1) to re-enqueue recovered rows. The store primitive
  `complete_metadata_jobs` is also reused. This function lives in the runtime
  layer, not in the store layer, to avoid circular imports (§0 clarification 1).
- `backend/app.py` — call `indexer.recover_metadata_index_jobs()` in
  `_startup_background_services` (`:98-104`) after `recover_stale_jobs()`.
- Optionally `backend/config.py` — flag to disable/limit recovery work for
  very large libraries (e.g., `METADATA_RECOVERY_MAX_ROWS`, mirroring existing
  bounded-work flags).
- Tests: flip Phase 0 Tests 6 + 7 to passing; add the "durable done was
  lying" demote companion test.

### Phase 4 — Cleanup and docs

Rename/privatize the DB-only helpers and remove/update tests that mock too
low-level, and update architecture/testing docs.

Files expected to change:

- `backend/metadata_store/metadata_queue.py` — rename
  `queue_metadata_index_paths` → `persist_metadata_index_jobs` (underscore
  convention left as a decision for the implementation PR; the key constraint
  is that the public metadata-store re-export in
  `backend/metadata_store/__init__.py:227` is removed so production code
  cannot import it). Similarly privatize `_mark_current_metadata_done` and
  `mark_metadata_jobs_done` if no external caller remains after Phase 2
  routes through `complete_metadata_jobs`. Remove the
  `metadata_state="done"` side-effect from `_upsert_extracted_metadata_conn`
  now that the completion helper (§0 clarification 4) is proven to always
  run via tests.
- `backend/tests/test_indexer_staging.py`,
  `backend/tests/test_metadata_store_coverage.py`,
  `backend/tests/test_metadata_binary_sanitizer.py:83` — retarget existing
  monkeypatches and `from backend.metadata_store import queue_metadata_index_paths`
  references to the renamed helper / the new owner.
- `scripts/audit_test_matrix.py` or new
  `scripts/check_metadata_lifecycle_ownership.py` — add Test 9.
- `docs/ARCHITECTURE.md` — describe the metadata lifecycle owner and the
  invariants.
- `docs/testing/TEST_CATALOG.md` — finalize new test rows.
- `docs/research/IMMICH_PIPELINE_AUDIT.md` — no edit required (research
  snapshot); the plan cross-references it but does not change it.

## 8. Risk assessment

| Risk | Mitigation |
| --- | --- |
| **Double enqueue** (re-dispatch at recovery + scan in-flight) | Idempotency is enforced by `_queued_keys` (RAM) and `metadata_index_jobs.path PK` (DB). The recovery pass and the owner call the same `dispatch_metadata_index_paths`, so the second call coalesces. Test 10 covers it. |
| **Starting multiple metadata worker threads** | `_start_worker_if_needed` (`indexer.py:232-244`) is guarded by `_worker_lock` + `_worker_thread.is_alive()`; the owner calls exactly this. No new thread spawn path is added. |
| **Long SQLite transactions** | Completion transaction is bounded to two writes + one existence check (§4.2). Metadata `image_metadata` upsert stays a separate, larger transaction as today. Recovery is one scan + per-batch `dispatch_metadata_index_paths`. |
| **Scan/rebuild concurrency** | Catalog service already serializes via `claim_next_catalog_job` (`scan_worker.run_once`). The metadata owner inherits the existing `_DB_LOCK` + WAL semantics; no new cross-catalog locking is added. |
| **Old job marking a new asset done** | §4.3 DB-side guard: completion requires `assets.(mtime_ns,size) == job.(mtime,size)`; mismatches mark the job `'stale'` and leave the asset alone. Test 5 covers it. |
| **Repair marking the wrong asset done** | The §4.5 repair rule requires the `image_metadata` row's `(mtime, size)` to match the job before stamping the asset; otherwise the "durable done was lying" branch demotes and re-dispatches. The repair never bulk-updates `metadata_state='done'`. |
| **Current tests mocking too low-level / private functions hiding lifecycle bugs** | Phase 4 privatizes/renames the DB-only helpers and updates existing tests to mock the owner boundaries (`dispatch_metadata_index_paths`, `complete_metadata_jobs`) rather than the internal primitives. Test 9 enforces that no production caller bypasses the owners. |
| **Performance regression for large libraries** | Recovery is a single bounded pass; §5's `idx_assets_metadata_state` index keeps the repair scan cheap. The owner does no extra work on the happy path (the dispatch logic already exists today). |
| **Startup recovery doing too much work** | Recovery scope is metadata-only and bounded by `metadata_index_jobs` size. The optional `METADATA_RECOVERY_MAX_ROWS` flag caps per-pass rows; recovery idempotency means partial recovery resumes correctly across restarts. |
| **Behavior changes for existing partially indexed DBs** | The repair pass in §4.4/§4.5 is read-then-reconcile, never destructive; it cannot lose already-`done` state and cannot wrongly promote a non-current asset (guard in §4.3). Legacy DBs that relied on the rebuild being a no-op for metadata will now correctly dispatch metadata work — this is the intended behavior change and is documented in the Phase 1 summary. |

## 9. Acceptance criteria

- [ ] Scan and rebuild use the same metadata scheduling entrypoint
  (`dispatch_metadata_index_paths`).
- [ ] No production caller schedules DB-only metadata jobs without runtime
  dispatch; `scan_worker.execute_rebuild_job` no longer calls
  `queue_metadata_index_paths`/`persist_metadata_index_jobs` directly.
- [ ] Metadata job completion always materializes `assets.metadata_state='done'`
  when metadata is current and an asset row exists, via one owned completion
  transition (`complete_metadata_jobs`).
- [ ] Stale jobs (old `mtime`/`size`, missing file, replaced asset) cannot
  mark a changed asset done.
- [ ] `queued`/`running` metadata jobs do not get stuck after restart;
  `recover_metadata_index_jobs` re-dispatches them on startup.
- [ ] Inconsistent `done`-job + current-metadata + pending-asset states are
  repaired (or explicitly re-dispatched when "durable done was lying")
  during recovery.
- [ ] `/api/libraries/{id}/status` and Library Inspector coverage see indexed
  assets after metadata completion (Test 4).
- [ ] Regression tests for the known bug family exist: Bug 1 (Test 1),
  Bug 2 (Test 2), Bug 3 corrected (Test 3), stale guard (Test 5), recovery
  (Tests 6/7), shared entrypoint (Test 8), no half-pipeline import (Test 9),
  idempotency (Test 10).
- [ ] All existing backend tests still pass (where Phase 4 updates mocks,
  they are retargeted, not deleted).
- [ ] Frontend tests are unaffected (no API shape change); `./test.sh e2e`
  remains green.
- [ ] `docs/ARCHITECTURE.md` explains the new metadata lifecycle owner and
  the invariants it enforces; `docs/testing/TEST_CATALOG.md` lists the new
  regression tests.
- [ ] No new runtime dependency added; refactor stays on local SQLite +
  in-process workers and does not introduce Redis/BullMQ/PostgreSQL or any
  cross-process architecture.