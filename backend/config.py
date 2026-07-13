"""Read environment-backed backend configuration constants."""

import os
import warnings
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
    for endpoint in os.getenv("PROFILE_ENDPOINTS", "/api/browse,/api/metadata,/api/thumbnail,/api/preview").split(",")
    if endpoint.strip()
}
PROFILE_DIR = Path(__file__).resolve().parent / "profiles"

METADATA_CACHE_MAX_BYTES = 100 * 1024 * 1024  # 100 MB
METADATA_SIDECAR_MAX_BYTES = max(
    0,
    int(os.getenv("GALLERY_METADATA_SIDECAR_MAX_BYTES", str(1024 * 1024))),
)

_thumbnail_cache_env = os.getenv("GALLERY_THUMBNAIL_CACHE_DIR")
THUMBNAIL_CACHE_DIR = (
    Path(_thumbnail_cache_env) if _thumbnail_cache_env else Path(__file__).resolve().parent / ".cache" / "thumbnails"
)
DERIVATIVE_WORKER_COUNT = max(1, min(int(os.getenv("DERIVATIVE_WORKER_COUNT", "3")), 8))
DERIVATIVE_QUOTA_BYTES = max(
    0,
    int(os.getenv("GALLERY_DERIVATIVE_QUOTA_BYTES", str(10 * 1024**3))),
)
DERIVATIVE_VARIANTS = {
    "thumbnail": [
        {"name": "thumb_128", "max_long_edge": 128, "quality": 78},
        {"name": "thumb_512", "max_long_edge": 512, "quality": 78},
    ],
    "preview": [{"name": "preview_1440", "max_long_edge": 1440, "quality": 86}],
}
DERIVATIVE_RECONCILE_ENABLED = _env_flag("GALLERY_DERIVATIVE_RECONCILE_ENABLED", default=True)
DERIVATIVE_RECONCILE_INTERVAL_SECONDS = max(
    300, int(os.getenv("GALLERY_DERIVATIVE_RECONCILE_INTERVAL_SECONDS", "21600"))
)
DERIVATIVE_RECONCILE_BATCH_SIZE = max(25, min(int(os.getenv("GALLERY_DERIVATIVE_RECONCILE_BATCH_SIZE", "250")), 2000))
DERIVATIVE_RECONCILE_YIELD_SECONDS = max(0.0, float(os.getenv("GALLERY_DERIVATIVE_RECONCILE_YIELD_SECONDS", "0.02")))
DERIVATIVE_JOB_LEASE_SECONDS = max(
    30,
    int(os.getenv("GALLERY_DERIVATIVE_JOB_LEASE_SECONDS", "900")),
)
DERIVATIVE_LEASE_HEARTBEAT_SECONDS = min(
    DERIVATIVE_JOB_LEASE_SECONDS / 3.0,
    max(5.0, float(os.getenv("GALLERY_DERIVATIVE_LEASE_HEARTBEAT_SECONDS", str(DERIVATIVE_JOB_LEASE_SECONDS / 3.0)))),
)
DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", "30")),
)
VIDEO_POSTER_MAX_CONCURRENCY = max(1, int(os.getenv("GALLERY_VIDEO_POSTER_MAX_CONCURRENCY", "2")))
VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS = max(
    0.0,
    float(os.getenv("GALLERY_VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS", "5")),
)
VIDEO_POSTER_QUOTA_BYTES = max(
    0,
    int(os.getenv("GALLERY_VIDEO_POSTER_QUOTA_BYTES", str(1024**3))),
)
CATALOG_SHUTDOWN_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("GALLERY_CATALOG_SHUTDOWN_TIMEOUT_SECONDS", "30")),
)
CATALOG_JOB_LEASE_SECONDS = max(
    30,
    int(os.getenv("GALLERY_CATALOG_JOB_LEASE_SECONDS", "900")),
)
CATALOG_LEASE_HEARTBEAT_SECONDS = min(
    CATALOG_JOB_LEASE_SECONDS / 3.0,
    max(
        5.0,
        float(
            os.getenv(
                "GALLERY_CATALOG_LEASE_HEARTBEAT_SECONDS",
                str(CATALOG_JOB_LEASE_SECONDS / 3.0),
            )
        ),
    ),
)
SCAN_PERF_LOGS_ENABLED = os.getenv("SCAN_PERF_LOGS", "1" if os.getenv("PRODUCTION") != "1" else "0").lower() not in {
    "0",
    "false",
    "no",
}

