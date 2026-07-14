#!/usr/bin/env python3
"""Create a deterministic gallery performance fixture.

Purpose:
Create a repeatable local gallery tree and metadata DB for perf smoke tests.

Guarantees:
* generated images are valid PNG files suitable for scan, thumbnail, preview, and lightbox tests
* file_index and image_metadata rows are seeded for Library Inspector perf tests
* synthetic catalog/search rows scale to thousands without creating image files
* shell env output can be sourced by perf runners or copied into a backend launch

Run when:
* preparing a stable local dataset for perf smoke tests
* changing perf budgets, perf runner defaults, or Library Inspector payload behavior
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ROOT = Path("/tmp/gallery_perf_fixture")
DEFAULT_ALBUM = "perf_album"
RELATED_FIXTURE_VERSION = 1
SEARCH_BENCHMARK_COHORT_ROWS = 5_000


def _synthetic_search_values(
    index: int,
    *,
    search_cohort_rows: int = SEARCH_BENCHMARK_COHORT_ROWS,
) -> dict[str, object]:
    """Return deterministic metadata with controlled relation groups."""
    width = 768 + (index % 4) * 128
    height = 1024 if index % 2 else 768
    if index <= 100:
        prompt = "cobalt fox, glass forest, related benchmark cluster"
    elif index <= 150:
        prompt = f"cobalt fox, glass forest, alternate framing {index}"
    elif index <= 300:
        prompt = f"unrelated ceramic harbor subject {index}"
    elif index >= search_cohort_rows:
        prompt = f"relation corpus prompt {index}"
    else:
        cjk = " 星空 猫 風景" if index % 10 == 0 else ""
        prompt = f"blue forest prompt heavy constellation {index}{cjk}"
    model = "related-perf-model" if index <= 300 else f"perf-model-{index % 8}"
    sampler = "Euler a" if index <= 60 else "DPM++ 2M" if index <= 100 else ("Euler a", "DPM++ 2M", "UniPC")[index % 3]
    seed = "424242" if index <= 20 else str(200_000 + index)
    return {
        "width": width,
        "height": height,
        "model": model,
        "sampler": sampler,
        "scheduler": "normal",
        "seed": seed,
        "steps": 24 if index <= 60 else 30 if index <= 100 else 20 + index % 30,
        "cfg_scale": 6.5 if index <= 60 else 7.5 if index <= 100 else 6.0 + (index % 5) / 2,
        "prompt": prompt,
    }


def _digest(label: str) -> bytes:
    return hashlib.sha256(label.encode("utf-8")).digest()


def _visual_bytes(index: int, axis: str) -> bytes:
    base = int.from_bytes(_digest(f"related-visual-reference:{axis}")[:8], "big")
    if index <= 50:
        value = base
    elif index <= 80:
        value = base ^ (1 << ((index - 51) % 64))
    elif index <= 100:
        value = base
        for offset in range(4):
            value ^= 1 << ((index + offset * 13 + (0 if axis == "h" else 7)) % 64)
    else:
        value = int.from_bytes(_digest(f"related-visual:{axis}:{index}")[:8], "big")
    return value.to_bytes(8, "big")


def _hash_bands(value: bytes) -> tuple[int, int, int, int]:
    integer = int.from_bytes(value, "big")
    return tuple((integer >> shift) & 0xFFFF for shift in (48, 32, 16, 0))


def _color_grid(index: int) -> bytes:
    base = (_digest("related-color-reference") * 2)[:48]
    if index <= 80:
        return base
    if index <= 100:
        return bytes(min(255, value + 4) for value in base)
    return (_digest(f"related-color:{index}") * 2)[:48]


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


def _seed_synthetic_search_rows(
    metadata_db: Path,
    album: Path,
    library_id: int,
    row_count: int,
    *,
    search_cohort_rows: int,
) -> int:
    """Seed active search rows without creating thousands of image files."""
    if row_count <= 0:
        return 0

    synthetic_root = album / "_synthetic_search"
    folder_count = min(120, max(1, row_count // 25))
    now = time.time()
    prefix = f"{synthetic_root}{os.sep}%"
    connection = sqlite3.connect(metadata_db)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM assets WHERE library_id = ? AND path LIKE ?", (library_id, prefix))
        connection.execute("DELETE FROM file_index_fts WHERE path LIKE ?", (prefix,))
        connection.execute("DELETE FROM file_index WHERE library_id = ? AND path LIKE ?", (library_id, prefix))
        connection.execute("DELETE FROM image_metadata WHERE path LIKE ?", (prefix,))

        folder_rows: list[tuple[object, ...]] = []
        folder_fts_rows: list[tuple[str, str, str, str]] = []
        for folder_index in range(folder_count):
            folder = synthetic_root / f"search_album_{folder_index:03d}"
            path = str(folder)
            name = folder.name
            parent = str(synthetic_root)
            folder_rows.append((path, name, parent, "folder", now, int(now * 1_000_000_000), None, now, library_id))
            folder_fts_rows.append((name, path, "folder", parent))
        connection.executemany(
            """INSERT INTO file_index (
                   path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, library_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            folder_rows,
        )
        connection.executemany(
            "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            folder_fts_rows,
        )

        asset_rows: list[tuple[object, ...]] = []
        file_rows: list[tuple[object, ...]] = []
        file_fts_rows: list[tuple[str, str, str, str]] = []
        metadata_rows: list[tuple[object, ...]] = []
        for index in range(row_count):
            folder = synthetic_root / f"search_album_{index % folder_count:03d}"
            name = f"search_asset_{index:05d}.png" if index < search_cohort_rows else f"related_asset_{index:05d}.png"
            path = str(folder / name)
            parent = str(folder)
            mtime_ns = 1_760_000_000_000_000_000 + index
            mtime = mtime_ns / 1_000_000_000
            size = 2048 + index % 512
            values = _synthetic_search_values(index, search_cohort_rows=search_cohort_rows)
            width = int(values["width"])
            height = int(values["height"])
            model = str(values["model"])
            sampler = str(values["sampler"])
            scheduler = str(values["scheduler"])
            prompt = str(values["prompt"])
            raw_metadata = json.dumps(
                {
                    "fixture": "synthetic-search",
                    "index": index,
                    "model": model,
                    "prompt": prompt,
                    "sampler": sampler,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            asset_rows.append((library_id, path, parent, name, "image", mtime_ns, size, width, height, now, "ready", 0))
            file_rows.append((path, name, parent, "image", mtime, mtime_ns, size, width, height, now, library_id))
            file_fts_rows.append((name, path, "image", parent))
            metadata_rows.append(
                (
                    path,
                    name,
                    mtime,
                    mtime_ns,
                    size,
                    width,
                    height,
                    "PNG",
                    "RGB",
                    0,
                    prompt,
                    "low quality, watermark",
                    model,
                    sampler,
                    scheduler,
                    str(values["seed"]),
                    int(values["steps"]),
                    float(values["cfg_scale"]),
                    raw_metadata,
                    raw_metadata,
                    now,
                    now,
                    "gallery-perf-fixture",
                    f"perf_lora_{index % 12}",
                    f"{width}:{height}",
                )
            )

        connection.executemany(
            """INSERT INTO assets (
                   library_id, path, parent_path, name, type, mtime_ns, size, width, height,
                   indexed_at, metadata_state, offline
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            asset_rows,
        )
        connection.executemany(
            """INSERT INTO file_index (
                   path, name, parent_path, type, mtime, mtime_ns, size, width, height, indexed_at, library_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            file_rows,
        )
        connection.executemany(
            "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            file_fts_rows,
        )
        connection.executemany(
            """INSERT INTO image_metadata (
                   path, name, mtime, mtime_ns, size, width, height, format, mode, has_alpha,
                   prompt, negative_prompt, model, sampler, scheduler, seed, steps, cfg_scale,
                   raw_metadata_text, metadata_json, updated_at, indexed_at, tool, lora_text, aspect_ratio
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            metadata_rows,
        )
        connection.commit()
    finally:
        connection.close()
    return row_count


def _seed_synthetic_related_indexes(
    metadata_db: Path,
    album: Path,
    library_id: int,
    row_count: int,
    *,
    search_cohort_rows: int,
) -> dict[str, int]:
    """Enrich synthetic search assets with precomputed relation rows only."""
    if row_count <= 0:
        return {"rows": 0, "reference_asset_id": 0}

    from backend.generation_signatures import GENERATION_SIGNATURE_EXTRACTOR_VERSION, PROMPT_NORMALIZER_VERSION
    from backend.visual_fingerprints import (
        VISUAL_DERIVATIVE_VERSION,
        VISUAL_FINGERPRINT_ALGORITHM_VERSION,
        VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    )

    synthetic_root = album / "_synthetic_search"
    prefix = f"{synthetic_root}{os.sep}%"
    now = time.time()
    connection = sqlite3.connect(metadata_db)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "DELETE FROM search_index_jobs WHERE index_name IN ('generation_signatures', 'visual_fingerprints')"
        )
        connection.execute(
            "DELETE FROM asset_search_extractions WHERE index_name IN ('generation_signatures', 'visual_fingerprints')"
        )
        connection.execute("DELETE FROM derivative_jobs")
        connection.execute("DELETE FROM metadata_index_jobs")
        assets = connection.execute(
            """
            SELECT id, name, mtime_ns, size FROM assets
            WHERE library_id = ? AND path LIKE ?
            ORDER BY mtime_ns, id
            """,
            (library_id, prefix),
        )
        reference_asset_id = 0
        processed = 0
        batch_size = 2_000
        signature_rows: list[tuple[object, ...]] = []
        model_identity_rows: list[tuple[object, ...]] = []
        fingerprint_rows: list[tuple[object, ...]] = []
        band_rows: list[tuple[int, int, int, int, int]] = []

        def flush() -> None:
            if not signature_rows:
                return
            connection.executemany(
                """
                INSERT OR REPLACE INTO asset_generation_signatures (
                  asset_id, library_id, prompt_hash, family_hash, recipe_hash,
                  exact_hash, normalizer_version, extractor_version,
                  source_mtime_ns, source_size, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                signature_rows,
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO asset_model_identity_values (
                  asset_id, normalized_name, normalized_hash, display_name,
                  display_hash, source_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                model_identity_rows,
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO asset_visual_fingerprints (
                  asset_id, library_id, source_mtime_ns, source_size,
                  derivative_role, derivative_version, algorithm_version,
                  dhash_horizontal, dhash_vertical, color_grid, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                fingerprint_rows,
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO asset_visual_hash_bands (
                  asset_id, library_id, hash_kind, band_no, band_value
                ) VALUES (?, ?, ?, ?, ?)
                """,
                band_rows,
            )
            signature_rows.clear()
            model_identity_rows.clear()
            fingerprint_rows.clear()
            band_rows.clear()

        for index, asset in enumerate(assets):
            if index >= row_count:
                break
            asset_id = int(asset["id"])
            if index == 0:
                reference_asset_id = asset_id
            prompt_hash = _digest("related-prompt-cluster") if index <= 100 else _digest(f"related-prompt:{index}")
            family_hash = _digest("related-family-cluster") if index <= 100 else _digest(f"related-family:{index}")
            recipe_hash = _digest("related-recipe-cluster") if index <= 60 else _digest(f"related-recipe:{index}")
            exact_hash = _digest("related-exact-cluster") if index <= 20 else _digest(f"related-exact:{index}")
            signature_rows.append(
                (
                    asset_id,
                    library_id,
                    prompt_hash,
                    family_hash,
                    recipe_hash,
                    exact_hash,
                    PROMPT_NORMALIZER_VERSION,
                    GENERATION_SIGNATURE_EXTRACTOR_VERSION,
                    int(asset["mtime_ns"]),
                    int(asset["size"]),
                    now,
                )
            )
            model_name = str(_synthetic_search_values(index, search_cohort_rows=search_cohort_rows)["model"])
            model_identity_rows.append(
                (
                    asset_id,
                    model_name.casefold(),
                    "",
                    model_name,
                    "",
                    f"{int(asset['mtime_ns'])}:{int(asset['size'])}",
                )
            )
            horizontal = _visual_bytes(index, "h")
            vertical = _visual_bytes(index, "v")
            fingerprint_rows.append(
                (
                    asset_id,
                    library_id,
                    int(asset["mtime_ns"]),
                    int(asset["size"]),
                    "fixture:precomputed",
                    VISUAL_DERIVATIVE_VERSION,
                    VISUAL_FINGERPRINT_ALGORITHM_VERSION,
                    horizontal,
                    vertical,
                    _color_grid(index),
                    now,
                )
            )
            for hash_kind, value in ((0, horizontal), (1, vertical)):
                band_rows.extend(
                    (asset_id, library_id, hash_kind, band_no, band_value)
                    for band_no, band_value in enumerate(_hash_bands(value))
                )
            processed += 1
            if len(signature_rows) >= batch_size:
                flush()
                connection.commit()
        flush()
        for index_name, extractor_version in (
            ("generation_signatures", GENERATION_SIGNATURE_EXTRACTOR_VERSION),
            ("visual_fingerprints", VISUAL_FINGERPRINT_EXTRACTOR_VERSION),
        ):
            connection.execute(
                """
                INSERT INTO search_index_states (
                  index_name, library_id, state, schema_version, extractor_version,
                  indexed_count, target_count, failed_count, skipped_count,
                  completed_at, updated_at
                ) VALUES (?, ?, 'ready', 1, ?, ?, ?, 0, 0, ?, ?)
                ON CONFLICT(index_name, library_id) DO UPDATE SET
                  state = 'ready', schema_version = 1,
                  extractor_version = excluded.extractor_version,
                  indexed_count = excluded.indexed_count,
                  target_count = excluded.target_count,
                  failed_count = 0, skipped_count = 0, active_job_id = NULL,
                  completed_at = excluded.completed_at,
                  updated_at = excluded.updated_at,
                  error_code = NULL, error_summary = NULL
                """,
                (index_name, library_id, extractor_version, processed, processed, now, now),
            )
        connection.execute("ANALYZE asset_generation_signatures")
        connection.execute("ANALYZE asset_visual_fingerprints")
        connection.execute("ANALYZE asset_visual_hash_bands")
        connection.execute("DELETE FROM derivative_jobs")
        connection.execute("DELETE FROM metadata_index_jobs")
        connection.commit()
    finally:
        connection.close()
    return {"rows": processed, "reference_asset_id": reference_asset_id}


def _seed_metadata(
    root: Path,
    album: Path,
    metadata_db: Path,
    search_rows: int,
    *,
    search_cohort_rows: int,
    related_assets: bool,
) -> tuple[int, int, dict[str, int]]:
    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import (
        index_directory_tree,
        initialize_database,
        register_library,
        update_folder_index_state,
        upsert_extracted_metadata,
    )

    initialize_database()
    library = register_library(root)
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
    synthetic = _seed_synthetic_search_rows(
        metadata_db,
        album,
        int(library["id"]),
        search_rows,
        search_cohort_rows=search_cohort_rows,
    )
    related = (
        _seed_synthetic_related_indexes(
            metadata_db,
            album,
            int(library["id"]),
            synthetic,
            search_cohort_rows=search_cohort_rows,
        )
        if related_assets
        else {"rows": 0, "reference_asset_id": 0}
    )
    return indexed, synthetic, related


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"export {key}={json.dumps(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Create a deterministic gallery fixture for performance tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="fixture root directory")
    parser.add_argument("--album-name", default=DEFAULT_ALBUM, help="album folder name to create")
    parser.add_argument("--images", type=int, default=240, help="number of valid PNG images to generate")
    parser.add_argument(
        "--search-rows",
        type=int,
        default=0,
        help="synthetic active search rows to seed without creating image files (CI uses 5000)",
    )
    parser.add_argument(
        "--search-cohort-rows",
        type=int,
        default=SEARCH_BENCHMARK_COHORT_ROWS,
        help="leading synthetic rows that use managed lexical benchmark names/prompts",
    )
    parser.add_argument(
        "--related-assets",
        action="store_true",
        help="precompute generation signatures and visual fingerprints for synthetic search rows",
    )
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

    os.environ["PATH_SAFETY_ROOT"] = str(root)
    os.environ["GALLERY_METADATA_DB"] = str(metadata_db)
    os.environ["GALLERY_THUMBNAIL_CACHE_DIR"] = str(thumbnail_cache)
    os.environ.setdefault("ENABLE_WARM_INDEXED_LISTING", "true")

    existing = list(album.glob("*.png"))
    if len(existing) != args.images:
        for path in existing:
            path.unlink()
        for index in range(args.images):
            _write_png(album / f"perf_{index:04d}.png", index)

    indexed, synthetic_search_rows, related = _seed_metadata(
        root,
        album,
        metadata_db,
        max(0, args.search_rows),
        search_cohort_rows=max(0, min(args.search_cohort_rows, args.search_rows)),
        related_assets=bool(args.related_assets),
    )

    env_values = {
        "PATH_SAFETY_ROOT": str(root),
        "PATH_SAFETY_ROOT_PATH": str(root),
        "GALLERY_METADATA_DB": str(metadata_db),
        "GALLERY_THUMBNAIL_CACHE_DIR": str(thumbnail_cache),
        "GALLERY_PERF_ALBUM_NAME": args.album_name,
        "GALLERY_PERF_ALBUM_PATH": str(album),
        "GALLERY_PERF_SCAN_PATH": str(album),
        "GALLERY_PERF_INSPECTOR_SCOPE": "all",
        "GALLERY_PERF_SEARCH_ROWS": str(min(args.search_cohort_rows, synthetic_search_rows)),
        "GALLERY_PERF_RELATED_ROWS": str(related["rows"]),
        "GALLERY_PERF_RELATED_REFERENCE_ASSET_ID": str(related["reference_asset_id"]),
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
                "synthetic_search_rows": synthetic_search_rows,
                "synthetic_related_rows": related["rows"],
                "related_reference_asset_id": related["reference_asset_id"],
                "env": env_values,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
