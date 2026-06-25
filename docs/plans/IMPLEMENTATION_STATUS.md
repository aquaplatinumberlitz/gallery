# Metadata Lifecycle D·Full Clean — Implementation Status

Plan: `docs/plans/METADATA_LIFECYCLE_D_FULL_REFACTOR_PLAN.md`
Last updated: 2026-06-25

---

## Overall progress

| Phase | Description | Status |
| --- | --- | --- |
| 0A | Characterization tests (existing API) | ✅ Complete |
| 0B | Contract tests for DB-claim worker | ✅ Complete (merged into Phase 1) |
| **1** | **DB-claim metadata worker** | **✅ Complete** |
| 2 | Convert scheduling to durable DB queue + wake worker | ⬜ Pending |
| 3 | Completion invariant and stale guards | ⬜ Pending |
| 4 | Startup recovery and repair | ⬜ Pending |
| 5 | Remove/deprecate old in-memory queue bridge | ⬜ Pending |
| 6 | Status/debug diagnostics and docs | ⬜ Pending |
| 7 | Broader integrity checker (P2 follow-up) | ⬜ Pending |

---

## Phase 0A — Characterization Tests ✅

6 tests capture the bug family using existing API and store primitives, no new symbols.

### Tests

| Test | File | What it characterizes | Status |
| --- | --- | --- | --- |
| **1** | `backend/tests/test_scan_worker.py` | Bug 1: rebuild creates SQLite rows but `_job_queue` stays empty | ✅ |
| **2** | `backend/tests/test_indexer_staging.py` | Bug 1 divergence: scan calls `_enqueue_metadata_jobs_from_result`, rebuild does not | ✅ |
| **6** | `backend/tests/test_metadata_store_coverage.py` | Bug 2: "already current" shortcut marks job done but not asset | ✅ |
| **7** | `backend/tests/test_catalog_status_ready_assets.py` | `ready_assets` requires both `asset_done` AND current `image_metadata` | ✅ |
| **8** | `backend/tests/test_metadata_store_coverage.py` | `mark_metadata_jobs_done` has no stale guard | ✅ |
| **14** | `backend/tests/test_indexer_staging.py` | `queue_metadata_index_paths` is idempotent | ✅ |

### Files changed

- `backend/tests/test_scan_worker.py` — **new**
- `backend/tests/test_indexer_staging.py` — added Tests 2, 14
- `backend/tests/test_metadata_store_coverage.py` — added Tests 6, 8
- `backend/tests/test_catalog_status_ready_assets.py` — added Test 7
- `docs/testing/TEST_CATALOG.md` — appended new test rows

---

## Phase 1 — DB-Claim Metadata Worker ✅ *(audit fixes applied 2026-06-25)*

### Schema migration

- Added `metadata_index_jobs.library_id INTEGER`
- Added `metadata_index_jobs.priority INTEGER NOT NULL DEFAULT 3`
- Added `idx_metadata_index_jobs_claim` on `(state, priority, queued_at)`
- Added `idx_metadata_index_jobs_library_state` on `(library_id, state)`
- Added `idx_assets_metadata_state` on `assets(metadata_state)`
- Added `MetadataIndexJob.library_id` field to types module

### Store primitives (`backend/metadata_store/metadata_queue.py`)

- `claim_next_metadata_job()` — `BEGIN IMMEDIATE`, SELECT queued, UPDATE running
- `complete_metadata_job(conn, job)` — updates both job (done) and asset (done)
- `fail_metadata_job(conn, job, error)` — marks job failed
- `mark_metadata_job_stale(conn, job)` — marks job stale
- `list_recoverable_metadata_jobs(conn, states)` — lists jobs by state
- `reset_running_jobs_to_queued(conn, job_paths)` — resets running to queued

### Worker class (`backend/indexer.py`)

- `MetadataLifecycleWorker` with start/stop/is_running/wake/worker_loop/claim_job/run_job
- Singleton `metadata_worker` instance wired to `app.py` startup/shutdown
- `_run_job` follows DerivativeScheduler pattern: short claim tx → extract → short complete tx

### Phase 0B — Contract tests (`backend/tests/test_metadata_lifecycle.py`)

| Test | What it verifies | Status |
| --- | --- | --- |
| **3** | Worker claims queued jobs directly from SQLite | ✅ |
| **4** | Claimed jobs move `queued -> running` atomically | ✅ |
| **16** | Worker does not hold long write transactions during extraction | ✅ |

### Files changed

- `backend/metadata_store/_schema.py` — additive migration + indexes
- `backend/metadata_store/metadata_queue.py` — 6 new store primitives
- `backend/metadata_store/__init__.py` — exports
- `backend/metadata_store/types.py` — `library_id` field
- `backend/indexer.py` — `MetadataLifecycleWorker` class + singleton + imports
- `backend/app.py` — wire worker start/stop
- `backend/tests/test_metadata_lifecycle.py` — **new** (Phase 0B)
- `docs/testing/TEST_CATALOG.md` — updated

---

## Test Results (current)

All 45 related tests pass with no regressions:

```
$ backend/venv/bin/python -m pytest \
    backend/tests/test_scan_worker.py \
    backend/tests/test_indexer_staging.py \
    backend/tests/test_metadata_store_coverage.py \
    backend/tests/test_catalog_status_ready_assets.py \
    backend/tests/test_metadata_lifecycle.py \
    backend/tests/test_catalog_recovery.py \
    backend/tests/test_libraries_catalog.py \
    -v --timeout=60
======================= 45 passed in 11.16s ========================
```

---

## Remaining known issues (resolved in plan)

All pre-implementation audit issues resolved before Phase 0A:
1. ✅ Migration uses `queued_at`, not `created_at`
2. ✅ No `id` auto-increment in Phase 1; keep `path TEXT PK`
3. ✅ Path-centric model with `library_id` as diagnostic only
4. ✅ Mutual exclusion rule for old/new worker (Phase 2 disables old worker)
5. ✅ `mtime_ns` vs `mtime` normalisation with REAL-vs-INTEGER tolerance (1000 ns)
6. ✅ Transitional bridge wording consistent (no real work pushed to `_job_queue` after Phase 2)

---

## Next phase

**Phase 2 — Convert scheduling to durable DB queue + wake worker**

Change scan/rebuild/manual/startup scheduling so they persist/coalesce jobs and wake the DB-claim worker. No production path pushes real work into `_job_queue` after Phase 2.
