"""Serve original video files with HTTP Range support and cached posters."""

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, Response, StreamingResponse

from .config import (
    THUMBNAIL_CACHE_DIR,
    VIDEO_POSTER_MAX_CONCURRENCY,
    VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS,
    VIDEO_POSTER_QUOTA_BYTES,
)
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
_POSTER_SLOTS = threading.BoundedSemaphore(VIDEO_POSTER_MAX_CONCURRENCY)
_POSTER_STATE_LOCK = threading.RLock()
_POSTER_GENERATING_PATHS: set[str] = set()
_POSTER_SERVED_PATHS: set[str] = set()

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_RANGE_CHUNK_SIZE = 1024 * 1024
_REVALIDATE_CACHE_CONTROL = "public, max-age=0, must-revalidate"


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


def _release_poster_serving(path: str) -> None:
    with _POSTER_STATE_LOCK:
        _POSTER_SERVED_PATHS.discard(path)


def _enforce_poster_quota(*, protect: str | None = None) -> bool:
    """Evict least-recently-used poster files while protecting active paths."""
    POSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _POSTER_STATE_LOCK:
        protected = _POSTER_GENERATING_PATHS | _POSTER_SERVED_PATHS
        if protect is not None:
            protected = {*protected, protect}
        files = [path for path in POSTER_CACHE_DIR.glob("*.webp") if path.is_file()]
        total = sum(path.stat().st_size for path in files)
        for path in sorted(files, key=lambda item: (item.stat().st_atime_ns, str(item))):
            if total <= VIDEO_POSTER_QUOTA_BYTES:
                break
            if str(path) in protected:
                continue
            size = path.stat().st_size
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
        return total <= VIDEO_POSTER_QUOTA_BYTES


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
        "Cache-Control": _REVALIDATE_CACHE_CONTROL,
    }

    if request.headers.get("if-none-match") == etag and not request.headers.get("range"):
        return Response(status_code=304, headers=common_headers)

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


def _get_or_generate_poster(file_path: Path) -> Path:
    """Generate a poster synchronously; callers must run this off the event loop."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise APIError(503, ErrorType.VIDEO_TOOL_UNAVAILABLE, "ffmpeg is not available on this system")

    stat = file_path.stat()
    cache_key = f"{file_path}_{stat.st_mtime_ns}_{stat.st_size}"
    cached_path = POSTER_CACHE_DIR / f"{hashlib.sha256(cache_key.encode()).hexdigest()}.webp"
    POSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not cached_path.exists():
        if not _POSTER_SLOTS.acquire(timeout=VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS):
            raise APIError(503, "video_poster_saturated", "Video poster generation is busy")
        lock = _poster_lock_for(cache_key)
        try:
            with lock:
                # Re-check inside the lock so only one request runs ffmpeg per key.
                if not cached_path.exists():
                    temp_path = cached_path.with_name(
                        f"{cached_path.stem}.tmp.{os.getpid()}.{threading.get_ident()}.webp"
                    )
                    temp_path.unlink(missing_ok=True)
                    with _POSTER_STATE_LOCK:
                        _POSTER_GENERATING_PATHS.add(str(cached_path))
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
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=30,
                            check=False,
                        )
                        if result.returncode != 0 or not temp_path.exists():
                            raise APIError(422, ErrorType.VIDEO_POSTER_FAILED, "ffmpeg could not produce a poster")
                        temp_path.replace(cached_path)
                    except APIError:
                        temp_path.unlink(missing_ok=True)
                        raise
                    except (OSError, subprocess.SubprocessError) as exc:
                        temp_path.unlink(missing_ok=True)
                        raise APIError(
                            422,
                            ErrorType.VIDEO_POSTER_FAILED,
                            "ffmpeg could not produce a poster",
                        ) from exc
                    finally:
                        temp_path.unlink(missing_ok=True)
                        with _POSTER_STATE_LOCK:
                            _POSTER_GENERATING_PATHS.discard(str(cached_path))
        finally:
            _POSTER_SLOTS.release()

    with suppress(OSError):
        cached_stat = cached_path.stat()
        os.utime(cached_path, ns=(time.time_ns(), cached_stat.st_mtime_ns))
    if not _enforce_poster_quota(protect=str(cached_path)):
        cached_path.unlink(missing_ok=True)
        raise APIError(507, ErrorType.CAPACITY_EXCEEDED, "Video poster cache capacity exceeded")

    return cached_path


@router.get("/api/video/poster")
async def api_video_poster(request: Request, path: str = Query(...)):
    """Return a cached WebP poster or generate one without blocking the event loop."""
    file_path = _validate_video(path)
    cached_path = await run_in_threadpool(_get_or_generate_poster, file_path)
    cached_stat = cached_path.stat()
    etag = f'"{cached_stat.st_mtime_ns}-{cached_stat.st_size}"'
    headers = {"Cache-Control": _REVALIDATE_CACHE_CONTROL, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    with _POSTER_STATE_LOCK:
        _POSTER_SERVED_PATHS.add(str(cached_path))
    return FileResponse(
        cached_path,
        media_type="image/webp",
        headers=headers,
        background=BackgroundTask(_release_poster_serving, str(cached_path)),
    )
