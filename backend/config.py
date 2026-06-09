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
    for endpoint in os.getenv("PROFILE_ENDPOINTS", "/api/scan,/api/metadata,/api/thumbnail").split(",")
    if endpoint.strip()
}
PROFILE_DIR = Path(__file__).resolve().parent / "profiles"

METADATA_CACHE_MAX_BYTES = 100 * 1024 * 1024         # 100 MB

THUMBNAIL_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "thumbnails"

SCAN_PERF_LOGS_ENABLED = os.getenv("SCAN_PERF_LOGS", "1" if os.getenv("PRODUCTION") != "1" else "0").lower() not in {"0", "false", "no"}

GALLERY_ROOT = Path(os.getenv("GALLERY_ROOT", "/")).resolve()
DEFAULT_ROOT = GALLERY_ROOT

MAX_IMAGE_FILE_BYTES = 75 * 1024 * 1024   # 75 MB
MAX_IMAGE_PIXELS = 100 * 1024 * 1024      # 100 megapixels
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

PRODUCTION = os.getenv("PRODUCTION", "0") == "1"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

OPEN_FOLDER_ENABLED = os.getenv("GALLERY_OPEN_FOLDER", "false").lower() == "true"

METADATA_DB_DIR = Path(__file__).resolve().parent / ".cache"
GALLERY_METADATA_DB = METADATA_DB_DIR / "gallery_metadata.db"
