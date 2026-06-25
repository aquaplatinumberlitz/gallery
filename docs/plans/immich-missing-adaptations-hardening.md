# Backend Hardening Plan: Remaining Immich Adaptations

## Summary

Implement the remaining backend and contract hardening that Immich suggests, after the admin UI for generated files / library health has already been completed.

This plan does **not** redo the finished `Generated images`, `Live status`, `Problems`, or `Admin > Maintenance` shell UI work. It focuses on the missing backend truth sources and the last read-model/contract gaps:

1. remove remaining `mtime_ns` identity drift from browse/status/read paths,
2. add a persisted file-health report API behind the existing Maintenance page,
3. make integrity checks auditable instead of only repair-side effects,
4. add contract fixtures and schema checks so the frontend and backend stay aligned.

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

## Contracts / Decisions (chốt cứng, dev không được tự пере quyết)

Tham chiếu chặt vào section đã audit. Mục này là nguồn sự thật khi section
"Key Changes" mơ hồ.

### A. Identity helper

- **File mới:** `backend/metadata_store/identity.py`
- **Public API:**
  ```python
  def asset_matches_image_metadata_sql(*, asset_alias: str = "a", im_alias: str = "im") -> str
  def asset_matches_metadata_job_sql(*, asset_alias: str = "a", job_alias: str = "mj") -> str
  def job_matches_image_metadata_sql(*, job_alias: str = "mj", im_alias: str = "im") -> str
  ```
  Trả về **SQL fragment string** (không phải builder, không query executor), dạng
  có thể nhúng vào `LEFT JOIN ... ON <fragment>` hoặc `WHERE EXISTS (SELECT 1 ... WHERE <fragment>)`.
  Mỗi fragment phải là một biểu thức boolean khép kín, tham chiếu alias theo tham số.
- **Canonical tolerance** = duy nhất **Variant A** (ns-tolerance `< 1000` + legacy
  seconds-bridge `a.mtime_ns/1e9 - im.mtime < 1e-3` khi một bên `mtime_ns IS NULL`).
  Stateful COALESCE-0 (Variant B trong `integrity_checker`) được **loại bỏ**; helper
  mặc định NULL không khớp hostname trừ khi có seconds-bridge. Đây là quyết định
  semantic thống nhất, kèm theo việc refactor `integrity_checker.py` sang helper.
- **Tolerance constants** phải được export từ helper (`MTIME_NS_TOLERANCE = 1000`,
  `MTIME_SEC_TOLERANCE = 1e-3`) để tests có thể import — không hardcode số ảo trong SQL.
- **Host NULL**: cả hai bên `mtime_ns IS NULL` ⇒ **không match** trừ seconds-bridge.
  Một bên NULL + bên kia có ns ⇒ đi qua seconds-bridge nếu `*mtime_seconds` tồn tại.

### B. Browse multi-row matching

- Khi nới tolerance, một asset có thể khớp nhiều `image_metadata` row (exact + lân cận ns).
- **Bắt buộc tie-break** trong browse: `JOIN` phải chọn duy nhất 1 row im cho mỗi asset.
  - Cách thực thi: dùng `ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY
    ABS(im.mtime_ns - a.mtime_ns) ASC, im.id ASC)` subquery rồi filter `rn = 1`,
    hoặc LEFT JOIN theo kiểu LATERAL tương đương (SQLite ≤3.35+ hỗ trợ window funcs).
  - Không được để COALESCE width/height nhận "hàng nào cũng được".
- Thứ tự tie-break: độ lệch ns nhỏ nhất trước, rồi `im.id` nhỏ hơn (row nhập trước
  ổn định hơn). Acceptance test phải có case 2-row match và xác nhận width/height đến
  từ row lệch nhỏ nhất.

### C. Browse seconds-fallback scope

- `browse_store.py` hiện **không** có seconds fallback (NULL=NULL false ⇒ drop).
- Quyết định **CHỈ nới ns-tolerance**, **KHÔNG** thêm seconds-bridge cho browse
  trong plan này. Lý do: browse là read path nóng; chấp nhận NULL-width (`COALESCE`
  fallback vô `assets.width/height`) đúng hành vi cũ, và tránh phình helper.
