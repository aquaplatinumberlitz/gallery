"""Authorize media file paths for serving under the PATH_SAFETY_ROOT containment model.

The legacy ``GET /api/scan`` route, ``scan_directory`` filesystem fallback, and
``GALLERY_DB_REQUIRED`` conditional branches were removed in Phase 9 of the
catalog scan pipeline refactor. Gallery browsing now uses the read-only
``GET /api/browse`` route backed by the catalog. This module retains the shared
``require_media_path_allowed`` helper used by the image, video, and thumbnail
routers, plus the router included by ``backend/app.py``.
"""

from pathlib import Path

from fastapi import APIRouter

from .errors import APIError, ErrorType
from .paths import is_path_safe, resolve_path

router = APIRouter()


def require_media_path_allowed(path: str | Path, expected_type: str | None = None) -> Path:
    """Authorize a media file path for serving under the current security model.

    The path must pass the ``PATH_SAFETY_ROOT`` containment check via
    ``is_path_safe()``. File-extension checks remain the caller's
    responsibility. ``expected_type`` is accepted for caller compatibility and
    reserved for future catalog-backed type validation.

    Returns the resolved, authorized Path.
    """
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    return file_path
