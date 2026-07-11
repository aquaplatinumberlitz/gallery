"""Metadata extraction persistence helpers."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..files import is_image_path, is_index_excluded_path
from ..metadata_extract import ExtractedMetadata, parse_float, parse_int, safe_text
from ._asset_store import _upsert_asset_conn
from ._db import _DB_LOCK, _connect
from ._resources import _replace_image_resources_conn
from .metadata_queue import _mark_current_metadata_done, _metadata_job_from_path
from .types import CachedDimensions


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _extract_metadata(path: Path) -> ExtractedMetadata:
    from . import extract_metadata

    return extract_metadata(path)


def _sanitize_metadata_for_json(metadata: dict[str, Any]) -> Any:
    from . import sanitize_metadata_for_json

    return sanitize_metadata_for_json(metadata)


def _needs_reindex(conn: sqlite3.Connection, path: Path, mtime: float, size: int) -> bool:
    row = conn.execute(
        "SELECT mtime, size, metadata_json FROM image_metadata WHERE path = ?", (str(path.resolve()),)
    ).fetchone()
    if row is None:
        return True
    return row["mtime"] != mtime or row["size"] != size or not row["metadata_json"]


def _upsert_extracted_metadata_conn(conn: sqlite3.Connection, metadata: ExtractedMetadata) -> None:
    conn.execute(
        """
        INSERT INTO image_metadata (
          path, name, mtime, mtime_ns, size, width, height, prompt, negative_prompt,
          format, mode, has_alpha, model, sampler, seed, steps, cfg_scale,
          raw_metadata_text, metadata_json, updated_at, indexed_at,
          tool, scheduler, model_hash, lora_text, generation_time,
          clip_skip, hires_upscale, hires_steps, denoising_strength,
          vae, ensd, aesthetic_score, date, aspect_ratio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          name=excluded.name,
          mtime=excluded.mtime,
          mtime_ns=excluded.mtime_ns,
          size=excluded.size,
          width=excluded.width,
          height=excluded.height,
          format=excluded.format,
          mode=excluded.mode,
          has_alpha=excluded.has_alpha,
          prompt=excluded.prompt,
          negative_prompt=excluded.negative_prompt,
          model=excluded.model,
          sampler=excluded.sampler,
          seed=excluded.seed,
          steps=excluded.steps,
          cfg_scale=excluded.cfg_scale,
          raw_metadata_text=excluded.raw_metadata_text,
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at,
          indexed_at=excluded.indexed_at,
          tool=excluded.tool,
          scheduler=excluded.scheduler,
          model_hash=excluded.model_hash,
          lora_text=excluded.lora_text,
          generation_time=excluded.generation_time,
          clip_skip=excluded.clip_skip,
          hires_upscale=excluded.hires_upscale,
          hires_steps=excluded.hires_steps,
          denoising_strength=excluded.denoising_strength,
          vae=excluded.vae,
          ensd=excluded.ensd,
          aesthetic_score=excluded.aesthetic_score,
          date=excluded.date,
          aspect_ratio=excluded.aspect_ratio
        """,
        (
            metadata.path,
            metadata.name,
            metadata.mtime,
            metadata.mtime_ns,
            metadata.size,
            metadata.width,
            metadata.height,
            metadata.prompt,
            metadata.negative_prompt,
            metadata.format,
            metadata.mode,
            metadata.has_alpha,
            metadata.model,
            metadata.sampler,
            metadata.seed,
            metadata.steps,
            metadata.cfg_scale,
            metadata.raw_metadata_text,
            metadata.metadata_json,
            metadata.indexed_at,
            metadata.indexed_at,
            metadata.tool,
            metadata.scheduler,
            metadata.model_hash,
            metadata.lora_text,
            metadata.generation_time,
            metadata.clip_skip,
            metadata.hires_upscale,
            metadata.hires_steps,
            metadata.denoising_strength,
            metadata.vae,
            metadata.ensd,
            metadata.aesthetic_score,
            metadata.date,
            metadata.aspect_ratio,
        ),
    )
    _upsert_asset_conn(
        conn,
        path=metadata.path,
        name=metadata.name,
        parent_path=Path(metadata.path).parent,
        type="image",
        mtime_ns=metadata.mtime_ns,
        size=metadata.size,
        width=metadata.width,
        height=metadata.height,
        reactivate_existing=False,
        preserve_existing_identity=True,
    )
    _sync_dimensions_to_file_index(
        conn,
        metadata.path,
        metadata.width,
        metadata.height,
        expected_mtime_ns=metadata.mtime_ns,
        expected_size=metadata.size,
    )
    _replace_image_resources_conn(conn, metadata.path, metadata.metadata_json, metadata.lora_text, metadata.indexed_at)


def _sync_dimensions_to_file_index(
    conn: sqlite3.Connection,
    path: str | Path,
    width: int | None,
    height: int | None,
    *,
    expected_mtime_ns: int,
    expected_size: int,
) -> None:
    """Fill missing file-index dimensions inside the caller's transaction."""
    if width is None and height is None:
        return
    conn.execute(
        """
        UPDATE file_index
        SET width = COALESCE(?, width),
            height = COALESCE(?, height)
        WHERE path = ? AND mtime_ns = ? AND size = ?
        """,
        (width, height, str(Path(path).resolve()), expected_mtime_ns, expected_size),
    )
    conn.execute(
        """
        UPDATE assets
        SET width = COALESCE(?, width),
            height = COALESCE(?, height)
        WHERE path = ? AND mtime_ns = ? AND size = ?
        """,
        (width, height, str(Path(path).resolve()), expected_mtime_ns, expected_size),
    )


def upsert_extracted_metadata(metadata: ExtractedMetadata, *, mark_job_done: bool = False) -> bool:
    """Persist extracted metadata and optionally complete the metadata job.

    When mark_job_done is True, creates a MetadataIndexJob from current file stat
    and completes it via _mark_current_metadata_done (which delegates to
    complete_metadata_job) so job state and asset state are materialized together.
    """
    if is_index_excluded_path(metadata.path):
        return False
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        _upsert_extracted_metadata_conn(conn, metadata)
        if mark_job_done:
            job = _metadata_job_from_path(metadata.path)
            if job is not None and job.mtime == metadata.mtime and job.size == metadata.size:
                _mark_current_metadata_done(conn, job, metadata.indexed_at)
    return True


def upsert_metadata_batch(metadata_items: Iterable[ExtractedMetadata]) -> int:
    """Write extracted metadata rows in one bounded SQLite transaction."""
    rows = list(metadata_items)
    if not rows:
        return 0
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        for metadata in rows:
            _upsert_extracted_metadata_conn(conn, metadata)
    return len(rows)


def index_image(path: Path) -> bool:
    """Extract and persist metadata for one image when its indexed file version is stale."""
    if is_index_excluded_path(path) or not is_image_path(path):
        return False
    try:
        stat = path.stat()
    except OSError:
        return False

    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        if not _needs_reindex(conn, path, stat.st_mtime, stat.st_size):
            return False
        try:
            metadata = _extract_metadata(path)
        except Exception:  # noqa: BLE001
            return False
        _upsert_extracted_metadata_conn(conn, metadata)
        return True


def index_images(paths: Iterable[str | Path]) -> int:
    """Index metadata for multiple image paths and return the number updated."""
    indexed = 0
    for path_value in paths:
        try:
            if index_image(Path(path_value)):
                indexed += 1
        except Exception:  # noqa: BLE001
            continue
    return indexed


def get_lightbox_metadata(path: str | Path) -> dict | None:
    """Read metadata from SQLite. Returns None if not cached or stale."""
    resolved = str(Path(path).resolve())
    try:
        stat = Path(path).stat()
    except OSError:
        return None

    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM image_metadata
            WHERE path = ? AND mtime = ? AND size = ? AND metadata_json IS NOT NULL
            """,
            (resolved, stat.st_mtime, stat.st_size),
        ).fetchone()
        if row is None:
            return None

        metadata_json = row["metadata_json"]
        if not metadata_json:
            return None

        try:
            parsed = json.loads(metadata_json)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(parsed, dict):
            return None

        parsed.setdefault("tool", "Unknown")
        parsed.setdefault("prompt", row["prompt"] or "")
        parsed.setdefault("negative_prompt", row["negative_prompt"] or "")
        parsed.setdefault("params", {})
        parsed["width"] = row["width"]
        parsed["height"] = row["height"]
        parsed["name"] = row["name"]
        return parsed


def get_cached_dimensions_for_files(files: Iterable[tuple[str | Path, float, int]]) -> dict[str, CachedDimensions]:
    """Return cached dimensions for files whose mtime and size still match."""
    file_rows = [(str(Path(path).resolve()), mtime, size) for path, mtime, size in files]
    if not file_rows:
        return {}

    _initialize_database()
    cached: dict[str, CachedDimensions] = {}
    expected = {path: (mtime, size) for path, mtime, size in file_rows}
    paths = list(expected)

    with _DB_LOCK, _connect() as conn:
        for start in range(0, len(paths), 900):
            chunk = paths[start : start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT path, mtime, size, width, height
                FROM image_metadata
                WHERE path IN ({placeholders})
                  AND width IS NOT NULL
                  AND height IS NOT NULL
                """,
                chunk,
            )
            for row in rows:
                expected_mtime, expected_size = expected[row["path"]]
                if row["mtime"] == expected_mtime and row["size"] == expected_size:
                    cached[row["path"]] = CachedDimensions(width=row["width"], height=row["height"])

    return cached


