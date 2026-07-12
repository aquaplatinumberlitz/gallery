"""Serve original image files after path and file-type validation."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from .errors import APIError, ErrorType
from .files import is_image
from .scan import require_media_path_allowed

router = APIRouter()


@router.get("/api/image")
async def api_image(request: Request, path: str = Query(..., description="Absolute path to image file")):
    """Return an original image file with identity-aware revalidation."""
    file_path = require_media_path_allowed(path, "image")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    stat = file_path.stat()
    etag = f'"{stat.st_mtime_ns}-{stat.st_size}"'
    headers = {"Cache-Control": "public, max-age=0, must-revalidate", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(file_path, headers=headers)
