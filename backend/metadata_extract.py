from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError



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
    tool: str = ""
    scheduler: str = ""
    model_hash: str = ""
    lora_text: str = ""
    generation_time: float | None = None
    clip_skip: int | None = None
    hires_upscale: float | None = None
    hires_steps: int | None = None
    denoising_strength: float | None = None
    vae: str = ""
    ensd: int | None = None
    aesthetic_score: float | None = None
    date: str = ""
    aspect_ratio: str = ""


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


def parse_ai_text_parameters(params_text: str) -> dict[str, Any]:
    """Parse A1111/WebUI-style parameter strings for the metadata panel."""
    metadata: dict[str, Any] = {}
    if not params_text or not isinstance(params_text, str):
        return metadata

    neg_match = re.search(r"Negative prompt:", params_text, re.IGNORECASE)
    neg_idx = neg_match.start() if neg_match else -1

    params_start = None
    for marker in ["Steps:", "Size:", "Seed:", "Model:"]:
        idx = params_text.find(marker)
        if idx > 0 and (params_start is None or idx < params_start):
            params_start = idx

    if neg_idx >= 0:
        metadata["prompt"] = params_text[:neg_idx].strip()
        neg_end = params_start if params_start and params_start > neg_idx else len(params_text)
        neg_text = params_text[neg_match.end() : neg_end].strip()
        for marker in ["Steps:", "Size:", "Seed:", "Model:", "Sampler:"]:
            marker_idx = neg_text.find(marker)
            if marker_idx > 0:
                neg_text = neg_text[:marker_idx].strip()
                break
        metadata["negative_prompt"] = neg_text
    elif params_start:
        metadata["prompt"] = params_text[:params_start].strip()
    else:
        metadata["prompt"] = params_text.strip()

    patterns = {
        "Steps": r"Steps:\s*(\d+)",
        "Sampler": r"Sampler:\s*([^,\n]+?)(?:,|\n|$)",
        "CFG": r"CFG [Ss]cale:\s*([\d.]+)",
        "Seed": r"Seed:\s*(\d+)",
        "Model": r"Model:\s*([^,\n]+?)(?:,|\n|$)",
        "Scheduler": r"Scheduler:\s*([^,\n]+?)(?:,|\n|$)",
        "model_hash": r"Model hash:\s*(\w+)",
        "clip_skip": r"Clip skip:\s*(\d+)",
        "hires_upscale": r"Hires upscale:\s*([\d.]+)",
        "hires_steps": r"Hires steps:\s*(\d+)",
        "denoising_strength": r"Denoising strength:\s*([\d.]+)",
        "Size": r"Size:\s*(\d+x\d+)",
        "vae": r"VAE:\s*([^,\n]+?)(?:,|\n|$)",
        "ensd": r"ENSD:\s*(\d+)",
        "aesthetic_score": r"Aesthetic score:\s*([\d.]+)",
    }

    params: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, params_text, re.IGNORECASE)
        if match:
            params[key] = match.group(1).strip()

    size_val = params.pop("Size", None)
    if size_val:
        size_match = re.match(r"(\d+)x(\d+)", size_val)
        if size_match:
            params["Width"] = size_match.group(1)
            params["Height"] = size_match.group(2)

    loras = extract_loras(f"{metadata.get('prompt', '')} {metadata.get('negative_prompt', '')} {params_text}")
    if loras:
        params["Lora"] = loras

    metadata["params"] = params
    return metadata


