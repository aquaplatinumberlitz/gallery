# Gallery Repo Evolution Master Plan

Last reviewed: 2026-06-09

Sources: DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md, DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md, DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md, IMMICH_PIPELINE_AUDIT.md, MEDIA_PIPELINE_COMPARISON.md, ARCHITECTURE.md, PERFORMANCE_TESTING.md, METADATA_PARSING.md, plus current implementation inspection.

---

## SECTION B — Executive Summary

### Core Strategy

gallery-repo should NOT become Immich.
gallery-repo should NOT become DiffusionToolkit.
gallery-repo should preserve its fast local web hot path, then selectively add a small local background indexing layer inspired by DT/Immich.

### Key Answers

| Question | Answer |
|---|---|
| Best current architecture to preserve | `/api/scan` direct filesystem listing with batch SQLite dimension lookup, no PIL/metadata parsing, lazy thumbnails, PhotoSwipe `/api/image` main source, and TanStack Query server-state ownership |
| Best DT idea to borrow | Bounded background metadata indexing queue with batched SQLite writes, feeding a unified parser core |
| Best Immich idea to borrow | DB-first viewer metadata reads when warm, compact list DTOs, derivative status rows, and next/previous preloading (thumbnails only, never full originals) |
| Biggest current gallery-repo weakness | No background metadata indexing — warm cache depends on users opening thumbnails or metadata manually |
| Biggest danger if we copy DT blindly | Synchronous viewer reparse-before-preview would stall lightbox; full-file hash/read on scan would destroy cold-folder latencies |
| Biggest danger if we copy Immich blindly | PostgreSQL/Redis/BullMQ becoming default would explode deployment complexity; preview replacing `/api/image` as lightbox main source would violate the hard-won original-image guarantee |
| Recommended direction for the next 3 implementation phases | Phase 1: unified parser + background indexer + batched SQLite + index status. Phase 2: fielded search + derivative status + neighbor prefetch. Phase 3: warm indexed folder listing + optional watcher + richer metadata facets |

---

## SECTION C — Non-Negotiable Design Rules

### Rule 1: `/api/scan` must never parse metadata or open images with PIL

**Why:** `/api/scan` is the folder-open hot path. Opening images during scan would add per-image decode time (tens to hundreds of ms each), destroying the current sub-second folder-open experience for dozens of images.

**What breaks if violated:** Album-open perf test fails. Cold cache folders take seconds instead of milliseconds. The entire pipeline design assumption — that scan is a cheap directory listing — collapses.

**Which previous bug/regression it prevents:** The current architecture explicitly chose direct filesystem listing over image probing. Reverting that would regress to a world where every large PNG adds 50-200ms of PIL parsing to the scan response.

**Which perf test should guard it:** `frontend/tests/perf/album-open.perf.spec.ts` already enforces scan budget. Add a code-level test or assertion that verifies no `Image.open()` call from `scan.py` call chain during `/api/scan`.

### Rule 2: `/api/scan` may only read cached dimensions/metadata if already available and validated by path + mtime + size

**Why:** Cached dimensions are free reads from SQLite. The batch lookup (`get_cached_dimensions_for_files()`) is a single SQL query with mtime+size validation — fast and safe. Dimensions from any other source would require image opening.

**What breaks if violated:** Stale dimensions (wrong aspect ratio in lightbox) or slow scan (if fallback triggers image opens).

**Which previous bug/regression it prevents:** Dimensions stored during thumbnail generation persist correctly only when revalidated against current file state. Bypassing mtime+size validation produces wrong dimensions after image edits or replacements.

**Which perf test should guard it:** The existing album-open perf test, plus a code-path assertion that the only source of dimensions in scan is `get_cached_dimensions_for_files()`.

### Rule 3: `/api/thumbnail` can open images because it is already the image-open path

**Why:** Thumbnail generation requires reading the original image. This is an explicit, lazy action triggered by the browser requesting a specific thumbnail. It is acceptable to spend CPU/disk here because the user directly requests the visual output.

**What breaks if violated:** If thumbnail generation were prohibited from opening images, thumbnails could never be generated. The rule is not "don't open images anywhere" — it's "don't open images on the scan hot path."

**Which previous bug/regression it prevents:** None directly. This rule clarifies that thumbnail is the designated image-open boundary — it is where dimensions and format data naturally enter the cache.

**Which perf test should guard it:** Thumbnail p95 budget in album-open test.

### Rule 4: `/api/metadata` can parse original files on demand, but should be cache-backed and coalesced

**Why:** Parsing metadata from original files is expensive (PIL open + PNG text chunk read + regex parsing). The current design already has in-memory LRU cache, in-flight coalescing, and SQLite persistence. Background indexing should eventually make on-demand parsing rare for warm folders.

**What breaks if violated:** Every metadata panel open would have unbounded parsing latency. Multiple concurrent lightbox opens hitting the same file would duplicate parse work. The current coalescing and LRU cache prevent both problems.

**Which previous bug/regression it prevents:** Duplicate in-flight parse requests for the same file. The `_metadata_inflight` dict + `Future` pattern coalesces concurrent callers onto a single parse.

**Which perf test should guard it:** Metadata parse p95 metrics; backend unit tests for coalescing behavior.

### Rule 5: Background indexing must never block folder open

**Why:** The entire architecture treats `/api/scan` as the hot path. Background work (file_index updates, metadata parsing, thumbnail warming) runs via `BackgroundTasks` and must not gate the scan response.

**What breaks if violated:** Folder open becomes serial — the UI waits for all background indexing to finish. This would violate the current design contract and break the album-open perf test.

**Which previous bug/regression it prevents:** The current `index_files_from_scan` and `index_directory_tree` calls are `background_tasks.add_task(...)` — non-blocking. Any new indexer must maintain that contract.

**Which perf test should guard it:** Album-open perf test. The scan request must return its response before background tasks complete.

### Rule 6: PhotoSwipe main `src` must remain `/api/image` unless product requirements change

**Why:** The lightbox perf test explicitly asserts `srcIsFullImage === true` and `usedFullImageEndpoint === true`. This is a deliberate design choice: gallery-repo displays original images in the lightbox, not preview derivatives. Immich's preview-first approach is correct for its photo-server use case but violates gallery-repo's intent.

**What breaks if violated:** The lightbox perf test fails on `expect(srcIsFullImage).toBe(true)`. Users see derivative/preview quality instead of originals, and the product guarantee changes silently.

**Which previous bug/regression it prevents:** This test was introduced to prevent PhotoSwipe quietly switching to a low-res source. A regression would reintroduce the bug where the lightbox showed thumbnails instead of full images.

**Which perf test should guard it:** `frontend/tests/perf/lightbox.perf.spec.ts` — specifically the `srcIsFullImage` and `usedFullImageEndpoint` assertions.

### Rule 7: Thumbnail/preview must be placeholder/prefetch/derivative only, not a silent replacement for original image

**Why:** The design goal is fidelity first, progressive enhancement second. Thumbnails provide `msrc` placeholders and dimension resolution. They must not become the authoritative image source.

**What breaks if violated:** Same as Rule 6 — the lightbox displays derivatives instead of originals.

**Which previous bug/regression it prevents:** The PhotoSwipe slide showing a thumbnail-sized image because the `src` was accidentally set to `/api/thumbnail` instead of `/api/image`.

**Which perf test should guard it:** Same as Rule 6.

### Rule 8: Album-open and lightbox perf tests are hard gates

**Why:** These are the two most performance-critical user interactions. Regressing either would degrade the core experience for every user.

**What breaks if violated:** Performance regressions go undetected. Hot paths erode over time.

**Which previous bug/regression it prevents:** Ensures future features or refactors do not silently add work to these paths.

**Which perf test should guard it:** `album-open.perf.spec.ts` and `lightbox.perf.spec.ts`. Both must pass in CI before merge.

### Rule 9: SQLite remains the default database; PostgreSQL/Redis/BullMQ must not become default requirements

**Why:** gallery-repo is a local-first web app. SQLite handles the metadata cache, file index, and FTS5 search with zero external daemons. PostgreSQL + Redis would increase the deployment burden 10x for a use case that SQLite handles well.

**What breaks if violated:** Installation complexity explodes. Local users who just want to browse folders need to run a database server and a queue server. The project loses its "pip install + npm install" simplicity.

**Which previous bug/regression it prevents:** None yet — this is a forward-looking constraint. Immich's full stack (PostgreSQL + Redis + BullMQ + ML services) is appropriate for a multi-user photo server but inappropriate for a local folder browser.

**Which perf test should guard it:** Startup test — the backend must start with only SQLite available.

### Rule 10: Search must remain simple for normal text, with fielded search added as an extension, not a replacement

**Why:** The current FTS5 + trigram search is fast, predictable, and handles plain text queries well. Fielded search (`seed:`, `model:`, etc.) should add structured filtering on top of the existing FTS engine, not replace it.

**What breaks if violated:** Plain text queries break or become significantly slower. Users who just type "cat" expect prompt/filename search to work as it does now.

**Which previous bug/regression it prevents:** Over-engineering the query parser to the point where basic FTS fallback stops working.

**Which perf test should guard it:** Search query tests with plain text, CJK text, fielded filters, and mixed queries. The FTS/LIKE fallback path must still work for unrecognized input.

---

## SECTION D — Decision Matrix: Borrow / Adapt / Reject

### From DiffusionToolkit

