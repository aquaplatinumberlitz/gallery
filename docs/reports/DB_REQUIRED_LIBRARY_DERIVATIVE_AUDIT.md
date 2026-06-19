# DB-required, library, and derivative audit

Date: 2026-06-19

Scope: audit of the DB-required/library/asset-catalog/derivative changes introduced across the Phase 0-4 commit set, plus follow-up findings from a second GPT review.

## Executive summary

The code compiles, lint passes, backend tests pass, frontend lint/test/build pass. The remaining risks are logic and product-semantics issues, mostly around one theme:

> The database is being treated as authoritative, but the code still has paths where the database can be implicit, stale, incomplete, or semantically ambiguous.

The highest-priority fixes are:

1. Stop auto-registering `/` as a default library.
2. In DB-required mode, never return an empty gallery unless the DB can prove the folder is indexed and empty.
3. Reconcile deleted/offline filesystem assets during rebuild/scan flows.
4. Make derivative jobs fail cleanly instead of getting stuck in `running`.
5. Align backend semantic errors with frontend typed error handling.

## Giải thích dễ hiểu bằng tiếng Việt

Các issue trong file này đều xuất phát từ việc app chuyển sang chế độ "DB là nguồn dữ liệu chính", nhưng DB chưa đủ đáng tin trong một số tình huống. DB có thể tự đăng ký sai root, thiếu dữ liệu, còn dữ liệu cũ, hoặc frontend không hiểu lỗi backend trả về.

### 1. Default library `/` làm hỏng ý nghĩa "registered library"

Hiện `GALLERY_ROOT` mặc định là `/`. Khi DB khởi tạo, code tự tạo library mặc định từ root này.

Vấn đề: `/` bao trùm gần như toàn bộ filesystem. Vì vậy gần như path nào cũng bị coi là "đã registered", ví dụ:

```text
/tmp/foo
/home/ubuntu/Pictures
/mnt/photos
```

Hậu quả:

- `library_not_registered` gần như không bao giờ xảy ra.
- User không register được `/home/ubuntu/Pictures` vì nó overlap với library `/`.
- DB-required mode mất ý nghĩa bảo vệ.

Fix sạch:

- Không tự tạo default library nếu `GALLERY_ROOT == "/"`.
- Trong DB-required mode, chỉ coi path là registered nếu user/API đã register rõ ràng.
- Nếu cần backward compatibility, thêm field như `source = "implicit" | "user"` hoặc `implicit = true/false`.

### 2. DB-required trả gallery rỗng cho path sai hoặc chưa indexed

Hiện nếu DB-required bật và DB không có listing, backend có thể trả:

```json
{
  "folders": [],
  "images": [],
  "index_source": "warm_db"
}
```

Response này nghe như folder tồn tại nhưng rỗng. Nhưng thực tế có thể là:

- path không tồn tại,
- path là file chứ không phải folder,
- library chưa scan,
- library đang discovering/indexing,
- DB chưa có dữ liệu.

Hậu quả: user tưởng folder không có ảnh, trong khi thật ra app chưa index hoặc path sai.

Fix sạch:

- path không tồn tại -> `404 not_found`
- path không phải folder -> `400 not_directory`
- chưa register -> `409 library_not_registered`
- đã register nhưng chưa index -> `409 library_not_indexed`
- đang scan/index -> `202` hoặc `409 library_discovering`
- thật sự folder rỗng và đã index xong -> mới trả `200` empty gallery

Nguyên tắc: không được trả empty gallery trừ khi DB chứng minh folder đó đã indexed và thật sự rỗng.

### 3. Ảnh đã xóa khỏi ổ đĩa nhưng vẫn hiện trong gallery

Flow lỗi:

1. Có ảnh `a.png`.
2. App scan và lưu vào DB.
3. User xóa `a.png` khỏi disk.
4. App rebuild/scan lại.
5. DB vẫn giữ asset cũ là active.
6. Gallery vẫn hiện `a.png`.

Nguyên nhân: rebuild hiện tại chủ yếu upsert file còn tồn tại, nhưng không reconcile file đã mất.

Hậu quả:

- Gallery hiện "ghost image".
- Thumbnail/preview có thể fail vì source file không còn.
- DB-required mode hiển thị dữ liệu sai.

Fix sạch:

- Quét filesystem hiện tại.
- Upsert file còn tồn tại.
- File trước đây có trong DB nhưng giờ không còn thì mark `offline=1` hoặc `deleted_at=now`.
- Listing chỉ show asset active.

