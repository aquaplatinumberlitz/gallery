# Immich / DiffusionToolkit Adaptation Audit and Roadmap

Last reviewed: June 19, 2026 — Phases 0–4 implemented; CI verified at `bd03061`

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

All five original implementation gaps identified below were addressed in
Phases 0–4 of this roadmap:

1. dimensions can be present in `image_metadata` but absent from `file_index`;
2. derivative rendering runs on the shared request threadpool without dedicated
   concurrency control or same-key request coalescing;
3. derivatives are normally generated on demand, without durable readiness,
   priority, warming, or maintenance state;
4. neighbor preloading does not guarantee that preview, dimensions, and metadata
   are all ready before navigation;
5. some performance tests mix browser actionability delay, animation duration,
   cold generation, and warm-cache latency into one budget.

The implementation remains intentionally hybrid at rollout time:

- registered libraries, asset rows, derivative jobs, readiness state, repair,
  and registered-root watching are available now;
- `GALLERY_DB_REQUIRED` remains disabled by default, so direct filesystem scan
  is still the compatibility fallback until operators opt into DB-required
  browsing;
- capacity reservation, `deferred_capacity`, queue aging, and use of the
  reserved P1/P2 priorities remain hardening work, not completed features.

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
| `gallery-repo` | `bd03061` | Phases 0–4 plus CI regression fixes, 2026-06-19 |
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

### Implementation verification

The post-implementation verification at `bd03061` established:

- GitHub Actions run
  [`27803442500`](https://github.com/aquaplatinumberlitz/gallery/actions/runs/27803442500)
  passed `lint`, `test:unit`, and `test:e2e`;
- backend: **592 passed**, **85.90% coverage** on Python 3.11;
- frontend unit tests: **393 passed**;
- Playwright contract suite: **22 passed**;
- frontend lint and production build passed.

Per-commit reconstruction also showed why testing only the final pushed SHA was
insufficient: phases 0 and 1 passed independently; phase 2 passed assertions but
failed the 85% coverage gate; phases 3 and 4 failed the stale `FileNode` response
shape assertion. Commit `bd03061` updated the response contract tests, added
derivative scheduler coverage, and prevented the startup-hook test from leaking
worker threads into later SQLite fixtures.

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
| Neighbor preload | Immich | Preview + dimensions + metadata bundle with cancellable AbortController | **Done** |
| Watcher/scheduled refresh | Immich/DT | Configured-root watcher, enabled by default for registered libraries | **Done** |
| AI metadata parsing/search | DT | Broad parser and indexed search | Done |
| Fielded search/facets | DT/Immich | Implemented | Done |
| Virtualized grid/list | Immich scale pattern | Implemented | Done |
| Perf tests/instrumentation | Gallery-specific | Implemented; metrics split into queue/render/network/decode stages | **Done** |
| Dedicated derivative workers | Immich/DT | **3 bounded thread workers, configurable 1-8, priority P0-P3, coalescing** | **Done** |
| Derivative readiness/catalog | Immich | **asset_derivatives + derivative_jobs tables with status tracking** | **Done** |
| Full derivative warming | Immich-style prepared library | **Background warming after metadata index, 10 GiB LRU quota** | **Done** |
| Dimension invariants across catalog tables | Immich DTO guarantee | **COALESCE + sync_dimensions_to_file_index in same transaction** | **Done** |

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
- compatibility mode cannot provide the same readiness guarantees as a fully
  prepared registered library.

#### Decision

The non-blocking principle remains mandatory. Registered libraries now move
enumeration into import/index work and expose progressive DB rows. Direct scan
remains only as the default compatibility fallback until
`GALLERY_DB_REQUIRED` is enabled.

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
- metadata and derivative work use separate SQLite-backed schedulers and
  lifecycle conventions;
- queue fairness, capacity reservation, and distributed execution remain less
  mature than Immich.

#### Decision

Keep the SQLite job architecture. Phase 2 extended its conventions to
derivative jobs without introducing Redis.

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
- dimensions remain duplicated in compatibility tables and therefore require
  the transactional synchronization and migration invariant added in phase 0.

#### Decision

Preserve this architecture. Phase 0 now synchronizes dimensions in the same
transaction, uses `COALESCE` for compatibility reads, and backfills existing
databases.

### 5. Persistent derivatives and strong invalidation

Immich catalogs generated files by asset and derivative type. DT uses a local
thumbnail cache keyed around its desktop model.

gallery-repo persists generated WebP files, catalogs their source version and
readiness in `asset_derivatives`, and uses a key containing:

```text
kind + cache version + resolved path + mtime_ns + source size
+ requested long edge + output format + output quality
```

This invalidation is well suited to mutable local files and is stronger than a
filename/size-only cache. Phase 2 retained it as the derivative identity
foundation for the durable catalog.

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
- an unwarmed or evicted preview can still require interactive generation;
- DB readiness is progressive, so compatibility/direct-scan responses can have
  unknown dimensions until indexing completes.

#### Decision

Keep this quality policy. Phases 0–3 added synchronized dimensions, prepared
derivatives, catalog readiness, and cancellable neighbor preload bundles.

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

The watcher is enabled by default but resolves only registered library roots;
it does not start when no registered roots exist. Watching `/`, cache folders,
build trees, or arbitrary temporary paths remains prohibited.

### 9. Virtualized browsing and compact result paths

Immich virtualizes its timeline and loads compact bucket data near the
viewport. gallery-repo uses TanStack Virtual for the gallery and Library
Inspector and paginates API results.

The UI virtualization is complete. The compact listing DTO now includes
`asset_id`, dimensions, `metadata_state`, and `derivative_ready`; compatibility
direct scans return the same DTO shape with readiness fields unset when no
catalog row exists.

### 10. Performance tests and instrumentation

The gallery has:

- Prometheus HTTP and derivative counters;
- optional pyinstrument profiles;
- scan, warm listing, search, thumbnail, album, lightbox, and metadata tests;
- a centralized budget file and budget-consumer validation.

This is more explicit than the evidence found in the two upstream audits.
Phase 0 split the main timing stages so actionability delay, animation, network,
decode, queue wait, cold rendering, and warm cache hits are no longer treated as
one milestone. Queue-state and quota observability still need broader acceptance
coverage before DB-required mode becomes the default.

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

## Implemented gaps and residual hardening

### 1. DB-first dimensions

Phase 0 fixed the verified cross-table mismatch by synchronizing dimension
writes, using `COALESCE` in compatibility reads, backfilling old databases, and
repairing PhotoSwipe geometry in place. Listing, metadata, and orientation tests
cover the invariant.

Residual hardening: `assets` should eventually be the sole authoritative DTO
source after compatibility tables and direct-scan mode can be retired.

### 2. Derivative-first without derivative readiness

Phase 2 added `asset_derivatives` and `derivative_jobs`, source-version identity,
durable readiness, bounded workers, same-key coalescing, interactive promotion,
warming, rebuild/clear operations, and LRU quota enforcement. Cold generation
and warm serving are reported separately.

Residual hardening: quota enforcement currently happens after generation. The
design for pre-generation capacity reservation and a durable
`deferred_capacity` state is not implemented and must not be described as an
existing guarantee.

### 3. Neighbor preload

Phase 3 made the neighbor contract explicit and cancellable:

```text
preview derivative ready
+ authoritative dimensions ready
+ metadata query cached or deterministically unavailable
```

The original file is not preloaded. Rapid navigation cancels or reassigns the
bundle through `AbortController`.

### 4. Derivative worker isolation

Derivative rendering now runs in a dedicated scheduler with three workers by
default and a configurable range of one to eight. Interactive HTTP misses queue
P0 work and wait for the durable result; library warming and rebuild work use
P3. Same-key requests coalesce onto one catalog/job identity.

Local measurements from the 2026-06-18 investigation showed:

- one-at-a-time cold thumbnail p95 around 72 ms;
- warm p95 around 3 ms;
- 48 simultaneous cold thumbnail requests produced several-hundred-millisecond
  tail latency;
- album-open p95 was dominated by the first uncached iteration.

Those measurements motivated the dedicated worker implementation. Residual
hardening includes explicit stress tests for the configured concurrency limit,
queue aging/fairness, and capacity reservation under a saturated quota.

## Implemented architecture and rollout state

The implemented product direction is:

- persistent multi-library registry;
- full DB-first gallery browsing;
- progressive indexed results for an unindexed library;
- full derivative catalog;
- thumbnail and preview warming for the whole library by default;
- configured-library watchers enabled by default;
- global 10 GiB derivative quota with LRU regeneration;
- controlled configuration-defined variants.

The catalog and worker architecture is implemented. Rollout is intentionally
incomplete: `GALLERY_DB_REQUIRED=false` remains the default for backward
compatibility. Enabling it changes unregistered-path behavior to HTTP 409 and
removes direct filesystem fallback from normal browsing.

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

## Implemented data model

The phase 1/2 migrations use these tables, advance `PRAGMA user_version`, and
preserve existing data.

### `libraries`

| Column | Purpose |
| --- | --- |
| `id` | Stable integer library identifier |
| `root_path` | Unique canonical filesystem root |
| `name` | User-facing library name |
| `state` | `discovering`, `indexing`, `ready`, `error`, `offline` |
| `watch_enabled` | Default true for registered roots |
| `warm_enabled` | Default true |
| `created_at`, `updated_at` | Lifecycle timestamps |
| `last_scan_at`, `last_error` | Operational status |

### `assets`

This is the compact listing source for registered libraries. Existing
`file_index` remains a compatibility store during rollout.

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
| `status` | Current persisted states: `queued`, `running`, `ready`, `failed` |
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
| `priority` | Integer `0..3`; P0 interactive, P3 warming/rebuild, P1/P2 reserved |
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

`GET /api/scan` resolves registered paths through SQLite. When
`GALLERY_DB_REQUIRED=false`, an unregistered or unavailable warm listing may
still use the compatibility filesystem scan. When the flag is true, registered
DB browsing is required.

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

Existing `/api/thumbnail` and `/api/preview` accept both path and `asset_id`
parameters. Cataloged requests use controlled variant names; arbitrary sizing
remains a compatibility path and must not create unbounded durable variants.

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
P1 reserved for neighbor promotion
P2 reserved for viewport warming
P3 full-library warming
```

The scheduler currently clamps priority to `0..3`. Production call sites use P0
for interactive requests and P3 for warming/rebuild. Promotion is monotonic: a
background job requested interactively becomes P0. P1/P2 call-site policies and
queue aging are not yet implemented.

### Failure and retry

- transient IO/SQLite errors: bounded exponential retry;
- missing/changed source: mark stale and reschedule against the new version;
- unsupported/corrupt source: durable failed state, no hot retry loop;
- quota enforcement: evict eligible LRU derivatives after successful
  generation.

Pre-generation capacity reservation and `deferred_capacity` remain proposed
hardening work.

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

Full warming is a desired state, not permission to loop forever. The following
capacity-safe behavior remains the target rather than the current guarantee:

1. evict eligible old derivatives;
2. generate only when capacity can be reserved;
3. mark remaining work `deferred_capacity`;
4. expose coverage and required/available bytes;
5. retry only after capacity, policy, or source set changes.

### Controlled variants

The current configured set is:

```text
thumb_512
preview_1440
```

Future configuration may add `thumb_256` or `preview_2560`. Variants are
configuration-defined and schema-cataloged. Arbitrary
`max_long_edge` requests may still be served transiently for compatibility but
must not create unlimited durable catalog rows.

## Migration and rollout plan

### Phase 0 - Correctness and measurement ✅ IMPLEMENTED

- ✅ dimensions synchronized between image_metadata and file_index within same transaction
- ✅ COALESCE in warm listing queries
- ✅ Backfill migration (PRAGMA user_version = 3)
- ✅ PhotoSwipe slide dimension repair (in-place geometry update, no Safari regression)
- ✅ Perf metrics split: event→overlay, queue wait, render/encode/persist, network, browser decode

Exit criteria:

- ✅ no known aspect-ratio mismatch
- ✅ dimensions invariant tests pass
- ✅ baseline metrics are reproducible

### Phase 1 - Library and asset catalog ✅ IMPLEMENTED

- ✅ `libraries` + `assets` tables (PRAGMA user_version = 4)
- ✅ Default library auto-created on startup
- ✅ `file_index` → `assets` migration on upgrade
- ✅ Dual-write on metadata update (`upsert_extracted_metadata`, `index_file`) and scan
- ✅ Library CRUD API: `GET/POST /api/libraries`, `GET/DELETE /api/libraries/{id}`, scan endpoint
- ✅ DB listing endpoint (`get_asset_folder_listing`) with asset-first, fallback to warm listing
- ✅ Shadow comparison logging for mismatch detection

Exit criteria:

- ✅ ordering, pagination, counts, and path scope match existing behavior
- ✅ restart resumes incomplete discovery
- ✅ no source files are modified

### Phase 2 - Derivative catalog and workers ✅ IMPLEMENTED

- ✅ `asset_derivatives` + `derivative_jobs` tables (PRAGMA user_version = 5)
- ✅ Import of existing cached derivatives on migration
- ✅ 3 bounded thread workers (configurable 1-8 via DERIVATIVE_WORKER_COUNT)
- ✅ Coalescing: same-key concurrent requests render once
- ✅ Priority range P0-P3 with monotonic promotion (interactive request promotes P3→P0); P1/P2 are reserved
- ✅ Exponential backoff retry (max 3 attempts), permanent failure for corrupt/unsupported
- ✅ 10 GiB LRU quota (configurable via GALLERY_DERIVATIVE_QUOTA_BYTES)
- ✅ Background warming after metadata index completes
- ✅ Derivative API endpoints: `GET /api/derivatives/status`, `POST /api/derivatives/warm|rebuild|clear`

Exit criteria:

- ✅ same-key concurrent requests render once
- ✅ worker concurrency never exceeds configuration
- ✅ interactive work preempts/promotes background warming
- ✅ restart recovers queued/generating jobs safely
- ⚠️ post-generation LRU enforcement is implemented; pre-generation reservation and `deferred_capacity` remain open

### Phase 3 - Viewer readiness ✅ IMPLEMENTED

- ✅ `asset_id`, `metadata_state`, `derivative_ready` fields in compact listing DTO (FileNode)
- ✅ `derivative_ready` populated from asset_derivatives table in get_asset_folder_listing
- ✅ Neighbor preload bundle: preview + dimensions + metadata via Promise.all, with AbortController cancellable
- ✅ Original-on-demand policy preserved (original only on zoom, fullscreen, preference, animated content, or preview failure)
- ✅ Controlled adaptive variants via DERIVATIVE_VARIANTS config (replaces hardcoded DEFAULT_VARIANTS)

Exit criteria:

- ✅ normal lightbox open never waits for metadata parsing
- ✅ neighbor transitions do not request original
- ✅ active slide aspect ratio is correct

### Phase 4 - DB-required cutover ✅ IMPLEMENTED

- ✅ `GALLERY_DB_REQUIRED` env var (default `false` for backward-compatible rollout)
- ✅ `_require_db_path()` raises HTTP 409 with `{"error": "library_not_registered"}` for unregistered roots when flag is true
- ✅ Watcher defaults to registered library roots only (via `_registered_watcher_roots()`)
- ✅ Watcher starts only when registered libraries exist; skips if none registered
- ✅ Deprecation warning logged when direct filesystem scan fallback is used
- ✅ Library repair endpoint: `POST /api/libraries/{library_id}/repair`

Rollback support:

- ✅ `GALLERY_DB_REQUIRED=0` restores filesystem scan fallback behavior

## Test plan and acceptance criteria

Status below reflects the `bd03061` verification. Checked items are covered by
the current suite; unchecked items remain release-hardening criteria.

### Database and migration

- ✅ Existing v2 databases migrate idempotently.
- ✅ Every metadata dimension update is visible in the asset/listing row in the
  same committed transaction.
- ✅ Backfill preserves paths, metadata, resources, and FTS behavior.
- ✅ Library registration rejects overlapping/unsafe roots according to one
  documented policy.
- ✅ Unregister and rebuild never remove source files.

### Progressive DB browsing

- ✅ A new library exposes indexed rows progressively.
- ✅ Result order and cursor pagination remain stable.
- ✅ Restart resumes durable indexing without duplicate asset identities.
- ✅ Moved/deleted/offline files converge through watcher and repair.
- ✅ In DB-required mode, unregistered paths return the specified 409 response.

### Derivative scheduler

- ✅ Same-key scheduling coalesces onto one active job and supports P3→P0 promotion.
- ✅ Worker count defaults to 3 and is clamped to 1–8.
- ✅ Different source versions never share a derivative identity.
- ✅ Failed/corrupt images use bounded retries or durable failure.
- ✅ Restart changes abandoned `running` jobs to queued state.
- ✅ LRU eviction protects files currently served or generated.
- ⬜ Add a deterministic 100-request render-once stress test.
- ⬜ Add a deterministic active-worker concurrency stress test.
- ⬜ Implement capacity reservation and `deferred_capacity` before claiming
  quota oversubscription prevention.

### Viewer

- ✅ Thumbnail -> preview -> original source policy is unchanged.
- ✅ Original is not fetched during normal open or neighbor transition.
- ✅ Dimensions match source orientation and active PhotoSwipe slide geometry.
- ✅ Previous/next preview and metadata are canceled/reassigned on rapid direction
  changes.
- ✅ Safari duplicate-image regression remains covered.

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

Current instrumentation covers HTTP, scan/listing, cache, derivative, and
split lightbox timing paths. Remaining queue/quota observability should use
bounded-label metrics for:

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
| 10 GiB is insufficient | Current LRU enforcement; add capacity reservation, `deferred_capacity`, and coverage reporting before strict-cap rollout |
| DB-required browsing worsens first use | Progressive rows and explicit import state |
| Watcher event storms | Registered roots only, debounce, batch coalescing, scheduled reconciliation |
| SQLite contention | Separate bounded workers, short transactions, WAL, busy retry, batch writes |
| Catalog/cache divergence | Reconcile at startup/maintenance, source-version keys, atomic file rename before ready state |
| Migration loses arbitrary-folder convenience | Persistent multi-library registration and explicit 409 guidance |
| Adaptive variants multiply storage | Controlled variant set only; phase after core stability |
| PhotoSwipe repair reintroduces Safari duplicates | Update internal geometry safely and retain visual-layer regression tests |

## Final recommendation

The project should not become an Immich deployment or a DiffusionToolkit port.
It now provides the core of a prepared local AI-image library with these
guarantees:

- SQLite remains the local durable control plane.
- Registered libraries and assets are the DB-first browsing source when
  DB-required mode is enabled.
- Metadata and derivatives are background-prepared, observable, and restartable.
- Derivative generation is bounded, coalesced, prioritized, and LRU
  quota-aware.
- The browser receives authoritative dimensions and compact readiness state.
- The lightbox remains preview-first and metadata-independent.
- Source files remain external, immutable inputs unless a future feature
  explicitly introduces editing.

This captures the relevant operational discipline from Immich and DT without
importing their platform-specific cost. The remaining release gate is rollout
hardening—especially capacity reservation, queue stress coverage, and deciding
when `GALLERY_DB_REQUIRED` can safely default to true.
