from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
DB_PATH = Path(__file__).resolve().parents[1] / ".cache" / "gallery_metadata.db"
SEARCH_FIELDS = ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
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
