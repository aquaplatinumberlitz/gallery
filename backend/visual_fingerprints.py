"""Pillow-only visual fingerprints and bounded near-duplicate lookup."""

from __future__ import annotations

import math
import sqlite3
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .config import GALLERY_RELATED_VISUAL_ENABLED
from .metadata_store._db import _DB_LOCK, _connect
from .metadata_store.path_utils import canonicalize_catalog_path, named_path_scope_sql
from .models import RelatedSearchResultV1
from .search_scope import SearchScopeContext
from .thumbnails import DERIVATIVE_CACHE_VERSION

VISUAL_FINGERPRINT_ALGORITHM_VERSION = 1
VISUAL_HASH_HORIZONTAL = 0
VISUAL_HASH_VERTICAL = 1
VISUAL_CANDIDATE_LIMIT = 500
VISUAL_NEAR_DUPLICATE_MAX_DISTANCE = 16
VISUAL_COLOR_GRID_MAX_DISTANCE = 40.0


def _derivative_version() -> int:
    value = DERIVATIVE_CACHE_VERSION.removeprefix("v")
    return int(value) if value.isdigit() else 1


VISUAL_DERIVATIVE_VERSION = _derivative_version()
VISUAL_FINGERPRINT_EXTRACTOR_VERSION = VISUAL_FINGERPRINT_ALGORITHM_VERSION * 1000 + VISUAL_DERIVATIVE_VERSION


def _composite_rgb(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    if "A" not in transposed.getbands():
        return transposed.convert("RGB")
    rgba = transposed.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def _dhash_horizontal(image: Image.Image) -> bytes:
    pixels = list(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).getdata())
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return value.to_bytes(8, "big")


def _dhash_vertical(image: Image.Image) -> bytes:
    pixels = list(image.convert("L").resize((8, 9), Image.Resampling.LANCZOS).getdata())
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 8 + x] > pixels[(y + 1) * 8 + x])
    return value.to_bytes(8, "big")


def compute_visual_fingerprint(path: str | Path) -> dict[str, bytes]:
    """Decode one derivative and return fixed-size dHash/color-grid bytes."""
    with Image.open(path) as opened:
        opened.load()
        image = _composite_rgb(opened)
    color_grid = image.resize((4, 4), Image.Resampling.BOX).tobytes()
    return {
        "dhash_horizontal": _dhash_horizontal(image),
        "dhash_vertical": _dhash_vertical(image),
        "color_grid": color_grid,
    }


def _current_derivative(asset: dict[str, Any]) -> dict[str, Any] | None:
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            """
            SELECT kind, variant, cache_path
            FROM asset_derivatives
            WHERE asset_id = ? AND source_mtime_ns = ? AND source_size = ?
              AND status = 'ready' AND cache_path IS NOT NULL
            ORDER BY CASE
              WHEN kind = 'thumbnail' AND variant = 'thumb_512' THEN 0
              WHEN kind = 'preview' AND variant = 'preview_1440' THEN 1
              WHEN kind = 'thumbnail' AND variant = 'thumb_128' THEN 2
              ELSE 3 END,
              id DESC
            """,
            (int(asset["id"]), int(asset.get("mtime_ns") or 0), int(asset.get("size") or 0)),
        ).fetchall()
    for row in rows:
        cache_path = Path(str(row["cache_path"]))
        if cache_path.is_file():
            return {"role": f"{row['kind']}:{row['variant']}", "path": cache_path}
    return None


def _queue_default_derivative(asset_id: int) -> None:
    from .derivative_scheduler import scheduler

    scheduler.schedule_derivative(
        asset_id,
        "thumbnail",
        "thumb_512",
        priority=3,
        max_long_edge=512,
        quality=78,
        format="webp",
    )


