# Architecture

Status: Maintained

Last reviewed: 2026-07-13

Historical Library Management V1 handoff context is retained in the
[archived implementation status](archived/CODEX_LIBRARY_MANAGEMENT_IMPLEMENTATION_STATUS.md).

## Metadata Lifecycle

### Owner: `backend/indexer.py`

The metadata lifecycle owner is `MetadataLifecycleWorker` in `backend/indexer.py`,
modeled on `DerivativeScheduler` (`backend/derivative_scheduler.py`). It owns
scheduling, dispatch, worker lifecycle, completion invariants, stale guards,
and startup recovery.

### DB-claim worker pattern

The worker claims jobs directly from SQLite — no in-memory queue bridges the
DB to the runtime. This mirrors how `DerivativeScheduler._claim_job()` claims
from `derivative_jobs`.

```
dispatch_metadata_index_paths(paths, priority)
  → _persist_metadata_index_jobs(paths, root_path, priority=priority)
    → INSERT/ON CONFLICT into metadata_index_jobs
  → metadata_worker.wake()

metadata_worker._worker_loop
  → claim_next_metadata_job()
    → BEGIN IMMEDIATE
    → SELECT metadata_index_jobs WHERE state='queued'
      ORDER BY priority ASC, queued_at ASC LIMIT 1
    → UPDATE state='running', attempts+1, started_at=now
    → COMMIT
  → extract_metadata(path)  [outside any DB transaction]
  → upsert_metadata_batch([metadata])  [short transaction]
  → complete_metadata_job(conn, job)
    → verify image_metadata current for job identity
    → verify matching asset row exists
    → UPDATE metadata_index_jobs state='done'
    → UPDATE assets metadata_state='done'
```

### Invariants

1. **SQLite is the runtime queue.** The worker claims from `metadata_index_jobs`,
   not from an in-memory `_job_queue`. Queued jobs survive process restart.

2. **Completion materializes both job and asset.** `complete_metadata_job` atomically
   marks the job `done` AND stamps `assets.metadata_state='done'`. If no asset
   row exists, the job is `skipped`. If the asset version differs, the job is `stale`.

3. **Extraction runs outside DB transactions.** Claim and complete are short
   `BEGIN IMMEDIATE` transactions. `extract_metadata` (PIL + JSON parsing) runs
   outside any transaction, matching `DerivativeScheduler._run_job`.

4. **Identity is the image plus its optional sidecar.** Image freshness uses
   `path + mtime_ns + size`; completion additionally requires the stored
   same-stem `.txt` identity (`path + mtime_ns + size`) to match. Sidecar create,
   replacement, modification, or deletion requeues extraction without requiring
   the image to change. Sidecars are opened with no-follow protection where
   supported, validated against the active image asset/import root/safety root,
   and read from one descriptor with a limit-plus-one bounded read. `library_id`
   is a secondary diagnostic field.

### Legacy fallback

For rows created before `mtime_ns` was populated, the system falls back to
comparing `mtime` (float seconds) with `assets.mtime_ns / 1e9` using a 1 ms
tolerance.

### Startup recovery

`recover_metadata_index_jobs()` resets interrupted `running` jobs to `queued`,
fails jobs whose attempts have been exhausted, and repairs `done` jobs whose
asset state never materialised. It also demotes `done` jobs whose sidecar
identity changed. Queued jobs are left claimable — they survive restart because
SQLite is the queue.

### Diagnostics

`get_metadata_lifecycle_status(scope_path)` returns 15 counters covering job
queue depth, inconsistency detection, worker health, and throughput. These are
included in the status API envelope as `metadata_lifecycle`.

### Integrity checker

`backend/integrity_checker.py` runs a periodic background consistency pass when
`GALLERY_INTEGRITY_CHECK_ENABLED` is true. It repairs, re-queues, or marks failed
mismatches between `assets`, `image_metadata`, `metadata_index_jobs`,
`asset_derivatives`, and `derivative_jobs`, including missing derivative cache
files, active metadata jobs whose source file or asset row disappeared, and
ownerless/mismatched media rows in `file_index` that search cannot safely
authorize. Each daemon or manual run persists a summary into
`integrity_check_runs`, which backs the Maintenance file-health API.

Destructive imported-data maintenance holds a shared producer gate across the
operation. Metadata dispatch, metadata workers, derivative scheduling and
reconciliation, integrity repair, and catalog queue producers cannot create new
work while the gate is held. After in-flight producers are quiescent, durable
active work is rechecked; derivative and catalog database rows are then deleted
in one transaction, and cache files are removed only after commit. Releasing the
gate resumes paused producers.

## Derivative Lifecycle

### Owner: `backend/derivative_scheduler.py`

Thumbnail and preview work is a durable SQLite state machine. A queued job is
claimed with a process/worker owner, unique claim token, and a configurable lease
(default 900 seconds). Rendering runs outside database transactions. Completion,
retry, skip, and failure writes are fenced by the claim token so an expired
worker cannot overwrite a newer claim.

While a worker renders, a fenced lease heartbeat owned by the job ID and claim
token renews `lease_expires_at` at most once per heartbeat interval (clamped to
one third of the lease). The heartbeat only updates a row that is still `running`
with the same claim token, stops before the worker persists its terminal outcome,
and never overwrites render state on a failed renewal. A healthy heartbeat keeps
a long render from being duplicated by supervisor or startup recovery when the
original lease would otherwise expire.

Derivative catalog rows use the full state machine `queued` → `running` →
`ready`, with terminal or policy states `failed`, `skipped`, `evicted`, and
`deferred_capacity`. `ready` means the cache path was published after a fenced
job completion. Inactive, missing, or superseded sources become `skipped` with
a machine-readable result code. Invalid sources and exhausted or internal
failures become `failed`; transient SQLite/I/O failures retry at most three
attempts. Quota eviction changes a replaceable `ready` row to `evicted` and
unlinks its cache file. Automatic work that cannot reserve enough quota becomes
`deferred_capacity` without a runnable job. Derivative job rows separately use
`queued`, `running`, `done`, `skipped`, and `failed`.

Every source-dependent operation, including cache-path calculation, is inside
the job exception boundary. The worker loop has an additional catch-all, so one
bad source cannot terminate a worker. A supervisor runs every 30 seconds,
recovers claims owned by dead workers or expired leases, and restores the
configured worker count. Startup applies the same recovery policy before
workers claim new jobs.

`stop()` sets the stop event, wakes all workers, and gives all workers plus the
supervisor/reconciler one shared absolute shutdown deadline. Each join receives
only the time remaining before that deadline, so total shutdown time is bounded
by `GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS`, not multiplied by the thread
count. Overlapping stop calls keep startup blocked until every stop caller has
finished. A timeout records an incomplete shutdown and leaves in-flight renders
running rather than abandoning them. `start()` prunes stale dead worker thread
objects left by an incomplete stop before restoring the configured worker count,
so a prior incomplete stop never permanently refuses to restart.

