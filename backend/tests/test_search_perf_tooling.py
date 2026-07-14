"""Managed search performance tooling contracts.

Purpose:
Lock the representative search benchmark classes and aggregate-report budget
interpretation used by the managed performance suite.

Guarantees:
The benchmark covers filename, prompt, album, fielded, CJK, and repeated
keyset-page workloads, and the report summarizer evaluates every class against
the lexical search p95 budget.

Run when:
Changing search perf fixtures, benchmark classes, budgets, or report summaries.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bench_search import SEARCH_QUERY_CLASSES
from scripts.summarize_perf_reports import summarize


def test_search_benchmark_covers_required_query_classes() -> None:
    assert {name for name, _query, _pages in SEARCH_QUERY_CLASSES} == {
        "broad_filename",
        "prompt_heavy",
        "album_heavy",
        "fielded",
        "cjk",
        "repeated_keyset_pages",
    }
    assert {name: pages for name, _query, pages in SEARCH_QUERY_CLASSES}["repeated_keyset_pages"] >= 2


def test_perf_summary_checks_each_search_class(tmp_path: Path) -> None:
    report = {
        "search_classes": [
            {"class": "broad_filename", "p95_ms": 125.0},
            {"class": "cjk", "p95_ms": 301.0},
        ],
        "inspector_metadata": {"p95_ms": 20.0},
        "budgets": {"search_p95_ms": 300.0, "inspector_metadata_p95_ms": 200.0},
    }
    (tmp_path / "search-benchmark-report.json").write_text(json.dumps(report), encoding="utf-8")

    summary = summarize(tmp_path)

    assert summary["overall_status"] == "fail"
    checks = summary["reports"][0]["checks"]
    assert [(check["label"], check["status"]) for check in checks] == [
        ("search broad_filename p95", "pass"),
        ("search cjk p95", "fail"),
        ("inspector metadata p95", "pass"),
    ]


def test_perf_summary_checks_related_assets_budgets(tmp_path: Path) -> None:
    report = {
        "fixture_rows": 100_000,
        "metadata": {"p95_ms": 140.0},
        "visual": {"p95_ms": 76.0},
        "combined": {"p95_ms": 190.0},
        "lexical_backfill": {"during_p95_ms": 250.0, "regression_pct": 4.0},
        "visual_worker_rss_delta_mib": 32.0,
        "storage_mib": 90.0,
        "budgets": {
            "rows": 100_000,
            "metadata_p95_ms": 150.0,
            "visual_p95_ms": 75.0,
            "combined_p95_ms": 200.0,
            "lexical_p95_ms": 300.0,
            "backfill_regression_pct": 10.0,
            "visual_worker_rss_mib": 64.0,
            "storage_mib": 100.0,
        },
    }
    (tmp_path / "related-assets-benchmark-report.json").write_text(json.dumps(report), encoding="utf-8")

    summary = summarize(tmp_path)

    assert summary["overall_status"] == "fail"
    checks = summary["reports"][0]["checks"]
    assert next(check for check in checks if check["label"] == "visual candidate p95")["status"] == "fail"
    assert next(check for check in checks if check["label"] == "fixture rows")["status"] == "pass"
