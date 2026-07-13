"""Authorize media and folder paths against safety and catalog ownership.

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
from .files import is_index_excluded_path
from .metadata_store import get_asset_state_for_path, get_library_for_path
from .paths import is_path_safe, resolve_path

router = APIRouter()


def require_media_path_allowed(path: str | Path, expected_type: str | None = None) -> Path:
    """Authorize a media file path for serving under the current security model.

    Safety-root escapes are forbidden. Everything else that is not an active,
    catalog-owned asset of the expected type is intentionally hidden as 404.

    Returns the resolved, authorized Path.
    """
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    asset = get_asset_state_for_path(file_path)
    if (
        asset is None
        or asset["offline"]
        or asset["deleted_at"] is not None
        or (expected_type is not None and asset["type"] != expected_type)
    ):
        raise APIError(404, ErrorType.NOT_FOUND, "Asset not found")
    return file_path


def require_registered_path_allowed(path: str | Path) -> tuple[Path, dict]:
    """Authorize a folder-like scope owned by a non-excluded library root."""
    resolved = resolve_path(str(path))
    if not is_path_safe(resolved):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    library = get_library_for_path(resolved)
    if library is None or is_index_excluded_path(
        resolved,
        library["matched_import_path"],
        library["exclusion_patterns"],
    ):
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    return resolved, library
