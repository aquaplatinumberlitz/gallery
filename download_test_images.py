#!/usr/bin/env python3
"""Download AI images WITH metadata from CivitAI for gallery testing."""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from PIL import Image
import io

OUTPUT = Path("/home/ubuntu/gallery-repo/test-images")
OUTPUT.mkdir(exist_ok=True)

CIVITAI_API = "https://civitai.com/api/v1/images"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

TARGET = 100  # target images
sources = {
    "trending_day": f"{CIVITAI_API}?limit=100&sort=Most+Reactions&period=Day&nsfw=false",
    "trending_week": f"{CIVITAI_API}?limit=100&sort=Most+Reactions&period=Week&nsfw=false",
    "trending_month": f"{CIVITAI_API}?limit=100&sort=Most+Reactions&period=Month&nsfw=false",
    "newest": f"{CIVITAI_API}?limit=100&sort=Newest&nsfw=false",
}

def has_metadata(meta, workflow):
    """Check if an image has useful embedded metadata for gallery testing."""
    if workflow and workflow != "{}" and len(str(workflow)) > 50:
        return True
    if meta and isinstance(meta, dict):
        # Check for various metadata fields
        fields = ["prompt", "negativePrompt", "model", "seed", "steps", "cfgScale",
                  "sampler", "Model", "Positive Prompt", "Negative Prompt"]
        for f in fields:
            if meta.get(f):
                return True
        # Check ComfyUI mode
        if meta.get("comfy"):
            return True
    return False

def get_meta_info(meta):
    """Describe what metadata is available."""
    info = []
    if not meta:
        return "no meta"
    for f in ["model", "Model", "prompt", "Positive Prompt"]:
        v = meta.get(f, "")
        if v and isinstance(v, str) and len(v) > 3:
            info.append(f"{f}={v[:60]}..")
            break
    if meta.get("seed"):
        info.append(f"seed={meta['seed']}")
    if meta.get("steps"):
        info.append(f"steps={meta['steps']}")
    if meta.get("cfgScale") or meta.get("cfg"):
        info.append(f"cfg={meta.get('cfgScale') or meta.get('cfg')}")
    if meta.get("sampler"):
        info.append(f"sampler={meta['sampler']}")
    return ", ".join(info) if info else "minimal"

def download_file(url, path):
    """Download a file with retries."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  FAIL: {e}")
    return False

def verify_png(path):
    """Check if PNG has any metadata chunks (tEXt, iTXt, zTXt)."""
    try:
        img = Image.open(path)
        if img.format != "PNG":
            return False
        # Check for text chunks in PNG info
        info = img.info or {}
        text_chunks = {k: v for k, v in info.items() 
                       if isinstance(v, str) and len(k) > 0}
        if text_chunks:
            keys = list(text_chunks.keys())
            return f"PNG chunks: {keys[:5]}"
        return False
    except Exception:
        return False

def main():
    downloaded = 0
    checked = 0
    skipped_no_meta = 0
    
    for source_name, url in sources.items():
        print(f"\n=== Source: {source_name} ===")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  API error: {e}")
            continue
        
        images = data.get("items", data.get("images", data.get("metadata", [])))
        if not images:
            print(f"  No items found")
            continue
        
        print(f"  Got {len(images)} images from API")
        
        for img in images:
            if downloaded >= TARGET:
                break
            
            img_url = img.get("url", "")
            if not img_url:
                continue
            
            # Check metadata
            meta = img.get("meta") or {}
            workflow = img.get("workflow") or img.get("comfyui") or ""
            
            checked += 1
            
            # Create a category based on platform
            platform = "other"
            if workflow or (meta and "comfy" in str(meta).lower()):
                platform = "comfyui"
            elif meta.get("Model") or meta.get("model"):
                platform = "a1111"
            elif meta.get("sd_model_name"):
                platform = "swarmui"
            
            # Determine filename
            ext = os.path.splitext(img_url.split("?")[0])[1] or ".png"
            if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".png"
            
            fid = img.get("id", checked)
            fname = f"{platform}_{fid}_{downloaded+1:03d}{ext}"
            fpath = OUTPUT / fname
            
            if fpath.exists():
                continue
            
            print(f"  [{source_name[:3]}] #{checked}: {fname}", end="")
            if download_file(img_url, fpath):
                result = verify_png(fpath)
                if result:
                    meta_info = get_meta_info(meta)
                    print(f" ✓ {meta_info}")
                    downloaded += 1
                else:
                    fpath.unlink()  # delete if no metadata
                    print(" ✗ no metadata chunks")
                    skipped_no_meta += 1
            else:
                print(" ✗ download failed")
            
            # Rate limit
            time.sleep(0.3)
    
    print(f"\n=== Summary ===")
    print(f"Checked: {checked}")
    print(f"Downloaded with metadata: {downloaded}")
    print(f"Skipped (no metadata): {skipped_no_meta}")
    print(f"Total in folder: {len(list(OUTPUT.glob('*')))}")
    
    # Verify all PNGs have metadata
    print(f"\n=== Metadata verification ===")
    meta_count = 0
    no_meta = []
    for f in sorted(OUTPUT.glob("*")):
        result = verify_png(f)
        if result:
            meta_count += 1
        else:
            no_meta.append(f.name)
    
    print(f"With metadata: {meta_count}/{meta_count + len(no_meta)}")
    if no_meta:
        print(f"No metadata: {no_meta}")

if __name__ == "__main__":
    main()
