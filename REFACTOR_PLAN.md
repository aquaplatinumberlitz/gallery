# Backend Refactor Plan

## 1. Motivation

The current `backend/main.py` (~1500+ lines) mixes app setup, config, errors, models, path safety, scan logic, folder logic, image serving, thumbnail rendering/cache, AI metadata parsing, metadata SQLite index/search, search routes, health route, and production frontend static file serving. There is also a circular-import hazard between `metadata_parse` logic and `metadata_store` logic because both need raw extraction primitives.

This refactor splits the monolith into a flat, domain-based set of modules, introduces a third metadata extraction layer (`metadata_extract.py`) to break the cycle, and moves `services/` contents into top-level modules — then deletes the `services/` directory entirely.

Goals:
- Flat, maintainable backend structure with zero nesting beyond `test/`.
- No circular imports.
- Pure refactor: no API behaviour, response shape, status code, or cache behaviour changes.
- `backend/main.py` stays as a compatibility shim so existing `start.py` / `uvicorn` commands keep working.
- No vague names like `helper.py`, `common.py`, `manager.py`.

---

## 2. Target Structure

```
backend/
├── app.py                 FastAPI app + middleware + router composition
├── main.py                Compatibility shim (from app import app) + uvicorn
├── config.py              Environment variables, constants, cache dirs, PRODUCTION
├── errors.py              APIError, ErrorType
├── models.py              FileNode + Pydantic models
├── paths.py               resolve_path, is_path_safe, GALLERY_ROOT checks
├── files.py               is_image, natural_sort_key, IMAGE_EXTENSIONS,
│                          _check_image_limits, _has_alpha
├── albums.py              build_album_metadata, has_subfolders
├── scan.py                /api/scan route + scan_directory + SCAN_PERF_LOGS
│                          + perf helpers
├── folders.py             /api/folders + /api/open-folder
├── images.py              /api/image  (original image serving)
├── thumbnails.py          /api/thumbnail + cache + render + _thumbnail_disk_cache
├── metadata_extract.py    Raw metadata extraction from image files
│                          (lowest layer — no SQLite, no API response formatting)
├── metadata_parse.py      /api/metadata route + rich AI parsers + in-memory LRU cache
├── metadata_store.py      SQLite metadata cache + FTS5 index/search
├── search.py              /api/search + /api/search-metadata
├── health.py              /api/health + favicon + GIT_COMMIT
├── static_files.py        Root / + /api/landing-pages + production SPA fallback
├── test/                  Smoke / regression tests
└── requirements.txt       Unchanged
```

The `services/` directory is **deleted** once all logic has been moved to the flat modules above.

---

## 3. Module Responsibilities

| File | Contents | Key Exports |
|---|---|---|
| `app.py` | `FastAPI()` creation, CORS middleware, Prometheus Instrumentator, pyinstrument profiler middleware, `include_router` calls for all route modules | `app` |
| `main.py` | Compatibility shim: `from app import app` | `app` (re-export), `__main__` block for uvicorn |
| `config.py` | All env vars (`GALLERY_ROOT`, `PRODUCTION`, `THUMBNAIL_CACHE_DIR`, `METADATA_DB_DIR`, etc.), constants, cache directory creation | `GALLERY_ROOT`, `PRODUCTION`, `THUMBNAIL_CACHE_DIR`, `METADATA_DB_DIR`, `SCAN_PERF_LOGS_ENABLED`, … |
| `errors.py` | `APIError`, `ErrorType` enum, error response helpers | `APIError`, `ErrorType` |
| `models.py` | Pydantic `FileNode` and any shared request/response schemas | `FileNode` |
| `paths.py` | `resolve_path`, `is_path_safe`, path traversal prevention, GALLERY_ROOT boundary checks | `resolve_path`, `is_path_safe` |
| `files.py` | `is_image`, `natural_sort_key`, `IMAGE_EXTENSIONS`, `_check_image_limits`, `_has_alpha` | `is_image`, `natural_sort_key`, `IMAGE_EXTENSIONS`, `_check_image_limits`, `_has_alpha` |
| `albums.py` | `build_album_metadata`, `has_subfolders`, album cover/child detection (moved from `services/album_utils.py`) | `build_album_metadata`, `has_subfolders` |
| `scan.py` | `GET /api/scan`, `scan_directory`, `SCAN_PERF_LOGS`, `_new_scan_perf`, `_elapsed_ms` | `router` (APIRouter) |
| `folders.py` | `GET /api/folders`, `POST /api/open-folder`, `GALLERY_OPEN_FOLDER` guard | `router` |
| `images.py` | `GET /api/image`, original file serving with cache/header/range support | `router` |
| `thumbnails.py` | `GET /api/thumbnail`, generation, persistent disk cache (`_thumbnail_disk_cache`), ETag/304, WebP, large-image safety | `router` |
| `metadata_extract.py` | Raw metadata extraction from PNG/JPEG/WebP image files, A1111/ComfyUI/NovelAI/EasyDiffusion/SwarmUI parameter parsing, `extract_loras`, `_read_image_info` — NO SQLite imports, NO API response formatting | `extract_loras`, `_read_image_info`, parameter parsing helpers |
| `metadata_parse.py` | `GET /api/metadata` route, rich AI metadata parsers, in-memory LRU cache (`_metadata_cache`), imports from `metadata_extract.py` for raw parsing and `metadata_store.py` for cache upsert | `router`, `_metadata_cache` |
| `metadata_store.py` | SQLite metadata cache, FTS5 index/search, `metadata_index` tables, DB init/migration, WAL/busy_timeout (moved from `services/metadata_index.py`), imports from `metadata_extract.py` for background indexing | `MetadataIndex`, `get_index`, DB helpers |
| `search.py` | `GET /api/search`, `GET /api/search-metadata`, search orchestration calling `metadata_store.py` and scan/file helpers | `router` |
| `health.py` | `GET /api/health`, favicon, `GIT_COMMIT` constant | `router`, `GIT_COMMIT` |
| `static_files.py` | `GET /` (root), `GET /api/landing-pages`, production Vue SPA static file serving + fallback | `router` |

