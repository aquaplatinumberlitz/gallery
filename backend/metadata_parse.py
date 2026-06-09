import copy
import json
import re
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Optional

from PIL import Image
from cachetools import LRUCache
from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .config import METADATA_CACHE_MAX_BYTES
from .errors import APIError, ErrorType
from .files import check_image_limits, is_image
from .metadata_extract import extract_loras
from .metadata_store import upsert_image_dimensions, upsert_metadata_result
from .paths import is_path_safe, resolve_path


def _estimate_dict_size(d: dict) -> int:
    """Estimate memory size of a dict in bytes (rough approximation)."""
    try:
        return len(json.dumps(d, default=str).encode('utf-8'))
    except Exception:
        return sys.getsizeof(d)


_metadata_cache: LRUCache = LRUCache(maxsize=METADATA_CACHE_MAX_BYTES, getsizeof=_estimate_dict_size)
_metadata_cache_lock = threading.Lock()
_metadata_inflight: dict[tuple, Future[dict]] = {}

router = APIRouter()


def parse_ai_text_parameters(params_text: str) -> dict:
    """
    Parse A1111/WebUI parameter strings into metadata dict.
    Ported and adapted from legacy source.
    """
    metadata = {}
    if not params_text or not isinstance(params_text, str):
        return metadata

    neg_match = re.search(r'Negative prompt:', params_text, re.IGNORECASE)
    neg_idx = neg_match.start() if neg_match else -1

    params_start = None

    for marker in ['Steps:', 'Size:', 'Seed:', 'Model:']:
        idx = params_text.find(marker)
        if idx > 0 and (params_start is None or idx < params_start):
            params_start = idx

    if neg_idx >= 0:
        metadata['prompt'] = params_text[:neg_idx].strip()
        neg_end = params_start if params_start and params_start > neg_idx else len(params_text)
        neg_text = params_text[neg_match.end():neg_end].strip()
        for marker in ['Steps:', 'Size:', 'Seed:', 'Model:', 'Sampler:']:
            marker_idx = neg_text.find(marker)
            if marker_idx > 0:
                neg_text = neg_text[:marker_idx].strip()
                break
        metadata['negative_prompt'] = neg_text
    elif params_start:
        metadata['prompt'] = params_text[:params_start].strip()
    else:
        metadata['prompt'] = params_text.strip()

    patterns = {
        'Steps': r'Steps:\s*(\d+)',
        'Sampler': r'Sampler:\s*([^,\n]+?)(?:,|\n|$)',
        'CFG': r'CFG [Ss]cale:\s*([\d.]+)',
        'Seed': r'Seed:\s*(\d+)',
        'Model': r'Model:\s*([^,\n]+?)(?:,|\n|$)',
        'Scheduler': r'Scheduler:\s*([^,\n]+?)(?:,|\n|$)',
        'model_hash': r'Model hash:\s*(\w+)',
        'clip_skip': r'Clip skip:\s*(\d+)',
        'hires_upscale': r'Hires upscale:\s*([\d.]+)',
        'hires_steps': r'Hires steps:\s*(\d+)',
        'denoising_strength': r'Denoising strength:\s*([\d.]+)',
        'Size': r'Size:\s*(\d+x\d+)',
        'vae': r'VAE:\s*([^,\n]+?)(?:,|\n|$)',
        'ensd': r'ENSD:\s*(\d+)',
        'aesthetic_score': r'Aesthetic score:\s*([\d.]+)',
    }

    params = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, params_text, re.IGNORECASE)
        if match:
            params[key] = match.group(1).strip()

    size_val = params.pop('Size', None)
    if size_val:
        size_match = re.match(r'(\d+)x(\d+)', size_val)
        if size_match:
            params['Width'] = size_match.group(1)
            params['Height'] = size_match.group(2)

    combined_text = f"{metadata.get('prompt', '')} {metadata.get('negative_prompt', '')} {params_text}"
    loras = extract_loras(combined_text)

    if loras:
        params['Lora'] = loras

    metadata['params'] = params
    return metadata


def parse_comfy(prompt_json: str, workflow_json: Optional[str]) -> dict:
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

    nodes_by_id: dict = {}
    if isinstance(nodes, dict):
        nodes_by_id = nodes
    elif isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                nid = node.get("id") if isinstance(node, dict) else None
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

    def resolve_value(val, max_depth=5):
        """Resolve a ComfyUI input value, following node references."""
        if max_depth <= 0:
            return None
        if isinstance(val, list) and len(val) == 2:
            ref_node_id = str(val[0])
            ref_node = nodes_by_id.get(ref_node_id)
            if ref_node and isinstance(ref_node, dict):
                ref_inputs = ref_node.get("inputs", {})
                for input_key, input_val in ref_inputs.items():
                    if not isinstance(input_val, list):
                        return resolve_value(input_val, max_depth - 1)
                return None
        return val

    def get_scalar(val):
        """Extract a scalar value, returning None for node references."""
        resolved = resolve_value(val)
        if resolved is None:
            return None
        if isinstance(resolved, list):
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
                if name.endswith('.safetensors'):
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


