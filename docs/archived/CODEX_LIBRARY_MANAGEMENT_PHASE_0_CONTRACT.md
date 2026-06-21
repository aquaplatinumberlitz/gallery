# Codex Library Management Phase 0 Contract Lock

> **Archived:** Historical binding contract for the completed Library
> Management V1 implementation. The schema baseline and phase language below
> describe the rollout; use [Architecture](../ARCHITECTURE.md) for current state.

Status: implemented and archived

Locked: 2026-06-20  
Implementation baseline: SQLite `user_version = 5`

Current implementation progress:
[`CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_STATUS.md`](CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_STATUS.md).
This contract describes the required end state; the status document describes
which parts currently exist.

This document is the binding implementation contract for Phases 1-8 of
`CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_PLAN.md`. If the broader plan is
ambiguous, this document takes precedence. A contract change after Phase 0
requires updating this document and the affected tests before implementation.

Phase 0 changes documentation only. It does not add routes, mutate the database,
or change the current gallery state model.

## 1. Decisions Locked

### 1.1 System boundaries

- The existing FastAPI, SQLite, Vue 3, Pinia, TanStack Query, and path-based
  viewer architecture remains in place.
- Registered library administration is local and single-user. No owner, tenant,
  authentication, Redis, BullMQ, NestJS, Socket.IO, or HLS contract is added.
- TanStack Query owns library/job API data. Pinia owns only selected IDs and
  in-memory viewer navigation state.
- Existing image browsing and PhotoSwipe behavior remain path-based.
- SSE is an invalidation/progress optimization. SQLite and HTTP queries remain
  the source of truth.

### 1.2 Identifiers, paths, and timestamps

- Library, import-path, asset, and job IDs are positive SQLite integer IDs.
- Persisted filesystem paths are absolute canonical paths produced by
  `Path.resolve()`. API responses use the platform-native canonical string.
- Path containment and overlap checks operate on path components, never raw
  string prefixes.
- API timestamps are Unix epoch seconds as JSON numbers, or `null`.
- New database timestamps are Unix epoch seconds (`REAL`).
- Phase 1 migration converts existing `libraries.created_at`, `updated_at`, and
  non-null `last_scan_at` values from SQLite Julian day to Unix epoch seconds.
  The conversion is applied only to values in the Julian-day range
  `2_000_000 <= value < 3_000_000`, making the migration idempotent.

### 1.3 Compatibility rules

- `libraries.root_path` remains a database compatibility column through V1.
- `RegisteredLibrary.root_path` is always the first import path ordered by
  `(position, id)`.
- Every library must have at least one import path.
- Legacy create payload `{ "root_path": "..." }` remains accepted.
- New code reads `import_paths`; it does not treat `root_path` as an independent
  source of truth.
- Existing `/api/scan`, `/api/folders`, `/api/search`, image, thumbnail,
  preview, and metadata path parameters remain supported.
- No-path viewer fallback resolves to the first library by library ID, then its
  first import path by `(position, id)`.

## 2. HTTP Conventions

### 2.1 Success and error envelopes

- Successful endpoints return their documented JSON object or array directly.
- `DELETE /api/libraries/{id}` keeps its current JSON confirmation response;
  it does not change to an empty `204` response.
- Errors keep the existing FastAPI shape:

```json
{
  "detail": {
    "error": "bad_request",
    "message": "Human-readable detail"
  }
}
```

Locked error codes:

| Code                     | HTTP status | Use                                                                       |
| ------------------------ | ----------- | ------------------------------------------------------------------------- |
| `bad_request`            | 400         | Invalid payload, empty replacement list, malformed pattern, invalid Range |
| `confirmation_required`  | 400         | Unregister called without `confirm=true`                                  |
| `permission`             | 403         | Outside `PATH_SAFETY_ROOT` or unreadable                                  |
| `not_found`              | 404         | Library, job, path, or source file not found                              |
| `not_directory`          | 400         | Import path exists but is not a directory                                 |
| `invalid_file`           | 400         | Unsupported or invalid media                                              |
| `library_overlap`        | 409         | Import path overlaps another registered library                           |
| `library_offline`        | 409         | Required import path is unavailable                                       |
| `library_busy`           | 409         | Operation cannot safely run beside an active job                          |
| `video_tool_unavailable` | 503         | Poster generation requires unavailable `ffmpeg`                           |
| `video_poster_failed`    | 422         | `ffmpeg` could not produce a poster                                       |
| `server_error`           | 500         | Unexpected backend failure                                                |

