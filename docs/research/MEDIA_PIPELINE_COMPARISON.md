# Media Pipeline Comparison

> **Status:** Research snapshot. This comparison is tied to the revisions below;
> use [Architecture](../ARCHITECTURE.md) for current gallery behavior.

Date: 2026-06-09

References inspected:

- gallery-repo: `155f120f81730fa7ac1e65609364135e4262e776`
- Immich: `f382624e689315f327632fff1505cca3cfa21640`
- DiffusionToolkit audit: [DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md), which inspected DiffusionToolkit commit `153409c3a0e9569886e6601530365808d4ecbb0e`

Inputs:

- Local gallery-repo code and docs listed in [IMMICH_PIPELINE_AUDIT.md](IMMICH_PIPELINE_AUDIT.md).
- Immich source files listed in [IMMICH_PIPELINE_AUDIT.md](IMMICH_PIPELINE_AUDIT.md).
- Existing DiffusionToolkit audit doc. I did not reclone DiffusionToolkit because the existing audit already contains recent file-level evidence for the claims used here.

## Executive Summary

Best for fast web folder open: **gallery-repo**.

Best for AI metadata indexing: **DiffusionToolkit for Stable Diffusion prompt/workflow metadata today**. Immich is stronger for photo/EXIF/OCR/CLIP metadata at full photo-library scale, but DiffusionToolkit is more directly aligned with AI-generation metadata formats.

Best for large photo library: **Immich**.

Best for lightbox responsiveness: **gallery-repo for current original-image web lightbox goals**. Immich is excellent once derivatives are warm, but it normally displays preview derivatives before original. DiffusionToolkit is weaker here because the audited desktop preview path reparses metadata before preview display.

Best for search: **Immich overall at large scale**. gallery-repo is simpler and good for local AI metadata search. DiffusionToolkit is strong for desktop AI metadata search, but not a web-scale photo search architecture.

Best for maintainability in our project: **gallery-repo with selective borrowing**. Keep the existing scan/thumbnail/lightbox guarantees. Borrow small, local versions of DiffusionToolkit's background indexing patterns and Immich's DB-first metadata/derivative status ideas.

## Pipeline Diagrams

### gallery-repo pipeline

```txt
User opens folder
  -> GET /api/scan
     [hot path: os.scandir/stat/sort/page, no PIL, no metadata parse]
  -> batch SQLite dimension cache lookup
     [DB read, width/height only if path+mtime+size match]
  -> grid renders PhotoCard
     [TanStack Query owns scan state]
  -> browser requests /api/thumbnail
     [lazy thumbnail serve/generate, opens image only on cache miss]
  -> thumbnail generation stores dimensions
     [SQLite dimension cache populated while image is already open]
  -> user opens lightbox
     [PhotoSwipe item main src = /api/image original]
  -> dimension resolver
     [scan dims -> remembered thumbnail natural dims -> cached metadata -> /api/metadata -> thumbnail natural dims]
  -> metadata panel
     [on-demand /api/metadata, parser cache + SQLite metadata cache]
  -> search
     [SQLite file index / metadata cache / FTS and trigram tables]
```

### DiffusionToolkit pipeline

```txt
User adds/scans folder
  -> desktop scanning service enumerates files
     [background service, local filesystem]
  -> metadata scanner parses generation metadata
     [original image read; supports PNG/JPEG/WebP/sidecar/stealth formats per audit]
  -> hash/metadata/dimensions written through database writer
     [SQLite/local DB, batched writes]
  -> thumbnail cache/service generates or serves thumbnails
     [desktop cache]
  -> search page queries indexed metadata
     [desktop DB/search UI]
  -> preview pane opens image
     [audit found metadata can be reparsed synchronously before preview load]
```

### Immich pipeline

```txt
Upload or external library scan
  -> asset row persisted
     [DB write; upload streams checksum, external scan uses stat/path-derived checksum]
  -> background jobs
     [sidecar check -> metadata extraction -> storage/template step -> thumbnail generation]
  -> DB metadata and derivatives
     [asset, asset_exif, asset_file, asset_job_status, OCR/smart-search tables]
  -> timeline route
     [bucket counts first, compact bucket assets when near viewport]
  -> grid thumbnails
     [/assets/:id/thumbnail?size=thumbnail, generated derivative file]
  -> viewer
     [getAssetInfo DTO, thumbnail -> preview, original/fullsize on zoom/preference/fallback/download]
  -> search
     [PostgreSQL metadata filters, trigram/unaccent, OCR, CLIP vector search]
```

## Comparison Table

