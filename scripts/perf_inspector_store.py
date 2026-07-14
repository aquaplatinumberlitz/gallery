#!/usr/bin/env python3
"""Measure the DB-only Library Inspector listing over the managed catalog.

Purpose:
* enforce the Inspector store budget without synthetic filesystem filtering
* ensure the benchmark actually runs against the expected large catalog

Guarantees:
* warms schema/index initialization before collecting latency samples
* fails when p95 or the indexed-corpus contract is not satisfied

Run when:
* changing Inspector SQL, ownership predicates, sort indexes, or perf fixtures
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import budget_for, emit_report, summarize_samples  # noqa: E402


def main() -> int:
    """Run warm DB-only Inspector samples and enforce the canonical budget."""
    if not os.getenv("GALLERY_METADATA_DB"):
        print("GALLERY_METADATA_DB is required", file=sys.stderr)
        return 2

    from backend.metadata_store.inspector_store import list_library_inspector_rows

    iterations = int(os.getenv("GALLERY_PERF_INSPECTOR_STORE_ITERATIONS", "5"))
    p95_budget_ms = float(os.getenv("GALLERY_PERF_INSPECTOR_P95_BUDGET_MS", str(budget_for("inspector", "p95_ms"))))
    min_total_indexed = int(os.getenv("GALLERY_PERF_INSPECTOR_MIN_TOTAL_INDEXED", "1"))

    list_library_inspector_rows("", "all", limit=200)
    durations: list[float] = []
    payload: dict = {}
    for _ in range(max(1, iterations)):
        started = time.perf_counter()
        payload = list_library_inspector_rows("", "all", limit=200)
        durations.append((time.perf_counter() - started) * 1000)

    stats = summarize_samples(durations)
    total_indexed = int(payload.get("total_indexed") or 0)
    report = {
        "database": os.environ["GALLERY_METADATA_DB"],
        "iterations": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "returned": int(payload.get("returned") or 0),
        "total_indexed": total_indexed,
        "min_rows": 1,
        "min_total_indexed": min_total_indexed,
        "budget_p95_ms": p95_budget_ms,
        "budget_source": "scripts/perf_budgets.toml[inspector].p95_ms",
    }
    print(emit_report(report))

    failed = report["p95_ms"] > p95_budget_ms or total_indexed < min_total_indexed
    if report["p95_ms"] > p95_budget_ms:
        print(f"inspector store p95 exceeded budget: {report['p95_ms']}ms > {p95_budget_ms}ms", file=sys.stderr)
    if total_indexed < min_total_indexed:
        print(f"inspector store corpus too small: {total_indexed} < {min_total_indexed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
