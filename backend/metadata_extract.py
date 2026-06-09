from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from .files import IMAGE_EXTENSIONS, is_image_path

LORA_PATTERN = re.compile(r"<lora:([^:>]+)(?::([^>]+))?>", re.IGNORECASE)
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
GENERIC_TEXT_KEYS = ("Description", "Comment", "UserComment", "Software", "parameters", "prompt", "workflow")


@dataclass
class ExtractedMetadata:
    path: str
    name: str
    mtime: float
    size: int
    width: int | None
    height: int | None
    format: str
    mode: str
    has_alpha: int
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


def extract_loras(text: str) -> list[str]:
    """Extract LoRA tags from text string."""
    loras = []
    for match in LORA_PATTERN.finditer(text):
        name, weight = match.group(1), match.group(2)
        loras.append(f"{name}:{weight}" if weight else name)
    alt_matches = re.findall(r'LoRA:\s*\[([^\]]+)\]', text)
    for match in alt_matches:
        loras.extend([item.strip() for item in match.split(',') if item.strip()])
    return list(dict.fromkeys(loras))


def contains_cjk(query: str) -> bool:
    return bool(CJK_RE.search(query))


def safe_text(value: Any) -> str:
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


def parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float(value: str) -> float | None:
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

    metadata["steps"] = parse_int(_first_match(params_text, r"Steps:\s*(\d+)"))
    metadata["sampler"] = _first_match(params_text, r"Sampler:\s*([^,\n]+)")
    metadata["cfg_scale"] = parse_float(_first_match(params_text, r"CFG [Ss]cale:\s*([\d.]+)"))
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


def _read_image_info(path: Path) -> tuple[int | None, int | None, str, str, int, dict[str, str]]:
    with Image.open(path) as img:
        image_format = img.format or ""
        mode = img.mode or ""
        has_alpha = 1 if (img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info)) else 0
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        info = {str(key): safe_text(value) for key, value in img.info.items() if safe_text(value)}
        try:
            exif = img.getexif()
        except Exception:
            exif = None
        if exif:
            user_comment = safe_text(exif.get(37510))
            if user_comment:
                info.setdefault("UserComment", user_comment)
    return width, height, image_format, mode, has_alpha, info


def extract_metadata(path: Path) -> ExtractedMetadata:
    stat = path.stat()
    width: int | None = None
    height: int | None = None
    image_format = ""
    mode = ""
    has_alpha = 0
    info: dict[str, str] = {}
    try:
        width, height, image_format, mode, has_alpha, info = _read_image_info(path)
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
        format=image_format,
        mode=mode,
        has_alpha=has_alpha,
        prompt=safe_text(normalized.get("prompt")),
        negative_prompt=safe_text(normalized.get("negative_prompt")),
        model=safe_text(normalized.get("model")),
        sampler=safe_text(normalized.get("sampler")),
        seed=safe_text(normalized.get("seed")),
        steps=normalized.get("steps") if isinstance(normalized.get("steps"), int) else None,
        cfg_scale=normalized.get("cfg_scale") if isinstance(normalized.get("cfg_scale"), (int, float)) else None,
        raw_metadata_text=raw_metadata_text,
        metadata_json=metadata_json,
        indexed_at=time.time(),
    )
