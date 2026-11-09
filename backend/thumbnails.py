"""Generate and serve cached WebP thumbnail and preview derivatives."""

import hashlib
import math
import os
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from starlette.background import BackgroundTask

from . import config as _config
from .config import THUMBNAIL_CACHE_DIR
from .derivative_fastpath import FastPathEntry, FastPathKey, derivative_fast_path, fast_path_key
from .disk_cache import ThreadClosingCache
from .errors import APIError, ErrorType
from .files import check_image_limits, content_version, is_image, is_permanent_decode_error
from .metadata_store import image_dimensions_unchanged, upsert_image_dimensions
from .scan import require_media_path_allowed

_thumbnail_disk_cache = ThreadClosingCache(str(THUMBNAIL_CACHE_DIR), size_limit=64 * 1024 * 1024)
_thumbnail_file_dir = THUMBNAIL_CACHE_DIR / "files"
DERIVATIVE_CACHE_VERSION = "v3"
_CACHE_VERSION_KEY = "__gallery_derivative_cache_version__"
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


def _initialize_path_metadata_cache() -> None:
    """Clear legacy byte-valued entries once and retain only path metadata."""
    if _thumbnail_disk_cache.get(_CACHE_VERSION_KEY) != DERIVATIVE_CACHE_VERSION:
        _thumbnail_disk_cache.clear()
        _thumbnail_disk_cache.set(_CACHE_VERSION_KEY, DERIVATIVE_CACHE_VERSION)


_initialize_path_metadata_cache()


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
    """Clear diskcache path metadata while preserving the version marker."""
    count = max(0, len(_thumbnail_disk_cache) - int(_CACHE_VERSION_KEY in _thumbnail_disk_cache))
    _thumbnail_disk_cache.clear()
    _thumbnail_disk_cache.set(_CACHE_VERSION_KEY, DERIVATIVE_CACHE_VERSION)
    return int(count)


WEBP_ENCODE_METHOD = 4
"""libwebp effort for every WebP derivative (0 fastest .. 6 smallest).

Method 4 encodes about 2x faster than the former method 6 for roughly 7 % more bytes; the pixels are the
same quality setting, so it is a pure speed trade. It does not change a derivative's URL, dimensions or
``DERIVATIVE_CACHE_VERSION`` compatibility: files rendered with either method are interchangeable.
"""


@dataclass(frozen=True)
class DerivativeSpec:
    """One variant a cascade render has to produce from a single decode of the source."""

    kind: DerivativeKind
    max_long_edge: int
    quality: int
    format: str
    no_upscale: bool = True


