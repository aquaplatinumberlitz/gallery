#!/usr/bin/env python3
"""Measure `/api/scan` latency against a running backend and enforce a p95 budget.

Purpose:
Measure scan endpoint latency against a running backend and real or fixture album.

Guarantees:
* repeated `/api/scan` requests produce min/p50/p95/max JSON output
* p95 and minimum returned-image budgets fail the process when exceeded

Run when:
* changing scan pagination, warm listing, cached dimensions, or scan perf budgets
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import budget_for, emit_report, summarize_samples  # noqa: E402


def fetch_scan(base_url: str, path: str) -> tuple[float, dict]:
    """Request `/api/scan` once and return elapsed milliseconds plus JSON payload."""
    url = f"{base_url.rstrip('/')}/api/scan?{urlencode({'path': path})}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8")
        import json

        data = json.loads(payload)
    return (time.perf_counter() - started) * 1000, data


def main() -> int:
    """Run repeated scan requests, print a compact JSON report, and enforce budget."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:8000")
    scan_path = os.getenv("GALLERY_PERF_SCAN_PATH", "/home/ubuntu/gallery-repo/test mika")
    iterations = int(os.getenv("GALLERY_PERF_SCAN_ITERATIONS", "10"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_SCAN_P95_BUDGET_MS", str(budget_for("scan", "p95_ms"))))
    min_images = int(os.getenv("GALLERY_PERF_SCAN_MIN_IMAGES", "1"))

    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        duration_ms, last_payload = fetch_scan(base_url, scan_path)
        durations.append(duration_ms)

    stats = summarize_samples(durations)
    report = {
        "url": f"{base_url.rstrip('/')}/api/scan",
        "path": scan_path,
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "image_count": sum(item.get("type") == "image" for item in last_payload.get("media", [])),
        "folder_count": len(last_payload.get("folders", [])),
        "total_images": last_payload.get("total_images"),
        "next_media_cursor": last_payload.get("next_media_cursor"),
        "budget_p95_ms": p95_budget_ms,
        "min_images": min_images,
        "budget_source": "scripts/perf_budgets.toml[scan].p95_ms",
    }
    print(emit_report(report))

    failed = False
    if report["p95_ms"] > p95_budget_ms:
        print(f"scan p95 exceeded budget: {report['p95_ms']}ms > {p95_budget_ms}ms", file=sys.stderr)
        failed = True
    if report["image_count"] < min_images and not report["next_media_cursor"]:
        print(f"scan returned too few images: {report['image_count']} < {min_images}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