| Area                           | gallery-repo                                                                          | DiffusionToolkit                                                                             | Immich                                                                                      | Winner                                                                             | Reason                                                                           |
| ------------------------------ | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Folder open hot path           | `/api/scan` lists/stat/sorts; no PIL/metadata parse; cached dimensions only.          | Folder import is a scan/index workflow, not a minimal web open path.                         | Existing library timeline is DB-fast; new external library import is background scan/index. | gallery-repo for ad hoc web folder open.                                           | It returns useful grid data with the least cold-start work.                      |
| Metadata parsing timing        | On-demand `/api/metadata`; background indexing is opportunistic and scan-safe.        | During scan/index, plus audited preview path can reparse before display.                     | Background metadata job after asset row/sidecar checks.                                     | Depends: gallery-repo for first open; Immich/DT for pre-indexed metadata.          | Timing should match UX goal.                                                     |
| Metadata cache/database        | SQLite metadata cache, file index, FTS/trigram tables.                                | Local DB with metadata/hash records and batch writer per audit.                              | PostgreSQL asset/exif/file/job/OCR/vector tables.                                           | Immich for large libraries; gallery-repo for project simplicity.                   | PostgreSQL is stronger but heavier.                                              |
| Thumbnail generation           | Lazy per `/api/thumbnail`, persistent disk cache, dimensions cached while image open. | Desktop thumbnail cache/service per audit.                                                   | Eager background derivative generation, `asset_file` records.                               | gallery-repo for cold small folders; Immich for warm large libraries.              | Lazy avoids up-front work; eager improves repeat browsing.                       |
| Lightbox image source          | Main PhotoSwipe `src` is original `/api/image`; thumbnail is placeholder/msrc.        | Desktop preview image path; audit found metadata reparse can precede preview.                | Thumbnail -> preview derivative; original/fullsize on zoom/preference/fallback/download.    | gallery-repo for current original-image web lightbox.                              | It matches the explicit original-display requirement and tests.                  |
| Lightbox metadata source       | TanStack metadata query; can trigger on-demand extraction.                            | Preview path can parse metadata before preview per audit.                                    | Asset detail DTO from DB/API.                                                               | Immich warm; gallery-repo cold.                                                    | DB-first is best after indexing, but gallery-repo avoids mandatory pre-indexing. |
| Search/filtering               | SQLite search over cached metadata/file index.                                        | Strong desktop AI metadata search/filtering per audit.                                       | PostgreSQL metadata filters, trigram/OCR, CLIP vectors.                                     | Immich overall; DT for AI prompt metadata focus.                                   | Immich has the most scalable search architecture.                                |
| Background jobs                | Lightweight background tasks; no durable queue stack.                                 | Scanning/indexing/background writer services.                                                | BullMQ queues/workers for media, metadata, ML, library, OCR, faces.                         | Immich for robustness; gallery-repo for maintainability.                           | Full queue systems help at scale but add ops cost.                               |
| Queue/batch processing         | Limited; scan does batch dimension lookup.                                            | Strong local batch writer pattern.                                                           | Durable named queues and configurable concurrency.                                          | DT for a simple local pattern; Immich for server scale.                            | gallery-repo should borrow the smaller DT-style batch idea first.                |
| Watcher/change detection       | Path+mtime+size cache validation; no persistent watcher.                              | Folder watching/change detection per audit.                                                  | Scheduled library scan and optional chokidar watcher; missing files marked offline/deleted. | Immich for managed libraries; DT for desktop local; gallery-repo for ad hoc.       | Watchers matter only after adopting a persistent library model.                  |
| Cache invalidation             | Path+mtime+size keys for dimensions/thumbnails/metadata.                              | DB/cache invalidation tied to scanner/watcher/hash per audit.                                | Thumbhash URL cache key, derivative rows, watcher/offline state, asset cache invalidation.  | gallery-repo for simple file freshness; Immich for managed assets.                 | Both are good for their scope.                                                   |
| 50 image cold cache            | Fast folder open; thumbnails generate as requested.                                   | Import parses/indexes more up front.                                                         | Requires import/background jobs before fully warm.                                          | gallery-repo.                                                                      | Few-dozen ad hoc folders benefit from minimal work.                              |
| 50 image warm cache            | Fast; cached thumbnails/dimensions/metadata help.                                     | Fast after indexed.                                                                          | Fast after indexed/derivatives generated.                                                   | Tie, with gallery-repo simplest.                                                   | All can handle 50 warm images.                                                   |
| 5000 image cold cache          | Scan/sort still walks all files; metadata remains lazy.                               | Background indexing is useful but initial import costs work.                                 | Background library import and jobs; UI improves after indexing.                             | gallery-repo for immediate partial browsing; Immich/DT for eventual indexed state. | Cold and warm answers diverge.                                                   |
| 5000 image warm cache          | Better than cold, but still folder-scan based.                                        | Good desktop indexed browsing.                                                               | Strong DB bucketed browsing and derivatives.                                                | Immich.                                                                            | DB-first timeline avoids repeated large folder scans.                            |
| 100k library                   | Not currently designed as a persistent 100k asset library.                            | Better than gallery-repo for desktop indexed local library, but not a photo-server timeline. | Designed for this scale.                                                                    | Immich.                                                                            | PostgreSQL, queues, derivatives, and buckets are the right architecture.         |
| Mobile/web suitability         | Web UI with PhotoSwipe; focused local app.                                            | Desktop WPF/local app, not web/mobile-first.                                                 | Full web/mobile photo server model.                                                         | Immich.                                                                            | It has the broadest client/server UX.                                            |
| Desktop/local-only suitability | Good local web app.                                                                   | Excellent desktop/local fit.                                                                 | Possible self-hosted, but heavier than needed.                                              | DiffusionToolkit for desktop app; gallery-repo for local web.                      | DT was built for desktop workflows.                                              |
| Deployment complexity          | Low.                                                                                  | Desktop install/app complexity, but no full server stack.                                    | High: server, DB, queue, storage, optional ML.                                              | gallery-repo.                                                                      | Lowest operational burden.                                                       |
| Ideas worth borrowing          | Keep hot path; add local queue/status/preload carefully.                              | Batch writer, metadata parser coverage, watcher/index status.                                | DB-first detail, derivative status rows, compact list DTOs, preloading, queue status.       | gallery-repo with selective borrowing.                                             | Copy patterns, not platforms.                                                    |