def _parse_novelai_metadata(text: str) -> dict | None:
    """Parse NovelAI metadata from PNG parameters text."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    software = data.get("Software", "")
    if "NovelAI" not in software:
        return None

    params = {}

    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", "")

    for key, field in [
        ('Steps', 'steps'),
        ('Sampler', 'sampler'),
        ('Seed', 'seed'),
        ('CFG', 'scale'),
        ('Model', 'model'),
    ]:
        val = data.get(field)
        if val is not None:
            params[key] = str(val)

    for key in ['sm', 'sm_dyn', 'noise_schedule', 'width', 'height', 'cfg_rescale']:
        val = data.get(key)
        if val is not None:
            params[key] = str(val)

    width = data.get('width')
    height = data.get('height')

    loras = extract_loras(f"{prompt} {negative_prompt}")
    if loras:
        params['Lora'] = loras

    return {
        "tool": "NovelAI",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "params": params,
        "width": int(width) if width else 0,
        "height": int(height) if height else 0,
    }


def _parse_easydiffusion_metadata(text: str) -> dict | None:
    """Parse EasyDiffusion metadata from JSON parameters text."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None
    if 'sui_image_params' in data:
        return None
    if not all(k in data for k in ['prompt', 'negative_prompt', 'width', 'height']):
        return None

    params = {}
    prompt = data.get('prompt', '')
    negative_prompt = data.get('negative_prompt', '')

    for key, field in [
        ('Seed', 'seed'),
        ('Steps', 'steps'),
        ('Sampler', 'sampler'),
        ('CFG', 'cfg_scale'),
        ('Model', 'model'),
    ]:
        val = data.get(field)
        if val is not None:
            params[key] = str(val)

    width = data.get('width')
    height = data.get('height')

    loras = extract_loras(f"{prompt} {negative_prompt}")
    if loras:
        params['Lora'] = loras

    return {
        "tool": "EasyDiffusion",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "params": params,
        "width": int(width) if width else 0,
        "height": int(height) if height else 0,
    }


