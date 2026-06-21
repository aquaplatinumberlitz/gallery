# Immich Media Pipeline Audit

> **Status:** Research snapshot. Statements about gallery-repo describe the
> reviewed revision and may be historical; use [Architecture](../ARCHITECTURE.md)
> for current behavior.

Date: 2026-06-21

References inspected:

- Immich: `f382624e689315f327632fff1505cca3cfa21640` (`2026-06-09`, shallow clone at `/tmp/immich-audit`)
- Immich re-verification: `62b00a1f26856845bc9005bb2dabf36ff478e358` (`2026-06-19`, shallow clone at `/home/ubuntu/immich`)
- gallery-repo: `155f120f81730fa7ac1e65609364135e4262e776`
- DiffusionToolkit audit input: [docs/DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md)

This is a source audit only. I did not run Immich, migrate its database, or benchmark it locally.

## Files Inspected

gallery-repo files:

- [backend/main.py](../../backend/main.py)
- [backend/app.py](../../backend/app.py)
- [backend/scan.py](../../backend/scan.py)
- [backend/thumbnails.py](../../backend/thumbnails.py)
- [backend/images.py](../../backend/images.py)
- [backend/metadata_store.py](../../backend/metadata_store.py)
- [backend/metadata_parse.py](../../backend/metadata_parse.py)
- [backend/metadata_extract.py](../../backend/metadata_extract.py)
- [backend/search.py](../../backend/search.py)
- [frontend/src/components/GalleryGrid.vue](../../frontend/src/components/GalleryGrid.vue)
- [frontend/src/components/PhotoCard.vue](../../frontend/src/components/PhotoCard.vue)
- [frontend/src/components/Lightbox.vue](../../frontend/src/components/Lightbox.vue)
- [frontend/src/components/PhotoSwipeViewer.vue](../../frontend/src/components/PhotoSwipeViewer.vue)
- [frontend/src/composables/usePhotoSwipe.ts](../../frontend/src/composables/usePhotoSwipe.ts)
- [frontend/src/utils/lightbox.ts](../../frontend/src/utils/lightbox.ts)
- [frontend/src/stores/lightbox.ts](../../frontend/src/stores/lightbox.ts)
- [frontend/src/services/api.ts](../../frontend/src/services/api.ts)
- [frontend/tests/e2e/perf/album-open.perf.spec.ts](../../frontend/tests/e2e/perf/album-open.perf.spec.ts)
- [frontend/tests/e2e/perf/lightbox.perf.spec.ts](../../frontend/tests/e2e/perf/lightbox.perf.spec.ts)
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- [docs/testing/PERFORMANCE_TESTING.md](../testing/PERFORMANCE_TESTING.md)
- [docs/DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md)

Note: the requested `backend/services/metadata_index.py` does not exist in this repo. The active metadata/indexing implementation is in [backend/metadata_store.py](../../backend/metadata_store.py), [backend/metadata_parse.py](../../backend/metadata_parse.py), and [backend/search.py](../../backend/search.py).

Immich files:

- `package.json`
- `server/package.json`
- `web/package.json`
- `mobile/pubspec.yaml`
- `machine-learning/pyproject.toml`
- `docker/docker-compose.yml`
- `server/src/main.ts`
- `server/src/app.module.ts`
- `server/src/app.common.ts`
- `server/src/workers/api.ts`
- `server/src/workers/microservices.ts`
- `server/src/workers/maintenance.ts`
- `server/src/controllers/library.controller.ts`
- `server/src/services/library.service.ts`
- `server/src/repositories/library.repository.ts`
- `server/src/repositories/storage.repository.ts`
- `server/src/controllers/asset-media.controller.ts`
- `server/src/services/asset-media.service.ts`
- `server/src/middleware/file-upload.interceptor.ts`
- `server/src/middleware/asset-upload.interceptor.ts`
- `server/src/services/metadata.service.ts`
- `server/src/repositories/metadata.repository.ts`
- `server/src/services/media.service.ts`
- `server/src/repositories/media.repository.ts`
- `server/src/cores/storage.core.ts`
- `server/src/repositories/asset.repository.ts`
- `server/src/repositories/asset-job.repository.ts`
- `server/src/schema/tables/asset.table.ts`
- `server/src/schema/tables/asset-exif.table.ts`
- `server/src/schema/tables/asset-file.table.ts`
- `server/src/schema/tables/asset-job-status.table.ts`
- `server/src/services/job.service.ts`
- `server/src/repositories/job.repository.ts`
- `server/src/repositories/event.repository.ts`
- `server/src/services/queue.service.ts`
- `server/src/controllers/queue.controller.ts`
- `server/src/controllers/job.controller.ts`
- `server/src/controllers/timeline.controller.ts`
- `server/src/services/timeline.service.ts`
- `server/src/dtos/asset-response.dto.ts`
- `server/src/services/search.service.ts`
- `server/src/repositories/search.repository.ts`
- `server/src/controllers/search.controller.ts`
- `server/src/dtos/search.dto.ts`
- `server/src/schema/tables/smart-search.table.ts`
- `server/src/schema/tables/ocr-search.table.ts`
- `server/src/schema/tables/asset-ocr.table.ts`
- `server/src/services/smart-info.service.ts`
- `server/src/repositories/machine-learning.repository.ts`
- `server/src/services/ocr.service.ts`
- `server/src/controllers/sync.controller.ts`
- `server/src/services/sync.service.ts`
- `server/src/repositories/sync.repository.ts`
- `server/src/schema/tables/sync-checkpoint.table.ts`
- `server/src/controllers/video-stream.controller.ts`
- `server/src/services/hls.service.ts`
- `server/src/services/transcoding.service.ts`
- `server/src/repositories/video-stream.repository.ts`
- `server/src/schema/tables/video-stream.table.ts`
- `server/src/schema/tables/asset-av.table.ts`
- `server/src/controllers/plugin.controller.ts`
- `server/src/controllers/workflow.controller.ts`
- `server/src/services/plugin.service.ts`
- `server/src/services/workflow.service.ts`
- `server/src/services/workflow-execution.service.ts`
- `server/src/repositories/plugin.repository.ts`
- `server/src/repositories/workflow.repository.ts`
- `server/src/schema/tables/plugin.table.ts`
- `server/src/schema/tables/plugin-method.table.ts`
- `server/src/schema/tables/workflow.table.ts`
- `server/src/schema/tables/workflow-step.table.ts`
- `server/src/services/database-backup.service.ts`
- `server/src/services/integrity.service.ts`
- `server/src/repositories/integrity.repository.ts`
- `server/src/schema/tables/integrity-report.table.ts`
- `server/src/enum.ts`
- `server/src/config.ts`
- `web/src/lib/utils.ts`
- `web/src/lib/utils/asset-utils.ts`
- `web/src/lib/utils/thumbnail-util.ts`
- `web/src/lib/utils/adaptive-image-loader.svelte.ts`
- `web/src/lib/actions/image-loader.svelte.ts`
- `web/src/lib/components/AdaptiveImage.svelte`
- `web/src/lib/components/ImageLayer.svelte`
- `web/src/lib/components/assets/thumbnail/Thumbnail.svelte`
- `web/src/lib/components/assets/thumbnail/ImageThumbnail.svelte`
- `web/src/lib/components/timeline/Timeline.svelte`
- `web/src/lib/components/timeline/Month.svelte`
- `web/src/lib/components/timeline/TimelineAssetViewer.svelte`
- `web/src/lib/managers/timeline-manager/timeline-manager.svelte.ts`
- `web/src/lib/managers/timeline-manager/internal/load-support.svelte.ts`
- `web/src/lib/managers/asset-viewer-manager.svelte.ts`
- `web/src/lib/managers/AssetCacheManager.svelte.ts`
- `web/src/lib/components/asset-viewer/AssetViewer.svelte`
- `web/src/lib/components/asset-viewer/PhotoViewer.svelte`
- `web/src/lib/components/asset-viewer/PreloadManager.svelte.ts`
- `web/src/lib/components/asset-viewer/DetailPanel.svelte`
- `web/src/routes/(user)/+layout.ts`
- `web/src/routes/(user)/+layout.svelte`
- `web/src/routes/(user)/photos/[[assetId=id]]/+page.svelte`
- `web/src/routes/(user)/photos/[[assetId=id]]/+page.ts`
- `machine-learning/immich_ml/main.py`
- `machine-learning/immich_ml/models/cache.py`
- `machine-learning/immich_ml/models/clip/visual.py`
- `machine-learning/immich_ml/models/clip/textual.py`
- `machine-learning/immich_ml/models/facial_recognition/detection.py`
- `machine-learning/immich_ml/models/facial_recognition/recognition.py`
- `machine-learning/immich_ml/models/ocr/detection.py`
- `machine-learning/immich_ml/models/ocr/recognition.py`
- `mobile/lib/infrastructure/repositories/sync_api.repository.dart`
- `mobile/lib/domain/services/sync_stream.service.dart`