def parse_comfy(prompt_json: str, workflow_json: str | None) -> dict[str, Any]:
    try:
        data = json.loads(prompt_json)
    except Exception:
        data = None
    if data is None and workflow_json:
        try:
            data = json.loads(workflow_json)
        except Exception:
            data = None
    if not isinstance(data, dict):
        return {}

    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else data

    nodes_by_id: dict[str, Any] = {}
    if isinstance(nodes, dict):
        nodes_by_id = nodes
    elif isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                nid = node.get("id")
                if nid is not None:
                    nodes_by_id[str(nid)] = node

    def iter_nodes():
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                yield node_id, node
        elif isinstance(nodes, list):
            for node in nodes:
                node_id = node.get("id") if isinstance(node, dict) else None
                yield node_id, node

    def resolve_value(val: Any, max_depth: int = 5) -> Any:
        if max_depth <= 0:
            return None
        if isinstance(val, list) and len(val) == 2:
            ref_node_id = str(val[0])
            ref_node = nodes_by_id.get(ref_node_id)
            if ref_node and isinstance(ref_node, dict):
                ref_inputs = ref_node.get("inputs", {})
                for input_val in ref_inputs.values():
                    if not isinstance(input_val, list):
                        return resolve_value(input_val, max_depth - 1)
                return None
        return val

    def get_scalar(val: Any) -> Any:
        resolved = resolve_value(val)
        if resolved is None or isinstance(resolved, list):
            return None
        return resolved

    prompts: list[str] = []
    params: dict[str, str | list[str]] = {}
    lora_list: list[str] = []

    for _, node in iter_nodes():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type") or node.get("type")
        inputs = node.get("inputs", {})
        if ctype == "CLIPTextEncode":
            text = inputs.get("text")
            if isinstance(text, str):
                prompts.append(text)
        if ctype in {"KSampler", "KSamplerAdvanced"}:
            seed = get_scalar(inputs.get("seed"))
            steps = get_scalar(inputs.get("steps"))
            cfg = get_scalar(inputs.get("cfg") or inputs.get("cfg_scale"))
            sampler = get_scalar(inputs.get("sampler_name") or inputs.get("sampler"))
            if seed is not None:
                params["Seed"] = str(seed)
            if steps is not None:
                params["Steps"] = str(steps)
            if cfg is not None:
                params["CFG"] = str(cfg)
            if sampler is not None:
                params["Sampler"] = str(sampler)
        if ctype == "CheckpointLoaderSimple":
            model = inputs.get("ckpt_name")
            if model and isinstance(model, str):
                params["Model"] = str(model)
        if ctype in {"VAEDecode", "VAELoader"}:
            vae_name = inputs.get("vae_name") or inputs.get("vae")
            if vae_name and isinstance(vae_name, str):
                params["VAE"] = str(vae_name)
        if ctype == "UpscaleModelLoader":
            upscale = inputs.get("model_name")
            if upscale and isinstance(upscale, str):
                params["UpscaleModel"] = str(upscale)
        if ctype == "ControlNetLoader":
            cn = inputs.get("control_net_name")
            if cn and isinstance(cn, str):
                params["ControlNet"] = str(cn)
        if ctype in {"LoraLoader", "LoraLoaderModelOnly"}:
            lora_name = inputs.get("lora_name")
            lora_strength = inputs.get("strength_model")
            if lora_name and isinstance(lora_name, str):
                name = str(lora_name)
                if name.endswith(".safetensors"):
                    name = name[:-12]
                if lora_strength is not None and not isinstance(lora_strength, list):
                    lora_list.append(f"{name}:{lora_strength}")
                else:
                    lora_list.append(name)
        if ctype == "CLIPSetLastLayer":
            clip_skip = get_scalar(inputs.get("stop_at_clip_layer"))
            if clip_skip is not None:
                params["clip_skip"] = str(clip_skip)

    prompts_sorted = sorted(prompts, key=lambda x: len(x), reverse=True)
    prompt = prompts_sorted[0] if prompts_sorted else ""
    negative_prompt = prompts_sorted[1] if len(prompts_sorted) > 1 else ""

    loras_from_text = extract_loras(" ".join(prompts))
    all_loras = list(dict.fromkeys(lora_list + loras_from_text))
    if all_loras:
        params["Lora"] = all_loras

    return {
        "tool": "ComfyUI",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "params": params,
    }