def _parse_metadata_uncached(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    try:
        check_image_limits(path)

        with Image.open(path) as img:
            width, height = img.size
            parameters = img.info.get("parameters")
            prompt_json = img.info.get("prompt")
            workflow_json = img.info.get("workflow")
            exif_data = img.getexif()

        result: dict = {}
        swarm_data = None

        # 1. Try SwarmUI (JSON in parameters - PNG)
        if parameters and parameters.strip().startswith('{'):
            try:
                data = json.loads(parameters)
                if 'sui_image_params' in data:
                    swarm_data = data
            except json.JSONDecodeError:
                pass

        # 2. Try SwarmUI (JSON in Exif UserComment - JPEG)
        if not swarm_data and exif_data:
            user_comment = exif_data.get(37510)
            if user_comment:
                if isinstance(user_comment, bytes):
                    if user_comment.startswith(b'ASCII\x00\x00\x00'):
                        user_comment = user_comment[8:]
                    try:
                        user_comment = user_comment.decode('utf-8', errors='ignore').strip()
                    except Exception:
                        user_comment = None

                if isinstance(user_comment, str) and user_comment.strip().startswith('{'):
                    try:
                        data = json.loads(user_comment)
                        if 'sui_image_params' in data:
                            swarm_data = data
                    except json.JSONDecodeError:
                        pass

        if swarm_data:
            sui_params = swarm_data.get('sui_image_params', {})
            sui_extra = swarm_data.get('sui_extra_data', {})
            sui_models = swarm_data.get('sui_models', [])

            params = {
                'Seed': str(sui_params.get('seed', '')),
                'Steps': str(sui_params.get('steps', '')),
                'CFG': str(sui_params.get('cfgscale', '')),
                'Sampler': sui_params.get('sampler', ''),
                'Scheduler': sui_params.get('scheduler', ''),
                'Model': sui_params.get('model', ''),
                'SwarmVersion': sui_params.get('swarm_version', ''),
                'AspectRatio': sui_params.get('aspectratio', ''),
                'Width': str(sui_params.get('width', '')),
                'Height': str(sui_params.get('height', ''))
            }

            final_loras = []
            seen_loras = set()

            if 'loras' in sui_params and isinstance(sui_params['loras'], list):
                lora_list = sui_params['loras']
                lora_weights = sui_params.get('loraweights', [])

                for i, lora in enumerate(lora_list):
                    model = ""
                    weight = 1.0

                    if isinstance(lora, dict):
                        model = lora.get('model', '')
                        weight = lora.get('weight', 1.0)
                    elif isinstance(lora, str):
                        model = lora
                        if isinstance(lora_weights, list) and i < len(lora_weights):
                            try:
                                weight = float(lora_weights[i])
                            except (ValueError, TypeError):
                                weight = 1.0

                    if model:
                        if model.endswith('.safetensors'):
                            model = model[:-12]
                        if model not in seen_loras:
                            final_loras.append(f"{model}:{weight}")
                            seen_loras.add(model)

            if isinstance(sui_models, list):
                for m in sui_models:
                    if m.get('param') == 'used_loras':
                        name = m.get('name', '')
                        if name.endswith('.safetensors'):
                            name = name[:-12]
                        if name and name not in seen_loras:
                            final_loras.append(name)
                            seen_loras.add(name)

            if final_loras:
                params['Lora'] = final_loras

            models_out = []
            if isinstance(sui_models, list):
                for m in sui_models:
                    models_out.append({
                        'name': m.get('name'),
                        'param': m.get('param'),
                        'hash': m.get('hash')
                    })

            result = {
                "tool": "SwarmUI",
                "prompt": sui_params.get('prompt', ''),
                "negative_prompt": sui_params.get('negativeprompt', ''),
                "params": {k: v for k, v in params.items() if v},
                "models": models_out
            }

            date = sui_extra.get('date')
            if date:
                result['date'] = date

            gen_time = sui_extra.get('generation_time') or sui_extra.get('prep_time')
            if gen_time:
                result['generation_time'] = gen_time

        # 3. Try ComfyUI
        if not result and (prompt_json or workflow_json):
            result = parse_comfy(prompt_json or "", workflow_json)

        # 4. Try A1111 or NovelAI/EasyDiffusion
        if not result and parameters:
            if parameters.strip().startswith('{'):
                novelai_result = _parse_novelai_metadata(parameters)
                if novelai_result:
                    result = novelai_result
                else:
                    easy_result = _parse_easydiffusion_metadata(parameters)
                    if easy_result:
                        result = easy_result
                    else:
                        parsed = parse_ai_text_parameters(parameters)
                        if parsed and parsed.get('params'):
                            result = {
                                "tool": "A1111",
                                "prompt": parsed.get('prompt', ''),
                                "negative_prompt": parsed.get('negative_prompt', ''),
                                "params": parsed.get('params', {})
                            }
            else:
                parsed = parse_ai_text_parameters(parameters)
                if parsed and parsed.get('params'):
                    prompt_text = parsed.get('prompt', '')
                    if prompt_text.startswith('masterpiece, best quality,'):
                        result = {
                            "tool": "NovelAI",
                            "prompt": prompt_text,
                            "negative_prompt": parsed.get('negative_prompt', ''),
                            "params": parsed.get('params', {})
                        }
                    else:
                        result = {
                            "tool": "A1111",
                            "prompt": prompt_text,
                            "negative_prompt": parsed.get('negative_prompt', ''),
                            "params": parsed.get('params', {})
                        }

        # 5. Try .txt sidecar file
        if not result:
            txt_path = path.with_suffix('.txt')
            if txt_path.exists():
                text = txt_path.read_text(encoding='utf-8', errors='ignore')
                parsed = parse_ai_text_parameters(text)
                if parsed and parsed.get('params'):
                    result = {
                        "tool": "A1111",
                        "prompt": parsed.get('prompt', ''),
                        "negative_prompt": parsed.get('negative_prompt', ''),
                        "params": parsed.get('params', {})
                    }

        if not result:
            result = {"tool": "Unknown", "prompt": "", "negative_prompt": "", "params": {}}

        result["width"] = width
        result["height"] = height
        result["name"] = path.name
        return result

    except APIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise APIError(400, ErrorType.INVALID_FILE, f"Unable to parse metadata: {exc}")


def _metadata_cache_key(path: Path) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime, stat.st_size)


def parse_metadata(path: Path) -> dict:
    """
    Parse and cache image metadata.
    Uses size-based LRU cache (100MB max) for optimal memory usage.
    """
    if not path.exists() or not path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")

    try:
        key = _metadata_cache_key(path)
    except OSError as exc:
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found") from exc

    with _metadata_cache_lock:
        cached = _metadata_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        future = _metadata_inflight.get(key)
        if future is None:
            future = Future()
            _metadata_inflight[key] = future
            is_producer = True
        else:
            is_producer = False

    if not is_producer:
        return copy.deepcopy(future.result())

    try:
        metadata = _parse_metadata_uncached(path)
        upsert_metadata_result(path, metadata)
        with _metadata_cache_lock:
            _metadata_cache[key] = metadata
        future.set_result(metadata)
        return copy.deepcopy(metadata)
    except OSError as exc:
        api_exc = APIError(404, ErrorType.NOT_FOUND, "Image file not found")
        future.set_exception(api_exc)
        raise api_exc from exc
    except APIError as exc:
        future.set_exception(exc)
        raise
    except Exception as exc:  # noqa: BLE001
        api_exc = APIError(500, ErrorType.SERVER_ERROR, "Internal server error")
        future.set_exception(api_exc)
        raise api_exc from exc
    finally:
        with _metadata_cache_lock:
            _metadata_inflight.pop(key, None)


@router.get("/api/metadata")
async def api_metadata(path: str = Query(..., description="Absolute path to image file")):
    file_path = resolve_path(path)
    if not is_path_safe(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")

    return await run_in_threadpool(parse_metadata, file_path)