## Executive Summary

Immich is DB-first. It discovers or receives files, persists asset rows, then uses background queues for sidecar checks, metadata extraction, thumbnail generation, search indexing, OCR, face detection, and duplicate detection. Its web UI does not parse metadata from original files. It gets asset metadata from API DTOs backed by PostgreSQL rows.

Immich keeps the timeline fast by separating the lightweight timeline path from full asset detail. The timeline loads time bucket counts first, then loads compact per-month asset arrays when a month is in or near the viewport. Browser image requests use generated derivatives (`thumbnail`, `preview`, optional `fullsize`) or original endpoints depending on view and settings.

The server image supervises separate API and microservices runtime roles, with a
restricted maintenance role used during repair/migration mode. PostgreSQL is
the durable source of truth, Valkey/Redis backs BullMQ and cross-process
Socket.IO events, and the optional Python ML service handles CLIP, faces, and
OCR. Mobile clients maintain their own Drift/SQLite state through a checkpointed
incremental sync protocol rather than consuming the web timeline directly.

gallery-repo is intentionally different. Its `/api/scan` hot path lists a folder and reads cached dimensions from SQLite in a batch. It does not probe images with PIL or parse metadata during scan. Metadata is extracted on demand through `/api/metadata`, thumbnails are generated on demand through `/api/thumbnail`, and PhotoSwipe's main source is the original `/api/image`.

The strongest ideas to borrow from Immich are the DB-first metadata source, derivative/file status rows, bounded background jobs, compact list DTOs, and next/previous viewer preloading. The weakest fit is copying Immich's full server architecture: PostgreSQL, Redis/BullMQ, ML services, multi-user permissions, backup semantics, and mobile/server deployment assumptions are too heavy for gallery-repo's current local web folder-open goals.

## Direct Answers About Immich

| Question                                                   | Answer                                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Does Immich parse metadata immediately on import/scan?     | Not in the discovery hot path. Uploads enqueue `AssetExtractMetadata` after asset row creation. External library scans create asset rows from filesystem stat data, then queue sidecar checks, which queue metadata extraction.                                                 |
| Does Immich store metadata in the database?                | Yes. Core asset fields live in `asset`; EXIF/media fields live in `asset_exif`; derivative and sidecar files live in `asset_file`; job timestamps live in `asset_job_status`; OCR and smart-search data have separate tables.                                                   |
| Does Immich UI read metadata directly from original files? | No evidence found. The UI calls SDK/API methods such as `getAssetInfo`, `getTimeBuckets`, `getTimeBucket`, search endpoints, OCR, and faces. Original files are read server-side for extraction or media serving.                                                               |
| Does Immich generate thumbnails eagerly?                   | Yes, as background jobs after metadata extraction/storage-template flow, and through admin/maintenance queue-all jobs for missing thumbnails. It is not per-request lazy thumbnail generation in the gallery-repo sense.                                                        |
| What thumbnail/media sizes exist by default?               | `thumbnail` WebP around 250 px, `preview` JPEG around 1440 px, and optional `fullsize` JPEG. Defaults are in `server/src/config.ts`.                                                                                                                                            |
| Does the lightbox/viewer load original directly?           | Usually no. The web viewer starts with thumbnail, promotes to preview, and loads original/fullsize on zoom, user preference, animated images, preview failure, or explicit original/download flows.                                                                             |
| Is original only loaded for zoom/download/fullscreen?      | No. Zoom and download are explicit original paths, but the `alwaysLoadOriginalFile` preference, animated images, unsupported formats that need `fullsize`, and preview fallback also affect source choice. Fullscreen alone does not force original in the normal photo viewer. |
| How does Immich search?                                    | PostgreSQL SQL filters and indexes for metadata; trigram/unaccent indexes for filename/path/OCR/person/place style search; vector search over CLIP embeddings for smart search; OCR text indexed separately.                                                                    |
| How does Immich handle large libraries?                    | It relies on PostgreSQL indexes, time-bucket timeline APIs, background queues, batch scan jobs, compact timeline responses, generated derivatives, and optional external library watcher support.                                                                               |

## Current gallery-repo Pipeline

`/api/scan`:

- Hot path for opening folders.
- Uses `os.scandir`, path filtering, stat data, sorting, and pagination.
- Does not open image files with PIL and does not parse AI metadata.
- Uses `get_cached_dimensions_for_files()` to batch-read cached width/height from SQLite.
- Returns width/height only when the cache row matches the file path, mtime, and size.
- Schedules background indexing work, but scan response does not wait for full metadata parsing.

`/api/thumbnail`:

- Serves or generates thumbnails.
- Uses persistent disk cache and file cache keys based on path, mtime, size, requested max size, and quality.
- Opens the image only when the thumbnail is not already cached.
- Populates the SQLite dimension cache when the image is already open for thumbnail generation.
- Uses ETag and browser cache headers.

`/api/metadata`:

- Extracts metadata on demand.
- Uses an in-process LRU and in-flight coalescing.
- Parses AI-generation metadata and sidecars.
- Populates the SQLite metadata cache and FTS/index tables.

Frontend:

- TanStack Query owns scan and metadata server state.
- Grid images use `/api/thumbnail`.
- PhotoSwipe main `src` is `/api/image`; `msrc` and placeholders can use thumbnails.
- The lightbox dimension resolver uses scan dimensions, remembered thumbnail natural dimensions, cached metadata, fetched metadata, and thumbnail natural dimensions in that order.
- Playwright perf tests cover album open and lightbox open/transition. The lightbox test asserts the full image source is `/api/image`.

## Immich Pipeline Detail

### 1. Asset Discovery and Import

Immich has two main import/discovery modes.

Upload import:

- `AssetMediaController.uploadAsset()` receives uploads at `/api/assets`.
- `FileUploadInterceptor` streams the file to storage while computing a SHA1 checksum.
- `AssetUploadInterceptor` can short-circuit duplicate uploads using a checksum header.
- `AssetMediaService.uploadAsset()` creates an `asset` row with checksum, original path, filename, owner, type, and initial date fields.
- If a sidecar is uploaded, it is stored in `asset_file` with sidecar type.
- An initial EXIF row can be upserted with file size.
- `AssetExtractMetadata` is queued.

External library scan:

- `LibraryController.scanLibrary()` queues library scan work.
- `LibraryService.queueScan()` queues `LibrarySyncFilesQueueAll` and `LibrarySyncAssetsQueueAll`.
- `StorageRepository.walk()` uses `fast-glob` over configured import paths, hidden-file and exclusion settings, and supported media extensions.
- `LibraryRepository.filterNewExternalAssetPaths()` filters already-known paths.
- `LibraryService.handleSyncFiles()` stats new files and creates asset rows.
- External scan uses a path-derived checksum (`sha1("path:" + normalizedPath)`) instead of reading and hashing the full file.
- Created external assets are marked `isExternal=true` and receive initial dates from filesystem stat data.
- `queuePostSyncJobs()` queues sidecar discovery; the job chain then queues metadata extraction.

Change and delete detection:

- `LibraryService.handleSyncAssets()` compares existing assets with filesystem stat data and marks missing/inaccessible/out-of-import-path/excluded assets offline.
- Optional watcher support uses `StorageRepository.watch()` with `chokidar`; add/change events queue `LibrarySyncFiles`, unlink queues removal.
- Library watching is disabled by default in config. Scheduled scan is enabled by default.

### 2. Metadata Extraction

Immich metadata extraction is background work.

Evidence:

- `JobService.onDone(SidecarCheck)` queues `AssetExtractMetadata`.
- `MetadataService.handleMetadataExtraction()` loads asset job data, reads tags from original media and sidecar files, updates the asset row, upserts EXIF, handles side effects, and marks `metadataExtractedAt`.
- `MetadataRepository` wraps `exiftool-vendored` and uses `exiftool.read(path, options)` for tag extraction.
- Video and GIF metadata may use ffprobe through the media repository.