This lifecycle assumes the maintained single-process deployment: one backend
process owns the derivative workers, the SQLite queue, and all claim leases. It
does not support multiple Uvicorn/Gunicorn processes sharing one derivative
queue; claim fencing and the lease heartbeat are correct only within one process.

Scheduling, claiming, status, and integrity repair all require an active image
asset whose `mtime_ns` and size match the derivative source identity. The
integrity checker requeues missing cache files only for current sources;
inactive, missing, and superseded sources are skipped instead.

HTTP thumbnail/preview requests accept only `128`/`512` and `1440`
respectively, always resolve an active catalog asset, and always pass through
the durable scheduler. Capacity is reserved before runnable work exists;
interactive refusal returns `507`, while automatic work remains
`deferred_capacity`. The WebP file cache is authoritative and quota-counted;
the 64 MiB diskcache stores only key-to-path metadata. Integrity checks skip
and remove legacy unsupported variants after committing their terminal state.

Video posters use a separate 1 GiB default LRU quota plus a global bounded
ffmpeg semaphore. A reference-counted serving lease is acquired before quota
protection is released and remains held through response stat/revalidation and
stream completion. The response itself releases the lease in an ASGI-level
`finally`, including file-open, send, disconnect, and cancellation failures;
cleanup does not depend on a Starlette background task running. Duplicate
requests wait on the per-video lock before using an ffmpeg slot. Queue
saturation returns `503`, subprocess output is discarded, and temporary files
and leases are cleaned on every exit path.

Desired-state reconciliation has explicit trigger ownership:

- The catalog worker reconciles the committed library or path scope after a
  successful scan or rebuild. These automatic passes create missing identities
  but preserve existing capacity-deferred/evicted identities.
- Metadata completion reconciles that asset as a safety net after its durable
  metadata state is committed; it also preserves existing capacity deferrals.
- Scheduler startup reconciles all warm-enabled libraries; its periodic loop
  later fills missing configured identities but does not reconsider existing
  `deferred_capacity` or fully unlinked `evicted` rows, preventing quota-driven
  thumbnail/preview rotation on every pass.
- Integrity checks own repair of missing expected rows, queued rows without an
  active job, and explicit reconsideration of capacity-deferred/evicted rows.
- Enabling warm policy reconciles that library immediately. The admin
  `Generate missing images` action is an explicit library-scoped trigger and may
  retry failed or capacity-deferred work even when warm policy is off.
- Cache clear deletes derivative jobs and catalog rows; later startup,
  catalog, policy, integrity, or explicit generation triggers rebuild desired
  state. A process restart after a configured quota increase uses startup
  reconciliation to reconsider deferred work.

`GET /api/derivatives/status` reports current configured coverage for one
library, that library's ready bytes as `library_used_bytes`, and global quota
accounting as `quota_used_bytes`, `quota_bytes`, and `quota_utilization`.

## Overview

AI Art Gallery is a local-first mixed-media browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans folders, serves original images, generates cached WebP derivatives, extracts AI generation metadata, indexes folders/photos/metadata in SQLite FTS5, and exposes read-only inspection/search APIs.
- Frontend: uses Vue Router for the gallery and metadata inspector routes, Pinia for UI/navigation state, TanStack Query for API state, TanStack Virtual for large grids and the Library Inspector table body, PhotoSwipe for the lightbox, TanStack Form for advanced search, and TanStack Table for the Library Inspector.
- Startup: `start.py` creates/repairs the Python virtualenv, installs Python and pnpm frontend dependencies when needed, and starts the backend on fixed port `4701` and frontend on fixed port `4702`. It exits with an error if either port is occupied.
- Tooling: Ruff, ESLint, and Prettier scan the full codebase. Vitest/V8 covers frontend units; Playwright runs sharded functional E2E and isolated performance suites against deterministic FastAPI fixtures.

Major external library integrations are documented in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).
Environment variables and parser behavior are documented in
[Configuration](CONFIGURATION.md) and [Metadata Parsing](METADATA_PARSING.md).

## Backend

Backend modules are mostly flat, with selected domain packages.

| File                       | Purpose                                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `app.py`                   | FastAPI app creation, CORS, optional Prometheus metrics, optional pyinstrument middleware, router composition, startup background services |
| `main.py`                  | Import-compatible `app` shim and uvicorn fallback block                                                                                    |
| `config.py`                | Environment flags, cache paths, derivative limits, image limits, indexer/catalog tuning, production/static config                           |
| `errors.py`                | `APIError`, `ErrorType`, and FastAPI error shaping                                                                                         |
| `models.py`                | Shared Pydantic DTOs, including `FileNode`                                                                                                 |
| `paths.py`                 | `resolve_path`, `is_path_safe`, and `PATH_SAFETY_ROOT` boundary checks                                                                     |
| `files.py`                 | Image/video classification, exclusion checks, natural sort, and image safety limits                                                        |
| `albums.py`                | Album cover/count/child-folder metadata                                                                                                    |
| `scan.py`                  | Routes removed (Phase 9); scan.py still exports `require_media_path_allowed` and the router included by app.py                            |
| `browse.py`                | DB-only read-only browse via `/api/browse`; virtual import-root listing, path-scoped asset/folder pagination                              |
| `maintenance.py`           | `/api/maintenance/file-health` latest-run report and `/api/maintenance/file-health/check` manual integrity run                             |
| `folders.py`               | `/api/folders` folder-tree endpoint and `/api/open-folder` OS explorer hook                                                                |
| `images.py`                | `/api/image` original file serving                                                                                                         |
| `thumbnails.py`            | `/api/thumbnail`, `/api/preview`, WebP derivative generation, persistent disk cache                                                        |
| `metadata_extract.py`      | Raw metadata extraction/parsing helpers for A1111, SwarmUI, ComfyUI, NovelAI, EasyDiffusion, and generic EXIF/text fields                  |
| `metadata_parse.py`        | `/api/metadata`, in-memory metadata cache, response shaping                                                                                |
| `fielded_search_parser.py` | Parser for `prompt:`, `seed:`, `model:`, numeric operators, quoted values, and related fielded search syntax                               |
| `search.py`                | `/api/search/query`, legacy `/api/search`, `/api/search-metadata`, `/api/library/inspector`, `/api/library/inspector/metadata`              |
| `related_assets.py`        | `/api/search/related` reference authorization and persisted relation-readiness contract                                                      |
| `search_indexes.py`        | Search capabilities plus derived-index state, rebuild-job, and cancellation APIs                                                          |
| `search_indexer.py`        | Fixed index registry and supervised single-writer durable derived-index worker                                                             |
| `facets.py`                | `/api/facets` aggregation over indexed metadata                                                                                            |
| `indexer.py`               | DB-claim metadata lifecycle worker, durable scheduling, startup recovery, diagnostics, and scan worker rebuild helpers                      |
| `integrity_checker.py`     | Periodic cross-table consistency checker for metadata jobs, assets, image metadata, derivatives, and derivative jobs                       |
| `refresh.py`               | Optional scheduled refresh loop                                                                                                            |
| `watcher.py`               | Optional filesystem watcher loop                                                                                                           |
| `libraries.py`             | Registered-library CRUD/validation, multi-import-path scan, unregister flows, status endpoints                                             |
| `library_events.py`        | Best-effort single-process SSE fan-out for library/job progress                                                                            |
| `video.py`                 | Range-capable original video streaming and cached poster generation                                                                        |
| `health.py`                | `/api/health`, favicon, git commit reporting                                                                                               |
| `static_files.py`          | `/`, `/api/landing-pages`, and production SPA fallback                                                                                     |
| `scan_worker.py`           | Background catalog scan/rebuild worker, durable job queue, startup stale-job recovery, queue_scan/queue_rebuild/run_once/start/stop        |

