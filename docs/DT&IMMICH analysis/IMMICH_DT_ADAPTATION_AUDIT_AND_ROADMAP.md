# Immich / DiffusionToolkit Adaptation Audit and Roadmap

Last reviewed: June 19, 2026

## Executive summary

`gallery-repo` has already adapted most of the Immich and DiffusionToolkit
patterns that are useful for a local AI-image gallery:

- folder navigation does not wait for metadata parsing or PIL image decoding;
- metadata indexing is durable, coalesced, bounded, and batch-written to SQLite;
- warm metadata, search, facets, and optional folder listings are database-backed;
- thumbnails and previews are persistent, versioned derivatives;
- the lightbox uses thumbnail -> preview -> original quality promotion;
- metadata does not gate the lightbox overlay;
- the frontend virtualizes large visual and tabular result sets;
- performance budgets and endpoint instrumentation are part of the repository.

The current architecture is therefore not a failed attempt to copy Immich or
DiffusionToolkit. It is a deliberate hybrid that protects ad-hoc folder-open
latency while progressively building a prepared library.

The remaining problems are operational rather than conceptual:

1. dimensions can be present in `image_metadata` but absent from `file_index`;
2. derivative rendering runs on the shared request threadpool without dedicated
   concurrency control or same-key request coalescing;
3. derivatives are normally generated on demand, without durable readiness,
   priority, warming, or maintenance state;
4. neighbor preloading does not guarantee that preview, dimensions, and metadata
   are all ready before navigation;
5. some performance tests mix browser actionability delay, animation duration,
   cold generation, and warm-cache latency into one budget.

This document recommends two distinct policies:

- **Do not copy either upstream architecture 100%.** PostgreSQL, Redis/BullMQ,
  multi-user storage semantics, ML queues, WPF-specific image loading, eager
  full-file hashing, and synchronous viewer parsing are not appropriate default
  dependencies for this project.
- **Do adopt the relevant behavioral guarantees completely.** The target roadmap
  is a persistent multi-library, DB-first catalog with a durable derivative
  catalog, bounded priority workers, full default warming, progressive indexed
  results, configured-root watchers, and quota-controlled regeneration.

That target is intentionally closer to Immich operationally, while remaining a
single-process FastAPI/Vue/SQLite application.

## Scope, evidence, and confidence

### Repositories and revisions