Metadata sources:

- Original file tags from ExifTool.
- Sidecar tags when an `asset_file` sidecar exists.
- Video probe data for video/GIF-specific fields.
- Filesystem stat data for file size and date fallbacks.
- Reverse geocoding for place fields when coordinates are present.

Date selection:

- Immich tries EXIF/media date tags such as DateTimeOriginal, CreateDate, MediaCreateDate, GPSDateTime, and related fields.
- If metadata dates are unavailable, it falls back to file-created and file-modified timestamps.

Stored metadata:

| Metadata                | Where Immich stores it                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Width/height            | `asset.width`, `asset.height`; EXIF dimensions also in `asset_exif.exifImageWidth` and `asset_exif.exifImageHeight` |
| Date taken/local time   | `asset.localDateTime`, `asset.fileCreatedAt`, `asset.fileModifiedAt`; EXIF date fields in `asset_exif`              |
| EXIF camera info        | `asset_exif.make`, `model`, `lensModel`, `fNumber`, `focalLength`, `iso`, `exposureTime`                            |
| Location                | `asset_exif.latitude`, `longitude`, `city`, `state`, `country`, `timeZone`                                          |
| Orientation/projection  | `asset_exif.orientation`, `projectionType`; dimensions may be orientation-adjusted                                  |
| File size               | `asset_exif.fileSizeInByte`                                                                                         |
| Checksum/hash           | `asset.checksum`, `asset.checksumAlgorithm`; upload uses file SHA1, external library scan uses path-derived SHA1    |
| Sidecar info            | `asset_file` rows with sidecar file type and path                                                                   |
| Thumbnail/preview files | `asset_file` rows with derivative file type, path, edit flag, transparency/progressive flags                        |
| Job status              | `asset_job_status.metadataExtractedAt`, `facesRecognizedAt`, `duplicatesDetectedAt`, `ocrAt`                        |
| OCR                     | `asset_ocr` and `ocr_search`                                                                                        |
| Smart search            | `smart_search.embedding` vector                                                                                     |

The web UI reads this data through API DTOs such as `AssetResponseDto`; it does not parse EXIF from the original file in the browser.

### 3. Database and Indexing

Core model:

- `asset.table.ts`: id, owner, type, original path, original file name, dates, checksum, library id, external/offline flags, local date time, dimensions, thumbhash, status, visibility, stack/duplicate fields.
- `asset-exif.table.ts`: camera, EXIF, dimensions, file size, location, description, colorspace, bits, projection, rating, tags, and related media metadata.
- `asset-file.table.ts`: sidecar and derivative file records.
- `asset-job-status.table.ts`: job progress timestamps.

Indexes:

- Timeline/date indexes on local date time.
- Original path/library uniqueness for external libraries.
- Trigram/unaccent indexes for filename and text-style searches.
- Geography/location and person/place related indexes.
- Vector index over `smart_search.embedding`.

Immich's storage/indexing strategy assumes PostgreSQL and uses database capabilities that do not map directly to gallery-repo's current SQLite-only design.

### 4. Thumbnail, Preview, Fullsize, and Original Serving

Generation:

- `MediaService.handleGenerateThumbnails()` handles `AssetGenerateThumbnails`.
- Images are processed with sharp; videos/GIFs use ffmpeg extraction/probing paths.
- It generates a small thumbnail, preview, thumbhash, and optional fullsize derivative.
- It writes derivative files and then upserts `asset_file` rows.
- Old derivative files are queued for deletion.

Defaults from `server/src/config.ts`:

- `image.thumbnail`: WebP, size `250`, quality `80`.
- `image.preview`: JPEG, size `1440`, quality `80`.
- `image.fullsize`: disabled by default, JPEG, quality `80`.

Storage paths:

- `StorageCore.getImagePath()` places image derivatives under the thumbnails storage folder with owner-id nesting and filenames based on asset id and file type.
- `asset_file` records tell the server where a derivative or sidecar lives.

Serving:

- `/api/assets/:id/thumbnail?size=thumbnail|preview|fullsize` is served by `AssetMediaController.viewAsset()` and `AssetMediaService.viewThumbnail()`.
- `/api/assets/:id/original` serves the original or edited fullsize path through `downloadOriginal`.
- If `fullsize` is requested and the original is web-compatible and not edited, the thumbnail endpoint can redirect to original.
- If `fullsize` is requested but unavailable, Immich can fall back toward preview.

This differs from gallery-repo. gallery-repo lazily creates thumbnails on `/api/thumbnail` and serves originals through `/api/image`; Immich expects derivatives to exist from background jobs and serves them by asset id.

### 5. Timeline and Grid

Server:

- `TimelineController` exposes `/timeline/buckets` and `/timeline/bucket`.
- `AssetRepository.getTimeBuckets()` returns bucket counts grouped by month/day depending on request.
- `AssetRepository.getTimeBucket()` returns compact asset data for one bucket, not full EXIF detail.
- The bucket payload includes arrays such as ids, dates, owner ids, visibility flags, type/video flags, ratios, status, thumbhash, location snippets, and stack data.

Web:

- `TimelineManager` calls `getTimeBuckets()` during initialization.
- It creates virtual month objects from bucket counts before loading all assets.
- `loadFromTimeBuckets()` calls `getTimeBucket()` for a month when needed.
- `Timeline.svelte` renders only loaded, in-or-near-viewport months and shows skeletons for unloaded buckets.
- `Thumbnail.svelte` uses `getAssetMediaUrl({ size: AssetMediaSize.Thumbnail })`.
- `ImageThumbnail.svelte` renders the thumbnail image; videos can overlay playback on hover.

This keeps the normal timeline hot path DB-bound and derivative-bound. It does not read original files or parse metadata during scroll.

### 6. Viewer and Lightbox Source Selection

Route and asset detail:

- Clicking a timeline thumbnail navigates to an asset route.
- `web/src/routes/(user)/+layout.ts` calls `getAssetInfoFromParam(params)`.
- `web/src/routes/(user)/+layout.svelte` puts `page.data.asset` into `assetViewerManager`.
- `TimelineAssetViewer.svelte` uses `assetCacheManager.getAsset()` for the current, next, and previous full `AssetResponseDto` objects.
- `DetailPanel.svelte` displays metadata from `asset.exifInfo` and other DTO fields.

Image URL builder:

- `getAssetUrls(asset)` returns:
  - `thumbnail`: `/assets/:id/thumbnail?size=thumbnail`
  - `preview`: normally `/assets/:id/thumbnail?size=preview`
  - `original`: `/assets/:id/original` for web-compatible originals or `/assets/:id/thumbnail?size=fullsize` for non-web-compatible originals
- `targetImageSize()` chooses preview by default.
- It chooses original/fullsize when forced, when the `alwaysLoadOriginalFile` preference is set, or when the asset is an animated image.

Viewer loading:

- `AdaptiveImage.svelte` creates a `QualityList` of thumbnail, preview, original.
- `AdaptiveImageLoader` starts with thumbnail.
- After thumbnail load it triggers preview unless the viewer is zoomed; if zoomed, it triggers original.
- If preview errors, it triggers original.
- A reactive effect triggers original when zoom becomes greater than 1.
- `PreloadManager.svelte.ts` preloads next/previous assets by loading thumbnail and then preview; it does not eagerly load original unless preview fails.

Answer to original/preview question:

- Normal photo viewer initial display: thumbhash/thumbnail, then preview derivative.
- Original image: loaded on zoom, explicit original/download flows, `alwaysLoadOriginalFile`, animated images, or fallback.
- Unsupported browser formats: fullsize derivative may stand in for original.
- Metadata panel: DB/API DTO, not original file probing.

### 7. Search

Immich search is layered.

Metadata/filter search:

- `SearchController.searchMetadata()` handles metadata queries.
- `SearchService.searchMetadata()` applies user/partner/shared-link permissions and calls repository SQL.
- `SearchRepository.searchAssetBuilder()` joins asset, exif, tags, people, albums, OCR, and related tables as needed.
- Filters include dates, city/state/country, camera make/model/lens, rating, checksum, ids, library, user, original path/name, description, type, favorite, offline, encoded, motion, album membership, stack, EXIF presence, faces, deleted state, and visibility.

Text-ish search:

- Filename/path/description paths use PostgreSQL `ilike`, `f_unaccent`, and trigram indexes where configured.
- OCR text uses the OCR tables and trigram search.

Smart search:

- `SmartInfoService` queues assets with preview files for ML embedding.
- `MachineLearningRepository` calls ML `/predict` endpoints for CLIP image/text encoding and OCR/face functions.
- `smart_search.table.ts` stores a 512-dimensional vector embedding.
- `SearchRepository.searchSmart()` orders by vector distance.

The search path reads database/search-index data and generated previews; it does not inspect original files in the web request.

### 8. Background Jobs, Workers, and Queues

Immich uses BullMQ workers.

Relevant queues include:

- `metadataExtraction`
- `thumbnailGeneration`
- `videoConversion`
- `smartSearch`
- `faceDetection`
- `facialRecognition`
- `duplicateDetection`
- `backgroundTask`
- `storageTemplateMigration`
- `migration`
- `search`
- `sidecar`
- `library`
- `notifications`
- `backupDatabase`
- `ocr`
- `workflow`
- `integrityCheck` (present in the 2026-06-19 re-verification revision)
- `editor`

Important job chain:

```txt
Upload asset row
-> AssetExtractMetadata
-> AssetMetadataExtracted event
   -> StorageTemplateMigrationSingle
   -> matching plugin workflows
-> AssetGenerateThumbnails after storage-template success or skip
-> queue SmartSearch / face detection / OCR, plus video encoding for video
   [only when source=upload or notify=true]
-> emit upload-ready websocket notification without waiting for those follow-up jobs
-> SmartSearch success queues duplicate detection only when source=upload

External library asset row
-> SidecarCheck
-> same chain above
   [queuePostSyncJobs currently labels the source as upload to enable the fan-out]
```

The microservices process creates one BullMQ worker per queue. `QueueService`
updates worker concurrency from config, while the API process watches for the
presence of microservices workers. Admin/queue endpoints expose queue status,
pause/resume, empty, and job inspection operations.

### 9. Process Architecture

Immich packages several runtime roles in the server image rather than running
each domain as an independent service.

Supervisor and worker topology:

- `server/src/main.ts` is the process supervisor. It checks PostgreSQL for
  maintenance mode and starts the configured worker roles.
- The API role runs as a Node child process. It creates the NestJS/Express HTTP
  app, REST controllers, Socket.IO endpoint, OpenAPI setup, and static web app
  serving.
- The microservices role runs in a Node worker thread. It creates the common
  Nest application without public controllers, discovers job handlers, and
  starts one BullMQ worker for every queue.
- The maintenance role replaces normal API/microservices startup when the
  database is in maintenance mode. It exposes a restricted maintenance surface
  while migrations, restore, or repair operations are being handled.
- API and microservices use the same service/repository classes, but event and
  job decorators can restrict a handler to specific worker roles.

In-process orchestration:

- `EventRepository` discovers methods decorated with `@OnEvent`, orders them by
  priority, and invokes matching handlers sequentially within the process.
- Cross-process events and client updates use Socket.IO. The Redis/Valkey
  adapter allows events to reach the API or microservices process that owns the
  relevant handler or client connection.
- `JobRepository` discovers `@OnJob` handlers, verifies at startup that every
  `JobName` has exactly one handler, and maps each job to its BullMQ queue.
- PostgreSQL advisory locks serialize migrations, storage-template moves,
  nightly scheduling, library watching, plugin import, backups, and other
  singleton operations across server instances.

Deployment shape:

```txt
immich-server container
  -> supervisor
     -> API child process
        [REST, Socket.IO, OpenAPI, static Svelte app]
     -> microservices worker thread
        [BullMQ consumers, media/metadata/ML/library work]
     -> maintenance worker instead of normal roles when maintenance mode is active

shared infrastructure
  -> PostgreSQL
     [assets, EXIF, derivatives, jobs, sync/audit data, search vectors]
  -> Valkey/Redis protocol
     [BullMQ queues and Socket.IO adapter]
  -> filesystem storage
     [originals, sidecars, derivatives, encoded video, backups, temporary HLS]
  -> optional Immich ML service
     [CLIP, faces, OCR]
```

### 10. Mobile Sync and Incremental State Replication

Mobile synchronization is a separate workflow from upload and from the web
timeline APIs.

Server protocol:

- `POST /sync/stream` returns `application/jsonlines+json`, allowing the server
  to stream ordered changes without building one large response in memory.
- Sync requires a user session; API keys cannot use the checkpoint protocol.
- Each session stores acknowledgements in `session_sync_checkpoint`. The mobile
  client sends the latest acknowledgement after applying a batch locally.
- The server captures a `nowId` at the start of a stream so all requested entity
  types are read against a stable upper bound.
- Entity streams include users, partners, assets, stacks, albums and album
  membership, EXIF, OCR, people/faces, memories, user metadata, asset metadata,
  and asset edits.
- Upserts use monotonic update ids. Deletes and relationship changes use audit
  tables and delete triggers so removals can be replicated after the primary
  row is gone.
- Newly shared partner/album data can require backfill. Backfill checkpoints
  track both the entity that caused the backfill and progress inside its rows.
- Audit history is retained for a bounded period. If the last complete client
  checkpoint is older than 30 days, the server sends `SyncResetV1` and the
  client must perform a full resynchronization.
- `AuditTableCleanup` removes expired audit rows as background maintenance.

Mobile client behavior:

- The Flutter client reads the JSONL response incrementally, applies events in
  bounded batches, and acknowledges durable progress.
- Remote state is materialized into the mobile Drift/SQLite database; the
  mobile UI does not use the web timeline manager as its source of truth.
- Local-device backup/upload is a related but distinct path: file upload creates
  server assets, while sync propagates resulting server-side state and later
  updates back to the mobile database.

### 11. Video, Encoded Media, and On-Demand HLS

Video has two serving paths: a persistent encoded-video derivative and an
on-demand adaptive HLS path.

Metadata and persistent encoding:

- Metadata extraction calls ffprobe for video/GIF media and stores normalized
  stream data in `asset_video`, `asset_audio`, and `asset_keyframe`, in addition
  to asset/EXIF fields such as dimensions, duration, frame rate, and dates.
- Video thumbnail generation extracts a representative frame and writes the
  same thumbnail/preview/thumbhash derivative set used by image assets.
- For upload-source videos, successful thumbnail generation queues
  `AssetEncodeVideo` along with smart search, faces, and OCR.
- The encoded output is recorded as an `asset_file` row of type
  `encoded_video`. The normal playback endpoint serves that derivative when it
  exists and otherwise falls back to the original file.
- FFmpeg policy selects codecs, resolution, bitrate, audio handling, and
  hardware acceleration from system configuration. Supported deployment
  profiles include CPU and platform-specific acceleration such as NVENC,
  Quick Sync, VAAPI, RKMPP, and Mali paths.

On-demand HLS:

- Real-time transcoding is feature-gated by the FFmpeg realtime configuration.
- The API returns a master playlist with supported codec/resolution variants
  and creates a video-stream session in PostgreSQL.
- Session ownership is acquired by one microservices worker. API and worker
  coordinate session, heartbeat, segment request, and segment-ready events over
  the server Socket.IO channel.
- The worker launches FFmpeg only when a segment/variant is needed. It writes
  fragmented MP4 init and media segments under a temporary HLS session folder.
- A filesystem watcher detects completed segment renames and wakes the pending
  API request. Backpressure pauses or resumes FFmpeg based on how far generated
  segments are ahead of the client.
- Variant switches and seeks can restart transcoding at a calculated segment.
  The current implementation accepts position/init-segment hints and prewarms a
  target variant to reduce startup after a seek or quality switch.
- Session end and scheduled cleanup terminate FFmpeg processes, remove rows,
  and delete temporary HLS files.

The original audit's image viewer analysis remains correct for photos, but it
does not describe this video session/transcoding path.

### 12. Plugins and User Workflows

Immich includes a WebAssembly plugin system and user-configurable workflow
engine in the inspected revisions.

Plugin loading:

- Core and optionally external plugin folders contain a manifest and WASM
  module. The microservices worker imports them under a PostgreSQL advisory
  lock.
- Plugin manifests, WASM bytes, exported methods, accepted workflow types,
  templates, and host-function permissions are persisted in PostgreSQL.
- Extism loads ordinary modules in process and modules requiring host functions
  in worker isolation. Plugins without declared host-function access receive
  rejecting stubs.