Pydantic's normal `422` response remains valid for structurally malformed JSON.
Domain validation uses the typed errors above.

### 2.2 Route declaration order

Static collection routes must be declared before dynamic
`/api/libraries/{library_id}` routes:

1. `/api/libraries`
2. `/api/libraries/validate`
3. `/api/libraries/scan-all`
4. `/api/libraries/{library_id}`
5. nested `/{library_id}/...` routes

This prevents `validate` or `scan-all` from being parsed as an integer ID.

## 3. Library API Contract

### 3.1 Shared response objects

```ts
type LibraryState =
  | "queued"
  | "discovering"
  | "indexing"
  | "ready"
  | "error"
  | "offline";

type LibraryJobState =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

interface LibraryImportPath {
  id: number;
  library_id: number;
  path: string;
  position: number;
  created_at: number;
  updated_at: number;
}

interface RegisteredLibrary {
  id: number;
  root_path: string;
  import_paths: LibraryImportPath[];
  exclusion_patterns: string[];
  name: string;
  state: LibraryState | string;
  watch_enabled: 0 | 1;
  warm_enabled: 0 | 1;
  asset_count: number;
  created_at: number;
  updated_at: number;
  last_scan_at: number | null;
  last_error: string | null;
}
```

`asset_count` counts active non-folder assets:
`deleted_at IS NULL AND offline = 0 AND type IN ('image', 'video')`.

### 3.2 Create and update payload semantics

```ts
interface LibraryCreateRequest {
  name?: string;
  import_paths?: string[];
  exclusion_patterns?: string[];
  root_path?: string;
}

interface LibraryUpdateRequest {
  name?: string;
  import_paths?: string[];
  exclusion_patterns?: string[];
}
```

Rules:

- Create accepts exactly one path source: non-empty `import_paths`, or legacy
  `root_path`. Supplying both returns `bad_request`.
- Import-path order in the request is persisted as zero-based `position`.
- Update is replacement semantics for each supplied list. Omitted fields remain
  unchanged.
- `import_paths: []` is invalid.
- An update with no recognized field is invalid.
- Path strings are trimmed and surrounding matching single/double quotes are
  removed before canonicalization.
- Duplicate canonical paths within one payload are rejected as `bad_request`.
- Cross-library exact matches and ancestor/descendant overlaps are rejected as
  `library_overlap`.
- Overlap among paths in the same library is accepted but returned as a
  validation warning. Discovery must deduplicate by canonical asset path.
- Name is trimmed. A missing or blank create name derives from the first import
  path's basename, falling back to the full path.
- Exclusion patterns are trimmed, must be non-empty and unique, and are capped
  at 128 entries. Their request order is preserved.

### 3.3 Validation

`POST /api/libraries/validate` validates a create payload.  
`POST /api/libraries/{id}/validate` validates replacement values against an
existing library without writing.

Both return `200` for valid and invalid domain values:

```ts
interface LibraryValidationItem {
  value: string;
  normalized_value: string | null;
  is_valid: boolean;
  message: string | null;
  warnings: string[];
}

interface LibraryValidationResult {
  is_valid: boolean;
  import_paths: LibraryValidationItem[];
  exclusion_patterns: LibraryValidationItem[];
}
```

Structural payload errors may return `422`; a missing edit target returns `404`.
Create/update repeat all validation transactionally and never trust a prior
validation response.

### 3.4 Endpoint table