| Idea | Source | Decision | Why | Advantages | Disadvantages | Risk | Complexity | Priority |
|---|---|---|---|---|---|---|---|---|
| Bounded background metadata indexing queue | DT | **Adopt now** | Fills the biggest gallery-repo gap: warm metadata depends on user opening thumbnails/metadata | Warm search/viewer without blocking scan; coalesced jobs by path+mtime+size | CPU/disk contention with thumbnails; needs careful yielding | Medium | Medium | P1 |
| Batched SQLite writer | DT | **Adopt now** | Reduces write overhead for large folders; DT batches of ~33 rows; gallery-repo can use similar bounded batches | Fewer write transactions, less lock churn | Overly large batches increase lock hold time | Medium | Medium | P1 |
| Broad AI metadata parser coverage | DT | **Adapt later** | DT covers Fooocus, InvokeAI, Stealth PNG, Stable Diffusion sidecar text, WebP EXIF ComfyUI conventions | Richer metadata for more generators | Needs fixture tests first; format coverage without tests causes divergence | Medium | Medium-High | P2 |
| Sidecar metadata support | DT | **Adapt now (partial), later (extended)** | gallery-repo already has exact `.txt` sidecar. DT has prefix matching and directory caching. | Recover metadata from naming variants | Ambiguous prefix matching can attach wrong sidecar | Low-Medium | Low | P1/P2 |
| Fielded AI metadata search | DT | **Adapt now** | DT splits prompt text from structured predicates, then combines. gallery-repo can add this on top of existing FTS | Powerful filtering without replacing current search | Query parser complexity; malformed field tokens need clear behavior | Medium | Medium | P1 |
| ComfyUI node/property search | DT | **Research first** | DT indexes node properties separately for search. gallery-repo's lightbox ComfyUI parser is heuristic. | Precise search over ComfyUI workflows | Schema bloat; performance of node property scans | High | High | P2 |
| Prompt grouping/usage stats | DT | **Adapt later** | Group prompts by usage count, expose as separate endpoint | Library management view of most-used prompts | Not a lightbox/gallery feature; separate concern | Low | Medium | P2 |
| Optional local folder watcher | DT | **Adapt later** | DT uses `FileSystemWatcher`. gallery-repo can use `watchfiles`/`watchdog`, disabled by default | Warm cache stays fresh for stable folders | Platform-specific watcher behavior; missed events | High | Medium | P2 |
| Index status/progress | DT | **Adopt now** | DT reports scan progress; gallery-repo users cannot tell if cache is warming | Visible system state; debuggable failures | Misleading progress if indexing is opportunistic | Low-Medium | Medium | P1 |
| Thumbnail visible-area queue discipline | DT | **Research first** | DT queues thumbnails around visible viewport area | Reduces thumbnail storms on first load of large folders | gallery-repo already has browser lazy loading; backend queue is additional complexity | Low-Medium | Medium | P2 |
| Synchronous viewer metadata reparse | DT | **Reject** | DT reparses metadata before preview display | None for gallery-repo | Would block lightbox open; violates current async metadata design | High | N/A | N/A |
| Full-file hash/read for every image on scan | DT | **Reject** | DT reads and hashes whole files before parsing | None for gallery-repo | Massive cold-open latency; memory pressure for large AI images | V High | N/A | N/A |
| Stealth PNG pixel scan | DT | **Reject (defer to P3+)** | DT scans PNG pixel LSB for hidden parameters | Recover metadata from images with stripped text chunks | Expensive; should only run in explicit background rebuild, never hot path | High | High | P3 |
| Per-folder thumbnail SQLite cache | DT | **Reject** | DT stores thumbnails in per-folder `dt_thumbnails.db` | None over current persistent file cache | Weaker invalidation (no mtime key); harder to manage/debug | Medium | N/A | N/A |

### From Immich

| Idea | Source | Decision | Why | Advantages | Disadvantages | Risk | Complexity | Priority |
|---|---|---|---|---|---|---|---|---|
| DB-first viewer metadata | Immich | **Adopt now** | When cache is warm, metadata panel reads SQLite instead of parsing original file | Instant metadata display for warm folder | Stale metadata risk if cache invalidation wrong | Medium | Medium | P1 |
| Compact list/grid DTO | Immich | **Adopt now** | Timeline bucket vs asset detail separation; gallery-repo already does this with `/api/scan` minimal response | Keeps scan response small; full metadata on separate endpoint | Already largely in place | Low | Low | P0/P1 |
| Background job chain | Immich | **Adopt now (local SQLite version)** | Immich chains sidecar -> metadata -> thumbnail jobs. gallery-repo can do same with local queue | Orderly background processing; avoids redundant work | Queue bugs can cause stalled processing | Medium | Medium | P1 |
| Derivative status rows | Immich | **Adapt later** | Immich stores `asset_file` rows for thumbnails/previews; gallery-repo can add derivative table | Queryable thumbnail/preview readiness; no implicit disk cache state | Duplicate truth between disk cache and SQLite | Medium | Medium | P2 |
| Thumbnail/preview/original source policy | Immich | **Adapt (preview as placeholder only)** | Immich goes thumbnail -> preview -> original. gallery-repo must keep original as main src | Perceived faster load for huge images via higher quality placeholder | Risk of preview replacing original (Rule 6/7) | Medium | Medium | P2 |
| Next/previous viewer preloading | Immich | **Adopt now** | Immich preloads neighbor thumbnail and preview. gallery-repo already preloads thumbnail; can add metadata prefetch | Smoother next/prev transitions | Wasteful preloads during fast navigation; cap concurrency | Low | Low-Medium | P1 |
| Time-bucket/timeline API | Immich | **Reject (out of scope)** | Immich groups assets by month/day. gallery-repo is a folder browser, not a timeline photo manager | N/A for current product | Adds a second navigation model orthogonal to folder tree | Medium | High | N/A |
| PostgreSQL metadata filters | Immich | **Reject** | Immich uses PostgreSQL for powerful SQL filtering. gallery-repo uses SQLite | N/A | Would require PostgreSQL as dependency | V High | V High | N/A |
| Trigram/unaccent search | Immich | **Adapt (already exists)** | gallery-repo already has trigram FTS for CJK search and unicode61 for normal text. Immich uses PostgreSQL equivalents | CJK and Unicode search already work | None — this is already done | Low | Low | Done |
| OCR/CLIP smart search | Immich | **Reject (defer indefinitely)** | Immich has ML embedding/OCR search. gallery-repo is a local AI art browser, not a general photo library | Discovery for large libraries | ML dependencies, hardware requirements, ops complexity | V High | V High | N/A |
| Asset checksum/change detection | Immich | **Adapt (keep path+mtime+size)** | gallery-repo already validates by path+mtime+size. Immich uses path-derived SHA1 for external assets | Fast invalidation | Content hash would require full file reads | Low | Low | Done |
| External library scan model | Immich | **Reject** | Immich has a persistent external library scan model with scheduled scans. gallery-repo is ad hoc folder browsing | N/A for current product | Adds persistent library state management orthogonal to folder browsing | High | High | N/A |
| Optional watcher/scheduled scan | Immich | **Adapt later** | Immich supports chokidar watcher and scheduled scan. gallery-repo can add optional watcher | Warm cache stays current | Watcher complexity and platform differences | High | Medium | P2 |
| Queue status/admin endpoint | Immich | **Adapt now** | Immich exposes queue/job status. gallery-repo needs `/api/index/status` | Visible indexing progress | Misleading status if queue is opportunistic | Low-Medium | Low-Medium | P1 |
| Multi-user/album/sharing model | Immich | **Reject** | Immich has full multi-user with permissions, sharing, storage templates. gallery-repo is local and single-user | N/A | Massive scope explosion | V High | V High | N/A |
| Redis/BullMQ full stack | Immich | **Reject** | Immich uses Redis + BullMQ for distributed workers. gallery-repo uses in-process background tasks + SQLite | N/A | Deployment complexity increases 10x | V High | V High | N/A |

---

## SECTION E — Root-Cause Driven Improvement Plan

### E1: Metadata warm cache depends on user actions

**Current gallery-repo problem:** Metadata must be warmed by user explicitly opening thumbnails (via `/api/thumbnail`) or opening the lightbox metadata panel (via `/api/metadata`). Until then, search results and dimensions are incomplete.

**Root cause:** No background metadata indexing. `/api/scan` schedules `index_directory_tree(include_metadata=False)`, so file_index rows exist, but the `image_metadata` table (which holds prompt, model, sampler, seed, etc.) is only populated by on-demand `/api/metadata` or dimension-only `upsert_image_dimensions` from `/api/thumbnail`.

**Evidence from current docs/code:**
- `scan.py` line 180: `background_tasks.add_task(index_directory_tree, target, False)` — explicit `False` means no metadata indexing
- `ARCHITECTURE.md` line 82: "Background indexing: Directory tree index runs with include_metadata=False during scan"
- `PERFORMANCE_TESTING.md` line 178: "Background indexing: ... full metadata (prompt, models) is only indexed when images are actually opened in the lightbox or thumbnailed"

**Idea borrowed from DT/Immich:** DT's bounded background metadata scanner with 2 workers and batched DB writes. Immich's background job chain (scan -> sidecar check -> metadata extraction).

**Why this is the correct adaptation:** A small in-process queue (1 worker by default) fed by files discovered during `/api/scan`, throttled to avoid CPU/disk contention with interactive requests. Each job wraps `extract_metadata(path)` (not the richer `/api/metadata` parse) and upserts via `upsert_metadata_result`.

