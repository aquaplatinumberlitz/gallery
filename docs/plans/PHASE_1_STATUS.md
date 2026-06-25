# Metadata Lifecycle D·Full Clean — Implementation Status

Updated: 2026-06-25
Plan: `docs/plans/METADATA_LIFECYCLE_D_FULL_REFACTOR_PLAN.md`

## Phase 0A — Characterization Tests

**Status:** Complete ✅

6 characterization tests capture the bug family using existing API and store primitives:

| Test | File | What it characterizes |
| --- | --- | --- |
| Test 1 | `backend/tests/test_scan_worker.py` | Bug 1: `execute_rebuild_job` creates SQLite rows but `_job_queue` stays empty |
| Test 2 | `backend/tests/test_indexer_staging.py` | Bug 1 divergence: scan calls `_enqueue_metadata_jobs_from_result`, rebuild does not |
| Test 6 | `backend/tests/test_metadata_store_coverage.py` | Bug 2: "already current" shortcut marks job done but not asset |
| Test 7 | `backend/tests/test_catalog_status_ready_assets.py` | `ready_assets` requires both `asset_done` AND current `image_metadata` |
| Test 8 | `backend/tests/test_metadata_store_coverage.py` | `mark_metadata_jobs_done` has no stale guard |
| Test 14 | `backend/tests/test_indexer_staging.py` | `queue_metadata_index_paths` is idempotent |

## Phase 1 — DB-Claim Metadata Worker

**Status:** Complete ✅

### Schema migration (`backend/metadata_store/_schema.py`)
- Added `metadata_index_jobs.library_id INTEGER`
- Added `metadata_index_jobs.priority INTEGER NOT NULL DEFAULT 3`
- Added `idx_metadata_index_jobs_claim` on `(state, priority, queued_at)`
- Added `idx_metadata_index_jobs_library_state` on `(library_id, state)`
- Added `idx_assets_metadata_state` on `assets(metadata_state)`
- Added `MetadataIndexJob.library_id` field to types module

### Store primitives (`backend/metadata_store/metadata_queue.py`)
- `claim_next_metadata_job()` — `BEGIN IMMEDIATE`, SELECT queued, UPDATE running, COMMIT (modeled on `DerivativeScheduler._claim_job`)
- `complete_metadata_job(conn, job)` — updates both `metadata_index_jobs` (done) and `assets` (metadata_state='done')
- `fail_metadata_job(conn, job, error)` — marks job failed
- `mark_metadata_job_stale(conn, job)` — marks job stale
- `list_recoverable_metadata_jobs(conn, states)` — lists jobs by state
- `reset_running_jobs_to_queued(conn, job_paths)` — resets running to queued

### Worker class (`backend/indexer.py`)
- `MetadataLifecycleWorker` class with `start`, `stop`, `is_running`, `wake`, `_worker_loop`, `_claim_job`, `_run_job`, `_is_job_current`
- Singleton `metadata_worker` instance
- Wired to `app.py` startup/shutdown

### Phase 0B — Contract tests (`backend/tests/test_metadata_lifecycle.py`)
| Test | What it verifies |
| --- | --- |
| Test 3 | Worker claims queued jobs directly from SQLite |
| Test 4 | Claimed jobs move `queued -> running` atomically |
| Test 16 | Worker does not hold long write transactions during extraction |

## Test Results

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
======================= 45 passed, 4 warnings in 11.16s ========================
```

## Next Phase

**Phase 2 — Convert scheduling to durable DB queue + wake worker**

Change scan/rebuild/manual/startup scheduling to use `dispatch_metadata_index_paths()` which persists/coalesces jobs and wakes the DB-claim worker. Remove transitional `_job_queue` push from production paths.
