"""Serve original video files with HTTP Range support and cached posters."""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Query, Request
from starlette.responses import FileResponse, Response

from .config import THUMBNAIL_CACHE_DIR
from .errors import APIError, ErrorType
from .files import is_video_path
from .paths import is_path_safe, resolve_path

router = APIRouter()

POSTER_CACHE_DIR = Path(THUMBNAIL_CACHE_DIR).resolve() / "video_posters"

_VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}


def _validate_video(path: str) -> Path:
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Video file not found")
    if not is_video_path(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid video file")
    return file_path


@router.get("/api/video")
async def api_video(request: Request, path: str = Query(...)):
    """Stream an original video file with support for one HTTP byte range."""
    file_path = _validate_video(path)
    stat = file_path.stat()
    file_size = stat.st_size
    etag = f'"{stat.st_mtime}-{file_size}"'
    content_type = _VIDEO_MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    common_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "public, max-age=31536000, immutable",
    }

    range_header = request.headers.get("range", "")
    if not range_header:
        return FileResponse(file_path, media_type=content_type, headers=common_headers)

    range_match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header.strip())
    if not range_match:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    content_length = end - start + 1
    with file_path.open("rb") as video_file:
        video_file.seek(start)
        body = video_file.read(content_length)

    return Response(
        content=body,
        status_code=206,
        media_type=content_type,
        headers={
            **common_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        },
    )


@router.get("/api/video/poster")
async def api_video_poster(path: str = Query(...)):
    """Return a cached WebP poster or generate one from the video."""
    file_path = _validate_video(path)
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise APIError(503, ErrorType.VIDEO_TOOL_UNAVAILABLE, "ffmpeg is not available on this system")

    stat = file_path.stat()
    cache_key = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
    cached_path = POSTER_CACHE_DIR / f"{hashlib.sha256(cache_key.encode()).hexdigest()}.webp"
    POSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not cached_path.exists():
        try:
            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-ss",
                    "1",
                    "-i",
                    str(file_path),
                    "-vframes",
                    "1",
                    "-q:v",
                    "3",
                    str(cached_path),
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise APIError(422, ErrorType.VIDEO_POSTER_FAILED, "ffmpeg could not produce a poster") from exc
        if result.returncode != 0 or not cached_path.exists():
            cached_path.unlink(missing_ok=True)
            raise APIError(422, ErrorType.VIDEO_POSTER_FAILED, "ffmpeg could not produce a poster")

    cached_stat = cached_path.stat()
    etag = f'"{cached_stat.st_mtime}-{cached_stat.st_size}"'
    return FileResponse(
        cached_path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag},
    )
