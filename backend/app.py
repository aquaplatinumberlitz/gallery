"""Configure the FastAPI application, routers, middleware, and startup hooks."""

import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import indexer as metadata_indexer
from .browse import router as browse_router
from .config import (
    ENABLE_METRICS,
    ENABLE_PROFILER,
    GALLERY_CATALOG_SERVICE_ENABLED,
    GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED,
    INTEGRITY_CHECK_ENABLED,
    PROFILE_DIR,
    PROFILE_ENDPOINTS,
)
from .derivative_scheduler import scheduler
from .facets import router as facets_router
from .folders import router as folders_router
from .health import router as health_router
from .images import router as images_router
from .indexer import metadata_worker, recover_metadata_index_jobs
from .indexer import router as indexer_router
from .integrity_checker import integrity_checker
from .libraries import router as libraries_router
from .maintenance import router as maintenance_router
from .metadata_parse import router as metadata_parse_router
from .metadata_store import recover_stale_jobs
from .paths import InvalidPathError
from .refresh import start_refresh as _start_refresh
from .refresh import stop_refresh as _stop_refresh
from .scan import router as scan_router
from .scan_worker import queue_startup_scans, start, stop
from .search import router as search_router
from .security import require_trusted_proxy, validate_trusted_proxy_configuration
from .static_files import router as static_files_router
from .thumbnails import router as thumbnails_router
from .video import router as video_router
from .watcher import start_watcher as _start_watcher
from .watcher import stop_watcher as _stop_watcher

LOGGER = logging.getLogger(__name__)


def _get_cors_origins() -> list[str]:
    origin = os.getenv("FRONTEND_ORIGIN")
    port = os.getenv("FRONTEND_PORT")

    origins: list[str] = []
    configured = os.getenv("GALLERY_CORS_ORIGINS", "")
    origins.extend(value.strip().rstrip("/") for value in configured.split(",") if value.strip())
    if origin:
        origins.append(origin.rstrip("/"))
    if port and port.isdigit() and 1 <= int(port) <= 65535:
        origins.extend(
            [
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            ]
        )

    if not origins:
        origins = ["http://localhost:4702", "http://127.0.0.1:4702"]

    validated: list[str] = []
    for value in origins:
        parsed = urlsplit(value)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {"", "/"}
        ):
            normalized = value.rstrip("/")
            if normalized not in validated:
                validated.append(normalized)
    return validated


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    cleanups: list[tuple[str, Callable[[], object]]] = []
    try:
        validate_trusted_proxy_configuration()
        recover_stale_jobs()
        if metadata_indexer.METADATA_INDEXER_ENABLED:
            recover_metadata_index_jobs()
        if GALLERY_CATALOG_SERVICE_ENABLED:
            start()
            cleanups.append(("catalog", stop))
            if GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED:
                queue_startup_scans()
        if metadata_indexer.METADATA_INDEXER_ENABLED:
            metadata_worker.start()
            cleanups.append(("metadata", metadata_worker.stop))
        if INTEGRITY_CHECK_ENABLED:
            integrity_checker.start()
            cleanups.append(("integrity", integrity_checker.stop))
        scheduler.start()
        cleanups.append(("derivative", scheduler.stop))
        _start_refresh()
        cleanups.append(("refresh", _stop_refresh))
        _start_watcher()
        cleanups.append(("watcher", _stop_watcher))
        yield
    finally:
        for service_name, cleanup in reversed(cleanups):
            try:
                cleanup()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Backend service shutdown failed: %s", service_name)


app = FastAPI(title="Museum Art Gallery API", lifespan=_lifespan)

if ENABLE_METRICS:
    from prometheus_fastapi_instrumentator import Instrumentator

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/favicon.ico"],
    )
    instrumentator.instrument(app).expose(app, include_in_schema=False, should_gzip=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=os.getenv("GALLERY_CORS_ALLOW_CREDENTIALS", "0").lower() in {"1", "true", "yes"},
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

_api_dependencies = [Depends(require_trusted_proxy)]
app.include_router(images_router, dependencies=_api_dependencies)
app.include_router(thumbnails_router, dependencies=_api_dependencies)
app.include_router(video_router, dependencies=_api_dependencies)
app.include_router(metadata_parse_router, dependencies=_api_dependencies)
app.include_router(scan_router, dependencies=_api_dependencies)
app.include_router(browse_router, dependencies=_api_dependencies)
app.include_router(folders_router, dependencies=_api_dependencies)
app.include_router(search_router, dependencies=_api_dependencies)
app.include_router(health_router, dependencies=_api_dependencies)
app.include_router(indexer_router, dependencies=_api_dependencies)
app.include_router(libraries_router, dependencies=_api_dependencies)
app.include_router(maintenance_router, dependencies=_api_dependencies)
app.include_router(facets_router, dependencies=_api_dependencies)
app.include_router(static_files_router)


@app.exception_handler(InvalidPathError)
async def invalid_path_handler(_request: Request, _exc: InvalidPathError) -> JSONResponse:
    """Map malformed external paths to a stable validation response."""
    return JSONResponse(
        status_code=400,
        content={"detail": {"error": "bad_request", "message": "Invalid path"}},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures with traceback without disclosing internals."""
    LOGGER.exception("Unhandled backend error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": {"error": "server_error", "message": "Internal server error"}},
    )


if ENABLE_PROFILER:
    import pyinstrument

    @app.middleware("http")
    async def profile_middleware(request: Request, call_next):
        """Profile selected requests and write pyinstrument HTML reports to disk."""
        if request.url.path not in PROFILE_ENDPOINTS:
            return await call_next(request)
        profiler = pyinstrument.Profiler()
        profiler.start()
        response = await call_next(request)
        profiler.stop()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_path = request.url.path.replace("/", "_")
        html_path = PROFILE_DIR / f"{safe_path}_{timestamp}.html"
        with open(html_path, "w") as f:
            f.write(profiler.output_html())
        return response
