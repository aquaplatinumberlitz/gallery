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
    configured_path = os.getenv("GALLERY_PERF_INSPECTOR_PATH", "").strip()
    if configured_path:
        return configured_path
    inspector_query = os.getenv("GALLERY_PERF_INSPECTOR_QUERY", "").strip()
    try:
        _, payload = _get_json(
            base_url,
            "/api/library/inspector",
            {"q": inspector_query, "scope": "all", "limit": "1"},
        )
    except Exception:  # noqa: BLE001
        return None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not rows:
        return None
    return rows[0].get("path")


SEARCH_QUERY_CLASSES = (
    ("broad_filename", "search_asset_000", 1, 50),
    ("prompt_heavy", "blue forest prompt heavy constellation", 1, 50),
    ("album_heavy", "search_album", 1, 1),
    ("fielded", 'constellation model:perf-model-3 sampler:"Euler a"', 1, 1),
    ("fielded_model_only", "model:perf-model-3", 1, 50),
    ("fielded_sampler_only", 'sampler:"Euler a"', 1, 50),
    ("mixed_short_token", "Euler a", 1, 50),
    ("cjk", "星空 猫 風景", 1, 50),
    ("repeated_keyset_pages", "search_asset_00", 3, 150),
)

SEARCH_RESULT_CONTRACTS: dict[str, dict[str, str]] = {
    "fielded_model_only": {"model": "perf-model-3"},
    "fielded_sampler_only": {"sampler": "Euler a"},
}


def bench_search_case(
    base_url: str,
    name: str,
    query: str,
    iterations: int,
    pages: int = 1,
    min_matches_per_iteration: int = 1,
) -> dict:
    """Benchmark one representative search class, including keyset pages."""
    durations: list[float] = []
    last_payload: dict = {}
    completed_page_chains = 0
    minimum_observed_matches: int | None = None
    unexpected_matches = 0
    expected_fields = SEARCH_RESULT_CONTRACTS.get(name, {})
    for _ in range(max(1, iterations)):
        cursor = ""
        observed_matches = 0
        requested_pages = max(1, pages)
        completed_pages = 0
        for page_index in range(requested_pages):
            params = {"q": query, "scope": "all", "limit": "50"}
            if cursor:
                params["cursor"] = cursor
            duration, last_payload = _get_json(base_url, "/api/search", params)
            durations.append(duration)
            media = last_payload.get("media", []) if isinstance(last_payload, dict) else []
            for row in media if isinstance(media, list) else []:
                if not isinstance(row, dict):
                    unexpected_matches += 1
                    continue
                if any(str(row.get(field) or "").casefold() != expected.casefold() for field, expected in expected_fields.items()):
                    unexpected_matches += 1
            observed_matches += int(last_payload.get("returned") or 0)
            if page_index == 0:
                observed_matches += len(last_payload.get("albums", []))
            completed_pages += 1
            cursor = str(last_payload.get("next_cursor") or "")
            if page_index + 1 < requested_pages and not cursor:
                break
        if completed_pages == requested_pages:
            completed_page_chains += 1
        minimum_observed_matches = (
            observed_matches if minimum_observed_matches is None else min(minimum_observed_matches, observed_matches)
        )
    stats = summarize_samples(durations)
    expected_requests = max(1, iterations) * max(1, pages)
    observed_matches = minimum_observed_matches or 0
    return {
        "class": name,
        "endpoint": "/api/search",
        "query": query,
        "requests": int(stats["count"]),
        "expected_requests": expected_requests,
        "pages_per_iteration": pages,
        "completed_page_chains": completed_page_chains,
        "expected_page_chains": max(1, iterations),
        "minimum_observed_matches": observed_matches,
        "minimum_required_matches": min_matches_per_iteration,
        "expected_result_fields": expected_fields,
        "unexpected_matches": unexpected_matches,
        "contract_ok": (
            int(stats["count"]) == expected_requests
            and completed_page_chains == max(1, iterations)
            and observed_matches >= min_matches_per_iteration
            and unexpected_matches == 0
        ),
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
        bench_search_case(base_url, name, query_text, iterations, pages, min_matches)
        for name, query_text, pages, min_matches in SEARCH_QUERY_CLASSES
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
        if not result["contract_ok"]:
            print(
                f"/api/search {result['class']} workload contract failed: "
                f"requests={result['requests']}/{result['expected_requests']}, "
                f"page_chains={result['completed_page_chains']}/{result['expected_page_chains']}, "
                f"matches={result['minimum_observed_matches']}/{result['minimum_required_matches']}, "
                f"unexpected_matches={result['unexpected_matches']}",
                file=sys.stderr,
            )
            failed = True
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
    if inspector_md_result is None or "error" in inspector_md_result:
        print("/api/library/inspector/metadata workload contract failed: no usable fixture path", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
