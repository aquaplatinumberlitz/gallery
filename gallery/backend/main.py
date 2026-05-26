import json
import re
import os
from pathlib import Path
from typing import Literal, Optional
import copy
from concurrent.futures import Future

import sys
import subprocess
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from PIL import Image, ImageOps, UnidentifiedImageError
from io import BytesIO
from cachetools import LRUCache
import threading

# =============================================================================
# CUSTOM ERROR TYPES - For better frontend error handling
# =============================================================================
class APIError(HTTPException):
    """Custom API error with error type for frontend handling."""
    def __init__(self, status_code: int, error_type: str, detail: str):
        super().__init__(
            status_code=status_code,
            detail={"error": error_type, "message": detail}
        )

class ErrorType:
    NOT_FOUND = "not_found"           # Path/file doesn't exist
    NOT_DIRECTORY = "not_directory"   # Path is not a folder
    PERMISSION_DENIED = "permission"  # No access permission
    INVALID_FILE = "invalid_file"     # Not an image or can't process
    TIMEOUT = "timeout"               # Operation took too long
    SERVER_ERROR = "server_error"     # Internal server error

# =============================================================================
# CACHE CONFIGURATION - Size-based LRU Cache (Big Tech style)
# =============================================================================
# Thumbnail cache: 1GB max (stores WebP bytes)
# Metadata cache: 100MB max (stores dict objects)
THUMBNAIL_CACHE_MAX_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB
METADATA_CACHE_MAX_BYTES = 100 * 1024 * 1024         # 100 MB

# Thread-safe caches with size-based eviction
_thumbnail_cache: LRUCache = LRUCache(maxsize=THUMBNAIL_CACHE_MAX_BYTES, getsizeof=len)
_thumbnail_cache_lock = threading.Lock()
_thumbnail_inflight: dict[tuple, Future[bytes]] = {}

def _estimate_dict_size(d: dict) -> int:
    """Estimate memory size of a dict in bytes (rough approximation)."""
    import sys
    try:
        # Use JSON serialization as size estimate (reasonable for metadata)
        return len(json.dumps(d, default=str).encode('utf-8'))
    except Exception:
        return sys.getsizeof(d)

_metadata_cache: LRUCache = LRUCache(maxsize=METADATA_CACHE_MAX_BYTES, getsizeof=_estimate_dict_size)
_metadata_cache_lock = threading.Lock()
_metadata_inflight: dict[tuple, Future[dict]] = {}


class FileNode(BaseModel):
    name: str
    path: str  # absolute path on disk
    type: Literal["folder", "image"]
    has_children: bool
    cover_images: list[str] = []
    mtime: float = 0  # Modified time (Unix timestamp)
    image_count: int = 0  # Number of images in folder (applies to "folder" type only)


app = FastAPI(title="Museum Art Gallery API")

def _get_cors_origins() -> list[str]:
    origin = os.getenv("FRONTEND_ORIGIN")
    port = os.getenv("FRONTEND_PORT")

    origins: list[str] = []
    if origin:
        origins.append(origin.rstrip("/"))
    if port:
        origins.extend([
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ])

    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get root path from environment variable, default to current directory
env_root = os.getenv("GALLERY_ROOT")
DEFAULT_ROOT = Path(env_root).resolve() if env_root else Path(".").resolve()
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

# Hard limits to avoid decompression bombs or extremely large files.
# Aligned with common thresholds: Google Photos and many cloud services use ~75MB and 100MP.
MAX_IMAGE_FILE_BYTES = 75 * 1024 * 1024   # 75 MB
MAX_IMAGE_PIXELS = 100 * 1024 * 1024      # 100 megapixels
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

LORA_PATTERN = re.compile(r"<lora:([^:>]+)(?::([^>]+))?>", re.IGNORECASE)