**Why not copy the original design exactly:** DT uses full-file read + hash before parse (too expensive for cold web). Immich uses BullMQ + Redis (too heavy). Both process all files at import time (eager). gallery-repo should index opportunistically: files seen during scan, then visible thumbnail paths.

**Expected benefit:** After one pass through a folder, search returns prompt/model/sampler matches, metadata panels show cached data immediately, and dimensions are available for layout.

**Trade-off:** CPU/disk IO during and after folder open. The indexer must yield to the request hot path.

**Failure mode:** Indexer steals CPU from thumbnail generation, causing slow thumbnail load. Mitigation: single worker, bounded concurrency, low I/O priority if platform supports it.

**How to test:** Queue coalescing tests (same file re-enqueued should skip), stale invalidation tests (file changed after indexing should re-index), index status endpoint tests, album-open perf test with background indexer active.

### E2: `/api/scan` enumerates and sorts all images before pagination

**Current gallery-repo problem:** For large folders (5000+ images), the entire directory is listed via `os.scandir`, filtered, stat'd, sorted, then sliced into pages. Every page request repeats the full enumeration (not full sort — list is already sorted once).

**Root cause:** `scan_directory` collects all image entries into a list, sorts them, then pagination slices that list. There is no indexed folder listing path — every scan is a full directory walk.

**Evidence from current docs/code:**
- `scan.py` line 144: `images.sort(key=lambda x: natural_sort_key(x.name))` — sort happens before pagination
- `scan.py` line 168-173: pagination slices from already-sorted list
- `DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md` line 157: "gallery-repo still enumerates and sorts all images in a directory before returning a page"
- `MEDIA_PIPELINE_COMPARISON.md` line 111: "Scan/sort still walks all files; metadata remains lazy"

**Idea borrowed from DT/Immich:** DT's SQLite-backed search page with paging. Immich's timeline bucket API that reads compact arrays from indexed DB rows.

**Why this is the correct adaptation:** For warm folders, `/api/scan` should be able to fall back to `file_index` rows sorted by mtime/name and paginated directly in SQLite. Cold folders (unindexed or just discovered) keep the current direct scan path.

**Why not copy the original design exactly:** Immich's timeline doesn't map to folder browsing. DT's full DB search page would lose the direct-filesystem freshness guarantee. gallery-repo should keep filesystem scan as the authoritative source and use indexed listing as an acceleration only when proven fresh.

**Expected benefit:** 5000-image warm folder first page drops from seconds (full walk) to 300-500ms (SQLite query). Cold folders unaffected.

**Trade-off:** Stale index risk. If the index is outdated, the user sees old listings or missing files. Mitigation: always validate returned index rows against filesystem stat before returning; degrade to full scan on mismatch.

**Failure mode:** Index shows files that were deleted externally. Mitigation: stale file detection during scan/serve should mark them and trigger background cleanup.

**How to test:** Large-folder warm/cold benchmark. File added/deleted externally should reflect on next scan. Perf budget: 5000-image warm first page <= 500ms on target hardware.

### E3: Search lacks fielded metadata query syntax

**Current gallery-repo problem:** Users cannot search by specific metadata fields like `seed:`, `model:`, `sampler:`, `cfg:`, `negative:`, `size:`. All searches are full-text across prompt, negative_prompt, model, sampler, and raw_metadata_text.

**Root cause:** The search endpoint (`/api/search` and `/api/search-metadata`) uses FTS5 unicode61/trigram tokenizers. There's no query parser that strips structured field tokens from the query string before sending remaining text to FTS.

**Evidence from current docs/code:**
- `metadata_store.py` line 29: `PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")`
- `DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md` line 55: "No fielded metadata query language"
- `DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md` line 192: "P1: Split query into residual text plus structured facets"

**Idea borrowed from DT/Immich:** DT's `QueryBuilder.ParseParameters()` that strips recognized field tokens and builds SQL predicates from them. The remaining text stays in the existing FTS pipeline.

**Why this is the correct adaptation:** Keep FTS5 as the default prompt engine. Add a query parser that recognizes `field:value` tokens with quoted-value support, removes them from the text query, and adds SQL `WHERE` clauses to filter `image_metadata` columns. Combine prompt FTS results with field filters via INTERSECT or AND.

**Why not copy the original design exactly:** DT uses comma-separated AND logic and prompt-first syntax. gallery-repo should support field tokens anywhere in the query when values are quoted or unambiguous. DT's `%LIKE%` as primary path is not needed — gallery-repo already has FTS5.

**Expected benefit:** Precise search by model, seed, sampler, CFG, dimensions. Users can find all images from a specific model within a specific CFG range.

**Trade-off:** Query parser complexity. Malformed field tokens (e.g., `seed:abc` where abc is not numeric) need clear behavior — ignore as text or error? Prefer ignore-as-text for now to avoid breaking current search.

**Failure mode:** Field filter parsing breaks plain text search. Mitigation: parser must always pass through unrecognized text to FTS. Tests for plain text, mixed, and malformed queries.

**How to test:** Backend query parser tests: plain text, CJK text, field filters (`seed:123 steps:30 model:"Realistic"`), malformed filters (`seed:abc`), scope filtering with field filters, fallback behavior when FTS fails.

### E4: Metadata parser coverage can be improved

**Current gallery-repo problem:** Two parser stacks exist (`metadata_parse.py` for the API and `metadata_extract.py` for SQLite indexing). The indexing parser has less format coverage (no SwarmUI, NovelAI, EasyDiffusion; limited ComfyUI). Coverage gaps include Fooocus, InvokeAI, Stable Diffusion sidecar text format, WebP EXIF ComfyUI conventions, and Stealth PNG.

**Root cause:** The parser was built incrementally. `/api/metadata` parser got richer format support while the SQLite index path stayed with a minimal subset. No fixture test suite exists, making format additions risky.

**Evidence from current docs/code:**
- `DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md` line 131: "Two parser stacks"
- `metadata_parse.py`: has `_parse_novelai_metadata()`, `_parse_easydiffusion_metadata()`, ComfyUI node resolver
- `metadata_extract.py`: has only `parse_a1111_parameters()`, simple ComfyUI text extraction, no SwarmUI/NovelAI/EasyDiffusion
- `DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md` line 175: "No parser fixture suite"

**Idea borrowed from DT/Immich:** DT's single `Metadata.ReadFromFile()` entry point with format-specific adapters. Immich's separation of metadata extraction from metadata serving.

**Why this is the correct adaptation:** Introduce a shared parser core module that both `/api/metadata` and `metadata_store.index_image()` route through. The core module extracts raw candidates from file containers (PNG chunks, EXIF, sidecar), then dispatches to format-specific adapters. The API layer shapes the output for the frontend; the index layer reduces it to searchable fields.

**Why not copy the original design exactly:** DT's parser requires reading the whole file and hashing it — this is unnecessary for gallery-repo's mtime+size validation model. DT's parser is monolithic; gallery-repo should keep the candidate pipeline separate from the format adapters.

**Expected benefit:** Search index and lightbox panel show the same metadata from the same parser. Adding a format adapter benefits both paths simultaneously. One bug fix in the parser fixes both.

**Trade-off:** Unification requires careful extraction without regressing current behavior. Both paths must produce equivalent results for already-supported formats.

**Failure mode:** Unification changes metadata output shape for existing formats, breaking frontend expectations. Mitigation: fixture tests before unification, then migration, then new formats.

**How to test:** Golden fixture tests for each supported format (A1111, SwarmUI, ComfyUI, NovelAI, EasyDiffusion, EXIF UserComment, sidecar text). Compare API output vs index output for the same fixture. Verify backward compatibility of `/api/metadata` response shape.

### E5: Lightbox next/prev could preload more agressively

**Current gallery-repo problem:** The lightbox store preloads neighbor thumbnails via `preloadImage(path)` (which creates an `Image()` with thumbnail URL). But metadata and dimensions for neighbors are not prefetched. When the user navigates to the next image, metadata is fetched on-demand, and dimensions may need resolution.

**Root cause:** The neighbor preload path only handles thumbnail images. The dimension resolver runs on slide change, and metadata queries are reactive to the current path.

**Evidence from current docs/code:**
- `lightbox.ts` line 74-80: `preloadNeighbors()` calls `preloadImage(item.path)` for thumbnails only
- `usePhotoSwipe.ts` line 60-62: `bestKnownDimensions` checks scan -> thumbnail -> cached metadata, but cached metadata is not warmed by preload
- `IMMICH_PIPELINE_AUDIT.md` line 681: "P1: Prefetch next/previous metadata and medium thumbnails in lightbox"

**Idea borrowed from DT/Immich:** Immich's `PreloadManager` preloads next/previous thumbnail and preview. gallery-repo can extend to prefetch metadata queries and higher-quality thumbnail placeholders.

**Why this is the correct adaptation:** Background prefetch metadata queries via TanStack Query's `queryClient.prefetchQuery()`. Preload a medium-resolution thumbnail for the likely next image. Keep current guarantee: never preload full `/api/image` originals.

**Why not copy the original design exactly:** Immich preloads preview derivatives (1440px JPEG). gallery-repo should stick to thumbnail + metadata prefetch. Preloading full-resolution or near-full images wastes bandwidth on fast navigation.

**Expected benefit:** Smoother next/prev transitions — metadata panel updates faster, dimensions are resolved before slide display.

**Trade-off:** Extra network/disk requests during lightbox navigation. Mitigation: cap concurrent preloads to 2 (next and previous), cancel in-flight preloads on rapid navigation.

