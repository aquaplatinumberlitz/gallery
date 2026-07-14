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
    RelatedSearchResultV1,
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


def _aggregate_component_status(
    index_name: str,
    *,
    rows: dict[int, sqlite3.Row],
    library_ids: list[int],
    reference_library_id: int,
    reference_ready: bool,
    extractor_version: int,
    target_counts: dict[int, int],
) -> RelatedIndexComponentStatusV1:
    indexed_count = sum(int(row["indexed_count"] or 0) for row in rows.values())
    target_count = sum(target_counts.get(library_id, 0) for library_id in library_ids)
    reference_state = rows.get(reference_library_id)
    if reference_state is None:
        return _component_status(
            index_name,
            ready=False,
            indexed_count=indexed_count,
            target_count=target_count,
        )

    def row_usable(row: sqlite3.Row) -> bool:
        state = str(row["state"])
        current = int(row["schema_version"]) == 1 and int(row["extractor_version"]) == extractor_version
        return current and (
            state == "ready"
            or (
                state in {"building", "degraded"}
                and (int(row["indexed_count"] or 0) > 0 or int(row["target_count"] or 0) == 0)
            )
        )

    reference_state_name = str(reference_state["state"])
    reference_usable = row_usable(reference_state) and reference_ready
    if not reference_usable:
        return RelatedIndexComponentStatusV1(
            index_name=index_name,
            state="not_ready" if reference_state_name == "pending" or not reference_ready else reference_state_name,
            usable=False,
            indexed_count=indexed_count,
            target_count=target_count,
        )

    all_usable = all(library_id in rows and row_usable(rows[library_id]) for library_id in library_ids)
    if not all_usable:
        state = "degraded"
    else:
        states = {str(rows[library_id]["state"]) for library_id in library_ids}
        state = "building" if "building" in states else "degraded" if "degraded" in states else "ready"
    return RelatedIndexComponentStatusV1(
        index_name=index_name,
        state=state,
        usable=True,
        indexed_count=indexed_count,
        target_count=target_count,
    )


def _related_status(reference_asset_id: int, context: SearchScopeContext) -> RelatedSearchStatusV1:
    """Report only persisted readiness; never decode or derive media here."""
    with _DB_LOCK, _connect() as conn:
        asset = conn.execute("SELECT library_id FROM assets WHERE id = ?", (reference_asset_id,)).fetchone()
        reference_library_id = int(asset["library_id"]) if asset is not None else 0
        if context.kind == "all":
            library_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM libraries ORDER BY id")]
        else:
            library_ids = [reference_library_id] if reference_library_id else []
        target_counts = {
            int(row["library_id"]): int(row["target_count"])
            for row in conn.execute(
                """
                SELECT library_id, count(*) AS target_count
                FROM assets
                WHERE offline = 0 AND deleted_at IS NULL AND type IN ('image', 'video')
                GROUP BY library_id
                """
            )
        }
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
        metadata_states = {
            int(row["library_id"]): row
            for row in conn.execute(
                """
                SELECT library_id, state, schema_version, extractor_version, indexed_count, target_count
                FROM search_index_states
                WHERE index_name = 'generation_signatures'
                """,
            )
            if int(row["library_id"]) in library_ids
        }
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
        visual_states = {
            int(row["library_id"]): row
            for row in conn.execute(
                """
                SELECT library_id, state, schema_version, extractor_version, indexed_count, target_count
                FROM search_index_states
                WHERE index_name = 'visual_fingerprints'
                """,
            )
            if int(row["library_id"]) in library_ids
        }
    metadata = _aggregate_component_status(
        "generation_signatures",
        rows=metadata_states,
        library_ids=library_ids,
        reference_library_id=reference_library_id,
        reference_ready=metadata_reference_ready,
        extractor_version=GENERATION_SIGNATURE_EXTRACTOR_VERSION,
        target_counts=target_counts,
    )
    if not GALLERY_RELATED_VISUAL_ENABLED:
        visual = RelatedIndexComponentStatusV1(
            index_name="visual_fingerprints",
            state="disabled",
            usable=False,
        )
    else:
        visual = _aggregate_component_status(
            "visual_fingerprints",
            rows=visual_states,
            library_ids=library_ids,
            reference_library_id=reference_library_id,
            reference_ready=visual_ready,
            extractor_version=VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
            target_counts=target_counts,
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


def _merge_related_items(
    metadata_items: list[RelatedSearchResultV1],
    visual_items: list[RelatedSearchResultV1],
    *,
    limit: int,
) -> list[RelatedSearchResultV1]:
    merged = {item.asset_id: item for item in metadata_items}
    for visual in visual_items:
        existing = merged.get(visual.asset_id)
        if existing is None:
            merged[visual.asset_id] = visual
            continue
        reasons = list(existing.relation_reasons)
        reasons.extend(reason for reason in visual.relation_reasons if reason not in reasons)
        merged[visual.asset_id] = existing.model_copy(
            update={
                "relation_tier": max(existing.relation_tier, visual.relation_tier),
                "relation_reasons": reasons,
                "visual_distance": visual.visual_distance,
            }
        )
    return sorted(
        merged.values(),
        key=lambda item: (
            -item.relation_tier,
            -(item.metadata_score or 0),
            item.visual_distance if item.visual_distance is not None else float("inf"),
            -item.mtime,
            item.asset_id,
        ),
    )[:limit]


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
        status = _related_status(int(reference["id"]), context)
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
        if required.state in {"not_ready", "disabled"} or (required.state == "building" and not required.usable):
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
        if request.profile == "visual":
            items = query_visual_variants(int(reference["id"]), context, limit=request.limit)
        else:
            metadata_items = rank_related_metadata(
                int(reference["id"]),
                context,
                profile=request.profile,
                limit=request.limit,
            )
            visual_items = (
                query_visual_variants(int(reference["id"]), context, limit=request.limit)
                if request.profile == "related" and status.visual.usable
                else []
            )
            items = _merge_related_items(metadata_items, visual_items, limit=request.limit)
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