### Domain Packages

| Package / Module                     | Purpose                                                   |
| ------------------------------------ | --------------------------------------------------------- |
| `metadata_store/`                    | SQLite data access layer: schema, search, CRUD, job queue |
| `metadata_store/_db.py`              | SQLite connection, init flags, shared constants           |
| `metadata_store/_schema.py`          | Schema creation, v1 compatibility handling, and additive post-v1 columns/indexes |
| `metadata_store/types.py`            | Shared dataclasses and exceptions                         |
| `metadata_store/path_utils.py`       | Path normalization and overlap helpers                    |
| `metadata_store/library_store.py`    | Library CRUD                                              |
| `metadata_store/job_store.py`        | Catalog job queue management                              |
| `metadata_store/rebuild_store.py`    | Staging area for rebuild operations                       |
| `metadata_store/browse_store.py`     | Browse listing queries                                    |
| `metadata_store/file_index.py`       | File index operations                                     |
| `metadata_store/folder_index.py`     | Folder index operations                                   |
| `metadata_store/metadata_queue.py`   | Durable metadata index job queue primitives, completion invariants, and stale guards |
| `metadata_store/metadata_persist.py` | Metadata persistence helpers                              |
| `metadata_store/search_store.py`     | FTS5 search queries                                       |
| `metadata_store/ranked_search.py`    | Tiered search candidates and opaque keyset cursors        |
| `metadata_store/search_index_store.py` | Derived-index states, fenced jobs, keyset asset batches, and extraction fingerprints |
| `metadata_store/inspector_store.py`  | Library Inspector data access                             |
| `metadata_store/_asset_store.py`     | Shared asset upsert helper                                |
| `metadata_store/_resources.py`       | Image resource parsing helpers                            |
| `metadata_store/status_store.py`     | Unified catalog status query builder                      |
| `tests/`                             | Backend test suite (pytest)                               |

### Route Reference

| Endpoint                                  | Purpose                                                               | Module              |
| ----------------------------------------- | --------------------------------------------------------------------- | ------------------- |
| `GET /api/browse`                         | Return folders and paginated mixed-media rows from catalog rows for a library | `browse.py`         |
| `GET /api/folders`                        | Return direct non-hidden child folders for sidebar expansion          | `folders.py`        |
| `GET /api/image`                          | Serve an original image file                                          | `images.py`         |
| `GET /api/thumbnail`                      | Serve a cached WebP thumbnail, default max long edge 512px            | `thumbnails.py`     |
| `GET /api/preview`                        | Serve a cached WebP preview, default max long edge 1440px             | `thumbnails.py`     |
| `GET /api/video`                          | Stream an original video with HTTP Range support                      | `video.py`          |
| `GET /api/video/poster`                   | Serve a cached WebP poster generated with ffmpeg                      | `video.py`          |
| `GET /api/metadata`                       | Extract and normalize AI generation metadata for one image            | `metadata_parse.py` |
| `GET /api/search`                         | Cursor-paginated unified search media stream plus first-page album suggestions, including fielded metadata queries | `search.py`         |
| `POST /api/search/query`                  | Canonical Search V2 body with versioned ID-based scope, structured filters, and opaque cursor paging    | `search.py`         |
| `POST /api/search/related`                | Bounded reference-asset relation request with explicit profile, reason, score, and index-status models   | `related_assets.py` |
| `POST /api/search/prompt-usage/query`     | Normalized prompt-group usage within an authorized canonical scope                                      | `search.py`         |
| `POST /api/search/workflow/raw`           | Opt-in literal trigram search over size/budget-bounded canonical workflow JSON                           | `search.py`         |
| `GET /api/search/capabilities`            | Enabled modes, scopes, fixed limits/registries, and required derived indexes                            | `search_indexes.py` |
| `GET /api/search/indexes`                 | Per-library derived-index state with separate usability and active job progress                         | `search_indexes.py` |
| `POST /api/search/indexes/{name}/rebuild` | Queue one durable missing/full rebuild; duplicate active work returns 409                               | `search_indexes.py` |
| `GET /api/search/index-jobs/{id}`         | Inspect one durable derived-index job                                                                    | `search_indexes.py` |
| `POST /api/search/index-jobs/{id}/cancel` | Idempotently request or finish cancellation                                                              | `search_indexes.py` |
| `GET /api/search-metadata`                | Legacy metadata-only search endpoint                                  | `search.py`         |
| `GET /api/library/inspector`              | Bounded read-only rows for the desktop metadata inspector             | `search.py`         |
| `GET /api/library/inspector/metadata`     | DB-first full metadata detail for one inspector row                   | `search.py`         |
| `GET /api/facets`                         | DB-derived model/tool/sampler/etc. aggregation counts                 | `facets.py`         |
| `POST /api/open-folder`                   | Open a folder in the OS file explorer when enabled                    | `folders.py`        |
| `GET /api/health`                         | Return service health and commit metadata                             | `health.py`         |
| `GET /api/landing-pages`                  | List intro page HTML templates from `frontend/public/landpage/`       | `static_files.py`   |
| `GET /api/maintenance/runtime`            | Return global runtime diagnostics and metadata lifecycle counters     | `maintenance.py`    |
| `GET /api/libraries`                      | List libraries with ordered import paths and exclusions               | `libraries.py`      |
| `GET /api/libraries/status`               | Return admin batch status for all libraries                           | `libraries.py`      |
| `POST /api/libraries`                     | Register a library using import_paths                                 | `libraries.py`      |
| `POST /api/libraries/validate`            | Validate create settings without writing                              | `libraries.py`      |
| `POST /api/libraries/scan-all`            | Queue one update job per registered library                           | `libraries.py`      |
| `GET /api/stats`                          | Return aggregate statistics across registered libraries               | `libraries.py`      |
| `GET /api/jobs`                           | Return recent library-management jobs                                 | `libraries.py`      |
| `GET /api/jobs/{job_id}`                  | Return one library-management job                                     | `libraries.py`      |
| `GET /api/events`                         | Stream best-effort library job and progress events over SSE           | `libraries.py`      |
| `PATCH/PUT /api/libraries/{id}`           | Replace supplied library settings                                     | `libraries.py`      |
| `GET /api/libraries/{id}`                 | Return library details                                                | `libraries.py`      |
| `POST /api/libraries/{id}/validate`       | Validate update settings without writing                              | `libraries.py`      |
| `GET /api/libraries/{id}/progress`        | Return progressive discovery and metadata coverage                    | `libraries.py`      |
| `POST /api/libraries/{id}/scan`           | Update every import path in one library                               | `libraries.py`      |
| `GET /api/libraries/{id}/status`          | Return unified status envelope for a library or path scope            | `libraries.py`      |
| `GET /api/libraries/{id}/stats`           | Return aggregate media statistics for one library                     | `libraries.py`      |
| `GET /api/libraries/{id}/offline-assets`  | List exact unavailable image/video catalog rows                       | `libraries.py`      |
| `DELETE /api/libraries/{id}/offline-assets?confirm=true` | Forget unavailable media rows and dependent derivative jobs without deleting source files | `libraries.py` |
| `GET /api/libraries/{id}/jobs`            | Return recent jobs for one library                                    | `libraries.py`      |
| `DELETE /api/libraries/{id}?confirm=true` | Unregister catalog data without deleting source files                 | `libraries.py`      |
| `GET /api/derivatives/status`             | Return policy-aware thumbnail/preview coverage, convergence, quota, job counts, and worker health | `libraries.py`      |
| `POST /api/derivatives/warm`              | Explicitly queue missing configured images for one library; optional `kind=thumbnail\|preview` limits scope | `libraries.py`      |
| `POST /api/maintenance/imported-data/clear` | Clear imported catalog, metadata, and generated-image data          | `maintenance.py`    |
| `POST /api/maintenance/imported-data/rebuild` | Clear imported data and queue whole-library rebuild jobs          | `maintenance.py`    |
| `POST /api/maintenance/catalog/reset`     | Reset catalog database data, including registered libraries           | `maintenance.py`    |
| `GET /` and `GET /{path:path}`            | Serve the built SPA in production mode                                | `static_files.py`   |

