import os
from pathlib import Path

from fastapi import APIRouter, Response


def _get_git_commit() -> str:
    import subprocess as _subprocess
    try:
        return _subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent
        ).stdout.strip()
    except Exception:
        return "unknown"


GIT_COMMIT = _get_git_commit()

router = APIRouter()


@router.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "commit": GIT_COMMIT,
        "features": {
            "metadata_search": True,
        },
    }


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)