| Method   | Endpoint                           | Success                       | Locked behavior                                     |
| -------- | ---------------------------------- | ----------------------------- | --------------------------------------------------- |
| `GET`    | `/api/libraries`                   | `200 RegisteredLibrary[]`     | Ordered by library ID                               |
| `POST`   | `/api/libraries`                   | `201 RegisteredLibrary`       | Atomic library/path/pattern create                  |
| `POST`   | `/api/libraries/validate`          | `200 LibraryValidationResult` | No writes                                           |
| `GET`    | `/api/libraries/{id}`              | `200 RegisteredLibrary`       | `404` if absent                                     |
| `PATCH`  | `/api/libraries/{id}`              | `200 RegisteredLibrary`       | Canonical update method                             |
| `PUT`    | `/api/libraries/{id}`              | `200 RegisteredLibrary`       | Exact alias of PATCH semantics                      |
| `POST`   | `/api/libraries/{id}/validate`     | `200 LibraryValidationResult` | Excludes current library from cross-library overlap |
| `GET`    | `/api/libraries/{id}/progress`     | `200 LibraryProgress`         | Polling source of truth                             |
| `GET`    | `/api/libraries/{id}/stats`        | `200 LibraryStats`            | Aggregate asset stats                               |
| `GET`    | `/api/libraries/{id}/jobs`         | `200 LibraryJob[]`            | Newest first, default limit 50, max 200             |
| `POST`   | `/api/libraries/{id}/scan`         | `202 LibraryScanResponse`     | Queue/coalesce scan                                 |
| `POST`   | `/api/libraries/scan-all`          | `202 ScanAllResponse`         | Parent plus per-library children                    |
| `POST`   | `/api/libraries/{id}/repair`       | `200 LibraryRepairResponse`   | Synchronous V1 operation recorded as a job          |
| `DELETE` | `/api/libraries/{id}?confirm=true` | `200` confirmation object     | Never deletes source files                          |
| `GET`    | `/api/stats`                       | `200 GalleryStats`            | All registered libraries                            |
| `GET`    | `/api/jobs`                        | `200 LibraryJob[]`            | Newest first, default limit 100, max 500            |
| `GET`    | `/api/jobs/{id}`                   | `200 LibraryJob`              | `404` if absent                                     |
| `GET`    | `/api/events`                      | `200 text/event-stream`       | Best-effort events                                  |

List endpoints may add cursor pagination later, but V1 query/response shapes are
plain bounded arrays.

### 3.5 Progress, stats, and mutation responses

```ts
interface LibraryProgress {
  indexed_assets: number;
  estimated_assets: number;
  discovery_complete: boolean;
  library_state: LibraryState | string;
  active_job_id: number | null;
}

interface LibraryStats {
  photos: number;
  videos: number;
  total_assets: number;
  active_assets: number;
  offline_assets: number;
  usage_bytes: number;
  import_path_count: number;
}

interface GalleryStats extends Omit<LibraryStats, "import_path_count"> {
  library_count: number;
}

interface LibraryScanResponse {
  library_id: number;
  job_id: number;
  state: "queued" | "running";
}

interface ScanAllResponse {
  job_id: number;
  state: "queued" | "running";
  child_job_ids: number[];
}

interface LibraryRepairResponse {
  library_id: number;
  job_id: number;
  added: number;
  removed: number;
  modified: number;
}
```

Stats definitions:

- `photos`: active assets with `type = 'image'`.
- `videos`: active assets with `type = 'video'`.
- `total_assets` and `active_assets`: identical in V1; active images + videos.
- `offline_assets`: non-deleted image/video assets with `offline = 1`.
- `usage_bytes`: sum of `size` for active images/videos; null sizes count as 0.
- Folder rows never contribute to asset counts or bytes.

Scanning the same library while a queued/running scan exists is idempotent:
return `202` with the existing job ID. Repair while a scan/repair for that
library is active returns `library_busy`.

While a scan/repair job is active, a name-only update is allowed; changing
import paths or exclusion patterns returns `library_busy`. Unregistering a
library with an active scan/repair job also returns `library_busy`.

