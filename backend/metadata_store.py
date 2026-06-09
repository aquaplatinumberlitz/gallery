from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .albums import build_album_metadata
from .config import GALLERY_METADATA_DB, GALLERY_ROOT
from .files import IMAGE_EXTENSIONS, is_image_path
from .metadata_extract import (
    CJK_RE,
    GENERIC_TEXT_KEYS,
    contains_cjk,
    extract_metadata,
    parse_a1111_parameters,
    parse_float,
    parse_int,
    safe_text,
)


SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
_DB_LOCK = threading.RLock()


@dataclass(frozen=True)
class CachedDimensions:
    width: int
    height: int


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _connect() -> sqlite3.Connection:
    GALLERY_METADATA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GALLERY_METADATA_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_database() -> None:
    with _DB_LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS image_metadata (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              mtime REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              format TEXT,
              mode TEXT,
              has_alpha INTEGER,
              prompt TEXT,
              negative_prompt TEXT,
              model TEXT,
              sampler TEXT,
              seed TEXT,
              steps INTEGER,
              cfg_scale REAL,
              raw_metadata_text TEXT,
              metadata_json TEXT,
              updated_at REAL,
              indexed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_name
              ON image_metadata(mtime DESC, name);

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS image_metadata_fts_trigram USING fts5(
              name, prompt, negative_prompt, model, sampler, raw_metadata_text,
              content='image_metadata',
              content_rowid='id',
              tokenize='trigram'
            );

            CREATE TRIGGER IF NOT EXISTS image_metadata_ai AFTER INSERT ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_ad AFTER DELETE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
            END;

            CREATE TRIGGER IF NOT EXISTS image_metadata_au AFTER UPDATE ON image_metadata BEGIN
              INSERT INTO image_metadata_fts(image_metadata_fts, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(image_metadata_fts_trigram, rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES ('delete', old.id, old.name, old.prompt, old.negative_prompt, old.model, old.sampler, old.raw_metadata_text);
              INSERT INTO image_metadata_fts_trigram(rowid, name, prompt, negative_prompt, model, sampler, raw_metadata_text)
              VALUES (new.id, new.name, new.prompt, new.negative_prompt, new.model, new.sampler, new.raw_metadata_text);
            END;

            CREATE TABLE IF NOT EXISTS file_index (
              path TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              parent_path TEXT NOT NULL,
              type TEXT NOT NULL,
              mtime REAL,
              size INTEGER,
              width INTEGER,
              height INTEGER,
              indexed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_file_index_parent_path ON file_index(parent_path);
            CREATE INDEX IF NOT EXISTS idx_file_index_type ON file_index(type);
            CREATE INDEX IF NOT EXISTS idx_file_index_name ON file_index(name);

            CREATE VIRTUAL TABLE IF NOT EXISTS file_index_fts USING fts5(
              name,
              path UNINDEXED,
              type UNINDEXED,
              parent_path UNINDEXED,
              tokenize='unicode61'
            );
            """
        )
        _ensure_column(conn, "image_metadata", "format", "TEXT")
        _ensure_column(conn, "image_metadata", "mode", "TEXT")
        _ensure_column(conn, "image_metadata", "has_alpha", "INTEGER")
        _ensure_column(conn, "image_metadata", "updated_at", "REAL")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_image_metadata_mtime_size
              ON image_metadata(path, mtime, size)
            """
        )


def _needs_reindex(conn: sqlite3.Connection, path: Path, mtime: float, size: int) -> bool:
    row = conn.execute("SELECT mtime, size FROM image_metadata WHERE path = ?", (str(path.resolve()),)).fetchone()
    if row is None:
        return True
    return row["mtime"] != mtime or row["size"] != size


def index_image(path: Path) -> bool:
    if not is_image_path(path):
        return False
    try:
        stat = path.stat()
    except OSError:
        return False

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        if not _needs_reindex(conn, path, stat.st_mtime, stat.st_size):
            return False
        try:
            metadata = extract_metadata(path)
        except Exception:
            return False
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, prompt, negative_prompt,
              format, mode, has_alpha, model, sampler, seed, steps, cfg_scale,
              raw_metadata_text, metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
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
              indexed_at=excluded.indexed_at
            """,
            (
                metadata.path,
                metadata.name,
                metadata.mtime,
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
            ),
        )
        return True


def index_images(paths: Iterable[str | Path]) -> int:
    indexed = 0
    for path_value in paths:
        try:
            if index_image(Path(path_value)):
                indexed += 1
        except Exception:
            continue
    return indexed


def get_cached_dimensions_for_files(files: Iterable[tuple[str | Path, float, int]]) -> dict[str, CachedDimensions]:
    """Return cached dimensions for files whose mtime and size still match."""
    file_rows = [(str(Path(path).resolve()), mtime, size) for path, mtime, size in files]
    if not file_rows:
        return {}

    initialize_database()
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
    initialize_database()
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

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, prompt, negative_prompt,
              model, sampler, seed, steps, cfg_scale, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
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
    return True


def _path_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_file_type(type_value: str) -> str:
    return "photo" if type_value in {"image", "photo", "file"} else "folder"


def index_file(
    path: str | Path,
    name: str,
    parent_path: str | Path,
    type: str,
    mtime: float | None,
    size: int | None,
    width: int | None,
    height: int | None,
) -> bool:
    resolved_path = str(Path(path).resolve())
    resolved_parent = str(Path(parent_path).resolve())
    normalized_type = _normalize_file_type(type)
    initialize_database()
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO file_index (
              path, name, parent_path, type, mtime, size, width, height, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              parent_path=excluded.parent_path,
              type=excluded.type,
              mtime=excluded.mtime,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              indexed_at=excluded.indexed_at
            """,
            (
                resolved_path,
                name,
                resolved_parent,
                normalized_type,
                mtime,
                size,
                width,
                height,
                time.time(),
            ),
        )
        conn.execute("DELETE FROM file_index_fts WHERE path = ?", (resolved_path,))
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            (name, resolved_path, normalized_type, resolved_parent),
        )
    return True


def _cleanup_stale_index_conn(conn: sqlite3.Connection, root_path: str | Path | None = None) -> int:
    root = Path(root_path).resolve() if root_path is not None else None
    candidate_paths: set[str] = set()
    for table in ("file_index", "file_index_fts", "image_metadata"):
        candidate_paths.update(row["path"] for row in conn.execute(f"SELECT path FROM {table}"))

    stale_paths: list[str] = []

    for path_value in candidate_paths:
        path = Path(path_value)
        if root is not None and not _is_inside_root(path, root):
            stale_paths.append(path_value)
            continue
        if not path.exists():
            stale_paths.append(path_value)

    if not stale_paths:
        return 0

    conn.executemany("DELETE FROM file_index_fts WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM file_index WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM image_metadata WHERE path = ?", ((path,) for path in stale_paths))
    return len(stale_paths)


def cleanup_stale_index(state: Any, root_path: str | Path | None = None) -> int:
    """Remove stale database rows for missing or out-of-root paths.

    This only deletes index records. It never deletes filesystem entries.
    """
    initialize_database()
    if isinstance(state, sqlite3.Connection):
        return _cleanup_stale_index_conn(state, root_path)

    with _DB_LOCK, _connect() as conn:
        return _cleanup_stale_index_conn(conn, root_path)


def index_files_from_scan(folders: list[Any], images: list[Any]) -> int:
    indexed = 0
    for item in [*folders, *images]:
        raw_path = _path_value(item, "path")
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            stat = path.stat()
        except OSError:
            stat = None
        try:
            if index_file(
                path=path,
                name=_path_value(item, "name", path.name),
                parent_path=path.parent,
                type=_path_value(item, "type", "photo"),
                mtime=_path_value(item, "mtime", stat.st_mtime if stat else None),
                size=stat.st_size if stat and path.is_file() else None,
                width=_path_value(item, "width", None),
                height=_path_value(item, "height", None),
            ):
                indexed += 1
        except Exception:
            continue
    return indexed


def index_directory_tree(root: str | Path, include_metadata: bool = False) -> int:
    root_path = Path(root)
    indexed = 0
    image_paths: list[Path] = []

    def visit(folder: Path) -> None:
        nonlocal indexed
        try:
            stat = folder.stat()
            if index_file(folder, folder.name or str(folder), folder.parent, "folder", stat.st_mtime, None, None, None):
                indexed += 1
        except OSError:
            return
        except Exception:
            pass

        try:
            entries = list(folder.iterdir())
        except (OSError, PermissionError):
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    visit(entry)
                elif entry.is_file() and is_image_path(entry):
                    stat = entry.stat()
                    if index_file(entry, entry.name, entry.parent, "photo", stat.st_mtime, stat.st_size, None, None):
                        indexed += 1
                    image_paths.append(entry)
            except (OSError, PermissionError):
                continue

    visit(root_path)
    if include_metadata:
        indexed += index_images(image_paths)
    return indexed


def _escape_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _unicode_match_query(query: str) -> str:
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _trigram_match_query(query: str) -> str:
    return _escape_fts_token(query.strip())


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _relative_path(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root))
    except (OSError, ValueError):
        return str(Path(path).name)