def _parse_swarm_metadata(text: str) -> dict[str, Any] | None:
    if not text or not text.strip().startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if "sui_image_params" not in data:
        return None

    sui_params = data.get("sui_image_params", {})
    sui_extra = data.get("sui_extra_data", {})
    sui_models = data.get("sui_models", [])

    params: dict[str, Any] = {
        "Seed": str(sui_params.get("seed", "")),
        "Steps": str(sui_params.get("steps", "")),
        "CFG": str(sui_params.get("cfgscale", "")),
        "Sampler": sui_params.get("sampler", ""),
        "Scheduler": sui_params.get("scheduler", ""),
        "Model": sui_params.get("model", ""),
        "SwarmVersion": sui_params.get("swarm_version", ""),
        "AspectRatio": sui_params.get("aspectratio", ""),
        "Width": str(sui_params.get("width", "")),
        "Height": str(sui_params.get("height", "")),
    }

    final_loras: list[str] = []
    seen_loras: set[str] = set()
    if isinstance(sui_params.get("loras"), list):
        lora_weights = sui_params.get("loraweights", [])
        for i, lora in enumerate(sui_params["loras"]):
            model = ""
            weight = 1.0
            if isinstance(lora, dict):
                model = lora.get("model", "")
                weight = lora.get("weight", 1.0)
            elif isinstance(lora, str):
                model = lora
                if isinstance(lora_weights, list) and i < len(lora_weights):
                    try:
                        weight = float(lora_weights[i])
                    except (ValueError, TypeError):
                        weight = 1.0
            if model:
                if model.endswith(".safetensors"):
                    model = model[:-12]
                if model not in seen_loras:
                    final_loras.append(f"{model}:{weight}")
                    seen_loras.add(model)

    if isinstance(sui_models, list):
        for model_info in sui_models:
            if not isinstance(model_info, dict):
                continue
            if model_info.get("param") == "used_loras":
                name = model_info.get("name", "")
                if name.endswith(".safetensors"):
                    name = name[:-12]
                if name and name not in seen_loras:
                    final_loras.append(name)
                    seen_loras.add(name)

    if final_loras:
        params["Lora"] = final_loras

    models_out = []
    if isinstance(sui_models, list):
        for model_info in sui_models:
            if isinstance(model_info, dict):
                models_out.append(
                    {
                        "name": model_info.get("name"),
                        "param": model_info.get("param"),
                        "hash": model_info.get("hash"),
                    }
                )

    result: dict[str, Any] = {
        "tool": "SwarmUI",
        "prompt": sui_params.get("prompt", ""),
        "negative_prompt": sui_params.get("negativeprompt", ""),
        "params": {k: v for k, v in params.items() if v},
        "models": models_out,
    }
    date = sui_extra.get("date") if isinstance(sui_extra, dict) else None
    if date:
        result["date"] = date
    gen_time = None
    if isinstance(sui_extra, dict):
        gen_time = sui_extra.get("generation_time") or sui_extra.get("prep_time")
    if gen_time:
        result["generation_time"] = gen_time
    return result


