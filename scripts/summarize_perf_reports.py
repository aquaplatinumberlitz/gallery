#!/usr/bin/env python3
"""Summarize generated performance JSON reports.

Purpose:
Aggregate frontend and backend perf report JSON files into one summary.

Guarantees:
* reads perf report files from the configured results directory
* writes machine-readable JSON and human-readable Markdown summaries
* preserves per-report budget pass/fail status when budgets are present

Run when:
* after perf smoke tests complete
* comparing perf results across branches, releases, or fixture sizes
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any


def _status_for(value: float | int | None, budget: float | int | None, *, lower_is_better: bool = True) -> str:
    if value is None or budget is None:
        return "info"
    if lower_is_better:
        return "pass" if value <= budget else "fail"
    return "pass" if value >= budget else "fail"


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and math.isfinite(value):
        return value
    return None


def _check(label: str, value: Any, budget: Any = None, unit: str = "ms", *, lower_is_better: bool = True) -> dict:
    numeric_value = _number(value)
    numeric_budget = _number(budget)
    return {
        "label": label,
        "value": numeric_value,
        "budget": numeric_budget,
        "unit": unit,
        "status": _status_for(numeric_value, numeric_budget, lower_is_better=lower_is_better),
    }


def _checks_for_report(name: str, data: dict[str, Any]) -> list[dict]:
    checks: list[dict] = []

    if "scan" in data and "thumbnails" in data:
        budgets = data.get("budgets", {})
        scan = data.get("scan", {})
        thumbnails = data.get("thumbnails", {})
        checks.extend(
            [
                _check("scan duration", scan.get("durationMs"), budgets.get("scanBudgetMs")),
                _check(
                    "first thumbnail start", thumbnails.get("firstStartAfterClickMs"), budgets.get("firstThumbBudgetMs")
                ),
                _check("thumbnail p95", thumbnails.get("p95Ms"), budgets.get("thumbP95BudgetMs")),
            ]
        )
    elif "open" in data:
        budgets = data.get("budgets", {})
        open_report = data.get("open", {})
        checks.extend(
            [
                _check(
                    "lightbox visible", open_report.get("lightboxVisibleAfterClickMs"), budgets.get("openVisibleMs")
                ),
                _check(
                    "preview loaded",
                    open_report.get("lightboxPreviewLoadedAfterClickMs"),
                    budgets.get("openPreviewLoadedMs"),
                ),
            ]
        )
    elif "transition" in data:
        budgets = data.get("budgets", {})
        transition = data.get("transition", {})
        checks.append(
            _check(
                "transition preview loaded",
                transition.get("transitionPreviewLoadedAfterActionMs"),
                budgets.get("transitionMs"),
            )
        )
    elif "metadataNavigation" in data:
        report = data.get("metadataNavigation", {})
        budgets = report.get("budgets", {})
        checks.extend(
            [
                _check("metadata API", report.get("apiDurationMs"), budgets.get("apiMs")),
                _check("table ready", report.get("clickToTableReadyMs"), budgets.get("tableReadyMs")),
                _check(
                    "API response to first row", report.get("apiResponseToFirstRowMs"), budgets.get("responseRenderMs")
                ),
                _check("rendered rows", report.get("renderedRows"), budgets.get("renderedRowsMax"), "rows"),
            ]
        )
    elif "sort" in data:
        report = data.get("sort", {})
        budgets = report.get("budgets", {})
        checks.extend(
            [
                _check("sort API", report.get("apiDurationMs"), budgets.get("apiMs")),
                _check("sort total", report.get("totalMs"), budgets.get("totalMs")),
                _check("sort response to update", report.get("apiResponseToUpdateMs"), budgets.get("responseRenderMs")),
                _check("rendered rows", report.get("renderedRows"), budgets.get("renderedRowsMax"), "rows"),
            ]
        )
    elif all(key in data for key in ("metadata", "visual", "combined", "lexical_backfill")):
        budgets = data.get("budgets", {})
        checks.extend(
            [
                _check("metadata related p95", data["metadata"].get("p95_ms"), budgets.get("metadata_p95_ms")),
                _check("visual candidate p95", data["visual"].get("p95_ms"), budgets.get("visual_p95_ms")),
                _check("combined related p95", data["combined"].get("p95_ms"), budgets.get("combined_p95_ms")),
                _check(
                    "lexical during backfill p95",
                    data["lexical_backfill"].get("during_p95_ms"),
                    budgets.get("lexical_p95_ms"),
                ),
                _check(
                    "lexical backfill regression",
                    data["lexical_backfill"].get("regression_pct"),
                    budgets.get("backfill_regression_pct"),
                    "%",
                ),
                _check(
                    "visual worker RSS",
                    data.get("visual_worker_rss_delta_mib"),
                    budgets.get("visual_worker_rss_mib"),
                    "MiB",
                ),
                _check("relation storage", data.get("storage_mib"), budgets.get("storage_mib"), "MiB"),
                _check("fixture rows", data.get("fixture_rows"), budgets.get("rows"), "rows", lower_is_better=False),
            ]
        )
    elif "search_classes" in data:
        budgets = data.get("budgets", {})
        for report in data.get("search_classes", []):
            checks.extend(
                [
                    _check(
                        f"search {report.get('class', 'unknown')} p95",
                        report.get("p95_ms"),
                        budgets.get("search_p95_ms"),
                    ),
                    _check(
                        f"search {report.get('class', 'unknown')} workload contract",
                        1 if report.get("contract_ok") is True else 0,
                        1,
                        "boolean",
                        lower_is_better=False,
                    ),
                ]
            )
        inspector = data.get("inspector_metadata") or {}
        if "p95_ms" in inspector:
            checks.append(
                _check(
                    "inspector metadata p95",
                    inspector.get("p95_ms"),
                    budgets.get("inspector_metadata_p95_ms"),
                )
            )
    elif "search" in data:
        report = data.get("search", {})
        budgets = report.get("budgets", {})
        checks.extend(
            [
                _check("search API", report.get("finalApiDurationMs"), budgets.get("apiMs")),
                _check("search total", report.get("totalMs"), budgets.get("totalMs")),
                _check(
                    "search response to update", report.get("finalResponseToUpdateMs"), budgets.get("responseRenderMs")
                ),
                _check("search requests", report.get("requestsWhileTyping"), budgets.get("requestsMax"), "requests"),
                _check("rendered rows", report.get("renderedRows"), budgets.get("renderedRowsMax"), "rows"),
            ]
        )
    elif "p95_ms" in data and "budget_p95_ms" in data:
        label = "p95"
        if "inspector" in name:
            label = "inspector p95"
        elif "scan" in name:
            label = "scan p95"
        checks.append(_check(label, data.get("p95_ms"), data.get("budget_p95_ms")))
        if "returned" in data:
            checks.append(
                _check("returned rows", data.get("returned"), data.get("min_rows"), "rows", lower_is_better=False)
            )
        if "image_count" in data:
            checks.append(
                _check(
                    "returned images", data.get("image_count"), data.get("min_images"), "images", lower_is_better=False
                )
            )
    elif "warm" in data:
        warm = data.get("warm") or {}
        checks.append(_check("warm listing", warm.get("duration_ms"), data.get("budget_ms")))

    return checks


def _report_status(data: dict[str, Any], checks: list[dict]) -> str:
    if data.get("verdict") == "fail":
        return "fail"
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if checks:
        return "pass" if any(check["status"] == "pass" for check in checks) else "info"
    return str(data.get("verdict") or "info")


def _format_metric(check: dict) -> str:
    value = check["value"]
    budget = check["budget"]
    unit = check["unit"]
    suffix = f" {unit}" if unit in {"rows", "requests", "images"} else unit
    if value is None:
        return f"{check['label']}: n/a"
    if budget is None:
        return f"{check['label']}: {value:g}{suffix}"
    comparator = "<=" if check["label"] not in {"returned rows", "returned images"} else ">="
    return f"{check['label']}: {value:g}{suffix} {comparator} {budget:g}{suffix}"


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Perf Summary",
        "",
        f"Generated at: `{summary['generated_at']}`",
        "",
        f"Overall status: **{summary['overall_status']}**",
        "",
        "| Report | Status | Metrics |",
        "| --- | --- | --- |",
    ]
    for report in summary["reports"]:
        metrics = "<br>".join(_format_metric(check) for check in report["checks"]) or "n/a"
        lines.append(f"| `{report['file']}` | **{report['status']}** | {metrics} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(results_dir: Path) -> dict[str, Any]:
    """Aggregate performance report files into one summary."""
    reports: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        if path.name in {"perf-summary.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            reports.append({"file": path.name, "status": "error", "error": str(exc), "checks": []})
            continue
        if not isinstance(data, dict):
            reports.append(
                {"file": path.name, "status": "error", "error": "report root is not an object", "checks": []}
            )
            continue
        checks = _checks_for_report(path.name, data)
        reports.append({"file": path.name, "status": _report_status(data, checks), "checks": checks})

    fail_count = sum(1 for report in reports if report["status"] in {"fail", "error"})
    pass_count = sum(1 for report in reports if report["status"] == "pass")
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results_dir": str(results_dir),
        "overall_status": "fail" if fail_count else "pass" if pass_count else "info",
        "total_reports": len(reports),
        "passed": pass_count,
        "failed": fail_count,
        "reports": reports,
    }


def main() -> int:
    """Write JSON and Markdown summaries for performance reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", default="frontend/test-results/perf", help="directory containing perf JSON reports"
    )
    parser.add_argument("--output", default="", help="summary JSON output path")
    parser.add_argument("--markdown-output", default="", help="summary Markdown output path")
    parser.add_argument("--fail-on-regression", action="store_true", help="exit non-zero when any report fails")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(results_dir)

    output = Path(args.output).resolve() if args.output else results_dir / "perf-summary.json"
    markdown_output = Path(args.markdown_output).resolve() if args.markdown_output else results_dir / "perf-summary.md"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(markdown_output, summary)

    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    print(f"Perf summary written to {output}")
    print(f"Perf markdown summary written to {markdown_output}")
    return 1 if args.fail_on_regression and summary["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
