# Phase 0A — Characterization Tests Implementation Status

Status: **Complete** ✅ (2026-06-25)
Target: D full clean — `metadata_index_jobs` is the durable runtime queue; metadata worker claims jobs directly from SQLite.
Plan: `docs/plans/METADATA_LIFECYCLE_D_FULL_REFACTOR_PLAN.md`

## Summary

Phase 0A (characterization tests that reproduce lifecycle gaps using existing API) is implemented and passing. All 6 tests capture the current buggy behavior and document the expected invariants for future phases.

## Tests implemented

| Test | File | What it characterizes | Status |
| --- | --- | --- | --- |
| **Test 1** | `backend/tests/test_scan_worker.py` (`test_rebuild_schedules_db_jobs_but_not_runtime_dispatch`) | Bug 1: `execute_rebuild_job` creates `metadata_index_jobs` rows in SQLite but `_job_queue` stays empty — metadata work is stranded | ✅ |
| **Test 2** | `backend/tests/test_indexer_staging.py` (`test_scan_path_calls_enqueue_metadata_jobs_but_rebuild_does_not`) | Bug 1 divergence: scan path calls `_enqueue_metadata_jobs_from_result`, rebuild path does not | ✅ |
| **Test 6** | `backend/tests/test_metadata_store_coverage.py` (`test_shortcut_marks_job_done_but_not_asset`) | Bug 2: "already current" shortcut marks `metadata_index_jobs.state='done'` but leaves `assets.metadata_state` unchanged | ✅ |
| **Test 7** | `backend/tests/test_catalog_status_ready_assets.py` (`test_ready_assets_requires_both_asset_done_and_current_metadata`) | API invariant: `ready_assets` requires both `assets.metadata_state='done'` AND current `image_metadata`; job table alone does not count | ✅ |
| **Test 8** | `backend/tests/test_metadata_store_coverage.py` (`test_mark_metadata_jobs_done_has_no_stale_guard`) | `mark_metadata_jobs_done` has no DB-side stale guard — marks old job done even after file change | ✅ |
| **Test 14** | `backend/tests/test_indexer_staging.py` (`test_queue_metadata_index_paths_is_idempotent`) | `queue_metadata_index_paths` coalesces duplicate calls — idempotency works | ✅ |

## Test execution

```
$ backend/venv/bin/python -m pytest \
    backend/tests/test_scan_worker.py \
    backend/tests/test_indexer_staging.py::test_scan_path_calls_enqueue_metadata_jobs_but_rebuild_does_not \
    backend/tests/test_indexer_staging.py::test_queue_metadata_index_paths_is_idempotent \
    backend/tests/test_metadata_store_coverage.py::test_shortcut_marks_job_done_but_not_asset \
    backend/tests/test_metadata_store_coverage.py::test_mark_metadata_jobs_done_has_no_stale_guard \
    backend/tests/test_catalog_status_ready_assets.py::test_ready_assets_requires_both_asset_done_and_current_metadata \
    -v --timeout=60

======================== 6 passed in 1.83s =========================
```

## Files changed

| File | Action |
| --- | --- |
| `backend/tests/test_scan_worker.py` | **New** — Test 1 |
| `backend/tests/test_indexer_staging.py` | **Modified** — added Tests 2, 14 |
| `backend/tests/test_metadata_store_coverage.py` | **Modified** — added Tests 6, 8 |
| `backend/tests/test_catalog_status_ready_assets.py` | **Modified** — added Test 7 |
| `docs/testing/TEST_CATALOG.md` | **Modified** — appended new test rows |
| `docs/plans/PHASE_0A_STATUS.md` | **New** — this file |

## Next phase

**Phase 0B** (contract tests for DB-claim worker) can begin after Phase 1 provides `claim_next_metadata_job`, `MetadataLifecycleWorker`, and the schema migration (`library_id`, `priority`).

## Remaining known issues fixed in plan

All 6 pre-implementation audit issues resolved before Phase 0A:
1. ✅ Migration uses `queued_at`, not `created_at`
2. ✅ No `id` auto-increment in Phase 1; keep `path TEXT PK`
3. ✅ Path-centric model with `library_id` as diagnostic only
4. ✅ Mutual exclusion rule for old/new worker (Phase 2 disables old worker)
5. ✅ `mtime_ns` vs `mtime` normalisation with REAL-vs-INTEGER tolerance (1000 ns)
6. ✅ Transitional bridge wording consistent (no real work pushed to `_job_queue` after Phase 2)
