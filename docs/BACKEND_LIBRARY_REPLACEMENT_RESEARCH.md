# Backend Library Replacement Research

Last reviewed: 2026-06-07

## Executive summary

The backend is already built on a reasonable foundation: FastAPI, Pydantic models, Pillow, and `cachetools`. Most current risk is not the API framework; it is concentrated in directory indexing strategy, image processing throughput, and AI-generation metadata parsing coverage.

Recommended direction:

- Keep FastAPI. Alternatives do not remove meaningful custom code in this backend.
- Make a backend refactor plus `pydantic-settings` the Phase 1 priority. Plan the module split first, then move code with zero behavior change.
- Add tests before replacing logic: path safety, natural sort, metadata parser fixtures, and thumbnail guardrails.
- Keep the current path safety implementation. `pathvalidate` solves different problems: validating/sanitizing path strings, not authorizing resolved filesystem access under `GALLERY_ROOT`.
- Keep Fuse.js for current-view filename/folder search only. SQLite FTS5 is now used for backend prompt/metadata search.
- Keep the custom Stable Diffusion metadata parser. It is project-specific and currently supports more relevant formats, including SwarmUI, EasyDiffusion, sidecar files, and LoRA extraction.
- Keep Pillow. Do not prioritize `pyvips` unless thumbnail throughput or memory usage becomes a measured bottleneck.
- Keep `cachetools` memory cache. Prototype `diskcache` only if persistent thumbnails or cross-process cache reuse becomes necessary.
- Keep `/api/open-folder` custom and disabled by default.

No runtime code or dependency files were changed for this investigation.

## Current backend functional groups

Source reviewed:

- `backend/main.py`
- `backend/requirements.txt`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`
- `docs/METADATA_PARSING.md`
- `docs/THIRD_PARTY_LIBRARIES.md`

Current backend responsibilities:

| Group | Current implementation |
|---|---|
| API framework | FastAPI app, route decorators, Pydantic `FileNode`, `HTTPException`, CORS middleware, threadpool offload for blocking image work |
| Config/env settings | Direct `os.getenv()` calls for `GALLERY_ROOT`, `GALLERY_OPEN_FOLDER`, `PRODUCTION`, `PORT`, `FRONTEND_ORIGIN`, `FRONTEND_PORT` |
| Path safety/filesystem | `Path.resolve()` plus `GALLERY_ROOT in resolved.parents or resolved == GALLERY_ROOT`; custom Windows long-path fallback |
| Folder scanning/indexing | `os.scandir()` / `Path.iterdir()`, skips hidden files, computes folders/images, direct image dimensions via Pillow, offset pagination |
| Thumbnail generation | Pillow open/transposition/conversion/resize/WebP encode; size and pixel guardrails |
| Cache | `cachetools.LRUCache` for thumbnail bytes and metadata dicts; explicit locks and in-flight `Future` de-duplication |
| Metadata extraction/EXIF | Pillow `Image.info`, `Image.getexif()`, PNG text chunks, EXIF `UserComment`, sidecar `.txt` fallback |
| SD metadata parsing | Custom parsers for A1111/WebUI, ComfyUI, SwarmUI, NovelAI, EasyDiffusion, LoRA extraction |
| Search/full-text | Frontend Fuse.js filters currently loaded filename/folder rows. Backend `/api/search-metadata` searches indexed prompt/metadata text in SQLite FTS5 |
| Sort | Backend natural filename sort via regex; frontend also owns user-facing search/sort state |
| Static serving | FastAPI `FileResponse` for originals, thumbnails, production SPA root, and production catch-all |
| Open folder OS integration | Custom `os.startfile` / `open` / `xdg-open`, gated by `GALLERY_OPEN_FOLDER=false` by default |

## Library/tool evaluation matrix

| Group | Candidate | Official link | What it replaces or improves | Maturity | Integration risk | Recommendation |
|---|---|---|---|---|---|---|
| API framework | FastAPI | https://fastapi.tiangolo.com/ | Current API framework | Very mature, widely used; PyPI 0.136.3; GitHub ~99k stars | Low because already integrated | Keep |
| API framework | Flask | https://flask.palletsprojects.com/ | Alternative web framework | Very mature; PyPI 3.1.3; GitHub ~71k stars | High migration, loses native current FastAPI/Pydantic shape | Do not migrate |
| API framework | Litestar | https://docs.litestar.dev/ | Alternative ASGI API framework | Mature and active; PyPI 2.23.0; GitHub ~8k stars | Medium-high route/model migration | Do not migrate unless starting a larger backend rewrite |
| Config/env | pydantic-settings | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ | Manual env parsing and defaults | Production/stable; PyPI 2.14.1 | Low | Adopt in Phase 1 |
| Path safety | pathvalidate | https://pathvalidate.readthedocs.io/en/latest/ | Filename/path string validation | Production/stable; PyPI 3.3.1 | Medium if confused with authorization | Do not replace path safety; optional input validation only |
| Folder indexing | watchdog | https://watchdog.readthedocs.io/en/stable/ | Poll/rescan model with filesystem events | Production/stable; PyPI 6.0.0; GitHub ~7.3k stars | Medium-high; platform-specific watcher behavior | Prototype only if indexing is added |
| Folder indexing | watchfiles | https://watchfiles.helpmanual.io/ | Modern file watching | Production/stable; PyPI 1.2.0; GitHub ~2.5k stars | Medium; Rust-backed dependency, event semantics | Prototype only if indexing is added |
| Folder indexing/search | SQLite index | https://www.sqlite.org/ | Persist image metadata and search fields | Extremely mature, stdlib `sqlite3` available | Medium; metadata index implemented without replacing folder pagination | Use for metadata search only |
| Thumbnails | Pillow | https://pillow.readthedocs.io/ | Current image decode/resize/WebP/EXIF transpose | Mature and already integrated; PyPI 12.0.0 in requirements | Low | Keep |
| Thumbnails | pyvips | https://libvips.github.io/pyvips/ | Faster/lower-memory thumbnail pipeline | Production/stable; PyPI 3.1.1; GitHub ~800 stars; backed by libvips | Medium-high; native libvips dependency and behavior parity testing | Prototype only for measured bottlenecks |
| Thumbnails | Wand/ImageMagick | https://docs.wand-py.org/en/latest/ | Alternative image pipeline | Production/stable; PyPI 0.7.1; GitHub ~1.5k stars | High; native ImageMagick dependency and policy/config concerns | Do not prefer |
| Cache | cachetools | https://cachetools.readthedocs.io/en/stable/ | Current in-memory LRU cache classes | Production/stable; PyPI 7.1.4; GitHub ~2.7k stars | Low because already integrated | Keep |
| Cache | diskcache | https://grantjenks.com/docs/diskcache/ | Persistent disk-backed cache, cross-process cache | Production/stable; PyPI 5.6.3; GitHub ~2.9k stars | Medium; cache directory lifecycle and eviction policy | Prototype for persistent thumbnails |
| EXIF | Pillow EXIF | https://pillow.readthedocs.io/ | Current basic EXIF access and orientation handling | Mature and already integrated | Low | Keep for current needs |
| EXIF | piexif | https://piexif.readthedocs.io/en/latest/ | EXIF read/write manipulation | Production/stable; PyPI 1.1.3, but less active | Medium; extra dependency mostly for writes | Do not add unless EXIF write/edit is needed |
| EXIF | ExifRead | https://exif-py.readthedocs.io/en/latest/ | Read-only EXIF extraction | Production/stable; PyPI 3.5.1; GitHub ~950 stars | Low-medium | Consider only if Pillow misses needed EXIF tags |
| EXIF | PyExifTool | https://sylikc.github.io/pyexiftool/ | Wrapper around external ExifTool | Beta on PyPI; active fork; requires ExifTool binary | High operational dependency | Optional advanced metadata tool, not default |
| SD metadata | sd-parsers | https://github.com/d3x-at/sd-parsers | Stable Diffusion metadata parser library | Small project; PyPI 0.6; GitHub ~45 stars | Medium-high; output schema differs; no SwarmUI listed | Do not prioritize; keep custom parser |
| Search | Fuse.js | https://www.fusejs.io/ | Frontend fuzzy search over loaded filename/folder gallery data | Mature and frontend-local | Low; already integrated | Keep for current-view search only |
| Search | SQLite FTS5 | https://sqlite.org/fts5.html | Backend full-text search over filename/prompt/metadata | Built into SQLite builds when enabled | Medium; schema and query API implemented | Use for backend prompt/metadata search |
| Search | Whoosh | https://whoosh.readthedocs.io/en/latest/ | Pure-Python full-text indexing | Stable but old; PyPI 2.7.4 | Medium; extra index format, older maintenance profile | Avoid unless SQLite FTS5 is unavailable |
| Sort | natsort | https://natsort.readthedocs.io/en/stable/ | Custom regex natural sort | Production/stable; PyPI 8.4.0; GitHub ~1k stars | Low | Adopt if filename sort bugs appear |
| Static serving | WhiteNoise | https://whitenoise.readthedocs.io/en/latest/ | Production static asset serving | Production/stable; PyPI 6.12.0; GitHub ~2.7k stars | Medium; WSGI-focused docs, ASGI integration less direct | Do not add for this app |
| OS integration | Keep custom | https://docs.python.org/3/library/os.html | `open-folder` route | N/A | Low if disabled | Keep disabled by default |

## Detailed findings per group

### 1. API framework - FastAPI

Current fit is strong. The backend already uses FastAPI route decorators, query validation, Pydantic response models, `FileResponse`, CORS middleware, and `run_in_threadpool` for blocking image work. FastAPI remains active and widely adopted.

Alternatives:

- Flask is stable and popular, but would require replacing route declarations, validation behavior, OpenAPI generation, and async/threadpool patterns.
- Litestar is a credible ASGI alternative, but migration would be a framework rewrite without solving scanning, thumbnails, metadata parsing, or caching.
- Starlette is the lower-level ASGI base under FastAPI-style apps; moving down would remove conveniences the backend currently uses.

Pros of staying:

- Lowest risk.
- Existing frontend API contract remains unchanged.
- Current dependency list is small.
- Good match for typed Pydantic models and query constraints.

Cons:

- FastAPI does not solve indexing, image processing, or metadata parsing by itself.
- Current FastAPI version is newer than the old "beta" classifier suggests, but PyPI still reports `Development Status :: 4 - Beta`.

Recommendation: Keep FastAPI.

Final project decision: Keep FastAPI. The framework is not the problem.

### 2. Config/env settings - pydantic-settings

Current code manually reads env vars in several places. `pydantic-settings` provides a typed `BaseSettings` model that reads values from environment variables, supports defaults, `.env` files, env prefixes, and secrets files.

What it could replace:

- `_get_cors_origins()` env parsing.
- `GALLERY_ROOT`, `OPEN_FOLDER_ENABLED`, `PRODUCTION`, and `PORT` parsing.
- Boolean string parsing such as `GALLERY_OPEN_FOLDER=false`.

Pros:

- Centralizes configuration.
- Gives typed validation and clearer defaults.
- Fits the existing Pydantic/FastAPI stack.
- Low behavioral risk if introduced with tests.

Cons:

- Adds a dependency.
- Requires careful mapping to preserve current env variable names and defaults.

Integration risk: Low.

Recommendation: Adopt in Phase 1, preserving current env names and defaults exactly.

Final project decision: `pydantic-settings` is part of the Phase 1 backend refactor priority.

### 3. Path safety/filesystem - pathvalidate or keep custom

Current path safety is an authorization check: resolve a user-supplied path and ensure it remains under `GALLERY_ROOT`. This guards traversal and symlink escape by checking the resolved path.

`pathvalidate` validates and sanitizes path strings across platforms. That is useful for generated filenames or user-created paths, but it is not a replacement for "is this resolved absolute path inside an allowed root?"

Pros of `pathvalidate`:

- Good for validating filenames.
- Cross-platform filename/path constraints.

Cons:

- Does not replace containment authorization.
- Could create a false sense of security if used instead of `Path.resolve()` containment.

Integration risk: Medium if misapplied.

Recommendation: Keep the custom containment check. Consider `pathvalidate` only if the app later creates or renames files from user input.

Final project decision: Preserve current `GALLERY_ROOT` safety behavior during the refactor. Production hardening can be documented separately, but it is not part of the behavior-preserving Phase 1 change.

### 4. Folder scanning/indexing - watchdog, watchfiles, SQLite index

Current scanning is synchronous directory enumeration per `/api/scan`. It computes folder rows, image rows, folder covers, image counts, dimensions, natural sort, and offset pagination on each request.

Possible improvements:

- `watchdog`: mature cross-platform filesystem events.
- `watchfiles`: modern, fast watcher written with Rust internals.
- SQLite index: store image path, mtime, size, dimensions, folder path, metadata summary, and search fields.

Pros:

- Watchers can avoid repeated full rescans.
- SQLite can make pagination, sorting, and search more predictable for large folders.
- Indexed dimensions avoid reopening images during every scan.

Cons:

- Watchers are best as cache invalidation, not the only source of truth. Network filesystems, permissions, moves, and missed events still require rescan/rebuild logic.
- SQLite needs schema design, migrations, corruption handling, rebuild UX, and invalidation rules.
- Current frontend expects folder-local scans and cursor offsets; an index could change timing and consistency.

Integration risk: Medium-high.

Metadata-search decision update: add a narrow SQLite metadata index without replacing folder scanning or pagination. The index lives at `backend/.cache/gallery_metadata.db`, is keyed by path, mtime, and size, and is populated opportunistically from `/api/scan`. This keeps `/api/scan`, pagination, folder navigation, and current frontend sort behavior intact.

### 5. Thumbnail generation - Pillow, pyvips, Wand/ImageMagick

Current Pillow pipeline is clear and correct for the current feature set: file/pixel guardrails, EXIF transpose, color conversion, Lanczos thumbnail, WebP output, and cache storage.

`pyvips` is the strongest alternative for performance. libvips is known for streaming and lower memory usage on large images. It may improve throughput for large folders and high-resolution images.

Wand uses ImageMagick. It is mature, but it adds a larger native dependency surface and can be sensitive to system policy/configuration. It is less attractive for a small local-first gallery unless ImageMagick-specific format support is required.

Pros of pyvips:

- Potentially faster and lower memory for thumbnailing.
- Mature native image library.

Cons of pyvips:

- Requires native libvips availability.
- Need parity tests for EXIF orientation, transparency flattening, WebP output, animated images, and error handling.
- More complicated installation than Pillow.

Integration risk: Medium-high.

Recommendation: Keep Pillow. Prototype pyvips only after profiling shows thumbnail generation is the bottleneck.

Final project decision: Do not prioritize `pyvips`. Keep Pillow unless a bottleneck is measured.

### 6. Cache - cachetools, diskcache

Current code already uses `cachetools.LRUCache` with byte-size accounting for thumbnails and estimated-size accounting for metadata. It adds locks and in-flight `Future` de-duplication, which is important because cachetools cache objects are mutable collections and are not a full concurrent work scheduler by themselves.

`diskcache` offers persistent, disk-backed, thread-safe and process-safe caches. It could be useful for thumbnails because regenerated WebP bytes are expensive and survive process restarts.

Pros of current cachetools setup:

- Already integrated.
- Simple in-memory lifecycle.
- No cache directory to manage.
- Key invalidates on mtime and size.

Pros of diskcache:

- Persistent thumbnails across restarts.
- Cross-process sharing.
- Built-in eviction policies.

Cons of diskcache:

- Adds disk lifecycle, cleanup, cache location config, and eviction tuning.
- For metadata, persistent caching risks stale parser behavior after code changes unless versioned keys are introduced.

Integration risk: Low for keeping `cachetools`, medium for `diskcache`.

Recommendation: Keep `cachetools`. Prototype `diskcache` for thumbnail bytes only if restart regeneration or multi-worker use becomes painful.

Final project decision: Keep `cachetools`. `diskcache` is optional later only if persistent cache behavior is needed.

### 7. Metadata extraction/EXIF - Pillow, piexif, ExifRead, ExifTool wrappers

Current extraction needs are mostly read-only:

- PNG text chunks: `parameters`, `prompt`, `workflow`
- EXIF `UserComment`
- dimensions
- EXIF orientation for display/thumbnail dimensions

Pillow already handles these needs well enough for the current parser. `ExifRead` can be useful if the app needs more complete read-only EXIF coverage. `piexif` is more compelling for EXIF manipulation and writing, which the app does not currently do. PyExifTool can expose very broad metadata support but requires an external ExifTool binary and introduces subprocess/process lifecycle concerns.

Pros of ExifRead:

- Read-only EXIF extraction.
- Pure Python and mature.

Cons:

- Does not parse Stable Diffusion generator metadata by itself.
- Adds another metadata representation to normalize.

Pros of PyExifTool:

- Broadest metadata coverage through ExifTool.
- Can handle formats and tags Pillow may not expose.

Cons:

- External binary requirement.
- More operational complexity.
- Licensing and deployment need review.

Integration risk: Low-medium for ExifRead, high for PyExifTool.

Recommendation: Keep Pillow for current metadata extraction and for metadata-search indexing. Consider ExifRead only for a specific missing EXIF tag requirement. Keep ExifTool wrappers out of default local setup.

### 8. SD metadata parsing - custom parser, sd-parsers

Current custom parser supports A1111/WebUI, ComfyUI, SwarmUI, NovelAI, EasyDiffusion, LoRA extraction, and sidecar `.txt` fallback. The detection order is documented and important.

`sd-parsers` supports Automatic1111, ComfyUI, Fooocus, InvokeAI, and NovelAI according to its README. It exposes structured `PromptInfo` objects, parser configuration, metadata extraction eagerness, and custom parser/extractor extension points.

Pros of `sd-parsers`:

- Purpose-built for Stable Diffusion metadata.
- Supports several generators not currently covered, including Fooocus and InvokeAI.
- Has tests and typed package structure.
- Depends on Pillow, which is already in the backend.

Cons of `sd-parsers`:

- Small project: PyPI 0.6, GitHub ~45 stars.
- README notes custom ComfyUI nodes may parse incorrectly or incompletely.
- SwarmUI and EasyDiffusion are not listed as supported generators.
- Output schema differs from current frontend metadata contract.
- Current sidecar behavior and LoRA display conventions would still need custom glue.

Integration risk: Medium-high.

Recommendation: Keep the custom parser as the recommended path. Do not prioritize `sd-parsers` as a prototype path because it does not cover all project-specific behavior and would still require compatibility glue.

Final project decision: Remove `sd-parsers` from the recommended path. The current parser supports more relevant formats for this app, including SwarmUI, EasyDiffusion, sidecar files, and existing frontend response conventions.

### 9. Search/full-text - Fuse.js current view, SQLite FTS5 metadata search

The frontend filters currently loaded filename/folder data client-side, so current-view search scope is limited by what has been loaded.

Fuse.js remains the right fit for lightweight current-view filename/folder fuzzy search. It is intentionally not used for prompt/metadata search and does not receive full metadata text from scans.

SQLite FTS5 is now used for backend prompt/metadata search. It indexes names, prompts, negative prompts, model names, sampler values, and raw metadata text in one local database. SQLite fits the local-first app and is available through Python's stdlib `sqlite3`.

Whoosh is a pure-Python full-text search library. It is stable but old, and it would add a separate indexing format when SQLite can likely cover both indexing and FTS.

Pros of Fuse.js:

- Keeps search in the frontend where search state already lives.
- Avoids backend behavior changes.
- Does not require database schema, background indexing, or invalidation rules.
- Low implementation risk.

Cons of Fuse.js:

- Search remains limited to data loaded in the frontend.
- It is not suitable for full prompt/metadata search without sending too much metadata text to the browser.

Pros of SQLite FTS5:

- Local, durable, no service dependency.
- Can share the same DB as folder/image index.
- Supports full-text query syntax, tokenizers, and virtual tables.

Cons:

- Requires index build and invalidation.
- Query syntax needs escaping and frontend UX decisions.
- Metadata parsing must happen before metadata search is useful.
- Search covers indexed images only.

Integration risk: Medium.

Recommendation: Keep Fuse.js for current-view filename/folder fuzzy search and SQLite FTS5 for backend prompt/metadata search. Avoid Whoosh unless FTS5 is unavailable.

Final project decision: Implement backend metadata search with SQLite FTS5. Use `unicode61` FTS for normal tokenized search, `trigram` FTS for Japanese/CJK substring search, and parameterized `LIKE` fallback for short CJK queries or no-result fallback. Do not add ExifTool, Meilisearch, Typesense, Tantivy, Whoosh, sqlite-vec, MeCab, Sudachi, Kuromoji, or external services for this implementation.

### 10. Sort - natsort

Current backend natural sort splits filenames with `re.split(r'(\d+)', s)` and converts digit chunks to integers. This handles common cases like `2.png` before `10.png`, but it is limited for decimals, signs, locale-ish cases, mixed paths, and edge cases.

`natsort` is a mature natural sorting library.

Pros:

- Replaces a custom helper with a tested library.
- Handles more filename edge cases.
- Low integration risk.

Cons:

- Adds dependency for a small amount of current code.
- Existing frontend/backend sort expectations need snapshot tests to avoid surprise ordering changes.

Integration risk: Low.

Recommendation: Keep the current sort logic for now. Add tests before any replacement, and consider `natsort` only if filename ordering bugs appear.

Final project decision: Add natural-sort tests before replacing sorting logic.

### 11. Static serving - FileResponse, WhiteNoise

Current static serving is simple:

- `/api/image` uses `FileResponse` for original image files with ETag and cache headers.
- `/` and catch-all serve the built SPA in production with MIME guessing.
- Thumbnails use `Response` because bytes are generated/cached in memory.

WhiteNoise is mature for Python web apps, especially WSGI/Django-style static assets. For this app, the custom production SPA catch-all is small and understandable. FastAPI/Starlette can also serve static directories directly, but the current catch-all supports SPA fallback.

Pros of WhiteNoise:

- Strong static asset caching/compression story in traditional Python deployments.
- Mature and active.

Cons:

- Does not simplify protected original image serving under `GALLERY_ROOT`.
- WSGI-oriented documentation; ASGI usage would need careful verification.
- Adds dependency for a small production-only code path.

Integration risk: Medium.

Recommendation: Keep `FileResponse` static serving. Revisit only if production asset serving becomes more complex.

### 12. Open folder OS integration

Current route is intentionally gated:

- `GALLERY_OPEN_FOLDER=false` by default.
- Validates target exists and is a directory.
- Uses `os.startfile` on Windows, `open` on macOS, and `xdg-open` elsewhere.

This is environment-specific OS integration. A third-party library would not remove the core security concern: exposing a server endpoint that launches local programs.

Pros of keeping custom:

- Minimal code.
- Clear security gate.
- No extra dependency.

Cons:

- Platform behavior can vary.
- Still dangerous if enabled on public deployments.

Integration risk: Low if disabled by default, high if exposed publicly.

Recommendation: Keep custom and disabled by default. Do not enable in public deployments.

## Recommended migration plan

### Phase 1 backend refactor and settings

1. Write focused tests before each move: path safety, natural sort, metadata parser fixtures, thumbnail guardrails, and cache behavior where touched.
2. Extract `config.py` with `pydantic-settings`, preserving current env variable names and defaults.
3. Extract backend modules by responsibility with zero behavior change.
4. Keep old import paths working during the transition where practical.
5. Keep FastAPI, Pillow, `cachetools`, custom path containment, and the custom metadata parser.

Expected outcome: the current backend behavior is preserved, but the code is split into testable modules and configuration is centralized.

### Phase 2 search

1. Keep Fuse.js for current-view filename/folder search over loaded frontend rows.
2. Use backend SQLite FTS5 for prompt/metadata search.
3. Validate that clearing metadata search returns to the normal gallery view and that current-view Fuse search preserves existing sort behavior.

Expected outcome: lightweight current-view search stays frontend-local while prompt/metadata search stays backend-driven.

### Phase 3 measured backend prototypes

1. Consider a broader SQLite folder index only if folder scale or pagination behavior becomes a measured problem.
2. Extend SQLite FTS5 metadata coverage only as parser requirements grow.
3. Consider `diskcache` only if persistent thumbnail caching or cross-process cache reuse becomes necessary.
4. Do not prototype `sd-parsers` as a replacement path unless future requirements exceed the custom parser's supported formats.

Expected outcome: optional backend prototypes are driven by measurements and requirements, not library replacement for its own sake.

### Phase 4 targeted performance or production hardening

1. Prototype `pyvips` only if Pillow thumbnail generation is a measured bottleneck.
2. Consider ExifRead only if a documented metadata requirement cannot be met by Pillow.
3. Revisit production middleware, CORS, static serving, and `GALLERY_ROOT` defaults as a separate hardening project.
4. Keep `/api/open-folder` disabled by default and avoid exposing it publicly.

Expected outcome: performance and production-hardening changes happen as scoped projects with their own tests and deployment review.

## Refactor plan required before implementation

This plan is documentation only. Do not implement it as part of this research update.

The backend should be split by responsibility before library replacement work. Each move should preserve existing behavior, keep the frontend API contract unchanged, and be paired with tests before logic is moved.

Proposed future module layout:

```text
backend/
  main.py (app factory, middleware, startup)
  config.py (pydantic-settings)
  security.py (path safety, GALLERY_ROOT containment)
  scanner.py (os.scandir, pagination, natural sort)
  thumbnails.py (Pillow rendering, cache helpers)
  metadata_parser.py (SD parsers, EXIF, sidecar)
  cache.py (cachetools wrappers, in-flight dedup)
  routers/
    __init__.py
    scan.py
    image.py
    thumbnail.py
    metadata.py
    open_folder.py
    static.py
  tests/
    test_security.py
    test_scanner.py
    test_metadata_parser.py
    test_thumbnails.py
    test_sort.py
