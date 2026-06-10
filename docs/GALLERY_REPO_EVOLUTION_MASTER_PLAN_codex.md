# Gallery Repo Evolution Master Plan

Last reviewed: 2026-06-10 (updated to track actual implementation: Phase 2 split into 2A ✅ + 2B next, Phase 3 ✅ done)

## Executive Summary

Core strategy:
gallery-repo should NOT become Immich.
gallery-repo should NOT become DiffusionToolkit.
gallery-repo should preserve its fast local web hot path, then selectively add a small local background indexing layer inspired by DT/Immich.

| Question | Answer |
| --- | --- |
| Best current architecture to preserve | The direct `/api/scan` folder-open path, lazy `/api/thumbnail` image-open path, on-demand/coalesced `/api/metadata` path, derivative-first PhotoSwipe `/api/preview` main source + on-demand `/api/image` original, SQLite cache/index, and TanStack Query ownership of server state. |
| Best DT idea to borrow | A bounded local metadata indexing queue with coalesced jobs and batched SQLite writes. DT's best lesson is not its viewer path; it is its background scanner/writer discipline. |
| Best Immich idea to borrow | DB-first warm viewer metadata and derivative readiness/status rows, implemented with SQLite and local workers rather than PostgreSQL, Redis, and BullMQ. |
| Biggest current gallery-repo weakness | Metadata/search warmness depends mostly on user-triggered thumbnail and metadata opens. A folder can scan quickly but still be cold for prompt search and lightbox metadata. |
| Biggest danger if we copy DT blindly | DT-style full-file reads, hashing, pixel fallback scans, or synchronous viewer metadata reparsing would destroy the folder-open and lightbox responsiveness that gallery-repo already has. |
| Biggest danger if we copy Immich blindly | Immich's full server stack, multi-user storage model, preview-first behavior without original-on-demand guarantees, and DB-first-only timeline assumptions would add operational weight and fundamentally change the product. (gallery-repo adapted Immich's derivative-first concept in Phase 2A but kept original-on-zoom guarantee.) |
| Recommended direction for the implementation phases | Phase 0: lock current guarantees. Phase 1: add a unified parser core, local background metadata indexer, batched writer, and index status. **Phase 2A (✅ done): derivative-first lightbox** — `/api/preview` (1440px) as PhotoSwipe main src, original `/api/image` only on zoom/fullscreen/download/animated, shared derivative core (`generate_derivative`), cache key per derivative type, neighbor preload (thumbnail + preview only, never original). **Phase 2B (next): fielded metadata search + DB-first warm metadata reads** — first-class search fields for all lightbox-visible metadata, generic `param:`/`advanced:`/`raw:` fallback, backward-compatible unified plain text, and SQLite-first metadata reads for the lightbox panel. Phase 3: warm indexed folder listing + optional watcher. |

The correct direction is not "DT plus a web UI" and not "Immich lite." It is:

```text
gallery-repo with:
- fast scan
- derivative-first lightbox (preview 1440 main src, original on zoom/fullscreen)
- local background metadata indexer
- batched SQLite writes
- DB-first warm metadata
- simple optional fielded search
- observable perf gates
```

## Sources Read

This is a planning document only. It proposes no code changes, dependency
changes, or behavior changes by itself.

Primary inputs read:

- [DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md)
- [DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md](DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md)
- [DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md](DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md)
- [IMMICH_PIPELINE_AUDIT.md](IMMICH_PIPELINE_AUDIT.md)
- [MEDIA_PIPELINE_COMPARISON.md](MEDIA_PIPELINE_COMPARISON.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [PERFORMANCE_TESTING.md](PERFORMANCE_TESTING.md)
- [METADATA_PARSING.md](METADATA_PARSING.md)

Implementation files inspected:

- Backend: [scan.py](../backend/scan.py), [thumbnails.py](../backend/thumbnails.py), [images.py](../backend/images.py), [metadata_store.py](../backend/metadata_store.py), [metadata_parse.py](../backend/metadata_parse.py), [metadata_extract.py](../backend/metadata_extract.py), [search.py](../backend/search.py), [main.py](../backend/main.py), [app.py](../backend/app.py)
- Frontend: [GalleryGrid.vue](../frontend/src/components/GalleryGrid.vue), [PhotoCard.vue](../frontend/src/components/PhotoCard.vue), [Lightbox.vue](../frontend/src/components/Lightbox.vue), [PhotoSwipeViewer.vue](../frontend/src/components/PhotoSwipeViewer.vue), [usePhotoSwipe.ts](../frontend/src/composables/usePhotoSwipe.ts), [lightbox.ts](../frontend/src/stores/lightbox.ts), [lightbox.ts](../frontend/src/utils/lightbox.ts), [api.ts](../frontend/src/services/api.ts)
- Perf tests: [album-open.perf.spec.ts](../frontend/tests/perf/album-open.perf.spec.ts), [lightbox.perf.spec.ts](../frontend/tests/perf/lightbox.perf.spec.ts)

## Current System Facts

These facts are the constraints the roadmap must respect.

### Current Hot Paths

| Hot path | Current behavior | Why it matters |
| --- | --- | --- |
| Folder open | `GET /api/scan` resolves path, runs `scan_directory()` in a threadpool, lists entries with `os.scandir`, stats image files, batch-reads cached dimensions, sorts folders/images, slices the requested page, and returns JSON. | This is the core local web browsing experience. It must stay cheap and predictable. |
| First thumbnails | Browser `img` tags in `PhotoCard.vue` request `/api/thumbnail`; the backend opens the original only on cache miss, renders WebP, persists cache bytes/files, and upserts dimensions. | This is the designated image-open path for grid thumbnails. |
| Lightbox open | `lightboxStore.open()` sets UI state immediately; `Lightbox.vue` renders a PhotoSwipe wrapper; `buildPhotoSwipeItem()` uses `/api/preview` (1440px) as the main `src` and `/api/thumbnail` (512px) as `msrc`. Original `/api/image` loads only on zoom/fullscreen/download via `zoomTriggerOriginal()`. | Lightbox display must not wait for metadata extraction. |
| Lightbox dimensions | `usePhotoSwipe.ts` uses scan dimensions, remembered thumbnail natural dimensions, cached metadata dimensions, fetched metadata dimensions, then preview (1440px) natural dimensions as fallback. | PhotoSwipe needs dimensions up front, but the app repairs them asynchronously without blocking open. |
| Metadata panel | `usePhotoMetadataQuery()` fetches `/api/metadata` only while lightbox is open and path is present; backend parsing is LRU-cached and in-flight coalesced. | Metadata is valuable, but it is not allowed to gate the image. |
| Search | `GET /api/search` reads `file_index`, `file_index_fts`, `image_metadata`, `image_metadata_fts`, and `image_metadata_fts_trigram`; frontend search is debounced and Query-owned. | Current search is simple text search over indexed data, not a live filesystem parser. |

### Current Cache Boundaries

| Cache | Owner | Key/invalidation | Filled by | Read by |
| --- | --- | --- | --- | --- |
| Browser image cache | Browser | URL + server headers | `/api/image`, `/api/thumbnail` responses | Grid, PhotoSwipe, preloads |
| Thumbnail disk cache | `backend/thumbnails.py` | resolved path + `mtime_ns` + size + max size + quality | `/api/thumbnail` cache misses | `/api/thumbnail` |
| Metadata LRU cache | `backend/metadata_parse.py` | path + mtime + size | `/api/metadata` parse | `/api/metadata` and dimension resolver through TanStack Query |
| SQLite image metadata | `backend/metadata_store.py` | path unique row, validated by mtime + size for dimensions | `/api/metadata`, `/api/thumbnail`, `index_image()` | `/api/scan`, search, future index status |
| SQLite file index | `backend/metadata_store.py` | path primary key | `/api/scan` background tasks, `index_directory_tree()` | `/api/search` filename/album sections |
| TanStack Query scan cache | frontend query layer | `["scan", path, imageLimit]`, `["scan-infinite", path, imageLimit]` | `scanDirectory()` | `GalleryGrid.vue` |
| TanStack Query metadata cache | frontend query layer | `["metadata", path]` | `fetchMetadata()` | `Lightbox.vue`, `usePhotoSwipe.ts` |
| Pinia lightbox dimensions | `frontend/src/stores/lightbox.ts` | path | `PhotoCard` natural dimensions and PhotoSwipe resolver | `usePhotoSwipe.ts` and lightbox navigation |

### Current Metadata/Search Limitations

- Metadata parser coverage is useful but split across two stacks:
  - `metadata_parse.py` powers `/api/metadata` and has richer SwarmUI, ComfyUI, A1111, NovelAI, EasyDiffusion, LoRA, and exact `.txt` sidecar behavior.
  - `metadata_extract.py` powers `metadata_store.index_image()` and is simpler, so indexed search can diverge from lightbox metadata.
- Prompt search has SQLite FTS5 and CJK trigram support, but no fielded query syntax such as `seed:`, `model:`, `sampler:`, `steps:`, `cfg:`, `negative:`, or `size:`.
- Full prompt/search cache warms only when metadata is parsed or explicitly indexed. Current `/api/scan` schedules file indexing and directory tree indexing with `include_metadata=False`.
- `file_index` helps album/photo filename search, but warm folder opening still uses filesystem enumeration and sorting rather than DB-first page reads.
- There is no formal derivative readiness table, so thumbnail/preview availability is implicit in disk cache files.
- There is no user-visible background index status.

### Current Lightbox Guarantees (Phase 2A)

- The PhotoSwipe main image `src` is `/api/preview` (1440px derivative).
- `/api/thumbnail` (512px) is `msrc`, placeholder, grid thumbnail, hover preview trigger for animated files.
- `/api/image` (original) loads only on zoom, fullscreen, download, or animated files via `zoomTriggerOriginal()`.
- Lightbox opens before metadata resolves.
- Metadata follows `lightbox.itemPath` through TanStack Query.
- The current perf test asserts `usedPreviewEndpoint === true` and `srcIsPreview === true`; zoom triggers `/api/image`.
- Neighbor preloading: only getThumbnailUrl() + getPreviewUrl(), never getImageUrl().

### Current Perf Tests And Budgets

| Test | What it protects | Current default budgets |
| --- | --- | --- |
| `npm run perf:album` | Album click to `/api/scan`, first thumbnail start, thumbnail p95, duplicate first-page scan count. | scan <= 500 ms, first thumbnail start <= 1000 ms, thumbnail p95 <= 1200 ms. |
| `npm run perf:lightbox` first image | Lightbox visible time, preview image loaded time, use of `/api/preview` not `/api/image` (unless zoom), display size sanity. | visible <= 1500 ms, preview loaded <= 4000 ms. |
| `npm run perf:lightbox` transition | Next-image load after ArrowRight and aspect-ratio correctness. | transition <= 3000 ms, ratio diff < 0.2. |

Future budgets in this plan add:

- 50-image album scan p95 <= current budget or no more than 10% regression.
- 5000-image warm first page target: 300-500 ms after indexed listing exists.
- `/api/index/status` p95 <= 50 ms warm.
- Background indexer must yield to request hot paths.

### Current SQLite Schema And Data Ownership

SQLite remains the local cache/index authority. Current tables are:

- `image_metadata`: dimensions, format, mode, alpha, prompt, negative prompt, model, sampler, seed, steps, cfg scale, raw metadata text, JSON metadata, timestamps.
- `image_metadata_fts`: unicode FTS over name/prompt/negative/model/sampler/raw text.
- `image_metadata_fts_trigram`: trigram FTS for substring/CJK-style matching.
- `file_index`: path, name, parent path, type, mtime, size, dimensions, indexed timestamp.
- `file_index_fts`: FTS over file/folder names with path/type/parent metadata.

Important ownership rules:

- `image_metadata` is both a dimension cache and a prompt metadata/search cache.
- `file_index` is the recursive album/photo name index.
- `/api/scan` may read `image_metadata` dimensions but must not make cache misses expensive.
- `/api/metadata` owns rich parse results.
- `/api/thumbnail` owns thumbnail rendering and dimension upserts when the image is already open.

### Current TanStack Query vs Pinia Ownership

TanStack Query owns server/API state:

- scan first page and infinite pages
- folder children
- unified search results
- lightbox metadata
- cache staleness and background refetching

Pinia owns UI/navigation state:

- root/current path
- folder tree expansion
- navigation history
- search input/scope/sort
- lightbox open state/current index/gallery item list
- remembered image dimensions
- toasts

Future work must preserve this split. Do not copy server responses into Pinia just to make new features easier.

## Non-negotiable Rules

### Rule 1: `/api/scan` must never parse metadata or open images with PIL.

Why:

- `/api/scan` is the folder-open hot path.
- Current `scan_directory()` uses `os.scandir`, `entry.stat()`, cached dimension lookup, sorting, and pagination.
- Adding `Image.open()` or metadata parsing makes folder open scale with image decode cost instead of directory listing cost.

Advantage:

- Cold folders with dozens of files can show content quickly.
- The scan path remains easy to profile with `SCAN_PERF_LOGS`, Prometheus, and pyinstrument.

Disadvantage:

- Cold scans return null dimensions when cache is empty.
- Metadata/search can remain cold until thumbnail/metadata/indexer work catches up.

Regression risk:

- A well-intentioned "fix missing dimensions during scan" patch could accidentally decode every image.

What breaks if violated:

- Album-open latency becomes proportional to image count and image size.
- Large AI PNG/WebP folders become unusable on first open.
- The background indexer no longer has a clear purpose because expensive work moved into the request.

Which previous bug/regression it prevents:

- Regressions where folder open waits for image probing, metadata extraction, or PIL decode before returning rows.

Which perf test should guard it:

- `frontend/tests/perf/album-open.perf.spec.ts`.
- Add a backend guard test that monkeypatches `PIL.Image.open` and asserts `/api/scan` does not call it.

### Rule 2: `/api/scan` may only read cached dimensions/metadata if already available and validated by path + mtime + size.

Why:

- `get_cached_dimensions_for_files()` already validates cached rows against current file mtime and size.
- Cached dimensions are useful only if freshness is explicit.

Advantage:

- Warm scans improve PhotoSwipe aspect ratios without image opening.
- Edited/replaced files naturally invalidate stale dimensions.

Disadvantage:

- Files can show neutral 1200x1200 fallback until a thumbnail, metadata request, or indexer fills dimensions.

Regression risk:

- Reading unvalidated dimensions causes wrong aspect ratios after edits.
- Falling back to image opens causes Rule 1 failure.

What breaks if violated:

- PhotoSwipe can render stretched/squashed slides.
- Search/grid rows can advertise stale readiness.
- The app can silently trust wrong DB data.

Which previous bug/regression it prevents:

- Wrong dimensions after EXIF orientation fixes, file edits, or same-path replacements.

Which perf test should guard it:

- Album-open perf test for latency.
- Lightbox transition perf test for aspect-ratio sanity.
- Backend stale-cache invalidation tests for mtime/size mismatch.

### Rule 3: `/api/thumbnail` can open images because it is already the image-open path.

Why:

- Thumbnail generation cannot happen without reading the original.
- `backend/thumbnails.py` already validates limits, opens with Pillow, records dimensions, transposes EXIF orientation, renders WebP, persists the cache, and returns a cacheable response.

Advantage:

- The grid gets real visuals lazily and only for requested images.
- Dimensions can be captured while the image is already open.

Disadvantage:

- Cold thumbnail bursts can consume CPU/disk.
- Browser-visible lazy loads can create concurrent thumbnail requests.

Regression risk:

- If thumbnail generation becomes too eager or unbounded, it can compete with lightbox `/api/image` and `/api/metadata`.

What breaks if violated:

- If thumbnail is not allowed to open images, thumbnails cannot be generated.
- If thumbnail opens are moved into scan, scan becomes slow.

Which previous bug/regression it prevents:

- Confusion between "never open images in scan" and "never open images anywhere."

Which perf test should guard it:

- Album-open first-thumbnail-start and thumbnail p95 budgets.
- Future queue metrics for thumbnail render latency and concurrency.

### Rule 4: `/api/metadata` can parse original files on demand, but should be cache-backed and coalesced.

Why:

- Metadata parsing is a legitimate original-file read, but it must not duplicate work or block the image display.
- Current `metadata_parse.py` has an LRU cache keyed by path/mtime/size and `_metadata_inflight` coalescing with `Future`.

Advantage:

- Users can always request metadata even before background indexing is complete.
- Warm parse results are reused in-process and persisted to SQLite.

Disadvantage:

- Cold metadata open can still parse the original file.
- In-memory cache is process-local and lost on restart.

Regression risk:

- Removing coalescing can duplicate parse work under rapid lightbox navigation or multiple panels.
- Making `/api/metadata` synchronous on the UI path can stall interactions.

What breaks if violated:

- Metadata panel becomes slow and inconsistent.
- Multiple requests for the same file can parse repeatedly.

Which previous bug/regression it prevents:

- Duplicate in-flight metadata work and UI waits for metadata before opening the lightbox.

Which perf test should guard it:

- Backend metadata queue coalescing tests.
- Lightbox visible-time budget, because metadata must not gate overlay visibility.

### Rule 5: Background indexing must never block folder open.

Why:

- Current `/api/scan` schedules `index_file`, `index_files_from_scan`, and `index_directory_tree(..., False)` with FastAPI `BackgroundTasks`.
- A new metadata indexer should be a continuation of this non-blocking model.

Advantage:

- Users see the folder immediately while the cache warms.
- Large folder indexing becomes observable and resumable without becoming the scan response.

Disadvantage:

- Search/metadata status may lag behind visible files.
- The UI needs a calm status model for in-progress work.

Regression risk:

- A queue implementation can accidentally `await` job completion before returning scan.

What breaks if violated:

- Folder open becomes an import pipeline.
- Cold folders behave like a heavyweight desktop/library ingest.

Which previous bug/regression it prevents:

- Reintroducing eager metadata indexing on album click.

Which perf test should guard it:

- Album-open perf test.
- A backend test that `/api/scan` returns before index jobs complete.

### Rule 6 (Phase 2A): PhotoSwipe main `src` is `/api/preview` (1440px derivative). Original `/api/image` loads only on zoom, fullscreen, download, or animated files.

Why:

- `frontend/src/utils/buildPhotoSwipeItem.ts` builds `src = getPreviewUrl(item.path)`, `msrc = getThumbnailUrl(item.path)`.
- `frontend/composables/usePhotoSwipe.ts` implements `zoomTriggerOriginal()` that swaps to `/api/image` on zoom.
- `frontend/tests/perf/lightbox.perf.spec.ts` asserts the actual loaded image contains `/api/preview` for normal open.
- `frontend/tests/perf/lightbox-loading-policy.spec.ts` asserts zoom triggers `/api/image`.

Advantage:

- Lightbox shows preview (1440px) instantly for fast perceived load; original fidelity preserved on demand.
- The product guarantee is measurable in tests.

Disadvantage:

- Users must zoom/fullscreen to see the original.
- Preview generation adds CPU cost on first access.

Regression risk:

- A regression could load `/api/thumbnail` (512px) as the main src, showing a low-quality image.
- A regression could fail to load original on zoom.

What breaks if violated:

- Users see low-quality images as the main lightbox content.
- Users cannot zoom to original fidelity.
- Lightbox perf/policy tests fail.

Which previous bug/regression it prevents:

- PhotoSwipe showing a thumbnail-sized image or never loading the original on zoom.

Which perf test should guard it:

- `lightbox.perf.spec.ts` — asserts `/api/preview` is used, not `/api/image` unless zoom.
- `lightbox-loading-policy.spec.ts` — zoom triggers `/api/image`, neighbor preload skips original.

### Rule 7: Preview (1440px) is the authoritative lightbox main image. `/api/thumbnail` (512px) is placeholder/msrc only, never the main src.

Why:

- Phase 2A established preview (1440px) as the lightbox source. Thumbnail serves grid display and PhotoSwipe `msrc`.
- `/api/image` (original) loads only on zoom, fullscreen, download, or animated files.

Advantage:

- The app gains perceived responsiveness from previews while preserving original fidelity on demand.
- Three clear derivative tiers: thumbnail (512), preview (1440), original (full).

Disadvantage:

- Normal lightbox open shows a derivative (1440px), not the original.
- Some bandwidth savings from original-only display are intentionally not taken.

Regression risk:

- Thumbnail (512px) could accidentally become the PhotoSwipe `src`, degrading quality.
- Preview could be bypassed and original loaded unnecessarily, wasting bandwidth.

What breaks if violated:

- Lightbox shows a low-quality thumbnail as the main image.
- Original loads on every slide instead of only on zoom.

Which previous bug/regression it prevents:

- Thumbnail-sized lightbox image masquerading as the preview.
- Full original loading on every lightbox open.

Which perf test should guard it:

- `lightbox-loading-policy.spec.ts` — preview source assertions, no original on normal open.
- `lightbox.perf.spec.ts` — preview load time, zoom trigger.
- Future "does not preload full original for neighbors" test, to distinguish previews from originals.

### Rule 8: Album-open and lightbox perf tests are hard gates.

Why:

- These tests cover the core experience: open folder, see thumbnails, open original image, move next.
- They encode the current architecture's most important contracts.

Advantage:

- Performance regressions are caught before they become architectural drift.
- The team can borrow ideas without guessing about hot-path impact.

Disadvantage:

- Some useful features may require test updates and benchmark calibration.
- The tests need stable sample folders and predictable environment configuration.

Regression risk:

- Treating perf tests as optional lets background indexing, prefetching, or parser changes erode responsiveness.

What breaks if violated:

- The project loses the ability to tell whether it is still gallery-repo or becoming a slower ingest tool.

Which previous bug/regression it prevents:

- Duplicate scan requests, thumbnail-first lightbox source, and false confidence in unmeasured optimizations.

Which perf test should guard it:

- `album-open.perf.spec.ts`.
- `lightbox.perf.spec.ts`.

### Rule 9: SQLite remains the default database; PostgreSQL/Redis/BullMQ must not become default requirements.

Why:

- gallery-repo is local-first and currently uses SQLite, FTS5, WAL, and path/mtime/size validation effectively.
- Immich's PostgreSQL/Redis/BullMQ stack solves a different class of problem.

Advantage:

- Startup/deployment remain simple.
- Local users do not need external services.
- SQLite FTS/trigram support is enough for the near-term AI metadata search extensions.

Disadvantage:

- SQLite write concurrency and very large-library timelines need careful design.
- Some PostgreSQL capabilities such as trigram indexes, unaccent, vectors, and advanced filters are not directly available.

Regression risk:

- A queue/status feature can import server-platform complexity before proving need.

What breaks if violated:

- The app becomes harder to install and operate.
- Documentation, tests, and support load increase sharply.

Which previous bug/regression it prevents:

- Scope expansion from a local folder browser into a full photo-server deployment.

Which perf test should guard it:

- Not a single perf test; enforce through dependency review, startup tests, and docs.

### Rule 10: Search must remain simple for normal text, with fielded search added as an extension, not a replacement.

Why:

- Current unified search is predictable: plain text searches albums, photo names, and prompt metadata.
- DT-style fielded search is useful, but it should parse recognized tokens and leave the remaining text on the existing FTS path.

Advantage:

- Existing users keep normal search behavior.
- Advanced users gain precise filters such as `seed:123` or `model:"realistic*"`.

Disadvantage:

- Query parsing has edge cases around quotes, colons, malformed fields, CJK, and commas.
- The UI may need help text or error handling later.

Regression risk:

- Plain search could become less relevant or break because the parser consumes text incorrectly.

What breaks if violated:

- Normal filename/prompt searches become surprising.
- Search no-results and loading states can flicker while parser behavior changes.

Which previous bug/regression it prevents:

- Replacing simple search with a query language that only power users understand.

Which perf test should guard it:

- Backend fielded search parser tests.
- Frontend search no-results only after fetch settled test.
- Existing search behavior regression tests for plain text and CJK.

## Decision Matrix: Borrow / Adapt / Reject

Decision values:

- Adopt now: implement in the next implementation phase after Phase 0 locks.
- Adapt later: good idea, but only after prerequisite work or product validation.
- Research first: promising but uncertain; requires fixtures, benchmarks, or UX proof.
- Reject: do not copy for gallery-repo's current goals.

### DiffusionToolkit Ideas

| Idea | Source | Decision | Why | Advantages | Disadvantages | Risk | Complexity | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bounded background metadata indexing queue | DT | Adopt now | It directly fixes cold metadata/search caches without changing `/api/scan`. | Warms SQLite metadata/search; keeps folder open fast; enables progress UI. | Adds queue state, worker lifecycle, cancellation/staleness concerns. | Medium | Medium | P1 |
| Batched SQLite writer | DT | Adopt now | DT's batch writer maps well to SQLite and reduces lock churn under indexing. | Fewer commits; lower write overhead; cleaner metrics. | Batch sizing can create long transactions if too large. | Medium | Medium | P1 |
| Broad AI metadata parser coverage | DT | Adopt now | gallery-repo is AI-art oriented and parser coverage is a real capability gap. | Better metadata panels and search; supports more generators. | Parser changes are easy to regress without fixtures. | Medium | Medium | P1/P2 |
| Sidecar metadata support | DT | Adapt later | Exact `.txt` sidecars exist now; safer unique-prefix and richer sidecars can be added after fixtures. | Recovers metadata exported separately from images. | Prefix matching can attach wrong sidecars. | Medium | Medium | P2 |
| Fielded AI metadata search | DT | Adopt now | Existing columns support useful first fields: seed, steps, cfg, sampler, model, negative, size. | Precise search without abandoning simple FTS. | Parser and SQL builder edge cases. | Medium | Medium | P2 |
| ComfyUI node/property search | DT | Research first | Useful for workflow-heavy users, but raw node/property rows can bloat SQLite. | Powerful workflow discovery. | Schema bloat; noisy results; performance risk. | High | High | P3/research |
| Prompt grouping/usage stats | DT | Adapt later | Valuable once background indexing makes metadata coverage broad. | Shows repeated prompts, negative prompts, and model usage. | Less important than core search; group-by can be costly. | Low/Medium | Medium | P3 |
| Optional local folder watcher | DT | Adapt later | Useful for stable local roots but unsafe as a default for web/VPS/mobile use. | Keeps warm folders fresh; reduces manual rescans. | Platform-specific missed events and bursts. | High | Medium | P3 |
| Index status/progress | DT | Adopt now | Users need to know when background metadata/search is warming. | Better trust; easier debugging; supports observability. | Status can become noisy or misleading. | Medium | Medium | P1 |
| Thumbnail visible-area queue discipline | DT | Research first | Browser lazy loading already works; backend throttling may help thumbnail storms if measured. | Reduces CPU spikes from offscreen thumbnails. | Adds scheduling complexity over HTTP request order. | Medium | Medium | P2/P3 |
| Synchronous viewer metadata reparse | DT | Reject | gallery-repo's lightbox must open before metadata; DT's audited viewer path is the wrong model here. | None for current goals. | Blocks click/next transitions; duplicates parse work. | High | Low to copy, high to repair | Never |
| Full-file hash/read for every image on scan | DT | Reject | gallery-repo already has path+mtime+size freshness; full reads would destroy scan. | Content identity could help duplicates, but not worth hot-path cost. | Massive IO/memory cost. | Very high | Medium | Never |
| Stealth PNG pixel scan | DT | Reject | Pixel LSB scanning is too expensive for normal scan/viewer paths. | Could recover hidden metadata from rare files. | CPU-heavy; surprising; hard to bound. | High | High | Never by default |
| Per-folder thumbnail SQLite cache | DT | Reject | gallery-repo's thumbnail cache key is stronger and already mtime/size-aware. | Per-folder locality. | Duplicate cache system; weaker invalidation if copied directly. | Medium | Medium | Never |

### Immich Ideas

| Idea | Source | Decision | Why | Advantages | Disadvantages | Risk | Complexity | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DB-first viewer metadata | Immich | Adopt now | Warm metadata panels should read SQLite instead of parsing originals. | Instant warm lightbox metadata; fewer original reads. | Must handle stale rows and missing cache cleanly. | Medium | Medium | P1/P2 |
| Compact list/grid DTO separate from full detail DTO | Immich | Adopt now | `/api/scan` should stay minimal even as metadata grows. | Protects payload size and grid performance. | Requires discipline when adding readiness fields. | Low | Low | P0/P1 |
| Background job chain for metadata/thumbnail/search | Immich | Adapt later | Use the idea, not BullMQ: local metadata -> derivative -> search readiness chain. | Clear sequencing and retries. | Too much job machinery if overbuilt. | Medium | Medium/High | P1/P2 |
| Derivative status rows | Immich | Adapt later | SQLite readiness rows can make thumbnail/preview cache queryable. | Lets scan/status know cache readiness without opening files. | Duplicate truth with disk cache unless ownership is clear. | Medium | Medium | P2 |
| Thumbnail/preview/original source policy | Immich | Research first | Immich's preview-first policy conflicts with current original-lightbox guarantee, but preview placeholders are useful. | Better perceived load for huge originals. | Easy to replace original accidentally. | High | Medium | P2/research |
| Next/previous viewer preloading | Immich | Adopt now | Current neighbor preloading only requests 800px thumbnails; metadata/dimensions can be prefetched too. | Faster transitions and metadata panels. | Bandwidth/disk waste if unbounded. | Medium | Low/Medium | P2 |
| Time-bucket/timeline API | Immich | Research first | Great for 100k photo libraries, but gallery-repo is folder-first. Research only if warm-folder listing is not enough. | Large library navigation. | New product model and API surface. | High | High | P4/research |
| PostgreSQL metadata filters | Immich | Reject | SQLite remains default. Borrow filter concepts, not PostgreSQL. | Strong filtering at scale. | Requires default DB migration and ops burden. | Very high | Very high | Never |
| Trigram/unaccent search | Immich | Adapt later | SQLite already has trigram FTS for CJK/substrings; unaccent may be considered if needed. | Better fuzzy text matching. | SQLite implementation differs; can hurt relevance. | Medium | Medium | P3 |
| OCR/CLIP smart search | Immich | Reject | Valuable but too heavy for current default local AI gallery. | Powerful semantic discovery. | ML dependencies, hardware, indexing cost. | Very high | Very high | Never by default |
| Asset checksum/change detection | Immich | Research first | Content checksums may help duplicates/moves but must not run on scan. | Better duplicate/move detection if explicit. | Full-file reads are expensive. | High | Medium | P4/research |
| External library scan model | Immich | Reject | gallery-repo should remain ad hoc folder-first, not an owned library import system. | Strong managed library behavior. | Product scope shift. | High | High | Never |
| Optional watcher/scheduled scan | Immich | Adapt later | Disabled-by-default watcher/scheduled refresh can warm stable roots. | Better freshness for local folders. | Missed events, event storms, platform differences. | High | Medium | P3 |
| Queue status/admin endpoint | Immich | Adopt now | A small `/api/index/status` maps well to local indexing. | Debuggable progress and failures. | Must avoid noisy UI. | Medium | Medium | P1 |
| Multi-user/album/sharing/storage-template model | Immich | Reject | It solves backup/photo-server needs, not local gallery browsing. | Full photo app features. | Massive schema/UI scope. | Very high | Very high | Never |
| Redis/BullMQ/PostgreSQL full stack | Immich | Reject | The operational cost is wrong for gallery-repo. | Robust distributed processing. | External services become required. | Very high | Very high | Never |

## Root-Cause Driven Improvement Plan

### Problem 1: Metadata is still mostly on-demand; warm cache depends on user opening thumbnails/metadata.

Current gallery-repo problem:

- `image_metadata` is populated by `/api/metadata`, `/api/thumbnail` dimensions, or explicit `index_image()`.
- `/api/scan` schedules `index_directory_tree(..., include_metadata=False)`, so prompt metadata is not warmed just by opening folders.

Root cause:

- The system correctly protected scan latency by removing metadata parsing from the hot path, but it has no replacement background metadata queue.

Evidence from current docs/code:

- [ARCHITECTURE.md](ARCHITECTURE.md) states `/api/scan` indexes folder/file rows in the background without re-indexing image metadata.
- [backend/scan.py](../backend/scan.py) calls `background_tasks.add_task(index_directory_tree, target, False)`.
- [metadata_store.py](../backend/metadata_store.py) can index images but does so synchronously per image when called.

Idea borrowed from DT/Immich:

- DT: bounded metadata scanner workers and batch writer.
- Immich: background metadata extraction after asset discovery.

Why this is the correct adaptation:

- Add a local SQLite-backed or SQLite-observed in-process queue that accepts files seen by scan and parses them after the scan response returns.
- Coalesce jobs by path+mtime+size.
- Keep worker count low, likely one metadata worker by default.

Why not copy the original design exactly:

- Do not read/hash every file during scan like DT.
- Do not import Immich's BullMQ/Redis worker stack.
- Do not require a persistent asset import model before browsing.

Expected benefit:

- Warm lightbox metadata and prompt search without manual opens.
- Large folders become progressively more useful after first open.

Trade-off:

- Background CPU/disk work can interfere with thumbnails or lightbox unless throttled.

Failure mode:

- Queue steals resources or indexes stale files after edits.

How to test:

- Metadata queue coalescing test.
- Stale file invalidation test.
- Album-open perf must not regress.
- Metrics for queue depth, active jobs, job duration, and errors.

### Problem 2: `/api/scan` is fast for dozens but still enumerates/sorts large folders before returning a page.

Current gallery-repo problem:

- `scan_directory()` builds the complete `images` list, sorts all images, then `/api/scan` slices by `image_cursor`.
- Pagination happens after enumeration/sort.

Root cause:

- The current design optimizes cold direct browsing and simple correctness, not DB-first warm listing.

Evidence from current docs/code:

- [backend/scan.py](../backend/scan.py) returns `total_images = len(images)` after all image rows are collected and sorted.
- [MEDIA_PIPELINE_COMPARISON.md](MEDIA_PIPELINE_COMPARISON.md) identifies 5000+ warm folders as a case where Immich/DT-style indexed browsing wins.

Idea borrowed from DT/Immich:

- DT: indexed DB-backed paging after scan.
- Immich: compact timeline/list DTOs served from DB once rows exist.

Why this is the correct adaptation:

- Keep cold `/api/scan` direct.
- Add an optional warm fast path that reads from `file_index` only when the folder index is complete and fresh enough.
- Validate folder mtime and sampled file mtime/size before trusting DB rows.

Why not copy the original design exactly:

- Do not replace folder browsing with Immich month buckets.
- Do not force users to import a library before browsing.

Expected benefit:

- 5000-image warm first page can target 300-500 ms after indexed listing exists.

Trade-off:

- Requires index completeness tracking and stale fallback logic.

Failure mode:

- Stale DB listing misses new/deleted files.

How to test:

- Warm indexed listing tests with file add/delete/rename.
- Backend perf script for 5000-file fixture.
- Album-open perf must stay within current or <= 10% regression.

### Problem 3: Search has FTS/trigram but lacks fielded metadata query syntax like `seed:`, `model:`, `sampler:`, `cfg:`.

Current gallery-repo problem:

- Unified search treats the query as plain text for album/photo/prompt sections.
- Structured columns exist but are not queryable through field filters.

Root cause:

- Current search focuses on simple text and safe FTS fallback. No parser separates residual prompt text from structured predicates.

Evidence from current docs/code:

- [backend/metadata_store.py](../backend/metadata_store.py) has columns `seed`, `steps`, `cfg_scale`, `model`, `sampler`, `width`, `height`.
- `_search_prompt_rows()` searches FTS/LIKE over text fields, not structured predicates.
- [DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md](DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md) proposes field parsing over current columns.

Idea borrowed from DT/Immich:

- DT: query parser removes recognized field tokens and combines structured filters with prompt text.
- Immich: metadata filters are DB predicates, not file parsing.

Why this is the correct adaptation:

- Add fielded search as a parser layer above existing FTS.
- Recognized fields become SQL predicates; residual text goes through current unicode/trigram/LIKE flow.

Why not copy the original design exactly:

- Do not copy every DT filter family before those concepts exist.
- Do not use PostgreSQL-only filtering from Immich.

Expected benefit:

- Users can find exact seeds, models, samplers, steps, CFG values, and orientations.

Trade-off:

- Parser complexity and malformed-query behavior need tests.

Failure mode:

- Parser eats normal text or breaks CJK/plain searches.

How to test:

- Fielded parser unit tests.
- SQL builder tests with SQLite fixtures.
- Plain text, CJK, malformed token, current/all scope tests.

### Problem 4: Metadata parser coverage can be improved for AI generator formats and sidecars.

Current gallery-repo problem:

- Parser coverage is split and incomplete relative to DT.
- `metadata_parse.py` and `metadata_extract.py` can return different normalized fields.

Root cause:

- There are two parser stacks: one rich for lightbox, one simpler for indexing/search.

Evidence from current docs/code:

- [DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md](DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md) identifies parser divergence and missing Fooocus, InvokeAI, some WebP EXIF conventions, richer sidecars, and Stealth PNG.
- [backend/metadata_parse.py](../backend/metadata_parse.py) has richer SwarmUI/ComfyUI/NovelAI/EasyDiffusion handling.
- [backend/metadata_extract.py](../backend/metadata_extract.py) has a smaller normalized extraction path.

Idea borrowed from DT/Immich:

- DT: broad AI metadata candidate/parsing coverage.
- Immich: backend normalizes metadata; frontend renders normalized DTOs.

Why this is the correct adaptation:

- First unify parser core and fixtures.
- Then widen coverage incrementally with fixtures for each generator/source.
- Record internal source/provenance where useful.

Why not copy the original design exactly:

- Do not read/hash whole files before parsing.
- Do not add ExifTool as a default dependency for AI metadata.
- Do not put Stealth PNG pixel scans in normal paths.

Expected benefit:

- Lightbox metadata and search index agree.
- More generator outputs become searchable.

Trade-off:

- Parser maintenance grows; fixtures become mandatory.

Failure mode:

- Bad parser heuristics misclassify metadata or attach wrong sidecars.

How to test:

- Parser fixture tests for A1111, ComfyUI, SwarmUI, NovelAI, EasyDiffusion, exact sidecar, EXIF UserComment, malformed JSON.
- Regression tests that `/api/metadata` and `index_image()` agree on normalized fields.

### Problem 5: Lightbox is good now, but next/prev metadata and dimensions can be prefetched better. *(Historical — resolved by Phase 2A: neighbor preload now fetches thumbnail+preview 1440, and metadata prefetch follows navigation.)*

Evidence from current docs/code:

- [frontend/src/stores/lightbox.ts](../frontend/src/stores/lightbox.ts) `preloadNeighbors()` creates `Image()` objects for thumbnail URLs.
- [frontend/src/composables/usePhotoSwipe.ts](../frontend/src/composables/usePhotoSwipe.ts) fetches metadata dimensions on demand through TanStack Query.
- Lightbox perf tests assert original source and transition budget.

Idea borrowed from DT/Immich:

- Immich: next/previous viewer asset DTO and preview preloading.

Why this is the correct adaptation:

- Prefetch neighbor metadata via TanStack Query with low concurrency.
- Prefetch medium thumbnails/previews only.
- Never preload full originals for neighbors by default.

Why not copy the original design exactly:

- Switch PhotoSwipe main source to preview 1440 (Phase 2A), keeping original only on zoom/fullscreen.
- Do not load original for next/prev neighbors — only thumbnail + preview.

Expected benefit:

- Faster next/prev metadata panels and more stable dimensions on transition.

Trade-off:

- Extra background requests for users who do not navigate.

Failure mode:

- Bandwidth spikes or disk contention during rapid navigation.

How to test:

- Lightbox transition perf test.
- Network assertion that neighbor prefetch does not request `/api/image`.
- Metadata query count/coalescing tests.

### Problem 6: There is no visible index status/progress, so users cannot tell if metadata/search cache is warming.

Current gallery-repo problem:

- Background file indexing and future metadata indexing are invisible.
- Users cannot distinguish "no metadata exists" from "metadata is still indexing."

Root cause:

- Current background work is opportunistic and not represented as first-class status.

Evidence from current docs/code:

- [backend/scan.py](../backend/scan.py) schedules background tasks but exposes no status endpoint.
- [metadata_store.py](../backend/metadata_store.py) has no job/status table.
- Previous UI guidance warns against noisy status/toast regressions.

Idea borrowed from DT/Immich:

- DT: scanning progress.
- Immich: queue status/admin endpoints.

Why this is the correct adaptation:

- Add `/api/index/status` with counters by folder/root: queued, running, done, failed, stale, last error, updated timestamp.
- Frontend should show a subtle status affordance, not a toast per event.

Why not copy the original design exactly:

- Do not build a full Immich admin queue console.
- Do not spam toasts.

Expected benefit:

- Users understand why search improves over time.
- Debugging large folders becomes easier.

Trade-off:

- Progress estimates can be approximate.

Failure mode:

- Status UI becomes noisy or misleading.

How to test:

- Index status endpoint tests.
- Frontend no landing toast regression.
- `/api/index/status` p95 <= 50 ms warm.

### Problem 7: SQLite writes may become inefficient under large background indexing.

Current gallery-repo problem:

- `index_image()` and `index_file()` write rows individually under `_DB_LOCK`.
- That is fine for small opportunistic updates but inefficient for thousands of metadata jobs.

Root cause:

- Current code was built around request-adjacent cache upserts, not a sustained indexer.

Evidence from current docs/code:

- [metadata_store.py](../backend/metadata_store.py) opens transactions per function call.
- Existing docs identify DT's batched writer as the best local pattern.

Idea borrowed from DT/Immich:

- DT: batch around small groups of records.
- Immich: background jobs separate request reads from processing writes.

Why this is the correct adaptation:

- Add a batched writer with bounded batch size/time flush.
- Keep WAL and busy timeout.
- Track write latency metrics.

Why not copy the original design exactly:

- Do not create distributed queues.
- Do not hold huge transactions.

Expected benefit:

- Lower SQLite lock churn and better large-folder indexing throughput.

Trade-off:

- Small delay before parsed metadata becomes visible.

Failure mode:

- Long write transactions block search/status reads.

How to test:

- Batch writer unit test.
- SQLite write latency metric.
- Concurrent scan/search while background writes run.

### Problem 8: There is no formal derivative readiness/status table for thumbnails/previews.

Current gallery-repo problem:

- Thumbnail readiness is implicit in diskcache/files.
- `/api/scan` cannot cheaply report derivative readiness without checking disk paths per image.

Root cause:

- Lazy thumbnail generation started as a simple request cache, not an indexed derivative model.

Evidence from current docs/code:

- [backend/thumbnails.py](../backend/thumbnails.py) persists WebP files based on cache key.
- No `asset_file`-like table exists in [metadata_store.py](../backend/metadata_store.py).

Idea borrowed from Immich:

- `asset_file` derivative rows, adapted to SQLite and path+mtime+size.

Why this is the correct adaptation:

- Add a `derivative_status` table keyed by path, mtime, size, derivative type, max size, quality, cache file path, ready/error timestamps.
- Use it for status/readiness, not as a second thumbnail cache owner.

Why not copy the original design exactly:

- Do not require eager derivative generation for every file.
- Do not switch to asset-id storage ownership.

Expected benefit:

- Grid/status can know if thumbnails/previews are ready.
- Future preview warmer can be controlled.

Trade-off:

- More schema and cleanup logic.

Failure mode:

- DB status says ready while disk file is missing, or vice versa.

How to test:

- Derivative readiness tests.
- Stale file invalidation tests.
- Cache-file missing recovery test.

### Problem 9: Optional watcher/scheduled refresh is not available for stable local folders.

Current gallery-repo problem:

- Users must revisit/scan folders to update indexes.
- Stable local roots cannot warm automatically in the background.

Root cause:

- gallery-repo is ad hoc folder-first and avoids platform-specific watchers by default.

Evidence from current docs/code:

- No watcher module exists.
- Existing docs identify watcher support as useful but risky.

Idea borrowed from DT/Immich:

- DT/Immich optional watchers and scheduled library scans.

Why this is the correct adaptation:

- Add opt-in watcher/scheduled refresh only after index status and queue coalescing exist.
- Scope it to configured roots, not arbitrary browsing.

Why not copy the original design exactly:

- Do not make watchers default.
- Do not adopt Immich's external library/offline asset model.

Expected benefit:

- Stable local folders stay warm without manual refresh.

Trade-off:

- Watcher behavior varies by platform and filesystem.

Failure mode:

- Missed events or event storms create stale data or queue floods.

How to test:

- Watcher integration tests behind opt-in flag.
- Queue coalescing under burst events.
- Scheduled refresh metrics and stale cleanup tests.

### Problem 10: Large warm libraries still cannot behave like Immich's DB-first timeline/search.

Current gallery-repo problem:

- Even warm metadata/search caches do not make folder open fully DB-first.
- There is no time-bucket/timeline API and no persistent asset model.

Root cause:

- The app is folder-first and direct-scan-first by design.

Evidence from current docs/code:

- `/api/scan` always calls `scan_directory()` today.
- [IMMICH_PIPELINE_AUDIT.md](IMMICH_PIPELINE_AUDIT.md) shows Immich timeline APIs read compact DB buckets.

Idea borrowed from Immich:

- DB-first compact list APIs and bucketed thinking, adapted to folder pages before any timeline product shift.

Why this is the correct adaptation:

- First solve warm folder listing from `file_index`.
- Only research time buckets if product requirements move toward timeline browsing.

Why not copy the original design exactly:

- Do not make gallery-repo a full photo timeline server.
- Do not introduce multi-user assets/albums/storage templates.

Expected benefit:

- Warm 5000-image folders can feel prepared without losing ad hoc browsing.

Trade-off:

- Requires index completeness and stale detection.

Failure mode:

- Users see stale folder pages from DB-first reads.

How to test:

- Warm listing fixture with adds/deletes/renames.
- 5000-image warm first-page target.
- Fallback-to-direct-scan test when index is incomplete/stale.

## Phased Roadmap

### Phase 0 - Preserve and Lock Current Guarantees

| Field | Plan |
| --- | --- |
| Goal | Make existing scan, thumbnail, metadata, lightbox, search, and state ownership contracts explicit and test-protected before adding new background work. |
| Why now | The borrowed DT/Immich ideas are useful only if they do not erode the current hot paths. |
| Why this order | Locking guarantees first reduces risk in every later phase. |
| Borrowed from | gallery-repo itself: current fast scan, lazy thumbnails, derivative-first lightbox (Phase 2A), Query/Pinia split, perf tests. |
| Current problem solved | Prevents accidental regressions while implementing larger changes. |
| Files likely affected | Primarily docs and tests: `docs/`, `frontend/tests/perf/`, backend tests. No behavior changes unless guard tests expose existing gaps. |
| Backend changes | Add or strengthen tests proving `/api/scan` does not call PIL/metadata parsing and only reads validated cached dimensions. |
| Frontend changes | Add tests for no false empty state, no search no-results before settled fetch, no landing toast regression, and lightbox source policy. |
| DB/schema changes | None. |
| API changes | None. |
| Docs changes | Keep `ARCHITECTURE.md`, `PERFORMANCE_TESTING.md`, and this plan synchronized. |
| Tests to add/update | Scan no-PIL guard; cached dimension validation; lightbox `/api/preview` normal + `/api/image` on-demand assertion (Phase 2A); no full-original neighbor preload assertion; empty/search state regressions. |
| Perf budgets | Existing album/lightbox budgets; 50-image scan p95 <= current budget or <= 10% regression. |
| Acceptance criteria | Existing perf tests pass; guard tests fail if scan opens images or lightbox main source changes. |
| Rollback plan | Remove only added guard tests if they are incorrectly specified; do not relax perf budgets without benchmark evidence. |
| Risk level | Low. |
| What not to do | Do not use Phase 0 to refactor backend/frontend or introduce dependencies. |

### Phase 1 - Unified Parser, Background Metadata Indexer, Batched Writer, Index Status

| Field | Plan |
| --- | --- |
| Goal | Warm metadata/search in the background while keeping scan fast. Unify parser behavior so `/api/metadata` and SQLite indexing agree. |
| Why now | This fixes the largest current weakness: metadata/search caches depend on user actions. |
| Why this order | Parser fixture/unification should precede broad background indexing so the indexer stores the same truth as the lightbox. |
| Borrowed from | DT metadata parser coverage, DT bounded scanner/writer, Immich background metadata extraction/status concept. |
| Current problem solved | Metadata cache and search index warm after folder open without blocking folder open. |
| Files likely affected | `backend/metadata_parse.py`, `backend/metadata_extract.py`, `backend/metadata_store.py`, `backend/scan.py`, new backend indexer module if implemented, `backend/app.py` if adding route, `frontend/src/services/api.ts` if adding status API, optional small status component. |
| Backend changes | Add parser fixtures; extract shared normalized parser core; add queue/job records or in-process queue with SQLite-observed status; coalesce by path+mtime+size; add one-worker default; add batch writer; add `/api/index/status`. |
| Frontend changes | Add optional subtle indexing status indicator; do not add toasts for every job; keep gallery display unchanged. |
| DB/schema changes | Add index job/status table(s): path, mtime, size, state, attempts, error, queued/running/done timestamps, folder/root scope. Consider parser provenance fields if needed. *(Implemented as RAM staging queue per user choice — avoids SQLite write contention on hot paths.)* |
| API changes | Add `GET /api/index/status?path=...` returning cheap counts and last error. Existing `/api/scan`, `/api/metadata`, `/api/search` remain backward-compatible. |
| Docs changes | Update architecture cache boundaries and performance docs. |
| Tests to add/update | Parser fixtures; queue coalescing; stale invalidation; batch writer; index status endpoint; scan perf. |
| Perf budgets | `/api/scan` p95 no more than 10% regression; `/api/index/status` p95 <= 50 ms warm; background indexer yields to request hot path. |
| Acceptance criteria | Opening a folder enqueues metadata jobs and returns before jobs finish; warm metadata can be read from SQLite; duplicate jobs coalesce; stale file changes invalidate queued/done rows; status endpoint is fast. |
| Rollback plan | Feature-flag/disable background metadata worker and continue serving on-demand `/api/metadata`; preserve parser fixtures. |
| Risk level | Medium. |
| What not to do | Do not parse metadata inside `/api/scan`; do not add Redis/BullMQ; do not introduce ExifTool as a default dependency; do not run Stealth PNG scans. |

### Phase 2A (✅ Done) — Derivative-first Lightbox with Preview Layers, Zoom Trigger, Neighbor Prefetch

| Field | Plan |
| --- | --- |
| Goal | Replace `/api/image` as PhotoSwipe main `src` with `/api/preview` (1440px) derivative; keep original `/api/image` only for zoom, fullscreen, download, and animated files. Preload only thumbnail+preview for neighbors, never original. |
| Why now | Derivative-first model makes lightbox faster: preview 1440 loads faster than original for large files, zoom triggers original on demand, neighbor preload doesn't spike bandwidth. |
| Borrowed from | Immich derivative-first viewer policy (adapted — gallery-repo keeps original fidelity as zoom layer, not as the main source). |
| Current problem solved | Lightbox image load blocks on full original download; neighbor preload wastes bandwidth on originals. |
| Files affected (implemented) | `backend/thumbnails.py` — `/api/preview` endpoint, shared `generate_derivative()` core, cache key per derivative type. `backend/config.py` — `PREVIEW_SIZE` (1440), `PREVIEW_QUALITY`, cache version. `backend/images.py` — `/api/image` kept for zoom/animated. `backend/models.py` — derivative-related models. `frontend/src/utils/api.ts` — `getPreviewUrl()`. `frontend/src/utils/buildPhotoSwipeItem.ts` — derivative-first policy. `frontend/src/composables/usePhotoSwipe.ts` — zoom trigger, preview preload. `frontend/src/stores/lightbox.ts` — preload neighbor only thumbnail+preview. `frontend/src/utils/constants.ts` — `PREVIEW_SIZE`. `frontend/components/GridItem.vue`, `AlbumCard.vue` — thumbnail 512. |
| Backend changes (done) | 3 clear endpoints: `/api/thumbnail` (grid 512), `/api/preview` (lightbox 1440), `/api/image` (original — zoom/fullscreen/download/animated only). Shared `generate_derivative()` core with per-type cache keys. No upscale. |
| Frontend changes (done) | PhotoSwipe `src = /api/preview`. Zoom/fullscreen triggers original load via `zoomTriggerOriginal()`. Neighbor preload: only `getThumbnailUrl()` + `getPreviewUrl()`, never `getImageUrl()`. Grid items use thumbnail 512. |
| DB/schema changes (done) | Derivative readiness via cache file persistence + cache key versioning. No new table — derivative status is implicit in disk cache. Prometheus metrics: `gallery_derivative_ready_total`, `gallery_derivative_errors_total`. |
| API changes (done) | Added `GET /api/preview?path=...&max_size=1440&quality=85`. |
| Docs changes (done) | Updated perf comparison report. |
| Tests to add/update (done) | `test_derivatives.py` (7 backend tests — preview generation, cache key, no upscale, zoom trigger policy). `lightbox-loading-policy.spec.ts` (7 Playwright tests — preview used, original only on zoom, no neighbor original preload). Updated `lightbox.perf.spec.ts` (transition, zoom). |
| Perf budgets (validated) | Scan p95: **61ms** ✅ Lightbox visible: **690ms** ✅ Preview loaded: **1,581ms** ✅ Transition: **65ms** ✅ |
| Acceptance criteria (met) | Normal open: no `/api/image` request ✅ Zoom triggers `/api/image` ✅ Neighbor preload: only thumbnail+preview ✅ |
| Rollback plan | Revert to `src = /api/image` (pre-Phase-2A commit `a471eed`). |
| Risk level | Medium (successfully mitigated — tests pass, budgets met). |
| What was learned | iPad Safari doesn't support `color-mix()`. `backdrop-filter + v-if + transition` causes jank on iPad. test-only hook must be gated; do not expose __pswp in production |

### Phase 2B (Next) — Fielded Metadata Search + DB-first Warm Metadata Reads

**Rule:** Any metadata field visible in the lightbox should be searchable either as a first-class field or via a generic `param:` / `advanced:` / `raw:` fallback.

#### A. First-class search fields

**Core**
- `name:` — filename search
- `prompt:` / `positive:` — positive prompt only
- `negative:` — negative prompt only
- `date:` — file date / EXIF date
- `generation_time:` / `gen_time:` — generation timestamp
- `source:` / `tool:` — generator application (A1111, ComfyUI, SwarmUI, etc.)

**Generation**
- `seed:` — exact seed match
- `steps:` — step count (numeric, supports `>` `<` `>=` `<=`)
- `cfg:` / `cfg_scale:` — CFG scale
- `sampler:` — sampler name
- `scheduler:` — scheduler name
- `size:` — exact size `WxH` or dimension range
- `width:` — width in pixels
- `height:` — height in pixels
- `aspect_ratio:` / `ratio:` — aspect ratio (e.g. `16:9`, `1:1`)

**Resources**
- `model:` — model name / identifier
- `checkpoint:` — checkpoint name
- `model_hash:` — exact model hash
- `model_or_hash:` — model name or hash match
- `lora:` — LoRA name
- `resource:` — any resource name (LoRA, embedding, etc.)
- `resource_hash:` — resource hash

**Extra settings**
- `clip_skip:` — CLIP skip value
- `hires_upscale:` — hires fix upscale factor
- `hires_steps:` — hires fix steps
- `denoising_strength:` — denoising strength
- `vae:` — VAE name
- `ensd:` — ENSD value
- `aesthetic_score:` — aesthetic score

**Location / path**
- `path:` — exact or partial file path
- `folder:` — parent folder name
- `location:` — alias for path/folder (not GPS unless GPS EXIF support added later)

#### B. Generic fallback fields

- `param:<key>:` — search any metadata key by name
- `advanced:<key>:` — search advanced/workflow-specific keys
- `raw:` — search raw metadata text

The generic fallback exists so advanced/lightbox-visible metadata can be searched without adding a first-class token for every possible backend-specific metadata key.

#### C. DB-first warm metadata read path

- Lightbox metadata panel reads fresh SQLite metadata first.
- Fallback to parsing the original file only on cache miss, stale data, or error.
- Must not block lightbox image open.
- Must not regress `/api/scan` performance.

#### Important semantics

**1. Plain text remains backward-compatible**

Text outside field tokens remains the current backward-compatible unified search. It preserves existing filename / folder / album / photo / prompt behavior.

Example: `rain seed:123` means unified text search for "rain" AND seed = 123.

**2. Explicit prompt-only search**

`prompt:` / `positive:` search positive prompt only.

Example: `prompt:"girl, rain" seed:123` means: positive prompt contains "girl" AND positive prompt contains "rain" AND seed = 123.

**3. Explicit negative-only search**

`negative:` searches negative prompt only.

Example: `negative:"watermark, blurry"` means: negative prompt contains "watermark" AND negative prompt contains "blurry".

**4. DT-inspired, but gallery-modified**

Inspired by DiffusionToolkit fielded search, but modified for gallery-repo:

- DiffusionToolkit treats residual text as prompt query.
- Gallery keeps residual text as backward-compatible unified search, and adds explicit `prompt:` / `positive:` for positive-prompt-only search.

**5. Albums section is folder/album suggestions, not field-filtered image results**

For fielded queries (e.g. `rain seed:123`):

- **Photos / Prompt image result sections**: narrowed by metadata field filters (seed:, model:, etc.). Results are guaranteed to satisfy all field predicates.
- **Albums section**: based solely on residual text (e.g. `rain`). Albums are folder/album *navigation suggestions*, similar to search suggestions / folder suggestions. They are intentionally not narrowed by metadata field filters.
- This is a deliberate product decision: albums are entry points for browsing, not strict filtered image results.

**Future enhancement**: Consider adding a separate "Albums containing matching photos" section that aggregates folders/albums from the field-filtered image result set when a user wants folder-level organization of filtered results.

#### Implementation scope

| Field | Plan |
| --- | --- |
| Goal | Make warmed metadata useful: precise fielded search and DB-first warm metadata reads for the lightbox panel (no re-parse when SQLite has fresh data). |
| Why now | Phase 1 created broad indexed data. Phase 2B exposes it safely to search and lightbox workflows. |
| Why this order | Fielded search and DB-first metadata depend on reliable indexed metadata from Phase 1. |
| Borrowed from | DT fielded metadata search (modified — gallery keeps unified text residual); Immich DB-first viewer metadata. |
| Current problem solved | Search lacks structured filters; warm lightbox still parses originals instead of reading cached SQLite metadata. |
| Files likely affected | `backend/search.py`, `backend/metadata_store.py`, `backend/metadata_parse.py`, `frontend/src/services/api.ts`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/stores/lightbox.ts`, `frontend/src/components/Lightbox.vue`, search UI tests. |
| Backend changes | Add fielded query parser and SQL predicate builder for all first-class fields; add generic `param:` / `advanced:` / `raw:` fallback; add cached metadata read path so lightbox reads from SQLite when fresh. |
| Frontend changes | Prefetch next/previous metadata with TanStack Query; optionally show index readiness subtly; keep normal search behavior unchanged. |
| DB/schema changes | Add columns for new search fields as needed (`tool`, `model_hash`, `scheduler`, `lora_text`, `generation_time`, `aesthetic_score`, etc.) after parser fixtures. |
| API changes | Extend `/api/search` to parse supported field tokens; add generic fallback parsing; add cache status fields; keep plain query response shape compatible. |
| Docs changes | Document all fielded syntax, generic fallback, and DB-first metadata read path. |
| Tests to add/update | Fielded search parser per field; generic fallback parser; SQL builder; plain text compatibility; warm metadata read path; search no-results settled state. |
| Perf budgets | Plain search p95 must not regress materially; lightbox metadata p95 <= current budget. |
| Acceptance criteria | `cat seed:123 model:"foo*"` searches unified text for `cat` and filters metadata; `prompt:"girl, rain" seed:123` searches prompt only; plain `cat` still behaves like today; warm lightbox metadata does not parse the original. |
| Rollback plan | Disable fielded parser and treat all queries as plain text; disable generic fallback; disable neighbor metadata prefetch. |
| Risk level | Medium. |
| What not to do | Do not replace normal search with a strict query language; do not preload `/api/image` for neighbors; do not add Redis/BullMQ. |

### Phase 3 (✅ Done) — Warm Indexed Folder Listing, Optional Watcher/Scheduled Refresh, Richer Facets

| Field | Plan |
| --- | --- |
| Goal | Make large warm folders feel more DB-first while keeping cold ad hoc folders direct and fast. |
| Why now | Warm metadata/search and status must exist before trusting DB-first folder pages. |
| Why this order | Indexed listing requires completeness/staleness signals from Phase 1 and derivative/search readiness from Phase 2. |
| Borrowed from | DT indexed search/listing and watcher ideas; Immich compact list DTOs and scheduled/watcher refresh ideas. |
| Current problem solved | `/api/scan` still enumerates/sorts large folders before returning a page; stable roots do not refresh automatically. |
| Files affected | `backend/scan.py`, `backend/metadata_store.py`, `backend/config.py`, `backend/app.py`, `backend/facets.py` (new), `backend/refresh.py` (new), `backend/watcher.py` (new), `scripts/perf_warm_listing.py` (new), backend tests (4 new files), docs. |
| Backend changes | Add `folder_index_state` SQLite table; add `get_warm_folder_listing()` helper; add `update_folder_index_state()`; wire warm listing into `/api/scan` before fallback to `scan_directory()`; add disabled-by-default scheduled refresh (`backend/refresh.py`); add disabled-by-default watcher stub with optional watchdog (`backend/watcher.py`); add facets endpoint (`backend/facets.py`); add warm listing metrics. |
| Frontend changes | None required. Response shape remains backward-compatible with optional `index_source` field. |
| DB/schema changes | Added `folder_index_state` table (path, dir_mtime_ns, indexed_at, complete, child_count, folder_count, image_count, last_error, updated_at). |
| API changes | `/api/scan` may respond from `file_index` with `index_source: "warm_db"` when `ENABLE_WARM_INDEXED_LISTING=true` and freshness checks pass. Added `GET /api/facets` for DB-derived facet counts. Response shape is backward-compatible. |
| Docs changes | This plan updated. Phase 3 implementation details below. |
| Tests to add/update | `test_warm_folder_listing.py` (10 tests), `test_scheduled_refresh.py` (8 tests), `test_watcher.py` (7 tests), `test_facets.py` (7 tests). Existing scan hot path tests updated for `index_source` field. |
| Perf budgets | 5000-image warm first page target 300-500 ms after indexed listing exists; cold scan no worse than current. See `scripts/perf_warm_listing.py`. |
| Acceptance criteria | ✅ Warm indexed listing works for complete/fresh folders. ✅ Warm path avoids os.scandir on the requested folder. ✅ Stale/incomplete/missing state falls back to direct scan. ✅ Cold scan behavior unchanged. ✅ Response shape backward-compatible. ✅ Folder sorting/pagination matches direct scan. ✅ Scheduled refresh exists and disabled by default. ✅ Watcher exists as safe optional implementation with watchdog. ✅ Watcher/scheduled refresh cannot start without explicit config. ✅ Facets are DB-derived and bounded. ✅ No metadata parsing or PIL image open in `/api/scan`. ✅ Existing Phase 1/2A/2B tests still pass. ✅ New tests cover warm listing, refresh, watcher config, and facets. |
| Rollback plan | Set `ENABLE_WARM_INDEXED_LISTING=false`, `ENABLE_SCHEDULED_REFRESH=false`, `ENABLE_FILE_WATCHER=false`. Direct `/api/scan` remains source of truth. |
| Risk level | Medium. |
| What not to do | Resisted: import-before-browse, Immich timeline buckets, enabled-by-default watcher. |

### Phase 4 - Research-Only Advanced Library Features

| Field | Plan |
| --- | --- |
| Goal | Explore features that may help very large or workflow-heavy libraries after core local indexing is proven. |
| Why now | Not now for implementation; this phase names deferred research so it does not leak into early phases. |
| Why this order | Advanced features need warm metadata coverage, status, and benchmarks first. |
| Borrowed from | DT prompt usage stats and ComfyUI node/property search; Immich timeline/smart-search concepts. |
| Current problem solved | Optional deeper discovery for large indexed libraries. |
| Files likely affected | TBD; likely search/index schema, optional frontend views, optional feature modules. |
| Backend changes | Research prompt grouping, node summaries, raw workflow opt-in search, content checksum jobs, and possibly semantic/OCR plugin concepts. |
| Frontend changes | Research separate views or filters; avoid cluttering the main gallery. |
| DB/schema changes | Only after size/perf benchmarks. Candidate tables: prompt_usage, comfy_node_summary, optional checksum rows. |
| API changes | Dedicated endpoints only; do not overload `/api/scan`. |
| Docs changes | Research notes and benchmarks before implementation. |
| Tests to add/update | Benchmark fixtures, DB bloat analysis, opt-in feature tests. |
| Perf budgets | No default startup, scan, or lightbox cost. |
| Acceptance criteria | A feature graduates from research only if it is optional, measured, and does not alter current guarantees. |
| Rollback plan | Keep research behind config or out of default builds. |
| Risk level | High if implemented prematurely. |
| What not to do | Do not add ML/OCR/CLIP, PostgreSQL, Redis, or storage-template concepts as defaults. |

## Architecture Diagrams

### Current gallery-repo pipeline

```text
click folder
-> useInfiniteScanQuery(path)
-> GET /api/scan
-> resolve path and path-safety check
-> os.scandir direct folder listing
-> stat image files
-> batch SQLite dimension lookup
   [only rows matching path + mtime + size]
-> sort folders/images
-> paginate after sort
-> return folders + image page
-> BackgroundTasks:
   -> index_file(folder)
   -> index_files_from_scan(folders, images)
   -> index_directory_tree(root, include_metadata=False)
-> GalleryGrid renders Query-owned rows
-> PhotoCard lazy-loads /api/thumbnail
-> /api/thumbnail opens image on cache miss and stores dimensions
-> click image
-> lightbox opens immediately
-> PhotoSwipe main src = /api/preview (1440px), /api/image only on zoom/fullscreen
-> metadata query fetches /api/metadata asynchronously
-> /api/metadata parses and upserts SQLite metadata
```

### Target near-term pipeline

```text
Cold folder open:
click folder
-> /api/scan direct folder scan
-> return rows fast
-> enqueue metadata jobs by path + mtime + size
-> grid thumbnails lazy
-> background metadata indexer parses originals with bounded workers
-> batched SQLite writer stores dimensions/metadata/search text
-> /api/index/status reports progress
```

Key rule: the enqueue operation may be cheap request-adjacent bookkeeping, but parsing and writing must not block the scan response.

### Target warm-cache pipeline

```text
Warm folder open:
click folder
-> /api/scan checks folder index state
-> if indexed and fresh:
     read first page from file_index/image_metadata
     include cached dimensions and readiness flags
     return page without full enumerate/sort
   else:
     direct scan fallback
     enqueue/refresh index jobs
-> grid thumbnails use browser/disk cache
-> metadata panels read cached DB metadata first
-> background indexer only fills stale/missing rows
```

Warm listing is an optimization, not the only path. Direct scan remains the fallback source of truth.

### Lightbox target pipeline (Phase 2A — current)

```text
click image
-> lightboxStore.open(path, visibleImages)
-> PhotoSwipe dataSource built:
     src  = /api/preview?max_size=1440&quality=85
     msrc = /api/thumbnail?max_size=512
     dimensions = scan -> remembered thumbnail -> cached metadata -> fallback
-> overlay visible
-> preview derivative (1440px) loads for current slide
-> zoom / fullscreen / download triggers original /api/image load
-> metadata panel:
     check TanStack metadata cache
     if warm DB metadata exists, return quickly
     else /api/metadata parses on demand and queues/store result
-> neighbor prefetch:
     metadata query for prev/next
     thumbnail + preview for prev/next (never /api/image)
```

Preview (1440px) is the authoritative lightbox main image. Thumbnail (512px) serves as msrc/placeholder. Original `/api/image` loads only on zoom, fullscreen, download, or for animated files.

### Search target pipeline (Phase 2B)

```text
plain query:
search box "rain portrait"
-> debounce
-> GET /api/search?q=rain%20portrait&scope=current&path=...
-> albums/photos: file_index_fts
-> prompt: image_metadata_fts or trigram FTS (backward-compatible unified)
-> fallback LIKE as today
-> grouped Albums / Photos / Prompt response

fielded query (first-class fields):
search box 'rain prompt:"girl, rain" seed:123 model:"realistic*" negative:"watermark"'
-> parser extracts:
     residual text = "rain" (unified search)
     filters = prompt text "girl, rain", seed exact 123,
               model wildcard realistic*, negative text watermark
-> residual text uses current unified FTS flow
-> filters become SQL predicates over image_metadata
-> current/all scope still joins through file_index
-> grouped response shape remains compatible

fielded query (generic fallback):
search box 'param:some_key:"value" advanced:workflow_field:"data" raw:"raw text"'
-> generic param:<key>: maps to metadata key-value columns
-> advanced:<key>: maps to advanced/workflow metadata columns
-> raw: searches raw metadata text blob
-> all other rules same as fielded query above

Plain text remains the default. Fielded search is an extension.
DiffusionToolkit treats residual text as prompt-only; gallery-repo keeps it as unified backward-compatible search.

## Testing And Perf Gates

### Backend Test Matrix

| Test | Purpose | Acceptance | Status |
| --- | --- | --- | --- |
| metadata queue coalescing test | Multiple enqueue calls for same path+mtime+size produce one active job. | One job runs; duplicate callers observe same status/result. | ✅ Phase 1 |
| stale file invalidation test | mtime/size changes invalidate dimensions, metadata, queued jobs, and derivative readiness. | Old rows are ignored or marked stale; fresh row/job is created. | ✅ Phase 1 |
| batch writer test | Parsed metadata writes flush in bounded batches. | Correct rows/FTS updates; transaction size bounded; write errors reported. | ✅ Phase 1 |
| parser fixture tests | Lock supported generator formats and sidecars. | Same normalized fields for API and index paths. | ✅ Phase 1 |
| fielded search parser tests | Preserve plain search and support supported fields. | Tokens parse correctly; malformed fields are predictable; residual text preserved. | 📋 Phase 2B |
| derivative readiness tests | Thumbnail/preview generation updates readiness and invalidates stale derivatives. | Ready row matches disk cache; missing file recovers. | ✅ Phase 2A |
| index status tests | `/api/index/status` reports queued/running/done/error quickly. | Counts accurate enough; last error present; p95 <= 50 ms warm. | ✅ Phase 1 |
| scan no-PIL test | Protect Rule 1. | `/api/scan` does not call `Image.open` or metadata parser. | ✅ Phase 0 |
| scan cached dimensions test | Protect Rule 2. | Only path+mtime+size-matching rows are returned. | ✅ Phase 0 |
| direct scan fallback test | Warm listing never hides stale filesystem changes. | Stale/incomplete index falls back to direct scan. | 📋 Phase 3 |

### Frontend Test Matrix

| Test | Purpose | Acceptance | Status |
| --- | --- | --- | --- |
| album-open perf test | Protect folder-open and thumbnails. | Scan p95/current budget passes; first thumbnail and p95 pass; duplicate cursor-0 count <= 1. | ✅ Phase 0 |
| lightbox-open perf test | Protect overlay and preview source. | Visible/preview budgets pass; `srcIsPreview` true; `/api/preview` used; zoom triggers `/api/image`. | ✅ Phase 2A |
| lightbox transition perf test | Protect next-image load and ratio. | Transition budget passes; aspect ratio diff < 0.2. | ✅ Phase 2A |
| lightbox loading policy | Protect derivative-first lightbox rules. | Normal open: no `/api/image`; zoom triggers original; neighbor preload skips original. | ✅ Phase 2A (7 tests) |
| no landing toast regression | Prevent noisy status/error UI on startup. | No success/progress toast appears just because indexing starts. | ✅ Phase 0 |
| empty state no flicker | Preserve `hasEverLoaded`/delayed empty behavior. | Empty state appears only after settled scan and no content. | ✅ Phase 0 |
| search no-results only after fetch settled | Preserve current no-results guard. | No-results state appears only after successful non-fetching search with empty sections. | ✅ Phase 0 |
| lightbox does not preload full original for neighbors | Prevent bandwidth spike. | Neighbor prefetch may request metadata/thumbnail/preview, not `/api/image`. | ✅ Phase 2A |
| fielded search plain compatibility | Ensure parser does not break normal search UI. | Plain query behavior/result grouping remains compatible. | 📋 Phase 2B |

### Perf Budgets

| Budget | Target |
| --- | --- |
| 50-image album scan p95 | <= current budget or no more than 10% regression. Current default scan budget is 500 ms. |
| First thumbnail start | <= current budget. Current default is 1000 ms. |
| Thumbnail p95 | <= current budget. Current default is 1200 ms. |
| Lightbox visible | <= current budget. Current default is 1500 ms. |
| Lightbox preview loaded | <= current budget. Current default is 4000 ms. |
| Lightbox transition | <= current budget. Current default is 3000 ms. |
| 5000-image warm first page | 300-500 ms after indexed listing exists. |
| `/api/index/status` warm p95 | <= 50 ms. |
| Background indexer | Must yield to request hot path; default one metadata worker unless benchmarks justify more. |

### Observability

Prometheus metrics to reuse:

- `http_request_duration_seconds`
- `http_request_count_total`
- route-level labels only, no per-path labels

Prometheus metrics to add:

- `gallery_index_queue_depth{state="queued|running|failed"}`
- `gallery_index_jobs_total{result="done|error|stale|skipped"}`
- `gallery_index_job_duration_seconds`
- `gallery_metadata_parse_duration_seconds`
- `gallery_sqlite_write_duration_seconds`
- `gallery_sqlite_write_batch_size`
- `gallery_derivative_ready_total{type="thumbnail|preview"}`
- `gallery_derivative_errors_total`
- `gallery_warm_listing_hits_total`
- `gallery_warm_listing_fallbacks_total{reason="stale|incomplete|error"}`

pyinstrument profile points:

- `/api/scan`
- `/api/metadata`
- `/api/thumbnail`
- `/api/search`
- `/api/index/status`
- background metadata worker parse loop, profiled through an explicit debug endpoint or command if needed

Queue metrics:

- queued/running/done/error counts
- age of oldest queued job
- active worker count
- coalesced duplicate count
- jobs skipped due to stale mtime/size

Job error metrics:

- parse error count by broad reason, not by path
- thumbnail render error count
- SQLite write error count
- retry/attempt count

SQLite write latency metrics:

- batch flush duration
- rows per batch
- busy timeout incidents
- write lock wait duration if measurable

## Risk Register

| Risk | Cause | Impact | Probability | Mitigation | Test/metric |
| --- | --- | --- | --- | --- | --- |
| Background indexer steals CPU/disk from UI | Worker parses too many large images while user opens folders/thumbnails. | Slow scan, thumbnail, metadata, or image serving. | Medium | One worker default; backoff/yield; pause under high request activity; metrics. | Album/lightbox perf; queue duration; request latency. |
| SQLite write locks | Large transactions or too many writer calls. | Search/status/scan cache reads stall. | Medium | WAL, busy timeout, bounded batch size, single writer. | SQLite write latency; concurrent read/write tests. |
| Duplicate jobs | Scan, watcher, metadata, and refresh enqueue same file. | Wasted CPU and confusing status. | High without coalescing | Coalesce by path+mtime+size; unique pending key. | Queue coalescing test; coalesced duplicate metric. |
| Stale metadata | File changed after job queued or DB row written. | Wrong prompts/dimensions/search results. | Medium | Validate mtime+size before parse and before write; stale cleanup. | Stale invalidation test; stale skip metric. |
| Invalid dimensions after EXIF orientation | Different paths store raw vs transposed dimensions. | Lightbox aspect ratio wrong. | Medium | Standardize dimension semantics in parser/thumbnail; fixture tests. | Lightbox ratio test; EXIF orientation fixture. |
| Fielded search breaks normal search | Parser consumes text incorrectly or changes FTS behavior. | Search feels worse for all users. | Medium | Residual-text parser tests; plain search compatibility tests; malformed fields as text until UI supports errors. | Search parser tests; frontend no-results test. |
| Too much DB bloat from raw workflows/node props | Indexing every ComfyUI node/property or raw JSON by default. | Slow DB, slow search, large cache files. | Medium | Store compact summaries first; raw/node search opt-in; benchmark DB size. | DB size metric; node search benchmark. |
| Prefetch causes bandwidth spikes | Neighbor prefetch loads large originals or too many previews. | Slow navigation and network/disk waste. | Medium | Do not preload `/api/image` for neighbors; cap concurrency; use metadata/thumbnail only. | Network assertion; lightbox perf. |
| Watcher misses events | Platform/filesystem watcher limitations. | Stale index after changes. | Medium | Watcher disabled by default; scheduled refresh fallback; manual rescan. | Watcher integration tests; stale cleanup metric. |
| New status UI becomes noisy like previous toast bug | Index events surface as toasts or distracting banners. | Poor UX and annoyance. | Medium | Subtle passive indicator; no per-job toasts; errors only when actionable. | No landing toast regression; manual UX review. |
| Thumbnail (512px) used as lightbox main src instead of preview (1440px) | Bug or regression uses wrong derivative endpoint. | Degraded lightbox quality. | Low | Source policy tests enforce preview endpoint. | `srcIsPreview` assertion in perf test; policy test zoom assertion. |
| Warm listing serves stale DB rows | Index completeness/freshness is wrong. | Missing or extra files in folder page. | Medium | Direct scan fallback; folder index state; stale validation. | Warm listing stale tests; fallback metric. |
| Parser fixture gap hides regressions | New parser coverage lacks representative samples. | Search/lightbox disagree or wrong fields. | High | Fixture-first parser changes; keep malformed fixtures. | Parser fixture suite. |
| Status endpoint becomes expensive | Counts query too many rows or scan paths. | Status polling hurts UI. | Low/Medium | Pre-aggregated counters or indexed status table; no path-cardinality metrics. | `/api/index/status` p95 <= 50 ms. |

## Final Recommendation

Do first:

1. Lock the current guarantees with tests and docs.
2. Unify metadata parsing so `/api/metadata` and SQLite indexing produce the same normalized fields.
3. Add a bounded local metadata indexer that is fed by scan but never blocks scan.
4. Add a batched SQLite writer and `/api/index/status`.
5. [Phase 2A] Add preview/derivative layer to lightbox: `/api/preview` (1440px) as PhotoSwipe main src, original `/api/image` only on zoom/fullscreen/download/animated. Keep loading policy strict in tests (`lightbox-loading-policy.spec.ts`).

Do next:

1. [Phase 2B] Add fielded search: first-class fields for all lightbox-visible metadata (prompt:, negative:, seed:, steps:, cfg:, sampler:, scheduler:, model:, model_hash:, lora:, path:, folder:, size:, width:, height:, aspect_ratio:, source:/tool:, date:, generation_time:, clip_skip:, hires_*, denoising_strength:, vae:, ensd:, aesthetic_score:), generic `param:<key>:`, `advanced:<key>:`, and `raw:` fallback for non-first-class keys.
2. [Phase 2B] Add DB-first warm metadata reads for the lightbox panel (read from SQLite, no re-parse when fresh).
3. [Phase 3] Add warm indexed folder listing behind freshness checks and fallback.
4. [Phase 3] Add optional watcher/scheduled refresh.

Defer:

1. Optional local watcher/scheduled refresh until queue coalescing and status are proven.
2. Prompt grouping/usage stats until background indexing coverage is high.
3. ComfyUI node/property search until DB bloat and query performance are benchmarked.
4. Time-bucket/timeline APIs until gallery-repo has a real product requirement for timeline browsing.
5. Content checksums until there is an explicit duplicate/move-detection feature that can run off the hot path.

Reject:

1. Do not make PostgreSQL, Redis, or BullMQ default requirements.
2. Do not parse metadata or open images with PIL inside `/api/scan`.
3. Do not copy DT's synchronous viewer metadata reparse.
4. Do not show thumbnail (512px) as the lightbox main source — preview (1440px) is the correct derivative for lightbox display.
5. Do not add OCR/CLIP/ML smart search as a default feature.
6. Do not import Immich's multi-user, sharing, backup, or storage-template model.
7. Do not add Stealth PNG pixel scanning to normal scan, metadata, or lightbox paths.

The opinionated answer:

```text
Do not become Immich.
Do not become DiffusionToolkit.

Become gallery-repo with:
- fast scan
- derivative-first lightbox (preview 1440 main src, original on zoom/fullscreen)
- local background metadata indexer
- batched SQLite writes
- DB-first warm metadata
- simple optional fielded search
- observable perf gates
```

Phases 0, 1, 2A, 2B, and 3 are complete as of June 2026. Phase 2A (derivative-first lightbox) was added mid-stream per user request and successfully implemented. Phase 2B (fielded search, DB-first metadata) and Phase 3 (warm folder listing, optional scheduled refresh, optional watcher, richer facets) are complete. Every later improvement builds on the foundations already laid: a single parser truth, bounded background metadata work, batched writes, visible index status, the derivative-first lightbox, and warm indexed folder listings.
