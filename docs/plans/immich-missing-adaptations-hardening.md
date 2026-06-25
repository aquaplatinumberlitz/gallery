# Backend Hardening Plan: Remaining Immich Adaptations

## Summary

This is a follow-up hardening plan created after the Immich adaptation audit and
after the frontend library-health/generated-files plan was implemented. It
finishes the remaining backend and contract hardening that Immich suggests,
without reopening the completed admin UI work.

This plan does **not** redo the finished `Generated images`, `Live status`, `Problems`, or `Admin > Maintenance` shell UI work. It focuses on the missing backend truth sources and the last read-model/contract gaps:

1. remove remaining `mtime_ns` identity drift from browse/status/read paths,
2. add a persisted file-health report API behind the existing Maintenance page,
3. make integrity checks auditable instead of only repair-side effects,
4. add contract fixtures and schema checks so the frontend and backend stay aligned.

## Why This Plan Exists

Gallery has already adapted the useful local-first parts of Immich's lifecycle
model: durable metadata jobs, derivative jobs, readiness state, watcher/refresh
workers, status diagnostics, and admin surfaces for generated files and library
health. The frontend follow-up for `Generated images`, `Live status`,
`Problems`, and `Admin > Maintenance` is now done, so the remaining work is no
longer UI discovery or layout.

The reason this plan still exists is that the backend truth sources and
contracts are not fully closed. The metadata lifecycle refactor fixed the major
worker-lifecycle bugs by making SQLite the queue, materializing completion into
`assets.metadata_state`, adding recovery/repair, and aligning catalog status on
the tolerant identity rule. The codebase still shows narrower read-model,
reporting, and contract gaps that can make the UI show placeholders or disagree
with the lifecycle state.

| Cause | Current Gallery state | Why it matters | Plan response |
| --- | --- | --- | --- |
| Frontend health/generated-files UI is done | Admin pages show generated-image coverage and Maintenance placeholders | UI now exposes places where backend truth is missing | Add file-health API and wire Maintenance to real data |
| Metadata lifecycle uses tolerant identity | Status/indexer paths tolerate small `mtime_ns` drift | Browse can still disagree because it uses exact joins | Add shared identity helper and fix browse matching |
| Integrity checker mutates silently | Repairs happen but no persisted run summary exists | Admin cannot audit what was found or repaired | Add `integrity_check_runs` and response envelope |
| Contract guards exist for catalog status | New maintenance response has no schema/fixture contract | Frontend/backend drift can return | Add backend fixtures, JSON schema, and frontend contract tests |
| Schema compatibility is additive | No explicit lifecycle schema-check helper exists | Missing tables/indexes can become runtime bugs | Add schema-check helper and tests |

This plan deliberately extracts the local lesson from Immich rather than copying
Immich's infrastructure. Gallery stays SQLite-first and single-process; it does
not adopt Redis/BullMQ, PostgreSQL-specific migrations, a microservice split, or
distributed-worker assumptions.

## Already Done / Not Reopened Here

- The generated-images card, live-status/problems sections, and Maintenance
  shell UI are complete.
- `derivative_ready` remains an internal grid/lightbox loading and preload hint,
  not a visible admin status.
- User-facing labels stay simple: `Generated images`, `Live status`, `Problems`,
  `File issues`, `Check files`, and `Repair results`.
- This plan does not redesign admin UI and does not change the local
  SQLite-first architecture.

## Verified Current State (audit baseline)

These claims were checked against the codebase at the time of writing and are the
factual basis for every decision below. Re-audit before implementing if the tree
has moved.

- `backend/metadata_store/browse_store.py:236` and `:392` join `image_metadata`
  with the **exact** predicate `im.mtime_ns = a.mtime_ns AND im.size = a.size`.
- The tolerant predicate `ABS(im.mtime_ns - a.mtime_ns) < 1000 AND im.size = a.size`
  is already used in: `backend/metadata_store/status_store.py` (8 sites),
  `backend/indexer.py` (4 sites), `backend/integrity_checker.py` (2 sites),
  `backend/metadata_store/metadata_queue.py` (many sites).
