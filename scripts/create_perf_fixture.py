#!/usr/bin/env python3
"""Create a deterministic gallery performance fixture.

Purpose:
Create a repeatable local gallery tree and metadata DB for perf smoke tests.

Guarantees:
* generated images are valid PNG files suitable for scan, thumbnail, preview, and lightbox tests
* file_index and image_metadata rows are seeded for Library Inspector perf tests
* shell env output can be sourced by perf runners or copied into a backend launch

Run when:
* preparing a stable local dataset for perf smoke tests
* changing perf budgets, perf runner defaults, or Library Inspector payload behavior
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ROOT = Path("/tmp/gallery_perf_fixture")
DEFAULT_ALBUM = "perf_album"


def _write_png(path: Path, index: int) -> None:
    from PIL import Image, ImageDraw, PngImagePlugin

    width = 960 + (index % 5) * 40
    height = 720 + (index % 3) * 30
    image = Image.new("RGB", (width, height), ((index * 17) % 255, (index * 29) % 255, (index * 43) % 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, width - 24, height - 24), outline=(255, 255, 255), width=4)
    draw.text((48, 48), f"perf {index:04d}", fill=(255, 255, 255))

    params = (
        f"blue forest performance fixture image {index} <lora:perf_lora_{index % 7}:0.8>\n"
        "Negative prompt: low quality, blurry\n"
        f"Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: {100000 + index}, "
        f"Size: {width}x{height}, Model: perf-model-{index % 4}"
    )
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("parameters", params)
    png_info.add_text("Software", "gallery-perf-fixture")
    image.save(path, pnginfo=png_info)


def _folder_counts(folder: Path) -> dict[str, int]:
    child_count = 0
    folder_count = 0
    image_count = 0
    for entry in folder.iterdir():
        if entry.name.startswith("."):
            continue
        child_count += 1
        if entry.is_dir():
            folder_count += 1
        elif entry.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            image_count += 1
    return {"child_count": child_count, "folder_count": folder_count, "image_count": image_count}


def _seed_metadata(root: Path, album: Path) -> int:
    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import (
        index_directory_tree,
        initialize_database,
        register_library,
        update_folder_index_state,
        upsert_extracted_metadata,
    )

    initialize_database()
    register_library(root)
    index_directory_tree(root, include_metadata=False)
    update_folder_index_state(root, complete=True, **_folder_counts(root))
    update_folder_index_state(album, complete=True, **_folder_counts(album))

    indexed = 0
    for index, image_path in enumerate(sorted(album.glob("*.png"))):
        stat = image_path.stat()
        width = 960 + (index % 5) * 40
        height = 720 + (index % 3) * 30
        metadata = {
            "prompt": f"blue forest performance fixture image {index}",
            "negative_prompt": "low quality, blurry",
            "model": f"perf-model-{index % 4}",
            "sampler": "Euler a",
            "seed": str(100000 + index),
            "tool": "gallery-perf-fixture",
            "loras": [{"name": f"perf_lora_{index % 7}", "hash": f"perfhash{index % 7:02d}"}],
            "resources": [{"kind": "checkpoint", "name": f"perf-model-{index % 4}", "hash": f"modelhash{index % 4}"}],
        }
        if upsert_extracted_metadata(
            ExtractedMetadata(
                path=str(image_path.resolve()),
                name=image_path.name,
                mtime=stat.st_mtime,
                size=stat.st_size,
                width=width,
                height=height,
                format="PNG",
                mode="RGB",
                has_alpha=0,
                prompt=str(metadata["prompt"]),
                negative_prompt=str(metadata["negative_prompt"]),
                model=str(metadata["model"]),
                sampler=str(metadata["sampler"]),
                seed=str(metadata["seed"]),
                steps=20,
                cfg_scale=7.0,
                raw_metadata_text=json.dumps(metadata, sort_keys=True),
                metadata_json=json.dumps(metadata, sort_keys=True),
                indexed_at=time.time(),
                tool=str(metadata["tool"]),
                lora_text=f"perf_lora_{index % 7}",
                aspect_ratio=f"{width}:{height}",
            )
        ):
            indexed += 1
    return indexed


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"export {key}={json.dumps(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Create a deterministic gallery fixture for performance tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="fixture root directory")
    parser.add_argument("--album-name", default=DEFAULT_ALBUM, help="album folder name to create")
    parser.add_argument("--images", type=int, default=240, help="number of valid PNG images to generate")
    parser.add_argument("--metadata-db", default="", help="metadata DB path; defaults under the fixture root")
    parser.add_argument("--thumbnail-cache", default="", help="thumbnail cache path; defaults under the fixture root")
    parser.add_argument("--env-file", default="", help="write shell exports to this file")
    parser.add_argument("--clean", action="store_true", help="delete the fixture root before generating")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    album = root / args.album_name
    metadata_db = Path(args.metadata_db).resolve() if args.metadata_db else root / "gallery_perf_metadata.db"
    thumbnail_cache = Path(args.thumbnail_cache).resolve() if args.thumbnail_cache else root / "thumbnail_cache"

    if args.clean and root.exists():
        shutil.rmtree(root)

    root.mkdir(parents=True, exist_ok=True)
    album.mkdir(parents=True, exist_ok=True)
    thumbnail_cache.mkdir(parents=True, exist_ok=True)

    os.environ["GALLERY_ROOT"] = str(root)
    os.environ["GALLERY_METADATA_DB"] = str(metadata_db)
    os.environ["GALLERY_THUMBNAIL_CACHE_DIR"] = str(thumbnail_cache)
    os.environ.setdefault("ENABLE_WARM_INDEXED_LISTING", "true")

    existing = list(album.glob("*.png"))
    if len(existing) != args.images:
        for path in existing:
            path.unlink()
        for index in range(args.images):
            _write_png(album / f"perf_{index:04d}.png", index)

    indexed = _seed_metadata(root, album)

    env_values = {
        "GALLERY_ROOT": str(root),
        "GALLERY_ROOT_PATH": str(root),
        "GALLERY_METADATA_DB": str(metadata_db),
        "GALLERY_THUMBNAIL_CACHE_DIR": str(thumbnail_cache),
        "GALLERY_PERF_ALBUM_NAME": args.album_name,
        "GALLERY_PERF_ALBUM_PATH": str(album),
        "GALLERY_PERF_SCAN_PATH": str(album),
        "GALLERY_PERF_INSPECTOR_SCOPE": "all",
    }
    if args.env_file:
        _write_env_file(Path(args.env_file), env_values)

    print(
        json.dumps(
            {
                "root": str(root),
                "album": str(album),
                "images": args.images,
                "metadata_db": str(metadata_db),
                "thumbnail_cache": str(thumbnail_cache),
                "indexed_metadata_rows": indexed,
                "env": env_values,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
