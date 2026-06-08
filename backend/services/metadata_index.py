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

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from services.album_utils import build_album_metadata
except ModuleNotFoundError:
    from backend.services.album_utils import build_album_metadata


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
DB_PATH = Path(__file__).resolve().parents[1] / ".cache" / "gallery_metadata.db"
GALLERY_ROOT = Path(os.getenv("GALLERY_ROOT", "/")).resolve()
SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
PROMPT_SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
GENERIC_TEXT_KEYS = ("Description", "Comment", "UserComment", "Software", "parameters", "prompt", "workflow")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_DB_LOCK = threading.RLock()


@dataclass
class ExtractedMetadata:
    path: str
    name: str
    mtime: float
    size: int
    width: int | None
    height: int | None
    prompt: str
    negative_prompt: str
    model: str
    sampler: str
    seed: str
    steps: int | None
    cfg_scale: float | None
    raw_metadata_text: str
    metadata_json: str
    indexed_at: float


def contains_cjk(query: str) -> bool:
    return bool(CJK_RE.search(query))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
              prompt TEXT,
              negative_prompt TEXT,
              model TEXT,
              sampler TEXT,
              seed TEXT,
              steps INTEGER,
              cfg_scale REAL,
              raw_metadata_text TEXT,
              metadata_json TEXT,
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


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        if value.startswith(b"ASCII\x00\x00\x00"):
            value = value[8:]
        return value.decode("utf-8", errors="ignore").strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_a1111_parameters(params_text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "prompt": "",
        "negative_prompt": "",
        "steps": None,
        "sampler": "",
        "cfg_scale": None,
        "seed": "",
        "model": "",
    }
    if not params_text:
        return metadata

    settings_markers = ("Steps:", "Sampler:", "CFG scale:", "Seed:", "Size:", "Model:")
    params_start = min((idx for marker in settings_markers if (idx := params_text.find(marker)) > 0), default=None)
    neg_match = re.search(r"Negative prompt:", params_text, re.IGNORECASE)

    if neg_match:
        metadata["prompt"] = params_text[: neg_match.start()].strip()
        neg_end = params_start if params_start is not None and params_start > neg_match.start() else len(params_text)
        metadata["negative_prompt"] = params_text[neg_match.end() : neg_end].strip().rstrip(",")
    elif params_start is not None:
        metadata["prompt"] = params_text[:params_start].strip()
    else:
        metadata["prompt"] = params_text.strip()

    metadata["steps"] = _parse_int(_first_match(params_text, r"Steps:\s*(\d+)"))
    metadata["sampler"] = _first_match(params_text, r"Sampler:\s*([^,\n]+)")
    metadata["cfg_scale"] = _parse_float(_first_match(params_text, r"CFG [Ss]cale:\s*([\d.]+)"))
    metadata["seed"] = _first_match(params_text, r"Seed:\s*([^,\n]+)")
    metadata["model"] = _first_match(params_text, r"Model:\s*([^,\n]+)")
    return metadata


def _json_text_summary(value: Any) -> str:
    pieces: list[str] = []

    def visit(obj: Any) -> None:
        if isinstance(obj, str):
            if obj.strip():
                pieces.append(obj.strip())
        elif isinstance(obj, dict):
            for key, child in obj.items():
                if key in {"text", "prompt", "negative_prompt", "ckpt_name", "model", "model_name", "sampler_name", "seed"}:
                    visit(child)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(obj, list):
            for child in obj:
                visit(child)

    visit(value)
    return " ".join(dict.fromkeys(pieces))


def _parse_comfy_text(prompt_json: str, workflow_json: str) -> dict[str, Any]:
    raw_json = prompt_json or workflow_json
    summary = ""
    parsed: Any = None
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            summary = _json_text_summary(parsed)
        except (json.JSONDecodeError, TypeError):
            summary = raw_json

    return {
        "prompt": summary,
        "negative_prompt": "",
        "steps": None,
        "sampler": "",
        "cfg_scale": None,
        "seed": "",
        "model": "",
        "metadata_json": raw_json if raw_json and raw_json.strip().startswith(("{", "[")) else "",
    }


def _read_image_info(path: Path) -> tuple[int | None, int | None, dict[str, str]]:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        info = {str(key): _safe_text(value) for key, value in img.info.items() if _safe_text(value)}
        try:
            exif = img.getexif()
        except Exception:
            exif = None
        if exif:
            user_comment = _safe_text(exif.get(37510))
            if user_comment:
                info.setdefault("UserComment", user_comment)
    return width, height, info


def extract_metadata(path: Path) -> ExtractedMetadata:
    stat = path.stat()
    width: int | None = None
    height: int | None = None
    info: dict[str, str] = {}
    try:
        width, height, info = _read_image_info(path)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        info = {}

    raw_parts = [f"{key}: {value}" for key, value in info.items() if key in GENERIC_TEXT_KEYS or key.lower() in GENERIC_TEXT_KEYS]
    raw_metadata_text = "\n".join(raw_parts)
    normalized: dict[str, Any] = {}
    metadata_json = ""

    parameters = info.get("parameters", "")
    prompt_json = info.get("prompt", "")
    workflow_json = info.get("workflow", "")

    if prompt_json or workflow_json:
        normalized = _parse_comfy_text(prompt_json, workflow_json)
        metadata_json = normalized.get("metadata_json", "")
    elif parameters:
        if parameters.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(parameters)
                metadata_json = parameters
                normalized["prompt"] = _json_text_summary(parsed)
            except (json.JSONDecodeError, TypeError):
                normalized = parse_a1111_parameters(parameters)
        else:
            normalized = parse_a1111_parameters(parameters)
    elif raw_metadata_text:
        normalized["prompt"] = raw_metadata_text

    metadata_json = metadata_json or (prompt_json if prompt_json.strip().startswith(("{", "[")) else "")

    return ExtractedMetadata(
        path=str(path.resolve()),
        name=path.name,
        mtime=stat.st_mtime,
        size=stat.st_size,
        width=width,
        height=height,
        prompt=_safe_text(normalized.get("prompt")),
        negative_prompt=_safe_text(normalized.get("negative_prompt")),
        model=_safe_text(normalized.get("model")),
        sampler=_safe_text(normalized.get("sampler")),
        seed=_safe_text(normalized.get("seed")),
        steps=normalized.get("steps") if isinstance(normalized.get("steps"), int) else None,
        cfg_scale=normalized.get("cfg_scale") if isinstance(normalized.get("cfg_scale"), (int, float)) else None,
        raw_metadata_text=raw_metadata_text,
        metadata_json=metadata_json,
        indexed_at=time.time(),
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
              model, sampler, seed, steps, cfg_scale, raw_metadata_text, metadata_json, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              mtime=excluded.mtime,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              prompt=excluded.prompt,
              negative_prompt=excluded.negative_prompt,
              model=excluded.model,
              sampler=excluded.sampler,
              seed=excluded.seed,
              steps=excluded.steps,
              cfg_scale=excluded.cfg_scale,
              raw_metadata_text=excluded.raw_metadata_text,
              metadata_json=excluded.metadata_json,
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
                metadata.model,
                metadata.sampler,
                metadata.seed,
                metadata.steps,
                metadata.cfg_scale,
                metadata.raw_metadata_text,
                metadata.metadata_json,
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


def index_directory_tree(root: str | Path) -> int:
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
