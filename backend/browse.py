"""Read-only catalog browsing endpoints."""

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .errors import APIError, ErrorType
from .metadata_store import CatalogBrowseScopeError, get_catalog_browse_listing

router = APIRouter()


@router.get("/api/browse")
async def api_browse(
    request: Request,
    library_id: int = Query(..., ge=1),
    path: str | None = Query(None, description="Catalog path to browse; omitted means virtual library root"),
    cursor: int | None = Query(None, ge=0, description="Cursor/offset for mixed media"),
    limit: int | None = Query(None, ge=1, le=5000, description="Max media items to return"),
    include_offline: bool = Query(False, description="Include offline catalog tombstones for diagnostics"),
):
    """Return a read-only catalog listing for a library root or folder."""
    allowed = {"library_id", "path", "cursor", "limit", "include_offline"}
    extra = set(request.query_params.keys()) - allowed
    if extra:
        raise APIError(422, ErrorType.BAD_REQUEST, f"Unexpected query parameters: {', '.join(sorted(extra))}")
    try:
        result = await run_in_threadpool(
            get_catalog_browse_listing,
            library_id,
            path=path,
            cursor=cursor,
            limit=limit,
            include_offline=include_offline,
        )
    except KeyError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found") from exc
    except CatalogBrowseScopeError as exc:
        raise APIError(400, ErrorType.BAD_REQUEST, str(exc)) from exc
    return JSONResponse(content=jsonable_encoder(result))