## Specific Answers

### 1. When opening a folder with a few dozen images, which pipeline is currently superior?

gallery-repo.

Reason: `/api/scan` is intentionally a cheap hot path: directory iteration, stat, sort/page, and batch cached dimension lookup. It does not decode images or parse metadata. For a few dozen cold files, Immich and DiffusionToolkit both have more import/indexing machinery than this use case needs.

### 2. For metadata-to-lightbox flow, which pipeline is currently superior?

For a cold, ad hoc folder: gallery-repo is superior because the lightbox opens the original image path and metadata extraction is decoupled/on demand.

For a fully indexed warm library: Immich's DB-first viewer metadata is superior because `getAssetInfo` returns metadata from database rows and the viewer does not need to parse the original file.

DiffusionToolkit is not the model to copy for the web lightbox path because the existing audit found preview opening can synchronously reparse metadata before image display.

### 3. For search and indexing at large scale, which pipeline is superior?

Immich.

Reason: it has PostgreSQL metadata filters, timeline/date indexes, trigram/unaccent text search, OCR search, CLIP vector search, background indexing jobs, and derivative-backed ML workflows. gallery-repo's SQLite search is a better fit for current local AI metadata search, but not for a 100k+ multi-domain photo library.

### 4. For our gallery-repo goals, what should we borrow from DiffusionToolkit?

- Bounded background metadata indexing that does not block folder open.
- Batched SQLite writes for metadata/index updates.
- Broad AI-generation metadata parser coverage and sidecar discipline.
- Optional watcher/index refresh model for stable local folders.
- Clear indexing status/progress/error reporting.

### 5. For our gallery-repo goals, what should we borrow from Immich?

- DB-first viewer metadata when the cache is warm.
- Compact list/grid DTOs separate from full asset detail DTOs.
- Derivative status records for thumbnails/previews, mapped to SQLite.
- Next/previous viewer preloading for thumbnail/preview/metadata, not full originals by default.
- Queue/status model for background indexing and thumbnail warming, implemented locally rather than with Redis/BullMQ.

### 6. What should we avoid copying?

- PostgreSQL/Redis/BullMQ as default requirements.
- ML/OCR/CLIP smart search as a default path.
- Multi-user, album, sharing, backup, and storage-template semantics.
- Eager full derivative generation for every small cold folder.
- Replacing PhotoSwipe's original `/api/image` main source with preview derivatives.
- DiffusionToolkit's synchronous metadata reparse-before-preview pattern.

## Practical Borrowing Matrix

