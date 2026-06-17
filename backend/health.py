"""Health and browser-noise endpoints for the backend API."""

import subprocess
from pathlib import Path

from fastapi import APIRouter, Response


def _get_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).parent,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


GIT_COMMIT = _get_git_commit()

router = APIRouter()


@router.get("/api/health")
async def api_health():
    """Return service health, build commit, and feature flags."""
    return {
        "status": "ok",
        "commit": GIT_COMMIT,
        "features": {
            "metadata_search": True,
        },
    }


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Return an empty favicon response to avoid noisy 404s."""
    return Response(status_code=204)