### Backend Behavior

- `PATH_SAFETY_ROOT` is the outer filesystem safety boundary. Media routes additionally require an active registered-library catalog asset of the expected type; registered folder scopes must be owned and non-excluded. Safety-root escapes return `403`, while catalog-invisible paths return `404`.
- In production nginx owns browser Basic Auth and injects a secret header. FastAPI validates that header on every `/api` router and refuses production startup unless the shared secret is at least 32 characters.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- `ENABLE_METRICS` defaults to enabled outside production and exposes `/metrics` with route-level labels.
- `ENABLE_PROFILER=0` by default. When enabled, selected endpoints are profiled with pyinstrument and HTML reports are written to `backend/profiles/`.
- Original images are served only by `/api/image`; thumbnails and previews are generated derivatives.
- Original media and generated derivatives use ETags with `Cache-Control: public, max-age=0, must-revalidate`, so source identity changes are visible on the next request instead of being hidden by immutable browser caching.
- Video streaming supports one byte range, clamps a satisfiable end at EOF, returns `416` for malformed/empty/multi-ranges or invalid starts, and honors strong-ETag and HTTP-date `If-Range`; a mismatched validator receives the full `200` representation.
- Derivative cache keys include kind, cache version, resolved path, mtime, size, long-edge target, format, and quality. WebP files persist under `backend/.cache/thumbnails/`.
- Derivative claims use fenced tokens and 15-minute leases. Missing/inactive/current-source races terminate only their job; the supervisor replaces dead workers and recovers abandoned claims.
- The metadata DB defaults to `backend/.cache/gallery_metadata.db` and can be overridden with `GALLERY_METADATA_DB`.
- SQLite uses WAL mode and stores both file index rows and normalized metadata rows. FTS5 tables cover folder/photo names and metadata text.
- Catalog-only search/facet predicates correlate assets by `(library_id, path)`,
  matching the catalog's composite index instead of performing a per-file asset
  table scan.
- Catalog schema version 11 additively creates
  `asset_visual_fingerprints`, eight per-asset `asset_visual_hash_bands`, and
  the `(hash_kind, band_no, band_value, library_id, asset_id)` candidate index.
  Its `.v10.bak` migration creates storage only and never decodes or backfills
  media inline. Version 10 creates
  `asset_generation_signatures` and its library/hash candidate indexes. The
  `.v8.bak` migration performs no inline backfill, checks foreign keys, and
  publishes version 10 last; version 9 remains a historical reset sentinel.
  Version 8 creates `workflow_raw_documents`, its
  external-content trigram FTS table, and visible skipped-index counters; its
  `.v7.bak` migration performs no backfill. Version 7 creates typed `workflow_nodes` and
  `workflow_property_values` with fixed per-type lookup indexes; its `.v6.bak`
  migration creates storage only and leaves extraction to the durable
  `workflow_properties` index. Version 6 creates normalized
  `asset_prompt_values`, per-asset observed model identities, and
  `model_identity_aliases`; its `.v5.bak` migration creates storage only and
  leaves backfill to the durable `prompt_values` search-index job. Version 5
  creates `search_index_states`, `search_index_jobs`, and
  `asset_search_extractions`; it never backfills inline.
  The migration creates `.v4.bak`, runs under one `BEGIN IMMEDIATE`, checks
  foreign keys, and publishes `user_version=5` last. Version 4 still owns the
  unambiguous `file_index.library_id` backfill and `.v3.bak`; earlier versions
  retain their `.v2.bak` and `.v1.bak` rollback behavior.
- Registered libraries store ordered roots in `library_import_paths`. Relative globstar exclusions live in `library_exclusion_patterns`.
- `/api/browse` is the read-only catalog query endpoint. It accepts `library_id`, `path`, `cursor`, `limit`, and `include_offline`. The response contains `folders`, `media`, `next_cursor`, legacy alias `next_media_cursor`, `total_images`, `total_videos`, `total_assets`, `request_path`, `index_source`, `library_id`, and `path`. Image media rows also include `derivative_ready` for thumbnail/preview readiness; the frontend treats this as a loading/preload hint, not visible user-facing status. Catalog update and status are managed through library endpoints; imported-data clear, rebuild, and catalog reset are managed through maintenance endpoints.
- Catalog scan workers, the DB-claim metadata lifecycle worker, the single
  derived-search-index writer, the derivative scheduler, and the integrity
  checker run as background services. The catalog watcher and scheduled
  reconciliation are enabled by default for registered libraries.
- The enabled `prompt_values` derived index reads only persisted
  `image_metadata`/checkpoint-resource rows. It NFKC-normalizes and casefolds
  prompt identities, keeps positive and negative values distinct, and updates
  observed model-name/hash aliases without reopening source media.
- The enabled `generation_signatures` index reads only current persisted image
  metadata and normalized resources. Its versioned prompt atoms are NFKC,
  whitespace-collapsed, casefolded identities with bounded supported emphasis;
  positive/negative prompts cap at 64 atoms and candidate queries cap at 16.
  Compact SHA-256 layers separate prompt, generation family, recorded recipe,
  and exact deterministic settings. Hash identities win over name fallbacks,
  missing inputs are explicit, numeric values use canonical finite decimals,
  and only bounded registry-typed workflow properties participate. A common
  model, sampler, or seed without prompt evidence cannot form a strong family.
  Metadata persistence invalidates stale rows transactionally and coalesces a
  durable missing backfill; active assets are processed in the existing
  200-row single-writer batches and failures degrade only this optional index.