| Borrow                     | Source                    | Why                                        | gallery-repo mapping                                                   | Priority |
| -------------------------- | ------------------------- | ------------------------------------------ | ---------------------------------------------------------------------- | -------- |
| Keep scan minimal          | gallery-repo              | Protects first-open latency.               | Preserve `/api/scan` contract and tests.                               | P0       |
| Batch SQLite writes        | DiffusionToolkit          | Makes large indexing cheaper.              | Add writer batching around metadata/file index updates.                | P1       |
| Background indexing queue  | DiffusionToolkit + Immich | Warms metadata/search without blocking UI. | Small local SQLite/in-process queue, one worker default.               | P1       |
| DB-first lightbox metadata | Immich                    | Warm metadata panel becomes instant.       | Prefer cached metadata; queue missing extraction.                      | P1       |
| Index status/progress      | DiffusionToolkit + Immich | Makes background work visible.             | `/api/index/status` or similar.                                        | P1       |
| Next/prev preload          | Immich                    | Smoother lightbox navigation.              | Prefetch metadata and medium thumbnails; avoid full original preloads. | P1       |
| Derivative status rows     | Immich                    | Query cache readiness cheaply.             | SQLite derivative table keyed by path+mtime+size.                      | P1/P2    |
| Optional watcher           | DiffusionToolkit + Immich | Warms stable folders.                      | Disabled by default, opt-in per root.                                  | P2       |
| Full-text facets           | Immich                    | Better search at scale.                    | SQLite FTS/facet extensions after queue exists.                        | P2       |
| Semantic search            | Immich                    | Powerful discovery.                        | Optional plugin/feature flag only.                                     | P2/later |

## Recommended Roadmap

### P0 - Keep current guarantees

- Keep `/api/scan` free of metadata parsing and PIL probing.
- Keep scan dimension lookup batch-only and cache-only.
- Keep `/api/thumbnail` as the lazy image-open path.
- Keep `/api/metadata` on demand until a background index exists.
- Keep PhotoSwipe main `src` as `/api/image`.
- Keep album-open and lightbox-open/transition Playwright perf tests as hard gates.

### P1 - High value borrow

- Add a bounded local metadata indexing queue.
  - Files likely affected: `backend/metadata_store.py`, `backend/metadata_parse.py`, `backend/search.py`, new queue module.
  - Benefit: warm metadata/search without blocking scan.
  - Risk: CPU/disk contention.
  - Test plan: queue coalescing, stale invalidation, perf tests.
  - Perf budget: no scan p95 regression.

- Add batched SQLite writer.
  - Files likely affected: `backend/metadata_store.py`.
  - Benefit: fewer writes and less lock churn for large folders.
  - Risk: long transactions if batches are too large.
  - Test plan: transaction tests and large-folder fixture.
  - Perf budget: bounded batch size, no request-path long locks.

- Add index status/progress endpoint.
  - Files likely affected: backend API modules and frontend optional status view.
  - Benefit: users can tell whether metadata is still warming.
  - Risk: inaccurate status if queue bookkeeping is weak.
  - Test plan: API status tests for pending/running/done/error.
  - Perf budget: status p95 under 50 ms warm.

- Add next/previous metadata/thumbnail prefetch.
  - Files likely affected: `frontend/src/stores/lightbox.ts`, `frontend/src/composables/usePhotoSwipe.ts`.
  - Benefit: smoother lightbox transitions.
  - Risk: wasteful prefetch during rapid navigation.
  - Test plan: extend lightbox perf tests; assert no full original preloads.
  - Perf budget: no initial lightbox-open regression.

### P2 - Later

- DB-backed folder listing for very large folders.
- Optional folder watcher.
- Preview derivative table and warmer.
- Advanced search facets.
- Optional semantic search.

### Avoid

- Do not make PostgreSQL or Redis required.
- Do not parse all metadata in `/api/scan`.
- Do not eagerly generate every derivative before first grid render.
- Do not change PhotoSwipe main source away from `/api/image` unless the product requirement changes.
- Do not import Immich's multi-user/photo-backup model into the local gallery core.

## Files Inspected And Evidence Notes

gallery-repo evidence:

- `backend/scan.py`: scan path uses cached dimension lookup and avoids image probing.
- `backend/thumbnails.py`: thumbnail endpoint opens images only for thumbnail generation and records dimensions then.
- `backend/metadata_parse.py`: metadata extraction is request-driven and cached.
- `backend/metadata_store.py`: SQLite metadata, dimension, file index, FTS/trigram structures.
- `frontend/src/utils/lightbox.ts`: PhotoSwipe item `src` is `/api/image`; `msrc` is thumbnail.
- `frontend/src/composables/usePhotoSwipe.ts`: dimension resolver order includes scan/cache/metadata/thumbnail natural dimensions.
- `frontend/tests/e2e/perf/album-open.perf.spec.ts` and `frontend/tests/e2e/perf/lightbox.perf.spec.ts`: enforce the current hot paths.

