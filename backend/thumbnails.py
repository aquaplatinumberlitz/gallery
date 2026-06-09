import hashlib
import os
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from diskcache import Cache
from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .config import THUMBNAIL_CACHE_DIR
from .errors import APIError, ErrorType
from .files import check_image_limits, is_image
from .metadata_store import upsert_image_dimensions
from .paths import is_path_safe, resolve_path

_thumbnail_disk_cache = Cache(str(THUMBNAIL_CACHE_DIR), size_limit=2 * 1024 * 1024 * 1024)
_thumbnail_file_dir = THUMBNAIL_CACHE_DIR / "files"

router = APIRouter()


def _thumbnail_cache_key_str(path: Path, max_size: int, quality: int) -> str:
    """Build a deterministic cache key string. Invalidates on file change."""
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{max_size}:{quality}"


def _thumbnail_cache_file_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _thumbnail_file_dir / f"{digest}.webp"


def _persist_thumbnail_file(cache_key: str, thumbnail_bytes: bytes) -> Path:
    _thumbnail_file_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = _thumbnail_cache_file_path(cache_key)
    if thumbnail_path.exists():
        return thumbnail_path

    temp_path = thumbnail_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_bytes(thumbnail_bytes)
    temp_path.replace(thumbnail_path)
    return thumbnail_path


def _render_thumbnail_impl(path: Path, max_size: int, quality: int) -> bytes:
    """Render WebP thumbnail bytes (no caching here)."""
    with Image.open(path) as img:
        source_width, source_height = img.size
        source_format = img.format or ""
        source_mode = img.mode or ""
        source_has_alpha = source_mode in {"RGBA", "LA"} or (source_mode == "P" and "transparency" in img.info)
        upsert_image_dimensions(
            path,
            source_width,
            source_height,
            image_format=source_format,
            mode=source_mode,
            has_alpha=source_has_alpha,
        )

        img = ImageOps.exif_transpose(img)

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=quality, method=6)
        return buffer.getvalue()


def generate_thumbnail(file_path: Path, max_size: int = 800, quality: int = 75) -> bytes:
    """Generate a thumbnail, cached persistently on disk."""
    check_image_limits(file_path)
    cache_key = _thumbnail_cache_key_str(file_path, max_size, quality)

    cached = _thumbnail_disk_cache.get(cache_key)
    if cached is not None:
        _persist_thumbnail_file(cache_key, cached)
        return cached

    try:
        thumbnail_bytes = _render_thumbnail_impl(file_path, max_size, quality)
        _thumbnail_disk_cache.set(cache_key, thumbnail_bytes)
        _persist_thumbnail_file(cache_key, thumbnail_bytes)
        return thumbnail_bytes
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        api_exc = APIError(400, ErrorType.INVALID_FILE, f"Unable to process image: {exc}")
        raise api_exc from exc


@router.get("/api/thumbnail")
async def api_thumbnail(
    request: Request,
    path: str = Query(..., description="Absolute path to image file"),
    max_size: int = Query(800, ge=1, le=4096, description="Max dimension for thumbnail/display"),
):
    """
    Serve optimized WebP thumbnail.
    Uses persistent disk cache backed by diskcache.
    Returns FileResponse with proper HTTP caching headers when the cache file exists.
    """
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")

    stat = file_path.stat()
    etag = f'"{stat.st_mtime}-{stat.st_size}"'
    headers = {
        "Cache-Control": "public, max-age=86400, immutable",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        thumbnail_bytes = await run_in_threadpool(generate_thumbnail, file_path, max_size, 75)
    except APIError:
        raise
    except FileNotFoundError:
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    except OSError:
        raise APIError(400, ErrorType.INVALID_FILE, "Unable to process image")

    cache_key = _thumbnail_cache_key_str(file_path, max_size, 75)
    thumbnail_path = _thumbnail_cache_file_path(cache_key)

    if thumbnail_path.exists():
        return FileResponse(
            thumbnail_path,
            media_type="image/webp",
            headers=headers,
        )

    return Response(
        content=thumbnail_bytes,
        media_type="image/webp",
        headers={
            **headers,
            "Content-Length": str(len(thumbnail_bytes)),
        }
    )