def _folder_relative_path(parent_path: str, root: Path) -> str:
    try:
        relative = Path(parent_path).resolve().relative_to(root)
    except (OSError, ValueError):
        return ""
    if str(relative) == ".":
        return ""
    return str(relative)


def _is_inside_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        return resolved == resolved_root or resolved_root in resolved.parents
    except (OSError, RuntimeError):
        return False


def _path_prefix(root: Path) -> tuple[str, str]:
    root_str = str(root.resolve())
    root_prefix = f"{root_str.rstrip(os.sep)}{os.sep}"
    return root_str, f"{_like_escape(root_prefix)}%"


def _scope_clause(scope: str, root_path: str | Path | None, alias: str = "fi") -> tuple[str, list[Any], Path]:
    root = Path(root_path).resolve() if scope == "current" and root_path else GALLERY_ROOT
    root_str, root_prefix = _path_prefix(root)
    return f" AND ({alias}.path = ? OR {alias}.path LIKE ? ESCAPE '\\')", [root_str, root_prefix], root


def _format_file_index_rows(rows: list[sqlite3.Row], root: Path, match_type: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        result = {
            "name": row["name"],
            "path": row["path"],
            "type": row["type"],
            "parent_path": row["parent_path"],
            "relative_path": _folder_relative_path(row["parent_path"], root),
            "mtime": row["mtime"],
            "width": row["width"],
            "height": row["height"],
        }
        if row["type"] == "folder":
            resolved_path = Path(row["path"]).resolve()
            if resolved_path.exists() and resolved_path.is_dir():
                meta = build_album_metadata(resolved_path)
                result["cover_images"] = meta["cover_images"]
                result["image_count"] = meta["image_count"]
            else:
                result["cover_images"] = []
                result["image_count"] = 0
        result.update(
            {
                "match_type": match_type,
                "prompt_snippet": "",
                "model": "",
                "sampler": "",
                "seed": "",
            }
        )
        results.append(result)
    return results


def _search_file_index_fts(
    conn: sqlite3.Connection,
    query: str,
    file_type: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    scope_sql, scope_params, root = _scope_clause(scope, root_path, "fi")
    try:
        match_query = _unicode_match_query(query)
        rows = list(
            conn.execute(
                f"""
                SELECT fi.*
                FROM file_index_fts fts
                JOIN file_index fi ON fi.path = fts.path
                WHERE fts MATCH ? AND fi.type = ? {scope_sql}
                ORDER BY bm25(file_index_fts) ASC, fi.mtime DESC, fi.name ASC
                LIMIT ?
                """,
                [match_query, file_type, *scope_params, limit],
            )
        )
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(query)
    rows = list(
        conn.execute(
            f"""
            SELECT fi.*
            FROM file_index fi
            WHERE fi.name LIKE ? ESCAPE '\\' AND fi.type = ? {scope_sql}
            ORDER BY fi.mtime DESC, fi.name ASC
            LIMIT ?
            """,
            [pattern, file_type, *scope_params, limit],
        )
    )
    return rows, root


def _search_prompt_rows(
    conn: sqlite3.Connection,
    query: str,
    scope: str,
    root_path: str | Path | None,
    limit: int,
) -> tuple[list[sqlite3.Row], Path]:
    scope_sql, scope_params, root = _scope_clause(scope, root_path, "fi")
    rows: list[sqlite3.Row] = []
    try:
        if contains_cjk(query) and len(query) >= 3:
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts_trigram) AS rank
                    FROM image_metadata_fts_trigram fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts_trigram MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_trigram_match_query(query), *scope_params, limit],
                )
            )
        elif not contains_cjk(query):
            rows = list(
                conn.execute(
                    f"""
                    SELECT m.*, fi.parent_path, fi.type AS file_type, bm25(image_metadata_fts) AS rank
                    FROM image_metadata_fts fts
                    JOIN image_metadata m ON m.id = fts.rowid
                    JOIN file_index fi ON fi.path = m.path
                    WHERE image_metadata_fts MATCH ? {scope_sql}
                    ORDER BY rank ASC, m.mtime DESC, m.name ASC
                    LIMIT ?
                    """,
                    [_unicode_match_query(query), *scope_params, limit],
                )
            )
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return rows, root

    pattern = _like_pattern(query)
    where = " OR ".join(f"m.{field} LIKE ? ESCAPE '\\'" for field in PROMPT_SEARCH_FIELDS)
    rows = list(
        conn.execute(
            f"""
            SELECT m.*, fi.parent_path, fi.type AS file_type
            FROM image_metadata m
            JOIN file_index fi ON fi.path = m.path
            WHERE ({where}) {scope_sql}
            ORDER BY m.mtime DESC, m.name ASC
            LIMIT ?
            """,
            [*([pattern] * len(PROMPT_SEARCH_FIELDS)), *scope_params, limit],
        )
    )
    return rows, root