| Repository | Revision inspected | Date/context |
| --- | --- | --- |
| `gallery-repo` | `113b3a4` | Local checkout on 2026-06-19 |
| Immich | [`38920fc4cac8cbdbeb35fecf930583d875d033ba`](https://github.com/immich-app/immich/tree/38920fc4cac8cbdbeb35fecf930583d875d033ba) | `v3.0.0-rc.2`, 2026-06-18 |
| DiffusionToolkit | [`153409c3a0e9569886e6601530365808d4ecbb0e`](https://github.com/RupertAvery/DiffusionToolkit/tree/153409c3a0e9569886e6601530365808d4ecbb0e) | Current upstream HEAD at review time |

The earlier Immich audit used commit `f382624e`. The relevant upstream
guarantees were rechecked at `38920fc`: thumbnail-generation concurrency remains
bounded, derivative files remain cataloged, the viewer still promotes
thumbnail -> preview -> original, and previous/next assets are still preloaded.

### Primary upstream evidence

Immich:

- [default queue concurrency and image derivative sizes](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/server/src/config.ts)
- [thumbnail/preview generation jobs and asset-file persistence](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/server/src/services/media.service.ts)
- [asset dimensions and identity](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/server/src/schema/tables/asset.table.ts)
- [derivative file catalog](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/server/src/schema/tables/asset-file.table.ts)
- [adaptive thumbnail/preview/original loader](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/web/src/lib/utils/adaptive-image-loader.svelte.ts)
- [previous/next viewer preload manager](https://github.com/immich-app/immich/blob/38920fc4cac8cbdbeb35fecf930583d875d033ba/web/src/lib/components/asset-viewer/PreloadManager.svelte.ts)

DiffusionToolkit:

- [metadata scan channel and workers](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/MetadataScannerService.cs)
- [batched database writer](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/DatabaseWriterService.cs)
- [two-worker thumbnail queue](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Thumbnails/ThumbnailService.cs)
- [thumbnail cache](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Thumbnails/ThumbnailCache.cs)
- [viewer path that reparses metadata synchronously](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Pages/Search.xaml.cs)
- [filesystem watcher behavior](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/FolderService.cs)

Local supporting documents:

- [Immich Media Pipeline Audit](IMMICH_PIPELINE_AUDIT.md)
- [DiffusionToolkit Pipeline Audit](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md)
- [Media Pipeline Comparison](MEDIA_PIPELINE_COMPARISON.md)
- [Architecture](../ARCHITECTURE.md)
- [Performance Testing](../test-debug-perf/PERFORMANCE_TESTING.md)

The upstream conclusions are based on source inspection, not a cross-project
benchmark on identical hardware. Performance comparisons below distinguish
verified local measurements from architectural inference.

## Pattern status overview

| Pattern | Main reference | Current gallery status | Classification |
| --- | --- | --- | --- |
| Scan does not block on metadata/PIL | Immich + web hot-path design | Complete | Done |
| Background metadata indexing | Immich/DT | Durable SQLite jobs, coalescing, bounded workers | Done |
| Batch SQLite writes | DT | Implemented | Done |
| Index status/progress | Immich/DT | `/api/index/status` and rebuild UI | Done |
| DB-first metadata on warm cache | Immich | Implemented | Done |
| Warm folder listing | Immich/DT | DB path with direct-scan fallback | Done for current hybrid contract |
| Persistent thumbnail/preview cache | Immich/DT | Implemented | Done |
| Path/mtime/size cache invalidation | Gallery-specific adaptation | Implemented | Done |
| Derivative-first lightbox | Immich | Thumbnail -> preview -> original | Done at source-policy level |
| Original on zoom/fullscreen/preference | Immich | Implemented | Done |
| Separate derivative roles/cache keys | Immich | Implemented | Done |
| Metadata does not block overlay | Immich; avoids DT weakness | Implemented | Done |
| Neighbor preload | Immich | Thumbnail/preview only, incomplete readiness | Partial |
| Watcher/scheduled refresh | Immich/DT | Implemented, optional | Done for current hybrid; target policy changes |
| AI metadata parsing/search | DT | Broad parser and indexed search | Done |
| Fielded search/facets | DT/Immich | Implemented | Done |
| Virtualized grid/list | Immich scale pattern | Implemented | Done |
| Perf tests/instrumentation | Gallery-specific | Implemented | Done; metric semantics need refinement |
| Dedicated derivative workers | Immich/DT | Missing | Planned |
| Derivative readiness/catalog | Immich | Missing | Planned |
| Full derivative warming | Immich-style prepared library | Missing | Planned |
| Dimension invariants across catalog tables | Immich DTO guarantee | Incomplete | Planned |

## Patterns already adapted successfully

These patterns are considered complete for the current implementation. The
roadmap must preserve their guarantees even when the storage model becomes more
DB-first.

### 1. Non-blocking folder scan

#### Original patterns

Immich does not use a folder-open request as its import pipeline. It persists
asset rows, then queues metadata extraction and media generation. Normal
browsing reads prepared database rows.

DiffusionToolkit discovers files in background scanning services and processes
metadata through channels. Its normal indexed search is database-backed, but
initial import intentionally does more work than a web folder listing.

#### gallery-repo adaptation

`/api/scan` performs filesystem enumeration, lightweight stat work, sorting,
pagination, and one batched dimension-cache lookup. It does not open every image
with PIL and does not parse generation metadata before returning.

#### Why the adaptation differs

The project historically allowed arbitrary local paths to be opened without a
formal import step. A minimal direct scan was therefore more suitable than
Immich's managed-library prerequisite.

#### Advantages

- low first-response cost for small ad-hoc folders;
- no mandatory prepared library;
- parsing failures cannot block folder navigation;
- simpler deployment than an import-only catalog.

#### Disadvantages

- direct scans repeat filesystem work;
- DB and filesystem result paths can have different completeness;
- it is difficult to guarantee compact DTO fields such as dimensions;
- this contract conflicts with the selected future full DB-first model.

#### Decision

The non-blocking principle remains mandatory, but the future implementation will
move enumeration into an import/index job. The UI will consume progressive DB
rows instead of rendering a direct-scan response.

### 2. Durable background metadata indexing

#### Original patterns

Immich has durable named queues and configurable concurrency. Metadata,
thumbnail generation, search, OCR, face detection, and other workloads are
separate operational queues.

DiffusionToolkit uses channels for metadata work and a batched database writer.

#### gallery-repo adaptation

The gallery uses SQLite-backed metadata jobs plus in-memory staging:

- jobs are keyed by file path/version;
- duplicates are coalesced;
- work is processed in bounded batches;
- writes are grouped into SQLite transactions;
- queue and runtime state are exposed by `/api/index/status`.

#### Advantages

- no Redis/BullMQ dependency;
- jobs survive application restarts;
- path/mtime/size validation naturally matches local files;
- sufficient for a single-node local application.

#### Disadvantages

- no distributed workers;
- metadata and derivative work do not yet share a unified scheduler;
- queue priority and resource isolation are less mature than Immich.

#### Decision

Keep the SQLite job architecture. Extend its conventions to derivative jobs
instead of introducing Redis.

### 3. Batched writes and progress

DiffusionToolkit writes batches of roughly 33 records. gallery-repo similarly
stages paths and batch-persists normalized metadata. The exact batch size is a
local tuning detail; the adapted guarantee is fewer SQLite lock transitions and
observable progress.

The gallery implementation is preferable for this project because it includes
file-version coalescing and explicit SQLite busy retry/backoff. Copying DT's
service-locator/channel implementation literally would add desktop-specific
structure without improving the guarantee.

### 4. DB-first warm metadata and indexed search

#### Original patterns

Immich's viewer receives asset and EXIF DTOs from PostgreSQL. The browser does
not parse the original media file for its details panel.

DiffusionToolkit has broad AI metadata coverage in its local database, although
the audited viewer path can reparse metadata synchronously.

#### gallery-repo adaptation

- `/api/metadata` checks the normalized database before parsing;
- Library Inspector detail is index-only and does not parse files on popover
  open;
- AI metadata, resources, FTS, fielded predicates, and facets are SQLite-backed;
- metadata extraction is unified between request and background paths.

#### Advantages

- combines Immich's DB-first warm behavior with DT-oriented AI metadata;
- avoids synchronous viewer parsing;
- keeps a single normalized parser representation.

#### Disadvantages

- metadata completeness depends on indexing progress;
- the same dimensions are currently duplicated inconsistently in two tables.

#### Decision

Preserve this architecture and fix the cross-table dimension invariant.

### 5. Persistent derivatives and strong invalidation

Immich catalogs generated files by asset and derivative type. DT uses a local
thumbnail cache keyed around its desktop model.

gallery-repo currently persists generated WebP files and uses a key containing:

```text
kind + cache version + resolved path + mtime_ns + source size
+ requested long edge + output format + output quality
```

This invalidation is well suited to mutable local files and is stronger than a
filename/size-only cache. It should remain the derivative identity foundation
when the full catalog is added.

### 6. Derivative-first lightbox and original-on-demand

#### Immich original

The viewer uses an adaptive quality list:

```text
thumbhash/thumbnail -> preview -> original
```

The original is promoted for zoom, explicit preference, animated assets, or
fallback. Previous and next assets preload thumbnail followed by preview.

#### gallery-repo adaptation

PhotoSwipe receives:

- `/api/thumbnail` as `msrc`/placeholder;
- `/api/preview` as normal slide `src`;
- `/api/image` only for zoom, fullscreen, preference, animated content, or
  preview failure.

#### Advantages

- avoids full-resolution decode on normal open;
- integrates with PhotoSwipe pan/zoom;
- preserves original-file fidelity when explicitly requested;
- separate cache keys prevent thumbnail/preview role confusion.

#### Disadvantages

- PhotoSwipe requires dimensions before layout;
- current lazy preview generation can still be on the user path;
- the current slide dimension-repair workaround can leave PhotoSwipe's internal
  slide dimensions stale.

#### Decision

Keep this quality policy. Complete it with prepared derivatives, authoritative
dimensions, and neighbor readiness.

### 7. Metadata does not block the lightbox overlay

DiffusionToolkit's audited `LoadPreviewImage()` calls metadata parsing before
dispatching bitmap loading. The gallery intentionally does the opposite:

```text
open overlay -> start PhotoSwipe -> query metadata independently
```

This is a successful adaptation and must not regress. Even under full DB-first,
metadata panel readiness must not become a precondition for mounting the
lightbox.

### 8. Watcher and scheduled refresh

Immich supports managed-library scans and watching; DT uses
`FileSystemWatcher`. gallery-repo implements optional watcher and scheduled
refresh services, with path scoping and debounce controls.

The current opt-in default is appropriate for the hybrid arbitrary-folder
model. The selected target changes the policy: watchers will become enabled by
default for explicitly registered library roots only. Watching `/`, cache
folders, build trees, or arbitrary temporary paths remains prohibited.

### 9. Virtualized browsing and compact result paths

Immich virtualizes its timeline and loads compact bucket data near the
viewport. gallery-repo uses TanStack Virtual for the gallery and Library
Inspector and paginates API results.

The UI virtualization is complete. The remaining backend improvement is to make
the compact listing DTO reliably include dimensions and derivative readiness.

### 10. Performance tests and instrumentation

The gallery has:

- Prometheus HTTP and derivative counters;
- optional pyinstrument profiles;
- scan, warm listing, search, thumbnail, album, lightbox, and metadata tests;
- a centralized budget file and budget-consumer validation.

This is more explicit than the evidence found in the two upstream audits.
However, a test is useful only when its milestone has one meaning. Current
follow-up work must separate Playwright actionability delay, animation, network,
decode, queue wait, cold rendering, and warm cache hits.

## Why not copy the upstream architectures 100%?

### Immich 100% would solve a different product

Literal adoption would imply:

- PostgreSQL as the asset source of truth;
- Redis/BullMQ-style durable distributed queues;
- a multi-service deployment and migration system;
- multi-user ownership, sharing, backup, storage-template, and permission rules;
- video transcoding and optional ML/OCR/face/vector workloads;
- server-managed asset IDs and storage paths rather than a lightweight local
  filesystem browser.

Those capabilities are valuable for a photo server but would materially
increase installation, operations, migration, and failure-recovery complexity.
They are not required to implement prepared derivatives or DB-first browsing.

### DiffusionToolkit 100% would copy desktop constraints

Literal adoption would imply:

- WPF viewer and bitmap lifecycle assumptions;
- service-locator architecture;
- eager metadata/hash work during import;
- a viewer path that may synchronously reparse metadata;
- desktop watcher and thumbnail cache semantics;
- no browser HTTP cache, ETag, responsive derivative, or PhotoSwipe concerns.

The useful DT patterns are bounded channels, batch writes, local database
indexing, watcher discipline, and broad AI metadata parsing. Its viewer flow
should not be copied.

### Recommended interpretation of “100% complete”

“Complete” should mean implementing the selected guarantee fully, not copying
the original code or infrastructure:

| Guarantee | Upstream mechanism | gallery target mechanism |
| --- | --- | --- |
| Durable jobs | Redis/BullMQ or .NET channels | SQLite jobs + in-process workers |
| DB-first assets | PostgreSQL asset tables | SQLite libraries/assets |
| Derivative catalog | `asset_file` rows | SQLite `asset_derivatives` |
| Bounded media concurrency | queue concurrency 3 / DT workers 2 | configurable default 3 |
| Prepared viewer | eager background derivatives | default full-library warming |
| Neighbor preload | Immich `PreloadManager` | Query/cache readiness + browser preload |
| Library watching | chokidar/FileSystemWatcher | configured-root watcher |
| Compact dimensions | asset DTO | authoritative assets/listing DTO |

## Incomplete adaptations and verified gaps

### 1. DB-first dimensions

Current metadata writes can populate `image_metadata.width/height` while
`file_index.width/height` remains `NULL`. Warm listing reads `file_index`, so a
fully parsed image can still reach the frontend without dimensions.

Consequences:

- PhotoSwipe falls back to `1200x1200`;
- the opening path may load/decode preview only to recover dimensions;
- the data source may be repaired after PhotoSwipe has already constructed the
  current slide;
- the current slide can remain square even when its image is not.

Required completion:

1. choose one authoritative asset dimension record;
2. update compatibility columns transactionally;
3. use `COALESCE` during migration and corruption recovery;
4. backfill old databases;
5. assert listing, metadata, and viewer dimensions are identical for the same
   source version.

### 2. Derivative-first without derivative readiness

The endpoint and source policy is correct, but cache misses are resolved inside
the user request. The system does not durably answer:

- whether a thumbnail/preview is queued, generating, ready, failed, or evicted;
- which source version produced it;
- whether a rebuild is required;
- whether a warming job is lower priority than an interactive request;
- whether quota prevented generation.

Required completion:

- persistent derivative catalog;
- durable jobs with priority;
- full default warming after import/index;
- safe rebuild/clear operations;
- separate cold-generation and warm-serving objectives.

### 3. Neighbor preload

The lightbox store and PhotoSwipe both initiate neighbor image work, but the
contract is not atomic. A transition can have preview bytes available while
dimensions or metadata are not ready.

Required neighbor bundle:

```text
preview derivative ready
+ authoritative dimensions ready
+ metadata query cached or deterministically unavailable
```

The original file must not be preloaded.

### 4. Derivative worker isolation

Metadata work is bounded. Derivative generation currently calls
`generate_derivative()` through FastAPI's shared threadpool.

Local measurements from the 2026-06-18 investigation showed:

- one-at-a-time cold thumbnail p95 around 72 ms;
- warm p95 around 3 ms;
- 48 simultaneous cold thumbnail requests produced several-hundred-millisecond
  tail latency;
- album-open p95 was dominated by the first uncached iteration.

This is a concurrency/backpressure problem, not primarily a single-image resize
problem.

## Target architecture selected for this roadmap

The chosen product direction is:

- persistent multi-library registry;
- full DB-first gallery browsing;
- progressive indexed results for an unindexed library;
- full derivative catalog;
- thumbnail and preview warming for the whole library by default;
- configured-library watchers enabled by default;
- global 10 GiB derivative quota with LRU regeneration;
- controlled adaptive variants in a later phase.

### Target data flow

```text
Register library root
  -> persist library row
  -> discovery/import job enumerates files in batches
  -> upsert stable asset rows with source version and dimensions when known
  -> UI reads progressive asset pages from SQLite
  -> metadata jobs enrich asset rows and metadata tables
  -> derivative jobs warm thumbnail and preview variants
  -> watcher maintains asset and derivative staleness

Gallery request
  -> DB-only listing
  -> compact asset DTO includes dimensions and readiness
  -> browser requests a derivative
     -> ready file: serve immediately
     -> queued/generating: attach interactive waiter and promote priority
     -> missing/stale: create/coalesce interactive job

Lightbox
  -> use known dimensions immediately
  -> thumbnail layer
  -> preview layer
  -> original only on explicit policy
  -> preload previous/next preview + dimensions + metadata
```

## Proposed data model

Names are recommendations for implementation; migrations must use
`PRAGMA user_version` and preserve existing data.

### `libraries`

| Column | Purpose |
| --- | --- |
| `id` | Stable integer or UUID library identifier |
| `root_path` | Unique canonical filesystem root |
| `name` | User-facing library name |
| `state` | `discovering`, `indexing`, `ready`, `error`, `offline` |
| `watch_enabled` | Default true for registered roots |
| `warm_enabled` | Default true |
| `created_at`, `updated_at` | Lifecycle timestamps |
| `last_scan_at`, `last_error` | Operational status |

### `assets`

This becomes the compact listing source of truth. Existing `file_index` can be
migrated/renamed or retained as a compatibility view during rollout.

| Column | Purpose |
| --- | --- |
| `id` | Stable asset ID |
| `library_id` | Registered library |
| `path`, `parent_path`, `name`, `type` | Filesystem identity |
| `mtime_ns`, `size` | Source version |
| `width`, `height`, `orientation` | Authoritative display geometry |
| `indexed_at`, `metadata_state` | Readiness |
| `offline`, `deleted_at` | Watcher/import state |

Unique identity is `(library_id, path)`. Source version is
`(mtime_ns, size)`. Renames may initially be represented as delete/add; hash- or
inode-based rename detection is optional and must not enter the hot path.

### `asset_derivatives`

| Column | Purpose |
| --- | --- |
| `id`, `asset_id` | Catalog identity |
| `kind` | `thumbnail`, `preview`, later `fullsize` if required |
| `variant` | Controlled name such as `thumb_512` |
| `source_mtime_ns`, `source_size` | Version generated from |
| `format`, `quality`, `max_long_edge` | Output contract |
| `status` | `queued`, `generating`, `ready`, `failed`, `evicted`, `deferred_capacity` |
| `cache_path`, `byte_size` | Persisted output |
| `last_accessed_at` | LRU accounting |
| `attempts`, `last_error` | Recovery |
| `created_at`, `updated_at` | Lifecycle |

Unique key:

```text
(asset_id, kind, variant, source_mtime_ns, source_size)
```

### `derivative_jobs`

| Column | Purpose |
| --- | --- |
| `derivative_id` | One durable job per derivative version |
| `priority` | Interactive, neighbor, viewport, library warm |
| `state` | Queue lifecycle |
| `attempts`, `error` | Retry/error |
| queue timestamps | Metrics and recovery |

The catalog stores desired/current state; the job table stores execution state.
Completed jobs can be compacted after a retention period.

## Public API and DTO changes

### Library management

```text
GET    /api/libraries
POST   /api/libraries
GET    /api/libraries/{library_id}
POST   /api/libraries/{library_id}/scan
DELETE /api/libraries/{library_id}
```

Registration validates and canonicalizes the root path. Removing a library
deletes catalog rows only by default; deleting derivative files requires an
explicit confirmation flag. Source files are never deleted.

### DB-first listing

`GET /api/scan` remains temporarily for compatibility, but internally resolves
the path to a registered library and reads only SQLite.

Unregistered paths return:

```json
{
  "error": "library_not_registered",
  "message": "Register this root before browsing it"
}
```

with HTTP 409.

During discovery/indexing, responses include progressive state:

```json
{
  "index_source": "db",
  "library_state": "indexing",
  "discovery_complete": false,
  "indexed_assets": 1200,
  "estimated_assets": 5000
}
```

The compact image DTO must always contain stable asset ID, dimensions when
known, metadata readiness, and derivative readiness.

### Derivative operations

```text
GET  /api/derivatives/status?library_id=...
POST /api/derivatives/warm
POST /api/derivatives/rebuild
POST /api/derivatives/clear
```

Warm/rebuild/clear operations are scoped, asynchronous, observable, and require
confirmation when they evict or replace existing files.

Existing `/api/thumbnail` and `/api/preview` remain compatible with path
parameters during migration. The preferred future form uses `asset_id` and
controlled variant names, preventing unbounded arbitrary-size catalog growth.

## Worker and scheduling policy

### Concurrency

- Default derivative render workers: **3**, matching current Immich's default
  thumbnail-generation queue concurrency.
- Configurable range: 1-8.
- Metadata workers remain separately bounded.
- Derivative work must not execute in the generic request threadpool except for
  lightweight catalog lookups and file serving.

### Coalescing

One source-version/variant key may have only one active render. HTTP requests,
neighbor preloads, viewport warmers, and library warmers all attach to or
promote the same durable job.

### Priority

```text
P0 interactive HTTP miss
P1 current lightbox neighbor
P2 first/near viewport
P3 full-library warming
P4 maintenance/rebuild
```

Promotion is monotonic: a background job requested interactively becomes P0.
Workers use aging so low-priority jobs cannot starve indefinitely.

### Failure and retry

- transient IO/SQLite errors: bounded exponential retry;
- missing/changed source: mark stale and reschedule against the new version;
- unsupported/corrupt source: durable failed state, no hot retry loop;
- capacity unavailable: `deferred_capacity`, retried after eviction or quota
  change.

## Warming and quota policy

### Default warming

After each asset's metadata/index record is ready, queue:

```text
thumbnail 512 WebP
preview 1440 WebP
```

The UI may consume assets before warming completes. Interactive requests promote
their jobs.

### Global quota

- default: **10 GiB**;
- configurable;
- source originals and metadata DB do not count toward this quota;
- catalog tracks actual derivative byte size;
- eviction uses LRU with protection for active jobs and currently viewed assets.

Full warming is a desired state, not permission to loop forever. If the desired
derivative set cannot fit:

1. evict eligible old derivatives;
2. generate only when capacity can be reserved;
3. mark remaining work `deferred_capacity`;
4. expose coverage and required/available bytes;
5. retry only after capacity, policy, or source set changes.

### Later controlled variants

Phase 2 may add:

```text
thumb_256
thumb_512
preview_1440
preview_2560
```

Variants are configuration-defined and schema-cataloged. Arbitrary
`max_long_edge` requests may still be served transiently for compatibility but
must not create unlimited durable catalog rows.

## Migration and rollout plan

### Phase 0 - Correctness and measurement

1. Make asset dimensions authoritative and transactionally synchronize legacy
   tables.
2. Add defensive `COALESCE` and backfill migration.
3. Repair active PhotoSwipe slide dimensions without reintroducing duplicate
   Safari images.
4. Update lightbox tests to select the active holder.
5. Split perf measurements into:
   - action request/event to overlay;
   - derivative queue wait;
   - render/encode/persist;
   - network response;
   - browser decode/visual-ready;
   - cold and warm samples.

Exit criteria:

- no known aspect-ratio mismatch;
- dimensions invariant tests pass;
- baseline metrics are reproducible.

### Phase 1 - Library and asset catalog

1. Add `libraries` and authoritative `assets`.
2. Import existing `file_index` rows into a default library.
3. Dual-write old/new tables during migration.
4. Add progressive discovery/import status.
5. Add DB listing endpoint and shadow-compare it with existing scan output.
6. Expose persistent multi-library registration and status.

Exit criteria:

- ordering, pagination, counts, and path scope match existing behavior;
- restart resumes incomplete discovery;
- no source files are modified.

### Phase 2 - Derivative catalog and workers

1. Add `asset_derivatives` and `derivative_jobs`.
2. Import currently valid cached files when their keys can be reconstructed;
   otherwise leave them as legacy cache hits and catalog on access.
3. Implement three bounded workers, coalescing, priorities, retries, and
   metrics.
4. Route thumbnail/preview cache misses through the scheduler.
5. Enable default full warming and 10 GiB LRU policy.
6. Add warm/rebuild/clear/status APIs.

Exit criteria:

- same-key concurrent requests render once;
- worker concurrency never exceeds configuration;
- interactive work preempts/promotes background warming;
- restart recovers queued/generating jobs safely;
- no generate/evict loop at quota.

### Phase 3 - Viewer readiness

1. Include dimensions and derivative status in compact listing DTOs.
2. Preload previous/next preview, dimensions, and metadata as one logical
   readiness bundle.
3. Preserve original-on-demand policy.
4. Add controlled adaptive variants after 512/1440 behavior is stable.

Exit criteria:

- normal lightbox open never waits for metadata parsing;
- neighbor transitions do not request original;
- active slide aspect ratio is always correct.

### Phase 4 - DB-required cutover

1. Make registered-library DB listing the only gallery rendering source.
2. Return 409 for unregistered roots.
3. Enable watchers by default for registered libraries.
4. Remove direct-scan rendering fallback after shadow comparisons and rollback
   rehearsal pass.
5. Retain a maintenance discovery command for repair/import; do not expose it
   as a second frontend data source.

Rollback before final removal:

- disable DB-required flag;
- continue reading legacy `file_index`;
- stop derivative workers;
- serve valid legacy cache files;
- never delete originals or metadata DB automatically.

## Test plan and acceptance criteria

### Database and migration

- Existing v2 databases migrate idempotently.
- Every metadata dimension update is visible in the asset/listing row in the
  same committed transaction.
- Backfill preserves paths, metadata, resources, and FTS behavior.
- Library registration rejects overlapping/unsafe roots according to one
  documented policy.
- Unregister and rebuild never remove source files.

### Progressive DB browsing

- A new library renders indexed rows progressively.
- Result order and cursor pagination remain stable while later batches arrive.
- Restart resumes discovery without duplicate assets.
- Moved/deleted/offline files converge through watcher and scheduled repair.
- Unregistered paths return the specified 409 response.

### Derivative scheduler

- 100 concurrent requests for one key cause one render.
- Render concurrency never exceeds 3 by default.
- An interactive request promotes an existing P3 job to P0.
- Different source versions never share a derivative.
- Failed/corrupt images do not spin in retry loops.
- Restart changes abandoned `generating` jobs to retryable queued state.
- Quota reservation prevents oversubscription.
- LRU eviction never removes a file currently being served or generated.
- `deferred_capacity` work does not continuously requeue.

### Viewer

- Thumbnail -> preview -> original source policy is unchanged.
- Original is not fetched during normal open or neighbor transition.
- Dimensions match source orientation and active PhotoSwipe slide geometry.
- Previous/next preview and metadata are canceled/reassigned on rapid direction
  changes.
- Safari duplicate-image regression remains covered.

### Performance targets

Targets apply on the repository's deterministic fixture and documented reference
machine/profile:

| Metric | Target |
| --- | ---: |
| Warm album thumbnail request p95 | <= 200 ms |
| Lightbox event-to-overlay p95 | <= 100 ms |
| Warm preview HTTP p95 | <= 200 ms |
| Visual preview-ready p95 | <= 750 ms |
| Warm neighbor preview-ready p95 | <= 200 ms |
| Warm 5,000-image DB first page | <= 500 ms |
| Derivative queue worker overcommit | 0 |
| Same-key duplicate renders | 0 |

Cold derivative generation is reported separately and must not be compared to
warm serving budgets.

### Metrics

Add bounded-label metrics for:

- derivative cache hit/miss by kind/variant;
- queue depth by priority/state;
- queue wait, render, encode, persist, and total duration histograms;
- coalesced requests and priority promotions;
- worker active count;
- derivative bytes, quota utilization, evictions, and deferred capacity;
- warm coverage by library and variant;
- discovery/index throughput and library readiness.

No metric may use raw paths or asset IDs as labels.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Full warming saturates CPU/disk | Three workers, low background priority, interactive promotion, configurable disable |
| 10 GiB is insufficient | Capacity reservation, LRU, `deferred_capacity`, coverage reporting |
| DB-required browsing worsens first use | Progressive rows and explicit import state |
| Watcher event storms | Registered roots only, debounce, batch coalescing, scheduled reconciliation |
| SQLite contention | Separate bounded workers, short transactions, WAL, busy retry, batch writes |
| Catalog/cache divergence | Reconcile at startup/maintenance, source-version keys, atomic file rename before ready state |
| Migration loses arbitrary-folder convenience | Persistent multi-library registration and explicit 409 guidance |
| Adaptive variants multiply storage | Controlled variant set only; phase after core stability |
| PhotoSwipe repair reintroduces Safari duplicates | Update internal geometry safely and retain visual-layer regression tests |

## Final recommendation

The project should not become an Immich deployment or a DiffusionToolkit port.
It should become a prepared local AI-image library with these guarantees:

- SQLite remains the local durable control plane.
- Registered libraries and assets become the browsing source of truth.
- Metadata and derivatives are background-prepared, observable, and restartable.
- Derivative generation is bounded, coalesced, prioritized, and quota-aware.
- The browser receives authoritative dimensions and compact readiness state.
- The lightbox remains preview-first and metadata-independent.
- Source files remain external, immutable inputs unless a future feature
  explicitly introduces editing.

This captures the operational discipline that currently distinguishes Immich
and DT from gallery-repo, without importing their platform-specific cost.