def resolve_path(raw_path: str) -> Path:
    """
    Resolve a user-supplied path.
    Handles Windows extended-length paths to reduce MAX_PATH issues with deep folders.
    """
    p = Path(raw_path)
    try:
        return p.resolve()
    except OSError:
        if os.name == "nt":
            # Add \\?\ prefix to support paths >260 chars
            extended = Path(r"\\?\\" + str(p))
            return extended.resolve()
        raise


def extract_loras(text: str) -> list[str]:
    """Extract LoRA tags from text string."""
    loras = []
    # Pattern 1: <lora:name:weight>
    for match in LORA_PATTERN.finditer(text):
        name, weight = match.group(1), match.group(2)
        loras.append(f"{name}:{weight}" if weight else name)
    
    # Pattern 2: LoRA: [name] (sometimes used in metadata)
    alt_matches = re.findall(r'LoRA:\s*\[([^\]]+)\]', text)
    for match in alt_matches:
        loras.extend([item.strip() for item in match.split(',') if item.strip()])
    
    return list(dict.fromkeys(loras))  # dedupe, preserve order


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def first_images_in_dir(dir_path: Path, limit: int = 3) -> list[str]:
    """
    Get the most recently modified images in a directory.
    Returns up to `limit` images sorted by modified time (newest first).
    """
    images: list[tuple[float, str]] = []  # (mtime, path)
    try:
        for entry in dir_path.iterdir():
            if entry.is_file() and is_image(entry):
                try:
                    mtime = entry.stat().st_mtime
                    images.append((mtime, str(entry.resolve())))
                except OSError:
                    continue
    except PermissionError:
        pass
    
    # Sort by modified time descending (newest first) and return paths only
    images.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in images[:limit]]


def has_any_children(dir_path: Path) -> bool:
    try:
        next(dir_path.iterdir())
        return True
    except (StopIteration, PermissionError):
        return False


def count_images_in_dir(dir_path: Path) -> int:
    """Count the number of image files directly inside a directory (non-recursive)."""
    try:
        return sum(
            1 for entry in dir_path.iterdir()
            if not entry.name.startswith(".") and entry.is_file() and is_image(entry)
        )
    except (PermissionError, OSError):
        return 0


