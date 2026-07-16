#!/usr/bin/env python3
"""Shared cold/warm benchmark implementation for image derivatives."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from perf_lib import budget_for, emit_report, summarize_samples


def _list_image_files(folder: Path, limit: int) -> list[str]:
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
    found: list[str] = []
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.suffix.lower() in extensions:
            found.append(str(entry))
            if len(found) >= limit:
                break
    return found


def _fetch_derivative(base_url: str, endpoint: str, image_path: str, max_long_edge: int) -> tuple[float, int]:
    url = f"{base_url.rstrip('/')}{endpoint}?{urlencode({'path': image_path, 'max_long_edge': max_long_edge})}"
    request = Request(url, headers={"Accept": "image/webp"})
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        body = response.read()
    return (time.perf_counter() - started) * 1000, len(body)


def run_derivative_benchmark(
    *,
    kind: str,
    endpoint: str,
    default_folder: str,
    default_max_long_edge: int,
) -> int:
    """Benchmark one derivative endpoint and enforce cold/warm p95 budgets."""
    env_prefix = f"GALLERY_PERF_BENCH_{kind.upper()}"
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:4701")
    folder = Path(os.getenv(f"{env_prefix}_FOLDER", default_folder))
    sample_count = int(os.getenv(f"{env_prefix}_SAMPLES", "5"))
    warm_repeats = max(1, int(os.getenv(f"{env_prefix}_WARM_REPEATS", "3")))
    max_long_edge = int(os.getenv(f"{env_prefix}_MAX_LONG_EDGE", str(default_max_long_edge)))
    cold_budget = float(os.getenv(f"{env_prefix}_COLD_P95_MS", str(budget_for(kind, "cold_p95_ms"))))
    warm_budget = float(os.getenv(f"{env_prefix}_WARM_P95_MS", str(budget_for(kind, "warm_p95_ms"))))

    if sample_count < 1:
        print(f"{kind} sample count must be >= 1", file=sys.stderr)
        return 1
    if not folder.is_dir():
        print(f"{kind} bench folder missing: {folder}", file=sys.stderr)
        return 1
    images = _list_image_files(folder, sample_count)
    if len(images) != sample_count:
        print(f"{kind} workload requires {sample_count} images, found {len(images)} in {folder}", file=sys.stderr)
        return 1

    cold_durations: list[float] = []
    warm_durations: list[float] = []
    sample_details: list[dict] = []
    for image_path in images:
        detail: dict = {"path": image_path}
        try:
            cold_ms, cold_bytes = _fetch_derivative(base_url, endpoint, image_path, max_long_edge)
            detail.update({"cold_ms": round(cold_ms, 2), "cold_bytes": cold_bytes})
            cold_durations.append(cold_ms)
        except Exception as exc:  # noqa: BLE001
            detail["cold_error"] = str(exc)
            sample_details.append(detail)
            continue

        warm_samples: list[float] = []
        warm_bytes: list[int] = []
        for _ in range(warm_repeats):
            try:
                warm_ms, response_bytes = _fetch_derivative(base_url, endpoint, image_path, max_long_edge)
            except Exception as exc:  # noqa: BLE001
                detail.setdefault("warm_errors", []).append(str(exc))
                continue
            warm_samples.append(warm_ms)
            warm_bytes.append(response_bytes)
        warm_durations.extend(warm_samples)
        if warm_samples:
            detail.update(
                {
                    "warm_min_ms": round(min(warm_samples), 2),
                    "warm_mean_ms": round(sum(warm_samples) / len(warm_samples), 2),
                    "warm_response_bytes": warm_bytes,
                }
            )
        sample_details.append(detail)

    cold_stats = summarize_samples(cold_durations)
    warm_stats = summarize_samples(warm_durations)
    expected_warm_requests = len(images) * warm_repeats
    report = {
        "kind": kind,
        "url": f"{base_url.rstrip('/')}{endpoint}",
        "folder": str(folder),
        "max_long_edge": max_long_edge,
        "image_count": len(images),
        "successful_image_count": len(cold_durations),
        "expected_warm_requests": expected_warm_requests,
        "successful_warm_requests": len(warm_durations),
        "cold": cold_stats,
        "warm": warm_stats,
        "samples": sample_details,
        "budgets": {"cold_p95_ms": cold_budget, "warm_p95_ms": warm_budget},
        "budget_sources": {
            "cold_p95_ms": f"scripts/perf_budgets.toml[{kind}].cold_p95_ms",
            "warm_p95_ms": f"scripts/perf_budgets.toml[{kind}].warm_p95_ms",
        },
    }

    failures: list[str] = []
    if len(cold_durations) != len(images) or len(warm_durations) != expected_warm_requests:
        failures.append(
            f"workload contract cold={len(cold_durations)}/{len(images)}, "
            f"warm={len(warm_durations)}/{expected_warm_requests}"
        )
    response_sizes = [detail.get("cold_bytes", 0) for detail in sample_details if "cold_error" not in detail]
    response_sizes.extend(size for detail in sample_details for size in detail.get("warm_response_bytes", []))
    if len(response_sizes) != len(images) + expected_warm_requests or any(size <= 0 for size in response_sizes):
        failures.append("workload contract received an empty or missing response payload")
    if cold_stats["p95_ms"] > cold_budget:
        failures.append(f"cold p95 {cold_stats['p95_ms']}ms exceeds {cold_budget}ms")
    if warm_stats["p95_ms"] > warm_budget:
        failures.append(f"warm p95 {warm_stats['p95_ms']}ms exceeds {warm_budget}ms")

    report["contract_violations"] = failures
    report["verdict"] = "fail" if failures else "pass"
    for failure in failures:
        print(f"{kind} benchmark failed: {failure}", file=sys.stderr)
    print(emit_report(report))
    return 1 if failures else 0