```

Proposed refactor steps:

1. Extract `config.py` with `pydantic-settings`, keeping the same env names and defaults.
2. Extract `security.py`, moving `is_path_safe` and `resolve_path`.
3. Extract `cache.py`, moving cache objects, locks, and in-flight de-duplication.
4. Extract `scanner.py` with `scan_directory` and helper functions.
5. Extract `metadata_parser.py` with parser functions.
6. Extract `thumbnails.py` with render and cache helpers.
7. Create `routers/` and move route functions by endpoint group.
8. Create `tests/` and write focused tests before each move.
9. In each step, make zero behavior changes, import from the new module, and keep the old import path working where practical.

Risk areas:

- Metadata parser internal structure and detection order.
- Cache lock ordering and in-flight request de-duplication.
- Import cycles between routers, cache helpers, settings, and path safety.
- CORS, production middleware, static serving, and production `GALLERY_ROOT` hardening.

## Things not to replace yet

- FastAPI: it is not the source of current backend complexity.
- Path containment check: keep custom root authorization.
- Pillow: keep until profiling justifies native-image dependency complexity.
- `cachetools`: already integrated and appropriate for in-memory caching.
- Custom SD parser: keep it as the recommended path because it supports project-specific formats and response conventions.
- Static `FileResponse` serving: current needs are simple.
- Open-folder route: keep custom, gated, and disabled by default.

## Risks and compatibility notes

- `GALLERY_ROOT` currently defaults to `/`, which is broad for local use. Any config refactor must preserve the default unless a separate security change is explicitly planned.
- Path safety must keep symlink escape protection by checking resolved paths.
- Watcher-based indexing can miss events or behave differently across filesystems. Always keep a manual/full rescan path.
- SQLite FTS5 support is required for backend metadata search and should be verified in target Python/SQLite builds.
- Persistent caches need key versioning. Metadata cache keys should include parser/schema version if persisted.
- Thumbnail changes must preserve EXIF orientation, transparency flattening, WebP quality/method expectations, file-size and pixel guardrails, and frontend dimensions.
- `sd-parsers` output shape does not match the current API response. Treat it as outside the recommended path unless future requirements justify new parser work.
- `cachetools` should continue to be protected by explicit locks and in-flight de-duplication for concurrent requests.
- ExifTool wrappers require an external binary and should not become a default dependency without deployment review.
- WhiteNoise is not a replacement for protected user-image serving.

## Final recommendation

Do not perform a broad backend library replacement. The backend should evolve in small, measured steps:

1. Keep FastAPI, Pillow, `cachetools`, custom path authorization, custom static serving, and disabled-by-default OS folder opening.
2. Make the Phase 1 priority a behavior-preserving backend refactor plus `pydantic-settings`.
3. Add tests before replacing logic: path safety, natural sort, metadata parser fixtures, and thumbnail guardrails.
4. Keep Fuse.js for current-view filename/folder search and SQLite FTS5 for backend prompt/metadata search.
5. Keep the custom SD parser, keep `cachetools`, and keep Pillow unless measured requirements justify optional alternatives.

## Research sources

- FastAPI: https://fastapi.tiangolo.com/ and https://pypi.org/project/fastapi/
- Flask: https://flask.palletsprojects.com/ and https://pypi.org/project/Flask/
- Litestar: https://docs.litestar.dev/ and https://pypi.org/project/litestar/
- pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/ and https://pypi.org/project/pydantic-settings/
- pathvalidate: https://pathvalidate.readthedocs.io/en/latest/ and https://pypi.org/project/pathvalidate/
- watchdog: https://watchdog.readthedocs.io/en/stable/ and https://pypi.org/project/watchdog/
- watchfiles: https://watchfiles.helpmanual.io/ and https://pypi.org/project/watchfiles/
- Fuse.js: https://www.fusejs.io/
- SQLite FTS5: https://sqlite.org/fts5.html
- pyvips: https://libvips.github.io/pyvips/ and https://pypi.org/project/pyvips/
- Wand: https://docs.wand-py.org/en/latest/ and https://pypi.org/project/Wand/
- cachetools: https://cachetools.readthedocs.io/en/stable/ and https://pypi.org/project/cachetools/
- diskcache: https://grantjenks.com/docs/diskcache/ and https://pypi.org/project/diskcache/
- piexif: https://piexif.readthedocs.io/en/latest/ and https://pypi.org/project/piexif/
- ExifRead: https://exif-py.readthedocs.io/en/latest/ and https://pypi.org/project/ExifRead/
- PyExifTool: https://sylikc.github.io/pyexiftool/ and https://pypi.org/project/PyExifTool/
- sd-parsers: https://github.com/d3x-at/sd-parsers and https://pypi.org/project/sd-parsers/
- Whoosh: https://whoosh.readthedocs.io/en/latest/ and https://pypi.org/project/Whoosh/
- natsort: https://natsort.readthedocs.io/en/stable/ and https://pypi.org/project/natsort/
- WhiteNoise: https://whitenoise.readthedocs.io/en/latest/ and https://pypi.org/project/whitenoise/
