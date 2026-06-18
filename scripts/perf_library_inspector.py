#!/usr/bin/env python3
"""Measure `/api/library/inspector` latency against a running backend."""

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
    """Return the nearest-rank percentile for a list of duration values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[index]


def fetch_inspector(base_url: str, params: dict[str, str]) -> tuple[float, dict]:
    """Request `/api/library/inspector` once and return elapsed milliseconds plus JSON payload."""
    url = f"{base_url.rstrip('/')}/api/library/inspector?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, payload


def main() -> int:
    """Run repeated inspector requests, print JSON, and enforce p95/min-row budgets."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:8000")
    iterations = int(os.getenv("GALLERY_PERF_INSPECTOR_ITERATIONS", "10"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_INSPECTOR_P95_BUDGET_MS", "150"))
    min_rows = int(os.getenv("GALLERY_PERF_INSPECTOR_MIN_ROWS", "1"))
    params = {
        "q": os.getenv("GALLERY_PERF_INSPECTOR_QUERY", ""),
        "scope": os.getenv("GALLERY_PERF_INSPECTOR_SCOPE", "all"),
        "limit": os.getenv("GALLERY_PERF_INSPECTOR_LIMIT", "200"),
        "sort": os.getenv("GALLERY_PERF_INSPECTOR_SORT", "date_desc"),
    }
    path = os.getenv("GALLERY_PERF_INSPECTOR_PATH", "")
    if path:
        params["path"] = path

    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        duration_ms, last_payload = fetch_inspector(base_url, params)
        durations.append(duration_ms)

    returned = int(last_payload.get("returned", len(last_payload.get("rows", []))))
    report = {
        "url": f"{base_url.rstrip('/')}/api/library/inspector",
        "params": params,
        "iterations": len(durations),
        "min_ms": round(min(durations), 2),
        "p50_ms": round(median(durations), 2),
        "p95_ms": round(percentile(durations, 95), 2),
        "max_ms": round(max(durations), 2),
        "returned": returned,
        "total_indexed": last_payload.get("total_indexed"),
        "truncated": last_payload.get("truncated"),
        "budget_p95_ms": p95_budget_ms,
        "min_rows": min_rows,
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))

    failed = False
    if report["p95_ms"] > p95_budget_ms:
        print(f"inspector p95 exceeded budget: {report['p95_ms']}ms > {p95_budget_ms}ms", file=sys.stderr)
        failed = True
    if returned < min_rows:
        print(f"inspector returned too few rows: {returned} < {min_rows}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