- Two fallback variants exist in the wild:
  - Variant A (status/indexer, legacy-ns-aware): `im.mtime_ns IS NULL AND <a|im>_mtime_ns / 1e9 - im.mtime < 1e-3`.
  - Variant B (integrity_checker): `ABS(im.mtime_ns - COALESCE(a.mtime_ns, 0)) < 1000`
    (treats NULL asset mtime_ns as 0, no legacy seconds bridge).
- `backend/integrity_checker.py:IntegrityChecker.run_all_checks` returns
  `{check_name: int_count}` for **exactly 6** checks:
  1. `asset_done_but_no_metadata`
  2. `job_done_asset_not_done`
  3. `job_active_no_asset`
  4. `derivative_ready_no_file`
  5. `derivative_done_not_ready`
  6. `job_active_no_file`
  The checker mutates the catalog (UPDATE/INSERT) but persists nothing.
- `frontend/src/components/admin/MaintenancePage.vue` shows:
  - "File issues" with 5 listed rows all `—`,
  - "Check files" with a `disabled` "Run checks" button,
  - "Repair results" with 4 buckets all `—`,
  - literal "backend health report API not available yet".
- `backend/libraries.py` is the admin router: `APIRouter()` with **no prefix**,
  included plain in `backend/app.py:96`.
- No table `integrity_check_runs` exists. No `/maintenance` route. No
  `useFileHealth*` composable. No `queryKeys.maintenance*`.
- Contract-test convention: `frontend/src/contracts/__tests__/*.test.ts` read
  JSON schema/fixtures via `node:fs` + Ajv2020; backend uses
  `backend/tests/fixtures/` and pytest.
- `queryKeys` helper (`frontend/src/query/keys.ts`) is the canonical query-key
  factory (recently refactored away from raw magic strings).

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
- seconds fallback applies to status/indexer/integrity where already present;
  browse keeps the legacy NULL behavior via `COALESCE(a.width/a.height)`.

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

## Contracts / Decisions (binding — dev must not re-decide)

Tightly referenced by the audited sections above. This section is the source of
truth whenever the "Key Changes" section is ambiguous.

### A. Identity helper

- **New file:** `backend/metadata_store/identity.py`
- **Public API:**
  ```python
  def asset_matches_image_metadata_sql(*, asset_alias: str = "a", im_alias: str = "im") -> str
  def asset_matches_metadata_job_sql(*, asset_alias: str = "a", job_alias: str = "mj") -> str
  def job_matches_image_metadata_sql(*, job_alias: str = "mj", im_alias: str = "im") -> str
  ```
  Each returns a **SQL fragment string** (not a builder, not a query executor)
  that can be embedded as `LEFT JOIN ... ON <fragment>` or
  `WHERE EXISTS (SELECT 1 ... WHERE <fragment>)`. Each fragment is a self-contained
  boolean expression that references the aliases passed as parameters.
- **Canonical tolerance** = **Variant A only** (ns-tolerance `< 1000` plus the
  legacy seconds-bridge `a.mtime_ns/1e9 - im.mtime < 1e-3` when either side has
  `mtime_ns IS NULL`). The stateful COALESCE-0 (Variant B currently in
  `integrity_checker`) is **removed**; the helper defaults to "NULL does not
  match" unless the seconds-bridge applies. This unifies the semantics, and is
  paired with refactoring `integrity_checker.py` onto the helper.
- **Tolerance constants** must be exported from the helper
  (`MTIME_NS_TOLERANCE = 1000`, `MTIME_SEC_TOLERANCE = 1e-3`) so tests can import
  them — do not hardcode magic numbers in SQL.
- **NULL handling:** both sides `mtime_ns IS NULL` ⇒ **no match** unless the
  seconds-bridge applies. One side NULL plus the other with ns ⇒ goes through the
  seconds-bridge if the corresponding `*_mtime_seconds` column exists.

### B. Browse multi-row matching

- Once tolerance is relaxed, a single asset can match multiple `image_metadata`
  rows (exact plus ns-neighbors).
- **Tie-break is mandatory** in browse: the `JOIN` must pick exactly 1 im row per
  asset.
  - Implementation: use `ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY
    ABS(im.mtime_ns - a.mtime_ns) ASC, im.id ASC)` in a subquery and filter
    `rn = 1`, or an equivalent LATERAL-style LEFT JOIN (SQLite ≥3.35 supports
    window functions).
  - Do not let `COALESCE` width/height accept "any matching row".