def extract_visual_fingerprint(asset: dict[str, Any]):  # noqa: ANN201
    """Hash a current derivative outside SQLite writes or queue one if absent."""
    from .search_indexer import SearchExtractionResult

    if str(asset.get("type")) != "image":
        return SearchExtractionResult(status="not_applicable", payload=None)
    derivative = _current_derivative(asset)
    if derivative is None:
        try:
            _queue_default_derivative(int(asset["id"]))
        except (KeyError, OSError, ValueError):
            return SearchExtractionResult(status="failed", error_code="derivative_schedule_failed")
        return SearchExtractionResult(status="skipped", payload=None, error_code="derivative_pending")
    try:
        fingerprint = compute_visual_fingerprint(derivative["path"])
    except (OSError, ValueError):
        return SearchExtractionResult(status="failed", error_code="derivative_decode_failed")
    return SearchExtractionResult(
        status="ready",
        payload={
            **fingerprint,
            "source_mtime_ns": int(asset.get("mtime_ns") or 0),
            "source_size": int(asset.get("size") or 0),
            "derivative_role": derivative["role"],
            "derivative_version": VISUAL_DERIVATIVE_VERSION,
            "algorithm_version": VISUAL_FINGERPRINT_ALGORITHM_VERSION,
        },
    )


def _bands(value: bytes) -> list[int]:
    integer = int.from_bytes(value, "big")
    return [(integer >> shift) & 0xFFFF for shift in (48, 32, 16, 0)]