Workflow execution:

- Workflows and ordered workflow steps are stored in `workflow` and
  `workflow_step` rows linked to plugin methods.
- `AssetCreate` and `AssetMetadataExtracted` events select matching user
  workflows and enqueue `WorkflowAssetTrigger` on the workflow queue.
- A workflow reads a typed asset payload, executes each compatible plugin step,
  applies returned changes through normal services, refreshes the payload, and
  continues unless a step requests termination.
- Host functions use a per-process internal JWT-derived auth context and are
  limited to explicitly exposed operations such as album search/create and
  adding assets to albums.
- Metadata events sourced from `sidecar-write` do not retrigger metadata
  workflows, preventing the direct write/extract loop. General workflow loop
  detection is still marked as TODO in source.

This branch runs alongside storage-template handling after metadata extraction;
it is not represented by a purely linear metadata-to-thumbnail diagram.

### 13. Operational Lifecycle

Storage and change ownership:

- Uploaded originals are owned by Immich storage. External-library originals
  remain in place; storage templates explicitly do not move external assets.
- Upload errors and failed inserts queue file deletion. Successful asset/file
  deletion also uses background cleanup so request handlers do not perform all
  filesystem work synchronously.
- `asset_file` is the database inventory for sidecars, thumbnail/preview/
  fullsize images, and encoded video. Regeneration upserts the new rows and
  queues superseded files for deletion.
- Uploaded assets use content SHA1 and a per-owner uniqueness constraint.
  External assets currently use the deprecated `sha1-path` identity plus
  library/path/stat reconciliation.

Scheduled and singleton work:

- The API process holding the nightly advisory lock schedules database cleanup,
  memory generation, quota synchronization, missing-thumbnail checks, and face
  clustering according to config.
- External-library scheduled scan is enabled by default; filesystem watching is
  optional and guarded so only one microservices process watches a library.
- Database backups, version checks, geodata initialization, plugin import, and
  storage migrations use dedicated locks or deduplicated jobs.

Offline, trash, and repair states:

- External sync marks inaccessible files offline and restores them online when
  they reappear. File mtime changes re-enter sidecar/metadata processing.
- Trash is soft-delete state with delayed background deletion; asset status and
  visibility are distinct from filesystem offline state.
- Maintenance mode starts a restricted maintenance worker instead of the
  normal API/microservices pair.
- In the 2026-06-19 re-verification revision, the new integrity pipeline can
  scan for missing tracked files, untracked storage files, and checksum
  failures. Findings are stored in `integrity_report`; refresh and delete
  operations run through the `integrityCheck` queue and admin maintenance API.
  This integrity-report implementation was not present in the original
  2026-06-09 snapshot.

Observability and invalidation:

- OpenTelemetry instruments HTTP, NestJS, PostgreSQL, Redis, I/O, repository,
  and job work according to enabled metric groups; Prometheus export is
  available from configured API and microservices ports.
- Socket.IO update events invalidate or refresh web caches. Media URLs include
  thumbhash/cache keys, while database rows and timestamps are the durable
  source for server-side readiness and sync state.

### 14. Technology Stack

| Layer               | Technologies in the inspected repository                                                                       | Role                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Monorepo/tooling    | pnpm workspaces, TypeScript, Vitest, ESLint, Prettier                                                          | Shared server, web, SDK, plugin SDK, UI, and test packages.                             |
| Server/API          | Node.js, NestJS 11, Express 5, Zod/nestjs-zod, OpenAPI/Swagger                                                 | REST API, auth/permissions, DTO validation, websocket setup, and static web serving.    |
| Data access         | PostgreSQL 14, Kysely, `@immich/sql-tools`, migrations and triggers                                            | Asset state, EXIF, derivatives, audit/sync data, workflow state, and relational search. |
| Database extensions | VectorChord with pgvector compatibility, `pg_trgm`, `unaccent`, cube/earthdistance                             | CLIP/face vector indexes, fuzzy text search, and geographic queries.                    |
| Queue/realtime      | BullMQ, Valkey/Redis protocol, Socket.IO, Redis adapter                                                        | Durable jobs, configurable concurrency, worker coordination, and client events.         |
| Image/media         | ExifTool, Sharp/libvips, FFmpeg/ffprobe, ThumbHash                                                             | Metadata, RAW extraction, resize/convert/edit, video probe/transcode, and placeholders. |
| Web                 | Svelte 5, SvelteKit 2, Vite 8, Tailwind CSS 4, Immich UI                                                       | Static SPA, timeline virtualization, adaptive viewer, maps, search, and admin UI.       |
| Machine learning    | Python 3.11+, FastAPI, Gunicorn/Uvicorn, ONNX Runtime, OpenCLIP/MCLIP, InsightFace, RapidOCR, Hugging Face Hub | CLIP image/text embeddings, face detection/recognition, and OCR.                        |
| ML acceleration     | ONNX Runtime CPU, CUDA, OpenVINO, ROCm/MIGraphX, ARM NN, RKNN variants                                         | Optional hardware-specific inference images.                                            |
| Mobile              | Flutter/Dart, Riverpod, Drift/SQLite, generated OpenAPI client, native platform bridges                        | Device backup, local database, incremental sync, background work, and mobile viewer.    |
| Plugins             | Extism and `@immich/plugin-sdk`                                                                                | WASM plugin loading and workflow step execution.                                        |
| Observability       | OpenTelemetry and Prometheus exporter                                                                          | API, database, Redis, I/O, repository, and job metrics.                                 |
| Deployment          | Docker Compose; server, ML, Valkey, custom PostgreSQL/VectorChord images                                       | Default self-hosted topology with persistent media, database, and model cache volumes.  |

The production web build uses SvelteKit's static adapter. The NestJS server
serves the generated files and injects Open Graph metadata for shared-link
routes; it is not a general server-rendered Svelte application.

### 15. Cold Cache vs Warm Cache

Cold import or library scan:

- External library scan discovers paths with `fast-glob` and creates rows from stat data.
- Original file metadata and thumbnails are not available until background jobs finish.
- `/timeline/buckets` can count an asset after the `asset` row exists, but `/timeline/bucket` uses an inner join to `asset_exif`. An external asset does not enter the compact grid payload until metadata extraction has created its EXIF row.
- After the EXIF row exists, the grid can expose the asset before derivatives are ready; thumbnails/previews may still be missing or represented by placeholders.
- Upload-ready websocket notifications are emitted after thumbnail generation queues its follow-up jobs. They do not wait for smart search, faces, OCR, duplicate detection, or video encoding to finish.

Warm library:

- Asset rows, EXIF rows, derivative file rows, thumbhashes, and search rows already exist.
- Timeline APIs read PostgreSQL bucket/count data.
- Grid image requests hit stored derivative files and browser/service-worker cache where applicable.
- Viewer starts from available thumbnail/preview and can promote to original without metadata extraction.

Cache invalidation:

- Media URLs include a cache key from `asset.thumbhash`, so regenerated media can bust browser-side image cache.
- Derivative files are represented in `asset_file`; regeneration updates rows and queues old files for deletion.
- The web `AssetCacheManager` invalidates asset/OCR/face cache entries on asset edit/update events.
- External library sync marks offline/deleted state from stat and path checks; watcher events can queue sync or removal.

## Pipeline Diagrams

### Import / Library Scan Pipeline

```txt
User upload
  -> AssetMediaController.uploadAsset
     [sync request, original file write, checksum while streaming]
  -> asset row insert
     [DB write, UI waits for upload request]
  -> AssetExtractMetadata job
     [async background, original/sidecar read, DB write]
  -> StorageTemplateMigrationSingle
     [async background, storage/DB update]
  -> AssetGenerateThumbnails
     [async background, original read, thumbnail/preview/fullsize write, asset_file DB write]
  -> queue SmartSearch / OCR / faces and video encoding when applicable
     [conditional fan-out for source=upload or notify=true]
  -> websocket upload-ready/update events
     [sent after queueing follow-ups; UI does not wait for them to finish]
  -> SmartSearch success may queue duplicate detection
     [source=upload only]

External library scan
  -> LibraryController.scanLibrary
     [sync API queues work; UI does not wait for full scan]
  -> StorageRepository.walk import paths
     [async background, filesystem directory read, no full image decode]
  -> filterNewExternalAssetPaths
     [DB read]
  -> handleSyncFiles/processEntity
     [filesystem stat, DB asset insert, path-derived checksum]
  -> SidecarCheck
     [async background, filesystem/DB sidecar work; source is currently labeled upload]
  -> AssetExtractMetadata
     [async background, original/sidecar read, DB write]
  -> StorageTemplateMigrationSingle
     [storage move is a no-op for external assets; a disabled template returns skipped; either result advances the chain]
  -> AssetGenerateThumbnails, then conditional search/ML follow-ups
     [async background, derivative/search/index writes]
  -> asset becomes warm for timeline/search/viewer
     [UI reads DB and derivative files]
```

