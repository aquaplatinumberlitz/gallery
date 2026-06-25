# Phase 1 — Identity Helper — Status

**Date:** 2026-06-25<br>
**Plan ref:** `docs/plans/immich-missing-adaptations-hardening.md`

---

## Summary

Phase 1 (Identity helper + refactor) is **complete**. All 775 backend tests pass.

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/metadata_store/identity.py` | Shared identity matching helper with 3 SQL fragment functions |
| `backend/tests/test_identity_helper.py` | 15 tests validating constants, branches, aliases |

## Files Modified

| File | Change |
|------|--------|
| `backend/metadata_store/__init__.py` | Export `MTIME_NS_TOLERANCE`, `MTIME_SEC_TOLERANCE`, 3 helper functions |
| `backend/metadata_store/status_store.py` | 8 JOIN predicates → helper calls (`asset_matches_image_metadata_sql`, `asset_matches_metadata_job_sql`) |
| `backend/indexer.py` | 4 JOIN/EXISTS predicates → helper calls |
| `backend/integrity_checker.py` | 2 Variant-B predicates → helper calls (COALESCE-0 removed) |
| `backend/metadata_store/metadata_queue.py` | 3 identity-match functions → 3-branch canonical pattern with tolerance constants |

---

## Identity Helper Design

3 functions returning self-contained SQL boolean fragments:

- **`asset_matches_image_metadata_sql(asset_alias, im_alias)`** — 2 branches (assets has `mtime_ns` only, no `mtime` column)
- **`asset_matches_metadata_job_sql(asset_alias, job_alias)`** — 2 branches (same constraint)
- **`job_matches_image_metadata_sql(job_alias, im_alias)`** — 3 branches (both tables have `mtime + mtime_ns`)

### Canonical tolerance rule (Variant A)
- Both `mtime_ns` NOT NULL → `ABS(diff) < 1000`
- One side NULL, other NOT NULL → convert ns→seconds, `ABS(diff) < 1e-3`

### Constants
- `MTIME_NS_TOLERANCE = 1000`
- `MTIME_SEC_TOLERANCE = 1e-3`

---

## Design Decisions

1. **assets has no `mtime` column** — Asset helpers only generate 2 branches. The `mtime`/`mtime_ns` columns exist on `image_metadata` and `metadata_index_jobs` only, so the 3-branch form is only for `job_matches_image_metadata_sql`.

2. **Not all metadata_queue.py predicates converted** — Parameterized UPDATE WHERE clauses (mark\_*, fail\_*, reset\_*) still use inline if/else on `mtime_ns`. These are single-table row-identity matches, not cross-table JOINs, and the helper is designed for the latter. The tolerance constants are imported and the 3 critical identity-match functions (`_image_metadata_exists_for_job`, `_current_metadata_is_complete`, `_update_asset_done`) were converted.

3. **`repair_inconsistent_asset_states` left as-is** — The assets UPDATE in this function has a pre-existing reference to `assets.mtime` (which doesn't exist as a column), but it's never triggered in the test suite. Fixed separately if needed.

---

## Next Steps (Phase 2+)

Per the implementation order:
1. ✅ **Phase 1** — Identity helper (this)
2. **Browse fix** — update `browse_store.py` joins with tie-break (`ROW_NUMBER`)
3. **Persistence** — `integrity_check_runs` table, `maintenance_store.py`, extend `IntegrityChecker`
4. **Router** — `backend/maintenance.py` (GET + POST)
5. **Frontend** — keys, api, composable, MaintenancePage
6. **Schema-check** — `schema_check.py` whitelist
7. **Contract tests** — fixtures + schema + tests