- Do đó acceptance "legacy rows without `mtime_ns` still work through the seconds
  fallback" **chỉ áp dụng cho** status/indexer/integrity path — không cho browse.
  Browse giữ: NULL mtime_ns ở một bên ⇒ im không khớp ⇒ width/height lấy từ
  `assets.*` như cũ. Cần cập nhật lại dòng acceptance trong section 1 thành
  "seconds fallback áp dụng cho status/indexer/integrity (đã có); browse giữ
  hành vi NULL cũ qua COALESCE assets.*".

### D. Mapping 6 check ↔ UI rows

Chốt map cứng (không đổi). Mọi số trên UI lấy từ 1 run summary, không compute lại.

"File issues" 5 dòng — ánh xạ từ `run.issues.<key>`:

| UI label                  | run.issues key            | Từ check `run_all_checks` key        |
|---------------------------|---------------------------|--------------------------------------|
| Missing source files      | `missing_source_files`    | `job_active_no_file`                 |
| Generated image missing   | `generated_image_missing` | `derivative_ready_no_file`           |
| Metadata mismatch         | `metadata_mismatch`       | `asset_done_but_no_metadata`         |
| Orphaned work item        | `orphaned_work_item`      | `job_active_no_asset`                |
| Generated image job mismatch | `generated_image_job_mismatch` | `derivative_done_not_ready` _hoặc_ `job_done_asset_not_done` |

"Generated image job mismatch" là chỉ **derivative** jobs (check #5
`derivative_done_not_ready`); `job_done_asset_not_done` (check #2, về metadata
job) **không hiển thị** trên UI v1 để bảo chỉn giữa sự rõ ràng (nhức nhối sửa
trong Repair results, không nằm thống kê issue). Nếu cả 2 sau này cần thấy, thêm
$row mới, không tự ghép.

"Repair results" 4 bucket — lấy từ `run.repairs.<key>`:

| UI label              | run.repairs key |
|-----------------------|-----------------|
| Repaired              | `repaired`      |
| Requeued              | `requeued`      |
| Marked failed         | `failed`        |
| Skipped / unchanged   | `unchanged`     |

- `repaired` = số row đã UPDATE thành done/ready (check #2 + #5-positive).
- `requeued` = số row đã đưa về `queued` và (re)create job row (check #1 + #4).
- `failed` = số row đã UPDATE state='failed' với error (check #3 + #6 + #5-negative).
- `unchanged` = `sum(issues) - repaired - requeued - failed` (computed), không
  phải cột mới. Luôn ≥0; nếu âm do đoán sai map,raise trong tests.

### E. POST/GET semantics

- **`POST /api/maintenance/file-health/check`** = **mutating, idempotent.** Chạy
  toàn bộ `run_all_checks` (sửa catalog như daemon vẫn làm), persist 1 row vào
  `integrity_check_runs`, trả về run summary vừa tạo. Gọi 2 lần = 2 run riêng.
  Mỗi run mang `id`, `started_at`, `finished_at`, `trigger = "manual" | "daemon"`.
- **`GET /api/maintenance/file-health`** = trả về **latest run** (max
  `finished_at`), không chạy gì. Response envelope (xem điểm F).
- **Concurrency:** `_DB_LOCK` đã serialize; 2 POST chồng nhau sẽ chạy nối tiếp.
  Không cần thêm lock. Nhưng POST chạy khi daemon đang giữa chừng bad-feeling:
  - Hậu cần: dùng flag `IntegrityChecker.is_running` (thêm, mặc định False); nếu
    True, POST trả `409` với envelope `{ "run": null, "error": "check already running" }`.
    Daemon và manual dùng cùng flag. Không bắt buộc, nhưng khuyến nghị để tránh
    double repair lên cùng row.
- **Daemon persistence:** khi method mới persist summary, daemon loop
  (`_run_loop`) cũng phải persist run `trigger="daemon"`. GET-latest có thể là
  daemon run. Đúng ý, không loại trừ.
- POST không nhận body. Không nhận scope/filter v1 → kiểm toàn bộ thư viện.

### F. Response envelope (never-run + success + error)

```jsonc
// 200 OK, mọi trường hợp (bao gồm never-run và run-error)
{
  "run": {
    "id": 42,                       // int, NOT NULL khi có run
    "trigger": "manual",            // "manual" | "daemon"
    "started_at": 1730000000.0,     // float epoch seconds
    "finished_at": 1730000005.0,    // float epoch seconds, NULL nếu đang chạy (không xảy ra v1 GET)
    "status": "ok",                 // "ok" | "error"
    "error": null,                  // string khi status = "error", dạng ngắn
    "issues": { "missing_source_files": 0, ... }, // 5 keys theo map D
    "repairs": { "repaired": 0, "requeued": 0, "failed": 0, "unchanged": 0 }
  }
}
// never-run:
{ "run": null }
// run lỗi:
{ "run": { "id": 5, "trigger": "manual", "started_at": ..., "finished_at": ..., "status": "error", "error": "boom", "issues": {5 keys 0}, "repairs": {4 keys 0} } }
```

- **HTTP status luôn 200** ở GET/POST thành công (kể cả run lỗi). 500 chỉ khi
  server bản thân crash.
- POST đang chạy (concurrent) → `409` với `{ "run": null, "error": "check already running" }`
  (sync `E`, `H`).
- `issues` có **đúng 5 keys** theo map D, `repairs` **đúng 4 keys**. Missing key
  = contract break, tests phải fail.

### G. Persistence schema (`integrity_check_runs`)

DDL thêm vào `backend/metadata_store/_schema.py`:

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

- **No per-item rows v1.** Lưu issues/repairs dưới dạng JSON TEXT (SQLite không có
  JSON type native ổn định khớp mọi version; encode trong Python).
- "Latest run" = `ORDER BY finished_at DESC, id DESC LIMIT 1`.
- Migration: tạo bảng + index nằm trong `initialize_database()` (idempotent qua
  `IF NOT EXISTS`), giống các bảng khác. `_ensure_column` không dùng — bảng mới.
- Helper persistence: thêm `backend/metadata_store/maintenance_store.py` với
  `insert_run(conn, summary) -> run_id`, `get_latest_run(conn) -> row | None`.
  Router dùng 2 helper này.

### H. Router structure & prefix

- `backend/maintenance.py` mới. Router:
  ```python
  router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
  ```
  Include vào `backend/app.py` cạnh `libraries_router`.
- **V1 auth/rbac**: kế thừa trạng thái router admin hiện tại (xem `libraries.py`
  có phụ thuộc `Request`/dependency gì → mirror y hệt; nếu không có, không thêm
  mới trong plan này).
- Pydantic response model = type có cấu trúc như envelope F (export `FileHealthRun`,
  `FileHealthResponse`); các `issues`/`repairs` map thành **dict[str, int]** có freeze key-set để Ajv/frontend có schema ổn định. Không giải `dict[str,int]` thoải mái.

### I. Schema-check whitelist

`backend/metadata_store/schema_check.py` (mới). Public:

```python
def check_catalog_schema(conn) -> list[str]:  # trả về danh sách issue strings, rỗng = ok
```

Whitelist (bắt buộc v1 — chưa quét toàn bộ `_schema.py`, chỉ lifecycle path):

Tables:
- `assets`, `image_metadata`, `metadata_index_jobs`, `asset_derivatives`,
  `derivative_jobs`, `libraries`, `library_import_paths`,
  `catalog_rebuild_entries`, **`integrity_check_runs`** (mới).

Columns (chỉ cột lifecycle nghiêm ngặt):
- `assets`: `id, library_id, path, parent_path, name, type, mtime_ns, size,
  metadata_state, deleted_at, offline, indexed_at`
- `image_metadata`: `path, mtime, mtime_ns, size, width, height`
- `metadata_index_jobs`: `path, mtime_ns, size, state, library_id, queued_at, finished_at, updated_at`
- `asset_derivatives`: `id, asset_id, kind, status, cache_path, byte_size, updated_at`
- `derivative_jobs`: `id, derivative_id, state, updated_at`

Indexes:
- `idx_metadata_index_jobs_claim`, `idx_metadata_index_jobs_library_state`,
  `idx_image_metadata_mtime_size`, `idx_integrity_check_runs_finished`.

Command exposure v1: không expose như CLI riêng; chỉ function + test. Nếu sau cần
CLI, thêm sau. Router có thể thêm `GET /api/maintenance/schema-check` sau này,
không **v1**.

### J. Frontend wiring

- `frontend/src/query/keys.ts`: thêm
  ```ts
  maintenanceRoot: () => ["maintenance"] as const,
  maintenanceFileHealth: () => ["maintenance", "file-health"] as const,
  ```
  Tất cả query/mutation dùng key từ đây — không magic string.
- `frontend/src/services/api.ts`: thêm
  `fetchFileHealth(): Promise<FileHealthResponse>` và
  `runFileHealthCheck(): Promise<FileHealthResponse>` (POST, không body).
- `frontend/src/composables/admin/useFileHealthQuery.ts` (mới):
  - `useFileHealthQuery()` = `useQuery(queryKeys.maintenanceFileHealth(), fetchFileHealth, { staleTime: 60_000 })`.
  - `useFileHealthMutation()` = `useMutation({ mutationFn: runFileHealthCheck,
    onSuccess: () => queryClient.invalidateQueries({ queryKey:
    queryKeys.maintenanceFileHealth() }) })`.
  - Export types đồng bộ với envelope F.
- `MaintenancePage.vue`:
  - "File issues": lặp 5 key theo map D; `run.issues.<key>`; `<dd>` hiện số hoặc
    `—` khi `run === null`.
  - "Check files": bỏ `disabled`, gắn `useFileHealthMutation().mutateAsync()`;
    pending state disable button + spinner.
  - "Repair results": 4 bucket theo map D, số từ `run.repairs.<key>`; "Latest
    run" hiện `finished_at` format (`new Date(seconds*1000).toLocaleString()`) hoặc `—`.
  - never-run copy = "No run yet." (xóa câu "backend ... not available yet").
  - **Không đổi** section "Generated files (all libraries)" và "Active jobs".

### K. Contract fixtures location

- Backend schema/fixture: `backend/tests/fixtures/file_health/`
  - `never_run.json` — `{"run": null}`
  - `success.json` — envelope với 5+4 keys có giá trị khác 0.
  - `error.json` — `status:"error"`, `error:"boom"`, counts 0.
  - `schema_compat.json` — envelope min/max value cho boundary tests.
- FE contract test: `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`
  theo chuẩn `catalogStatusContract.test.ts` (read JSON, Ajv2020, validate types +
  key-sets). Schema document JSON cho envelope đặt tại
  `frontend/src/contracts/schemas/file-health-response.schema.json` (AxV2020) —
  đặt cấu trúc `$defs` tương tự schema doc catalog.

## Implementation Order

1. **identity helper** — `backend/metadata_store/identity.py` + tests; refactor
   `integrity_checker.py`, `status_store.py`, `indexer.py`, `metadata_queue.py`
   sang helper (Variant A canonical). **Không đụng browseStore v1 order này.**
2. **browse fix** — update 2 browse queries (`browse_store.py:236, :392`) dùng
   helper + tie-break (point B). Update test `test_warm_folder_listing.py` +
   `test_browse_api.py` cho 2-row match case.
3. **persistence** — `maintenance_store.py`, `_schema.py` thêm bảng `integrity_check_runs`;
   extend `IntegrityChecker` với `run_and_persist(trigger) -> summary`; hook daemon
   loop dùng `trigger="daemon"`.
4. **router** — `backend/maintenance.py` (`GET` + `POST`), include trong
   `app.py`, Quyết envelope F. tests `test_maintenance_file_health_api.py`.
5. **frontend wiring** — keys.ts, api.ts, composable, MaintenancePage.vue.
6. **schema-check helper** — `backend/metadata_store/schema_check.py` + test
   `test_schema_check.py` (whitelist I).
7. **contract tests** — fixtures + schema doc + 2 FE test files. Verify suite pass.

## File manifest

Backend tạo/sửa:

- NEW  `backend/metadata_store/identity.py`
- NEW  `backend/metadata_store/maintenance_store.py`
- NEW  `backend/metadata_store/schema_check.py`
- NEW  `backend/maintenance.py`
- NEW  `backend/tests/test_identity_helper.py`
- NEW  `backend/tests/test_maintenance_file_health_api.py`
- NEW  `backend/tests/test_schema_check.py`
- NEW  `backend/tests/fixtures/file_health/{never_run,success,error,schema_compat}.json`
- EDIT `backend/metadata_store/_schema.py`              (bảng + index)
- EDIT `backend/metadata_store/browse_store.py`          (2 joins)
- EDIT `backend/metadata_store/status_store.py`          (8 predicates sang helper)
- EDIT `backend/metadata_store/metadata_queue.py`        (predicates sang helper)
- EDIT `backend/indexer.py`                              (predicates sang helper)
- EDIT `backend/integrity_checker.py`                    (predicates + persist summary)
- EDIT `backend/app.py`                                    (include maintenance router)
- EDIT `backend/tests/test_integrity_checker.py`          (assert persisted summary)
- EDIT `backend/tests/test_warm_folder_listing.py` + `test_browse_api.py` (multi-row tie-break)

Frontend tạo/sửa:

- NEW  `frontend/src/composables/admin/useFileHealthQuery.ts`
- NEW  `frontend/src/composables/admin/__tests__/useFileHealthQuery.test.ts`
- NEW  `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`
- NEW  `frontend/src/contracts/schemas/file-health-response.schema.json`
- EDIT `frontend/src/query/keys.ts`                       (2 entries)
- EDIT `frontend/src/services/api.ts`                     (2 fn + types)
- EDIT `frontend/src/components/admin/MaintenancePage.vue` (wire)
- EDIT `frontend/package.json` / `vitest.config`          (chỉ nếu cần mới include path)

## Test Plan

Backend (`pytest`, từ repo root):

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

Smoke (sửa后再 cciar):

```bash
python start.py &  # chạy app
curl -s localhost:8000/api/maintenance/file-health | jq       # { "run": null } lần đầu
curl -sX POST localhost:8000/api/maintenance/file-health/check | jq
curl -s localhost:8000/api/maintenance/file-health | jq       # thấy run vừa POST
```

## Assumptions

- The completed UI plan stays as-is (chỉ wire data, không redesign).
- The new backend API is allowed to be synchronous-in-threadpool for v1 (POST
  chặn ≤ vài giây trên catalog vừa; nếu chậm, báo sau).
- A summary-only persisted maintenance report is enough for now (no per-item rows).
- SQLite-first implementation stays the source of truth; **không** copy Immich’s
  Redis/BullMQ or PostgreSQL migration toolchain.
- Helper canonicalization (Variant A) có thể nécess sửa semantics cũ (
  `integrity_checker` đang COALESCE-0). Acceptance trong `test_integrity_checker.py`
  phải được rà lại; nếu test cũ build fixture với NULL mtime_ns, chuyển sang
  seconds-bridge fixture chuẩn.

## Non-Goals

- Do not rework the finished generated-images UI.
- Do not add per-item maintenance report rows in v1.
- Do not introduce a distributed queue or microservice split.
- Do not rename the user-facing admin sections that already exist.
- Do not expose raw backend jargon (`integrity`, `mtime_ns`, `metadata_index_jobs`)
  in primary UI labels.
- Do not add auth/rbac middleware mới nếu `libraries.py` chưa có; chỉ mirror.
- Do not add CLI command v1; schema-check chỉ là function + test.
- Do not add `GET /api/maintenance/schema-check` v1.
- Do not add seconds-bridge cho browse (quyết định C).
- Do not expose `job_done_asset_not_done` (check #2) trên "File issues" v1 (chỉ
  Repair results ẩn).