### Grid / Timeline Pipeline

```txt
Web photos route
  -> TimelineManager.updateOptions
     [UI state]
  -> GET /timeline/buckets
     [hot path DB read, returns bucket counts, no original file read]
  -> virtual month layout and scrubber
     [UI computes geometry, no media read]
  -> month enters/near viewport
     [UI lazy loading]
  -> GET /timeline/bucket?timeBucket=...
     [DB read, compact asset arrays, no EXIF parse]
  -> Thumbnail.svelte
     [UI renders visible assets only]
  -> GET /assets/:id/thumbnail?size=thumbnail
     [thumbnail/preview file read, not original unless derivative policy redirects]
  -> browser displays derivative/thumbhash
     [UI waits only for image load of visible thumbnails]
```

### Viewer / Lightbox Pipeline

```txt
User clicks asset
  -> navigate to asset route
     [UI route change]
  -> +layout.ts getAssetInfoFromParam
     [API/DB read, UI waits for asset DTO]
  -> assetViewerManager.setAsset
     [UI state]
  -> TimelineAssetViewer loads next/previous getAssetInfo
     [parallel API/DB reads, cacheable]
  -> AdaptiveImage starts
     [UI hot path]
  -> thumbnail URL requested
     [derivative read]
  -> preview URL requested after thumbnail
     [derivative read; normal main display]
  -> original/fullsize requested on zoom, preference, animated image, preview failure, or download
     [original file or fullsize derivative read]
  -> DetailPanel renders asset.exifInfo
     [DB/API metadata already in DTO; no browser file parse]
  -> PreloadManager loads next/previous thumbnail then preview
     [background UI prefetch, no original unless preview fails]
```

### Search Pipeline

```txt
User metadata/filter search
  -> SearchController.searchMetadata
     [sync API request]
  -> SearchService permission and query setup
     [DB/user scope]
  -> SearchRepository.searchAssetBuilder
     [PostgreSQL query, indexes/trigram as applicable]
  -> Asset DTO/results
     [DB read, no original file read]
  -> thumbnails requested for visible results
     [derivative file read]
  -> viewer opens selected asset
     [same viewer pipeline]

User smart search
  -> text query
     [sync API request]
  -> MachineLearningRepository.encodeText
     [ML service call, cached in service LRU]
  -> SearchRepository.searchSmart
     [vector DB query over smart_search embeddings]
  -> Asset results and thumbnails
     [DB read + derivative file read]

Background smart index
  -> AssetGenerateThumbnails done
  -> SmartSearch job
  -> preview file sent to ML encodeImage
  -> smart_search embedding upsert
     [async background, preview read, DB write]
```

## Immich vs gallery-repo

| Area                             | Immich                                                                                    | gallery-repo                                                                          | Which is better                                                                    | Why                                                                                           |
| -------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Initial folder open latency      | External scan is async but requires DB/library setup; timeline opens from pre-indexed DB. | `/api/scan` lists the folder immediately and avoids PIL/metadata parsing.             | gallery-repo for ad hoc local folders; Immich for already-indexed libraries.       | gallery-repo's hot path is simpler and direct. Immich wins only after import/indexing exists. |
| Cold cache behavior              | Cold libraries need background metadata/thumbnails before the UI is fully warm.           | Folder opens immediately; thumbnails/metadata are lazy/on demand.                     | gallery-repo for dozens of cold local files.                                       | It avoids blocking on ingestion jobs.                                                         |
| Warm cache behavior              | DB rows, indexes, derivatives, thumbhash, and search rows make timeline/viewer very fast. | Cached dimensions/thumbnails/metadata improve repeat opens but still scan the folder. | Immich for very large warm libraries; gallery-repo for simple folders.             | Immich's DB-first timeline avoids scanning large folders on every open.                       |
| Metadata extraction strategy     | Background job reads original/sidecar, writes DB.                                         | On-demand `/api/metadata`; scan does not parse.                                       | Depends.                                                                           | Immich is better for prepared libraries; gallery-repo is better for first open latency.       |
| Thumbnail strategy               | Eager background derivative generation with DB `asset_file` rows.                         | Lazy thumbnail generation on `/api/thumbnail`, persistent cache.                      | Immich for warm large libraries; gallery-repo for cold small folders.              | Eager derivatives cost upfront work but reduce later UI latency.                              |
| Original image/lightbox strategy | Thumbnail -> preview -> original/fullsize on zoom/preference/fallback.                    | PhotoSwipe main `src` is original `/api/image`; thumbnail is placeholder/msrc.        | gallery-repo for exact original display; Immich for bandwidth-controlled browsing. | Different UX goals: original fidelity vs progressive derivative-first loading.                |
| Viewer metadata source           | Full asset DTO from DB/API.                                                               | TanStack metadata query; on-demand extraction may run when needed.                    | Immich once indexed; gallery-repo before indexing exists.                          | DB-first viewer metadata avoids UI-triggered file parsing.                                    |
| Search architecture              | PostgreSQL filters, trigram/unaccent, OCR, CLIP vector search.                            | SQLite FTS/trigram tables over cached AI metadata/file index.                         | Immich for large photo search; gallery-repo for local AI metadata simplicity.      | Immich has a deeper search stack but much higher operational cost.                            |
| Database/indexing                | PostgreSQL tables for assets, EXIF, files, jobs, OCR, vectors.                            | SQLite metadata/file index and thumbnail/dimension caches.                            | Immich for 100k+ libraries; gallery-repo for local deployment.                     | PostgreSQL scales better but is heavier.                                                      |
| Background workers/jobs          | BullMQ queues and workers across media, metadata, ML, library, OCR, faces.                | Lightweight background tasks around scan/indexing; no external queue.                 | Immich for robust processing; gallery-repo for maintainability.                    | Queue stack adds reliability and complexity.                                                  |
| Cache invalidation               | Thumbhash URL key, derivative rows, asset cache invalidation, watcher/offline state.      | Path/mtime/size cache keys for dimensions/thumbnails/metadata.                        | Tie by scope.                                                                      | Immich handles managed libraries; gallery-repo handles filesystem freshness simply.           |
| External library/folder watching | External libraries, scheduled scans, optional chokidar watcher.                           | Ad hoc folder scan; no persistent watcher model.                                      | Immich for managed libraries; gallery-repo for browsing arbitrary folders.         | Persistent watching is useful only with a persistent library model.                           |
| Mobile/web UX                    | Full photo-server UI with routes, timeline, thumbhash, preloading, mobile considerations. | Local web gallery with PhotoSwipe and perf tests.                                     | Immich for full photo app; gallery-repo for focused local AI gallery.              | Immich solves more product surface.                                                           |
| Scalability for 50 images        | Warm: excellent. Cold: import jobs add setup.                                             | Excellent cold and warm.                                                              | gallery-repo.                                                                      | Avoids ingest pipeline overhead.                                                              |
| Scalability for 5000+ images     | Strong if indexed; cold scan takes background processing time.                            | Folder scan still walks/sorts thousands; cached metadata helps.                       | Immich warm; gallery-repo may need DB-backed listing later.                        | DB-first buckets beat repeated filesystem scans at scale.                                     |
| Scalability for 100k+ images     | Designed for this with DB, queues, derivatives, timeline buckets.                         | Current architecture is not optimized for 100k single-folder/library browsing.        | Immich.                                                                            | gallery-repo lacks persistent asset model and large-library timeline index.                   |
| Complexity/maintenance burden    | High: PostgreSQL, Redis/BullMQ, ML optional services, many domains.                       | Low/medium: Python backend, SQLite, Vue, TanStack, PhotoSwipe.                        | gallery-repo.                                                                      | Fits current project size and deployment goal.                                                |
| Deployment requirements          | Server stack, database, queue, storage, optional ML, accounts.                            | Local backend/frontend with SQLite/disk caches.                                       | gallery-repo.                                                                      | Immich's requirements are not justified for local folder browsing.                            |
| Testability/perf observability   | Large test surface; queue/job observability endpoints.                                    | Focused Playwright perf budgets for album and lightbox.                               | gallery-repo for current guarantees; Immich for operations.                        | gallery-repo has direct tests for the critical paths we care about.                           |