Predicate active nên thống nhất:

```sql
deleted_at IS NULL AND offline = 0
```

### 4. Folder count / cover có thể tính cả offline asset

Main listing đã filter:

```sql
deleted_at IS NULL AND offline = 0
```

Nhưng query đếm image trong folder và chọn cover image chỉ check `deleted_at IS NULL`, thiếu `offline = 0`.

Hậu quả:

- Folder báo có ảnh dù ảnh đã offline.
- Cover folder có thể lấy ảnh đã mất khỏi disk.

Fix sạch:

- Mọi query listing/count/cover/status phải dùng cùng điều kiện active:

```sql
deleted_at IS NULL AND offline = 0
```

- Tốt hơn là gom predicate này thành helper/constant để tránh lệch logic giữa các query.

### 5. Derivative worker có thể chết và để job kẹt `running`

Derivative là thumbnail/preview.

Flow lỗi:

1. Worker claim job.
2. DB đánh dấu job là `running`.
3. Source image bị xóa trước khi worker xử lý.
4. Code gọi `stat()` hoặc tính cache path và bị `FileNotFoundError`.
5. Exception xảy ra ngoài block xử lý lỗi.
6. Worker có thể chết, job vẫn stuck `running`.

Hậu quả:

- Queue kẹt.
- Thumbnail/preview mãi không xong.
- Request có thể wait rồi timeout.

Fix sạch:

- Sau khi claim job, mọi thao tác có thể lỗi phải nằm trong `try`.
- Nếu source missing, mark job `failed` hoặc `skipped_source_missing`, ghi `last_error`, rồi cho worker tiếp tục xử lý job khác.
- Không claim derivative job cho asset đã `offline` hoặc `deleted`.
- Có watchdog reset/mark failed các job `running` quá lâu.

### 6. `derivative_ready` có thể stale

Listing hiện chỉ nhìn DB:

```text
asset_derivatives.status = "ready"
```

rồi báo thumbnail/preview đã ready.

Nhưng DB row `ready` không đảm bảo:

- cache file còn tồn tại,
- source image chưa bị sửa,
- source image chưa bị xóa,
- derivative còn đúng version,
- asset chưa offline.

Hậu quả: frontend nghĩ thumbnail ready, nhưng khi request thật thì backend phải regenerate, fail, hoặc timeout.

Fix sạch:

Derivative chỉ được coi là ready nếu:

- status là `ready`,
- cache path tồn tại,
- cache file còn tồn tại,
- source mtime/size khớp với lúc derivative được tạo,
- asset active: `deleted_at IS NULL AND offline = 0`.

Nếu stat cache/source trên mỗi listing quá đắt, dùng background repair/sweep:

- ready nhưng cache mất -> mark stale/queued,
- source đổi -> mark stale/queued,
- asset offline -> không count là ready.

### 7. Frontend chưa hiểu các lỗi `library_*`

Backend có thể trả lỗi semantic như:

```text
library_not_registered
library_overlap
library_offline
```

Và sau fix sẽ cần thêm:

```text
library_not_indexed
library_discovering
```

Nhưng frontend `ErrorType` chưa khai báo các loại này. Vì vậy nó fallback thành lỗi chung:

```text
Something went wrong
```

Hậu quả: backend trả đúng lỗi, nhưng UI không hướng dẫn user làm gì.

Fix sạch:

Frontend thêm error types:

```ts
"library_not_registered"
"library_not_indexed"
"library_discovering"
"library_overlap"
"library_offline"
```

UI nên map thành action rõ ràng:

- `library_not_registered` -> "Register this folder"
- `library_not_indexed` -> "Start library scan"
- `library_discovering` -> "Scan in progress"
- `library_overlap` -> "This path overlaps another library"
- `library_offline` -> "Library path is offline"

### 8. Thumbnail/preview request có thể wait 10 giây

Khi thumbnail/preview chưa ready, request có thể schedule job rồi chờ tối đa 10 giây.

Với lightbox preview thì còn chấp nhận được. Nhưng với grid thumbnail, nếu mở folder lạnh có nhiều ảnh, hàng loạt request thumbnail có thể cùng bị giữ 10 giây.

Hậu quả:

- request worker bị giữ lâu,
- tail latency cao,
- UI dễ chậm,
- server dễ nghẽn khi nhiều ảnh cold.

Fix sạch:

