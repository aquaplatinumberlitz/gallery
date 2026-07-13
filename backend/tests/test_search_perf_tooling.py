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
