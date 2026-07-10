"""Generate and serve cached WebP thumbnail and preview derivatives."""

import hashlib
import os
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Literal

from diskcache import Cache
from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.background import BackgroundTask

from .config import THUMBNAIL_CACHE_DIR
from .errors import APIError, ErrorType
from .files import check_image_limits, is_image
from .metadata_store import upsert_image_dimensions
from .scan import require_media_path_allowed

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


def derivative_cache_path(
    path: Path,
    *,
    kind: DerivativeKind,
    max_long_edge: int,
    quality: int,
    format: str,
) -> Path:
    """Return the persisted cache path for one source derivative."""
    cache_key = _derivative_cache_key_str(
        path,
        kind=kind,
        max_long_edge=max_long_edge,
        quality=quality,
        format=format,
    )
    return _derivative_cache_file_path(cache_key, format)


def _persist_derivative_file(cache_key: str, derivative_bytes: bytes, format: str) -> Path:
    _thumbnail_file_dir.mkdir(parents=True, exist_ok=True)
    derivative_path = _derivative_cache_file_path(cache_key, format)
    if derivative_path.exists():
        return derivative_path

    temp_path = derivative_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_bytes(derivative_bytes)
    temp_path.replace(derivative_path)
    return derivative_path


def clear_thumbnail_disk_cache() -> int:
    """Clear cached derivative bytes stored by diskcache."""
    count = len(_thumbnail_disk_cache)
    _thumbnail_disk_cache.clear()
    return int(count)


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
    request_timing: dict[str, float] | None = None,
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
        persist_started = time.perf_counter()
        _persist_derivative_file(cache_key, cached, normalized_format)
        if request_timing is not None:
            request_timing["render_encode_persist_ms"] = (time.perf_counter() - persist_started) * 1000
        return cached

    try:
        render_started = time.perf_counter()
        derivative_bytes = _render_derivative_impl(
            file_path,
            max_long_edge=max_long_edge,
            quality=quality,
            format=normalized_format,
            no_upscale=no_upscale,
        )
        _thumbnail_disk_cache.set(cache_key, derivative_bytes)
        _persist_derivative_file(cache_key, derivative_bytes, normalized_format)
        if request_timing is not None:
            request_timing["render_encode_persist_ms"] = (time.perf_counter() - render_started) * 1000
        _inc(_derivative_ready_total, kind)
        return derivative_bytes
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        _inc(_derivative_errors_total)
        api_exc = APIError(400, ErrorType.INVALID_FILE, f"Unable to process image: {exc}")
        raise api_exc from exc