def upsert_image_dimensions(
    path: str | Path,
    width: int | None,
    height: int | None,
    *,
    image_format: str = "",
    mode: str = "",
    has_alpha: int | bool | None = None,
) -> bool:
    """Insert or update dimensions for an image opened by thumbnail/metadata paths."""
    if width is None or height is None:
        return False

    image_path = Path(path)
    if not is_image_path(image_path):
        return False

    try:
        stat = image_path.stat()
    except OSError:
        return False

    resolved_path = str(image_path.resolve())
    alpha_value = None if has_alpha is None else int(bool(has_alpha))
    now = time.time()
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, format, mode, has_alpha,
              prompt, negative_prompt, model, sampler, seed, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', '', '', '', ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              format=excluded.format,
              mode=excluded.mode,
              has_alpha=excluded.has_alpha,
              updated_at=excluded.updated_at
            """,
            (
                resolved_path,
                image_path.name,
                stat.st_mtime,
                stat.st_size,
                width,
                height,
                image_format,
                mode,
                alpha_value,
                now,
                now,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=image_path.name,
            parent_path=image_path.parent,
            type="image",
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            width=width,
            height=height,
            metadata_state="done",
            reactivate_existing=False,
        )
        _sync_dimensions_to_file_index(
            conn,
            resolved_path,
            width,
            height,
            expected_mtime_ns=stat.st_mtime_ns,
            expected_size=stat.st_size,
        )
    return True


def _metadata_param(metadata: dict[str, Any], *names: str) -> Any:
    params = metadata.get("params")
    if not isinstance(params, dict):
        return None
    for name in names:
        if name in params:
            return params[name]
    return None


def upsert_metadata_result(path: str | Path, metadata: dict[str, Any]) -> bool:
    """Insert or update full metadata for an image opened by parse_metadata()."""
    image_path = Path(path)
    if not is_image_path(image_path):
        return False

    try:
        stat = image_path.stat()
    except OSError:
        return False

    sanitized_metadata = _sanitize_metadata_for_json(metadata)
    if not isinstance(sanitized_metadata, dict):
        sanitized_metadata = {}
    metadata = sanitized_metadata

    width = metadata.get("width")
    height = metadata.get("height")
    prompt = safe_text(metadata.get("prompt"))
    negative_prompt = safe_text(metadata.get("negative_prompt"))
    model = safe_text(_metadata_param(metadata, "Model", "model"))
    sampler = safe_text(_metadata_param(metadata, "Sampler", "sampler"))
    seed = safe_text(_metadata_param(metadata, "Seed", "seed"))
    steps = parse_int(safe_text(_metadata_param(metadata, "Steps", "steps")))
    cfg_scale = parse_float(safe_text(_metadata_param(metadata, "CFG", "CFG scale", "cfg_scale", "cfg")))
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    raw_metadata_text = "\n".join(
        text for text in (prompt, negative_prompt, model, sampler, seed, metadata_json) if text
    )
    now = time.time()
    resolved_path = str(image_path.resolve())

    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, mtime_ns, size, width, height, prompt, negative_prompt,
              model, sampler, seed, steps, cfg_scale, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
              mtime_ns=excluded.mtime_ns,
              size=excluded.size,
              width=COALESCE(excluded.width, image_metadata.width),
              height=COALESCE(excluded.height, image_metadata.height),
              prompt=excluded.prompt,
              negative_prompt=excluded.negative_prompt,
              model=excluded.model,
              sampler=excluded.sampler,
              seed=excluded.seed,
              steps=excluded.steps,
              cfg_scale=excluded.cfg_scale,
              raw_metadata_text=excluded.raw_metadata_text,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at,
              indexed_at=excluded.indexed_at
            """,
            (
                resolved_path,
                image_path.name,
                stat.st_mtime,
                stat.st_mtime_ns,
                stat.st_size,
                width if isinstance(width, int) else None,
                height if isinstance(height, int) else None,
                prompt,
                negative_prompt,
                model,
                sampler,
                seed,
                steps,
                cfg_scale,
                raw_metadata_text,
                metadata_json,
                now,
                now,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=image_path.name,
            parent_path=image_path.parent,
            type="image",
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            width=width if isinstance(width, int) else None,
            height=height if isinstance(height, int) else None,
            metadata_state="done",
            reactivate_existing=False,
        )
        _sync_dimensions_to_file_index(
            conn,
            resolved_path,
            width if isinstance(width, int) else None,
            height if isinstance(height, int) else None,
            expected_mtime_ns=stat.st_mtime_ns,
            expected_size=stat.st_size,
        )
    return True
