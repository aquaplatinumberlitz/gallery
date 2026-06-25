# Phase 3 — Persistence — Status

**Date:** 2026-06-25<br>
**Plan ref:** `docs/plans/immich-missing-adaptations-hardening.md`

---

## Summary

Phase 3 (persist integrity check runs via `integrity_check_runs` table) is **complete**. All 25 integrity checker tests pass; 69 tests pass across all affected modules.

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/metadata_store/maintenance_store.py` | `insert_run(conn, summary)` and `get_latest_run(conn)` — persists and retrieves integrity check run summaries. Issues/repairs stored as JSON TEXT. |

## Files Modified

| File | Change |
|------|--------|
| `backend/metadata_store/_schema.py` | Added `integrity_check_runs` table (id, trigger, started_at, finished_at, status, error, issues_json, repairs_json) + `idx_integrity_check_runs_finished` index in `_ensure_catalog_schema()`. |
| `backend/integrity_checker.py` | Added `is_running` flag. Added `run_and_persist(trigger)` — calls `run_all_checks()`, maps results to issues/repairs dicts, persists via `insert_run()`, handles exceptions. Updated `_run_loop` to call `run_and_persist(trigger="daemon")`. |
| `backend/tests/test_integrity_checker.py` | Added `TestRunAndPersist` with 5 tests: persist shape, error recording, empty DB, latest-run ordering, and `is_running` flag lifecycle. |

---

## Design Notes

- **Issue key mapping** (Contract D): `run_all_checks` keys → UI-friendly issue keys. `unchanged` is computed as `sum(issues) - repaired - requeued - failed`.
- **Daemon persistence**: daemon loop now persists every tick with `trigger="daemon"`. GET-latest may return either a manual or daemon run.
- **Concurrency**: `is_running` flag exists but not yet exposed via POST (Phase 4 will add 409 handling).

---

## Next Steps (Phase 4+)

1. ✅ **Phase 1** — Identity helper
2. ✅ **Phase 2** — Browse fix
3. ✅ **Phase 3** — Persistence (this)
4. **Router** — `backend/maintenance.py` (GET + POST), include in `app.py`
5. **Frontend** — keys, api, composable, MaintenancePage
6. **Schema-check** — `schema_check.py` whitelist
7. **Contract tests** — fixtures + schema + tests