def _resolve_image_request_path(path: str) -> Path:
    file_path = require_media_path_allowed(path, "image")
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
    path: str | None,
    asset_id: int | None = None,
    kind: DerivativeKind,
    max_long_edge: int,
    quality: int,
    format: str,
    failure_message: str,
):
    from .derivative_scheduler import derivative_variant, scheduler

    explicit_asset_id = asset_id is not None
    if explicit_asset_id:
        asset_path = scheduler.get_asset_path(asset_id)
        if asset_path is None:
            raise APIError(404, ErrorType.NOT_FOUND, "Asset not found")
        file_path = _resolve_image_request_path(str(asset_path))
    elif path is not None:
        file_path = _resolve_image_request_path(path)
        asset_id = scheduler.find_asset_id(file_path)
    else:
        raise APIError(400, ErrorType.BAD_REQUEST, "Either path or asset_id is required")
    normalized_format = _normalize_derivative_format(format)
    variant = derivative_variant(kind, max_long_edge, quality, normalized_format)

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

    if asset_id is not None and (explicit_asset_id or scheduler.is_running()):
        ready = await run_in_threadpool(scheduler.get_ready_derivative, asset_id, kind, variant)
        if ready is None:
            try:
                derivative_id = await run_in_threadpool(
                    scheduler.schedule_derivative,
                    asset_id,
                    kind,
                    variant,
                    0,
                    max_long_edge=max_long_edge,
                    quality=quality,
                    format=normalized_format,
                )
            except FileNotFoundError as exc:
                raise APIError(404, ErrorType.NOT_FOUND, "Image file not found") from exc

            def wait_for_derivative():
                deadline = time.monotonic() + 10
                current_derivative_id = derivative_id
                rescheduled = False
                while time.monotonic() < deadline:
                    outcome = scheduler.get_derivative_outcome(current_derivative_id)
                    if outcome is None:
                        return None
                    state = outcome["derivative_state"]
                    if state == "ready" and outcome.get("cache_path") and Path(outcome["cache_path"]).is_file():
                        return scheduler.get_ready_derivative(asset_id, kind, variant)
                    if state == "failed":
                        return ("failed", outcome)
                    if state == "deferred_capacity":
                        return ("deferred", outcome)
                    if state == "skipped":
                        result_code = outcome.get("result_code")
                        if result_code == "source_changed" and not rescheduled:
                            rescheduled = True
                            new_id = scheduler.schedule_derivative(
                                asset_id,
                                kind,
                                variant,
                                0,
                                max_long_edge=max_long_edge,
                                quality=quality,
                                format=normalized_format,
                            )
                            if new_id:
                                current_derivative_id = new_id
                                continue
                        return ("skipped", outcome)
                    time.sleep(0.05)
                return None

            wait_result = await run_in_threadpool(wait_for_derivative)
            if isinstance(wait_result, tuple):
                outcome_kind, outcome = wait_result
                if outcome_kind == "failed":
                    result_code = outcome.get("result_code")
                    if result_code == "invalid_source":
                        raise APIError(400, ErrorType.INVALID_FILE, failure_message)
                    if result_code in {"attempts_exhausted", "internal_error"}:
                        raise APIError(500, ErrorType.SERVER_ERROR, "Generated image worker failed")
                    raise APIError(500, ErrorType.SERVER_ERROR, "Generated image generation failed")
                if outcome_kind == "deferred":
                    raise APIError(
                        507,
                        ErrorType.CAPACITY_EXCEEDED,
                        "Derivative generation deferred: storage capacity limit reached",
                    )
                if outcome_kind == "skipped":
                    result_code = outcome.get("result_code")
                    if result_code in ("source_missing", "asset_inactive"):
                        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
                    if result_code == "source_changed":
                        raise APIError(409, ErrorType.SERVER_ERROR, "Image changed while its derivative was generated")
                    raise APIError(500, ErrorType.SERVER_ERROR, "Generated image request reached a terminal state")
                return None
            ready = wait_result
        if ready is None:
            raise APIError(503, ErrorType.SERVER_ERROR, "Derivative generation timed out")
        cache_path = str(ready["cache_path"])
        scheduler.acquire_serving(cache_path)
        return FileResponse(
            cache_path,
            media_type=DERIVATIVE_MEDIA_TYPES[normalized_format],
            headers=headers,
            background=BackgroundTask(scheduler.release_serving, cache_path),
        )

    try:
        queued_at = time.perf_counter()
        request_timing: dict[str, float] = {}

        def generate_for_request() -> bytes:
            request_timing["queue_wait_ms"] = (time.perf_counter() - queued_at) * 1000
            return generate_derivative(
                file_path,
                kind=kind,
                max_long_edge=max_long_edge,
                quality=quality,
                format=normalized_format,
                no_upscale=True,
                request_timing=request_timing,
            )

        derivative_bytes = await run_in_threadpool(
            generate_for_request,
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

    headers["Server-Timing"] = (
        f"queue;dur={request_timing.get('queue_wait_ms', 0):.3f}, "
        f"derivative;dur={request_timing.get('render_encode_persist_ms', 0):.3f}"
    )

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
    path: str | None = Query(None, description="Absolute path to image file"),
    asset_id: int | None = Query(None, ge=1, description="Catalog asset ID"),
    max_long_edge: int = Query(512, ge=1, le=4096, description="Max long edge for grid thumbnail"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
):
    """Serve optimized WebP thumbnail.

    Uses persistent disk cache backed by diskcache.
    Returns FileResponse with proper HTTP caching headers when the cache file exists.
    """
    return await _serve_derivative(
        request=request,
        path=path,
        asset_id=asset_id,
        kind="thumbnail",
        max_long_edge=_resolve_max_long_edge(max_long_edge, max_size),
        quality=78,
        format="webp",
        failure_message="Unable to process image",
    )


@router.get("/api/preview")
async def api_preview(
    request: Request,
    path: str | None = Query(None, description="Absolute path to image file"),
    asset_id: int | None = Query(None, ge=1, description="Catalog asset ID"),
    max_long_edge: int = Query(1440, ge=1, le=4096, description="Max long edge for viewer preview"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
):
    """Serve optimized WebP viewer preview.

    The preview derivative is distinct from thumbnails and originals.
    """
    return await _serve_derivative(
        request=request,
        path=path,
        asset_id=asset_id,
        kind="preview",
        max_long_edge=_resolve_max_long_edge(max_long_edge, max_size),
        quality=86,
        format="webp",
        failure_message="Unable to generate preview",
    )