**Failure mode:** Prefetch causes bandwidth spikes or fills the browser cache with unused images. Mitigation: concurrent preload cap; cancel on rapid slide changes.

**How to test:** Extend lightbox perf test to measure transition time with prefetch. Assert no full-original requests during preload. Assert metadata panel data arrival time improves.

### E6: No visible index status/progress

**Current gallery-repo problem:** Users cannot tell whether the metadata/search cache is warming, complete, or stalled. If they open a folder and search doesn't return results, they don't know if the indexer is running, finished, or failed.

**Root cause:** Background indexing runs silently via FastAPI `BackgroundTasks`. There's no status endpoint or frontend status UI.

**Evidence from current docs/code:**
- `scan.py` lines 178-180: background tasks fire silently
- `IMMICH_PIPELINE_AUDIT.md` line 708: "P1: Add index status/progress endpoint"

**Idea borrowed from DT/Immich:** DT reports scan progress to UI. Immich has queue/job status endpoints (`/api/queue`). gallery-repo can add `/api/index/status` with counters.

**Why this is the correct adaptation:** A simple status endpoint backed by SQLite counters: queued, running, done, error per folder or global. Frontend can show an unobtrusive indicator (not a noisy toast).

**Why not copy the original design exactly:** Immich has a full BullMQ admin panel with pause/resume/empty. gallery-repo needs read-only status for local use. DT's progress model is coupled to its scanning service; gallery-repo should keep it lightweight.

**Expected benefit:** Users understand when indexing is happening and whether search will improve.

**Trade-off:** Adding visible system state. Mitigation: status UI must be unobtrusive — a subtle progress bar or badge, not a blocking overlay or persistent toast.

**Failure mode:** Status UI becomes noisy or distracting, akin to the previous toast bug. Mitigation: status shows only while relevant (first cold folder visit), auto-dismisses when complete, never blocks interaction.

**How to test:** Status endpoint returns queued/running/done/error. Frontend status component renders without blocking scroll or clicks. Perf budget: status endpoint p95 <= 50ms warm.

### E7: SQLite writes inefficient under large background indexing

**Current gallery-repo problem:** Each `index_file()` and `upsert_metadata_result()` call acquires the global `_DB_LOCK`, opens a new connection, executes a single `INSERT ... ON CONFLICT DO UPDATE`, and closes. Under background indexing of hundreds of files, this produces many small transactions.

**Root cause:** No write batching. Each file index and metadata upsert is a separate transaction.

**Evidence from current docs/code:**
- `metadata_store.py` line 30: `_DB_LOCK = threading.RLock()`
- `metadata_store.py` line 445-492: `index_file()` does one insert per call
- `metadata_store.py` line 358-432: `upsert_metadata_result()` does one upsert per call
- `DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md` line 110: "Database writes are batched around 33 records"

**Idea borrowed from DT/Immich:** DT's `DatabaseWriterService` batches writes. gallery-repo can internally buffer results and flush in batches.

**Why this is the correct adaptation:** A batch writer that accumulates index upserts and flushes in chunks of ~50 rows. Uses `executemany` or single-transaction batch inserts. The batch writer is used by the background indexer; direct callers (individual `/api/metadata` or `/api/thumbnail`) still do single upserts.

**Why not copy the original design exactly:** DT's batch writer is a service with its own thread. gallery-repo can embed batching in the background index queue — the queue drains into the batch writer.

**Expected benefit:** Fewer SQLite write transactions, less locking overhead, faster indexing throughput.

**Trade-off:** Delay between parse and persistence (rows sit in buffer until flush). Mitigation: flush interval (e.g., 500ms) and flush-on-queue-drain.

**Failure mode:** Batch transaction too large, holding write lock for too long. Mitigation: bounded batch size (50-100 rows per transaction).

**How to test:** Large-folder indexing throughput test. SQLite write latency before/after. Verify no data loss on crash (batch flush guarantees).

### E8: No formal derivative readiness/status

**Current gallery-repo problem:** There's no way to query whether a thumbnail exists for a file without either checking the filesystem cache or attempting a thumbnail request. Dimensions are cached in `image_metadata` but thumbnail file readiness is not recorded.

**Root cause:** Thumbnail cache is purely filesystem-based (`_thumbnail_file_dir` + `_thumbnail_disk_cache`). No SQLite record tracks which thumbnails exist.

**Evidence from current docs/code:**
- `thumbnails.py` line 19-20: disk cache and file directory
- `thumbnails.py` line 25-28: cache key from path + mtime_ns + size + max_size + quality
- `IMMICH_PIPELINE_AUDIT.md` line 623: "P1/P2: Add optional SQLite derivative table"

**Idea borrowed from DT/Immich:** Immich stores `asset_file` rows for each derivative. DT stores thumbnails per-folder in SQLite. gallery-repo can add a `thumbnail_cache` table keyed by path+mtime+size+max_size.

**Why this is the correct adaptation:** Enable the scan response to include a `has_thumbnail` boolean (cheap SQLite lookup alongside the dimension batch query). Enable background thumbnail warming to target files without thumbnails.

**Why not copy the original design exactly:** Immich's derivative table is part of a broader storage-template system. gallery-repo just needs a quick readiness flag. DT's per-folder thumbnail DB is a different architecture.

**Expected benefit:** Scan can report thumbnail status without filesystem checks. Background indexer can prioritize thumbnail warming for visible files.

**Trade-off:** Duplicate source of truth between disk cache and SQLite row. Mitigation: make the thumbnail table the "observed" state — populate it when a thumbnail is generated or verified to exist. Missing row means "unknown/not present."

**Failure mode:** Stale derivative rows (thumbnail deleted, row remains). Mitigation: invalidate on mtime+size mismatch; rebuild on cache cleanup.

**How to test:** Derivative readiness query for scan batch. Thumbnail warming targets files without rows. Stale row cleanup works.

### E9: No optional watcher/scheduled refresh

**Current gallery-repo problem:** For stable local folders that the user browses repeatedly, there's no automatic cache refresh when files change externally. The user must re-open folders to re-scan.

**Root cause:** gallery-repo is built for ad-hoc folder browsing, not managed libraries. No watcher capability exists.

**Evidence from current docs/code:**
- `IMMICH_PIPELINE_AUDIT.md` line 241: "Optional watcher/scheduled scan"
- `MEDIA_PIPELINE_COMPARISON.md` line 178: "P2: Optional watcher"

**Idea borrowed from DT/Immich:** DT uses `FileSystemWatcher`; Immich uses optional `chokidar` watcher with scheduled scan as default.

**Why this is the correct adaptation:** Optional, disabled by default. Use `watchfiles` or `watchdog` library. When enabled, watch the current `GALLERY_ROOT` (or a configured watch set) and re-index changed files on create/modify and clean up on delete.

**Why not copy the original design exactly:** Immich's watcher is part of the managed library model with explicit add/remove semantics. gallery-repo should watch the root and its subdirectories passively. DT's watcher assumes a desktop app running continuously.

**Expected benefit:** Browsing a frequently-updated folder never requires manual rescan. Search results stay current after external file changes.

**Trade-off:** Watcher adds a persistent background thread. Platform differences (inotify limits on Linux, FSEvents latency on macOS, ReadDirectoryChangesW on Windows). Mitigation: disabled by default; clear documentation about known limitations.

**Failure mode:** Watcher misses events (filesystem event queues overflow). Mitigation: watcher fires a validation scan after batch changes; periodic full recheck.

**How to test:** Integration tests behind opt-in flag. File create/modify/delete while watcher is active. Verify index updates within reasonable time window.

### E10: Large warm libraries can't match DB-first timeline/search

**Current gallery-repo problem:** Even with warm cache, `/api/scan` walks the filesystem for every folder open. For very large folders (10k+ images), each scan is expensive even though all metadata is cached. The user experience is slower than Immich's DB-backed timeline.

**Root cause:** gallery-repo uses filesystem as the authoritative listing source. There's no indexed folder listing path.

**Evidence from current docs/code:**
- `scan.py` line 45-149: `scan_directory` always uses `os.scandir`
- `MEDIA_PIPELINE_COMPARISON.md` line 27: "Best for large photo library: Immich"
- `DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md` line 157: "Subsequent visit: still rescans/sorts directory"

**Idea borrowed from DT/Immich:** DT queries SQLite with paging for search results. Immich uses timeline buckets from PostgreSQL. gallery-repo can add an indexed folder listing path that queries `file_index` for listings when the index is proven fresh.

**Why this is the correct adaptation:** Add a `/api/scan` fast path: if the folder's `file_index` entries have been validated recently (within a freshness window), return paginated results from `file_index` + `image_metadata` join. On stale validation, fall back to direct filesystem scan. Both paths return the same `FileNode` shape.

**Why not copy the original design exactly:** Immich's timeline API (bucket counts, month views) doesn't map to folder browsing. gallery-repo needs indexed listing within folder scope, not time-based grouping.

**Expected benefit:** Warm 10k-image folder opens in 300-500ms instead of seconds.

**Trade-off:** Index freshness risk — files added/deleted externally won't appear until the next validation scan. Mitigation: make the freshness window configurable; always check mtime of the folder itself as a quick invalidation signal.

**Failure mode:** Index shows outdated listing. Mitigation: folder mtime check is one stat call and catches bulk changes; individual file stat validation catches per-file changes.

**How to test:** Warm folder open benchmark with 5k and 10k folders. Stale detection: add/delete files externally, verify next scan returns correct listing. Perf budget: 5000-image warm first page <= 500ms.

---

## SECTION F — Phased Roadmap

