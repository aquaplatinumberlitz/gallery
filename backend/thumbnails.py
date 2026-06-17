import hashlib
import os
import threading
from io import BytesIO
from pathlib import Path
from typing import Literal

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
DERIVATIVE_CACHE_VERSION = "v2"
DERIVATIVE_MEDIA_TYPES = {
    "webp": "image/webp",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
}
DERIVATIVE_PIL_FORMATS = {
    "webp": "WEBP",
    "jpeg": "JPEG",
    "jpg": "JPEG",
}

try:
    from prometheus_client import Counter
except ImportError:
    Counter = None


def _metric_counter(name, doc, *labels_args, **labels_kwargs):
    if Counter is None:
        return None
    try:
        return Counter(name, doc, *labels_args, **labels_kwargs)
    except ValueError:
        return None


def _inc(metric, *labels, amount=1.0):
    if metric is None:
        return
    target = metric.labels(*labels) if labels else metric
    target.inc(amount)


_derivative_ready_total = _metric_counter(
    "gallery_derivative_ready_total",
    "Derivative images successfully generated",
    ["type"],
)
_derivative_errors_total = _metric_counter(
    "gallery_derivative_errors_total",
    "Derivative generation errors",
)

router = APIRouter()


DerivativeKind = Literal["thumbnail", "preview"]


def _normalize_derivative_format(format: str) -> str:
    normalized = format.lower().lstrip(".")
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized not in DERIVATIVE_PIL_FORMATS:
        raise ValueError(f"Unsupported derivative format: {format}")
    return normalized


def _derivative_cache_key_str(
    path: Path,
    *,
    kind: DerivativeKind,
    max_long_edge: int,
    quality: int,
    format: str,
) -> str:
    """Build a deterministic derivative cache key. Invalidates on file change."""
    stat = path.stat()
    normalized_format = _normalize_derivative_format(format)
    return (
        f"{kind}:{DERIVATIVE_CACHE_VERSION}:{path.resolve()}:"
        f"{stat.st_mtime_ns}:{stat.st_size}:edge={max_long_edge}:"
        f"fmt={normalized_format}:q={quality}"
    )


