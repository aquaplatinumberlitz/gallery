# Metadata Lifecycle D·Full Clean — Implementation Status

Plan: `docs/plans/METADATA_LIFECYCLE_D_FULL_REFACTOR_PLAN.md`
Last updated: 2026-06-25

---

## Overall progress

| Phase | Description | Status |
| --- | --- | --- |
| 0A | Characterization tests (existing API) | ✅ Complete |
| 0B | Contract tests for DB-claim worker | ✅ Complete (merged into Phase 1) |
| 1 | DB-claim metadata worker | ✅ Complete |
| **2** | **Convert scheduling to durable DB queue + wake worker** | **✅ Complete** |
| **3** | **Completion invariant and stale guards** | **✅ Complete** |
| **4** | **Startup recovery and repair** | **✅ Complete** |
| 5 | Remove/deprecate old in-memory queue bridge | ✅ Complete |
| 6 | Status/debug diagnostics and docs | ⬜ Pending |
| 7 | Broader integrity checker (P2 follow-up) | ✅ Complete |

---

## Phase 2 — Convert Scheduling to Durable DB Queue ✅

### Dispatch entrypoint (`backend/indexer.py`)

- `dispatch_metadata_index_paths(...)` — single scheduling entrypoint for all metadata work
- Persists/coalesces jobs in SQLite via `queue_metadata_index_paths`
- Wakes the DB-claim worker via `metadata_worker.wake()`
- Does NOT push into in-memory `_job_queue`
- Returns `{queued, coalesced, skipped, failed}` counters

### Callers migrated

| Caller | Old path | New path |
| --- | --- | --- |
| `rebuild_index_scope` (`indexer.py`) | `queue_metadata_index_paths` + `_enqueue_metadata_jobs_from_result` | `dispatch_metadata_index_paths` |
| `_flush_staged_paths_to_job_queue` (`indexer.py`) | `queue_metadata_index_paths` + `_enqueue_metadata_jobs_from_result` | `dispatch_metadata_index_paths` |
| `execute_rebuild_job` (`scan_worker.py`) | `queue_metadata_index_paths` (DB-only, Bug 1) | `dispatch_metadata_index_paths` |

### Old memory queue APIs disabled

- `_enqueue_metadata_jobs_from_result` → no-op compatibility stub (returns zero counters)
- `_start_worker_if_needed` → no-op stub (DB-claim worker manages itself)
- `_job_queue` is no longer populated by any production path

### Worker start enabled

- `metadata_worker.start()` enabled in `app.py` startup
- `metadata_worker.stop()` enabled in `app.py` shutdown

### Test updates