- Grid thumbnail: nếu chưa ready, schedule job rồi trả placeholder/`202` nhanh; frontend retry/refetch sau.
- Lightbox preview: có thể wait ngắn hơn, ví dụ 1-2 giây; nếu chưa xong thì frontend hiển thị loading và poll lại.
- Thêm metric như `derivative_queue_wait_seconds` và `derivative_request_wait_timeout_total`.

### 9. `mtime_ns` naming/unit chưa nhất quán

Một số chỗ lưu `stat.st_mtime` tức giây, nhưng column tên là `mtime_ns`, nghe như nanoseconds.

Derivative logic lại dùng `stat.st_mtime_ns`.

Hậu quả:

- Dễ compare sai version source.
- Dễ miss thay đổi file trong cùng một giây.
- Code gây hiểu nhầm cho người maintain.

Fix sạch:

- Nếu column tên `mtime_ns` thì lưu thật sự `st_mtime_ns` dạng integer.
- Hoặc nếu muốn lưu seconds thì đổi tên thành `mtime`.
- Derivative/versioning nên dùng chung một source version:

```text
path + mtime_ns + size + variant + format + quality
```

### Thứ tự fix nên làm

1. Fix default library `/`.
2. Fix DB-required không được trả empty gallery sai.
3. Fix asset reconciliation để xóa ghost images.
4. Fix active asset predicate cho listing/count/cover.
5. Fix derivative worker stuck `running`.
6. Fix derivative readiness stale.
7. Fix frontend error mapping.
8. Tối ưu timeout thumbnail/preview.
9. Cleanup `mtime_ns`.

Nói ngắn gọn: trước hết phải làm DB-required nói đúng sự thật; sau đó làm asset catalog tự đồng bộ đúng với filesystem; cuối cùng harden derivative pipeline và frontend UX.

## Confirmed issues

### 1. Blocker: implicit default library from `GALLERY_ROOT="/"` breaks registered-library semantics

#### What happens

`GALLERY_ROOT` defaults to `/`. Database initialization always creates a default library from `GALLERY_ROOT` if no library exists.

That means a fresh DB can contain an implicit library rooted at `/`.

Because `/` contains almost every absolute path:

- `/tmp/foo` looks registered.
- `/home/user/Pictures` looks registered.
- DB-required `library_not_registered` checks become ineffective.
- Registering a real child library can fail because it overlaps the implicit `/` library.

#### Why this is bad

DB-required mode is supposed to mean: "only browse explicitly registered libraries."

An implicit `/` library turns that into: "almost everything is registered." This defeats the safety and product semantics of Phase 4.

#### Evidence

- `GALLERY_ROOT` default: `backend/config.py`
- Default library creation: `backend/metadata_store.py::_ensure_default_library_conn`
- Library matching treats `/` as containing every path: `backend/metadata_store.py::_path_is_within`
- `register_library()` rejects overlap with existing roots.

#### Clean fix

Do not auto-create a default library when `GALLERY_ROOT == "/"`.

Recommended model:

- Libraries table should contain explicit user/API-created libraries.
- A legacy/default library may be created only when `GALLERY_ROOT` is a real configured gallery root, not `/`.
- Add an `implicit` or `source` column only if backward compatibility requires distinguishing legacy auto-created libraries from user-registered libraries.
- In DB-required mode, `get_library_for_path()` should only accept explicit registered libraries.

#### Tests to add

- With `GALLERY_ROOT="/"` and `GALLERY_DB_REQUIRED=true`, `/api/scan?path=/tmp/foo` returns `409 library_not_registered` when no explicit library exists.
- With `GALLERY_ROOT="/"`, registering `/home/ubuntu/Pictures` is not blocked by an implicit `/` library.
- With `GALLERY_ROOT=/some/gallery`, legacy default-library behavior still works if backward compatibility is required.

---

### 2. Blocker: DB-required mode can return an empty gallery for missing, invalid, or unindexed paths

#### What happens

When `GALLERY_DB_REQUIRED=true`, `api_scan()` calls `get_asset_folder_listing()`. If the warm DB listing returns `None`, the API currently returns:

```json
{
  "folders": [],
  "images": [],
  "next_cursor": null,
  "total_images": 0,
  "index_source": "warm_db"
}
```

This can happen for multiple different states:

- Path does not exist.
- Path is a file, not a directory.
- Path is registered but has not been indexed.
- Library is currently `discovering`.
- Library is currently `indexing`.
- Folder has no asset rows because the DB is incomplete/stale.

The API collapses all of those cases into "empty folder."

