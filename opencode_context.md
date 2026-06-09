# Task: Implement backend refactor per REFACTOR_PLAN.md

You are in /home/ubuntu/gallery-repo. Read REFACTOR_PLAN.md first — the final plan the user approved.

Then read ALL current source files:
- backend/main.py (full ~1500 lines)
- backend/services/album_utils.py
- backend/services/metadata_index.py
- backend/requirements.txt
- docs/ARCHITECTURE.md
- docs/DEVELOPMENT.md
- backend/services/__init__.py
- backend/__init__.py (if exists)
- start.py

## CRITICAL RULES

1. Pure refactor — do NOT change API behavior, response shapes, status codes, query params, cache behavior, path behavior.
2. Do NOT touch frontend/ at all.
3. Do NOT introduce vague names (helper.py, common.py, manager.py, utils.py).
4. Follow the import DAG in section 6 of REFACTOR_PLAN.md EXACTLY to avoid circular imports.
5. Keep metadata_extract.py as the LOWEST layer — no SQLite imports, no FastAPI route decorators, no API response formatting.
6. metadata_extract.py must NOT import metadata_parse.py or metadata_store.py.
7. metadata_store.py imports metadata_extract.py (for extract_metadata during background indexing), NOT vice versa.
8. app.py must include static_files_router LAST.
9. main.py must support both `from .app import app` and `from app import app` (try/except). Must include `if __name__ == "__main__"` uvicorn block.
10. Delete services/ directory only after all code is moved (Commit 4 or 5).
11. Start.py needs NO changes.

## COMMIT 1 — Foundation modules

Create these files extracted from main.py and services/:

### config.py
All env vars, constants, cache dirs. Move from main.py:
- `_env_flag()`, `ENABLE_METRICS`, `ENABLE_PROFILER`, `PROFILE_ENDPOINTS`, `PROFILE_DIR`
- `METADATA_CACHE_MAX_BYTES`, `THUMBNAIL_CACHE_DIR`, `SCAN_PERF_LOGS_ENABLED` (env flag, keep the env logic)
- `GALLERY_ROOT`, `DEFAULT_ROOT`, `MAX_IMAGE_FILE_BYTES`, `MAX_IMAGE_PIXELS`
- `PRODUCTION`, `FRONTEND_DIST`, `OPEN_FOLDER_ENABLED`
- Import Path, os. Export everything as constants.

### errors.py
Move from main.py:
- `APIError` class, `ErrorType` class

### models.py
Move from main.py:
- `FileNode` Pydantic model (exactly as-is, same fields/defaults)

### paths.py
Move from main.py:
- `resolve_path()`, `is_path_safe()` (using GALLERY_ROOT from config)

### files.py
Move from main.py:
- `natural_sort_key()`
- `is_image()` from services/album_utils.py
- `IMAGE_EXTENSIONS` from services/metadata_index.py (single canonical set)
- `check_image_limits()` from main.py (rename from `_check_image_limits`)

DO NOT update main.py imports yet — just create these files.

Commit: git add -A && git commit -m "refactor: extract foundation modules (config, errors, models, paths, files)"

## COMMIT 2 — Service migrations

### Create albums.py
Copy services/album_utils.py content exactly. Keep `build_album_metadata()`, `has_subfolders()`, `has_any_children()`. Update imports: import `is_image` and `IMAGE_EXTENSIONS` from `files.py` instead of defining locally.

### Create metadata_extract.py
Extract from main.py and services/metadata_index.py the LOWEST-LEVEL raw metadata primitives:
- From services/metadata_index.py: `_read_image_info()`, `_safe_text()`, `_parse_int()`, `_parse_float()`, `_first_match()`, `parse_a1111_parameters()`, `_parse_comfy_text()`, `_json_text_summary()`, `GENERIC_TEXT_KEYS`, `_has_alpha()`, `contains_cjk()`, `CJK_RE`
- From main.py: `extract_loras()`, `LORA_PATTERN`
- Keep `extract_metadata()` here (the function that opens PIL and returns ExtractedMetadata)
- Keep `ExtractedMetadata` dataclass (with format, mode, has_alpha fields added earlier)
- Import ONLY from PIL, stdlib, and files.py as needed
- NO SQLite imports, NO FastAPI imports

### Create metadata_store.py
Rename services/metadata_index.py → metadata_store.py. Update:
- Import `extract_metadata`, `ExtractedMetadata`, `extract_loras`, `_safe_text`, `_parse_int`, `_parse_float`, `contains_cjk`, `CJK_RE` from metadata_extract.py instead of defining locally
- Import `build_album_metadata` from albums.py instead of services.album_utils
- Import `is_image_path`, `IMAGE_EXTENSIONS` from files.py
- Keep everything else: `_connect()`, `initialize_database()`, `index_image()`, `index_images()`, `index_file()`, `index_files_from_scan()`, `index_directory_tree()`, `search_metadata()`, `search_index()`, `cleanup_stale_index()`, `_DB_LOCK`, `DB_PATH`, `get_cached_dimensions_for_files`, `upsert_image_dimensions`, `upsert_metadata_result`, `CachedDimensions`
- Add `GALLERY_METADATA_DB` env var to config.py and import from there instead of hardcoded path

