import os
from pathlib import Path

from PIL import Image


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


ENABLE_METRICS = _env_flag("ENABLE_METRICS", default=os.getenv("PRODUCTION") != "1")
ENABLE_PROFILER = _env_flag("ENABLE_PROFILER", default=False)
PROFILE_ENDPOINTS = {
    endpoint.strip()
    for endpoint in os.getenv("PROFILE_ENDPOINTS", "/api/scan,/api/metadata,/api/thumbnail,/api/preview").split(",")
    if endpoint.strip()
}
PROFILE_DIR = Path(__file__).resolve().parent / "profiles"

METADATA_CACHE_MAX_BYTES = 100 * 1024 * 1024         # 100 MB

_thumbnail_cache_env = os.getenv("GALLERY_THUMBNAIL_CACHE_DIR")
THUMBNAIL_CACHE_DIR = Path(_thumbnail_cache_env) if _thumbnail_cache_env else Path(__file__).resolve().parent / ".cache" / "thumbnails"

SCAN_PERF_LOGS_ENABLED = os.getenv("SCAN_PERF_LOGS", "1" if os.getenv("PRODUCTION") != "1" else "0").lower() not in {"0", "false", "no"}

GALLERY_ROOT = Path(os.getenv("GALLERY_ROOT", "/")).resolve()
DEFAULT_ROOT = GALLERY_ROOT

METADATA_INDEXER_ENABLED = _env_flag("GALLERY_METADATA_INDEXER_ENABLED", default=True)
METADATA_INDEXER_BATCH_SIZE = max(1, min(int(os.getenv("GALLERY_METADATA_INDEXER_BATCH_SIZE", "8")), 64))
METADATA_INDEXER_WORKER_SLEEP_SECONDS = max(0.0, float(os.getenv("GALLERY_METADATA_INDEXER_WORKER_SLEEP_SECONDS", "0.01")))
METADATA_INDEXER_STAGE_BATCH_SIZE = max(
    1,
    min(
        int(os.getenv("GALLERY_METADATA_INDEXER_STAGE_BATCH_SIZE", os.getenv("METADATA_INDEXER_STAGE_BATCH_SIZE", "100"))),
        1000,
    ),
)
METADATA_INDEXER_STAGE_SLEEP_SECONDS = max(
    0.0,
    float(os.getenv("GALLERY_METADATA_INDEXER_STAGE_SLEEP_SECONDS", os.getenv("METADATA_INDEXER_STAGE_SLEEP_SECONDS", "0.2"))),
)
METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS = max(
    0.0,
    float(os.getenv("GALLERY_METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS", os.getenv("METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS", "5.0"))),
)
METADATA_INDEXER_SCAN_YIELD_SECONDS = max(
    0.0,
    float(os.getenv("GALLERY_METADATA_INDEXER_SCAN_YIELD_SECONDS", os.getenv("METADATA_INDEXER_SCAN_YIELD_SECONDS", "0.05"))),
)
METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS = max(
    0.0,
    float(os.getenv("GALLERY_METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS", os.getenv("METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS", "1.0"))),
)
METADATA_INDEXER_SQLITE_BUSY_RETRIES = max(
    0,
    int(os.getenv("GALLERY_METADATA_INDEXER_SQLITE_BUSY_RETRIES", os.getenv("METADATA_INDEXER_SQLITE_BUSY_RETRIES", "3"))),
)
METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS = max(
    0.0,
    float(
        os.getenv(
            "GALLERY_METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS",
            os.getenv("METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS", "0.1"),
        )
    ),
)

MAX_IMAGE_FILE_BYTES = 75 * 1024 * 1024   # 75 MB
MAX_IMAGE_PIXELS = 100 * 1024 * 1024      # 100 megapixels
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

PRODUCTION = os.getenv("PRODUCTION", "0") == "1"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

OPEN_FOLDER_ENABLED = os.getenv("GALLERY_OPEN_FOLDER", "false").lower() == "true"

_metadata_db_env = os.getenv("GALLERY_METADATA_DB")
if _metadata_db_env:
    GALLERY_METADATA_DB = Path(_metadata_db_env)
else:
    METADATA_DB_DIR = Path(__file__).resolve().parent / ".cache"
    GALLERY_METADATA_DB = METADATA_DB_DIR / "gallery_metadata.db"

# ---------------------------------------------------------------------------
# Phase 3 — Warm indexed folder listing
# ---------------------------------------------------------------------------
ENABLE_WARM_INDEXED_LISTING = _env_flag("ENABLE_WARM_INDEXED_LISTING", default=False)

# ---------------------------------------------------------------------------
# Phase 3 — Scheduled refresh
# ---------------------------------------------------------------------------
ENABLE_SCHEDULED_REFRESH = _env_flag("ENABLE_SCHEDULED_REFRESH", default=False)
SCHEDULED_REFRESH_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("SCHEDULED_REFRESH_INTERVAL_SECONDS", "300")),
)
SCHEDULED_REFRESH_ROOTS = [
    p.strip()
    for p in os.getenv("SCHEDULED_REFRESH_ROOTS", "").split(",")
    if p.strip()
]
SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK = max(
    1,
    int(os.getenv("SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", "20")),
)
SCHEDULED_REFRESH_ALLOW_ALL_INDEXED = _env_flag("SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", default=False)

# ---------------------------------------------------------------------------
# Phase 3 — Optional file watcher (disabled by default)
# ---------------------------------------------------------------------------
ENABLE_FILE_WATCHER = _env_flag("ENABLE_FILE_WATCHER", default=False)
WATCHER_ROOTS = [
    p.strip()
    for p in os.getenv("WATCHER_ROOTS", "").split(",")
    if p.strip()
]
WATCHER_DEBOUNCE_SECONDS = max(0.0, float(os.getenv("WATCHER_DEBOUNCE_SECONDS", "2.0")))
WATCHER_MAX_EVENTS_PER_TICK = max(1, int(os.getenv("WATCHER_MAX_EVENTS_PER_TICK", "500")))
