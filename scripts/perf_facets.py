#!/usr/bin/env python3
"""Measure `/api/facets` latency against the managed catalog.

Purpose:
* enforce a bounded p95 for the all-library facets aggregation
* fail when the managed fixture does not return model facet values

Guarantees:
* reads the canonical `[facets]` budget from `scripts/perf_budgets.toml`
* emits a machine-readable report and exits non-zero on latency/contract failure

Run when:
* changing facet authorization, aggregation SQL, indexes, or managed perf fixtures
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


def _fetch_facets(base_url: str) -> tuple[float, dict]:
    url = f"{base_url.rstrip('/')}/api/facets?{urlencode({'scope': 'all', 'max_values': '50'})}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, payload


def main() -> int:
    """Run repeated facets requests and enforce latency plus non-empty model values."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:4701")
    iterations = int(os.getenv("GALLERY_PERF_FACETS_ITERATIONS", "5"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_FACETS_P95_BUDGET_MS", str(budget_for("facets", "p95_ms"))))
    durations: list[float] = []
    payload: dict = {}
    for _ in range(max(1, iterations)):
        duration_ms, payload = _fetch_facets(base_url)
        durations.append(duration_ms)

    stats = summarize_samples(durations)
    model_values = len(payload.get("model", [])) if isinstance(payload, dict) else 0
    report = {
        "url": f"{base_url.rstrip('/')}/api/facets",
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "model_values": model_values,
        "budget_p95_ms": p95_budget_ms,
        "budget_source": "scripts/perf_budgets.toml[facets].p95_ms",
    }
    print(emit_report(report))

    failed = report["p95_ms"] > p95_budget_ms or model_values < 1
    if report["p95_ms"] > p95_budget_ms:
        print(f"facets p95 exceeded budget: {report['p95_ms']}ms > {p95_budget_ms}ms", file=sys.stderr)
    if model_values < 1:
        print("facets returned no model values", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
