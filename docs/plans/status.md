# Phase 2 — Browse Fix — Status

**Date:** 2026-06-25<br>
**Plan ref:** `docs/plans/immich-missing-adaptations-hardening.md`

---

## Summary

Phase 2 (Browse tolerant mtime_ns + ROW_NUMBER tie-break) is **complete**. All 25 browse tests pass.

---

## Files Modified

| File | Change |
|------|--------|
| `backend/metadata_store/browse_store.py` | 2 LEFT JOINs replaced with ROW_NUMBER tie-break subquery using `ABS(mtime_ns) < MTIME_NS_TOLERANCE` (1000ns). Closest-ns match wins; no seconds fallback per contract C. |
| `backend/tests/test_browse_api.py` | Updated `test_browse_stale_metadata_not_used` (gap changed 50→2100ns to be above tolerance). Added `test_browse_tolerant_mtime_picks_closest_metadata` (2 im rows, gap 400/500, asserts closest selected, no duplicates). |
| `backend/metadata_store/__init__.py` | Import sort fix (pre-existing). |
| `backend/tests/test_identity_helper.py` | Import sort fix (pre-existing). |

---

## Next Steps (Phase 3+)

Per the implementation order:
1. ✅ **Phase 1** — Identity helper
2. ✅ **Phase 2** — Browse fix (this)
3. **Persistence** — `integrity_check_runs` table, `maintenance_store.py`, extend `IntegrityChecker`
4. **Router** — `backend/maintenance.py` (GET + POST)
5. **Frontend** — keys, api, composable, MaintenancePage
6. **Schema-check** — `schema_check.py` whitelist
7. **Contract tests** — fixtures + schema + tests