---

## 4. Metadata Module Architecture

### 4.1 The circular-import problem

Before the split, `metadata_parse.py` needs to upsert into the SQLite cache (owned by `metadata_store.py`), and `metadata_store.py` needs to parse raw metadata from images (owned by `metadata_parse.py`). This creates a two-way import dependency.

### 4.2 Solution: three-file split

```
metadata_extract.py   ← LOWEST layer (no SQLite, no API formatting)
        ↑                        ↑
        |                        |
metadata_parse.py          metadata_store.py
  /api/metadata route        SQLite cache + FTS5 index/search
  in-memory LRU cache
  imports metadata_extract    imports metadata_extract
  imports metadata_store        for background indexing
    for cache upsert
```

### 4.3 Import direction (arrow = "imports from")

```
metadata_extract.py       ← used by both parse and store
metadata_store.py         ← used by parse (cache upsert) and search
metadata_parse.py         ← used by no other module for its internals
```

No module imports a module that imports it. The cycle is broken by extracting shared raw-parsing logic into the lowest layer that has no internal imports.

### 4.4 What goes where

**metadata_extract.py** (lowest layer)
- `_read_image_info()` — read raw PNG/JPEG/WebP metadata chunks
- A1111 / ComfyUI / NovelAI / EasyDiffusion / SwarmUI parameter parsing
- `extract_loras(text: str) -> list[str]`
- PNG tEXt chunk, EXIF UserComment, WebP/JPEG metadata extraction
- **No** SQLite imports, **no** `FileResponse`/`JSONResponse`, **no** FastAPI route decorators

**metadata_store.py** (middle layer)
- Moved from `services/metadata_index.py`
- `MetadataIndex` class: SQLite connection, table init, FTS5 triggers
- `get_index()` singleton factory
- `index_file()`, `search()`, `delete_file()`, background indexing helpers
- Imports `metadata_extract` for reading raw metadata during indexing
- **No** HTTP route decorators, **no** API response formatting

**metadata_parse.py** (top / API layer)
- `GET /api/metadata` route
- Rich AI metadata parsing and response construction
- In-memory LRU cache (`_metadata_cache` + `_metadata_cache_lock`)
- `_metadata_cache_key()` helper
- Imports `metadata_extract` for raw parsing
- Imports `metadata_store` for `get_index().upsert()` after successful parse

---

## 5. Other Key Decisions

### 5.1 Prometheus + pyinstrument setup location

Prometheus `Instrumentator` and pyinstrument `Profiler` middleware are configured in `app.py`, right after `app = FastAPI()`. They are currently embedded in `main.py`; this refactor moves them to the proper app-composition module. The `main.py` shim does NOT touch them.

### 5.2 `is_image` and `IMAGE_EXTENSIONS` live in `files.py`

Currently `is_image` and `has_subfolders` are in `services/album_utils.py`, and a separate `is_image_path` + `IMAGE_EXTENSIONS` live in `services/metadata_index.py`. After the refactor there is a single canonical `is_image` and `IMAGE_EXTENSIONS` in `files.py`. All modules that need image-type checks import from `files.py`.

### 5.3 `_check_image_limits` in `files.py`

Moves from `main.py` to `files.py` alongside the other file-level helpers.

### 5.4 `SCAN_PERF_LOGS` in `scan.py`

The `SCAN_PERF_LOGS_ENABLED` flag and the `_new_scan_perf()` / `_elapsed_ms()` helpers live in `scan.py`, not in `config.py` or a separate perf module.

### 5.5 `GIT_COMMIT` in `health.py`

The `_get_git_commit()` helper and `GIT_COMMIT` constant move to `health.py` alongside the `/api/health` route that uses them.

