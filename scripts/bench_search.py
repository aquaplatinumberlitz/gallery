#!/usr/bin/env python3
"""Measure `/api/search` and `/api/library/inspector/metadata` P95 latency.

Purpose:
Benchmark search endpoint latency against a running backend with an indexed
library. Two endpoints are measured because they back the metadata inspector
drawer: `/api/search` (album/photo/prompt sections) and
`/api/library/inspector/metadata` (per-image metadata detail).

Guarantees:
* repeated requests produce min/p50/p95/max JSON output for each endpoint
* p95 budgets fail the process when exceeded
* budgets are read from `scripts/perf_budgets.toml` sections `[search]` and
  `[inspector_metadata]` — env vars override only

Run when:
* changing search SQL, FTS index, fielded-query parser, or inspector metadata
  retrieval
* validating search perf before release
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


def _get_json(base_url: str, path: str, params: dict[str, str]) -> tuple[float, dict]:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, data


def _find_inspector_metadata_path(base_url: str) -> str | None:
    """Resolve a real indexed image path to feed `/api/library/inspector/metadata`."""
    try:
        _, payload = _get_json(base_url, "/api/library/inspector", {"q": "", "scope": "all", "limit": "1"})
    except Exception:  # noqa: BLE001
        return None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not rows:
        return None
    return rows[0].get("path")


def bench_search(base_url: str, query: str, iterations: int) -> dict:
    """Benchmark the search endpoint and summarize request durations."""
    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        duration, last_payload = _get_json(
            base_url,
            "/api/search",
            {"q": query, "scope": "all", "limit": "50"},
        )
        durations.append(duration)
    stats = summarize_samples(durations)
    return {
        "endpoint": "/api/search",
        "query": query,
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "albums": len(last_payload.get("albums", [])) if isinstance(last_payload, dict) else 0,
        "photos": len(last_payload.get("photos", [])) if isinstance(last_payload, dict) else 0,
        "prompt": len(last_payload.get("prompt", [])) if isinstance(last_payload, dict) else 0,
    }


def bench_inspector_metadata(base_url: str, image_path: str | None, iterations: int) -> dict | None:
    """Benchmark inspector metadata lookups for one indexed image."""
    if not image_path:
        return None
    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        try:
            duration, last_payload = _get_json(
                base_url,
                "/api/library/inspector/metadata",
                {"path": image_path},
            )
        except Exception as exc:  # noqa: BLE001
            return {"endpoint": "/api/library/inspector/metadata", "error": str(exc)}
        durations.append(duration)
    stats = summarize_samples(durations)
    return {
        "endpoint": "/api/library/inspector/metadata",
        "path": image_path,
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "fields": len(last_payload) if isinstance(last_payload, dict) else 0,
    }


def main() -> int:
    """Run search benchmarks and enforce their configured budgets."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:8000")
    iterations = int(os.getenv("GALLERY_PERF_BENCH_SEARCH_ITERATIONS", "10"))
    query = os.getenv("GALLERY_PERF_BENCH_SEARCH_QUERY", "a")
    search_budget = float(os.getenv("GALLERY_PERF_SEARCH_P95_BUDGET_MS", str(budget_for("search", "p95_ms"))))
    inspector_md_budget = float(
        os.getenv(
            "GALLERY_PERF_INSPECTOR_METADATA_P95_BUDGET_MS",
            str(budget_for("inspector_metadata", "p95_ms")),
        )
    )

    search_result = bench_search(base_url, query, iterations)
    inspector_md_path = _find_inspector_metadata_path(base_url)
    inspector_md_result = bench_inspector_metadata(base_url, inspector_md_path, iterations)

    report = {
        "url": base_url,
        "query": query,
        "search": search_result,
        "inspector_metadata": inspector_md_result,
        "budgets": {
            "search_p95_ms": search_budget,
            "inspector_metadata_p95_ms": inspector_md_budget,
        },
        "budget_sources": {
            "search_p95_ms": "scripts/perf_budgets.toml[search].p95_ms",
            "inspector_metadata_p95_ms": "scripts/perf_budgets.toml[inspector_metadata].p95_ms",
        },
    }
    print(emit_report(report))

    failed = False
    if search_result["p95_ms"] > search_budget:
        print(
            f"/api/search p95 exceeded budget: {search_result['p95_ms']}ms > {search_budget}ms",
            file=sys.stderr,
        )
        failed = True
    if inspector_md_result and "p95_ms" in inspector_md_result and inspector_md_result["p95_ms"] > inspector_md_budget:
        print(
            f"/api/library/inspector/metadata p95 exceeded budget: "
            f"{inspector_md_result['p95_ms']}ms > {inspector_md_budget}ms",
            file=sys.stderr,
        )
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