### Phase 0 — Preserve and Lock Current Guarantees

**Goal:** Freeze current performance contracts, add regression guards, prevent accidental violations of design rules.

**Why now:** Before adding any features, the existing hot paths must be provably locked. Every subsequent phase must pass these gates.

**Why this order:** Safety first. New features built on unstable guarantees create fragile systems.

**Borrowed from:** Internal architecture docs and perf tests.

**Current problem solved:** Ensures future work doesn't silently degrade current performance.

**Files likely affected:** Perf tests, CI config, possibly scan.py validation assertions.

**Backend changes:**
- Add code-level test/inspection that verifies `scan.py` never calls `Image.open()` or any metadata parsing function
- Add backend unit test for `/api/scan` dimension source assertion (only `get_cached_dimensions_for_files`)
- Lock scan response schema with a comprehensive test

**Frontend changes:**
- Ensure lightbox `srcIsFullImage` assertion cannot be bypassed
- Lock TanStack Query key patterns

**DB/schema changes:** None.

**API changes:** None.

**Docs changes:**
- Document non-negotiable rules in ARCHITECTURE.md
- Add regression test checklist to PERFORMANCE_TESTING.md

**Tests to add/update:**
- `test_scan_never_opens_images.py`: inspect scan call chain
- `test_scan_dimensions_source.py`: assert only batch cache lookup
- `test_lightbox_src_is_image.py`: assert `/api/image` usage

**Perf budgets:**
- All existing budgets must pass
- No scan p95 regression tolerated

**Acceptance criteria:**
- All existing perf tests pass
- New regression guard tests pass
- Scan never opens images with PIL (provable by test)

**Rollback plan:** This phase is purely additive (tests), no rollback needed.

**Risk level:** Minimal — only adding tests and docs.

**What not to do:** Do not optimize scan yet. Do not change any hot-path logic. Only add guards.

### Phase 1 — Unified Parser + Background Indexer + Batched SQLite + Index Status

**Goal:** Introduce the core infrastructure that warms metadata/search cache without blocking the UI.

**Why now:** The biggest gap is warm metadata dependency on user actions. This is the prerequisite for Phase 2 (fielded search) and Phase 3 (indexed folder listing).

**Why this order:** Without indexed metadata, fielded search has nothing to query. Without a background indexer, large folders stay cold until manually browsed.

**Borrowed from:** DT (background indexer, batched writes), Immich (job-like processing chain).

**Current problem solved:** E1 (metadata warm cache), E6 (no index status), E7 (SQLite write inefficiency), partially E4 (parser coverage via unified core).

**Files likely affected:**
- `backend/metadata_parse.py` (extract common parser core)
- `backend/metadata_extract.py` (refactor to use common core)
- `backend/metadata_store.py` (add batch writer, index queue table, status queries)
- New: `backend/index_queue.py` (background queue worker)
- `backend/scan.py` (feed queue from scan, no behavior change to hot path)
- `backend/app.py` (register new router)
- New: `backend/test/test_parser_fixtures.py`
- New: `backend/test/test_index_queue.py`

**Backend changes:**

1. **Unified parser core:**
   - Extract `parse_metadata_candidates(path)` from `metadata_parse.py` — reads PNG chunks, EXIF, sidecar text without generator-specific parsing
   - Extract generator adapters from `metadata_parse.py` into `parsers/` subdirectory
   - Refactor `metadata_extract.py` to use the same candidate pipeline and adapters
   - Add parser fixture tests for all supported formats (A1111, SwarmUI, ComfyUI, NovelAI, EasyDiffusion, sidecar)

2. **Background indexer:**
   - Add `index_job` SQLite table: id, path, mtime, size, status (queued/running/done/error), error_text, created_at, updated_at
   - Add in-process queue: bounded `queue.Queue` with 1 worker thread
   - Worker: pops job, checks mtime+size still match filesystem, runs `extract_metadata()`, writes via batch writer
   - Feed sources: (a) files seen during `/api/scan` (queue their paths), (b) files whose thumbnails are generated (queue after thumbnail), (c) explicit rebuild command
   - Coalesce: if a job for same path+mtime+size is already queued/running, skip new enqueue
   - Yield: worker sleeps briefly between jobs (e.g., 50ms) to avoid starving request threads

3. **Batched SQLite writer:**
   - Accumulate metadata upserts in a buffer (list of tuples)
   - Flush in batches of 50 rows or every 500ms, whichever comes first
   - Single transaction per batch
   - Direct `/api/metadata` and `/api/thumbnail` calls still do single-row upserts

4. **Index status endpoint:**
   - `GET /api/index/status?path=...` — returns queued, running, done, error counts for that folder
   - Global status also available
   - Response includes `last_error` text for debugging

**Frontend changes:**
- No mandatory frontend changes in Phase 1
- Optional: subtle index status indicator (not blocking, not noisy)

**DB/schema changes:**
- New `index_job` table
- New batch writer tracked state (in-memory + SQLite insert)
- No changes to `image_metadata` or `file_index` schema

**API changes:**
- New: `GET /api/index/status`
- New: `POST /api/index/rebuild` (optional, for explicit rebuild)
- No changes to existing endpoints

**Docs changes:**
- Update ARCHITECTURE.md with indexer pipeline description
- Update PERFORMANCE_TESTING.md with indexer perf guidance

**Tests to add/update:**
- Parser fixture tests for each format
- Queue coalescing test (same file re-enqueued = skip)
- Stale invalidation test (file changed after index = re-index)
- Batch writer test (batch of 100, verify atomic transaction)
- Index status endpoint tests (counts match reality)
- Album-open perf test still passes with indexer active
- `test_scan_never_opens_images` still passes

**Perf budgets:**
- `/api/scan` p95 unchanged (within current budget)
- `/api/index/status` p95 <= 50ms warm
- Background worker CPU <= 1 core, yield to request hot path
- No regression to thumbnail p95

**Acceptance criteria:**
1. After opening a folder, background indexer processes all scanned images' metadata into SQLite
2. Search returns prompt matches for newly indexed images
3. Metadata panel shows cached data for indexed images without re-parsing
4. Index status shows accurate queue counts
5. Album-open perf test passes with indexer active
6. Lightbox perf test passes
7. All parser fixtures pass
8. `/api/metadata` response is backward-compatible

**Rollback plan:** Disable indexer via env var `BACKGROUND_INDEXER_ENABLED=0`. All existing paths unchanged.

**Risk level:** Medium. Background CPU/disk contention is the primary risk. Mitigated by single worker, job yielding, and ability to disable.

**What not to do:**
- Do not change how `/api/metadata` responds to the frontend
- Do not add fielded search in this phase (Phase 2)
- Do not add derivative table (Phase 2)
- Do not change `/api/scan` hot path behavior
- Do not index metadata during scan — index in background only

### Phase 2 — Fielded Search + Derivative Status + Neighbor Prefetch

**Goal:** Add structured metadata search, thumbnail readiness tracking, and improved lightbox responsiveness.

**Why now:** Phase 1 provides the metadata index that fielded search queries. Derivative status builds on existing thumbnail cache. Neighbor prefetch improves lightbox UX.

**Why this order:** Fielded search needs metadata in the DB (Phase 1 output). Derivative status and neighbor prefetch are independent but build on the improved warm-cache story.

**Borrowed from:** DT (fielded search), Immich (derivative status, neighbor preload).

**Current problem solved:** E3 (fielded search), E5 (lightbox preload), E8 (derivative status).

**Files likely affected:**
- New: `backend/search/query_parser.py` (field tokenizer and SQL builder)
- `backend/metadata_store.py` (add metadata column indexes for filter columns)
- `backend/search.py` (integrate fielded search into `/api/search`)
- `backend/metadata_store.py` (add `thumbnail_cache` table)
- `backend/thumbnails.py` (write to `thumbnail_cache` on generation)
- `frontend/src/stores/lightbox.ts` (extend preloadNeighbors)
- `frontend/src/composables/usePhotoSwipe.ts` (prefetch metadata for neighbors)
- `frontend/tests/perf/lightbox.perf.spec.ts` (extend transition test)

**Backend changes:**

1. **Fielded search:**
   - New query parser module: `parse_query(q: str) -> (text: str, predicates: list[SearchPredicate])`
   - Recognized fields: `seed:`, `steps:`, `cfg:`, `sampler:`, `model:`, `negative:`, `size:`
   - Quoted values supported: `model:"Euler A"`, `negative:"watermark, blurry"`
   - Wildcards: `seed:123*` maps to LIKE
   - Remaining text goes to existing FTS5 search
   - SQL builder combines FTS results with structured predicates via INTERSECT
   - Malformed field tokens pass through as text (no breaking change)
   - Scope filtering unchanged

2. **Derivative status rows:**
   - New `thumbnail_cache` table: path, mtime, size, max_size, file_path, generated_at
   - Write on thumbnail generation success
   - Read in batch alongside `get_cached_dimensions_for_files()`
   - Add `has_thumbnail` bool to scan response

3. **`/api/scan` response enrichment (optional, minimal):**
   - Add `has_thumbnail: bool` field to `FileNode` (from `thumbnail_cache` batch lookup)
   - No additional file I/O — it's a SQLite join

**Frontend changes:**

1. **Neighbor prefetch:**
   - `lightboxStore.preloadNeighbors()` additionally calls `queryClient.prefetchQuery()` for neighbor metadata
   - Preload a higher-quality thumbnail (1200px) for next image
   - Cancel in-flight prefetches on rapid navigation (debounce 300ms)
   - Cap concurrent preloads to 2
   - Never preload full `/api/image` original

