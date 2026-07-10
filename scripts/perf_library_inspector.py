#!/usr/bin/env python3
"""Measure `/api/library/inspector` latency against a running backend."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import budget_for, emit_report, summarize_samples  # noqa: E402


def fetch_inspector(base_url: str, params: dict[str, str]) -> tuple[float, dict]:
    """Request `/api/library/inspector` once and return elapsed milliseconds plus JSON payload."""
    url = f"{base_url.rstrip('/')}/api/library/inspector?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        import json

        data = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, data


def main() -> int:
    """Run repeated inspector requests, print JSON, and enforce p95/min-row budgets."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:4701")
    iterations = int(os.getenv("GALLERY_PERF_INSPECTOR_ITERATIONS", "10"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_INSPECTOR_P95_BUDGET_MS", str(budget_for("inspector", "p95_ms"))))
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

    stats = summarize_samples(durations)
    returned = int(last_payload.get("returned", len(last_payload.get("rows", []))))
    report = {
        "url": f"{base_url.rstrip('/')}/api/library/inspector",
        "params": params,
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "returned": returned,
        "total_indexed": last_payload.get("total_indexed"),
        "truncated": last_payload.get("truncated"),
        "budget_p95_ms": p95_budget_ms,
        "min_rows": min_rows,
        "budget_source": "scripts/perf_budgets.toml[inspector].p95_ms",
    }
    print(emit_report(report))

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