def _derivative_cache_file_path(cache_key: str, format: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    normalized_format = _normalize_derivative_format(format)
    return _thumbnail_file_dir / f"{digest}.{normalized_format}"


def _persist_derivative_file(cache_key: str, derivative_bytes: bytes, format: str) -> Path:
    _thumbnail_file_dir.mkdir(parents=True, exist_ok=True)
    derivative_path = _derivative_cache_file_path(cache_key, format)
    if derivative_path.exists():
        return derivative_path

    temp_path = derivative_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_bytes(derivative_bytes)
    temp_path.replace(derivative_path)
    return derivative_path


def _render_derivative_impl(
    path: Path,
    *,
    max_long_edge: int,
    quality: int,
    format: str,
    no_upscale: bool,
) -> bytes:
    """Render derivative image bytes (no caching here)."""
    normalized_format = _normalize_derivative_format(format)
    pil_format = DERIVATIVE_PIL_FORMATS[normalized_format]

    with Image.open(path) as img:
        source_format = img.format or ""
        source_mode = img.mode or ""
        source_has_alpha = source_mode in {"RGBA", "LA"} or (source_mode == "P" and "transparency" in img.info)

        img = ImageOps.exif_transpose(img)
        oriented_width, oriented_height = img.size
        upsert_image_dimensions(
            path,
            oriented_width,
            oriented_height,
            image_format=source_format,
            mode=source_mode,
            has_alpha=source_has_alpha,
        )

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if no_upscale:
            img.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
        elif max(img.size) != max_long_edge:
            scale = max_long_edge / max(img.size)
            new_size = (
                max(1, round(img.size[0] * scale)),
                max(1, round(img.size[1] * scale)),
            )
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = BytesIO()
        save_kwargs = {"quality": quality}
        if normalized_format == "webp":
            save_kwargs["method"] = 6
        img.save(buffer, format=pil_format, **save_kwargs)
        return buffer.getvalue()


def generate_derivative(
    file_path: Path,
    *,
    kind: DerivativeKind,
    max_long_edge: int,
    quality: int,
    format: str,
    no_upscale: bool = True,
) -> bytes:
    """Generate a role-specific image derivative, cached persistently on disk."""
    check_image_limits(file_path)
    normalized_format = _normalize_derivative_format(format)
    cache_key = _derivative_cache_key_str(
        file_path,
        kind=kind,
        max_long_edge=max_long_edge,
        quality=quality,
        format=normalized_format,
    )

    cached = _thumbnail_disk_cache.get(cache_key)
    if cached is not None:
        _persist_derivative_file(cache_key, cached, normalized_format)
        return cached

    try:
        derivative_bytes = _render_derivative_impl(
            file_path,
            max_long_edge=max_long_edge,
            quality=quality,
            format=normalized_format,
            no_upscale=no_upscale,
        )
        _thumbnail_disk_cache.set(cache_key, derivative_bytes)
        _persist_derivative_file(cache_key, derivative_bytes, normalized_format)
        _inc(_derivative_ready_total, kind)
        return derivative_bytes
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        _inc(_derivative_errors_total)
        api_exc = APIError(400, ErrorType.INVALID_FILE, f"Unable to process image: {exc}")
        raise api_exc from exc


def _resolve_image_request_path(path: str) -> Path:
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    return file_path


def _resolve_max_long_edge(max_long_edge: int, max_size: int | None) -> int:
    return max_size if max_size is not None else max_long_edge


async def _serve_derivative(
    *,
    request: Request,
    path: str,
    kind: DerivativeKind,
    max_long_edge: int,
    quality: int,
    format: str,
    failure_message: str,
):
    file_path = _resolve_image_request_path(path)
    normalized_format = _normalize_derivative_format(format)

    stat = file_path.stat()
    etag = (
        f'"{kind}-{DERIVATIVE_CACHE_VERSION}-{stat.st_mtime_ns}-'
        f'{stat.st_size}-{max_long_edge}-{normalized_format}-{quality}"'
    )
    headers = {
        "Cache-Control": "public, max-age=86400, immutable",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        derivative_bytes = await run_in_threadpool(
            generate_derivative,
            file_path,
            kind=kind,
            max_long_edge=max_long_edge,
            quality=quality,
            format=normalized_format,
            no_upscale=True,
        )
    except APIError:
        raise
    except FileNotFoundError as exc:
        _inc(_derivative_errors_total)
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found") from exc
    except OSError as exc:
        _inc(_derivative_errors_total)
        raise APIError(400, ErrorType.INVALID_FILE, failure_message) from exc
    except Exception as exc:  # noqa: BLE001
        _inc(_derivative_errors_total)
        raise APIError(500, ErrorType.SERVER_ERROR, failure_message) from exc

    cache_key = _derivative_cache_key_str(
        file_path,
        kind=kind,
        max_long_edge=max_long_edge,
        quality=quality,
        format=normalized_format,
    )
    derivative_path = _derivative_cache_file_path(cache_key, normalized_format)

    if derivative_path.exists():
        return FileResponse(
            derivative_path,
            media_type=DERIVATIVE_MEDIA_TYPES[normalized_format],
            headers=headers,
        )

    return Response(
        content=derivative_bytes,
        media_type=DERIVATIVE_MEDIA_TYPES[normalized_format],
        headers={
            **headers,
            "Content-Length": str(len(derivative_bytes)),
        },
    )


@router.get("/api/thumbnail")
async def api_thumbnail(
    request: Request,
    path: str = Query(..., description="Absolute path to image file"),
    max_long_edge: int = Query(512, ge=1, le=4096, description="Max long edge for grid thumbnail"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
):
    """
    Serve optimized WebP thumbnail.
    Uses persistent disk cache backed by diskcache.
    Returns FileResponse with proper HTTP caching headers when the cache file exists.
    """
    return await _serve_derivative(
        request=request,
        path=path,
        kind="thumbnail",
        max_long_edge=_resolve_max_long_edge(max_long_edge, max_size),
        quality=78,
        format="webp",
        failure_message="Unable to process image",
    )


@router.get("/api/preview")
async def api_preview(
    request: Request,
    path: str = Query(..., description="Absolute path to image file"),
    max_long_edge: int = Query(1440, ge=1, le=4096, description="Max long edge for viewer preview"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
):
    """
    Serve optimized WebP viewer preview.
    The preview derivative is distinct from thumbnails and originals.
    """
    return await _serve_derivative(
        request=request,
        path=path,
        kind="preview",
        max_long_edge=_resolve_max_long_edge(max_long_edge, max_size),
        quality=86,
        format="webp",
        failure_message="Unable to generate preview",
    )
