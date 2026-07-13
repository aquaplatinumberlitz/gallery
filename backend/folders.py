"""Folder listing and local open-folder API endpoints."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .albums import has_subfolders
from .config import OPEN_FOLDER_ENABLED
from .errors import APIError, ErrorType
from .files import is_index_excluded_path, natural_sort_key
from .models import FileNode
from .paths import resolve_path
from .scan import require_registered_path_allowed

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _registered_or_requested_root(path: str | None) -> Path:
    if path:
        return resolve_path(path)
    from .metadata_store import get_first_library_root

    root = get_first_library_root()
    if root is None:
        raise APIError(400, ErrorType.BAD_REQUEST, "path required")
    return root


def list_folder_children(
    target_path: Path,
    import_root: str | Path | None = None,
    exclusion_patterns: tuple[str, ...] | list[str] = (),
) -> list[FileNode]:
    """List visible, non-excluded child folders as FileNode records."""
    if not target_path.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    if not target_path.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")

    folders: list[FileNode] = []
    try:
        for entry in os.scandir(target_path):
            if entry.name.startswith(".") or is_index_excluded_path(entry.path, import_root, exclusion_patterns):
                continue

            entry_path = Path(entry.path)

            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue

            try:
                path = str(entry_path.resolve())
            except OSError:
                path = str(entry_path.absolute())

            try:
                mtime = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                mtime = 0

            folders.append(
                FileNode(
                    name=entry.name,
                    path=path,
                    type="folder",
                    has_children=has_subfolders(entry_path, import_root, exclusion_patterns),
                    cover_images=[],
                    mtime=mtime,
                    image_count=0,
                )
            )
    except PermissionError as exc:
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Permission denied") from exc
    except OSError as exc:
        LOGGER.exception("Unable to list folder %s", target_path)
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc

    folders.sort(key=lambda x: natural_sort_key(x.name))
    return folders


@router.get("/api/folders")
async def api_folders(
    path: str | None = Query(None, description="Absolute path whose folder children should be listed"),
):
    """Return child folders under the requested path or first registered library root."""
    requested = await run_in_threadpool(_registered_or_requested_root, path)
    target, library = await run_in_threadpool(require_registered_path_allowed, requested)
    import_root = library["matched_import_path"]
    exclusion_patterns = library["exclusion_patterns"]
    return await run_in_threadpool(list_folder_children, target, import_root, exclusion_patterns)


@router.post("/api/open-folder")
async def api_open_folder(path: str = Query(..., description="Absolute path to folder")):
    """Open a folder on the host when explicitly enabled by server configuration."""
    if not OPEN_FOLDER_ENABLED:
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Open folder is disabled on this server")
    folder_path, _library = await run_in_threadpool(require_registered_path_allowed, path)
    if not folder_path.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    if not folder_path.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")

    try:
        if os.name == "nt":  # Windows
            os.startfile(folder_path)
        else:  # Linux / Mac
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(folder_path)])
        return {"message": "Opened successfully"}
    except OSError as exc:
        LOGGER.exception("Failed to open folder %s", folder_path)
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc
