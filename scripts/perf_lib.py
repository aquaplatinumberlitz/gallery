"""Shared helpers for performance scripts.

Purpose:
* load perf budgets from a single TOML source of truth
* compute percentiles consistently across `perf_*.py` and `bench_*.py`
* provide a compact report schema used by every perf script

Guarantees:
* `load_budgets()` returns a plain dict mirroring `scripts/perf_budgets.toml`
* `percentile()` matches the linear-interpolation definition used by the
  Playwright perf specs (sub-ms accuracy, no nearest-rank jump)
* `summarize_samples()` returns min/p50/p95/max for any list of durations

Run when:
* writing or refactoring any perf script that needs budgets or stats
* validating that budget overrides come from the shared TOML
"""

from __future__ import annotations

import json
import math
import tomllib
from collections.abc import Iterable
from pathlib import Path
from statistics import median
from typing import Any


def load_budgets(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every perf budget from the shared TOML file.

    Defaults to `scripts/perf_budgets.toml` next to this module. Override
    `path` for tests or alternate configs. Returns the raw `tomllib` dict.
    """
    if path is None:
        path = Path(__file__).resolve().parent / "perf_budgets.toml"
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def percentile(values: Iterable[float], pct: float) -> float:
    """Linear-interpolation percentile (matches numpy/default-pandas semantics).

    Returns 0 for an empty input. Sub-millisecond accurate for time samples.
    """
    vals = list(values)
    if not vals:
        return 0.0
    ordered = sorted(vals)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (pct / 100.0) * (len(ordered) - 1)
    floor = math.floor(k)
    ceil = math.ceil(k)
    if floor == ceil:
        return float(ordered[int(k)])
    lower = ordered[floor] * (ceil - k)
    upper = ordered[ceil] * (k - floor)
    return float(lower + upper)


def summarize_samples(values: Iterable[float]) -> dict[str, float]:
    """Return min/p50/p95/max for a list of duration values in milliseconds."""
    vals = [float(v) for v in values]
    if not vals:
        return {"min_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0, "count": 0}
    return {
        "count": float(len(vals)),
        "min_ms": round(min(vals), 2),
        "p50_ms": round(median(vals), 2),
        "p95_ms": round(percentile(vals, 95), 2),
        "max_ms": round(max(vals), 2),
    }


def budget_for(section: str, field: str | None = None, path: str | Path | None = None) -> Any:
    """Fetch a single budget value (or the whole section) from the TOML."""
    budgets = load_budgets(path)
    if section not in budgets:
        raise KeyError(f"perf budget section '{section}' not declared in perf_budgets.toml")
    if field is None:
        return budgets[section]
    if field not in budgets[section]:
        raise KeyError(f"perf budget '{section}.{field}' not declared in perf_budgets.toml")
    return budgets[section][field]


def emit_report(report: dict[str, Any]) -> str:
    """Serialize a perf report dict to a compact, sorted JSON line."""
    return json.dumps(report, separators=(",", ":"), sort_keys=True)


def _self_check() -> int:
    """Module self-check: load budgets and print a summary. For `python perf_lib.py`."""
    budgets = load_budgets()
    print(json.dumps(budgets, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
