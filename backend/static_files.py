"""Serve the production frontend shell and static assets."""

import mimetypes
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .config import FRONTEND_DIST, PRODUCTION

router = APIRouter()


@router.get("/")
async def read_root():
    """Return the frontend shell in production or a development API marker."""
    if PRODUCTION:
        return FileResponse(str(FRONTEND_DIST / "index.html"), media_type="text/html")
    return {"message": "Museum Art Gallery API"}


@router.get("/api/landing-pages")
def get_landing_pages():
    """List static landing-page HTML files bundled under frontend public assets."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    landpage_dir = os.path.join(base_dir, "..", "frontend", "public", "landpage")

    pages = []
    if os.path.exists(landpage_dir):
        for root, _dirs, files in os.walk(landpage_dir):
            for file in files:
                if file.lower().endswith(".html"):
                    public_dir = os.path.join(base_dir, "..", "frontend", "public")
                    rel_path = os.path.relpath(os.path.join(root, file), public_dir)

                    url_path = "/" + rel_path.replace(os.sep, "/")
                    pages.append(url_path)

    return pages


@router.api_route("/{path:path}", methods=["GET"], include_in_schema=False)
async def catch_all(path: str):
    """Serve production frontend assets or fall back to the SPA entrypoint."""
    if not PRODUCTION:
        raise HTTPException(status_code=404, detail="Only available in production mode")
    if path.startswith("api/") or path.startswith("openapi") or path.startswith("docs"):
        raise HTTPException(status_code=404, detail="Not Found")
    frontend_root = FRONTEND_DIST.resolve()
    file_path = (frontend_root / path).resolve()
    if path and file_path.is_relative_to(frontend_root) and file_path.is_file():
        media_type, _ = mimetypes.guess_type(str(file_path))
        return FileResponse(str(file_path), media_type=media_type)
    return FileResponse(str(FRONTEND_DIST / "index.html"), media_type="text/html")
