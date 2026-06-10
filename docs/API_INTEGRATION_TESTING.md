# API Integration Testing

## Architecture

The backend integration tests use a fully isolated environment:

- **GALLERY_ROOT** → tmp_path/gallery_root (no access to real filesystem)
- **GALLERY_METADATA_DB** → tmp_path/test_metadata.db (no shared DB state)
- **GALLERY_THUMBNAIL_CACHE_DIR** → tmp_path/thumbnail_cache (no shared disk cache)
- **Indexer/Watcher/Refresh** → disabled (deterministic, no background threads)
- **Warm indexed listing** → disabled (tests control DB state explicitly)

## Fixture Hierarchy

```
isolated_gallery_root   isolated_metadata_db   isolated_thumbnail_cache   disable_background_services
        \                    |                          |                          /
         \                   |                          |                         /
          \__________________|__________________________|________________________/
                             |
                        isolated_app (TestClient)
                             |
                    temp_gallery / temp_gallery_with_metadata
```

## Writing New Tests

### Basic pattern

```python
class TestYourFeature:
    def test_something(self, isolated_app: TestClient, temp_gallery: Path):
        resp = isolated_app.get("/api/scan", params={"path": str(temp_gallery)})
        assert resp.status_code == 200
```

### Search / metadata tests need DB seeding

```python
from backend.metadata_store import index_directory_tree

def _seed(gallery_root: Path):
    index_directory_tree(gallery_root, include_metadata=True)

class TestSearch:
    def test_search(self, isolated_app, temp_gallery_with_metadata):
        _seed(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "mika", "scope": "all"})
```

### Creating test images

```python
from .conftest import create_test_png, create_test_png_with_metadata

# Plain PNG
create_test_png(path, size=(800, 600))

# PNG with embedded AI metadata (A1111-style parameters chunk)
create_test_png_with_metadata(
    path,
    prompt="masterpiece, 1girl",
    negative_prompt="blurry",
    model="ponyDiffusionV6XL",
    sampler="Euler a",
    seed="12345",
    steps=30,
    cfg_scale=7.0,
    size=(1024, 1536),
)
```

## Test Isolation Details

### Why `GALLERY_ROOT` must be patched in multiple modules

Several backend modules import `GALLERY_ROOT` from `config.py` at module level:
- `backend.paths` — for `is_path_safe()`
- `backend.metadata_store` — for `search_index()` scope clauses
- `backend.facets` — for facet scope
- `backend.search` — for search scope

Each must be monkeypatched individually by `isolated_gallery_root`.

### Why `_DB_INITIALIZED` must be reset

`metadata_store.initialize_database()` caches its init state via `_DB_INITIALIZED`
and `_DB_INITIALIZED_PATH` globals. Each test gets a fresh DB path, so these must
be reset to force re-initialization.

### Running Tests

```bash
# All backend tests (existing + new)
cd backend && pytest -q

# Just the API integration tests
cd backend && pytest tests/test_api_integration_*.py -v

# A single test file
cd backend && pytest tests/test_api_integration_scan.py -v
```

## Test File Reference

| File | Tests | What It Covers |
|---|---|---|
| `test_api_integration_health_and_safety.py` | 9 | Health endpoint, path safety, 403/404/400 responses |
| `test_api_integration_scan.py` | 17 | Response shape, filtering, natural sort, pagination, hot path |
| `test_api_integration_derivatives.py` | 17 | Image/thumbnail/preview, cache headers, ETag/304, cache separation |
| `test_api_integration_metadata_search_facets.py` | 21 | Metadata parsing, plain search, fielded search, facets |
| `test_api_integration_index_status.py` | 7 | Index status with enabled/disabled indexer, empty state |