def persist_visual_fingerprint(conn: sqlite3.Connection, asset: dict[str, Any], payload: dict[str, Any] | None) -> None:
    """Atomically replace one fingerprint and all eight indexed hash bands."""
    asset_id = int(asset["id"])
    conn.execute("DELETE FROM asset_visual_fingerprints WHERE asset_id = ?", (asset_id,))
    conn.execute("DELETE FROM asset_visual_hash_bands WHERE asset_id = ?", (asset_id,))
    if payload is None:
        return
    conn.execute(
        """
        INSERT INTO asset_visual_fingerprints (
          asset_id, library_id, source_mtime_ns, source_size, derivative_role,
          derivative_version, algorithm_version, dhash_horizontal,
          dhash_vertical, color_grid, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            int(asset["library_id"]),
            int(payload["source_mtime_ns"]),
            int(payload["source_size"]),
            str(payload["derivative_role"]),
            int(payload["derivative_version"]),
            int(payload["algorithm_version"]),
            payload["dhash_horizontal"],
            payload["dhash_vertical"],
            payload["color_grid"],
            time.time(),
        ),
    )
    rows = []
    for hash_kind, field in (
        (VISUAL_HASH_HORIZONTAL, "dhash_horizontal"),
        (VISUAL_HASH_VERTICAL, "dhash_vertical"),
    ):
        rows.extend(
            (asset_id, int(asset["library_id"]), hash_kind, band_no, band_value)
            for band_no, band_value in enumerate(_bands(payload[field]))
        )
    conn.executemany(
        """
        INSERT INTO asset_visual_hash_bands (
          asset_id, library_id, hash_kind, band_no, band_value
        ) VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def schedule_visual_fingerprint_backfill(library_id: int) -> None:
    """Coalesce one durable missing-fingerprint rebuild for a library."""
    if not GALLERY_RELATED_VISUAL_ENABLED:
        return
    from .metadata_store.search_index_store import SearchIndexJobConflict, create_search_index_job
    from .search_indexer import search_index_worker

    with suppress(SearchIndexJobConflict):
        create_search_index_job(
            "visual_fingerprints",
            library_id,
            mode="missing",
            schema_version=1,
            extractor_version=VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
        )
    search_index_worker.wake()


def notify_derivative_ready(asset_id: int) -> None:
    """Invalidate a pending visual extraction and queue durable retry work."""
    if not GALLERY_RELATED_VISUAL_ENABLED:
        return
    with _DB_LOCK, _connect() as conn:
        asset = conn.execute(
            "SELECT library_id FROM assets WHERE id = ? AND type = 'image' AND offline = 0 AND deleted_at IS NULL",
            (asset_id,),
        ).fetchone()
        if asset is None:
            return
        current = conn.execute(
            """
            SELECT 1 FROM asset_visual_fingerprints AS fingerprint
            JOIN assets AS current_asset ON current_asset.id = fingerprint.asset_id
            WHERE fingerprint.asset_id = ?
              AND fingerprint.source_mtime_ns = current_asset.mtime_ns
              AND fingerprint.source_size = current_asset.size
              AND fingerprint.derivative_version = ?
              AND fingerprint.algorithm_version = ?
            """,
            (asset_id, VISUAL_DERIVATIVE_VERSION, VISUAL_FINGERPRINT_ALGORITHM_VERSION),
        ).fetchone()
        if current is not None:
            return
        conn.execute("DELETE FROM asset_visual_fingerprints WHERE asset_id = ?", (asset_id,))
        conn.execute("DELETE FROM asset_visual_hash_bands WHERE asset_id = ?", (asset_id,))
        conn.execute(
            "DELETE FROM asset_search_extractions WHERE asset_id = ? AND index_name = 'visual_fingerprints'",
            (asset_id,),
        )
        library_id = int(asset["library_id"])
    schedule_visual_fingerprint_backfill(library_id)


def _scope_sql(context: SearchScopeContext) -> tuple[str, dict[str, Any]]:
    if context.kind == "all":
        return "", {}
    if context.kind == "library":
        return " AND asset.library_id = :scope_library_id", {"scope_library_id": context.library_id}
    assert context.library_id is not None and context.folder_path is not None
    predicate, params = named_path_scope_sql(
        context.folder_path,
        column="asset.path",
        parameter_prefix="visual_scope",
        leading_and=True,
    )
    params["scope_library_id"] = context.library_id
    return f" AND asset.library_id = :scope_library_id{predicate}", params


def _current_reference(conn: sqlite3.Connection, asset_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fingerprint.*, asset.width, asset.height
        FROM asset_visual_fingerprints AS fingerprint
        JOIN assets AS asset ON asset.id = fingerprint.asset_id
        WHERE fingerprint.asset_id = ? AND asset.type = 'image'
          AND asset.offline = 0 AND asset.deleted_at IS NULL
          AND fingerprint.source_mtime_ns = asset.mtime_ns
          AND fingerprint.source_size = asset.size
          AND fingerprint.derivative_version = ?
          AND fingerprint.algorithm_version = ?
        """,
        (asset_id, VISUAL_DERIVATIVE_VERSION, VISUAL_FINGERPRINT_ALGORITHM_VERSION),
    ).fetchone()
    return dict(row) if row is not None else None


def _probe_values(value: bytes) -> list[tuple[int, int, int]]:
    probes: list[tuple[int, int, int]] = []
    for band_no, band_value in enumerate(_bands(value)):
        probes.append((band_no, band_value, 0))
        probes.extend((band_no, band_value ^ (1 << bit), 1) for bit in range(16))
    return probes


def _visual_candidate_rows(
    conn: sqlite3.Connection,
    reference: dict[str, Any],
    context: SearchScopeContext,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "reference_asset_id": int(reference["asset_id"]),
        "derivative_version": VISUAL_DERIVATIVE_VERSION,
        "algorithm_version": VISUAL_FINGERPRINT_ALGORITHM_VERSION,
    }
    value_rows: list[str] = []
    probe_index = 0
    for hash_kind, field in (
        (VISUAL_HASH_HORIZONTAL, "dhash_horizontal"),
        (VISUAL_HASH_VERTICAL, "dhash_vertical"),
    ):
        for band_no, band_value, probe_distance in _probe_values(reference[field]):
            prefix = f"probe_{probe_index}"
            params.update(
                {
                    f"{prefix}_kind": hash_kind,
                    f"{prefix}_band": band_no,
                    f"{prefix}_value": band_value,
                    f"{prefix}_distance": probe_distance,
                }
            )
            value_rows.append(f"(:{prefix}_kind, :{prefix}_band, :{prefix}_value, :{prefix}_distance)")
            probe_index += 1
    scope_predicate, scope_params = _scope_sql(context)
    band_library_predicate = "" if context.kind == "all" else " AND band.library_id = :scope_library_id"
    params.update(scope_params)
    rows = conn.execute(
        f"""
        WITH probes(hash_kind, band_no, band_value, probe_distance) AS (
          VALUES {",".join(value_rows)}
        ), candidates AS (
          SELECT band.asset_id, min(probes.probe_distance) AS probe_distance,
                 count(*) AS band_hits
          FROM probes
          JOIN asset_visual_hash_bands AS band
            ON band.hash_kind = probes.hash_kind
           AND band.band_no = probes.band_no
           AND band.band_value = probes.band_value
          JOIN assets AS asset ON asset.id = band.asset_id
          JOIN asset_visual_fingerprints AS fingerprint ON fingerprint.asset_id = asset.id
          WHERE band.asset_id != :reference_asset_id
            AND asset.type = 'image' AND asset.offline = 0 AND asset.deleted_at IS NULL
            AND fingerprint.source_mtime_ns = asset.mtime_ns
            AND fingerprint.source_size = asset.size
            AND fingerprint.derivative_version = :derivative_version
            AND fingerprint.algorithm_version = :algorithm_version
            {band_library_predicate}
            {scope_predicate}
          GROUP BY band.asset_id
          ORDER BY probe_distance, band_hits DESC, band.asset_id
          LIMIT {VISUAL_CANDIDATE_LIMIT}
        )
        SELECT asset.id AS asset_id, asset.library_id, library.name AS library_name,
               asset.path, asset.parent_path, asset.name, asset.mtime_ns,
               asset.width, asset.height, fingerprint.dhash_horizontal,
               fingerprint.dhash_vertical, fingerprint.color_grid
        FROM candidates
        JOIN assets AS asset ON asset.id = candidates.asset_id
        JOIN libraries AS library ON library.id = asset.library_id
        JOIN asset_visual_fingerprints AS fingerprint ON fingerprint.asset_id = asset.id
        ORDER BY candidates.probe_distance, candidates.band_hits DESC, asset.id
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _color_distance(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)


def _aspect_distance(reference: dict[str, Any], candidate: dict[str, Any]) -> float:
    values = reference.get("width"), reference.get("height"), candidate.get("width"), candidate.get("height")
    if not all(isinstance(value, int) and value > 0 for value in values):
        return 0.0
    reference_ratio = int(values[0]) / int(values[1])
    candidate_ratio = int(values[2]) / int(values[3])
    return abs(math.log(reference_ratio / candidate_ratio))


def _relative_parent(parent_path: str, context: SearchScopeContext) -> str:
    root = Path(context.folder_path) if context.kind == "folder" and context.folder_path else Path("/")
    try:
        relative = Path(canonicalize_catalog_path(parent_path)).relative_to(canonicalize_catalog_path(root))
    except ValueError:
        return ""
    return "" if str(relative) == "." else str(relative)


def query_visual_variants(
    reference_asset_id: int,
    context: SearchScopeContext,
    *,
    limit: int,
) -> list[RelatedSearchResultV1]:
    """Rank persisted visual near-duplicates without decoding in the request."""
    with _DB_LOCK, _connect() as conn:
        reference = _current_reference(conn, reference_asset_id)
        if reference is None:
            return []
        candidates = _visual_candidate_rows(conn, reference, context)
    scored: list[tuple[int, int, float, float, dict[str, Any]]] = []
    reference_horizontal = int.from_bytes(reference["dhash_horizontal"], "big")
    reference_vertical = int.from_bytes(reference["dhash_vertical"], "big")
    for candidate in candidates:
        horizontal = (reference_horizontal ^ int.from_bytes(candidate["dhash_horizontal"], "big")).bit_count()
        vertical = (reference_vertical ^ int.from_bytes(candidate["dhash_vertical"], "big")).bit_count()
        distance = horizontal + vertical
        if distance > VISUAL_NEAR_DUPLICATE_MAX_DISTANCE:
            continue
        color_distance = _color_distance(reference["color_grid"], candidate["color_grid"])
        aspect_distance = _aspect_distance(reference, candidate)
        if distance > 4 and (color_distance > VISUAL_COLOR_GRID_MAX_DISTANCE or aspect_distance > 0.08):
            continue
        tier = 80 if distance <= 4 and color_distance <= 8 and aspect_distance <= 0.03 else 60
        scored.append((tier, distance, color_distance, aspect_distance, candidate))
    scored.sort(
        key=lambda item: (-item[0], item[1], item[2], item[3], -int(item[4]["mtime_ns"] or 0), int(item[4]["asset_id"]))
    )
    return [
        RelatedSearchResultV1(
            asset_id=int(candidate["asset_id"]),
            library_id=int(candidate["library_id"]),
            library_name=str(candidate["library_name"]),
            name=str(candidate["name"]),
            path=str(candidate["path"]),
            type="image",
            parent_path=str(candidate["parent_path"]),
            relative_path=_relative_parent(str(candidate["parent_path"]), context),
            mtime=float(candidate["mtime_ns"] or 0) / 1_000_000_000,
            width=candidate.get("width"),
            height=candidate.get("height"),
            match_type="visual_variant",
            relation_tier=tier,
            relation_reasons=["visual_variant"],
            visual_distance=float(distance),
        )
        for tier, distance, _color, _aspect, candidate in scored[:limit]
    ]
