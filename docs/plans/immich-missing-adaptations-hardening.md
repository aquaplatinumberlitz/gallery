# Backend Hardening Plan: Remaining Immich Adaptations

## Summary

Implement the remaining backend and contract hardening that Immich suggests, after the admin UI for generated files / library health has already been completed.

This plan does **not** redo the finished `Generated images`, `Live status`, `Problems`, or `Admin > Maintenance` shell UI work. It focuses on the missing backend truth sources and the last read-model/contract gaps:

1. remove remaining `mtime_ns` identity drift from browse/status/read paths,
2. add a persisted file-health report API behind the existing Maintenance page,
3. make integrity checks auditable instead of only repair-side effects,
4. add contract fixtures and schema checks so the frontend and backend stay aligned.

## Key Changes

### 1. Fix remaining read-model identity drift

Current bug boundary:

- lifecycle and repair logic already treat identity as `path + size + tolerant mtime_ns`,
- `backend/metadata_store/browse_store.py` still uses exact `im.mtime_ns = a.mtime_ns` joins in browse queries,
- that means browse/grid can miss metadata-backed dimensions while lifecycle/status considers the asset current.

Implementation:

- Add a small shared identity helper module under `backend/metadata_store/`.
- Centralize the tolerant match rules for:
  - asset <- image metadata
  - asset <- metadata job
  - job <- image metadata
- Update browse queries to use the shared tolerant predicate.
- Refactor only the duplicated SQL predicates that match this identity rule; do not change unrelated query semantics.

Acceptance:

- 500ns and 999ns deltas still match.
- 1000ns deltas do not match.
- legacy rows without `mtime_ns` still work through the seconds fallback.

### 2. Add a persisted file-health API for Maintenance

Current state:

- `backend/integrity_checker.py` already repairs mismatches,
- `frontend/src/components/admin/MaintenancePage.vue` already has `File issues`, `Check files`, and `Repair results`,
- but the backend has no durable report API yet, so the page still shows placeholders.

Implementation:

- Add a new router/module for maintenance health, instead of expanding `libraries.py` further.
- Add:
  - `GET /api/maintenance/file-health`
  - `POST /api/maintenance/file-health/check`
- Persist run summaries so the Maintenance page can show the latest result and history later.
- Keep the run summary small in v1:
  - issue counts
  - repair counts
  - timestamps
  - error text if the run failed

Recommended v1 model:

- one `integrity_check_runs` table,
- one latest-run response,
- no item-level report rows yet.

### 3. Make integrity checks auditable

Current state:

- the checker silently repairs or requeues rows,
- the Maintenance UI has no actual backend-backed history,
- there is no explicit schema/check command for the catalog DB.

Implementation:

- Extend `IntegrityChecker` with a method that returns a run summary and persists it.
- Keep the current repair behavior, but also record:
  - what was found,
  - what was repaired,
  - what was requeued,
  - what was failed,
  - what was unchanged.
- Add a lightweight schema-check helper/command for catalog DB requirements.
- Validate required tables/columns/indexes for the lifecycle path, including the new integrity run table.

### 4. Wire Maintenance page to real data

Current UI already exists, so the work here is wiring only:

- replace placeholder counts in `File issues`,
- enable `Run checks`,
- populate `Repair results`,
- show latest run time and empty states cleanly.

Constraints:

- keep user-facing labels simple,
- do not surface backend terms like `integrity` in primary copy,
- keep the page factual and auditable.

### 5. Add contract fixtures and tests

Backend:

- add schema/fixture coverage for the new maintenance file-health response,
- add tests for:
  - never-run state,
  - successful manual check,
  - failed run envelope,
  - schema compatibility.

Frontend:

- add contract tests for the new maintenance response,
- add composable tests for loading/success/error and cache invalidation,
- keep existing catalog status tests intact.

## Implementation Order

1. Add shared identity helper and fix browse-status drift.
2. Add integrity run persistence and backend maintenance API.
3. Wire `MaintenancePage.vue` to the real API.
4. Add contract fixtures/tests for the new maintenance response.
5. Add the lightweight schema-check helper/command and its tests.

## Test Plan

Backend:

```bash
pytest \
  backend/tests/test_catalog_status_mtime_tolerance.py \
  backend/tests/test_catalog_status_contract.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_maintenance_file_health_api.py \
  backend/tests/test_schema_check.py
```

Frontend:

```bash
cd frontend
pnpm test:unit -- src/contracts/__tests__/maintenanceFileHealthContract.test.ts
pnpm test:unit -- src/composables/admin/__tests__/useFileHealthQuery.test.ts
pnpm typecheck
```

## Assumptions

- The completed UI plan stays as-is.
- The new backend API is allowed to be synchronous-in-threadpool for v1.
- A summary-only persisted maintenance report is enough for now.
- SQLite-first implementation stays the source of truth; do not copy Immich’s Redis/BullMQ or PostgreSQL migration toolchain.

## Non-Goals

- Do not rework the finished generated-images UI.
- Do not add per-item maintenance report rows in v1.
- Do not introduce a distributed queue or microservice split.
- Do not rename the user-facing admin sections that already exist.
- Do not expose raw backend jargon in primary UI labels.

