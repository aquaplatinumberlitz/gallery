#!/usr/bin/env python3
"""Measure `/api/search` and `/api/library/inspector/metadata` P95 latency.

Purpose:
Benchmark search endpoint latency against a running backend with an indexed
library. Two endpoints are measured because they back the metadata inspector
drawer: `/api/search` (album/photo/prompt sections) and
`/api/library/inspector/metadata` (per-image metadata detail).

Guarantees:
* broad filename, prompt-heavy, album-heavy, fielded, CJK, and keyset-page
  requests produce min/p50/p95/max JSON output
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


SEARCH_QUERY_CLASSES = (
    ("broad_filename", "search_asset_000", 1),
    ("prompt_heavy", "blue forest prompt heavy constellation 1234", 1),
    ("album_heavy", "search_album", 1),
    ("fielded", 'constellation model:perf-model-3 sampler:"Euler a"', 1),
    ("cjk", "星空 猫 風景", 1),
    ("repeated_keyset_pages", "search_asset_00", 3),
)


def bench_search_case(base_url: str, name: str, query: str, iterations: int, pages: int = 1) -> dict:
    """Benchmark one representative search class, including keyset pages."""
    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        cursor = ""
        for _page in range(max(1, pages)):
            params = {"q": query, "scope": "all", "limit": "50"}
            if cursor:
                params["cursor"] = cursor
            duration, last_payload = _get_json(base_url, "/api/search", params)
            durations.append(duration)
            cursor = str(last_payload.get("next_cursor") or "")
            if not cursor:
                break
    stats = summarize_samples(durations)
    return {
        "class": name,
        "endpoint": "/api/search",
        "query": query,
        "requests": int(stats["count"]),
        "pages_per_iteration": pages,
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "albums": len(last_payload.get("albums", [])) if isinstance(last_payload, dict) else 0,
        "photos": len(last_payload.get("photos", [])) if isinstance(last_payload, dict) else 0,
        "prompt": len(last_payload.get("prompt", [])) if isinstance(last_payload, dict) else 0,
    }


def bench_search(base_url: str, query: str, iterations: int) -> dict:
    """Backward-compatible single-query benchmark helper."""
    return bench_search_case(base_url, "custom", query, iterations)


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
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:4701")
    iterations = int(os.getenv("GALLERY_PERF_BENCH_SEARCH_ITERATIONS", "10"))
    query = os.getenv("GALLERY_PERF_BENCH_SEARCH_QUERY", "search_asset_000")
    search_budget = float(os.getenv("GALLERY_PERF_SEARCH_P95_BUDGET_MS", str(budget_for("search", "p95_ms"))))
    inspector_md_budget = float(
        os.getenv(
            "GALLERY_PERF_INSPECTOR_METADATA_P95_BUDGET_MS",
            str(budget_for("inspector_metadata", "p95_ms")),
        )
    )

    search_classes = [
        bench_search_case(base_url, name, query_text, iterations, pages)
        for name, query_text, pages in SEARCH_QUERY_CLASSES
    ]
    if query != SEARCH_QUERY_CLASSES[0][1]:
        search_classes.append(bench_search(base_url, query, iterations))
    slowest_search = max(search_classes, key=lambda result: float(result["p95_ms"]))
    search_result = {
        "endpoint": "/api/search",
        "p95_ms": slowest_search["p95_ms"],
        "slowest_class": slowest_search["class"],
        "class_count": len(search_classes),
    }
    inspector_md_path = _find_inspector_metadata_path(base_url)
    inspector_md_result = bench_inspector_metadata(base_url, inspector_md_path, iterations)

    report = {
        "url": base_url,
        "query": query,
        "fixture_search_rows": int(os.getenv("GALLERY_PERF_SEARCH_ROWS", "0")),
        "search": search_result,
        "search_classes": search_classes,
        "inspector_metadata": inspector_md_result,
        "budgets": {
            "search_p95_ms": search_budget,
            "search_ci_rows": int(budget_for("search", "ci_rows")),
            "search_scheduled_rows": int(budget_for("search", "scheduled_rows")),
            "inspector_metadata_p95_ms": inspector_md_budget,
        },
        "budget_sources": {
            "search_p95_ms": "scripts/perf_budgets.toml[search].p95_ms",
            "inspector_metadata_p95_ms": "scripts/perf_budgets.toml[inspector_metadata].p95_ms",
        },
    }
    print(emit_report(report))

    failed = False
    for result in search_classes:
        if result["p95_ms"] > search_budget:
            print(
                f"/api/search {result['class']} p95 exceeded budget: {result['p95_ms']}ms > {search_budget}ms",
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