## Ideas to Borrow From Immich

### Idea: Bounded Background Metadata/Thumbnail Queue

What Immich does: uses named background queues for metadata extraction, thumbnail generation, library scanning, search indexing, OCR, and related work.

Evidence/files: `server/src/services/job.service.ts`, `server/src/repositories/job.repository.ts`, `server/src/services/queue.service.ts`, `server/src/enum.ts`.

Why it helps gallery-repo: moves expensive metadata/thumbnail work out of request paths while preserving fast folder open.

How to map to gallery-repo: implement a small in-process queue backed by SQLite job rows, not BullMQ/Redis. Start with metadata indexing and thumbnail warming for files seen by `/api/scan`.

Complexity: Medium.

Risk: Queue bugs could compete with interactive thumbnail/lightbox requests.

Priority: P1.

Acceptance criteria: `/api/scan` latency budget unchanged; queue status endpoint shows pending/running/done/error; duplicate jobs coalesce by path+mtime+size.

Perf budget: scan p95 must not regress; background CPU should be bounded to one worker by default.

### Idea: DB-First Viewer Metadata Source

What Immich does: full viewer metadata comes from `getAssetInfo`/`AssetResponseDto`, backed by asset and EXIF rows.

Evidence/files: `web/src/routes/(user)/+layout.ts`, `web/src/lib/components/asset-viewer/DetailPanel.svelte`, `server/src/dtos/asset-response.dto.ts`, `server/src/schema/tables/asset-exif.table.ts`.

Why it helps gallery-repo: the lightbox metadata panel can become instant on warm cache and avoid per-open parser work.

How to map to gallery-repo: keep `/api/metadata` but make the frontend prefer a cache/status response when available; queue extraction in the background after scan.

Complexity: Medium.

Risk: stale metadata if cache invalidation is wrong.

Priority: P1.

Acceptance criteria: opening lightbox with cached metadata performs no image open or sidecar parse; stale rows are invalidated by mtime/size.

Perf budget: metadata panel warm p95 under 100 ms backend time for cached files.

### Idea: Derivative/File Status Rows

What Immich does: stores derivative and sidecar file records in `asset_file`.

Evidence/files: `server/src/schema/tables/asset-file.table.ts`, `server/src/services/media.service.ts`, `server/src/cores/storage.core.ts`.

Why it helps gallery-repo: makes thumbnail/preview cache state inspectable and queryable instead of only implicit in disk cache.

How to map to gallery-repo: add optional SQLite derivative table for thumbnail sizes and preview readiness, keyed by path+mtime+size.

Complexity: Medium.

Risk: duplicate truth between diskcache and SQLite unless one owner is clearly defined.

Priority: P1/P2.

Acceptance criteria: API can answer whether a thumbnail/preview exists without opening image files.

Perf budget: derivative lookup for a scan batch should be one SQLite query.

### Idea: Preview/Original Source Policy

What Immich does: normal viewer path uses thumbnail then preview; original/fullsize loads on zoom, preference, animated images, or fallback.

Evidence/files: `web/src/lib/utils.ts`, `web/src/lib/components/AdaptiveImage.svelte`, `web/src/lib/utils/adaptive-image-loader.svelte.ts`.

Why it helps gallery-repo: a preview layer could improve perceived lightbox time for very large files while preserving current original-display guarantee.

How to map to gallery-repo: keep PhotoSwipe main `src=/api/image` for current tests, but optionally precompute a high-quality `msrc`/placeholder preview and load original as the authoritative slide.

Complexity: Medium.

Risk: regressing the explicit requirement that PhotoSwipe's main source is the original.

Priority: P2.

Acceptance criteria: existing lightbox perf test still proves `srcIsFullImage`; preview appears only as placeholder/progressive layer.

Perf budget: lightbox visible <= current budget; full original load <= current budget.

### Idea: Compact Timeline/List DTOs

What Immich does: timeline bucket API returns compact arrays for list/grid rendering, while asset detail API returns full metadata.

Evidence/files: `server/src/controllers/timeline.controller.ts`, `server/src/repositories/asset.repository.ts`, `web/src/lib/managers/timeline-manager/internal/load-support.svelte.ts`.

Why it helps gallery-repo: future DB-backed folder listing can avoid shipping heavy metadata for every grid item.

How to map to gallery-repo: keep `/api/scan` response minimal: path/name/type/mtime/size/cached dimensions/cache status. Keep full metadata on `/api/metadata`.

Complexity: Low.

Risk: adding too many fields to scan again.

Priority: P0/P1.

Acceptance criteria: scan response remains minimal and documented.

Perf budget: album-open test budgets unchanged.

### Idea: Next/Previous Viewer Preload

What Immich does: preloads next/previous thumbnail and preview via `PreloadManager`.

Evidence/files: `web/src/lib/components/asset-viewer/PreloadManager.svelte.ts`, `web/src/lib/components/timeline/TimelineAssetViewer.svelte`.

Why it helps gallery-repo: reduces perceived transition cost between adjacent lightbox images.

How to map to gallery-repo: extend current neighbor thumbnail preload to optionally prefetch metadata and maybe a medium thumbnail/preview, not full originals by default.

Complexity: Low/Medium.

Risk: wasteful network/disk reads during fast navigation.

Priority: P1.

Acceptance criteria: next/prev transition p95 improves or stays within budget; no extra full-original requests before navigation.

Perf budget: no regression in initial lightbox open; cap concurrent preloads.

### Idea: Job Status and Progress API

What Immich does: exposes queue/job status for admin and processing visibility.

Evidence/files: `server/src/controllers/queue.controller.ts`, `server/src/controllers/job.controller.ts`, `server/src/services/queue.service.ts`.

Why it helps gallery-repo: users can see indexing progress for large folders.

How to map to gallery-repo: add a small `/api/index/status` endpoint backed by SQLite counters, without a full admin queue UI initially.

Complexity: Low/Medium.

Risk: exposing misleading progress if indexing work is opportunistic.

Priority: P1.

Acceptance criteria: status reports queued/running/done/error and last error per folder.

Perf budget: status endpoint under 50 ms on warm SQLite for normal folders.

### Idea: Asset Change Detection

What Immich does: upload assets use file checksums; external assets use path identity plus filesystem stat; sync marks missing paths offline.

Evidence/files: `server/src/services/library.service.ts`, `server/src/repositories/library.repository.ts`, `server/src/middleware/file-upload.interceptor.ts`.

Why it helps gallery-repo: explicit stale/missing detection would make search results and metadata cache cleaner.

How to map to gallery-repo: continue path+mtime+size validation; add stale cleanup and optional "missing from folder" status for indexed entries.

Complexity: Low.

Risk: deleting useful cached metadata too aggressively.

Priority: P1.

Acceptance criteria: search removes or marks stale paths without blocking scan.

Perf budget: cleanup is batched and never runs in `/api/scan` hot path beyond cheap validation.

## Things Not to Copy From Immich

| Do not copy                                                  | Why not                                                                                                       | Risk if copied blindly                                                      |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| PostgreSQL requirement as default                            | gallery-repo is currently simple/local and SQLite fits the deployment model.                                  | Higher install burden and more failure modes before clear need.             |
| Redis/BullMQ/microservice queue stack                        | Immich needs robust distributed workers; gallery-repo can start with a small local queue.                     | Queue infrastructure dominates the project.                                 |
| ML smart search as a default feature                         | CLIP/OCR/face services are valuable but heavy.                                                                | Turns a local gallery into an ops-heavy ML platform.                        |
| Multi-user/album/permission model                            | gallery-repo is not a full backup/photo server.                                                               | DTO and route complexity spreads everywhere.                                |
| Original-photo backup semantics                              | Immich owns uploaded storage and backup behavior; gallery-repo browses local folders.                         | Accidental file ownership assumptions and destructive workflows.            |
| Eager derivative generation for every small cold folder      | Good for managed libraries, bad for instant ad hoc folder open.                                               | Opening a folder starts too much CPU/disk work.                             |
| Path-derived checksum semantics as identity                  | It works for Immich external assets but is not content identity.                                              | Moved/renamed files look unrelated; duplicates are not detected by content. |
| Full storage-template migration model                        | Useful for managed photo libraries.                                                                           | Unnecessary file movement risk for local browsing.                          |
| Large generated DTO surface                                  | Immich serves many clients and domains.                                                                       | gallery-repo loses focused API contracts.                                   |
| Browser viewer policy that replaces main source with preview | Immich optimizes for photo-server browsing; gallery-repo currently requires PhotoSwipe main `src=/api/image`. | Regresses current lightbox correctness/perf tests.                          |