def _format_prompt_rows(rows: list[sqlite3.Row], root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        results.append(
            {
                "name": row["name"],
                "path": row["path"],
                "type": "photo",
                "parent_path": row["parent_path"],
                "relative_path": _folder_relative_path(row["parent_path"], root),
                "mtime": row["mtime"],
                "width": row["width"],
                "height": row["height"],
                "match_type": "prompt",
                "prompt_snippet": _snippet(row),
                "model": row["model"] or "",
                "sampler": row["sampler"] or "",
                "seed": row["seed"] or "",
            }
        )
    return results


def _snippet(row: sqlite3.Row) -> str:
    for field in ("prompt", "negative_prompt", "raw_metadata_text", "model", "sampler", "name"):
        text = row[field] or ""
        if text:
            text = " ".join(text.split())
            return text[:240]
    return ""


def _format_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [
        {
            "name": row["name"],
            "path": row["path"],
            "type": "file",
            "mtime": row["mtime"],
            "width": row["width"],
            "height": row["height"],
            "model": row["model"] or "",
            "sampler": row["sampler"] or "",
            "seed": row["seed"] or "",
            "prompt_snippet": _snippet(row),
        }
        for row in rows
    ]


def _search_fts(conn: sqlite3.Connection, table: str, bm25_table: str, match_query: str, limit: int, offset: int) -> list[sqlite3.Row]:
    sql = f"""
        SELECT m.*, bm25({bm25_table}) AS rank
        FROM {table}
        JOIN image_metadata m ON m.id = {table}.rowid
        WHERE {table} MATCH ?
        ORDER BY rank ASC, m.mtime DESC, m.name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (match_query, limit, offset)))


def _count_fts(conn: sqlite3.Connection, table: str, match_query: str) -> int:
    row = conn.execute(f"SELECT count(*) AS total FROM {table} WHERE {table} MATCH ?", (match_query,)).fetchone()
    return int(row["total"] if row else 0)


def _search_like(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[sqlite3.Row]:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    sql = f"""
        SELECT *
        FROM image_metadata
        WHERE {where}
        ORDER BY mtime DESC, name ASC
        LIMIT ? OFFSET ?
    """
    return list(conn.execute(sql, (*([pattern] * len(SEARCH_FIELDS)), limit, offset)))


def _count_like(conn: sqlite3.Connection, query: str) -> int:
    pattern = _like_pattern(query)
    where = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    row = conn.execute(f"SELECT count(*) AS total FROM image_metadata WHERE {where}", [pattern] * len(SEARCH_FIELDS)).fetchone()
    return int(row["total"] if row else 0)


def search_metadata(query: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    initialize_database()
    trimmed = query.strip()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if not trimmed:
        return {"query": query, "total": 0, "results": []}

    with _DB_LOCK, _connect() as conn:
        rows: list[sqlite3.Row] = []
        total = 0
        try:
            if contains_cjk(trimmed):
                if len(trimmed) >= 3:
                    match_query = _trigram_match_query(trimmed)
                    rows = _search_fts(conn, "image_metadata_fts_trigram", "image_metadata_fts_trigram", match_query, limit, offset)
                    total = _count_fts(conn, "image_metadata_fts_trigram", match_query)
                if not rows:
                    rows = _search_like(conn, trimmed, limit, offset)
                    total = _count_like(conn, trimmed)
            else:
                match_query = _unicode_match_query(trimmed)
                rows = _search_fts(conn, "image_metadata_fts", "image_metadata_fts", match_query, limit, offset)
                total = _count_fts(conn, "image_metadata_fts", match_query)
        except sqlite3.OperationalError:
            rows = _search_like(conn, trimmed, limit, offset)
            total = _count_like(conn, trimmed)

        if not rows and not contains_cjk(trimmed):
            rows = _search_like(conn, trimmed, limit, offset)
            total = _count_like(conn, trimmed)

        return {
            "query": query,
            "total": total,
            "results": _format_rows(rows),
        }


def search_index(query: str, scope: str, root_path: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    initialize_database()
    trimmed = query.strip()
    normalized_scope = "all" if scope == "all" else "current"
    limit = max(1, min(limit, 200))
    root = Path(root_path).resolve() if normalized_scope == "current" and root_path else GALLERY_ROOT

    if not trimmed:
        return {
            "query": query,
            "scope": normalized_scope,
            "root": str(root),
            "albums": [],
            "photos": [],
            "prompt": [],
        }

    with _DB_LOCK, _connect() as conn:
        album_rows, root = _search_file_index_fts(conn, trimmed, "folder", normalized_scope, root_path, limit)
        photo_rows, root = _search_file_index_fts(conn, trimmed, "photo", normalized_scope, root_path, limit)
        prompt_rows, root = _search_prompt_rows(conn, trimmed, normalized_scope, root_path, limit)

    return {
        "query": query,
        "scope": normalized_scope,
        "root": str(root),
        "albums": _format_file_index_rows(album_rows, root, "filename"),
        "photos": _format_file_index_rows(photo_rows, root, "filename"),
        "prompt": _format_prompt_rows(prompt_rows, root),
    }
