# DiffusionToolkit Pipeline Audit

Last reviewed: 2026-06-09

## Executive summary

This audit compares the metadata, thumbnail, indexing, and viewer pipeline in
[DiffusionToolkit](https://github.com/RupertAvery/DiffusionToolkit) with the
current gallery pipeline.

DiffusionToolkit is stronger at long-lived desktop library management: it has a
durable metadata database, broad Stable Diffusion metadata support, background
metadata scan queues, batch database writes, search-oriented indexes, and folder
watchers.

gallery-repo is stronger at the current web-gallery hot path: opening a folder
does not eagerly parse image metadata, thumbnails are lazy and strongly
invalidated by file mtime/size, metadata loading is on demand, and the lightbox
opens without waiting for metadata extraction.

The biggest gallery-repo gap is not lightbox metadata display. It is the lack of
a full background metadata indexing queue, plus the fact that `/api/scan` still
enumerates and sorts all images in a directory before returning a page.

The main idea worth borrowing from DiffusionToolkit is a bounded background
metadata indexing pipeline with batched SQLite writes. It should be adapted to
the FastAPI/Vue web architecture and kept off the `/api/scan` hot path.

## Scope and sources

This is a code-reading audit. No runtime code or dependency files were changed
for the investigation.

Reference commits:

| Repo | Commit inspected |
|---|---|
| DiffusionToolkit | `153409c3a0e9569886e6601530365808d4ecbb0e` |
| gallery-repo | `b7a83ed8bfe7d2e6e3662f63c6a23ad379e27ffb` |

One requested file, `backend/services/metadata_index.py`, does not exist in this
checkout. The actual gallery SQLite metadata and indexing layer is
[`backend/metadata_store.py`](../backend/metadata_store.py).

## DiffusionToolkit files inspected

| Area | Files |
|---|---|
| File discovery and scan entry points | [`Diffusion.Scanner/MetadataScanner.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/MetadataScanner.cs) |
| Metadata parsing | [`Diffusion.Scanner/Metadata.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/Metadata.cs), [`FileParameters.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/FileParameters.cs), [`StealthPng.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/StealthPng.cs) |
| Background scan/index queue | [`ScanningService.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/ScanningService.cs), [`MetadataScannerService.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/MetadataScannerService.cs), [`DatabaseWriterService.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/DatabaseWriterService.cs) |
| Folder import/watch | [`FolderService.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Services/FolderService.cs), [`MainWindow.xaml.Folders.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/MainWindow.xaml.Folders.cs), [`MainWindow.xaml.Scanning.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/MainWindow.xaml.Scanning.cs) |
| Database/schema/search | [`DataStore.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/DataStore.cs), [`Models/Image.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/Models/Image.cs), [`DataStore.Image.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/DataStore.Image.cs), [`DataStore.Search.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/DataStore.Search.cs), [`QueryCombiner.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/QueryCombiner.cs) |
| Thumbnails | [`ThumbnailService.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Thumbnails/ThumbnailService.cs), [`ThumbnailCache.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Thumbnails/ThumbnailCache.cs), [`ThumbnailView.xaml.Page.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Controls/ThumbnailView.xaml.Page.cs) |
| Viewer/detail/lightbox | [`Search.xaml.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Pages/Search.xaml.cs), [`Search.xaml.Navigation.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Pages/Search.xaml.Navigation.cs), [`PreviewPane.xaml.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Controls/PreviewPane.xaml.cs), [`MetadataPanel.xaml`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Controls/MetadataPanel.xaml), [`MainWindow.xaml.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/MainWindow.xaml.cs) |

## gallery-repo files inspected

| Area | Files |
|---|---|
| FastAPI composition | [`backend/main.py`](../backend/main.py), [`backend/app.py`](../backend/app.py) |
| Scan path | [`backend/scan.py`](../backend/scan.py) |
| Original image serving | [`backend/images.py`](../backend/images.py) |
| Thumbnail path | [`backend/thumbnails.py`](../backend/thumbnails.py) |
| Metadata parsing | [`backend/metadata_parse.py`](../backend/metadata_parse.py), [`backend/metadata_extract.py`](../backend/metadata_extract.py) |
| SQLite metadata/index/search | [`backend/metadata_store.py`](../backend/metadata_store.py), [`backend/search.py`](../backend/search.py) |
| API client/query keys | [`frontend/src/services/api.ts`](../frontend/src/services/api.ts), [`frontend/src/query/keys.ts`](../frontend/src/query/keys.ts), [`frontend/src/query/index.ts`](../frontend/src/query/index.ts) |
| Scan/search queries | [`frontend/src/composables/useInfiniteScanQuery.ts`](../frontend/src/composables/useInfiniteScanQuery.ts), [`frontend/src/composables/useUnifiedSearchQuery.ts`](../frontend/src/composables/useUnifiedSearchQuery.ts) |
| Grid and thumbnails | [`frontend/src/components/GalleryGrid.vue`](../frontend/src/components/GalleryGrid.vue), [`frontend/src/components/PhotoCard.vue`](../frontend/src/components/PhotoCard.vue) |
| Lightbox and dimensions | [`frontend/src/components/Lightbox.vue`](../frontend/src/components/Lightbox.vue), [`frontend/src/components/PhotoSwipeViewer.vue`](../frontend/src/components/PhotoSwipeViewer.vue), [`frontend/src/composables/usePhotoSwipe.ts`](../frontend/src/composables/usePhotoSwipe.ts), [`frontend/src/utils/lightbox.ts`](../frontend/src/utils/lightbox.ts), [`frontend/src/stores/lightbox.ts`](../frontend/src/stores/lightbox.ts) |
| Perf/instrumentation docs/tests | [`frontend/tests/e2e/perf/album-open.perf.spec.ts`](../frontend/tests/e2e/perf/album-open.perf.spec.ts), [`frontend/tests/e2e/perf/lightbox.perf.spec.ts`](../frontend/tests/e2e/perf/lightbox.perf.spec.ts), [`docs/ARCHITECTURE.md`](ARCHITECTURE.md), [`docs/PERFORMANCE_TESTING.md`](PERFORMANCE_TESTING.md) |

## DiffusionToolkit pipeline

```text
User adds/scans watched folder
-> MetadataScanner.GetFiles discovers image files
-> MetadataScannerService queues files to 2 metadata workers
-> Metadata.ReadFromFile reads whole file, hashes it, parses metadata
-> DatabaseWriterService batches DB writes
-> Search page queries SQLite with paging
-> ThumbnailView queues visible-ish thumbnails
-> ThumbnailService reads thumbnail cache or renders thumbnail
-> User selects/opens image
-> Search.LoadPreviewImage reparses metadata synchronously
-> full bitmap loads on Task.Run
-> PreviewPane and MetadataPanel show image and metadata
```

Stage notes:

| Stage | Behavior |
|---|---|
| Folder discovery | Async/background. Uses recursive directory enumeration with cancellation and ignored/inaccessible folder handling. |
| Image list | Primarily DB/search driven after scan. Search uses SQLite paging. |
| Metadata parsing | Eager for every file selected for scan/import. Also lazy again when selecting an image in the viewer. |
| PNG metadata | Handles PNG text chunks, NovelAI, InvokeAI, EasyDiffusion, ComfyUI, A1111-style parameters, EXIF user comments, sidecar text, and Stealth PNG fallback. |
| JPEG/WebP metadata | Handles EXIF user comments, Fooocus/A1111, SwarmUI, ComfyUI JSON/workflow conventions. |
| Cache/index | Durable SQLite image records with many AI metadata indexes; optional workflow/node storage. |
| Thumbnails | Background queue, 2 workers, visible-area loading, persistent per-folder SQLite `dt_thumbnails.db`. |
| Viewer metadata | Reparsed from the selected original file before the async bitmap load starts. This can block the WPF UI path for expensive metadata. |
| Dimensions | Parsed into DB during scan; viewer fit uses loaded bitmap dimensions. |
| Cold cache | Initial import does full metadata extraction and full-file hash work for each scanned image. |
| Warm cache | DB-backed search/list and thumbnail cache are strong, but viewer selection still reparses metadata from disk. |

Important implementation details:

- `Metadata.ReadFromFileInternal()` reads the entire file into memory and hashes it before metadata parsing.
- Metadata workers and thumbnail workers both use a degree of parallelism of 2.
- Database writes are batched around 33 records.
- `FolderService` can create `FileSystemWatcher` instances and queue new/renamed files.
- `Search.LoadPreviewImage()` calls `Metadata.ReadFromFile()` synchronously before dispatching the full bitmap load to `Task.Run`.
- In the inspected parser, `fileParameters.Hash = hash` appears only in the no-metadata fallback. Hash-based move detection may therefore be incomplete or intentional in a way that needs runtime confirmation.

## gallery-repo pipeline

```text
Album/folder click
-> useInfiniteScanQuery
-> GET /api/scan
-> os.scandir direct folder, stat image files, no PIL probing
-> batched SQLite lookup for cached dimensions
-> return folders + paginated images, null dimensions on cold cache
-> background index file/folder rows only, include_metadata=False
-> virtualized grid renders PhotoCard thumbnails
-> GET /api/thumbnail lazily generates/serves WebP and upserts dimensions
-> click image opens Lightbox immediately
-> PhotoSwipe item uses /api/image as src and thumbnail as msrc
-> async dimension resolver uses scan, remembered, metadata, thumbnail fallback
-> GET /api/metadata parses metadata on demand and upserts SQLite cache
-> metadata panel updates when query resolves
```

Current behavior:

| Stage | Behavior |
|---|---|
| `/api/scan` | Hot path. Lists folder entries with `os.scandir`, filters image extensions, stats files, does a single batch dimension lookup, sorts folders/images, then applies offset pagination. |
| Cold dimensions | Returns `width=None`, `height=None` when dimensions are not cached. It does not open images with PIL. |
| Background scan work | Indexes folder/file rows in SQLite, including recursive `file_index`, but calls `index_directory_tree(..., include_metadata=False)`. |
| `/api/thumbnail` | Generates WebP thumbnails lazily, persists cache files, uses browser ETags, and upserts dimensions because the image is already opened. |
| Thumbnail invalidation | Cache key includes resolved path, `mtime_ns`, size, max size, and quality. |
| `/api/metadata` | Parses metadata on demand in a FastAPI threadpool, uses an in-memory LRU keyed by path/mtime/size, coalesces in-flight duplicate parses, and upserts full metadata into SQLite. |
| SQLite metadata cache | Stores dimensions, core AI fields, raw text, JSON metadata, FTS5 unicode/trigram indexes, and separate `file_index` rows for recursive album/photo search. |
| Frontend server state | TanStack Query owns scan, infinite scan pages, metadata, and search responses. Pinia owns UI/navigation state. |
| Grid | TanStack Virtual renders image rows; IntersectionObserver fetches more scan pages. |
| Lightbox | Opens before metadata resolves. PhotoSwipe `src` is `/api/image`; thumbnail is `msrc` only. |
| Dimension resolver | Uses scan dimensions, remembered thumbnail dimensions, cached metadata dimensions, then async metadata or thumbnail fallback and refreshes slide content. |
| Perf coverage | Playwright tests enforce album-open and lightbox-open/transition budgets. Prometheus and pyinstrument are available for backend profiling. |

## Strengths and weaknesses

| Area | DiffusionToolkit | gallery-repo | Which is better | Why |
|---|---|---|---|---|
| Folder open latency | Strong after DB index; first import parses all selected files. | Fast cold direct scan; no metadata/PIL probing. | gallery-repo for cold dozens | Less work before first content appears. |
| Cold cache behavior | Background scan is non-UI-blocking, but metadata/hash work is eager for all imported files. | Returns null dimensions and defers expensive work. | gallery-repo | Better first-response latency. |
| Subsequent visit behavior | DB search/list and thumbnail cache are strong. | TanStack Query, cached thumbs/dims, but `/api/scan` still rescans/sorts directory. | DT for huge warm folders | Indexed warm listing scales better. |
| Metadata parsing strategy | Broad eager background parse plus viewer reparse. | On-demand parse, cached, threadpooled, in-flight coalesced. | Split | DT has coverage; gallery has better UI flow. |
| Thumbnail generation strategy | Background visible queue, persistent per-folder SQLite cache. | Browser lazy load, persistent WebP cache, ETag, mtime/size invalidation. | gallery-repo | Better fit for web and safer invalidation. |
| Viewer/lightbox dimensions | Fit uses loaded bitmap dimensions. | PhotoSwipe gets best-known dimensions up front and async repairs. | gallery-repo | Browser lightboxes need predeclared dimensions. |
| Full-image loading | WPF bitmap loaded on background task. | `/api/image` full-res FileResponse, tested that lightbox uses it. | gallery-repo | Correct browser endpoint separation. |
| UI responsiveness | Good during background scan; weaker on viewer metadata reparse. | Metadata and dimensions do not gate lightbox open. | gallery-repo | Avoids blocking click-to-lightbox path. |
| Background indexing | Mature queue, workers, progress, batch writes, watchers. | Background file index only; full metadata deferred. | DT | This is DT's strongest architecture piece. |
| Cache invalidation | DB rows by path; thumbnail cache key is filename+size inside per-folder DB. | Dimensions and thumbnails validated by path/mtime/size. | gallery-repo | Lower stale-cache risk. |
| Database schema/indexing | Rich AI columns, node/property indexes, tag/album data. | Simpler metadata table, FTS5, file_index. | DT for AI library management | More queryable metadata dimensions. |
| Error handling | IO retries and logs parse errors. | API errors, path safety, invalid image handling, tolerated cache misses. | gallery-repo for web | Better HTTP boundary and deployment behavior. |
| Scalability for 50 images | Good after import; first scan does more work. | Fast scan, lazy visible thumbnails. | gallery-repo | Better perceived cold performance. |
| Scalability for 5,000+ images | Expensive initial indexing; warm DB paging is strong. | Lists and sorts all images before returning a page. | DT warm | gallery needs indexed warm folder listing. |
| Simplicity/maintainability | Mature but desktop/service-locator heavy. | Smaller FastAPI/Vue pipeline with documented ownership. | gallery-repo | Easier to evolve for this web app. |
| Testability/perf coverage | No comparable perf tests found in inspected code. | Playwright perf tests plus Prometheus/pyinstrument docs. | gallery-repo | Regressions are measurable. |

## Ideas worth borrowing

| Idea | What DT does | How it maps to gallery-repo | Risk | Complexity | Affects | Improves |
|---|---|---|---|---|---|---|
| Background metadata indexer | Queues scanned files to metadata workers, writes results to DB in the background. | Add a bounded backend worker fed by `/api/scan`, explicit rebuild actions, and possibly idle thumbnail/metadata events. | Medium | Medium | Backend | Warm cache, search |
| Batched DB writer | Batches add/update writes and progress updates. | Batch `image_metadata` and `file_index` upserts to reduce SQLite lock churn. | Medium | Medium | Backend | Warm cache, 5,000+ scale |
| Queue status/progress | Scan services report progress and completion. | Add `/api/index/status` and optional frontend status UI. | Low-medium | Medium | Both | Operability |
| Rich AI metadata schema | Stores model, sampler, seed, steps, CFG, workflow, node/property data. | Add optional structured columns/facets beyond raw metadata JSON. | Medium-high | High | Both | Search/filter UX |
| Explicit rescan/rebuild controls | Supports scan/rebuild flows and thumbnail rebuild. | Add admin endpoints for metadata/thumb rebuild and stale-cache cleanup. | Low-medium | Medium | Backend, maybe frontend | Maintenance |
| Optional local folder watcher | Uses `FileSystemWatcher` for watched roots. | Optional local-only watcher using `watchdog` or `watchfiles`, disabled by default for VPS/web. | High | Medium | Backend | Warm cache freshness |
| Broader sidecar/format coverage | Supports sidecar text and many generator metadata layouts. | Extend `metadata_parse.py` and `metadata_extract.py` fixtures. | Medium | Medium | Backend | Metadata coverage |
| Visible thumbnail queue discipline | Queues thumbnails around visible viewport. | If thumbnail storms become measured, add backend-side concurrency limiting or request coalescing. | Low-medium | Medium | Backend | Cold thumbnail stability |

## Things not to copy

| DT pattern | Why it does not fit gallery-repo | Risk if copied blindly |
|---|---|---|
| Synchronous viewer metadata reparse | A web lightbox should open immediately and let metadata update asynchronously. | Click and next/prev stalls. |
| Full-file hash/read for every image on folder open | Bad for cold web/VPS folders and very large AI images. | Major cold-open latency and memory pressure. |
| Per-folder thumbnail SQLite keyed by filename+size | gallery already has path/mtime/size cache keys. | Stale thumbnails after edits/replacements. |
| Desktop `FileSystemWatcher` as default | The app is local-first but still web/VPS/mobile capable. | Platform-specific missed events or excess IO. |
| WPF paging/wrap-panel thumbnail model | gallery already has TanStack Virtual and browser lazy loading. | Worse DOM/scroll behavior. |
| Viewer dimensions only after full image load | PhotoSwipe needs dimensions before image load for correct layout. | Wrong aspect ratio or jumps. |
| Eager workflow/node indexing for every image | Workflows can be large and not always needed. | SQLite bloat and slow cold indexing. |
| Stealth PNG pixel scan in viewer path | Pixel-level fallback can be expensive. | Lightbox blocking on rare metadata formats. |

## Expected performance by case

| Case | DT likely bottleneck | gallery-repo likely bottleneck | Superior design | Evidence |
|---|---|---|---|---|
| Open folder with 50 AI images, cold cache | Eager full metadata/hash scan for each imported file. | Thumbnail generation after fast scan; dimensions initially null. | gallery-repo | `/api/scan` avoids PIL and metadata; DT reads whole files before parse. |
| Open same folder again, warm cache | DB query and thumbnail cache are fast. | `os.scandir` and sort still run, but dims/thumbs are cached. | Tie for 50; DT for large warm folders | DT DB paging; gallery direct scan plus Query cache. |
| Click first image into viewer/lightbox | Synchronous metadata reparse before preview model completes. | Full image load and async metadata query. | gallery-repo | Lightbox opens before `/api/metadata`; PhotoSwipe uses `/api/image`. |
| Switch next/prev in viewer/lightbox | Each selection can reparse metadata; page boundary reloads results. | PhotoSwipe swaps image and metadata query follows path. | gallery-repo | `usePhotoSwipe` resolves dimensions async and refreshes slide. |
| Open folder with 5,000 images | Initial indexing is expensive; warm DB paging is strong. | Direct `/api/scan` lists/sorts all images before slicing. | DT warm; gallery cold acceptable but weaker | gallery has pagination after full list/sort, not indexed folder listing. |

## Recommendations

### P0

No immediate correctness-critical change is required from this audit. Preserve
the current rule that `/api/scan` must not parse image metadata or open images
with PIL.

If 5,000+ image folders are a product target, treat indexed warm folder listing
or scan pagination optimization as P0 for that target.

### P1

1. Add a bounded background metadata indexer.
2. Add batched SQLite writes for metadata indexing.
3. Add index queue status/progress.
4. Add lightbox neighbor prefetch for metadata/dimensions.

### P2

1. Add richer structured AI metadata columns and facets.
2. Add optional local-only folder watching.
3. Add cache rebuild/clear endpoints.

### Do not copy

Do not copy DT's synchronous viewer parse, eager full-file hash on open,
thumbnail cache keying, or desktop-only folder watching assumptions.

## Proposed implementation tasks

| Task | Goal | Files likely affected | Risk | Acceptance criteria | Perf budget | Test plan |
|---|---|---|---|---|---|---|
| Background metadata index queue | Fill metadata cache/search in the background without slowing folder open. | `backend/metadata_store.py`, new worker module, `backend/scan.py`, `backend/metadata_parse.py`, maybe `backend/health.py` | Medium | `/api/scan` returns before metadata work; jobs coalesce by path+mtime+size; worker count is bounded. | `/api/scan` p95 regression under 10%. | Unit queue tests, parser fixture tests, album-open perf test. |
| Indexed warm folder listing | Avoid full list/sort work for large warm folders. | `backend/scan.py`, `backend/metadata_store.py`, `frontend/src/composables/useInfiniteScanQuery.ts` | Medium-high | Warm scan can serve page from `file_index` with stale validation/fallback. | 5,000-image warm first page under 300-500 ms on target machine. | Backend perf script and Playwright album-open perf. |
| Lightbox neighbor metadata/dimension prefetch | Make next/prev metadata and dimensions ready earlier. | `frontend/src/components/Lightbox.vue`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/stores/lightbox.ts` | Low | Previous/next metadata queries start in background; no duplicate requests; main image still uses `/api/image`. | No regression to lightbox open; transition budget improves or stays flat. | Existing lightbox perf tests plus query-count assertions if added. |
| Rich metadata facets | Improve search/filter by model, sampler, seed, steps, CFG, LoRA. | `backend/metadata_extract.py`, `backend/metadata_parse.py`, `backend/metadata_store.py`, search UI components | Medium | Structured fields populated from supported generators and searchable. | Metadata parse p95 remains bounded; DB size tracked. | Parser fixtures and search tests. |
| Cache maintenance endpoints | Let users rebuild stale thumbnails/metadata deliberately. | `backend/thumbnails.py`, `backend/metadata_store.py`, optional settings/admin UI | Low-medium | Rebuild/clear selected cache without deleting originals; operation reports progress. | Runs async; does not block normal scan/lightbox. | API tests and manual maintenance flow. |

## Direct answers

For opening a folder with dozens of images, gallery-repo is superior now because
the folder-open hot path avoids metadata extraction and image probing.

For metadata-to-lightbox flow, gallery-repo is superior now because the lightbox
opens before metadata resolves and repairs dimensions asynchronously.

For long-term maintainability, gallery-repo is superior for this web app if it
adds a background metadata indexer carefully. DiffusionToolkit is more mature as
a desktop AI-image library manager, but its pipeline is not directly portable to
a FastAPI/Vue browser app.

## Uncertainties

- DiffusionToolkit was not run end to end; conclusions are based on code reading.
- The UI-blocking assessment for DT viewer metadata is inferred from the
  synchronous `Metadata.ReadFromFile()` call in `LoadPreviewImage()`.
- The DT hash assignment path appears incomplete in the inspected parser because
  `Hash` is only assigned in the no-metadata fallback. This needs runtime or
  maintainer confirmation.
- Actual performance depends heavily on image size, disk speed, cache state,
  browser, device, and deployment topology.
