"""Configure the FastAPI application, routers, middleware, and startup hooks."""

import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
from .metadata_parse import router as metadata_parse_router
from .metadata_store import recover_stale_jobs
from .refresh import start_refresh as _start_refresh
from .refresh import stop_refresh as _stop_refresh
from .scan import router as scan_router
from .scan_worker import queue_startup_scans, start, stop
from .search import router as search_router
from .static_files import router as static_files_router
from .thumbnails import router as thumbnails_router
from .video import router as video_router
from .watcher import start_watcher as _start_watcher
from .watcher import stop_watcher as _stop_watcher


def _get_cors_origins() -> list[str]:
    origin = os.getenv("FRONTEND_ORIGIN")
    port = os.getenv("FRONTEND_PORT")

    origins: list[str] = []
    if origin:
        origins.append(origin.rstrip("/"))
    if port:
        origins.extend(
            [
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            ]
        )

    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    return origins


VPS_IP = "http://150.230.56.153"
VPS_ORIGINS = [f"{VPS_IP}:4180", f"{VPS_IP}:4173", f"{VPS_IP}:5173"]

app = FastAPI(title="Museum Art Gallery API")

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
    allow_origins=_get_cors_origins() + VPS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(images_router)
app.include_router(thumbnails_router)
app.include_router(video_router)
app.include_router(metadata_parse_router)
app.include_router(scan_router)
app.include_router(browse_router)
app.include_router(folders_router)
app.include_router(search_router)
app.include_router(health_router)
app.include_router(indexer_router)
app.include_router(libraries_router)
app.include_router(facets_router)
app.include_router(static_files_router)


@app.on_event("startup")
async def _startup_background_services():
    recover_stale_jobs()
    recover_metadata_index_jobs()  # Phase 4: recover metadata jobs
    if GALLERY_CATALOG_SERVICE_ENABLED:
        start()
        if GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED:
            queue_startup_scans()
    # Phase 2: DB-claim worker is authoritative
    metadata_worker.start()
    if INTEGRITY_CHECK_ENABLED:
        integrity_checker.start()
    scheduler.start()
    _start_refresh()
    _start_watcher()


@app.on_event("shutdown")
async def _shutdown_background_services():
    _stop_watcher()
    _stop_refresh()
    stop()
    metadata_worker.stop()
    scheduler.stop()
    integrity_checker.stop()


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
