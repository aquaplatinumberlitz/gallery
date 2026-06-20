"""Serve original video files with HTTP Range support and cached posters."""

import hashlib
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, Query, Request
from starlette.responses import FileResponse, Response, StreamingResponse

from .config import THUMBNAIL_CACHE_DIR
from .errors import APIError, ErrorType
from .files import is_video_path
from .scan import require_media_path_allowed

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

# Per-video lock guarding poster generation so concurrent requests for the
# same video do not both spawn ffmpeg against the same output path.
_POSTER_LOCKS_GUARD = threading.Lock()
_POSTER_LOCKS: dict[str, threading.Lock] = {}

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_RANGE_CHUNK_SIZE = 1024 * 1024


def _validate_video(path: str) -> Path:
    """Resolve, authorize, and validate a video file path."""
    file_path = require_media_path_allowed(path, "video")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Video file not found")
    if not is_video_path(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid video file")
    return file_path


def iter_file_range(path: Path, start: int, end: int, chunk_size: int = _RANGE_CHUNK_SIZE):
    """Yield byte chunks covering [start, end] of a file without loading it all into memory."""
    remaining = end - start + 1
    with path.open("rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _poster_lock_for(cache_key: str) -> threading.Lock:
    with _POSTER_LOCKS_GUARD:
        lock = _POSTER_LOCKS.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _POSTER_LOCKS[cache_key] = lock
        return lock


@router.get("/api/video")
async def api_video(request: Request, path: str = Query(...)):
    """Stream an original video file with support for a single HTTP byte range."""
    file_path = _validate_video(path)
    stat = file_path.stat()
    file_size = stat.st_size
    etag = f'"{stat.st_mtime_ns}-{file_size}"'
    content_type = _VIDEO_MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    common_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "public, max-age=31536000, immutable",
    }

    range_header = request.headers.get("range", "").strip()
    if not range_header:
        return FileResponse(file_path, media_type=content_type, headers=common_headers)

    # Reject multi-range requests cleanly; only a single range is supported.
    if "," in range_header:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    range_match = _RANGE_RE.fullmatch(range_header)
    if not range_match:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    start_str, end_str = range_match.group(1), range_match.group(2)
    if not start_str and not end_str:
        # "bytes=-" is not a satisfiable range.
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    if not start_str:
        # Suffix range (RFC 7233): bytes=-N returns the last N bytes.
        suffix = int(end_str)
        if suffix == 0:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
        start = max(0, file_size - suffix)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1

    if start >= file_size or end >= file_size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    content_length = end - start + 1
    return StreamingResponse(
        iter_file_range(file_path, start, end),
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
    """Return a cached WebP poster or generate one atomically from the video."""
    file_path = _validate_video(path)
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise APIError(503, ErrorType.VIDEO_TOOL_UNAVAILABLE, "ffmpeg is not available on this system")

    stat = file_path.stat()
    cache_key = f"{file_path}_{stat.st_mtime_ns}_{stat.st_size}"
    cached_path = POSTER_CACHE_DIR / f"{hashlib.sha256(cache_key.encode()).hexdigest()}.webp"
    POSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not cached_path.exists():
        lock = _poster_lock_for(cache_key)
        with lock:
            # Re-check inside the lock so only one request runs ffmpeg per key.
            if not cached_path.exists():
                temp_path = cached_path.with_name(f"{cached_path.stem}.tmp.{os.getpid()}.{threading.get_ident()}.webp")
                temp_path.unlink(missing_ok=True)
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
                            str(temp_path),
                        ],
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    temp_path.unlink(missing_ok=True)
                    raise APIError(
                        422,
                        ErrorType.VIDEO_POSTER_FAILED,
                        "ffmpeg could not produce a poster",
                    ) from exc
                if result.returncode != 0 or not temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                    raise APIError(422, ErrorType.VIDEO_POSTER_FAILED, "ffmpeg could not produce a poster")
                # Atomic rename so concurrent readers never see a half-written poster.
                temp_path.replace(cached_path)

    cached_stat = cached_path.stat()
    etag = f'"{cached_stat.st_mtime_ns}-{cached_stat.st_size}"'
    return FileResponse(
        cached_path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag},
    )
