"""File-health report API for the Maintenance page."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .integrity_checker import integrity_checker
from .metadata_store import _DB_LOCK, _connect
from .metadata_store.maintenance_store import get_latest_run

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class FileHealthIssues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missing_source_files: int
    generated_image_missing: int
    metadata_mismatch: int
    orphaned_work_item: int
    generated_image_job_mismatch: int


class FileHealthRepairs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repaired: int
    requeued: int
    failed: int
    unchanged: int


class FileHealthRun(BaseModel):
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
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    run: FileHealthRun | None


@router.get("/file-health")
async def get_file_health():
    with _DB_LOCK, _connect() as conn:
        run = get_latest_run(conn)
    if run is None:
        return FileHealthResponse(run=None)
    return FileHealthResponse(run=FileHealthRun(
        id=run["id"],
        trigger=run["trigger"],
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        status=run["status"],
        error=run["error"],
        issues=FileHealthIssues(**run["issues"]),
        repairs=FileHealthRepairs(**run["repairs"]),
    ))


@router.post("/file-health/check")
async def post_file_health_check():
    if integrity_checker.is_running:
        return JSONResponse(status_code=409, content={"run": None, "error": "check already running"})
    summary = integrity_checker.run_and_persist(trigger="manual")
    return FileHealthResponse(run=FileHealthRun(
        id=summary["id"],
        trigger=summary["trigger"],
        started_at=summary["started_at"],
        finished_at=summary["finished_at"],
        status=summary["status"],
        error=summary["error"],
        issues=FileHealthIssues(**summary["issues"]),
        repairs=FileHealthRepairs(**summary["repairs"]),
    ))