- Tie-break order: smallest ns delta first, then smallest `im.id` (earlier-inserted
  row is more stable). The acceptance test must include a 2-row match case and
  assert that width/height come from the closest-ns row.

### C. Browse seconds-fallback scope

- `browse_store.py` currently has **no** seconds fallback (NULL = NULL is false ⇒
  dropped).
- Decision: **only relax the ns-tolerance**, do **not** add a seconds-bridge for
  browse in this plan. Rationale: browse is a hot read path; keeping NULL-width
  (COALESCE fallback to `assets.width/height`) matches current behavior and avoids
  bloating the helper.
- Therefore the acceptance line "legacy rows without `mtime_ns` still work through
  the seconds fallback" **applies only to** the status/indexer/integrity path —
  not to browse. Browse keeps: NULL mtime_ns on either side ⇒ im does not match ⇒
  width/height come from `assets.*` as before. Update the section 1 acceptance
  line to: "seconds fallback applies to status/indexer/integrity (already
  present); browse keeps the legacy NULL behavior via COALESCE assets.*".

### D. Mapping 6 checks ↔ UI rows

Binding map (do not change). Every number on the UI comes from a single run
summary, never recomputed.

"File issues" 5 rows — mapped from `run.issues.<key>`:

| UI label                     | run.issues key                 | Source `run_all_checks` key              |
|------------------------------|--------------------------------|------------------------------------------|
| Missing source files         | `missing_source_files`         | `job_active_no_file`                     |
| Generated image missing      | `generated_image_missing`      | `derivative_ready_no_file`               |
| Metadata mismatch            | `metadata_mismatch`            | `asset_done_but_no_metadata`             |
| Orphaned work item           | `orphaned_work_item`           | `job_active_no_asset`                    |
| Generated image job mismatch | `generated_image_job_mismatch` | `derivative_done_not_ready`              |

"Generated image job mismatch" refers only to **derivative** jobs (check #5
`derivative_done_not_ready`); `job_done_asset_not_done` (check #2, about metadata
jobs) is **not displayed** in v1 to preserve clarity (its repairs belong in
Repair results, not in the issue counts). If both need to be visible later, add a
new row — do not merge them.

"Repair results" 4 buckets — from `run.repairs.<key>`:

| UI label            | run.repairs key |
|---------------------|-----------------|
| Repaired            | `repaired`      |
| Requeued            | `requeued`      |
| Marked failed       | `failed`        |
| Skipped / unchanged | `unchanged`     |