### 5.6 `_thumbnail_disk_cache` in `thumbnails.py`

The `diskcache.Cache` instance for thumbnail persistence is created in `thumbnails.py` as a module-level variable.

### 5.7 `/api/landing-pages` in `static_files.py`

This route lives in `static_files.py` alongside the root `/` route and production SPA fallback.

### 5.8 `services/` directory deletion

After all logic is moved to the flat modules, the entire `backend/services/` directory is deleted. There is no "temporary compatibility wrapper" kept past the final commit.

### 5.9 `start.py` needs NO changes

The existing `start.py` continues to work because `backend/main.py` remains a valid entrypoint shim.

---

## 6. Dependency Graph (Import DAG)

Text DAG showing import direction (arrow = "imports from"):

```
app.py
├── config.py
├── errors.py
├── scan.py ─────────────► files.py, paths.py, albums.py, metadata_store.py
├── folders.py ──────────► paths.py, files.py, albums.py
├── images.py ───────────► paths.py, files.py, errors.py
├── thumbnails.py ───────► paths.py, files.py, config.py, errors.py
├── metadata_parse.py ───► metadata_extract.py, metadata_store.py, files.py,
│                          config.py, errors.py
├── metadata_store.py ───► metadata_extract.py, config.py
├── search.py ───────────► metadata_store.py, paths.py, files.py
├── health.py ───────────► (standalone + GIT_COMMIT)
└── static_files.py ─────► config.py

metadata_extract.py   ← no internal imports (stdlib-only + Pillow)
metadata_store.py     ← metadata_extract.py, config.py
metadata_parse.py     ← metadata_extract.py, metadata_store.py, files.py, config.py
```

No circular imports exist in this graph.

---

## 7. Commit Strategy (5 commits)

**Commit 1** — Foundation modules
- Create `config.py`, `errors.py`, `models.py`, `paths.py`, `files.py`
- Extract from `main.py` and `services/` into these modules
- Update `main.py` to import from new modules
- No API behaviour change

**Commit 2** — Service migrations
- Move `services/album_utils.py` → `albums.py`, update imports
- Add `metadata_extract.py` (raw extraction primitives extracted from `main.py`)
- Move `services/metadata_index.py` → `metadata_store.py`, update import paths
- Delete `services/` directory

**Commit 3** — Core route modules
- Create `images.py`, `thumbnails.py`, `metadata_parse.py`
- Extract route handlers from `main.py`
- Wire routers in `app.py`
- Move `_thumbnail_disk_cache` to `thumbnails.py`, `_metadata_cache` to `metadata_parse.py`

**Commit 4** — Remaining route modules
- Create `scan.py`, `folders.py`, `search.py`, `health.py`, `static_files.py`
- Extract remaining route handlers from `main.py`
- Wire routers in `app.py`
- Move Prometheus/pyinstrument setup to `app.py`
- Move `SCAN_PERF_LOGS` to `scan.py`, `GIT_COMMIT` to `health.py`
- Verify all routes are registered

**Commit 5** — Tests, docs, cleanup
- Add backend smoke tests under `backend/test/` if not present
- Update `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT.md` with new module map
- Verify `backend/main.py` is reduced to a compatibility shim
- Final validation pass

---

## 8. Validation Checklist

- [ ] `python -c "from backend.app import app"` succeeds
- [ ] `python -c "from backend.main import app"` succeeds
- [ ] All routes registered: `/api/scan`, `/api/folders`, `/api/image`, `/api/thumbnail`, `/api/metadata`, `/api/search`, `/api/search-metadata`, `/api/open-folder`, `/api/health`, `/api/landing-pages`, `/`, favicon
- [ ] `GET /api/health` returns commit hash and status
- [ ] Unsafe path traversal is rejected (`..`, absolute paths outside `GALLERY_ROOT`)
- [ ] Missing/invalid thumbnail path does not crash the backend
- [ ] `services/` directory no longer exists
- [ ] No circular imports detected
- [ ] `start.py` starts the app without modification
- [ ] Lint/typecheck pass (if configured)
- [ ] Existing smoke/perf tests pass

---

## 9. Acceptance Criteria

1. Backend starts successfully via `python backend/main.py` and `start.py`.
2. Existing frontend can call every backend API with identical behaviour.
3. No API route path changes, no response shape changes.
4. No thumbnail generation/caching behaviour changes.
5. No metadata parsing behaviour changes.
6. No scan output or search output behaviour changes.
7. `backend/main.py` is reduced to a small compatibility shim (`from app import app`).
8. `backend/app.py` is small and only composes the backend (no business logic).
9. No vague names (`helper`, `common`, `manager`, `processor`, `service`, `utils`) introduced.
10. The flat module structure matches the target layout above.
11. Docs (`ARCHITECTURE.md`, `DEVELOPMENT.md`) reflect the new structure.
12. `services/` directory is fully deleted.
13. No circular imports anywhere in the graph.