def _parse_novelai_metadata(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "NovelAI" not in str(data.get("Software", "")):
        return None

    params: dict[str, Any] = {}
    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", "")
    for key, field in [
        ("Steps", "steps"),
        ("Sampler", "sampler"),
        ("Seed", "seed"),
        ("CFG", "scale"),
        ("Model", "model"),
    ]:
        val = data.get(field)
        if val is not None:
            params[key] = str(val)
    for key in ["sm", "sm_dyn", "noise_schedule", "width", "height", "cfg_rescale"]:
        val = data.get(key)
        if val is not None:
            params[key] = str(val)
    loras = extract_loras(f"{prompt} {negative_prompt}")
    if loras:
        params["Lora"] = loras
    return {
        "tool": "NovelAI",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "params": params,
    }


def _parse_easydiffusion_metadata(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "sui_image_params" in data:
        return None
    if not all(k in data for k in ["prompt", "negative_prompt", "width", "height"]):
        return None

    params: dict[str, Any] = {}
    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", "")
    for key, field in [
        ("Seed", "seed"),
        ("Steps", "steps"),
        ("Sampler", "sampler"),
        ("CFG", "cfg_scale"),
        ("Model", "model"),
    ]:
        val = data.get(field)
        if val is not None:
            params[key] = str(val)
    loras = extract_loras(f"{prompt} {negative_prompt}")
    if loras:
        params["Lora"] = loras
    return {
        "tool": "EasyDiffusion",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "params": params,
    }


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


def get_oriented_dimensions(path: Path) -> tuple[int, int]:
    """Open image, apply EXIF orientation, return display width/height.

    This is a lightweight helper that only reads pixel dimensions.
    It does not parse full metadata, so it is safe for paths that
    need oriented dimensions without the overhead of full extraction.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.size


def _read_image_info(path: Path) -> tuple[int | None, int | None, str, str, int, dict[str, str]]:
    with Image.open(path) as img:
        image_format = img.format or ""
        mode = img.mode or ""
        has_alpha = 1 if (img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info)) else 0
        info = {str(key): safe_text(value) for key, value in img.info.items() if safe_text(value)}
        try:
            exif = img.getexif()
        except Exception:
            exif = None
        if exif:
            user_comment = safe_text(exif.get(37510))
            if user_comment:
                info.setdefault("UserComment", user_comment)

        img = ImageOps.exif_transpose(img)
        width, height = img.size
    return width, height, image_format, mode, has_alpha, info


def _metadata_param(metadata: dict[str, Any], *names: str) -> Any:
    params = metadata.get("params")
    if not isinstance(params, dict):
        return None
    for name in names:
        if name in params:
            return params[name]
    return None


def _api_metadata_from_sources(path: Path, info: dict[str, str]) -> tuple[dict[str, Any], str]:
    parameters = info.get("parameters", "")
    prompt_json = info.get("prompt", "")
    workflow_json = info.get("workflow", "")
    user_comment = info.get("UserComment", "")
    raw_source_text = ""

    result: dict[str, Any] | None = None

    # 1. SwarmUI can store JSON in PNG parameters or EXIF UserComment.
    for candidate in (parameters, user_comment):
        result = _parse_swarm_metadata(candidate)
        if result:
            raw_source_text = candidate
            break

    # 2. ComfyUI stores prompt/workflow JSON chunks.
    if not result and (prompt_json or workflow_json):
        result = parse_comfy(prompt_json or "", workflow_json)
        raw_source_text = prompt_json or workflow_json

    # 3. PNG parameters may contain NovelAI/EasyDiffusion JSON or A1111 text.
    if not result and parameters:
        if parameters.strip().startswith("{"):
            result = _parse_novelai_metadata(parameters) or _parse_easydiffusion_metadata(parameters)
            if not result:
                parsed = parse_ai_text_parameters(parameters)
                if parsed and parsed.get("params"):
                    result = {
                        "tool": "A1111",
                        "prompt": parsed.get("prompt", ""),
                        "negative_prompt": parsed.get("negative_prompt", ""),
                        "params": parsed.get("params", {}),
                    }
        else:
            parsed = parse_ai_text_parameters(parameters)
            if parsed and parsed.get("params"):
                prompt_text = parsed.get("prompt", "")
                result = {
                    "tool": "NovelAI" if prompt_text.startswith("masterpiece, best quality,") else "A1111",
                    "prompt": prompt_text,
                    "negative_prompt": parsed.get("negative_prompt", ""),
                    "params": parsed.get("params", {}),
                }
        if result:
            raw_source_text = parameters

    # 4. Exact .txt sidecars stay opt-in and deterministic.
    if not result:
        txt_path = path.with_suffix(".txt")
        if txt_path.exists():
            try:
                text = txt_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            parsed = parse_ai_text_parameters(text)
            if parsed and parsed.get("params"):
                result = {
                    "tool": "A1111",
                    "prompt": parsed.get("prompt", ""),
                    "negative_prompt": parsed.get("negative_prompt", ""),
                    "params": parsed.get("params", {}),
                }
                raw_source_text = text

    if not result:
        raw_metadata_text = "\n".join(
            f"{key}: {value}"
            for key, value in info.items()
            if key in GENERIC_TEXT_KEYS or key.lower() in {generic.lower() for generic in GENERIC_TEXT_KEYS}
        )
        if raw_metadata_text:
            result = {
                "tool": "Unknown",
                "prompt": raw_metadata_text,
                "negative_prompt": "",
                "params": {},
            }
            raw_source_text = raw_metadata_text
        else:
            result = {"tool": "Unknown", "prompt": "", "negative_prompt": "", "params": {}}

    return result, raw_source_text


def extracted_metadata_to_api(metadata: ExtractedMetadata) -> dict[str, Any]:
    """Return the public /api/metadata DTO for an extracted row."""
    result: dict[str, Any] = {}
    if metadata.metadata_json:
        try:
            parsed = json.loads(metadata.metadata_json)
            if isinstance(parsed, dict):
                result = parsed
        except (json.JSONDecodeError, TypeError):
            result = {}

    if not result:
        result = {
            "tool": "Unknown",
            "prompt": metadata.prompt,
            "negative_prompt": metadata.negative_prompt,
            "params": {
                key: value
                for key, value in {
                    "Seed": metadata.seed,
                    "Steps": str(metadata.steps) if metadata.steps is not None else "",
                    "CFG": str(metadata.cfg_scale) if metadata.cfg_scale is not None else "",
                    "Sampler": metadata.sampler,
                    "Model": metadata.model,
                }.items()
                if value
            },
        }

    result.setdefault("tool", "Unknown")
    result.setdefault("prompt", metadata.prompt)
    result.setdefault("negative_prompt", metadata.negative_prompt)
    result.setdefault("params", {})
    result["width"] = metadata.width
    result["height"] = metadata.height
    result["name"] = metadata.name
    return result


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

    result, raw_source_text = _api_metadata_from_sources(path, info)
    metadata_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
    raw_parts = [
        f"{key}: {value}"
        for key, value in info.items()
        if key in GENERIC_TEXT_KEYS or key.lower() in {generic.lower() for generic in GENERIC_TEXT_KEYS}
    ]
    if raw_source_text and raw_source_text not in raw_parts:
        raw_parts.append(raw_source_text)
    raw_metadata_text = "\n".join(text for text in raw_parts if text)

    tool = safe_text(result.get("tool"))
    scheduler = safe_text(_metadata_param(result, "Scheduler", "scheduler"))
    model_hash = safe_text(_metadata_param(result, "model_hash", "Model hash"))
    lora_list = _metadata_param(result, "Lora", "lora")
    if isinstance(lora_list, list):
        lora_text = ", ".join(str(l) for l in lora_list)
    else:
        lora_text = safe_text(lora_list)
    generation_time = result.get("generation_time")
    if generation_time is not None:
        generation_time = parse_float(safe_text(generation_time))
    clip_skip = parse_int(safe_text(_metadata_param(result, "clip_skip", "Clip skip")))
    hires_upscale = parse_float(safe_text(_metadata_param(result, "hires_upscale", "Hires upscale")))
    hires_steps = parse_int(safe_text(_metadata_param(result, "hires_steps", "Hires steps")))
    denoising_strength = parse_float(safe_text(_metadata_param(result, "denoising_strength", "Denoising strength")))
    vae = safe_text(_metadata_param(result, "VAE", "vae"))
    ensd = parse_int(safe_text(_metadata_param(result, "ENSD", "ensd")))
    aesthetic_score = parse_float(safe_text(_metadata_param(result, "aesthetic_score", "Aesthetic score")))
    date = safe_text(result.get("date"))
    aspect_ratio = safe_text(_metadata_param(result, "AspectRatio", "aspect_ratio"))

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
        prompt=safe_text(result.get("prompt")),
        negative_prompt=safe_text(result.get("negative_prompt")),
        model=safe_text(_metadata_param(result, "Model", "model")),
        sampler=safe_text(_metadata_param(result, "Sampler", "sampler")),
        seed=safe_text(_metadata_param(result, "Seed", "seed")),
        steps=parse_int(safe_text(_metadata_param(result, "Steps", "steps"))),
        cfg_scale=parse_float(safe_text(_metadata_param(result, "CFG", "CFG scale", "cfg_scale", "cfg"))),
        raw_metadata_text=raw_metadata_text,
        metadata_json=metadata_json,
        indexed_at=time.time(),
        tool=tool,
        scheduler=scheduler,
        model_hash=model_hash,
        lora_text=lora_text,
        generation_time=generation_time,
        clip_skip=clip_skip,
        hires_upscale=hires_upscale,
        hires_steps=hires_steps,
        denoising_strength=denoising_strength,
        vae=vae,
        ensd=ensd,
        aesthetic_score=aesthetic_score,
        date=date,
        aspect_ratio=aspect_ratio,
    )