def natural_sort_key(s: str) -> list:
    """
    Split string into text and numeric chunks for natural sorting.
    e.g. "10.png" -> [10, ".png"]
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def scan_directory(target_path: Path) -> tuple[list[FileNode], list[FileNode]]:
    if not target_path.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    if not target_path.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")

    folders: list[FileNode] = []
    images: list[FileNode] = []
    try:
        for entry in target_path.iterdir():
            if entry.name.startswith("."):
                continue  # skip hidden

            if entry.is_dir():
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    mtime = 0
                folders.append(
                    FileNode(
                        name=entry.name,
                        path=str(entry.resolve()),
                        type="folder",
                        has_children=has_any_children(entry),
                        cover_images=first_images_in_dir(entry, limit=3),
                        mtime=mtime,
                        image_count=count_images_in_dir(entry),
                    )
                )
            elif entry.is_file() and is_image(entry):
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    mtime = 0
                images.append(
                    FileNode(
                        name=entry.name,
                        path=str(entry.resolve()),
                        type="image",
                        has_children=False,
                        cover_images=[],
                        mtime=mtime,
                    )
                )
            else:
                continue  # ignore non-image files
    except PermissionError:
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Permission denied")

    folders.sort(key=lambda x: natural_sort_key(x.name))
    images.sort(key=lambda x: natural_sort_key(x.name))

    return folders, images


@app.get("/api/scan")
async def api_scan(
    path: str | None = Query(None, description="Absolute path to scan"),
    image_limit: int | None = Query(None, ge=1, le=5000, description="Max images to return"),
    image_cursor: int = Query(0, ge=0, description="Cursor/offset for images"),
):
    target = resolve_path(path) if path else DEFAULT_ROOT
    folders, images = await run_in_threadpool(scan_directory, target)

    total_images = len(images)
    start = image_cursor
    end = image_cursor + image_limit if image_limit else total_images
    paged_images = images[start:end]
    next_cursor = end if end < total_images else None

    return {
        "folders": folders,
        "images": paged_images,
        "next_cursor": next_cursor,
        "total_images": total_images,
    }


@app.post("/api/open-folder")
async def api_open_folder(path: str = Query(..., description="Absolute path to folder")):
    folder_path = resolve_path(path)
    if not folder_path.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    if not folder_path.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")
    
    try:
        if os.name == "nt":  # Windows
            os.startfile(folder_path)
        else:  # Linux / Mac
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(folder_path)])
        return {"message": "Opened successfully"}
    except Exception as e:
        raise APIError(500, ErrorType.SERVER_ERROR, f"Failed to open: {str(e)}")


def is_accessible_path(path: Path) -> bool:
    """
    Local-only build: intentionally allow any absolute path.
    Keep this hook so we can reintroduce path whitelisting if ever exposed publicly.
    """
    return True


@app.get("/api/image")
async def api_image(path: str = Query(..., description="Absolute path to image file")):
    file_path = resolve_path(path)
    if not is_accessible_path(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    return FileResponse(file_path)


def _thumbnail_cache_key(path: Path, max_size: int, quality: int) -> tuple:
    """Build cache key that invalidates on file change."""
    stat = path.stat()
    return (str(path), stat.st_mtime, stat.st_size, max_size, quality)


def _check_image_limits(path: Path) -> None:
    """
    Guardrails against oversized files or decompression bombs.
    Raises APIError with user-friendly message on violation.
    """
    try:
        stat = path.stat()
    except OSError:
        return

    if stat.st_size > MAX_IMAGE_FILE_BYTES:
        raise APIError(
            400,
            ErrorType.INVALID_FILE,
            f"Image is too large (> {MAX_IMAGE_FILE_BYTES // (1024 * 1024)} MB)",
        )

    try:
        with Image.open(path) as img:
            width, height = img.size
    except Image.DecompressionBombError as exc:
        raise APIError(400, ErrorType.INVALID_FILE, f"Image too large: {exc}") from exc
    except UnidentifiedImageError as exc:
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file") from exc

    if width * height > MAX_IMAGE_PIXELS:
        raise APIError(
            400,
            ErrorType.INVALID_FILE,
            f"Image dimensions exceed limit (> {MAX_IMAGE_PIXELS:,} pixels)",
        )


def _render_thumbnail_impl(path: Path, max_size: int, quality: int) -> bytes:
    """Render WebP thumbnail bytes (no caching here)."""
    with Image.open(path) as img:
        # Auto-rotate image based on EXIF orientation
        img = ImageOps.exif_transpose(img)
        
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=quality, method=6)
        return buffer.getvalue()


def generate_thumbnail(file_path: Path, max_size: int = 600, quality: int = 75) -> bytes:
    """
    Generate a thumbnail for the given image file.
    Uses size-based LRU cache (1GB max) for optimal memory usage.
    Cache key includes (path, mtime, size, max_size, quality) for automatic invalidation.
    Returns WebP bytes.
    """
    # Guard against oversized / malicious images
    _check_image_limits(file_path)

    cache_key = _thumbnail_cache_key(file_path, max_size, quality)
    
    # Avoid global serialization: de-dupe work per cache key only.
    with _thumbnail_cache_lock:
        cached = _thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached

        future = _thumbnail_inflight.get(cache_key)
        if future is None:
            future = Future()
            _thumbnail_inflight[cache_key] = future
            is_producer = True
        else:
            is_producer = False

    if not is_producer:
        return future.result()

    try:
        thumbnail_bytes = _render_thumbnail_impl(file_path, max_size, quality)
        with _thumbnail_cache_lock:
            _thumbnail_cache[cache_key] = thumbnail_bytes
        future.set_result(thumbnail_bytes)
        return thumbnail_bytes
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        api_exc = APIError(400, ErrorType.INVALID_FILE, f"Unable to process image: {exc}")
        future.set_exception(api_exc)
        raise api_exc from exc
    except Exception as exc:  # noqa: BLE001
        future.set_exception(exc)
        raise
    finally:
        with _thumbnail_cache_lock:
            _thumbnail_inflight.pop(cache_key, None)


@app.get("/api/thumbnail")
async def api_thumbnail(
    path: str = Query(..., description="Absolute path to image file"),
    max_size: int = Query(600, ge=1, le=4096, description="Max dimension for thumbnail/display"),
):
    """
    Serve optimized thumbnail for grid view.
    Cached with LRU based on (path, mtime, size, max_size, quality).
    `max_size` allows sharing this endpoint for Lightbox display (e.g., 2048px).
    """
    file_path = resolve_path(path)
    if not is_accessible_path(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    
    # Generate thumbnail in threadpool to avoid blocking
    try:
        thumbnail_bytes = await run_in_threadpool(generate_thumbnail, file_path, max_size, 75)
    except APIError:
        raise
    except FileNotFoundError:
        raise APIError(404, ErrorType.NOT_FOUND, "Image file not found")
    except OSError:
        # Includes PIL.UnidentifiedImageError and IO errors
        raise APIError(400, ErrorType.INVALID_FILE, "Unable to process image")
    
    return Response(content=thumbnail_bytes, media_type="image/webp")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/")
async def read_root():
    return {"message": "Museum Art Gallery API"}


def parse_ai_text_parameters(params_text: str) -> dict:
    """
    Parse A1111/WebUI parameter strings into metadata dict.
    Ported and adapted from legacy source.
    """
    metadata = {}
    if not params_text or not isinstance(params_text, str):
        return metadata

    # Extract prompt (everything before "Negative prompt:" or parameters)
    neg_match = re.search(r'Negative prompt:', params_text, re.IGNORECASE)
    neg_idx = neg_match.start() if neg_match else -1
    
    params_start = None
    
    # Find where parameters start (usually after a newline)
    for marker in ['Steps:', 'Size:', 'Seed:', 'Model:']:
        idx = params_text.find(marker)
        if idx > 0 and (params_start is None or idx < params_start):
            params_start = idx
    
    # Extract main prompt
    if neg_idx >= 0:
        metadata['prompt'] = params_text[:neg_idx].strip()
        # Extract negative prompt
        neg_end = params_start if params_start and params_start > neg_idx else len(params_text)
        neg_text = params_text[neg_match.end():neg_end].strip()
        # Find actual end of negative prompt (before parameters)
        for marker in ['Steps:', 'Size:', 'Seed:', 'Model:', 'Sampler:']:
            marker_idx = neg_text.find(marker)
            if marker_idx > 0:
                neg_text = neg_text[:marker_idx].strip()
                break
        metadata['negative_prompt'] = neg_text
    elif params_start:
        metadata['prompt'] = params_text[:params_start].strip()
    else:
        # No clear structure, assume it's all prompt
        metadata['prompt'] = params_text.strip()

    # Parameter patterns
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
    
    # Parse Size into width/height
    size_val = params.pop('Size', None)
    if size_val:
        size_match = re.match(r'(\d+)x(\d+)', size_val)
        if size_match:
            params['Width'] = size_match.group(1)
            params['Height'] = size_match.group(2)
    
    # Extract LoRAs using the shared utility function
    # We combine prompt and negative prompt to search for LoRAs, 
    # plus check the raw params text for other formats
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

    # Build a lookup dict of all nodes by ID for resolving references
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
        """Resolve a ComfyUI input value, following node references.
        
        In ComfyUI JSON, inputs can be:
        - scalar: 20, "model.safetensors", -2
        - node reference: ["27", 0] -> node 27's output 0
        """
        if max_depth <= 0:
            return None
        if isinstance(val, list) and len(val) == 2:
            # Node reference: [node_id, output_index]
            ref_node_id = str(val[0])
            ref_node = nodes_by_id.get(ref_node_id)
            if ref_node and isinstance(ref_node, dict):
                ref_inputs = ref_node.get("inputs", {})
                ref_type = ref_node.get("class_type") or ref_node.get("type", "")
                # Try to get the widget_values or inputs that match this output
                output_idx = val[1] if len(val) > 1 else 0
                # Look for the value in the referenced node's primary input
                for input_key, input_val in ref_inputs.items():
                    if not isinstance(input_val, list):
                        return resolve_value(input_val, max_depth - 1)
                # If all inputs are references, just return the ref key
                return None
        return val

    def get_scalar(val):
        """Extract a scalar value, returning None for node references."""
        resolved = resolve_value(val)
        if resolved is None:
            return None
        if isinstance(resolved, list):
            return None  # Still a reference after resolution
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
        # VAE extraction
        if ctype in {"VAEDecode", "VAELoader"}:
            vae_name = inputs.get("vae_name") or inputs.get("vae")
            if vae_name and isinstance(vae_name, str):
                params["VAE"] = str(vae_name)
        # Upscale model
        if ctype == "UpscaleModelLoader":
            upscale = inputs.get("model_name")
            if upscale and isinstance(upscale, str):
                params["UpscaleModel"] = str(upscale)
        # ControlNet
        if ctype == "ControlNetLoader":
            cn = inputs.get("control_net_name")
            if cn and isinstance(cn, str):
                params["ControlNet"] = str(cn)
        # LoRA
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
        # Clip skip
        if ctype == "CLIPSetLastLayer":
            clip_skip = get_scalar(inputs.get("stop_at_clip_layer"))
            if clip_skip is not None:
                params["clip_skip"] = str(clip_skip)

    prompts_sorted = sorted(prompts, key=lambda x: len(x), reverse=True)
    prompt = prompts_sorted[0] if prompts_sorted else ""
    negative_prompt = prompts_sorted[1] if len(prompts_sorted) > 1 else ""

    # Merge LoRAs from nodes with those from prompt text
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

    # NovelAI signature: "Software": "NovelAI"
    software = data.get("Software", "")
    if "NovelAI" not in software:
        return None

    params = {}

    # Extract prompt and negative prompt
    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", "")

    # NovelAI params
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

    # NovelAI specific: sm, sm_dyn, noise_schedule, etc.
    for key in ['sm', 'sm_dyn', 'noise_schedule', 'width', 'height', 'cfg_rescale']:
        val = data.get(key)
        if val is not None:
            params[key] = str(val)

    # Parse width/height from data
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

    # EasyDiffusion signature: has prompt, negative_prompt, width, height keys
    # but NOT sui_image_params (which would be SwarmUI)
    if not isinstance(data, dict):
        return None
    if 'sui_image_params' in data:
        return None  # This is SwarmUI, not EasyDiffusion
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
        # Reuse shared guardrails for size/pixel limits
        _check_image_limits(path)

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
            # Tag 37510 is UserComment
            user_comment = exif_data.get(37510)
            if user_comment:
                # Handle bytes (common in Exif)
                if isinstance(user_comment, bytes):
                    # Remove "ASCII\0\0\0" prefix if present
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

            # LoRAs
            final_loras = []
            seen_loras = set()

            # From sui_image_params.loras
            if 'loras' in sui_params and isinstance(sui_params['loras'], list):
                lora_list = sui_params['loras']
                lora_weights = sui_params.get('loraweights', [])
                
                for i, lora in enumerate(lora_list):
                    model = ""
                    weight = 1.0
                    
                    # Case A: List of Objects (Newer SwarmUI)
                    if isinstance(lora, dict):
                        model = lora.get('model', '')
                        weight = lora.get('weight', 1.0)
                    
                    # Case B: List of Strings (Older SwarmUI / Different Config)
                    elif isinstance(lora, str):
                        model = lora
                        # Try to get weight from parallel list
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

            # From sui_models where param == "used_loras"
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

            # Models array
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

        # 3. Try ComfyUI (check before text parsers since ComfyUI often stores
        #    prompt text in 'parameters' chunk AND full JSON in 'prompt' chunk)
        if not result and (prompt_json or workflow_json):
            result = parse_comfy(prompt_json or "", workflow_json)

        # 4. Try A1111 (Text in parameters) or NovelAI/EasyDiffusion (JSON parameters)
        #    Only if ComfyUI didn't find anything (to avoid ComfyUI images being
        #    misidentified as A1111 when they have both prompt text and JSON)
        if not result and parameters:
            # Detect JSON-based formats (NovelAI, EasyDiffusion)
            if parameters.strip().startswith('{'):
                # Try NovelAI first
                novelai_result = _parse_novelai_metadata(parameters)
                if novelai_result:
                    result = novelai_result
                else:
                    # Try EasyDiffusion
                    easy_result = _parse_easydiffusion_metadata(parameters)
                    if easy_result:
                        result = easy_result
                    else:
                        # Try generic A1111 text parsing (may also match some JSON text)
                        parsed = parse_ai_text_parameters(parameters)
                        if parsed and parsed.get('params'):
                            result = {
                                "tool": "A1111",
                                "prompt": parsed.get('prompt', ''),
                                "negative_prompt": parsed.get('negative_prompt', ''),
                                "params": parsed.get('params', {})
                            }
            else:
                # Plain text parameters - A1111 style
                parsed = parse_ai_text_parameters(parameters)
                if parsed and parsed.get('params'):
                    # Check if this looks like NovelAI (signature prompt prefix)
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

        # 5. Try .txt sidecar file (for images with companion metadata files)
        if not result:
            txt_path = path.with_suffix('.txt')
            if txt_path.exists():
                text = txt_path.read_text(encoding='utf-8', errors='ignore')
                # Try A1111 format on the text file
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
        # Bubble up to API layer so frontend sees error (avoid caching bad result)
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

    # Avoid global serialization: de-dupe work per cache key only.
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


@app.get("/api/metadata")
async def api_metadata(path: str = Query(..., description="Absolute path to image file")):
    file_path = resolve_path(path)
    if not is_accessible_path(file_path):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
    if not is_image(file_path):
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file")
    
    # Run blocking image processing in threadpool
    return await run_in_threadpool(parse_metadata, file_path)


@app.get("/api/landing-pages")
def get_landing_pages():
    # Assuming backend is running from /backend
    # We need to go up one level, then into frontend/public/landpage
    base_dir = os.path.dirname(os.path.abspath(__file__))
    landpage_dir = os.path.join(base_dir, "..", "frontend", "public", "landpage")
    
    pages = []
    if os.path.exists(landpage_dir):
        for root, dirs, files in os.walk(landpage_dir):
            for file in files:
                if file.lower().endswith(".html"):
                    # Create relative path for frontend
                    # full path: .../frontend/public/landpage/theme/index.html
                    # relative: /landpage/theme/index.html
                    
                    # Get path relative to 'public'
                    public_dir = os.path.join(base_dir, "..", "frontend", "public")
                    rel_path = os.path.relpath(os.path.join(root, file), public_dir)
                    
                    # Ensure forward slashes for URL
                    url_path = "/" + rel_path.replace(os.sep, "/")
                    pages.append(url_path)
    
    return pages


if __name__ == "__main__":
    import uvicorn

    # Bind to 127.0.0.1 only for local security
    port_env = os.getenv("PORT")
    try:
        port_val = int(port_env) if port_env else 8000
    except ValueError:
        port_val = 8000

    uvicorn.run("main:app", host="127.0.0.1", port=port_val, reload=True)