2. **Fielded search UI (optional, minimal):**
   - No mandatory UI changes in Phase 2
   - Optional: search hints in search box placeholder
   - Search still works with plain text as before

**DB/schema changes:**
- New `thumbnail_cache` table
- Add indexes on `image_metadata.seed`, `image_metadata.steps`, `image_metadata.cfg_scale`, `image_metadata.model` for fielded search performance

**API changes:**
- `/api/search` gains fielded search capability (backward-compatible — plain text still works)
- `/api/scan` response gains optional `has_thumbnail` field
- No breaking API changes

**Docs changes:**
- Add fielded search syntax documentation
- Add thumbnail_cache schema documentation

**Tests to add/update:**
- Query parser unit tests: tokenization, quoted values, malformed input, plain text passthrough
- SQL predicate builder tests with in-memory SQLite
- Fielded search integration tests: `cat seed:123`, `model:"Realistic"`, mixed fields, scope filtering
- Derivative status tests: write on thumbnail, read in batch
- Lightbox prefetch tests: assert prefetch queries fire, assert no `/api/image` prefetch
- Existing perf tests still pass

**Perf budgets:**
- `/api/search` with fielded query p95 similar to plain text search
- `/api/scan` p95 unchanged (added `has_thumbnail` is a batch SQLite lookup)
- Lightbox transition budget improves or stays within current budget
- No extra full-original requests during preload

**Acceptance criteria:**
1. Model filter works with existing metadata
2. SEED filter works with existing metadata
3. Plain text search unchanged
4. Thumbnail status visible in scan response (optional)
5. Neighbor prefetch reduces metadata panel latency on next/prev
6. No `/api/image` prefetches during lightbox navigation
7. All perf tests pass

**Rollback plan:** Fielded search parser is a query pre-processing step — disable it and pass-through raw text if bugs found. Prefetch is client-side only, disable with flag. Derivative status is additive, no rollback needed.

**Risk level:** Low-Medium. Fielded search parser complexity is the main risk. Mitigated by extensive unit tests and passthrough-on-failure design.

**What not to do:**
- Do not replace FTS with raw SQL
- Do not add raw workflow search (P3)
- Do not add ComfyUI node property search (P3)
- Do not change scan hot path behavior

### Phase 3 — Warm Indexed Folder Listing + Optional Watcher + Richer Facets

**Goal:** Complete the warm-cache experience: indexed folder listing for large folders, optional file watcher for cache freshness, and richer metadata facets for advanced users.

**Why now:** Phases 1-2 provide the indexed metadata and status infrastructure. Phase 3 leverages it for the warm-folder acceleration and persistent freshness.

**Why this order:** Indexed listing needs the index (Phase 1) and the scanning mechanism (Phase 2). Watcher is only useful after the index exists and is trusted.

**Borrowed from:** DT (watcher, AI metadata schema depth), Immich (large-library listing performance, optional watcher).

**Current problem solved:** E2 (5000+ folder scan), E9 (watcher), E4 (broader parser coverage).

**Files likely affected:**
- `backend/scan.py` (add indexed fast path)
- `backend/metadata_store.py` (add folder freshness queries)
- New: `backend/watcher.py` (optional file watcher)
- `backend/metadata_parse.py` and `parsers/` (add Fooocus, InvokeAI, WebP EXIF adapters)
- `backend/metadata_extract.py` (wider format support via shared core)
- `backend/search.py` (optional richer facets)
- Frontend optional status/refresh UI

**Backend changes:**

1. **Indexed folder listing fast path:**
   - Before `scan_directory` walk, check if folder `file_index` entries match folder mtime
   - If matched: query `file_index` + `image_metadata` join for paginated results
   - If stale or missing: fall back to full `scan_directory` walk
   - Both paths return identical `FileNode` shape
   - Freshness window configurable via env var

2. **Optional file watcher:**
   - Library: `watchfiles` (lightweight, cross-platform)
   - Disabled by default; enable via `GALLERY_WATCH_ENABLED=1`
   - Watch `GALLERY_ROOT` and subdirectories for create/modify/delete events
   - On create/modify: queue re-index for affected file
   - On delete: remove from `file_index`, `image_metadata`, and `thumbnail_cache`
   - Batch events within a window (e.g., 1 second) to avoid index churn

3. **Broader parser coverage:**
   - Add Fooocus/RuinedFooocus/FooocusMRE adapters
   - Add InvokeAI adapters (legacy Dream command, sd-metadata JSON, invokeai_metadata)
   - Add Stable Diffusion text sidecar format adapter
   - Add WebP ComfyUI EXIF convention support (Make/Model fields)
   - Add `model_hash`, `tool`, `scheduler`, `lora_text` columns to `image_metadata`
   - All behind fixture tests

**Frontend changes:**
- No mandatory frontend changes
- Optional: watcher status indicator (passive — not noisy)
- Optional: richer metadata facets in search UI (advanced mode)

**DB/schema changes:**
- Add `model_hash`, `tool`, `scheduler`, `lora_text` columns to `image_metadata`
- Add migration for existing rows (populated on next re-index)
- Add `indexed_listing_fresh` column to `file_index` for freshness tracking

**API changes:**
- `/api/scan` may serve from index when fresh (transparent, same response shape)
- New: `POST /api/index/refresh?path=...` (explicit re-index trigger)
- No breaking API changes

**Docs changes:**
- Document watcher enablement and limitations
- Document indexed listing behavior and freshness guarantees
- Update parser format support matrix

**Tests to add/update:**
- Indexed listing vs direct scan comparison test (same results)
- Folder freshness invalidation test (mtime change triggers re-scan)
- Watcher integration test (file create/modify/delete)
- Watcher batch dedup test
- New parser format fixture tests
- Existing perf tests with indexed listing path and watcher active

**Perf budgets:**
- 5000-image warm scan <= 300-500ms via indexed path
- Watcher CPU overhead minimal when idle
- Cold scan p95 unchanged (index fallback to full scan)
- All existing budgets pass

**Acceptance criteria:**
1. Warm 5000-image folder opens in <= 500ms via indexed path
2. Adding/deleting files externally reflects in index within watcher batch window
3. Watcher does not interfere with normal gallery browsing
4. New parser formats produce correct metadata in fixtures
5. All Phase 0-2 acceptance criteria still met
6. All perf tests pass

**Rollback plan:** Disable indexed listing path via env var `INDEXED_LISTING_ENABLED=0`. Disable watcher via `GALLERY_WATCH_ENABLED=0`. Disable new parser formats individually.

**Risk level:** Medium for indexed listing (stale results risk), Medium for watcher (platform behavior differences), Low-Medium for parser additions (fixture-backed).

**What not to do:**
- Do not make indexed listing the only path — direct scan must always work as fallback
- Do not make watcher mandatory
- Do not add Stealth PNG in this phase
- Do not add ML/CLIP/OCR
- Do not add multi-user

---

## SECTION H — Architecture Diagrams

### H1: Current gallery-repo Pipeline

```text
Folder Open (Cold):
  click folder
  → useInfiniteScanQuery
  → GET /api/scan
    → resolve_path / is_path_safe
    → os.scandir + stat + filter images/folders
    → batch SQLite dimension lookup (path+mtime+size)
    → sort folders/images
    → paginate
    → return FileNode[]
    ↳ background_tasks:
        → index_file (folder row)
        → index_files_from_scan (file rows, no metadata)
        → index_directory_tree (recursive, include_metadata=False)
  → GalleryGrid renders albums + photo cards
  → PhotoCard triggers /api/thumbnail lazily
    → render WebP if cache miss
    → upsert_image_dimensions (width/height only)
    → persist to disk cache
  → infinite scroll fetches more pages (re-sorts, re-paginates)

Lightbox:
  click photo card
  → lightboxStore.open(node, items)
  → buildPhotoSwipeItem: src=/api/image, msrc=/api/thumbnail
  → PhotoSwipe opens with best-known dimensions
  → usePhotoSwipe dimension resolver:
    scan dims → remembered thumbnail dims → cached metadata dims → fetch metadata → load thumbnail natural dims
  → /api/metadata fetches + parses + upserts full metadata
  → metadata panel updates

Search:
  type query
  → debounce 300ms
  → GET /api/search (or /api/search-metadata legacy)
  → file_index_fts for albums/photos
  → image_metadata_fts (or trigram) for prompts
  → LIKE fallback if FTS fails
  → scope-filtered (current folder or all indexed)
  → stale cleanup if missing files detected

Warm Folder Open:
  same as cold, but:
  → batch dimension lookup returns cached values
  → thumbnails hit disk cache → 304 or fast serve
  → metadata queries hit in-memory LRU or SQLite
  → still walks and sorts directory
```

### H2: Target Near-Term Pipeline (Phase 1-2)

