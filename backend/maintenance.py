"""File-health report API for the Maintenance page."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .integrity_checker import integrity_checker
from .metadata_store import _DB_LOCK, _connect
from .metadata_store.maintenance_store import get_latest_run

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class FileHealthRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: int
    trigger: str
    started_at: float
    finished_at: float | None
    status: str
    error: str | None
    issues: dict[str, int]
    repairs: dict[str, int]


class FileHealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    run: FileHealthRun | None


@router.get("/file-health")
async def get_file_health():
    with _DB_LOCK, _connect() as conn:
        run = get_latest_run(conn)
    if run is None:
        return FileHealthResponse(run=None)
    return FileHealthResponse(run=FileHealthRun(**run))


@router.post("/file-health/check")
async def post_file_health_check():
    if integrity_checker.is_running:
        raise HTTPException(status_code=409, detail="check already running")
    summary = integrity_checker.run_and_persist(trigger="manual")
    return FileHealthResponse(run=FileHealthRun(**summary))