@dataclass(frozen=True)
class RenderedDerivative:
    """A variant the cascade rendered (or found already cached) and persisted."""

    path: Path
    byte_size: int


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white and return an RGB (or L) image, as every derivative expects."""
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGBA")
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _record_image_dimensions(
    path: Path,
    width: int,
    height: int,
    *,
    image_format: str,
    mode: str,
    has_alpha: bool,
) -> None:
    """Persist the source dimensions a decode just observed, unless the catalog already holds them.

    Every render used to be a writer op even when nothing changed; the read-only comparison keeps the
    single database writer free for work that matters (claims, completions).
    """
    if image_dimensions_unchanged(path, width, height, image_format=image_format, mode=mode, has_alpha=has_alpha):
        return
    upsert_image_dimensions(
        path,
        width,
        height,
        image_format=image_format,
        mode=mode,
        has_alpha=has_alpha,
    )


def _decode_source_rgb(path: Path) -> Image.Image:
    """Decode, orient and flatten the source once; record its dimensions in the catalog."""
    with Image.open(path) as img:
        source_format = img.format or ""
        source_mode = img.mode or ""
        source_has_alpha = source_mode in {"RGBA", "LA"} or (source_mode == "P" and "transparency" in img.info)

        img = ImageOps.exif_transpose(img)
        oriented_width, oriented_height = img.size
        _record_image_dimensions(
            path,
            oriented_width,
            oriented_height,
            image_format=source_format,
            mode=source_mode,
            has_alpha=source_has_alpha,
        )
        return _flatten_to_rgb(img)


def _contain_size(width: int, height: int, edge: int) -> tuple[int, int] | None:
    """Return the size ``Image.thumbnail((edge, edge))`` would produce, or None when it would not shrink."""
    if edge >= width and edge >= height:
        return None
    aspect = width / height

    def round_aspect(number: float, key) -> int:  # noqa: ANN001
        return max(min(math.floor(number), math.ceil(number), key=key), 1)

    x = y = edge
    if x / y >= aspect:
        x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def _fit_image(img: Image.Image, max_long_edge: int, *, no_upscale: bool) -> Image.Image:
    """Return ``img`` resized to ``max_long_edge`` without mutating it (it may feed sibling variants)."""
    if no_upscale:
        size = _contain_size(img.width, img.height, max_long_edge)
        if size is None or size == img.size:
            return img
        return img.resize(size, Image.Resampling.LANCZOS, reducing_gap=2.0)
    if max(img.size) == max_long_edge:
        return img
    scale = max_long_edge / max(img.size)
    new_size = (
        max(1, round(img.size[0] * scale)),
        max(1, round(img.size[1] * scale)),
    )
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _encode_image(img: Image.Image, normalized_format: str, quality: int) -> bytes:
    buffer = BytesIO()
    save_kwargs: dict[str, int] = {"quality": quality}
    if normalized_format == "webp":
        save_kwargs["method"] = WEBP_ENCODE_METHOD
    img.save(buffer, format=DERIVATIVE_PIL_FORMATS[normalized_format], **save_kwargs)
    return buffer.getvalue()


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
    base = _decode_source_rgb(path)
    return _encode_image(_fit_image(base, max_long_edge, no_upscale=no_upscale), normalized_format, quality)


def _map_render_error(exc: Exception) -> Exception:
    """Map permanent decode failures to the API error ``generate_derivative`` has always raised."""
    if is_permanent_decode_error(exc):
        _inc(_derivative_errors_total)
        api_exc = APIError(400, ErrorType.INVALID_FILE, f"Unable to process image: {exc}")
        api_exc.__cause__ = exc
        return api_exc
    return exc


def render_derivatives(
    file_path: Path,
    specs: Sequence[DerivativeSpec],
    *,
    primary: int = 0,
) -> Iterator[tuple[int, RenderedDerivative | Exception]]:
    """Render several variants of one source from a single decode, yielding each as soon as it is persisted.

    Yields ``(index into specs, RenderedDerivative or the Exception that variant failed with)``; every
    spec is yielded exactly once. A variant already present in the persistent cache is yielded without
    decoding; if every variant is cached the source is never opened. ``primary`` (the variant someone is
    waiting for) is rendered and yielded first; the rest follow largest to smallest. Each variant is resized
    from the smallest image already produced in this call that is at least as large (the cascade
    preview -> thumb_512 -> thumb_256 -> thumb_128), otherwise from the decoded source, so the work after the
    first resize is a fraction of a decode. The caller owns durability: it fences and records each yielded
    variant itself, so one variant failing never affects its siblings.
    """
    pending: list[int] = []
    keys: dict[int, str] = {}
    try:
        check_image_limits(file_path)
        for index, spec in enumerate(specs):
            normalized_format = _normalize_derivative_format(spec.format)
            key = _derivative_cache_key_str(
                file_path,
                kind=spec.kind,
                max_long_edge=spec.max_long_edge,
                quality=spec.quality,
                format=normalized_format,
            )
            keys[index] = key
            cached_path = _thumbnail_disk_cache.get(key)
            if isinstance(cached_path, str) and Path(cached_path).is_file():
                yield index, RenderedDerivative(Path(cached_path), Path(cached_path).stat().st_size)
            else:
                pending.append(index)
    except Exception as exc:  # noqa: BLE001 - delivered per variant, like a render failure
        mapped = _map_render_error(exc)
        for index in range(len(specs)):
            if index not in keys or index in pending:
                yield index, mapped
        return
    if not pending:
        return

    order = sorted(pending, key=lambda i: (i != primary, -specs[i].max_long_edge, i))
    try:
        base = _decode_source_rgb(file_path)
    except Exception as exc:  # noqa: BLE001
        mapped = _map_render_error(exc)
        for index in order:
            yield index, mapped
        return

    produced: list[Image.Image] = [base]
    for index in order:
        spec = specs[index]
        try:
            normalized_format = _normalize_derivative_format(spec.format)
            source = base
            if spec.no_upscale:
                larger = [im for im in produced if max(im.size) >= spec.max_long_edge]
                source = min(larger, key=lambda im: max(im.size), default=base)
            fitted = _fit_image(source, spec.max_long_edge, no_upscale=spec.no_upscale)
            if all(fitted is not existing for existing in produced):
                produced.append(fitted)
            derivative_bytes = _encode_image(fitted, normalized_format, spec.quality)
            derivative_path = _persist_derivative_file(keys[index], derivative_bytes, normalized_format)
            _thumbnail_disk_cache.set(keys[index], str(derivative_path))
            _inc(_derivative_ready_total, spec.kind)
            result: RenderedDerivative | Exception = RenderedDerivative(derivative_path, len(derivative_bytes))
        except Exception as exc:  # noqa: BLE001
            result = _map_render_error(exc)
        yield index, result


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

    cached_path = _thumbnail_disk_cache.get(cache_key)
    if isinstance(cached_path, str) and Path(cached_path).is_file():
        return Path(cached_path).read_bytes()

    try:
        render_started = time.perf_counter()
        derivative_bytes = _render_derivative_impl(
            file_path,
            max_long_edge=max_long_edge,
            quality=quality,
            format=normalized_format,
            no_upscale=no_upscale,
        )
        derivative_path = _persist_derivative_file(cache_key, derivative_bytes, normalized_format)
        _thumbnail_disk_cache.set(cache_key, str(derivative_path))
        if request_timing is not None:
            request_timing["render_encode_persist_ms"] = (time.perf_counter() - render_started) * 1000
        _inc(_derivative_ready_total, kind)
        return derivative_bytes
    except Exception as exc:  # noqa: BLE001 - only permanent decode failures become 400; the rest propagate
        if not is_permanent_decode_error(exc):
            raise
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


def _resolve_derivative_source(path: str | None, asset_id: int | None) -> tuple[Path, int, os.stat_result]:
    """Resolve and stat a derivative source outside the async event loop."""
    from .derivative_scheduler import scheduler

    if asset_id is not None:
        asset_path = scheduler.get_asset_path(asset_id)
        if asset_path is None:
            raise APIError(404, ErrorType.NOT_FOUND, "Asset not found")
        file_path = _resolve_image_request_path(str(asset_path))
    elif path is not None:
        file_path = _resolve_image_request_path(path)
        asset_id = scheduler.find_asset_id(file_path)
    else:
        raise APIError(400, ErrorType.BAD_REQUEST, "Either path or asset_id is required")
    if asset_id is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Asset not found")
    return file_path, asset_id, file_path.stat()


def _resolve_max_long_edge(max_long_edge: int, max_size: int | None) -> int:
    return max_size if max_size is not None else max_long_edge


def _validate_public_size(kind: DerivativeKind, value: int) -> int:
    allowed = {128, 256, 512} if kind == "thumbnail" else {1440}
    if value not in allowed:
        raise APIError(422, ErrorType.BAD_REQUEST, f"Unsupported {kind} size")
    return value


REVALIDATE_CACHE_CONTROL = "public, max-age=0, must-revalidate"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _derivative_etag(
    kind: DerivativeKind, mtime_ns: int, size: int, max_long_edge: int, normalized_format: str, quality: int
) -> str:
    return f'"{kind}-{DERIVATIVE_CACHE_VERSION}-{mtime_ns}-{size}-{max_long_edge}-{normalized_format}-{quality}"'


def _response_headers(etag: str, version: str | None, mtime_ns: int, size: int) -> dict[str, str]:
    """Return the caching headers: immutable only when ``version`` names the file as it is on disk right now.

    A URL carrying a matching ``v`` can never address different bytes later (a changed source has a new
    identity, hence a new ``v``), so the browser may keep it for a year without revalidating. An absent or
    stale ``v`` keeps the revalidating behaviour of an unversioned URL.
    """
    immutable = version is not None and version == content_version(mtime_ns, size)
    return {
        "Cache-Control": IMMUTABLE_CACHE_CONTROL if immutable else REVALIDATE_CACHE_CONTROL,
        "ETag": etag,
    }


def _check_fast_path(key: FastPathKey) -> tuple[FastPathEntry, os.stat_result] | None:
    """Return ``(entry, source stat)`` when a remembered resolution is still true of the file on disk.

    Runs in the thread pool (the stat may touch a network mount). An entry whose source identity no longer
    matches, or whose source is gone, is dropped so the full path re-resolves and reschedules.
    """
    entry = derivative_fast_path.get(key)
    if entry is None:
        return None
    try:
        stat = os.stat(entry.source_path)
    except OSError:
        derivative_fast_path.discard(key, entry)
        return None
    if stat.st_mtime_ns != entry.mtime_ns or stat.st_size != entry.size:
        derivative_fast_path.discard(key, entry)
        return None
    return entry, stat


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
    version: str | None = None,
):
    from .derivative_scheduler import derivative_variant, scheduler

    normalized_format = _normalize_derivative_format(format)
    variant = derivative_variant(kind, max_long_edge, quality, normalized_format)

    fast_key = fast_path_key(str(_config.GALLERY_METADATA_DB), path, asset_id, kind, variant)
    if fast_key is not None and derivative_fast_path.enabled:
        hit = await run_in_threadpool(_check_fast_path, fast_key)
        if hit is not None:
            entry, hit_stat = hit
            hit_headers = _response_headers(entry.etag, version, hit_stat.st_mtime_ns, hit_stat.st_size)
            if request.headers.get("if-none-match") == entry.etag:
                return Response(status_code=304, headers=hit_headers)
            if await run_in_threadpool(scheduler.try_acquire_serving, entry.cache_path):
                return FileResponse(
                    entry.cache_path,
                    media_type=DERIVATIVE_MEDIA_TYPES[normalized_format],
                    headers=hit_headers,
                    background=BackgroundTask(scheduler.release_serving, entry.cache_path),
                )
            derivative_fast_path.discard(fast_key, entry)

    file_path, asset_id, stat = await run_in_threadpool(_resolve_derivative_source, path, asset_id)

    etag = _derivative_etag(kind, stat.st_mtime_ns, stat.st_size, max_long_edge, normalized_format, quality)
    headers = _response_headers(etag, version, stat.st_mtime_ns, stat.st_size)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    if asset_id is not None:
        ready = await run_in_threadpool(
            scheduler.acquire_ready_derivative,
            asset_id,
            kind,
            variant,
            source_mtime_ns=stat.st_mtime_ns,
            source_size=stat.st_size,
        )
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
                poll_seconds = 0.03
                current_derivative_id = derivative_id
                rescheduled = False
                while time.monotonic() < deadline:
                    if not scheduler.is_running():
                        scheduler.run_once()
                    outcome = scheduler.get_derivative_outcome(current_derivative_id)
                    if outcome is None:
                        return None
                    state = outcome["derivative_state"]
                    if state == "ready" and outcome.get("cache_path") and Path(outcome["cache_path"]).is_file():
                        return scheduler.acquire_ready_derivative(asset_id, kind, variant)
                    if state == "failed":
                        return ("failed", outcome)
                    if state == "deferred_capacity":
                        return ("deferred", outcome)
                    if state == "evicted":
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
                    # Back off: dozens of requests waiting at once (a grid opening) would otherwise poll the
                    # catalog 20x/s each and starve the render workers of the GIL.
                    time.sleep(poll_seconds)
                    poll_seconds = min(poll_seconds * 1.4, 0.4)
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
        if (
            fast_key is not None
            and int(ready["source_mtime_ns"]) == stat.st_mtime_ns
            and int(ready["source_size"]) == stat.st_size
        ):
            derivative_fast_path.put(
                fast_key,
                source_path=str(file_path),
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                asset_id=asset_id,
                derivative_id=int(ready["id"]),
                cache_path=cache_path,
                etag=etag,
            )
        return FileResponse(
            cache_path,
            media_type=DERIVATIVE_MEDIA_TYPES[normalized_format],
            headers=headers,
            background=BackgroundTask(scheduler.release_serving, cache_path),
        )


@router.get("/api/thumbnail")
async def api_thumbnail(
    request: Request,
    path: str | None = Query(None, description="Absolute path to image file"),
    asset_id: int | None = Query(None, ge=1, description="Catalog asset ID"),
    max_long_edge: int = Query(512, ge=1, le=4096, description="Max long edge for grid thumbnail"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
    v: str | None = Query(
        None,
        max_length=128,
        description="Source content_version; a match with the current source makes the response immutable",
    ),
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
        max_long_edge=_validate_public_size("thumbnail", _resolve_max_long_edge(max_long_edge, max_size)),
        quality=78,
        format="webp",
        failure_message="Unable to process image",
        version=v,
    )


@router.get("/api/preview")
async def api_preview(
    request: Request,
    path: str | None = Query(None, description="Absolute path to image file"),
    asset_id: int | None = Query(None, ge=1, description="Catalog asset ID"),
    max_long_edge: int = Query(1440, ge=1, le=4096, description="Max long edge for viewer preview"),
    max_size: int | None = Query(None, ge=1, le=4096, description="Deprecated alias for max_long_edge"),
    v: str | None = Query(
        None,
        max_length=128,
        description="Source content_version; a match with the current source makes the response immutable",
    ),
):
    """Serve optimized WebP viewer preview.

    The preview derivative is distinct from thumbnails and originals.
    """
    return await _serve_derivative(
        request=request,
        path=path,
        asset_id=asset_id,
        kind="preview",
        max_long_edge=_validate_public_size("preview", _resolve_max_long_edge(max_long_edge, max_size)),
        quality=86,
        format="webp",
        failure_message="Unable to generate preview",
        version=v,
    )