## Recommended Roadmap for gallery-repo

### P0 - Keep Current Guarantees

| Item                                                        | Files likely affected                                                             | Expected benefit                         | Risk                                                                        | Test plan                                                       | Perf budget                                        |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------- |
| Keep `/api/scan` free of metadata parsing and PIL probing.  | `backend/scan.py`, docs/tests only                                                | Preserves fast folder open.              | Future features may accidentally add file opens.                            | Existing album-open perf test plus route-level unit/inspection. | Scan p95 must stay within current test budget.     |
| Keep scan dimensions cache-only.                            | `backend/scan.py`, `backend/metadata_store.py`                                    | Avoids opening cold images for layout.   | Some cold images lack dimensions until thumbnail/metadata path warms cache. | Verify scan only returns matching cached dimensions.            | Batch SQLite dimension lookup only.                |
| Keep PhotoSwipe main source as `/api/image`.                | `frontend/src/utils/lightbox.ts`, `frontend/tests/e2e/perf/lightbox.perf.spec.ts` | Preserves original-display guarantee.    | Preview experiments could replace original by mistake.                      | Lightbox perf test already asserts `/api/image`.                | No regression to lightbox-open/full-image budgets. |
| Keep TanStack Query as owner of scan/metadata server state. | frontend query/services/components                                                | Avoids duplicate client cache ownership. | Store/query drift.                                                          | Existing frontend tests plus manual query invalidation checks.  | No extra blocking request on grid open.            |

### P1 - High Value Borrow

| Item                                                               | Files likely affected                                                              | Expected benefit                                   | Risk                                     | Test plan                                                                         | Perf budget                                              |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Add a bounded local metadata indexing queue.                       | `backend/metadata_store.py`, `backend/metadata_parse.py`, new backend queue module | Warm viewer/search metadata without blocking scan. | CPU contention with thumbnails/lightbox. | Unit tests for coalescing, stale invalidation, queue ordering.                    | One worker by default; scan p95 unchanged.               |
| Add batched SQLite writer for index results.                       | `backend/metadata_store.py`                                                        | Reduces write overhead for large folders.          | Transaction locking if too large.        | Batch insert/update tests and large-folder smoke test.                            | Writes in bounded batches, no long lock on request path. |
| Add index status/progress endpoint.                                | backend API modules, frontend optional status UI                                   | Makes background work understandable.              | Status can become inaccurate.            | API tests for queued/running/done/error counts.                                   | Endpoint p95 under 50 ms warm.                           |
| Prefetch next/previous metadata and medium thumbnails in lightbox. | `frontend/src/stores/lightbox.ts`, `frontend/src/composables/usePhotoSwipe.ts`     | Faster navigation after first slide.               | Wasteful preloads.                       | Extend lightbox perf test for transitions and assert no full originals preloaded. | Transition budget improves or remains <= current.        |
| DB-backed folder listing experiment for very large folders.        | `backend/metadata_store.py`, `backend/scan.py`, maybe new endpoint                 | Avoid repeated full filesystem/sort work at scale. | Stale listings if invalidation is weak.  | Separate opt-in test fixture; compare cold/warm behavior.                         | Do not affect default `/api/scan` hot path until proven. |

### P2 - Later

| Item                                                | Files likely affected                                                                | Expected benefit                            | Risk                                    | Test plan                                        | Perf budget                                      |
| --------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------- | --------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
| Full-text search facets beyond current AI metadata. | `backend/search.py`, `backend/metadata_store.py`, frontend search UI                 | Better discovery in large indexed folders.  | Query complexity.                       | SQLite query tests with representative metadata. | Search p95 target defined before implementation. |
| Optional external folder watcher.                   | new backend watcher module, status API                                               | Warmer cache while browsing stable folders. | Platform-specific watcher behavior.     | Integration tests behind opt-in flag.            | Watcher must be disabled by default.             |
| Optional semantic search.                           | new optional service or local embedding path                                         | Powerful discovery for large libraries.     | Dependencies and hardware expectations. | Feature-flagged tests/mocks.                     | No dependency or startup cost when disabled.     |
| Preview derivative table and warmer.                | `backend/thumbnails.py`, `backend/metadata_store.py`, frontend lightbox placeholders | Better perceived load for huge originals.   | Duplicate cache ownership.              | Tests for path+mtime+size invalidation.          | No change to PhotoSwipe main original source.    |

### Avoid

| Item                                                           | Files likely affected                                    | Expected benefit                  | Risk                                         | Test plan                                           | Perf budget                              |
| -------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------- | -------------------------------------------- | --------------------------------------------------- | ---------------------------------------- |
| Requiring PostgreSQL/Redis for normal use.                     | Whole app                                                | None for current goals.           | Deployment complexity.                       | N/A                                                 | N/A                                      |
| Eagerly parsing all metadata during folder open.               | `backend/scan.py`                                        | Warm metadata eventually.         | Breaks album-open budget.                    | Perf test should fail if attempted.                 | Not allowed in scan hot path.            |
| Replacing original lightbox image with preview as main source. | `frontend/src/utils/lightbox.ts`, PhotoSwipe integration | Faster low-res display.           | Violates current original-display guarantee. | Existing test must continue to assert `/api/image`. | Not allowed unless product goal changes. |
| Copying Immich account/album/backup semantics.                 | Whole app                                                | Not aligned with current project. | Scope explosion.                             | N/A                                                 | N/A                                      |

## Final Recommendation

Keep gallery-repo's current hot-path contract: folder open should remain filesystem listing plus batch SQLite cache lookup, with no image decoding or metadata parsing. Borrow Immich's background processing and DB-first viewer ideas incrementally, using SQLite and local workers rather than PostgreSQL/Redis/BullMQ. Treat Immich's preview/original policy as inspiration for placeholders and preloads only; do not replace PhotoSwipe's original `/api/image` main source without changing the product requirement and tests.

## Uncertainties

- Immich behavior can vary by admin config, especially thumbnail/fullsize settings, queue concurrency, ML features, library watcher settings, and "always load original" user preferences.
- I inspected Immich source at one commit and did not run a live deployment to observe transient states during import.
- Generated SDK function names show frontend API intent, but endpoint path details were inferred from SDK imports plus controller/server code.
- Exact service-worker/browser cache behavior was not exhaustively audited; the code evidence here focuses on server endpoints, URL cache keys, and frontend cache managers.

## Updated for current architecture

Verified against the current repository on 2026-06-18:

- gallery-repo now follows a derivative-first viewer policy similar in shape to
  the audited Immich flow while retaining an explicit original-on-demand path.
  PhotoSwipe starts with `/api/preview`; `/api/image` is loaded for zoom,
  fullscreen, animated-image handling, preference, or fallback cases.
- `backend/thumbnails.py` generates and persistently caches both 512px thumbnail
  and 1440px preview derivatives with role-specific cache keys, mtime/size
  invalidation, ETags, format, edge, and quality in the key.
- The local background metadata pipeline is implemented in `backend/indexer.py`
  and `backend/metadata_store.py`: RAM path staging, durable SQLite jobs,
  duplicate coalescing, bounded worker batches, batched writes, and
  `/api/index/status`.
- `/api/metadata` is DB-first for matching path/mtime/size rows, then uses an
  in-memory LRU and coalesced cold parsing.
- Warm SQLite folder listing, optional filesystem watching, and optional
  scheduled refresh are implemented. The watcher and refresh remain disabled by
  default and do not require PostgreSQL, Redis, or BullMQ.
- Current module names are `backend/thumbnails.py` and `backend/refresh.py`; the
  requested `backend/derivatives.py` and `backend/refresh_service.py` files do
  not exist.

Historical roadmap and “keep original as PhotoSwipe main source” statements
above are superseded by the verified derivative-first implementation.