DiffusionToolkit evidence from existing audit:

- Scanner and metadata files include `Diffusion.Scanner/MetadataScanner.cs`, `Metadata.cs`, `FileParameters.cs`, and `StealthPng.cs`.
- Background services include `ScanningService.cs`, `MetadataScannerService.cs`, `DatabaseWriterService.cs`, and `FolderService.cs`.
- Thumbnail/cache/viewer files include `ThumbnailService.cs`, `ThumbnailCache.cs`, `Search.xaml.cs`, and `PreviewPane.xaml.cs`.
- The audit concluded that DiffusionToolkit has strong AI metadata parser/index coverage, but its first import and preview path do more work than gallery-repo's web hot paths.

Immich evidence:

- Import/library: `server/src/services/library.service.ts`, `server/src/repositories/storage.repository.ts`, `server/src/services/asset-media.service.ts`.
- Metadata: `server/src/services/metadata.service.ts`, `server/src/repositories/metadata.repository.ts`, `server/src/schema/tables/asset-exif.table.ts`.
- Thumbnails: `server/src/services/media.service.ts`, `server/src/cores/storage.core.ts`, `server/src/schema/tables/asset-file.table.ts`.
- Jobs: `server/src/services/job.service.ts`, `server/src/repositories/job.repository.ts`, `server/src/services/queue.service.ts`.
- Timeline: `server/src/controllers/timeline.controller.ts`, `server/src/repositories/asset.repository.ts`, `web/src/lib/managers/timeline-manager/timeline-manager.svelte.ts`, `web/src/lib/managers/timeline-manager/internal/load-support.svelte.ts`.
- Viewer: `web/src/lib/utils.ts`, `web/src/lib/components/AdaptiveImage.svelte`, `web/src/lib/components/asset-viewer/PreloadManager.svelte.ts`, `web/src/lib/components/asset-viewer/DetailPanel.svelte`.
- Search: `server/src/services/search.service.ts`, `server/src/repositories/search.repository.ts`, `server/src/schema/tables/smart-search.table.ts`, `server/src/services/smart-info.service.ts`, `server/src/services/ocr.service.ts`.

## Final Recommendation

Keep gallery-repo's current architecture as the base. It is the best match for fast local web folder browsing and original-image lightbox display. Borrow from DiffusionToolkit first where the pattern is local and SQLite-friendly: background indexing, batch writes, parser coverage, and status. Borrow from Immich where the pattern improves scale without importing the platform: DB-first metadata reads, compact list DTOs, derivative readiness records, and next/previous preloading.

The correct near-term direction is not "become Immich" or "become DiffusionToolkit." It is to preserve the existing scan/lightbox guarantees and add a small, observable background indexing layer that can make warm folders behave more like a prepared library.

## Uncertainties

- DiffusionToolkit claims here rely on the existing audit rather than a fresh source clone in this session.
- Immich behavior can vary by config, especially fullsize generation, watcher enablement, queue concurrency, ML enablement, and viewer original-loading preference.
- No live benchmarks were run across the three projects. The comparisons are architecture and code-path based.
- The 5000/100k conclusions assume warm indexed state for Immich and DiffusionToolkit, and current folder-scan behavior for gallery-repo.

## Updated for current architecture

Verified against the current repository on 2026-06-18:

- gallery-repo no longer uses the original image as the initial PhotoSwipe
  source. The current sequence is thumbnail placeholder → 1440px preview
  derivative → original on zoom/fullscreen/animated/preference/fallback.
- The comparison's proposed local metadata queue now exists. Scan-discovered
  paths are staged outside the hot path, persisted as SQLite jobs, coalesced,
  parsed by a bounded worker, and written in batches.
- DB-first warm metadata reads and `/api/index/status` are implemented.
- Warm indexed folder listing is available behind
  `ENABLE_WARM_INDEXED_LISTING`, with direct-scan fallback for missing,
  incomplete, or stale state.
- Optional watcher and scheduled refresh workers exist in `backend/watcher.py`
  and `backend/refresh.py` and are disabled by default.
- Derivative generation is implemented in `backend/thumbnails.py`; no separate
  `backend/derivatives.py` module exists.

The external DiffusionToolkit and Immich observations remain historical audit
findings. Statements above about gallery-repo lacking these features or
requiring `src=/api/image` as the main lightbox source are superseded by this
section and [Architecture](../ARCHITECTURE.md).