| Test | Old assertion | New assertion |
| --- | --- | --- |
| **Test 1** | `_job_queue.qsize() == 0` (Bug 1: rebuild doesn't dispatch) | `dispatch_metadata_index_paths` is called; `_job_queue` empty (DB-claim) |
| **Test 2** | scan calls `_enqueue_metadata_jobs_from_result`, rebuild doesn't | Both paths call `dispatch_metadata_index_paths` |
| Staging flush tests | assert `_job_queue.qsize() == 1` after flush | assert `_job_queue.qsize() == 0` (dispatch doesn't push to memory) |

### Files changed

- `backend/indexer.py` — added `dispatch_metadata_index_paths`, modified `rebuild_index_scope`, `_flush_staged_paths_to_job_queue`; made `_enqueue_metadata_jobs_from_result` and `_start_worker_if_needed` no-op stubs
- `backend/scan_worker.py` — import `dispatch_metadata_index_paths` from `indexer` (not `queue_metadata_index_paths` from `metadata_store`); updated `execute_rebuild_job` body
- `backend/app.py` — enabled `metadata_worker.start()` on startup, `metadata_worker.stop()` on shutdown
- `backend/tests/test_scan_worker.py` — updated Test 1 for Phase 2 behavior
- `backend/tests/test_indexer_staging.py` — updated Test 2 and 3 staging flush tests

---

## Test Results (current)

All 103 tests pass with no regressions:

```
$ backend/venv/bin/python -m pytest \
    backend/tests/test_catalog_recovery.py \
    backend/tests/test_catalog_status_ready_assets.py \
    backend/tests/test_indexer_staging.py \
    backend/tests/test_libraries_catalog.py \
    backend/tests/test_scan_worker.py \
    backend/tests/test_metadata_lifecycle.py \
    backend/tests/test_metadata_store_coverage.py \
    -v --timeout=60
======================= 103 passed in 17.83s ========================
```

---

## Phase 3 — Completion Invariant and Stale Guards ✅

### Completion owner unified

- `_mark_current_metadata_done` now calls `_update_asset_done` which materializes `assets.metadata_state='done'` alongside the job state (fixes Bug 2)
- `mark_metadata_jobs_done` (legacy batch path) now also calls `_update_asset_done` per job
- `upsert_extracted_metadata(mark_job_done=True)` routes through `_mark_current_metadata_done` (which includes asset materialization)

### Asset done helper

- Added `_update_asset_done(conn, job, now)` — shared helper that updates `assets.metadata_state='done'`
- Primary match: `path + ABS(mtime_ns - ?) < 1000 + size` (ns tolerance for REAL column)
- Legacy fallback: `path + ABS(mtime_ns / 1e9 - ?) < 1e-3 + size` (seconds tolerance)

### Tests updated

| Test | Old assertion | New assertion |
| --- | --- | --- |
| **Test 6** | Asset stays `reset` after shortcut (bug) | Asset goes `done` after shortcut (fix) |
| **Test 8** | Only job done, asset untouched | Both job and asset done via mark_metadata_jobs_done |

### Files changed

- `backend/metadata_store/metadata_queue.py` — `_mark_current_metadata_done` now calls `_update_asset_done`; added `_update_asset_done` helper; `mark_metadata_jobs_done` delegates to asset update
- `backend/metadata_store/metadata_persist.py` — updated docstring for `upsert_extracted_metadata`
- `backend/tests/test_metadata_store_coverage.py` — updated Tests 6 and 8 for Phase 3 behavior; added `mtime_ns` to ExtractedMetadata constructor in Test 6

---

## Test Results (current)

All 103 tests pass with no regressions:

```
$ backend/venv/bin/python -m pytest \
    backend/tests/test_catalog_recovery.py \
    backend/tests/test_catalog_status_ready_assets.py \
    backend/tests/test_indexer_staging.py \
    backend/tests/test_libraries_catalog.py \
    backend/tests/test_scan_worker.py \
    backend/tests/test_metadata_lifecycle.py \
    backend/tests/test_metadata_store_coverage.py \
    -v --timeout=60
======================= 103 passed in 21.34s ========================
```

---

---

## Phase 7 — Broader Integrity Checker ✅

### Files created

- `backend/integrity_checker.py` — `IntegrityChecker` class with 6 cross-table consistency checks
- `backend/tests/test_integrity_checker.py` — 13 tests covering all checks + lifecycle

### Files changed

- `backend/config.py` — added `INTEGRITY_CHECK_ENABLED`, `INTEGRITY_CHECK_INTERVAL_SECONDS`
- `backend/app.py` — wired `integrity_checker.start()` into startup, `integrity_checker.stop()` into shutdown
- `docs/plans/IMPLEMENTATION_STATUS.md` — Phase 7 marked complete

### Checks implemented

| # | Check | Description |
| --- | --- | --- |
| 1 | `asset_done_but_no_metadata` | Assets with `metadata_state='done'` but missing/stale `image_metadata` → demoted to pending + re-queued |
| 2 | `job_done_asset_not_done` | Done metadata jobs whose assets aren't `done` → stamped done |
| 3 | `job_active_no_asset` | Queued/running jobs with no corresponding asset row → failed |
| 4 | `derivative_ready_no_file` | Ready derivatives whose `cache_path` is missing from disk → re-queued |
| 5 | `derivative_job_done_not_ready` | Done derivative jobs whose deriviative status isn't `ready` → reconciled |
| 6 | `job_active_no_file` | Queued/running metadata jobs whose file is missing from disk → failed |

### Test Results (current)

All 116 tests pass with no regressions:

```
$ backend/venv/bin/python -m pytest \
    backend/tests/test_catalog_recovery.py \
    backend/tests/test_catalog_status_ready_assets.py \
    backend/tests/test_indexer_staging.py \
    backend/tests/test_libraries_catalog.py \
    backend/tests/test_scan_worker.py \
    backend/tests/test_metadata_lifecycle.py \
    backend/tests/test_metadata_store_coverage.py \
    backend/tests/test_integrity_checker.py \
    -v --timeout=60
======================= 116 passed in 19.23s ========================
```

---

## Next phase

**Phase 6 — Status/debug diagnostics and docs**

Add status/debug diagnostics and update documentation.