- Related metadata requests collect at most 600 distinct candidates from
  bounded signature, observed-model-identity, resource, optional
  typed-workflow, and prompt-FTS branches. Each branch performs its own direct
  indexed active/current-source/scope join and applies its cap before candidate
  IDs are united; the request does not materialize a catalog-wide eligibility
  CTE. Prompt FTS uses at most 16 versioned distinctive atoms and excludes
  common boilerplate from candidate lookup. The `recipe` profile executes only
  exact/recipe signature branches. Metadata rows are loaded only for the
  bounded union, and the SQLite read closes before deterministic
  weighted prompt/resource/workflow/settings scoring. Fixed tiers 100/90/80/
  70/60/40 and stable evidence codes determine ordering before mtime and
  `asset_id` tie-breakers. Same model, sampler, seed, folder, orientation, or
  common boilerplate alone never creates a result. The `recipe` profile keeps
  only exact-signature and same-recipe tiers; missing workflow-property rows
  safely reduce candidate evidence without disabling metadata ranking.
- The optional `visual_fingerprints` index uses only current persisted
  thumbnail/preview derivatives. Its background extractor applies EXIF
  transpose, composites alpha onto white, computes horizontal and vertical
  64-bit dHash plus a 4x4 RGB grid, and persists the fingerprint and eight
  16-bit bands atomically. Missing derivatives queue the normal `thumb_512`
  variant at low priority; successful derivative completion invalidates a
  pending extraction and coalesces durable retry work. Decode/hash work occurs
  outside SQLite writes, and related HTTP handlers never open an image.
- Visual requests probe exact and one-bit alternatives for each indexed
  16-bit band, cap the candidate pool at 500, then use Python `int.bit_count()`
  for exact Hamming distance. Color-grid and aspect-ratio distances only reject
  or order weak dHash matches; they are not semantic features. Resize and
  re-encode matches use tier 80, light modifications use tier 60, and every
  result carries `visual_variant`. Large crops, mirrors, rotations, and
  generative composition changes are documented limitations; a visual match
  does not prove prompt, recipe, lineage, or common source.
- A relation index in `building` state remains queryable when its persisted
  coverage is marked usable; unusable building coverage returns the typed
  retryable readiness error. Combined requests keep available metadata results
  when visual coverage is missing, building, degraded, failed, or disabled.
- The enabled `workflow_properties` index accepts only the code-owned ComfyUI
  registry advertised by search capabilities. API prompt graphs provide named
  inputs; supported UI graph widgets use a versioned positional map. Search
  predicates compile to fixed same-node `EXISTS` SQL with bound values, while
  links, containers, non-finite numbers, and unsupported identifiers are not indexed.
- Raw workflow search is disabled by default and owns a separate durable index.
  Enabled extraction compacts supported JSON without truncation, skips per-file
  or total-budget overflow into degraded status, and queries only trigram FTS.
  Reads use a dedicated query-only SQLite connection with a 250 ms progress
  deadline; timeout returns a typed complete failure rather than partial rows.
  Legacy `param:`/`advanced:` keys are limited to
  `[A-Za-z_][A-Za-z0-9_]{0,127}` and JSON paths and values remain bound parameters.
- FastAPI lifespan startup registers each stop callback immediately after its service starts. Startup failures and normal shutdown unwind callbacks in reverse order, attempt every cleanup, and log incomplete stops without masking the initiating failure.
- Unexpected exceptions are logged server-side with tracebacks. Public `500` responses use a generic message; durable background-job error fields retain bounded operational detail.
- The catalog service owns a supervisor thread. Each running job has a durable
  worker owner, unique claim token, and renewable lease; progress/completion is
  fenced by the token and unexpired lease. Scan writes are split into bounded
  transactions so the heartbeat can run between batches. Each scan batch,
  rebuild staging flush, rebuild activation, and reconciliation transaction
  validates the claim at entry and refreshes the same token immediately before
  commit; this remains safe if wall-clock expiry passes while its `BEGIN
  IMMEDIATE` prevents any recovery write from interleaving. Terminal job and
  library state commit atomically. Metadata job enqueueing also receives the
  catalog claim, splits its path list into bounded transactions, and refreshes
  before every commit rather than relying on a pre-dispatch assertion.
  In-process heartbeats register their active `(job_id, claim_token)` while work
  runs. Runtime recovery does not fence an expired claim whose owner thread and
  exact heartbeat token are both still live; after a global SQLite writer
  releases the lock, that token may renew even if its prior deadline passed.
  Claiming and active-token registration are serialized with the runtime
  supervisor, and heartbeat setup/event publication are inside the executor's
  cleanup boundary. When an executor returns, `run_once()` stops and
  unregisters the heartbeat, then token-fence-fails any row that is still
  `running` with that same claim. If that close transaction is temporarily
  blocked, runtime recovery treats a live worker's unregistered token as
  abandoned regardless of its renewed lease. Both close paths clear claim
  fields, remove rebuild staging, and move an indexing library to `error` in
  the same transaction. Dead owners and startup claims have no live-token
  protection and remain recoverable.
  Recovery deletes the recovered rebuild's staging rows in the same transaction
  and recomputes aggregate parents from both direct and dependency-table links
  only at startup or when a child actually recovered. Startup and runtime
  recovery otherwise restore the configured worker count independently of
  status traffic. Library and maintenance GET endpoints only observe state.
- Scheduled reconciliation records durable attempt time before queueing, even
  when work coalesces or maintenance is busy. Eligible libraries are ordered by
  oldest attempt, with never-attempted libraries first, so bounded ticks remain
  fair. Watcher drains are deterministic and bounded; overflow stays pending
  for the next tick.

## Frontend

Key paths:

| Path                                                      | Role                                                                                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `frontend/src/main.ts`                                    | Vue entry, global styles, Pinia, Vue Router, TanStack Query installation, dev debug utilities                                  |
| `frontend/src/router/index.ts`                            | Routes: `/` gallery, `/metadata` Library Inspector, `/admin/libraries`, `/admin/libraries/:id`, `/admin/maintenance`, fallback redirect |
| `frontend/src/App.vue`                                    | Root shell, layout dispatch, lightbox/settings/toast mounting, Query Devtools in dev                                           |
| `frontend/src/layouts/`                                   | Desktop, tablet, and mobile layout shells                                                                                      |
| `frontend/src/components/GalleryGrid.vue`                 | Main gallery renderer, browse album/photo sections, and search-query orchestration                                             |
| `frontend/src/components/Lightbox.vue`                    | Device-dispatch lightbox orchestrator with the image-level Related Assets action                                               |
| `frontend/src/components/RelatedAssetsPanel.vue`          | Canonical metadata/visual relation sheet, profile filters, coverage states, evidence, and lightbox handoff                     |
| `frontend/src/components/GenerationFamilySummary.vue`     | Recorded family/recipe counts and generation-setting comparison without provenance claims                                     |
| `frontend/src/components/LibraryInspector.vue`            | Desktop metadata inspection table at `/metadata`; TanStack Table for returned-row sorting plus TanStack Virtual for table rows |
| `frontend/src/components/admin/LibraryListPage.vue`       | Admin registered-library list, update-all entrypoint, status summaries, and navigation to library detail pages                  |
| `frontend/src/components/admin/LibraryDetailPage.vue`     | Admin library detail with status/progress, generated-image coverage, live watcher/refresh state, problems, jobs, and dialogs   |
| `frontend/src/components/admin/MaintenancePage.vue`       | Admin maintenance page with file-health sections, global generated-file actions, and active job visibility                      |
| `frontend/src/components/SortSelect.vue`                  | shadcn-vue Select sort control used by gallery desktop/tablet toolbars and the Library Inspector                               |
| `frontend/src/components/SortDropdown.vue`                | Dropdown-menu sort control still used by the mobile header                                                                     |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | Shared metadata/discovery composition sheet and canonical-request emitter                                                     |
| `frontend/src/components/search/SearchLibraryPopover.vue` | Browser-local saved/recent search actions                                                                                      |
| `frontend/src/components/search/PromptUsagePanel.vue`     | Query-backed positive/negative prompt groups and exact-group action                                                            |
| `frontend/src/components/search/WorkflowFilterBuilder.vue` | Capability-driven typed same-node predicate drafts                                                                             |
| `frontend/src/components/search/RawWorkflowSearch.vue`    | Optional acknowledged Apply-only raw workflow query                                                                            |
| `frontend/src/components/search/SearchIndexStatusPanel.vue` | Query-backed derived-index readiness, rebuild, and cancellation                                                               |
| `frontend/src/components/search/SearchResultsPanel.vue`   | Virtualized album/media search sections, page loading, and typed open/retry actions                                            |
| `frontend/src/components/search/SearchFeedback.vue`       | Pending, blocking-error, stale-warning, pagination-error, and successful-empty search states                                   |
| `frontend/src/components/search/SearchResultMetadata.vue` | Escaped match/snippet/generation/library context for one search result                                                         |
| `frontend/src/components/ui/`                             | shadcn-vue/Reka-inspired local UI primitives                                                                                   |
| `frontend/src/composables/`                               | Query wrappers including Related Assets, device detection, PhotoSwipe lifecycle, metadata/comparison helpers, theme, haptics  |
| `frontend/src/query/`                                     | TanStack Query client, normalized query keys, browse prefetch helpers                                                          |
| `frontend/src/db/`                                        | TanStack DB beta foundation and landing-pages pilot collection                                                                 |
| `frontend/src/stores/`                                    | Pinia stores for gallery UI/navigation, lightbox, Related Assets session UI, and toasts                                        |
| `frontend/src/services/api.ts`                            | Axios client, endpoint wrappers, URL helpers, API error mapping                                                                |
| `frontend/src/styles/`                                    | Tailwind 4 entry, shadcn token bridge, SCSS tokens, breakpoints, lightbox styles                                               |

### State Ownership

| Layer                | Responsibilities                                                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| TanStack Query       | `/api/browse`, `/api/folders`, `/api/search/query`, `/api/search/related`, `/api/metadata`, `/api/facets`, library status/jobs/stats, generated-image status/actions, Library Inspector rows/details, landing page fetches |
| TanStack DB          | Beta local reactive collection foundation; currently only the landing-pages collection is a runtime pilot                                             |
| Pinia gallery store  | Root/current path, selected path, history, expanded folders, search text/scope, sort, loaded flags, settings UI state                                 |
| Pinia lightbox store | Open image, current index, visible item list, navigation                                                                                              |
| Pinia related store  | Ephemeral open/reference/scope/profile UI state; no related result payloads and no saved/recent-search persistence                                  |
| Pinia toast store    | Toast API adapter (Gallery API → Sonner): IDs, variants, durations, dismiss, clear, actions, visible-toast limit; Sonner owns render/dismiss mechanics |

Query keys are centralized in `frontend/src/query/keys.ts`. Paths are normalized by trimming, converting backslashes to forward slashes, collapsing duplicate slashes, and removing a trailing slash except for `/`.

Core keys:

```text
["landing-pages"]
["libraries"]
["libraries", "list"]
["libraries", "detail", id]
["libraries", "stats", id]
["libraries", "jobs", id]
["generated-images"]
["generated-images", "status", libraryId]
["stats", "gallery"]
["jobs"]
["jobs", "list"]
["jobs", id]
["browse"]
["browse", libraryId]
["browse", libraryId, normalizedPath, limit, includeOffline]
["browse-infinite"]
["browse-infinite", libraryId]
["browse-infinite", libraryId, normalizedPath, limit, includeOffline]
["folder-children", normalizedPath]
["search", query, scope, normalizedPath, limit]
["metadata", normalizedPath]
["facets", canonicalScope, libraryId, normalizedPath]
["related-assets", canonicalRequest]
["status"]
["status", "libraries", "batch"]
["status", "library", libraryId]
["status", "path", libraryId]
["status", "path", libraryId, normalizedPath]
["library-inspector"]
["library-inspector", query, scope, normalizedPath, limit, sort]
["library-inspector-metadata", normalizedPath]
["maintenance"]
["maintenance", "file-health"]
```

### Admin Library Health

```text
/admin/libraries
-> LibraryListPage.vue
-> library list, batch status, update-all, and per-library navigation

/admin/libraries/:id
-> LibraryDetailPage.vue
-> GET /api/libraries/{id}/status
-> GET /api/derivatives/status?library_id=...
-> Generated image cache, Live status, Problems, jobs, stats, update/edit/delete

/admin/maintenance
-> MaintenancePage.vue
-> image-cache summary by querying registered libraries
-> POST /api/maintenance/imported-data/rebuild for all-library imported-data rebuild
-> POST /api/maintenance/imported-data/clear for all-library imported-data clearing
-> POST /api/maintenance/catalog/reset from Settings Danger Zone
-> GET /api/maintenance/file-health for latest File issues and Repair results
-> POST /api/maintenance/file-health/check from Check files
-> GET /api/maintenance/runtime for catalog, metadata, and image-cache worker/queue health
```

Primary admin UI labels intentionally avoid backend terms such as derivatives,
runtime, diagnostics, and integrity. User-facing labels are `Generated image cache`,
`Live status`, `Problems`, `File issues`, `Check files`, and `Repair results`.

## Data Flow

### Folder Load

```text
Folder selection
-> Pinia gallery store updates current path/history
-> useInfiniteBrowseQuery(libraryId, path)
-> GET /api/browse?library_id=...
-> TanStack Query stores pages under ["browse-infinite", libraryId, normalizedPath, IMAGE_PAGE_SIZE]
-> GalleryGrid renders folders and mixed-media rows
```