#### Why this is bad

An empty gallery is a valid successful result. Returning it for an error or incomplete state hides the real problem from the frontend and the user.

The user can incorrectly conclude that the folder has no images, when the actual problem is "not indexed yet" or "wrong path."

#### Evidence

- `backend/scan.py::api_scan`
- `backend/metadata_store.py::get_asset_folder_listing`

#### Clean fix

Separate these states explicitly:

1. Validate filesystem path after resolving and safety-checking:
   - missing path: `404 not_found`
   - non-directory path: `400 not_directory`
   - path outside allowed root: `403 permission`

2. Resolve library state:
   - no explicit registered library: `409 library_not_registered`
   - library `discovering`: `202 library_discovering` or `409 library_discovering`
   - library registered but never completed first scan: `409 library_not_indexed`
   - library `offline`: `409 library_offline`
   - library `error`: return semantic error with `last_error`

3. Return empty gallery only when:
   - path is valid,
   - library is explicit and ready,
   - folder was indexed,
   - DB confirms zero children/images.

Best-practice response shape:

```json
{
  "error": "library_not_indexed",
  "message": "Library is registered but has not been indexed yet.",
  "library_id": 123,
  "state": "discovering",
  "can_start_scan": true
}
```

#### Tests to add

- Missing path in DB-required mode returns `404 not_found`.
- File path in DB-required mode returns `400 not_directory`.
- Registered but unindexed library returns `409 library_not_indexed` or `202 library_discovering`.
- Ready indexed folder with no images returns `200` with empty `images`.

---

### 3. Blocker: rebuild/scan can leave deleted assets visible in the gallery

#### What happens

`rebuild_index_scope()` discovers and upserts currently found files, but it does not reconcile previously indexed assets that no longer exist on disk.

Result:

1. Image exists and is indexed into `assets`.
2. User deletes image from disk.
3. Rebuild/scan runs again.
4. Old asset remains `offline=0`, `deleted_at=NULL`.
5. DB listing still returns the deleted image.

There is a `repair_library_assets()` function that can mark missing paths offline, but the normal library scan path uses `rebuild_index_scope()` and does not guarantee this reconciliation.

#### Why this is bad

In DB-required mode, the DB is authoritative. If deleted files stay active in the DB, the gallery shows "ghost images." Downstream thumbnail/preview generation can then fail or queue invalid work.

#### Evidence

- `backend/indexer.py::rebuild_index_scope`
- `backend/metadata_store.py::_upsert_asset_conn`
- `backend/metadata_store.py::repair_library_assets`
- `backend/libraries.py::_discover_library`

#### Clean fix

Make library discovery/rebuild a reconciliation operation, not only an upsert operation.

Recommended model:

- For a scoped library scan:
  - collect all current folder/image paths under that library root,
  - upsert discovered paths,
  - mark previously active but now-missing paths as `offline=1` or `deleted_at=now`,
  - preserve derivative rows if they are useful for future reappearance, but do not count them as ready for active listings.

Prefer one canonical code path:

- Either make `rebuild_index_scope()` reconcile `assets`, or
- make `_discover_library()` call `repair_library_assets()` after/inside rebuild.

Avoid having two independent scanners with different semantics.

#### Tests to add

- Index image, delete it, run library scan/rebuild, assert it disappears from `/api/scan`.
- Deleted child image does not contribute to folder `image_count`.
- Deleted/offline child image is not used as folder cover.
- Reappearing file is restored to `offline=0` and `deleted_at=NULL`.

---

### 4. High: folder counts and covers can include offline assets

#### What happens

The main listing query filters active rows with:

```sql
deleted_at IS NULL AND offline = 0
```

But folder child counts and folder cover queries filter only:

```sql
deleted_at IS NULL
```

They do not consistently filter `offline = 0`.

#### Why this is bad

Even if the main listing hides offline assets, folder metadata can still show incorrect counts or cover images from files that are no longer available.

#### Evidence

- `backend/metadata_store.py::get_asset_folder_listing`

#### Clean fix

Use one shared "active asset" predicate everywhere:

```sql
deleted_at IS NULL AND offline = 0
```

Best practice: centralize this condition in helper query builders or constants so count/listing/cover/status queries cannot drift.

#### Tests to add

- Offline image is excluded from folder image count.
- Offline image is excluded from folder cover images.
- Deleted image is excluded from both.

---

### 5. High: derivative worker can crash and leave jobs stuck in `running`

#### What happens