```text
Folder Open (Warm with Indexer):
  click folder
  → GET /api/scan (unchanged hot path)
    → same directory walk + batch lookup
    → returns FileNode[] with cached dims + has_thumbnail
    ↳ background_tasks (NEW):
        → enqueue metadata jobs for scanned image paths
        → index queue coalesces by path+mtime+size
        → worker drains queue into batch writer
        → batch writer upserts image_metadata rows (50/transaction)
        → thumbnail_cache rows populated on thumbnail generation
  → GalleryGrid renders (unchanged)
  → /api/thumbnail: now also writes thumbnail_cache row

Lightbox (Warm Cache):
  click photo card
  → lightboxStore.open (unchanged)
  → buildPhotoSwipeItem: src=/api/image (unchanged)
  → PhotoSwipe opens (unchanged)
  → dimension resolver: cached metadata dims likely available from indexer
  → /api/metadata: SQLite cache hit → instant response, no file parse
  → neighbor prefetch (NEW): queryClient.prefetchQuery for next/prev metadata
  → neighbor thumbnail preload extended to higher-quality (1200px)

Search (With Fielded Support):
  type "cat model:realistic seed:12345"
  → debounce 300ms
  → query parser strips "model:realistic seed:12345"
    → residual text: "cat" → FTS5 search
    → predicates: model="realistic", seed="12345" → SQL WHERE
  → combine results: FTS INTERSECT metadata filter
  → scope-filtered as before
  → FTS/LIKE fallback for malformed tokens

Index Status:
  GET /api/index/status?path=...
    → returns { queued, running, done, error, lastError }
    → frontend optional subtle indicator
```

### H3: Target Warm-Cache Pipeline (Phase 3+)

```text
Folder Open (Warm Indexed Fast Path):
  click folder
  → GET /api/scan
    → check folder mtime vs file_index freshness
    → IF FRESH:
      → SELECT file_index JOIN image_metadata
        WHERE parent_path = ?
        ORDER BY mtime DESC LIMIT ? OFFSET ?
      → return FileNode[] from DB (300-500ms for 5000 images)
    → IF STALE OR COLD:
      → fallback to direct os.scandir walk (current behavior)
      → re-index in background
    → both paths return identical shape

Watcher (Optional, Enabled):
  GALLERY_WATCH_ENABLED=1
  → watchfiles monitors GALLERY_ROOT
  → create/modify → enqueue re-index
  → delete → cleanup file_index + image_metadata + thumbnail_cache
  → batch events within 1s window

Rich Metadata Facets:
  → model_hash, tool, scheduler, lora_text columns populated by unified parser
  → Fooocus, InvokeAI, WebP EXIF formats parsed
  → search facets include lora:lora_name, tool:swarmui queries
```

### H4: Lightbox Target Pipeline

```text
Lightbox Open:
  click photo
  → lightboxStore.open(node, items)
  → buildPhotoSwipeItem:
    src = /api/image          (unchanged — Rule 6)
    msrc = /api/thumbnail?max_size=2400  (high-quality placeholder)
    width/height = cached from scan or metadata or best-known
  → PhotoSwipe renders (unchanged)
  → parallel:
    → /api/image loads full original
    → /api/metadata returns from SQLite (warm) or parses (cold)
    → dimension resolver: cached > fetch > thumbnail natural (unchanged order)
  → metadata panel: DB-first when warm (Rule 4 + Immich idea)

Lightbox Neighbor Prefetch (Phase 2):
  → on open: preload next + previous
    → thumbnail: 1200px max (not original)
    → metadata: queryClient.prefetchQuery for /api/metadata
    → cap 2 concurrent, cancel on rapid nav
  → NEVER preload /api/image for neighbors

Lightbox Dimensions (Phase 2+):
  → preview/placeholder from warm thumbnail_cache
  → /api/image always authoritative (Rule 6)
  → no preview replacement for original
```

### H5: Search Target Pipeline

```text
Search Query Processing:
  user input: "portrait model:sd-v1 seed:42 steps:20 negative:blurry"
  → queryParser.parse() →
    residual text: "portrait"           → FTS5 (image_metadata_fts)
    metadata predicates:
      model ILIKE '%sd-v1%'
      seed = '42'
      steps = 20
      negative_prompt LIKE '%blurry%'
  → SQL:
    SELECT * FROM (
      FTS MATCH "portrait" → image_ids
      INTERSECT
      SELECT id FROM image_metadata WHERE model ILIKE ...
      INTERSECT
      SELECT id FROM image_metadata WHERE seed = ...
      INTERSECT ...
    ) JOIN file_index for scope filtering
  → combine with album/photo file_index_fts results
  → return grouped: albums, photos, prompt results
  → malformed tokens → passthrough to FTS (no error)
```

---

## SECTION I — Testing and Perf Gates

### Backend Tests

| Test | Description | Phase |
|---|---|---|
| `test_scan_never_opens_images` | Assert Image.open() never called from scan call chain | P0 |
| `test_scan_dims_only_from_cache` | Assert scan dimensions only from batch cache lookup | P0 |
| `test_parser_fixtures_a1111` | Golden test for A1111 parameter text | P1 |
| `test_parser_fixtures_swarmui` | Golden test for SwarmUI JSON metadata | P1 |
| `test_parser_fixtures_comfyui` | Golden test for ComfyUI prompt/workflow JSON | P1 |
| `test_parser_fixtures_novelai` | Golden test for NovelAI metadata | P1 |
| `test_parser_fixtures_easydiffusion` | Golden test for EasyDiffusion metadata | P1 |
| `test_parser_fixtures_sidecar` | Golden test for .txt sidecar metadata | P1 |
| `test_parser_fixtures_exif_usercomment` | Golden test for EXIF UserComment metadata | P1 |
| `test_parser_fixtures_fooocus` | Golden test for Fooocus metadata | P3 |
| `test_parser_fixtures_invokeai` | Golden test for InvokeAI metadata | P3 |
| `test_parser_fixtures_webp_comfy` | Golden test for WebP EXIF ComfyUI conventions | P3 |
| `test_indexer_coalescing` | Same file re-enqueued with same mtime+size → skip | P1 |
| `test_indexer_stale_invalidation` | File changed (mtime/size) → re-indexed | P1 |
| `test_indexer_skip_no_change` | File unchanged → not re-indexed | P1 |
| `test_indexer_queue_status` | Index status endpoint returns correct counts | P1 |
| `test_batch_writer_flush` | Batch of 50 rows written in single transaction | P1 |
| `test_batch_writer_atomic` | Batch write either fully succeeds or rolls back | P1 |
| `test_fielded_query_parser` | Tokenization, quoted values, malformed input, passthrough | P2 |
| `test_fielded_sql_builder` | SQL predicates generated correctly for each field type | P2 |
| `test_fielded_search_plain_compat` | Plain text search unchanged with fielded parser active | P2 |
| `test_derivative_readiness` | `thumbnail_cache` row written on generation, read in batch | P2 |
| `test_derivative_stale_cleanup` | Stale rows invalidated on mtime/size change | P2 |
| `test_indexed_listing_matches_scan` | Indexed fast path returns same rows as direct scan | P3 |
| `test_indexed_listing_stale_fallback` | Stale index triggers direct scan fallback | P3 |
| `test_watcher_create_modify_delete` | File events trigger correct index operations | P3 |
| `test_watcher_batch_dedup` | Rapid events batched into one re-index | P3 |

### Frontend Tests

| Test | Description | Phase |
|---|---|---|
| `album-open perf` | Existing test — must continue passing | P0+ |
| `lightbox-open perf` | Existing test — must continue passing | P0+ |
| `lightbox-transition perf` | Existing test — must continue passing | P0+ |
| `lightbox-src-is-full-image` | Assert PhotoSwipe src uses /api/image | P0 |
| `lightbox-no-full-preload` | Assert neighbor preload never uses /api/image | P2 |
| `lightbox-metadata-prefetch` | Assert neighbor metadata queries fire on open | P2 |
| `lightbox-rapid-nav-cancel` | Assert rapid navigation cancels in-flight preloads | P2 |
| `search-no-results-after-fetch` | Existing behavior — no flicker before fetch settles | P0+ |
| `empty-state-no-flicker` | Existing behavior | P0+ |
| `no-index-status-toast-noise` | Status UI does not create landing toast regression | P1 |

### Perf Budgets

| Budget | Cold/Current | Warm Target | Phase |
|---|---|---|---|
| 50-image album scan p95 | <= current budget | <= current budget | P0-P3 |
| First thumbnail start | <= current budget | <= current budget | P0-P3 |
| Lightbox visible after click | <= `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS` (1500ms) | <= budget | P0-P3 |
| Lightbox image loaded after click | <= `GALLERY_PERF_LIGHTBOX_IMAGE_BUDGET_MS` (4000ms) | <= budget | P0-P3 |
| Lightbox transition p95 | <= `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS` (3000ms) | <= budget or improved | P0-P3 |
| 5000-image warm first page (indexed) | N/A (currently cold walk) | 300-500ms | P3 |
| `/api/index/status` warm | N/A | <= 50ms | P1 |
| `/api/search` fielded query | N/A | <= plain text search p95 | P2 |
| Background indexer CPU | N/A | Must yield to request hot path | P1 |
| Thumbnail p95 | <= `GALLERY_PERF_THUMB_P95_BUDGET_MS` (1200ms) | <= budget | P0-P3 |
| No regression to any existing budget | — | — | P0-P3 |

### Observability

| Metric | Source | Purpose | Phase |
|---|---|---|---|
| `http_request_duration_seconds` | Prometheus (existing) | All endpoint latencies | P0+ |
| `http_request_count_total` | Prometheus (existing) | Request rates by method/status/route | P0+ |
| Background indexer queue depth | Custom Prometheus gauge | Detect stalled queues | P1 |
| Background indexer job errors | Custom Prometheus counter | Alert on parsing/index failures | P1 |
| SQLite write latency | Custom Prometheus histogram | Detect lock contention from batching | P1 |
| Indexer yield idle time | Custom Prometheus gauge | Verify yielding to request path | P1 |
| Thumbnail cache hit rate | Custom Prometheus counter | Track derivative readiness | P2 |
| pyinstrument profile points | Existing `/api/scan`, `/api/metadata`, `/api/thumbnail` | Debug hot path regressions | P0+ |
| Watcher event rate | Custom Prometheus counter | Monitor watcher event volume | P3 |
| Watcher event processing latency | Custom Prometheus histogram | Detect watcher backlog | P3 |