Create/update performs a synchronous configuration reconciliation over existing
asset rows before returning:

- rows outside all current import paths or matching current exclusions become
  offline;
- rows brought back into scope become active only when the source still exists;
- this pass does not discover new filesystem entries;
- new files are discovered by scan/repair.

This operation never deletes source files or derivative files.

## 4. Job and SSE Contract

### 4.1 Job object and lifecycle

```ts
interface LibraryJob {
  id: number;
  library_id: number | null;
  parent_job_id: number | null;
  type: "scan" | "repair" | "scan_all" | "video_poster" | "reconcile" | string;
  state: LibraryJobState;
  progress_current: number;
  progress_total: number | null;
  message: string | null;
  error: string | null;
  counters: Record<string, number>;
  created_at: number;
  updated_at: number;
  started_at: number | null;
  finished_at: number | null;
}
```

Allowed transitions:

```text
queued -> running -> succeeded
                  -> failed
queued/running   -> cancelled
```

Terminal jobs never return to an active state. A retry creates a new job.
`progress_current` is non-negative. `progress_total` is null until known and is
never lower than `progress_current` once set.

On process startup:

- stale `running` jobs become `failed`;
- `error` is `Interrupted by server restart`;
- `finished_at` and `updated_at` are set;
- stale `queued` jobs remain queued and may be claimed by the new runner.

The job runner claims queued work under the existing process/DB lock and writes
state before executing it. V1 does not promise multi-process worker safety.

### 4.2 Scan-all

- A `scan_all` parent is created first.
- One `scan` child is created per registered library.
- Child `parent_job_id` references the parent.
- A library with an existing active scan is represented by that existing job ID
  in the response but is not re-parented.
- Parent counters record total, succeeded, failed, and coalesced children.
- The parent tracks all returned job IDs, including coalesced active jobs.
- Parent succeeds only after all tracked jobs are terminal and none failed;
  otherwise it fails after all tracked jobs are terminal.

### 4.3 SSE wire format

`GET /api/events` uses standard SSE frames:

```text
event: library.progress
id: 123
data: {"type":"library.progress",...}

```

The `id` is the emitting job ID when available, otherwise the event's
`updated_at` value as a string. A comment heartbeat (`: keep-alive`) is sent at
least every 15 seconds. Response headers disable intermediary buffering/caching
where supported.

```ts
interface LibraryEventPayload {
  type: "job.updated" | "library.progress" | "job.completed" | "job.failed";
  job_id: number | null;
  library_id: number | null;
  state: LibraryJobState | LibraryState | string;
  progress_current: number;
  progress_total: number | null;
  message: string | null;
  error: string | null;
  updated_at: number;
}
```

Events may be duplicated or missed across reconnects. Frontend handlers use
events to update/invalidate Query caches and continue polling active jobs.

## 5. SQLite Migration Contract

The current baseline is `PRAGMA user_version = 5`. Migrations run inside the
existing initialization transaction and are idempotent.

### 5.1 Version 6: editable library roots and exclusions

```sql
CREATE TABLE library_import_paths (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(library_id, path),
  UNIQUE(library_id, position)
);

CREATE INDEX idx_library_import_paths_path
  ON library_import_paths(path);

CREATE TABLE library_exclusion_patterns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
  pattern TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(library_id, pattern),
  UNIQUE(library_id, position)
);
```

Migration order:

1. Create both tables and indexes.
2. Convert the three library timestamp columns when they contain Julian days.
3. Insert one import path at position 0 for each existing library that has no
   import-path row, using `libraries.root_path`.
4. Verify every library has at least one import path.
5. Set `user_version = 6`.

Writes to import paths and `libraries.root_path` occur in one transaction.
After create/update, `root_path` is set to the path at position 0.

### 5.2 Version 7: library jobs