The derivative scheduler claims a job and marks it `running`. Then `_run_job()` computes the derivative cache path before entering the failure-handling block.

If the source file is deleted after the job is claimed but before `stat()` succeeds, a `FileNotFoundError` can escape outside the handler.

Result:

- worker thread can die,
- derivative job remains `running`,
- derivative row remains `running`,
- future requests may wait or time out.

#### Why this is bad

Background queues must be self-healing. A missing source file should become a controlled failed/skipped job, not a dead worker or permanently running job.

#### Evidence

- `backend/derivative_scheduler.py::_claim_job`
- `backend/derivative_scheduler.py::_run_job`
- `backend/thumbnails.py::derivative_cache_path`

#### Clean fix

Move all source-file-dependent operations inside the `try` block after claim.

Recommended behavior:

- If source file is missing:
  - mark derivative/job as `failed` or `skipped_source_missing`,
  - set `last_error`,
  - do not kill the worker.
- If asset is now `offline` or `deleted`:
  - do not generate,
  - mark job skipped/failed with semantic reason.
- Add a watchdog/reaper:
  - jobs stuck `running` older than a threshold are reset to `queued` or marked `failed`.

#### Tests to add

- Claim job, delete source, run worker, assert job is not left `running`.
- Worker continues processing next job after source-missing failure.
- Deleted/offline asset is not claimed for derivative generation.

---

### 6. Medium/High: `derivative_ready` and derivative status can be stale or optimistic

#### What happens

Folder listing sets `derivative_ready.thumbnail/preview = true` if the DB has an `asset_derivatives` row with `status='ready'`.

It does not prove:

- cache file still exists,
- source file still exists,
- derivative source mtime/size still matches the current asset,
- asset is active,
- derivative variant still matches the requested variant policy.

`library_status()` has similar drift: it counts ready derivative rows without proving current source/cache validity, and active asset filtering is incomplete.

#### Why this is bad

The UI can think thumbnail/preview is ready while the serving route has to regenerate, fails, or times out. Library warm coverage can also look better than it really is.

#### Evidence

- `backend/metadata_store.py::get_asset_folder_listing`
- `backend/derivative_scheduler.py::library_status`
- `backend/derivative_scheduler.py::rebuild_stale`

#### Clean fix

Use a canonical source version key for every derivative:

```text
source_version = source_path + source_mtime_ns + source_size + variant + format + quality
```

Listing/status should only mark ready when:

- derivative status is `ready`,
- cache path is non-null,
- cache file exists,
- derivative source version matches the current asset version,
- asset is active (`deleted_at IS NULL AND offline = 0`).

For performance, do not stat every cache file on every listing request if that is too expensive. Use one or more of:

- periodic repair job,
- derivative health table,
- lazy invalidation on serve failure,
- background sweep that turns missing/stale ready rows back to `queued` or `stale`.

#### Tests to add

- Ready derivative with missing cache file is not reported ready after repair/sweep.
- Ready derivative with changed source mtime/size is not reported ready.
- Offline/deleted asset derivative is not counted in warm coverage.

---

### 7. High: frontend does not understand new library semantic errors

#### What happens

Backend returns semantic errors such as:

- `library_not_registered`
- `library_overlap`
- `library_offline`

Planned fixes should also add:

- `library_not_indexed`
- `library_discovering`

Frontend `ErrorType` does not include these values, so they fall through to a generic server error message.

#### Why this is bad

The backend can be semantically correct while the UI still says "Something went wrong." That blocks the intended user recovery flow:

- register this folder,
- start library scan,
- open library settings,
- resolve overlap,
- reconnect offline library.

#### Evidence

- `backend/scan.py::_require_db_path`
- `backend/libraries.py`
- `frontend/src/services/api.ts`

#### Clean fix

Create a shared API error contract and keep frontend/backend in sync.

Minimum frontend additions:

```ts
type ErrorType =
  | "library_not_registered"
  | "library_not_indexed"
  | "library_discovering"
  | "library_overlap"
  | "library_offline"
  // existing values...
```

Recommended UI actions:

- `library_not_registered`: show "Register this folder"
- `library_not_indexed`: show "Start library scan"
- `library_discovering`: show progress / "Scan in progress"
- `library_overlap`: show existing conflicting library root
- `library_offline`: show reconnect/rescan guidance

Best practice:

- Define error codes in OpenAPI or a generated shared schema.
- Add frontend tests for each semantic error.

#### Tests to add

