"""
Performance comparison: cold direct scan vs warm DB listing.

Usage:
    python scripts/perf_warm_listing.py [--path /path/to/folder] [--images 5000]

Requires a folder with real image files for meaningful cold-path timings.

Cold path: direct os.scandir + stat + sort.
Warm path:  SQLite file_index + folder_index_state read.

Target: 5000-image warm first page: 300-500ms.
"""

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENABLE_METRICS", "0")
os.environ.setdefault("ENABLE_WARM_INDEXED_LISTING", "true")


def create_test_fixtures(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (folder / f"image_{i:06d}.jpg").write_text(f"fake image {i}")
    # Add some subfolders
    for i in range(min(10, count // 10)):
        sub = folder / f"sub_{i:04d}"
        sub.mkdir(exist_ok=True)
        (sub / f"sub_img_{i:06d}.jpg").write_text(f"fake sub img {i}")
    print(f"Created {count} images + {min(10, count // 10)} subfolders in {folder}")


def benchmark_cold_scan(folder: Path, image_limit: int) -> dict:
    from backend.scan import scan_directory

    start = time.perf_counter()
    folders, images, perf = scan_directory(folder)
    scan_ms = (time.perf_counter() - start) * 1000

    total_images = len(images)
    start_idx = 0
    end_idx = start_idx + image_limit if image_limit else total_images
    paged = images[start_idx:end_idx]

    return {
        "method": "cold_direct_scan",
        "total_images": total_images,
        "returned_images": len(paged),
        "folders": len(folders),
        "duration_ms": round(scan_ms, 2),
        "list_ms": round(perf["list_ms"], 2),
        "stat_ms": round(perf["stat_ms"], 2),
        "sort_ms": round(perf["sort_ms"], 2),
    }


def benchmark_warm_listing(folder: Path, image_limit: int) -> dict | None:
    from backend.metadata_store import (
        get_warm_folder_listing,
        index_directory_tree,
        update_folder_index_state,
    )

    index_directory_tree(folder, include_metadata=False)

    counts = {"child_count": 0, "folder_count": 0, "image_count": 0}
    try:
        for entry in os.scandir(folder):
            if entry.name.startswith("."):
                continue
            counts["child_count"] += 1
            try:
                if entry.is_dir():
                    counts["folder_count"] += 1
                elif entry.is_file():
                    counts["image_count"] += 1
            except OSError:
                pass
    except OSError:
        pass

    update_folder_index_state(
        folder,
        complete=True,
        child_count=counts["child_count"],
        folder_count=counts["folder_count"],
        image_count=counts["image_count"],
    )

    start = time.perf_counter()
    result = get_warm_folder_listing(
        folder,
        offset=0,
        limit=image_limit,
        sort="name",
        image_limit=image_limit,
    )
    warm_ms = (time.perf_counter() - start) * 1000

    if result is None:
        return None

    return {
        "method": "warm_db_listing",
        "total_images": result["total_images"],
        "returned_images": len(result["images"]),
        "duration_ms": round(warm_ms, 2),
        "index_source": result.get("index_source", "warm_db"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm listing vs cold scan performance comparison")
    parser.add_argument("--path", type=str, default="/tmp/perf_warm_test", help="Path to folder with images")
    parser.add_argument("--images", type=int, default=5000, help="Number of test images to create")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep test fixtures after run")
    parser.add_argument("--image-limit", type=int, default=50, help="Images per page (default: 50)")
    args = parser.parse_args()

    import backend.metadata_store as ms

    ms.GALLERY_METADATA_DB = Path("/tmp/perf_warm_listing_test.db")
    ms._DB_INITIALIZED = False
    ms._DB_INITIALIZED_PATH = None

    folder = Path(args.path)
    needs_cleanup = not args.no_cleanup and folder.exists()

    if not folder.exists():
        create_test_fixtures(folder, args.images)
        needs_cleanup = True
    else:
        print(f"Using existing folder: {folder}")

    cold = benchmark_cold_scan(folder, args.image_limit)
    print(
        f"\nCold direct scan: {cold['duration_ms']}ms "
        f"({cold['total_images']} images, {cold['folders']} folders, "
        f"returned {cold['returned_images']})"
    )

    warm = benchmark_warm_listing(folder, args.image_limit)
    if warm is not None:
        print(
            f"Warm DB listing:  {warm['duration_ms']}ms "
            f"({warm['total_images']} images, "
            f"returned {warm['returned_images']})"
        )
        ratio = warm["duration_ms"] / cold["duration_ms"] * 100 if cold["duration_ms"] > 0 else 0
        print(f"Warm vs cold:     {ratio:.1f}% of cold time")
        if warm["duration_ms"] < 500:
            print("✅ Warm first page under 500ms target")
        else:
            print("⚠️  Warm first page exceeds 500ms target")
    else:
        print("Warm DB listing:  FAILED (returned None)")

    if needs_cleanup:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)
        print(f"\nCleaned up: {folder}")
    else:
        print(f"\nKept: {folder}")


if __name__ == "__main__":
    main()