```sql
CREATE TABLE library_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
  parent_job_id INTEGER REFERENCES library_jobs(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  state TEXT NOT NULL,
  progress_current INTEGER NOT NULL DEFAULT 0,
  progress_total INTEGER,
  message TEXT,
  error TEXT,
  counters_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL
);

CREATE INDEX idx_library_jobs_state_created
  ON library_jobs(state, created_at, id);

CREATE INDEX idx_library_jobs_library_created
  ON library_jobs(library_id, created_at DESC, id DESC);

CREATE INDEX idx_library_jobs_parent
  ON library_jobs(parent_job_id);
```

Unregistering a library sets historical job `library_id` to null rather than
deleting job history.

After the table/index creation succeeds, set `user_version = 7`.

### 5.3 Version 8: video metadata

Add nullable columns to `assets`:

```sql
ALTER TABLE assets ADD COLUMN mime_type TEXT;
ALTER TABLE assets ADD COLUMN duration_ms INTEGER;
ALTER TABLE assets ADD COLUMN codec TEXT;
```

Existing rows require no backfill. Existing `width` and `height` columns are
shared by image and video assets. `assets.type` accepts `folder`, `image`, and
`video`.

Poster files use the existing derivative catalog with `kind = 'video_poster'`;
no separate poster table is introduced.

After all three columns exist, set `user_version = 8`.

## 6. Import Path and Exclusion Semantics

### 6.1 Import path validation

For each import path:

1. Trim whitespace and matching surrounding quotes.
2. Require an absolute path.
3. Resolve symlinks/canonical components with `Path.resolve()`.
4. Require containment under `PATH_SAFETY_ROOT`.
5. Require existence, directory type, and read/scandir access.
6. Check canonical duplicates and cross-library overlap.

Validation and the final transactional write both perform overlap checks. The
existing process `_DB_LOCK` serializes local writers.

### 6.2 Exclusion matching

- Add `wcmatch` as a backend runtime dependency in Phase 1.
- Match with `glob.GLOBSTAR` semantics against the path relative to each import
  root after converting separators to `/`.
- Patterns are relative; absolute patterns and `..` traversal are invalid.
- Matching is case-sensitive on case-sensitive platforms and case-insensitive
  on Windows.
- Default dependency/cache/build exclusions remain active and are ORed with
  per-library patterns.
- Directories are checked before descent; excluded files never enter discovery.

No new frontend dependency is approved for this feature.

## 7. Video Contract

### 7.1 Asset classification

`backend/files.py` will expose:

```py
IMAGE_EXTENSIONS
VIDEO_EXTENSIONS
is_image_path(path)
is_video_path(path)
is_asset_path(path)
asset_type_for_path(path)  # "image" | "video" | None
```

The locked initial video extension set is:

```text
.mp4 .m4v .mov .webm .mkv .avi
```

MIME is inferred conservatively and refined by `ffprobe` when available.
Failure or absence of `ffprobe` does not prevent indexing a recognized video;
duration, codec, and dimensions remain null.

### 7.2 Video endpoints

`GET /api/video?path=...`

- Applies the same path safety and registered-library checks as image serving.
- Requires a recognized active video asset.
- Supports one RFC 7233 byte range.
- Returns `200` for a full response and `206` for a satisfiable range.
- Sets `Accept-Ranges`, `Content-Type`, `Content-Length`, and for partial
  responses `Content-Range`.
- Returns `416` with `Content-Range: bytes */{size}` for an unsatisfiable range.
- Streams from disk; it does not read the entire video into memory.

`GET /api/video/poster?path=...`

- Uses `ffmpeg` to select one representative frame.
- Stores the result through the existing derivative cache/catalog as WebP.
- Cache identity includes canonical path, source mtime/size, poster variant,
  dimensions, format, and quality.
- Returns the cached image with the same cache/ETag conventions as image
  derivatives.
- Missing `ffmpeg` returns `video_tool_unavailable`; generation failure returns
  `video_poster_failed`.

`ffmpeg` and `ffprobe` are optional system executables, discovered with
`shutil.which`. They are not Python or frontend package dependencies.

