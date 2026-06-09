import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import ENABLE_METRICS, ENABLE_PROFILER, PROFILE_DIR, PROFILE_ENDPOINTS
from .images import router as images_router
from .thumbnails import router as thumbnails_router
from .metadata_parse import router as metadata_parse_router


def _get_cors_origins() -> list[str]:
    origin = os.getenv("FRONTEND_ORIGIN")
    port = os.getenv("FRONTEND_PORT")

    origins: list[str] = []
    if origin:
        origins.append(origin.rstrip("/"))
    if port:
        origins.extend([
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ])

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
app.include_router(metadata_parse_router)

if ENABLE_PROFILER:
    import pyinstrument

    @app.middleware("http")
    async def profile_middleware(request: Request, call_next):
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
