#!/usr/bin/env python3
"""Measure thumbnail generation latency: cold (no cache) vs warm (cached).

Purpose:
Benchmark `/api/thumbnail` end-to-end latency for the first hit against a
previously-uncached image (cold: full PIL render + WebP encode + disk-cache
write) versus subsequent hits (warm: cached FileResponse, no render).

Guarantees:
* samples multiple distinct images so cold samples are not contaminated by
  cache warm-up from earlier iterations
* reports min/p50/p95/max for both cold and warm sets
* p95 budgets fail the process when exceeded
* budgets are read from `scripts/perf_budgets.toml` section `[thumbnail]`

Run when:
* changing thumbnail rendering, disk cache, or derivative persistence
* validating thumbnail perf before release
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import budget_for, emit_report, summarize_samples  # noqa: E402


def _list_image_files(folder: Path, limit: int) -> list[str]:
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
    found: list[str] = []
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.suffix.lower() in extensions:
            found.append(str(entry))
            if len(found) >= limit:
                break
    return found


def _fetch_thumbnail(base_url: str, image_path: str, max_long_edge: int) -> tuple[float, int]:
    url = (
        f"{base_url.rstrip('/')}/api/thumbnail?"
        f"{urlencode({'path': image_path, 'max_long_edge': max_long_edge})}"
    )
    request = Request(url, headers={"Accept": "image/webp"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        body = response.read()
    return (time.perf_counter() - started) * 1000, len(body)


def main() -> int:
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:8000")
    image_folder = os.getenv(
        "GALLERY_PERF_BENCH_THUMBNAIL_FOLDER",
        "/home/ubuntu/gallery-repo/test-images/a1111",
    )
    sample_count = int(os.getenv("GALLERY_PERF_BENCH_THUMBNAIL_SAMPLES", "5"))
    warm_repeats = int(os.getenv("GALLERY_PERF_BENCH_THUMBNAIL_WARM_REPEATS", "3"))
    max_long_edge = int(os.getenv("GALLERY_PERF_BENCH_THUMBNAIL_MAX_LONG_EDGE", "512"))
    cold_budget = float(
        os.getenv("GALLERY_PERF_BENCH_THUMBNAIL_COLD_P95_MS", str(budget_for("thumbnail", "cold_p95_ms")))
    )
    warm_budget = float(
        os.getenv("GALLERY_PERF_BENCH_THUMBNAIL_WARM_P95_MS", str(budget_for("thumbnail", "warm_p95_ms")))
    )

    folder = Path(image_folder)
    if not folder.is_dir():
        print(f"thumbnail bench folder missing: {folder}", file=sys.stderr)
        return 1
    images = _list_image_files(folder, sample_count)
    if not images:
        print(f"no image files found in {folder}", file=sys.stderr)
        return 1

    cold_durations: list[float] = []
    warm_durations: list[float] = []
    sample_details: list[dict] = []
    for image_path in images:
        try:
            cold_ms, cold_bytes = _fetch_thumbnail(base_url, image_path, max_long_edge)
        except Exception as exc:  # noqa: BLE001
            sample_details.append({"path": image_path, "error": str(exc)})
            continue
        cold_durations.append(cold_ms)
        warm_samples: list[float] = []
        for _ in range(max(1, warm_repeats)):
            warm_ms, _ = _fetch_thumbnail(base_url, image_path, max_long_edge)
            warm_samples.append(warm_ms)
        warm_durations.extend(warm_samples)
        sample_details.append(
            {
                "path": image_path,
                "cold_ms": round(cold_ms, 2),
                "cold_bytes": cold_bytes,
                "warm_min_ms": round(min(warm_samples), 2),
                "warm_p50_ms": round(sum(warm_samples) / len(warm_samples), 2),
            }
        )

    cold_stats = summarize_samples(cold_durations)
    warm_stats = summarize_samples(warm_durations)
    report = {
        "url": f"{base_url.rstrip('/')}/api/thumbnail",
        "folder": str(folder),
        "max_long_edge": max_long_edge,
        "image_count": len(images),
        "cold": cold_stats,
        "warm": warm_stats,
        "samples": sample_details,
        "budgets": {
            "cold_p95_ms": cold_budget,
            "warm_p95_ms": warm_budget,
        },
        "budget_sources": {
            "cold_p95_ms": "scripts/perf_budgets.toml[thumbnail].cold_p95_ms",
            "warm_p95_ms": "scripts/perf_budgets.toml[thumbnail].warm_p95_ms",
        },
    }
    print(emit_report(report))

    failed = False
    if cold_stats["p95_ms"] > cold_budget:
        print(
            f"thumbnail cold p95 exceeded budget: {cold_stats['p95_ms']}ms > {cold_budget}ms",
            file=sys.stderr,
        )
        failed = True
    if warm_stats["p95_ms"] > warm_budget:
        print(
            f"thumbnail warm p95 exceeded budget: {warm_stats['p95_ms']}ms > {warm_budget}ms",
            file=sys.stderr,
        )
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
