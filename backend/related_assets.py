"""Reference validation and the versioned Related Assets API contract."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter

from .config import GALLERY_RELATED_VISUAL_ENABLED
from .errors import APIError, ErrorType
from .generation_signatures import GENERATION_SIGNATURE_EXTRACTOR_VERSION, PROMPT_NORMALIZER_VERSION
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
from .related_ranking import rank_related_metadata
from .search_scope import SearchScopeContext, resolve_search_v2_scope
from .visual_fingerprints import (
    VISUAL_DERIVATIVE_VERSION,
    VISUAL_FINGERPRINT_ALGORITHM_VERSION,
    VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    query_visual_variants,
)

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
        asset = conn.execute("SELECT library_id FROM assets WHERE id = ?", (reference_asset_id,)).fetchone()
        metadata_reference_ready = _table_exists(conn, "asset_generation_signatures") and bool(
            conn.execute(
                """
                SELECT 1
                FROM asset_generation_signatures AS signature
                JOIN assets AS current_asset ON current_asset.id = signature.asset_id
                WHERE signature.asset_id = ?
                  AND signature.source_mtime_ns = current_asset.mtime_ns
                  AND signature.source_size = current_asset.size
                  AND signature.normalizer_version = ?
                  AND signature.extractor_version = ?
                """,
                (reference_asset_id, PROMPT_NORMALIZER_VERSION, GENERATION_SIGNATURE_EXTRACTOR_VERSION),
            ).fetchone()
        )
        metadata_state = (
            conn.execute(
                """
                SELECT state, schema_version, extractor_version, indexed_count, target_count
                FROM search_index_states
                WHERE index_name = 'generation_signatures' AND library_id = ?
                """,
                (int(asset["library_id"]),),
            ).fetchone()
            if asset is not None
            else None
        )
        visual_ready = _table_exists(conn, "asset_visual_fingerprints") and bool(
            conn.execute(
                """
                SELECT 1
                FROM asset_visual_fingerprints AS fingerprint
                JOIN assets AS current_asset ON current_asset.id = fingerprint.asset_id
                WHERE fingerprint.asset_id = ?
                  AND fingerprint.source_mtime_ns = current_asset.mtime_ns
                  AND fingerprint.source_size = current_asset.size
                  AND fingerprint.derivative_version = ?
                  AND fingerprint.algorithm_version = ?
                """,
                (reference_asset_id, VISUAL_DERIVATIVE_VERSION, VISUAL_FINGERPRINT_ALGORITHM_VERSION),
            ).fetchone()
        )
        visual_state = (
            conn.execute(
                """
                SELECT state, schema_version, extractor_version, indexed_count, target_count
                FROM search_index_states
                WHERE index_name = 'visual_fingerprints' AND library_id = ?
                """,
                (int(asset["library_id"]),),
            ).fetchone()
            if asset is not None
            else None
        )
    if metadata_state is None:
        metadata = _component_status("generation_signatures", ready=False)
    else:
        state = str(metadata_state["state"])
        indexed_count = int(metadata_state["indexed_count"] or 0)
        target_count = int(metadata_state["target_count"] or 0)
        usable = state == "ready" or (state in {"building", "degraded"} and (indexed_count > 0 or target_count == 0))
        usable = (
            usable
            and int(metadata_state["schema_version"]) == 1
            and int(metadata_state["extractor_version"]) == GENERATION_SIGNATURE_EXTRACTOR_VERSION
        )
        if state == "pending":
            state = "not_ready"
        if usable and not metadata_reference_ready:
            state = "not_ready"
            usable = False
        metadata = RelatedIndexComponentStatusV1(
            index_name="generation_signatures",
            state=state,
            usable=usable,
            indexed_count=indexed_count,
            target_count=target_count,
        )
    if not GALLERY_RELATED_VISUAL_ENABLED:
        visual = RelatedIndexComponentStatusV1(
            index_name="visual_fingerprints",
            state="disabled",
            usable=False,
        )
    elif visual_state is None:
        visual = _component_status("visual_fingerprints", ready=False)
    else:
        state = str(visual_state["state"])
        indexed_count = int(visual_state["indexed_count"] or 0)
        target_count = int(visual_state["target_count"] or 0)
        usable = state == "ready" or (state in {"building", "degraded"} and (indexed_count > 0 or target_count == 0))
        usable = (
            usable
            and int(visual_state["schema_version"]) == 1
            and int(visual_state["extractor_version"]) == VISUAL_FINGERPRINT_EXTRACTOR_VERSION
        )
        if state == "pending":
            state = "not_ready"
        if usable and not visual_ready:
            state = "not_ready"
            usable = False
        visual = RelatedIndexComponentStatusV1(
            index_name="visual_fingerprints",
            state=state,
            usable=usable,
            indexed_count=indexed_count,
            target_count=target_count,
        )
    return RelatedSearchStatusV1(
        metadata=metadata,
        visual=visual,
    )


def _visual_index_globally_usable(library_id: int) -> bool:
    if not GALLERY_RELATED_VISUAL_ENABLED:
        return False
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT state, schema_version, extractor_version, indexed_count, target_count FROM search_index_states
            WHERE index_name = 'visual_fingerprints' AND library_id = ?
            """,
            (library_id,),
        ).fetchone()
    if row is None:
        return False
    versions_current = (
        int(row["schema_version"]) == 1 and int(row["extractor_version"]) == VISUAL_FINGERPRINT_EXTRACTOR_VERSION
    )
    return versions_current and (
        str(row["state"]) == "ready"
        or (
            str(row["state"]) in {"building", "degraded"}
            and (int(row["indexed_count"] or 0) > 0 or int(row["target_count"] or 0) == 0)
        )
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
        if request.profile == "visual" and required.state == "disabled":
            raise APIError(
                409,
                ErrorType.FEATURE_DISABLED,
                "Visual related-assets indexing is disabled",
                extra={"status": status.model_dump(mode="json")},
            )
        if (
            request.profile == "visual"
            and required.state == "not_ready"
            and _visual_index_globally_usable(int(reference["library_id"]))
        ):
            raise APIError(
                409,
                ErrorType.REFERENCE_NOT_INDEXED,
                "Reference asset does not have a current visual fingerprint",
                extra={"status": status.model_dump(mode="json")},
            )
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
        items = (
            query_visual_variants(int(reference["id"]), context, limit=request.limit)
            if request.profile == "visual"
            else rank_related_metadata(
                int(reference["id"]),
                context,
                profile=request.profile,
                limit=request.limit,
            )
        )
        return RelatedSearchResponseV1(
            reference_asset_id=request.reference_asset_id,
            profile=request.profile,
            scope=request.scope,
            items=items,
            returned=len(items),
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
