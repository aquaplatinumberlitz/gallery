"""Parse image metadata for the lightbox API with DB and memory caching."""

import copy
import json
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

from cachetools import LRUCache
from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .config import METADATA_CACHE_MAX_BYTES
from .errors import APIError, ErrorType
from .files import check_image_limits, is_image
from .metadata_extract import extract_metadata, extracted_metadata_to_api, metadata_sidecar_identity
from .metadata_store import get_lightbox_metadata, upsert_extracted_metadata
from .paths import is_path_safe, resolve_path


def _estimate_dict_size(d: dict) -> int:
    """Estimate memory size of a dict in bytes (rough approximation)."""
    try:
        return len(json.dumps(d, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return sys.getsizeof(d)


_metadata_cache: LRUCache = LRUCache(maxsize=METADATA_CACHE_MAX_BYTES, getsizeof=_estimate_dict_size)
_metadata_cache_lock = threading.Lock()
_metadata_inflight: dict[tuple, Future[dict]] = {}

router = APIRouter()


def _parse_metadata_uncached(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    try:
        check_image_limits(path)
        extracted = extract_metadata(path)
        upsert_extracted_metadata(extracted, mark_job_done=True)
        return extracted_metadata_to_api(extracted)

    except APIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise APIError(400, ErrorType.INVALID_FILE, f"Unable to parse metadata: {exc}") from exc


def _metadata_cache_key(path: Path) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size, *metadata_sidecar_identity(path))


def parse_metadata(path: Path) -> dict:
    """Parse and cache image metadata.

    Uses DB-first warm reads with LRU fallback for optimal performance.
    """
    if not path.exists() or not path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")

    try:
        key = _metadata_cache_key(path)
    except OSError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found") from exc

    with _metadata_cache_lock:
        cached = _metadata_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        db_meta = get_lightbox_metadata(path)
        if db_meta is not None:
            _metadata_cache[key] = db_meta
            return copy.deepcopy(db_meta)

        future = _metadata_inflight.get(key)
        if future is None:
            future = Future()
            _metadata_inflight[key] = future
            is_producer = True
        else:
            is_producer = False

    if not is_producer:
        return copy.deepcopy(future.result())

    try:
        metadata = _parse_metadata_uncached(path)
        with _metadata_cache_lock:
            _metadata_cache[key] = metadata
        future.set_result(metadata)
        return copy.deepcopy(metadata)
    except OSError as exc:
        api_exc = APIError(404, ErrorType.NOT_FOUND, "Image file not found")
        future.set_exception(api_exc)
        raise api_exc from exc
    except APIError as exc:
        future.set_exception(exc)
        raise
    except Exception as exc:  # noqa: BLE001
        api_exc = APIError(500, ErrorType.SERVER_ERROR, "Internal server error")
        future.set_exception(api_exc)
        raise api_exc from exc
    finally:
        with _metadata_cache_lock:
            _metadata_inflight.pop(key, None)


@router.get("/api/metadata")
async def api_metadata(path: str = Query(..., description="Absolute path to image file")):
    """Return normalized metadata for one image after path and type validation."""
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")

    return await run_in_threadpool(parse_metadata, file_path)