- `repaired`  = count of rows UPDATEd to done/ready (check #2 + #5-positive).
- `requeued`  = count of rows set to `queued` with job rows (re)created (check #1 + #4).
- `failed`    = count of rows UPDATEd to `state='failed'` with error (check #3 + #6 + #5-negative).
- `unchanged` = `sum(issues) - repaired - requeued - failed` (computed), not a new
  column. Always ≥0; if negative due to a wrong map, raise in tests.

### E. POST/GET semantics

- **`POST /api/maintenance/file-health/check`** = **mutating, idempotent.** Runs
  the full `run_all_checks` (mutates the catalog just like the daemon does),
  persists 1 row into `integrity_check_runs`, and returns the just-created run
  summary. Two calls = two separate runs. Each run carries `id`, `started_at`,
  `finished_at`, `trigger = "manual" | "daemon"`.
- **`GET /api/maintenance/file-health`** = returns the **latest run**
  (max `finished_at`); it does not run anything. See point F for the envelope.
- **Concurrency:** `_DB_LOCK` already serializes; two overlapping POSTs run
  sequentially. No extra lock is needed. However, a POST while the daemon is
  mid-check is bad-feeling:
  - Fallback plan: add an `IntegrityChecker.is_running` flag (default False); if
    True, POST returns `409` with envelope
    `{ "run": null, "error": "check already running" }`. The daemon and the manual
    path share the same flag. Not mandatory, but recommended to avoid double
    repair on the same row.
- **Daemon persistence:** once the new method persists summaries, the daemon loop
  (`_run_loop`) must also persist runs with `trigger="daemon"`. GET-latest may
  return a daemon run — that's expected, not excluded.
- POST takes no body and no scope/filter in v1 → checks all libraries.

### F. Response envelope (never-run + success + error)

```jsonc
// 200 OK in all cases (including never-run and run-error)
{
  "run": {
    "id": 42,                       // int, NOT NULL when a run exists
    "trigger": "manual",            // "manual" | "daemon"
    "started_at": 1730000000.0,     // float epoch seconds
    "finished_at": 1730000005.0,    // float epoch seconds, NULL if running (does not happen in v1 GET)
    "status": "ok",                 // "ok" | "error"
    "error": null,                  // string when status = "error", short form
    "issues": { "missing_source_files": 0, ... }, // 5 keys per map D
    "repairs": { "repaired": 0, "requeued": 0, "failed": 0, "unchanged": 0 }
  }
}
// never-run:
{ "run": null }
// errored run:
{ "run": { "id": 5, "trigger": "manual", "started_at": ..., "finished_at": ..., "status": "error", "error": "boom", "issues": {5 keys 0}, "repairs": {4 keys 0} } }
```

- **HTTP status is always 200** for successful GET/POST (including errored runs).
  500 is reserved for the server itself crashing.
- Concurrent POST → `409` with `{ "run": null, "error": "check already running" }`
  (sync with `E`, `H`).
- `issues` has **exactly 5 keys** per map D, `repairs` **exactly 4 keys**. A missing
  key is a contract break and tests must fail.

### G. Persistence schema (`integrity_check_runs`)

DDL to add to `backend/metadata_store/_schema.py`:

```sql
CREATE TABLE IF NOT EXISTS integrity_check_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  trigger       TEXT NOT NULL CHECK (trigger IN ('manual', 'daemon')),
  started_at    REAL NOT NULL,
  finished_at   REAL,
  status        TEXT NOT NULL CHECK (status IN ('ok', 'error')),
  error         TEXT,
  issues_json   TEXT NOT NULL,   -- JSON object (5 keys)
  repairs_json  TEXT NOT NULL     -- JSON object (4 keys)
);
CREATE INDEX IF NOT EXISTS idx_integrity_check_runs_finished
  ON integrity_check_runs(finished_at DESC);
```

- **No per-item rows in v1.** Store issues/repairs as JSON TEXT (SQLite has no
  stable native JSON type across versions; encode in Python).
- "Latest run" = `ORDER BY finished_at DESC, id DESC LIMIT 1`.
- Migration: the table + index creation lives in `initialize_database()`
  (idempotent via `IF NOT EXISTS`), like the other tables. Do not use
  `_ensure_column` — this is a brand-new table.
- Persistence helpers: add `backend/metadata_store/maintenance_store.py` with
  `insert_run(conn, summary) -> run_id` and `get_latest_run(conn) -> row | None`.
  The router uses these two helpers.

### H. Router structure & prefix

- New file `backend/maintenance.py`. Router:
  ```python
  router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
  ```
  Include it in `backend/app.py` next to `libraries_router`.
- **v1 auth/rbac:** mirror the current admin router state (check whether
  `libraries.py` depends on `Request`/dependencies and copy exactly; if none,
  do not add new ones in this plan).
- Pydantic response model = types matching envelope F (export `FileHealthRun`,
  `FileHealthResponse`); map `issues`/`repairs` to **dict[str, int]** with a
  frozen key-set so Ajv/frontend get a stable schema. Do not expose a loose
  `dict[str, int]`.

### I. Schema-check whitelist

New file `backend/metadata_store/schema_check.py`. Public:

```python
def check_catalog_schema(conn) -> list[str]:  # returns list of issue strings, empty = ok
```

Whitelist (required for v1 — does not scan all of `_schema.py`, only the lifecycle
path):

Tables:
- `assets`, `image_metadata`, `metadata_index_jobs`, `asset_derivatives`,
  `derivative_jobs`, `libraries`, `library_import_paths`,
  `catalog_rebuild_entries`, **`integrity_check_runs`** (new).

Columns (only strictly lifecycle-required columns):
- `assets`: `id, library_id, path, parent_path, name, type, mtime_ns, size,
  metadata_state, deleted_at, offline, indexed_at`
- `image_metadata`: `path, mtime, mtime_ns, size, width, height`
- `metadata_index_jobs`: `path, mtime_ns, size, state, library_id, queued_at, finished_at, updated_at`
- `asset_derivatives`: `id, asset_id, kind, status, cache_path, byte_size, updated_at`
- `derivative_jobs`: `id, derivative_id, state, updated_at`

Indexes:
- `idx_metadata_index_jobs_claim`, `idx_metadata_index_jobs_library_state`,
  `idx_image_metadata_mtime_size`, `idx_integrity_check_runs_finished`.

v1 exposure: do not expose as a separate CLI; function + test only. Add a CLI
later if needed. A `GET /api/maintenance/schema-check` route may be added later —
**not in v1**.

### J. Frontend wiring

- `frontend/src/query/keys.ts`: add
  ```ts
  maintenanceRoot: () => ["maintenance"] as const,
  maintenanceFileHealth: () => ["maintenance", "file-health"] as const,
  ```
  All queries/mutations must use keys from here — no magic strings.
- `frontend/src/services/api.ts`: add
  `fetchFileHealth(): Promise<FileHealthResponse>` and
  `runFileHealthCheck(): Promise<FileHealthResponse>` (POST, no body).
- New file `frontend/src/composables/admin/useFileHealthQuery.ts`:
  - `useFileHealthQuery()` = `useQuery(queryKeys.maintenanceFileHealth(), fetchFileHealth, { staleTime: 60_000 })`.
  - `useFileHealthMutation()` = `useMutation({ mutationFn: runFileHealthCheck,
    onSuccess: () => queryClient.invalidateQueries({ queryKey:
    queryKeys.maintenanceFileHealth() }) })`.
  - Export types synchronized with envelope F.
- `MaintenancePage.vue`:
  - "File issues": iterate the 5 keys per map D; render `run.issues.<key>`; `<dd>`
    shows the number or `—` when `run === null`.
  - "Check files": remove `disabled`, wire to `useFileHealthMutation().mutateAsync()`;
    pending state disables the button + shows a spinner.
  - "Repair results": 4 buckets per map D, numbers from `run.repairs.<key>`;
    "Latest run" shows `finished_at` formatted
    (`new Date(seconds*1000).toLocaleString()`) or `—`.
  - never-run copy = "No run yet." (replace the "backend ... not available yet"
    line).
  - **Do not change** the "Generated files (all libraries)" and "Active jobs"
    sections.

### K. Contract fixtures location

- Backend schema/fixtures: `backend/tests/fixtures/file_health/`
  - `never_run.json` — `{"run": null}`
  - `success.json` — envelope with 5+4 keys, non-zero values.
  - `error.json` — `status:"error"`, `error:"boom"`, zero counts.
  - `schema_compat.json` — envelope with min/max values for boundary tests.
- FE contract test: `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`
  following the `catalogStatusContract.test.ts` convention (read JSON, use
  Ajv2020, validate types + key-sets). The envelope JSON schema document lives at
  `frontend/src/contracts/schemas/file-health-response.schema.json` (JSON Schema
  2020-12) — structure `$defs` similarly to the catalog schema doc.

## Implementation Order

1. **Identity helper** — `backend/metadata_store/identity.py` + tests; refactor
   `integrity_checker.py`, `status_store.py`, `indexer.py`, `metadata_queue.py`
   onto the helper (Variant A canonical). **Do not touch browse_store in this
   step** — it has its own ordering step below.
2. **Browse fix** — update the 2 browse queries (`browse_store.py:236, :392`) to
   use the helper + tie-break (point B). Update `test_warm_folder_listing.py` and
   `test_browse_api.py` for the 2-row match case.
3. **Persistence** — `maintenance_store.py`, `_schema.py` adds the
   `integrity_check_runs` table; extend `IntegrityChecker` with
   `run_and_persist(trigger) -> summary`; hook the daemon loop to use
   `trigger="daemon"`.
4. **Router** — `backend/maintenance.py` (`GET` + `POST`), include in `app.py`,
   envelope per F. Tests in `test_maintenance_file_health_api.py`.
5. **Frontend wiring** — `keys.ts`, `api.ts`, composable, `MaintenancePage.vue`.
6. **Schema-check helper** — `backend/metadata_store/schema_check.py` + test
   `test_schema_check.py` (whitelist I).
7. **Contract tests** — fixtures + schema doc + 2 FE test files. Verify the suite
   passes.

## File manifest

Backend (new/edited):

- NEW  `backend/metadata_store/identity.py`
- NEW  `backend/metadata_store/maintenance_store.py`
- NEW  `backend/metadata_store/schema_check.py`
- NEW  `backend/maintenance.py`
- NEW  `backend/tests/test_identity_helper.py`
- NEW  `backend/tests/test_maintenance_file_health_api.py`
- NEW  `backend/tests/test_schema_check.py`
- NEW  `backend/tests/fixtures/file_health/{never_run,success,error,schema_compat}.json`
- EDIT `backend/metadata_store/_schema.py`               (table + index)
- EDIT `backend/metadata_store/browse_store.py`           (2 joins)
- EDIT `backend/metadata_store/status_store.py`           (8 predicates onto helper)
- EDIT `backend/metadata_store/metadata_queue.py`         (predicates onto helper)
- EDIT `backend/indexer.py`                               (predicates onto helper)
- EDIT `backend/integrity_checker.py`                     (predicates + persist summary)
- EDIT `backend/app.py`                                   (include maintenance router)
- EDIT `backend/tests/test_integrity_checker.py`          (assert persisted summary)
- EDIT `backend/tests/test_warm_folder_listing.py` + `test_browse_api.py` (multi-row tie-break)

Frontend (new/edited):

- NEW  `frontend/src/composables/admin/useFileHealthQuery.ts`
- NEW  `frontend/src/composables/admin/__tests__/useFileHealthQuery.test.ts`
- NEW  `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`
- NEW  `frontend/src/contracts/schemas/file-health-response.schema.json`
- EDIT `frontend/src/query/keys.ts`                       (2 entries)
- EDIT `frontend/src/services/api.ts`                     (2 fn + types)
- EDIT `frontend/src/components/admin/MaintenancePage.vue` (wire)
- EDIT `frontend/package.json` / `vitest.config`          (only if a new include path is needed)

## Test Plan

Backend (`pytest`, from repo root):

```bash
pytest \
  backend/tests/test_identity_helper.py \
  backend/tests/test_catalog_status_mtime_tolerance.py \
  backend/tests/test_catalog_status_contract.py \
  backend/tests/test_integrity_checker.py \
  backend/tests/test_maintenance_file_health_api.py \
  backend/tests/test_schema_check.py \
  backend/tests/test_metadata_lifecycle.py \
  backend/tests/test_warm_folder_listing.py
```

Frontend:

```bash
cd frontend
pnpm test:unit -- src/contracts/__tests__/maintenanceFileHealthContract.test.ts
pnpm test:unit -- src/composables/admin/__tests__/useFileHealthQuery.test.ts
pnpm typecheck
```

Smoke (after editing):

```bash
python start.py &  # run the app
curl -s localhost:8000/api/maintenance/file-health | jq       # { "run": null } the first time
curl -sX POST localhost:8000/api/maintenance/file-health/check | jq
curl -s localhost:8000/api/maintenance/file-health | jq       # see the run just POSTed
```

## Assumptions

- The completed UI plan stays as-is (wire data only, no redesign).
- The new backend API is allowed to be synchronous-in-threadpool for v1 (POST
  blocks for a few seconds on a modest catalog; report a follow-up if it is slow).
- A summary-only persisted maintenance report is enough for now (no per-item rows).
- SQLite-first implementation stays the source of truth; **do not** copy Immich's
  Redis/BullMQ or PostgreSQL migration toolchain.
- Helper canonicalization (Variant A) may require changing legacy semantics
  (`integrity_checker` currently uses COALESCE-0). Acceptance in
  `test_integrity_checker.py` must be re-audited; if existing tests build fixtures
  with NULL `mtime_ns`, switch them to the canonical seconds-bridge fixture.

## Non-Goals

- Do not rework the finished generated-images UI.
- Do not add per-item maintenance report rows in v1.
- Do not introduce a distributed queue or microservice split.
- Do not rename the user-facing admin sections that already exist.
- Do not expose raw backend jargon (`integrity`, `mtime_ns`, `metadata_index_jobs`)
  in primary UI labels.
- Do not add new auth/rbac middleware if `libraries.py` has none; only mirror.
- Do not add a CLI command in v1; schema-check is a function + test only.
- Do not add `GET /api/maintenance/schema-check` in v1.
- Do not add a seconds-bridge for browse (decision C).
- Do not expose `job_done_asset_not_done` (check #2) in "File issues" v1 (it
  stays hidden in Repair results).