### Delete services/ directory
Remove backend/services/ and its __init__.py.

Commit: git add -A && git commit -m "refactor: migrate services to flat modules, add metadata_extract layer"

## COMMIT 3 — Core route modules

### Create images.py
- GET /api/image route from main.py
- `router = APIRouter()`
- Import from paths.py, files.py, errors.py, config.py
- Preserve ETag, Cache-Control, FileResponse exactly

### Create thumbnails.py
- GET /api/thumbnail route from main.py
- `_thumbnail_cache_key_str()`, `_thumbnail_cache_file_path()`, `_persist_thumbnail_file()`, `_thumbnail_disk_cache`, `_thumbnail_file_dir`
- `_render_thumbnail_impl()`, `generate_thumbnail()`
- Import from paths.py, files.py, errors.py, config.py, metadata_store.py (for upsert_image_dimensions)
- Import PIL, diskcache, hashlib as needed

### Create metadata_parse.py
- GET /api/metadata route from main.py
- In-memory LRU cache: `_metadata_cache`, `_metadata_cache_lock`, `_metadata_inflight`, `_metadata_cache_key()`
- Rich parsers from main.py: `_parse_metadata_uncached()`, `parse_metadata()`, `parse_ai_text_parameters()`, `parse_comfy()`, `_parse_novelai_metadata()`, `_parse_easydiffusion_metadata()`
- `_estimate_dict_size()`
- Import from metadata_extract.py for raw parsing
- Import from metadata_store.py for upsert_metadata_result, upsert_image_dimensions
- Import from paths.py, files.py, errors.py, config.py

### Update main.py to include routers via app.py
- Create app.py: FastAPI(), CORS, include_routers from all modules created so far
- Add Prometheus + pyinstrument setup in app.py after app creation
- Reduce main.py to compatibility shim

Commit: git add -A && git commit -m "refactor: extract images, thumbnails, metadata_parse into route modules"

## COMMIT 4 — Remaining route modules

### Create scan.py
- GET /api/scan route + scan_directory() from main.py
- `_new_scan_perf()`, `_elapsed_ms()`
- Import from paths.py, files.py, errors.py, models.py, config.py (SCAN_PERF_LOGS_ENABLED), albums.py, metadata_store.py (get_cached_dimensions_for_files)
- register router

### Create folders.py
- GET /api/folders + POST /api/open-folder from main.py
- list_folder_children()
- Import from paths.py, errors.py, models.py, files.py, albums.py, config.py

### Create search.py
- GET /api/search + GET /api/search-metadata from main.py
- Import from metadata_store.py, paths.py, errors.py, config.py

### Create health.py
- GET /api/health + favicon from main.py
- `GIT_COMMIT`, `_get_git_commit()` from main.py

### Create static_files.py
- GET / + SPA fallback + GET /api/landing-pages from main.py
- Must bypass/404 paths starting with /api/ in the fallback handler
- Import from config.py

### Update app.py
- Add all new routers: scan, folders, search, health, static_files (LAST)

### Clean up main.py
- Remove ALL route handlers, ALL business logic
- Keep only: from .app import app / from app import app + __main__ uvicorn block

Commit: git add -A && git commit -m "refactor: extract remaining route modules, finalize app.py and main.py shim"

## COMMIT 5 — Tests + docs

### Smoke tests
Create backend/tests/ with test_app.py:
```python
from backend.app import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

def test_unsafe_path_rejected():
    resp = client.get("/api/metadata?path=../../etc/passwd")
    assert resp.status_code == 403

def test_routes_registered():
    routes = [r.path for r in app.routes]
    assert "/api/scan" in routes
    assert "/api/metadata" in routes
    assert "/api/thumbnail" in routes
    assert "/api/health" in routes
    assert "/api/search" in routes
    assert "/api/folders" in routes
    assert "/api/image" in routes

def test_main_shim():
    from backend.main import app as main_app
    assert main_app is app
```

### Update docs
Update docs/ARCHITECTURE.md to replace the old backend table with the new flat module structure.
Update docs/DEVELOPMENT.md if it references old structure.

### Final validation
- `python -c "from backend.app import app"` ✓
- `python -c "from backend.main import app"` ✓
- `python -m compileall backend` ✓ (no syntax errors)
- All routes registered
- services/ directory gone
- No circular imports (check at runtime)

Commit: git add -A && git commit -m "refactor: add smoke tests, update docs, final cleanup"

## AFTER ALL COMMITS: git push origin main

Do NOT modify any frontend files. Do NOT change API behavior.
