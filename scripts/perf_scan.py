#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sys
import time
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[index]


def fetch_scan(base_url: str, path: str) -> tuple[float, dict]:
    url = f"{base_url.rstrip('/')}/api/scan?{urlencode({'path': path})}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, payload


def main() -> int:
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:8000")
    scan_path = os.getenv("GALLERY_PERF_SCAN_PATH", "/home/ubuntu/gallery-repo/test mika")
    iterations = int(os.getenv("GALLERY_PERF_SCAN_ITERATIONS", "10"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_SCAN_P95_BUDGET_MS", "500"))

    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        duration_ms, last_payload = fetch_scan(base_url, scan_path)
        durations.append(duration_ms)

    report = {
        "url": f"{base_url.rstrip('/')}/api/scan",
        "path": scan_path,
        "iterations": len(durations),
        "min_ms": round(min(durations), 2),
        "p50_ms": round(median(durations), 2),
        "p95_ms": round(percentile(durations, 95), 2),
        "max_ms": round(max(durations), 2),
        "image_count": len(last_payload.get("images", [])),
        "folder_count": len(last_payload.get("folders", [])),
        "total_images": last_payload.get("total_images"),
        "next_cursor": last_payload.get("next_cursor"),
        "budget_p95_ms": p95_budget_ms,
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))

    if report["p95_ms"] > p95_budget_ms:
        print(f"scan p95 exceeded budget: {report['p95_ms']}ms > {p95_budget_ms}ms", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