---

## SECTION J — Risk Register

| Risk | Cause | Impact | Probability | Mitigation | Test/Metric |
|---|---|---|---|---|---|
| Background indexer steals CPU/disk from UI | Worker thread too aggressive | Slow thumbnails, slow scan, sluggish UI | Medium | Single worker, 50ms job yield, configurable throttle, env var disable | Album-open + thumbnail perf tests; indexer yield idle metric |
| SQLite write locks | Large batch transactions or concurrent writers | Stalled requests, WAL busy errors | Medium | Bounded batch size (50), single writer lock, WAL mode, busy_timeout=5000 | SQLite write latency histogram |
| Duplicate index jobs | Queue coalescing bug (race on path+mtime+size) | Wasted CPU, redundant parsing | Low | Dedup by path+mtime+size in queue table; idempotent upsert in image_metadata | `test_indexer_coalescing` |
| Stale metadata | File edited after index, mtime+size not rechecked | Lightbox shows old prompt/params | Medium | Jobs revalidate mtime+size before processing; fanotify events in watcher phase | `test_indexer_stale_invalidation` |
| Invalid dimensions after EXIF orientation | Orientation header changed but dimensions cached | Wrong lightbox aspect ratio | Low | `ImageOps.exif_transpose()` already applied in thumbnail/dimension paths | Lightbox test asserts ratioDiff < 0.2 |
| Fielded search breaks normal search | Query parser mishandles plain text or emits bad SQL | Search returns wrong or no results | Medium | Parser passthrough on failure; extensive test suite; FTS fallback always available | `test_fielded_search_plain_compat` + search perf tests |
| Too much DB bloat from raw workflows/node props | ComfyUI workflow JSON stored in metadata_json | Large SQLite DB, slow queries | Medium | Store workflow externally or with size limit; don't index raw blobs in P1-P2 | SQLite DB size metric; configurable max JSON size |
| Prefetch causes bandwidth spikes | Many concurrent prefetch requests | Slow main image load, wasted bandwidth | Low | Cap 2 concurrent preloads; cancel on rapid navigation; prefetch thumbnails not originals | `lightbox-rapid-nav-cancel` test; network request count assertion |
| Watcher misses events | Filesystem event queue overflow, watcher not running | Stale index entries | Medium | Periodic full validation scan; batch event processing; watcher health check | Watcher event rate and latency metrics; stale index cleanup |
| Status UI becomes noisy (like previous toast bug) | Persistent status indicator shows too eagerly | Degraded UX, user annoyance | Low | Status visible only on relevant interaction; auto-dismiss; subtle indicator only; never blocking | `no-index-status-toast-noise` test; UI review |
| Optional previews drift toward replacing original lightbox image | Feature creep blurs the preview/original boundary | Violation of Rule 6 and 7, broken lightbox test | Medium | Document clearly: preview is placeholder only; main src always `/api/image`; test assertion guards | `lightbox-src-is-full-image` test; code review for `buildPhotoSwipeItem` |
| Watcher blocks thread pool during event storms | Many files created/modified in rapid succession | Unresponsive gallery | Low | Batch events within 1s windows; process as low-priority background jobs; configurable debounce | Watcher event processing latency metric; stress test |
| Indexer re-parses metadata already cached in SQLite | Queue feeds all files on scan, many already indexed | Wasted CPU | Low | Revalidate mtime+size before processing; skip if no change | `test_indexer_skip_no_change` |
| Indexed folder listing returns stale results | External file changes not detected | User sees deleted files or misses new files | Medium | Folder mtime check as quick invalidation; individual mtime+size validation; watcher in Phase 3 | `test_indexed_listing_stale_fallback` |
| Batch writer loses data on crash | Unflushed batches in memory | Fewer indexed files than expected | Low | Flush every 500ms or 50 rows; periodic flush on idle; restart re-scans missing folders | Crash recovery test |

---

## SECTION K — Final Recommendation

### Do First

1. **Phase 0**: Lock current perf guarantees with regression guard tests. Never skip this — it's the foundation.
2. **Unified parser core (P1)**: The single most important code quality improvement. Ends the two-parser divergence and enables fixture testing.
3. **Background indexer + batch writer + index status (P1)**: The core infrastructure that closes the biggest gap. Enables warm search, faster metadata panels, and foundation for all later phases.
4. **Fielded search (P2)**: Unlocks precise AI metadata search with minimal schema changes. Builds on the Phase 1 index.
5. **Neighbor metadata prefetch (P2)**: Low-risk, high-impact UX improvement for lightbox navigation.

### Do Next

6. **Derivative status table (P2)**: Enables smart thumbnail warming and readiness queries.
7. **Indexed folder listing fast path (P3)**: The leap from "good at dozens" to "good at thousands".
8. **Broader parser formats (P3)**: Fooocus, InvokeAI, WebP EXIF ComfyUI. Fixture-backed.
9. **Optional file watcher (P3)**: Comfort feature for stable local folders.

### Defer

10. **Stealth PNG fallback**: Only in explicit rebuild flow, never auto-triggered. Very niche use case.
11. **ComfyUI node/property search**: Needs to prove value before adding complexity. Schema and performance concerns.
12. **Prompt usage/grouping endpoint**: Nice library-management feature, separate from core gallery.
13. **Saved searches**: Client-side storage first, backend later if needed.
14. **Preview derivative generation**: Only if original load measured and shown to be a real problem for specific use cases.

### Reject

15. **PostgreSQL/Redis/BullMQ as defaults**: Kill the deployment simplicity and you kill the project's identity.
16. **Eager full-file hash/read on scan**: Unacceptable cold-folder latency for large AI images.
17. **Synchronous viewer metadata reparse**: Antithetical to the async lightbox design.
18. **Preview replacing original lightbox image**: Violates the hard requirement tested in the lightbox perf spec.
19. **Immich's full multi-user/album/backup model**: Scope explosion orthogonal to local folder browsing.
20. **ML/CLIP/OCR smart search**: Heavy infrastructure for a different product category.
21. **Per-folder thumbnail SQLite (DT style)**: Existing mtime+size-based file cache is superior for invalidation.

### Summary

The correct direction is:

```text
Do not become Immich.
Do not become DiffusionToolkit.
Become gallery-repo with:
  - fast scan (preserved)
  - original-image lightbox (preserved)
  - local background metadata indexer (borrowed from DT)
  - batched SQLite writes (borrowed from DT)
  - DB-first warm metadata (borrowed from Immich)
  - simple optional fielded search (borrowed from DT)
  - observable perf gates (preserved and extended)
```

The most important investment is Phase 1's unified parser + background indexer. It closes the largest capability gap while creating the foundation for every subsequent improvement. Without it, search will stay incomplete and metadata panels will stay slow for anything the user hasn't manually opened.

The most important thing to preserve is Phase 0's regression guard tests. Every Phase 1-3 feature must pass the same album-open and lightbox perf tests that the current code passes. Any feature that cannot live within those budgets must be redesigned or rejected.

---

## SECTION L — Commit and Push

*(To be executed after file is written)*

```bash
git status
git add docs/GALLERY_REPO_EVOLUTION_MASTER_PLAN.md
git commit -m "docs: add gallery evolution master plan"
git push
```

### Final Report

| Item | Detail |
|---|---|
| **Commit hash** | *(pending push)* |
| **File changed** | `docs/GALLERY_REPO_EVOLUTION_MASTER_PLAN.md` |
| **Short summary** | Comprehensive 10-section master plan for evolving gallery-repo by selectively borrowing background indexing, batched SQLite writes, fielded search, DB-first metadata, derivative status, and neighbor prefetch from DiffusionToolkit and Immich — while explicitly rejecting PostgreSQL/Redis, eager metadata parsing on scan, ML search, and any change that replaces the original-image lightbox source |
| **Top 10 decisions** | 1. Preserve `/api/scan` zero-PIL guarantee. 2. Unify the two parser stacks. 3. Add bounded background metadata indexer with coalesced jobs. 4. Add batched SQLite writer (50 rows/transaction). 5. Add fielded search on top of FTS5. 6. Add index status endpoint. 7. Add neighbor metadata + thumbnail prefetch (no originals). 8. Add indexed folder listing fast path for warm folders. 9. Add optional file watcher (disabled by default). 10. Add derivative readiness table. |
| **Top 5 things to implement first** | 1. Lock current perf guarantees with guard tests (Phase 0). 2. Unified parser core + fixture tests (Phase 1). 3. Background metadata indexer + batch writer + index status (Phase 1). 4. Fielded search (Phase 2). 5. Neighbor metadata prefetch (Phase 2). |
| **Top 5 things explicitly rejected** | 1. PostgreSQL/Redis/BullMQ — SQLite remains default. 2. Eager metadata parsing on `/api/scan`. 3. Synchronous viewer metadata reparse. 4. Preview replacing `/api/image` as lightbox main source. 5. ML/CLIP/OCR smart search. |
| **Any uncertainty** | DT and Immich assessments are based on code reading at specific commits, not live deployments. Actual performance of indexed folder listing will depend on SQLite performance for the target hardware. Watcher behavior varies by platform and filesystem — needs real-world testing before enabling by default. Parser fixture tests require representative sample images from each generator. |
