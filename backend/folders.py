"""Folder listing and local open-folder API endpoints."""

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
from .paths import is_path_safe, resolve_path

router = APIRouter()


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
        raise APIError(500, ErrorType.SERVER_ERROR, f"Unable to list folder: {exc}") from exc

    folders.sort(key=lambda x: natural_sort_key(x.name))
    return folders


@router.get("/api/folders")
async def api_folders(
    path: str | None = Query(None, description="Absolute path whose folder children should be listed"),
):
    """Return child folders under the requested path or first registered library root."""
    target = await run_in_threadpool(_registered_or_requested_root, path)
    if not is_path_safe(target):
        raise APIError(403, "permission", "Access denied: path outside allowed root")
    from .metadata_store import get_library_for_path

    library = await run_in_threadpool(get_library_for_path, target)
    import_root = library["matched_import_path"] if library is not None else None
    exclusion_patterns = library["exclusion_patterns"] if library is not None else []
    if is_index_excluded_path(target, import_root, exclusion_patterns):
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    return await run_in_threadpool(list_folder_children, target, import_root, exclusion_patterns)


@router.post("/api/open-folder")
async def api_open_folder(path: str = Query(..., description="Absolute path to folder")):
    """Open a folder on the host when explicitly enabled by server configuration."""
    if not OPEN_FOLDER_ENABLED:
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Open folder is disabled on this server")
    folder_path = resolve_path(path)
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
        raise APIError(500, ErrorType.SERVER_ERROR, f"Failed to open: {exc}") from exc