- `GalleryAPIError.fromAxiosError()` maps each library error to a specific user message.
- Scan view shows a register action for `library_not_registered`.
- Scan view shows a scan action/progress state for `library_not_indexed` / `library_discovering`.

---

### 8. Medium: thumbnail/preview request path can wait up to 10 seconds per request

#### What happens

When a derivative is not ready, `/api/thumbnail` and `/api/preview` can schedule work and poll for up to 10 seconds inside the HTTP request.

#### Why this is bad

This may be acceptable for an explicit lightbox preview, but it is risky for grid thumbnails. A cold folder with many images can create many concurrent long-held requests, causing threadpool pressure and high tail latency.

#### Evidence

- `backend/thumbnails.py::_serve_derivative`

#### Clean fix

Use different behavior by use case:

- Grid thumbnail:
  - schedule derivative,
  - return placeholder, `202`, or short fallback quickly,
  - frontend retries/polls/refetches.
- Lightbox preview:
  - optionally wait briefly,
  - use a shorter timeout, for example 1-2 seconds,
  - frontend can show loading and retry.

Add metrics:

- `derivative_queue_wait_seconds`
- `derivative_request_wait_timeout_total`
- `derivative_request_scheduled_total`
- `derivative_request_served_ready_total`

#### Tests to add

- Thumbnail route does not block for long cold-generation timeout.
- Preview route returns controlled timeout/fallback.
- Concurrent cold thumbnail requests do not exhaust request workers in integration/perf tests.

---

### 9. Medium: asset mtime field naming and units are inconsistent

#### What happens

Some asset paths store `stat.st_mtime` seconds in a column named `mtime_ns`, while derivative logic uses `stat.st_mtime_ns` nanoseconds.

#### Why this is bad

The naming makes it easy to write incorrect comparisons between asset and derivative versions. Even if current code paths avoid direct comparison in some places, this is a future bug trap.

#### Clean fix

Normalize source version fields:

- Rename `assets.mtime_ns` to `mtime` if it stores seconds, or
- migrate it to true nanoseconds everywhere.

Recommended:

- Store `mtime_ns INTEGER`.
- Store `size INTEGER`.
- Derive a stable `source_version_key` from `path`, `mtime_ns`, and `size`.
- Use the same units for assets, derivatives, rebuild, and listing readiness.

#### Tests to add

- Asset mtime stored by indexer equals `Path.stat().st_mtime_ns`.
- Derivative stale detection catches same-second source changes when size differs or nanosecond mtime changes.

## Recommended implementation order

### Phase A: restore correct DB-required semantics

1. Stop implicit `/` default library.
2. Add explicit library lifecycle errors:
   - `library_not_registered`
   - `library_not_indexed`
   - `library_discovering`
   - `library_offline`
3. Validate filesystem path before returning DB-required listing results.
4. Update frontend error mapping and recovery actions.

This phase fixes the most dangerous user-facing lies: "everything is registered" and "not indexed means empty."

### Phase B: make asset catalog reconciliation authoritative

1. Make library scan/rebuild reconcile missing paths.
2. Use the active asset predicate everywhere:

```sql
deleted_at IS NULL AND offline = 0
```

3. Add tests for deleted/offline assets in listings, counts, covers, and scan results.

This phase fixes ghost images and stale folder metadata.

### Phase C: harden derivatives

1. Make worker exceptions after claim always produce a terminal job state.
2. Do not claim work for deleted/offline assets.
3. Normalize derivative readiness around source version + cache existence.
4. Reduce request-path wait for grid thumbnails.
5. Add derivative queue/request metrics.

This phase prevents stuck queues and stale readiness flags.

### Phase D: schema cleanup

1. Normalize asset `mtime_ns` storage.
2. Add migration and compatibility tests.
3. Consider generated shared API schemas for frontend/backend error codes.

## Definition of done

The fix set should be considered complete when:

- DB-required mode never returns empty gallery for missing, invalid, unregistered, discovering, or unindexed paths.
- A fresh DB with `GALLERY_ROOT="/"` does not register `/` implicitly.
- User can register a real child library when `GALLERY_ROOT="/"`.
- Deleted files disappear from DB-backed listings after rebuild/scan.
- Offline/deleted assets do not affect folder counts, covers, derivative readiness, or warm coverage.
- Derivative worker survives missing-source races and does not leave jobs stuck in `running`.
- Frontend displays actionable messages for every library semantic error.
- Backend and frontend tests cover all of the above.
