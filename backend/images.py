from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from .errors import APIError, ErrorType
from .files import check_image_limits, is_image
from .paths import is_path_safe, resolve_path

router = APIRouter()


@router.get("/api/image")
async def api_image(path: str = Query(..., description="Absolute path to image file")):
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    stat = file_path.stat()
    etag = f'"{stat.st_mtime}-{stat.st_size}"'
    return FileResponse(
        file_path,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag
        }
    )