## 8. Frontend State Contract

### 8.1 Ownership

Persisted localStorage:

```text
gallery-active-library-id
gallery-active-import-path-id
```

One-shot legacy input:

```text
gallery-root-path
```

Pinia state:

```ts
activeLibraryId: number | null;
activeImportPathId: number | null;
currentBrowsePath: string;
sidebarTree: FolderTreeNode[];
expandedFolderPaths: Record<string, boolean>;
history: string[];
historyIndex: number;
hasEverLoaded: boolean;
```

TanStack Query owns `RegisteredLibrary[]`. The store receives the current list
as an action argument and does not cache a second mutable copy.

`activeImportRootPath` is a derived selector from:

```text
activeLibraryId + activeImportPathId + current libraries query data
```

It is not persisted. `currentBrowsePath` is in-memory only.

### 8.2 Hydration algorithm

Hydration runs once per app startup after `GET /api/libraries` settles and
before the first viewer scan:

1. Parse persisted IDs as positive base-10 integers; remove malformed values.
2. If the persisted library exists and has import paths, select the persisted
   path when it belongs to that library, otherwise its first ordered path.
3. Initialize `currentBrowsePath` to that import root and remove any legacy key.
4. If persisted selection is unusable, clear both IDs.
5. Read the legacy root path once.
6. Match exact/contained canonical paths and choose the longest matching import
   root; break equal-length ties by library ID then `(position, id)`.
7. On match, persist both IDs and retain the legacy subfolder as
   `currentBrowsePath`.
8. Remove the legacy key after match/no-match is known.
9. If no match exists and exactly one library has import paths, select its first
   ordered path.
10. Otherwise leave selection empty.

Network failure does not remove the legacy key because match/no-match is not
known. A successful empty library response does remove it as unusable.

Selecting a library/import path:

- persists both IDs;
- resets `currentBrowsePath` to the import root;
- clears search;
- resets sidebar expansion and browse history;
- starts the existing scan query for the import root.

No writable `rootPath` action/getter is part of the completed feature. A
temporary compatibility getter existed during migration but was removed in
Phase 6.

### 8.3 Query behavior

- Admin data uses the query keys defined in the implementation plan.
- Viewer scan/search/folder keys remain normalized-path keys.
- SSE events invalidate or patch library/job queries; active polling remains
  enabled until the terminal-state predicate is satisfied.
- Admin routes are available at all breakpoints and do not redirect mobile or
  tablet users to `/`.

## 9. Dependency Lock

Approved additions/usage:

| Dependency           | Decision                                                                                 |
| -------------------- | ---------------------------------------------------------------------------------------- |
| `wcmatch`            | Add to `backend/requirements.txt` in Phase 1 for globstar exclusion matching             |
| `ffmpeg` / `ffprobe` | Optional system executables; no automatic install                                        |
| Frontend packages    | No additions; reuse installed shadcn-vue/Reka, TanStack, PhotoSwipe, and Lucide packages |
| Queue/transport      | No Redis, BullMQ, Celery, Socket.IO, or WebSocket dependency                             |

The concrete `wcmatch` version constraint is selected and locked in
`backend/requirements.txt` when Phase 1 updates the resolved runtime dependency
set. It must use the stable `wcmatch.glob` API covered by backend tests.

## 10. Phase Gates

Phase 1 may start when tests can target:

- database v5 -> v6 migration and idempotent re-open;
- library serialization/order/root alias;
- create/update/validate replacement semantics;
- path/pattern validation and offline/reactivation behavior.

Phase 2 may start when tests can target:

- v7 job schema and startup recovery;
- job transition guards and scan coalescing;
- stats definitions, scan-all parent/child behavior, and SSE frame shape.

Phase 3 may start when tests can target:

- v8 asset columns;
- extension classification and probe fallback;
- HTTP Range behavior and poster cache/tool errors.

Frontend Phases 4-7 must consume this contract without introducing a second
persisted raw path or changing viewer APIs to library-ID-based cache keys.
