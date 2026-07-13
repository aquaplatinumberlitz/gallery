"""Reference validation and the versioned Related Assets API contract."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter

from .errors import APIError, ErrorType
from .metadata_store._db import _DB_LOCK, _connect, _table_exists
from .metadata_store.path_utils import catalog_path_contains
from .models import (
    APIErrorResponse,
    RelatedAPIErrorResponseV1,
    RelatedIndexComponentStatusV1,
    RelatedSearchRequestV1,
    RelatedSearchResponseV1,
    RelatedSearchStatusV1,
)
from .search_scope import SearchScopeContext, resolve_search_v2_scope

router = APIRouter()
LOGGER = logging.getLogger(__name__)

_RELATED_ERROR_RESPONSES = {
    404: {"model": APIErrorResponse, "description": "Reference asset is outside the authorized scope"},
    409: {"model": RelatedAPIErrorResponseV1, "description": "Reference or required relation index is not ready"},
    503: {"model": RelatedAPIErrorResponseV1, "description": "Persisted relation index is unusable"},
    500: {"model": APIErrorResponse, "description": "Sanitized internal failure"},
}


def _component_status(
    index_name: str,
    *,
    ready: bool,
    indexed_count: int = 0,
    target_count: int = 0,
) -> RelatedIndexComponentStatusV1:
    return RelatedIndexComponentStatusV1(
        index_name=index_name,
        state="ready" if ready else "not_ready",
        usable=ready,
        indexed_count=indexed_count,
        target_count=target_count,
    )


def _related_status(reference_asset_id: int) -> RelatedSearchStatusV1:
    """Report only persisted readiness; never decode or derive media here."""
    with _DB_LOCK, _connect() as conn:
        metadata_ready = _table_exists(conn, "asset_generation_signatures") and bool(
            conn.execute(
                "SELECT 1 FROM asset_generation_signatures WHERE asset_id = ?",
                (reference_asset_id,),
            ).fetchone()
        )
        visual_ready = _table_exists(conn, "asset_visual_fingerprints") and bool(
            conn.execute(
                "SELECT 1 FROM asset_visual_fingerprints WHERE asset_id = ?",
                (reference_asset_id,),
            ).fetchone()
        )
    return RelatedSearchStatusV1(
        metadata=_component_status("generation_signatures", ready=metadata_ready),
        visual=_component_status("visual_fingerprints", ready=visual_ready),
    )


def _reference_asset(reference_asset_id: int, context: SearchScopeContext) -> dict[str, Any]:
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT asset.id, asset.library_id, asset.path, asset.type,
                   asset.offline, asset.deleted_at
            FROM assets AS asset
            JOIN libraries AS library ON library.id = asset.library_id
            WHERE asset.id = ?
            """,
            (reference_asset_id,),
        ).fetchone()
    if row is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Reference asset not found in the authorized scope")
    asset = dict(row)
    if context.library_id is not None and int(asset["library_id"]) != context.library_id:
        raise APIError(404, ErrorType.NOT_FOUND, "Reference asset not found in the authorized scope")
    if context.kind == "folder" and (
        context.folder_path is None or not catalog_path_contains(context.folder_path, str(asset["path"]))
    ):
        raise APIError(404, ErrorType.NOT_FOUND, "Reference asset not found in the authorized scope")
    if asset["type"] != "image" or bool(asset["offline"]) or asset["deleted_at"] is not None:
        raise APIError(409, ErrorType.BAD_REQUEST, "Reference must be an active image")
    return asset


def _required_component(request: RelatedSearchRequestV1, status: RelatedSearchStatusV1):
    return status.visual if request.profile == "visual" else status.metadata


@router.post(
    "/api/search/related",
    response_model=RelatedSearchResponseV1,
    responses=_RELATED_ERROR_RESPONSES,
)
def api_search_related(request: RelatedSearchRequestV1) -> RelatedSearchResponseV1:
    """Validate one related-assets reference and read only persisted relation data."""
    context = resolve_search_v2_scope(request.scope)
    try:
        reference = _reference_asset(request.reference_asset_id, context)
        status = _related_status(int(reference["id"]))
        required = _required_component(request, status)
        if required.state in {"not_ready", "building", "disabled"}:
            raise APIError(
                409,
                ErrorType.RELATION_INDEX_NOT_READY,
                "Required relation index is not ready",
                extra={"status": status.model_dump(mode="json")},
            )
        if not required.usable:
            raise APIError(
                503,
                ErrorType.SERVER_ERROR,
                "Required persisted relation index is unusable",
                extra={"status": status.model_dump(mode="json")},
            )
        return RelatedSearchResponseV1(
            reference_asset_id=request.reference_asset_id,
            profile=request.profile,
            scope=request.scope,
            items=[],
            returned=0,
            limit=request.limit,
            status=status,
        )
    except APIError:
        raise
    except sqlite3.OperationalError as exc:
        raise APIError(503, ErrorType.SERVER_ERROR, "Relation index temporarily unavailable") from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Related assets request failed; error_type=%s", type(exc).__name__)
        raise APIError(500, ErrorType.SERVER_ERROR, "Internal server error") from exc