First uncached folder loads can show a skeleton. Cached revisits render immediately and show only subtle refresh state while Query refetches in the background.

### Folder Tree Expansion

```text
FolderTreeItem toggle
-> Pinia stores expanded/collapsed path state
-> useFolderChildrenQuery(path, enabled)
-> GET /api/folders when cache policy requires it
-> FolderTreeItem renders Query-owned child folder rows
```

Folder expansion state is UI state. Query-owned `FileNode` results should not be mutated to store expansion state.

### Infinite Scroll

```text
IntersectionObserver sees load-more sentinel
-> guard hasNextPage and fetch-in-progress flags
-> fetchNextPage()
-> GET /api/browse?library_id=...&cursor=...
-> TanStack Query appends page
-> grid rows recompute
```

### Search, Advanced Search, and Facets

```text
Header search or AdvancedSearchDrawer
-> Pinia stores search text/scope
-> useSearchUrlSync() encodes versioned shareable state after library hydration
-> useSearchCapabilitiesQuery()/usePromptUsageQuery()/useSearchIndexStatusQuery() own discovery server state
-> useUnifiedSearchQuery()
-> POST /api/search/query with a canonical ID-scoped request
-> SearchResultsPanel renders first-page Album suggestions and an appended Media stream
```

- Canonical scopes are `folder` (one authorized folder recursively), `library`
  (one registered library across all import paths), and `all`. Legacy GET
  `current` resolves through the same folder context and responses report the
  canonical `folder` value.
- Search and facets share one registered-ID/path resolver. A folder outside the
  selected library, a media-file path used as a folder, or a descendant with no
  catalog folder/active descendants returns `404`; invalid/missing scope values
  are `422`.
- `/api/search/query` is the active frontend contract. It accepts schema version
  1, lexical/workflow modes, a discriminated folder/library/all scope, and
  never accepts an absolute client path. Persisted/URL forms omit cursor and
  limit; query keys omit only cursor. Legacy `GET /api/search` authorizes its
  absolute-path inputs and adapts them into the same lexical executor.
- `/api/search/related` is a separate, non-persistable reference request. It
  reuses the canonical folder/library/all scope union, authorizes an active
  image reference before reading relation data, excludes the reference from
  results, and distinguishes missing relation coverage (409) from unusable
  persisted relation data (503). Generation signatures supply bounded
  metadata candidates and visual fingerprints supply indexed near-duplicate
  candidates. The combined `related` profile merges both result streams by
  stable asset identity, retains all typed evidence, and keeps metadata results
  available when visual coverage is disabled, building, degraded, or failed.
- Derived discovery indexes use durable per-library states and jobs. Claims
  carry worker ID, opaque token, and lease; completion is fenced. Workers read
  active assets by `asset_id` keyset in batches of at most 200, extract outside
  write transactions, and atomically persist one asset's derived rows plus its
  fingerprint/status. Metadata changes atomically invalidate initialized
  prompt/workflow/raw rows and coalesce a durable missing rebuild; indexes that
  have never been initialized remain opt-in. Expired claims are recovered in
  the next claim transaction, while startup recovery remains the process-crash
  safety net. Optional index failure never disables lexical search.
- Capabilities distinguish disabled features (`409 FEATURE_DISABLED`) from an
  enabled but unusable required index (`503 SEARCH_INDEX_NOT_READY` with
  `Retry-After`). Index status exposes `state` separately from `usable`; an old
  usable index remains available with a warning during rebuild or degradation.
- Search returns bounded `media` pages with opaque string `next_cursor`, `has_more`,
  `returned`, and `limit`. Legacy `albums`, `photos`, `videos`, and `prompt`
  fields remain for compatibility; the active gallery search UI renders
  `media`.
- TanStack Query passes its `AbortSignal` through Axios. Canonical media pages
  deduplicate by `(library_id, asset_id)` and use the exact case-preserved path
  only for compatibility rows that lack IDs; legacy arrays are consumed only
  when canonical `media` is absent.
- Ranked search unions filename token-prefix candidates with trigger-maintained
  trigram filename/metadata substring candidates. Short or mixed-length tokens
  stay on Unicode FTS token/prefix semantics; full-table LIKE is reserved for
  the FTS-unavailable degraded path. Metadata trigram queries retain AND-token
  semantics, and unscoped FTS plus structured-filter-only sources use bounded,
  cursor-aware preselection before strict catalog authorization. The candidate union also includes
  positive-prompt phrase tiers, negative prompts, and structured-filter-only rows. It
  deduplicates by stable asset ID and orders by relevance tier, a
  bounded/rounded FTS rank, source `mtime_ns`, then `asset_id`.
- Active pagination is keyset-only. The versioned base64url JSON cursor is bound
  to the canonical query/scope/root fingerprint and stores the complete final
  ordering tuple. Malformed, wrong-version, or wrong-request cursors return
  `400`. Decimal cursors are accepted only by legacy `GET /api/search`, use the
  old offset path for that request, and emit `Deprecation`/`Warning` headers;
  responses always return opaque cursors.
- Media rows are joined to their active asset, registered library, and import
  path ownership in SQLite and include `asset_id`, `library_id`, and
  `library_name`. Search does not perform per-result path resolution or
  existence checks.
- Album suggestions are returned only on the first search page. Their direct
  image count, three newest direct covers, and child visibility reuse the same
  bounded catalog aggregation as DB-first browse; search never enumerates the
  source directory.
- Watcher, scan, offline-asset, and integrity workflows reconcile stale catalog
  state. Search reflects the current catalog snapshot and never schedules
  cleanup from a response.
- Fielded queries are parsed server-side, for example `prompt:"blue hair"`, `seed:12345`, `model:pony`, `steps:>25`, `width:>=1024`. A shared JSON grammar contract covers single/double quotes, escaping, operators, repeated fields, aliases, pass-through tokens, and Unicode in pytest and Vitest.
- Recognized field filters fail closed: malformed numeric comparisons, numeric
  equalities, or
  dimensions return `422` rather than silently dropping the predicate.
- Library Inspector cursors validate JSON types, finite values, and SQLite
  integer bounds before binding. Its keyset uses nanosecond mtime ordering and
  bounded DB preselection; the managed suite separately measures the API and
  the 100k-row DB-only store path. Facets materialize authorized active/current
  rows once per request instead of repeating the ownership predicate for every
  aggregation.
- Fielded search keeps metadata filters scoped to filterable image/prompt
  media; filename-only videos are not returned for fielded queries unless a
  future video metadata index supports the same predicates.
- The shared Advanced Search drawer is owned by `App.vue`, uses TanStack Form
  for fielded metadata drafts, and composes separate saved/recent, prompt,
  workflow, raw, and index-status children. Children keep local drafts and emit
  typed canonical requests; `App.vue` applies library/import-path navigation
  and Pinia session state. It renders as a right sheet on tablet/desktop and a
  full-width sheet on compact mobile viewports.
