"""File-health report and runtime diagnostics API for the Maintenance page."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .indexer import get_metadata_lifecycle_status
from .integrity_checker import integrity_checker
from .metadata_store import _DB_LOCK, _connect
from .metadata_store.maintenance_store import get_latest_run
from .metadata_store.status_store import build_global_runtime

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class MaintenanceRuntimeResponse(BaseModel):
    """Response envelope for the runtime diagnostics endpoint."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    global_runtime: dict
    metadata_lifecycle: dict | None


@router.get("/runtime")
async def get_maintenance_runtime():
    """Return global runtime diagnostics and metadata lifecycle counters."""
    global_runtime = build_global_runtime()
    try:
        lifecycle = get_metadata_lifecycle_status()
    except Exception:  # noqa: BLE001
        lifecycle = None
    return MaintenanceRuntimeResponse(global_runtime=global_runtime, metadata_lifecycle=lifecycle)


class FileHealthIssues(BaseModel):
    """File-health issue counters for a maintenance run."""

    model_config = ConfigDict(extra="forbid")
    missing_source_files: int
    generated_image_missing: int
    metadata_mismatch: int
    orphaned_work_item: int
    generated_image_job_mismatch: int


class FileHealthRepairs(BaseModel):
    """File-health repair counters for a maintenance run."""

    model_config = ConfigDict(extra="forbid")
    repaired: int
    requeued: int
    failed: int
    unchanged: int


class FileHealthRun(BaseModel):
    """A single file-health check run."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: int
    trigger: str
    started_at: float
    finished_at: float | None
    status: str
    error: str | None
    issues: FileHealthIssues
    repairs: FileHealthRepairs


class FileHealthResponse(BaseModel):
    """Response envelope for file-health endpoints."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    run: FileHealthRun | None


@router.get("/file-health")
async def get_file_health():
    """Return the latest file-health check run, or null if never run."""
    with _DB_LOCK, _connect() as conn:
        run = get_latest_run(conn)
    if run is None:
        return FileHealthResponse(run=None)
    return FileHealthResponse(
        run=FileHealthRun(
            id=run["id"],
            trigger=run["trigger"],
            started_at=run["started_at"],
            finished_at=run["finished_at"],
            status=run["status"],
            error=run["error"],
            issues=FileHealthIssues(**run["issues"]),
            repairs=FileHealthRepairs(**run["repairs"]),
        )
    )


@router.post("/file-health/check")
async def post_file_health_check():
    """Trigger a new file-health check run."""
    if integrity_checker.is_running:
        return JSONResponse(status_code=409, content={"run": None, "error": "check already running"})
    summary = integrity_checker.run_and_persist(trigger="manual")
    return FileHealthResponse(
        run=FileHealthRun(
            id=summary["id"],
            trigger=summary["trigger"],
            started_at=summary["started_at"],
            finished_at=summary["finished_at"],
            status=summary["status"],
            error=summary["error"],
            issues=FileHealthIssues(**summary["issues"]),
            repairs=FileHealthRepairs(**summary["repairs"]),
        )
    )
