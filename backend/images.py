"""Serve original image files after path and file-type validation."""

import os
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from .errors import APIError, ErrorType
from .files import is_image
from .scan import require_media_path_allowed

router = APIRouter()


def _authorize_and_stat_image(path: str) -> tuple[Path, os.stat_result]:
    """Authorize, check and stat an image path. Catalog reads and file stats run here, off the event loop."""
    file_path = require_media_path_allowed(path, "image")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    return file_path, file_path.stat()


@router.get("/api/image")
async def api_image(request: Request, path: str = Query(..., description="Absolute path to image file")):
    """Return an original image file with identity-aware revalidation."""
    file_path, stat = await run_in_threadpool(_authorize_and_stat_image, path)
    etag = f'"{stat.st_mtime_ns}-{stat.st_size}"'
    headers = {"Cache-Control": "public, max-age=0, must-revalidate", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(file_path, headers=headers)