- TanStack Query owns capabilities, prompt usage pages, index states/jobs, raw
  search mutations, facets, and canonical result pages. Pinia owns only the
  active query/scope/mode/filters and navigation/UI state. Filter-only prompt
  or workflow requests are active searches even when their lexical text is empty.
- Active search replaces browse sorting with a visible `Relevance` label. Search feedback distinguishes initial pending, blocking error, stale-data warning, next-page error, and successful empty states on desktop, tablet, and mobile.
- Image-card and lightbox overflow actions open the global Related Assets
  sheet with the current canonical scope. `related` is the default profile;
  `recipe` and `visual` are explicit tabs. TanStack Query owns each complete
  reference/profile/scope response and forwards cancellation through Axios.
  Reference changes use a new key and do not show the prior reference's data;
  a failed background refresh retains the last successful response with a
  visible retry action. The ephemeral Pinia store owns only sheet state.
- Related results reuse `PhotoCard` and the existing lightbox item list. Stable
  reason codes map to concise evidence chips and fixed tier labels. The family
  summary compares only recorded seed, sampler, scheduler, steps, CFG,
  dimensions, model, LoRA/resources, denoising, hires, and VAE values and says
  `same recorded settings`, never lineage or probability.
- Smart-collection descriptors contain either a canonical Search V2 request or
  a persisted relation/fact descriptor. They do not persist materialized asset
  membership and Related Assets sessions never enter saved/recent search state.
- Search URL state uses `search_v=1` plus bounded base64url structured groups.
  Debounced edits replace browser history; committed actions push; guarded
  hydration applies Back/Forward without a write loop. Saved searches (50) and
  successful recent searches (20) are versioned, browser-local, and preserve
  case-sensitive values.
- `GET /api/search-metadata` remains available for older callers, returns the
  catalog-filtered global total, and follows the same DB-only response policy;
  the main gallery UI uses `POST /api/search/query`.
- Search, legacy metadata search, and facets use regular Pydantic response
  models and explicit synchronous FastAPI path operations. OpenAPI documents
  canonical media/album rows, legacy projections, facet values, opaque cursor
  types, sanitized 400/404/503/500 envelopes, and the `422` union of public API
  errors plus FastAPI validation errors.
- Desktop search surfaces show a fixed Relevance indicator while lexical or
  structured search is active; ordinary browsing uses `SortSelect.vue`.
  `MobileHeader.vue` still uses `SortDropdown.vue` outside search.

### Library Inspector

```text
/metadata route
-> LibraryInspector.vue
-> useLibraryInspectorFilters + useInfiniteLibraryInspectorQuery
-> GET /api/library/inspector
-> model/prompt filters and name/date sort are applied by SQLite before cursor pagination
-> LibraryInspectorToolbar.vue owns typed filter/sort/column controls
-> TanStack Table uses the server order and owns column visibility/header state
-> TanStack Virtual renders the table body rows
-> popovers/copy actions fetch GET /api/library/inspector/metadata
```

The inspector is read-only. It is backed by indexed SQLite metadata and opens images in the same lightbox store used by the gallery. Model and prompt-presence predicates are applied before the SQL limit/cursor, so an empty visible page means the filtered result is exhausted rather than merely absent from already-loaded client pages. The table uses cursor-based infinite pagination plus body virtualization, so the DOM only contains the visible row window plus small overscan/spacer rows rather than every loaded row.

### Open Image

```text
PhotoCard or inspector row click
-> lightboxStore.open({ path, name }, visibleImages)
-> PhotoSwipe wrapper opens derivative-first item
-> usePhotoMetadataQuery(path)
-> GET /api/metadata
-> active device panel/sheet renders metadata
```

PhotoSwipe normal `src` is `/api/preview`. The original `/api/image` is used for explicit original-load paths such as zoom/fullscreen/download settings or animated images.

## Lightbox Design

`Lightbox.vue` dispatches by device:

```text
Desktop/Wide -> PhotoSwipeViewer.vue + LightboxDesktopPanel.vue
Tablet       -> TabletPhotoSwipe.vue + LightboxTabletPanel.vue
Mobile       -> MobilePhotoSwipe.vue + LightboxMobileSheet.vue
```

- All PhotoSwipe wrappers share `usePhotoSwipe.ts` for lifecycle, item creation, index sync, and destroy guards.
- Lightbox item URL construction lives in `frontend/src/utils/lightbox.ts`.
- Desktop reserves `DESKTOP_METADATA_WIDTH` through PhotoSwipe padding so the image is not hidden under the metadata sidebar.
- Tablet uses custom top/bottom controls and a bottom metadata panel.
- Mobile uses `@douxcode/vue-spring-bottom-sheet` as a non-modal metadata sheet inside PhotoSwipe.

Mobile sheet contract:

- PhotoSwipe owns image rendering, swipe, pan/zoom, keyboard/focus context, and lightbox lifecycle.
- VSBS owns mobile sheet drag, snap, scroll, and animation only.
- Gallery glue owns the info button, outside-tap sheet close, tab content, copy actions, prompt expansion, and protections that preserve PhotoSwipe gestures.
- Keep VSBS `blocking=false`; do not add a second focus trap inside PhotoSwipe.

## Layout Dispatch

`App.vue` selects the layout from `useDevice()`:

```vue
<MobileLayout v-if="isMobile" />
<TabletLayout v-else-if="isTablet" />
<DesktopLayout v-else />
```

| Device                  | Layout              | Sidebar                        | Grid                      |
| ----------------------- | ------------------- | ------------------------------ | ------------------------- |
| Mobile `<768px`         | `MobileLayout.vue`  | Overlay/mobile shell           | Native scroll             |
| Tablet `768-1199px`     | `TabletLayout.vue`  | Drawer/sidebar shell           | TanStack Virtual row grid |
| Desktop/Wide `>=1200px` | `DesktopLayout.vue` | Persistent/collapsible sidebar | TanStack Virtual row grid |

## Fragile Contracts

- Keep `useDevice.ts`, `_breakpoints.scss`, and `useColumnResize.ts` synchronized when changing breakpoints.
- Keep desktop lightbox `DESKTOP_METADATA_WIDTH`, `--lightbox-sidebar-width`, PhotoSwipe `paddingFn`, counter positioning, and next-arrow offset synchronized.
- Keep mobile sheet drag/snap/scroll delegated to VSBS; do not restore the old custom pointer-drag sheet implementation.
- Keep mobile outside-tap close non-blocking: no `stopPropagation()`, track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the movement threshold, and handle `pointercancel`.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep Query as the owner of server/API data and Pinia as the owner of UI/navigation state.
- Do not move browse, infinite loading, folder tree, unified search, or lightbox metadata into TanStack DB without a dedicated collection-state design.
- Keep shadcn-vue Select controls as the metadata toolbar contract for model, prompt, and sort filters. `toolbarTrigger.ts` is a shared dropdown/button trigger class, but `SortSelect.vue` uses the local `SelectTrigger` styling directly.
