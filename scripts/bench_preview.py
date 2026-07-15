#!/usr/bin/env python3
"""Measure `/api/preview` cold generation and warm-cache latency.

Budget overrides: GALLERY_PERF_BENCH_PREVIEW_COLD_P95_MS and
GALLERY_PERF_BENCH_PREVIEW_WARM_P95_MS.
"""

from __future__ import annotations

from bench_derivative import run_derivative_benchmark


def main() -> int:
    """Run the managed preview derivative benchmark."""
    return run_derivative_benchmark(
        kind="preview",
        endpoint="/api/preview",
        default_folder="/home/ubuntu/gallery-repo/test-images/a1111",
        default_max_long_edge=1440,
    )


if __name__ == "__main__":
    raise SystemExit(main())