_raw = os.getenv("PATH_SAFETY_ROOT") or os.getenv("GALLERY_ROOT") or "/"
if "GALLERY_ROOT" in os.environ and "PATH_SAFETY_ROOT" not in os.environ:
    warnings.warn(
        "GALLERY_ROOT is deprecated. Use PATH_SAFETY_ROOT. "
        "It is only a path-safety boundary and never creates a library.",
        DeprecationWarning,
        stacklevel=2,
    )
PATH_SAFETY_ROOT = Path(_raw).resolve()

METADATA_INDEXER_ENABLED = _env_flag("GALLERY_METADATA_INDEXER_ENABLED", default=True)
METADATA_INDEXER_BATCH_SIZE = max(1, min(int(os.getenv("GALLERY_METADATA_INDEXER_BATCH_SIZE", "8")), 64))
METADATA_INDEXER_WORKER_SLEEP_SECONDS = max(
    0.0, float(os.getenv("GALLERY_METADATA_INDEXER_WORKER_SLEEP_SECONDS", "0.01"))
)
METADATA_INDEXER_STAGE_BATCH_SIZE = max(
    1,
    min(
        int(
            os.getenv(
                "GALLERY_METADATA_INDEXER_STAGE_BATCH_SIZE", os.getenv("METADATA_INDEXER_STAGE_BATCH_SIZE", "100")
            )
        ),
        1000,
    ),
)
METADATA_INDEXER_STAGE_SLEEP_SECONDS = max(
    0.0,
    float(
        os.getenv(
            "GALLERY_METADATA_INDEXER_STAGE_SLEEP_SECONDS", os.getenv("METADATA_INDEXER_STAGE_SLEEP_SECONDS", "0.2")
        )
    ),
)
METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS = max(
    0.0,
    float(
        os.getenv(
            "GALLERY_METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS",
            os.getenv("METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS", "5.0"),
        )
    ),
)
METADATA_INDEXER_SCAN_YIELD_SECONDS = max(
    0.0,
    float(
        os.getenv(
            "GALLERY_METADATA_INDEXER_SCAN_YIELD_SECONDS", os.getenv("METADATA_INDEXER_SCAN_YIELD_SECONDS", "0.05")
        )
    ),
)
METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS = max(
    0.0,
    float(
        os.getenv(
            "GALLERY_METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS",
            os.getenv("METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS", "1.0"),
        )
    ),
)
METADATA_INDEXER_SQLITE_BUSY_RETRIES = max(
    0,
    int(
        os.getenv(
            "GALLERY_METADATA_INDEXER_SQLITE_BUSY_RETRIES", os.getenv("METADATA_INDEXER_SQLITE_BUSY_RETRIES", "3")
        )
    ),
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

MAX_IMAGE_FILE_BYTES = 75 * 1024 * 1024  # 75 MB
MAX_IMAGE_PIXELS = 100 * 1024 * 1024  # 100 megapixels
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

PRODUCTION = os.getenv("PRODUCTION", "0") == "1"
GALLERY_TRUSTED_PROXY_SECRET = os.getenv("GALLERY_TRUSTED_PROXY_SECRET", "")
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

OPEN_FOLDER_ENABLED = os.getenv("GALLERY_OPEN_FOLDER", "false").lower() == "true"

_metadata_db_env = os.getenv("GALLERY_METADATA_DB")
if _metadata_db_env:
    GALLERY_METADATA_DB = Path(_metadata_db_env)
else:
    METADATA_DB_DIR = Path(__file__).resolve().parent / ".cache"
    GALLERY_METADATA_DB = METADATA_DB_DIR / "gallery_metadata.db"

# ---------------------------------------------------------------------------
# Warm indexed folder listing (optional, disabled by default)
# ---------------------------------------------------------------------------
ENABLE_WARM_INDEXED_LISTING = _env_flag("ENABLE_WARM_INDEXED_LISTING", default=False)

# ---------------------------------------------------------------------------
# Catalog scan pipeline
# ---------------------------------------------------------------------------
GALLERY_CATALOG_WORKERS = max(1, min(int(os.getenv("GALLERY_CATALOG_WORKERS", "1")), 8))
GALLERY_CATALOG_SERVICE_ENABLED = _env_flag("GALLERY_CATALOG_SERVICE_ENABLED", default=True)
GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED = _env_flag("GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED", default=True)
GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS = max(
    0,
    int(os.getenv("GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS", "600")),
)
GALLERY_CATALOG_WRITE_BATCH_SIZE = max(
    1,
    int(os.getenv("GALLERY_CATALOG_WRITE_BATCH_SIZE", "500")),
)

# ---------------------------------------------------------------------------
# Durable derived search indexes
# ---------------------------------------------------------------------------
GALLERY_SEARCH_INDEXER_ENABLED = _env_flag("GALLERY_SEARCH_INDEXER_ENABLED", default=True)
GALLERY_SEARCH_INDEX_BATCH_SIZE = min(200, max(1, int(os.getenv("GALLERY_SEARCH_INDEX_BATCH_SIZE", "200"))))
GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS = max(
    30,
    int(os.getenv("GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS", "300")),
)
GALLERY_SEARCH_INDEX_POLL_SECONDS = max(
    0.1,
    float(os.getenv("GALLERY_SEARCH_INDEX_POLL_SECONDS", "1.0")),
)
GALLERY_RELATED_VISUAL_ENABLED = _env_flag("GALLERY_RELATED_VISUAL_ENABLED", default=True)
GALLERY_SEARCH_WORKFLOW_RAW_ENABLED = _env_flag("GALLERY_SEARCH_WORKFLOW_RAW_ENABLED", default=False)
GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES = max(
    1,
    int(os.getenv("GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES", "1048576")),
)
GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES = max(
    1,
    int(os.getenv("GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES", "536870912")),
)

# ---------------------------------------------------------------------------
# Scheduled catalog reconciliation
# ---------------------------------------------------------------------------
ENABLE_SCHEDULED_REFRESH = _env_flag(
    "GALLERY_CATALOG_RECONCILE_ENABLED",
    default=_env_flag("ENABLE_SCHEDULED_REFRESH", default=True),
)
SCHEDULED_REFRESH_INTERVAL_SECONDS = max(
    60,
    int(
        os.getenv(
            "GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS", os.getenv("SCHEDULED_REFRESH_INTERVAL_SECONDS", "21600")
        )
    ),
)
SCHEDULED_REFRESH_ROOTS = [p.strip() for p in os.getenv("SCHEDULED_REFRESH_ROOTS", "").split(",") if p.strip()]
SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK = max(
    1,
    int(os.getenv("SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK", "20")),
)
SCHEDULED_REFRESH_ALLOW_ALL_INDEXED = _env_flag("SCHEDULED_REFRESH_ALLOW_ALL_INDEXED", default=False)

# ---------------------------------------------------------------------------
# File watcher (enabled by default for registered libraries)
# ---------------------------------------------------------------------------
ENABLE_FILE_WATCHER = _env_flag(
    "GALLERY_CATALOG_WATCHER_ENABLED",
    default=_env_flag("ENABLE_FILE_WATCHER", default=True),
)
WATCHER_ROOTS = [p.strip() for p in os.getenv("WATCHER_ROOTS", "").split(",") if p.strip()]
WATCHER_DEBOUNCE_SECONDS = max(
    0.1,
    float(os.getenv("GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS", os.getenv("WATCHER_DEBOUNCE_SECONDS", "2.0"))),
)
WATCHER_MAX_EVENTS_PER_TICK = max(1, int(os.getenv("WATCHER_MAX_EVENTS_PER_TICK", "500")))

# ---------------------------------------------------------------------------
# Integrity checker
# ---------------------------------------------------------------------------
INTEGRITY_CHECK_ENABLED = _env_flag("GALLERY_INTEGRITY_CHECK_ENABLED", default=True)
INTEGRITY_CHECK_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("GALLERY_INTEGRITY_CHECK_INTERVAL_SECONDS", "3600")),
)
