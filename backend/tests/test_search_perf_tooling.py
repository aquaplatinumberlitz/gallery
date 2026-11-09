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

from scripts import bench_related_assets, bench_search
from scripts.bench_search import SEARCH_COUNT_CLASSES, SEARCH_QUERY_CLASSES
from scripts.perf_manifest import expected_reports, load_perf_manifest
from scripts.summarize_perf_reports import summarize
from scripts.validate_perf_reports import validate_reports


def test_search_benchmark_covers_required_query_classes() -> None:
    assert {name for name, _query, _pages, _min_matches in SEARCH_QUERY_CLASSES} == {
        "broad_filename",
        "prompt_heavy",
        "album_heavy",
        "fielded",
        "fielded_model_only",
        "fielded_sampler_only",
        "mixed_short_token",
        "cjk",
        "short_cjk_two_char",
        "short_cjk_one_char",
        "short_cjk_mixed",
        "short_latin_prefix",
        "short_cjk_keyset_pages",
        "repeated_keyset_pages",
        "prefix_stability_2",
        "prefix_stability_3",
        "prefix_stability_4",
        "prefix_stability_keyset_pages",
        "accent_folded_latin",
        "accent_folded_vietnamese",
        "accent_folded_kana",
        "accent_folded_fielded_prompt",
        "accent_folded_fielded_two_char",
        "accent_folded_fielded_one_char",
        # BL-13: dense one-, two- and three-character queries and their keyset pages.
        "short_free_a",
        "short_free_m",
        "short_free_c",
        "short_free_a_keyset_pages",
        "short_free_m_keyset_pages",
        "short_free_c_keyset_pages",
        "short_fielded_prompt_c",
        "short_fielded_prompt_c_keyset_pages",
        "short_fielded_name_i",
        "short_fielded_name_a",
        "short_fielded_name_a_keyset_pages",
        "dense_two_char_filename",
        "dense_three_char_filename",
        "dense_three_char_model",
        "dense_three_char_prompt",
        "dense_three_char_keyset_pages",
    }
    cases = {name: (query, pages, min_matches) for name, query, pages, min_matches in SEARCH_QUERY_CLASSES}
    assert cases["short_cjk_two_char"] == ("少女", 1, 50)
    assert cases["short_cjk_keyset_pages"][1] >= 2
    assert cases["repeated_keyset_pages"][1] >= 2
    assert cases["repeated_keyset_pages"][2] >= 100
    assert cases["prompt_heavy"][0] == "blue forest prompt heavy constellation"
    assert cases["fielded_model_only"] == ("model:perf-model-3", 1, 50)
    assert cases["fielded_sampler_only"] == ('sampler:"Euler a"', 1, 50)
    assert cases["mixed_short_token"] == ("Euler a", 1, 50)
    for name in ("short_free_a", "short_free_m", "short_free_c", "short_fielded_prompt_c", "short_fielded_name_a"):
        assert cases[name][1:] == (1, 50), name
    for name in (
        "short_free_a_keyset_pages",
        "short_free_m_keyset_pages",
        "short_free_c_keyset_pages",
        "short_fielded_prompt_c_keyset_pages",
        "short_fielded_name_a_keyset_pages",
        "dense_three_char_keyset_pages",
    ):
        assert cases[name][1:] == (3, 150), name


def test_search_benchmark_covers_the_count_endpoint_for_dense_queries() -> None:
    assert {name for name, _query, _minimum in SEARCH_COUNT_CLASSES} == {
        "count_short_free_a",
        "count_short_free_m",
        "count_short_free_c",
        "count_short_fielded_prompt_c",
        "count_short_fielded_name_i",
        "count_short_fielded_name_a",
        "count_dense_three_char",
    }
    assert {query for _name, query, _minimum in SEARCH_COUNT_CLASSES} >= {"a", "m", "c", "prompt:c", "name:a"}


def test_ci_perf_manifest_declares_every_blocking_report() -> None:
    workloads = load_perf_manifest()
    assert {name for name, workload in workloads.items() if workload["suite"] == "ci"} == {
        "album_open",
        "facets",
        "inspector_api",
        "inspector_store",
        "lightbox",
        "preview",
        "related_assets",
        "search",
        "thumbnail",
    }
    assert expected_reports("ci") == [
        "album-open-report.json",
        "facets-report.json",
        "inspector-store-report.json",
        "library-inspector-report.json",
        "lightbox-open-report.json",
        "lightbox-transition-report.json",
        "preview-benchmark-report.json",
        "related-assets-benchmark-report.json",
        "search-benchmark-report.json",
        "thumbnail-benchmark-report.json",
    ]


def test_ci_perf_report_validation_fails_closed_on_missing_report(tmp_path: Path) -> None:
    assert validate_reports(tmp_path, "ci") == [
        f"missing expected ci report: {report}" for report in expected_reports("ci")
    ]
    for report in expected_reports("ci"):
        (tmp_path / report).write_text("{}", encoding="utf-8")
    assert validate_reports(tmp_path, "ci") == []


def test_mixed_short_workload_rejects_empty_responses(monkeypatch) -> None:
    monkeypatch.setattr(
        bench_search,
        "_get_json",
        lambda *_args, **_kwargs: (1.0, {"returned": 0, "albums": [], "next_cursor": None}),
    )

    result = bench_search.bench_search_case(
        "http://example.test",
        "mixed_short_token",
        "Euler a",
        iterations=1,
        min_matches_per_iteration=50,
    )

    assert result["contract_ok"] is False


def test_model_only_workload_rejects_cross_model_results(monkeypatch) -> None:
    monkeypatch.setattr(
        bench_search,
        "_get_json",
        lambda *_args, **_kwargs: (
            1.0,
            {
                "returned": 50,
                "albums": [],
                "next_cursor": None,
                "media": [{"model": "wrong-model", "sampler": "Euler a"}] * 50,
            },
        ),
    )

    result = bench_search.bench_search_case(
        "http://example.test",
        "fielded_model_only",
        "model:perf-model-3",
        iterations=1,
        min_matches_per_iteration=50,
    )

    assert result["unexpected_matches"] == 50
    assert result["contract_ok"] is False


def test_search_benchmark_fails_closed_on_short_cursor_chain(monkeypatch) -> None:
    monkeypatch.setattr(
        bench_search,
        "_get_json",
        lambda *_args, **_kwargs: (1.0, {"returned": 50, "albums": [], "next_cursor": None}),
    )

    result = bench_search.bench_search_case(
        "http://example.test",
        "repeated_keyset_pages",
        "search_asset_00",
        iterations=2,
        pages=3,
        min_matches_per_iteration=150,
    )

    assert result["requests"] == 2
    assert result["expected_requests"] == 6
    assert result["completed_page_chains"] == 0
    assert result["contract_ok"] is False


def test_perf_summary_checks_each_search_class(tmp_path: Path) -> None:
    report = {
        "search_classes": [
            {"class": "broad_filename", "p95_ms": 125.0, "contract_ok": True},
            {"class": "cjk", "p95_ms": 301.0, "contract_ok": False},
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
        ("search broad_filename workload contract", "pass"),
        ("search cjk p95", "fail"),
        ("search cjk workload contract", "fail"),
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
            "backfill_regression_pct": 20.0,
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


def _related_report(lexical: dict) -> dict:
    return {
        "fixture_rows": 100_000,
        "metadata": {"p95_ms": 40.0},
        "visual": {"p95_ms": 8.0},
        "combined": {"p95_ms": 120.0},
        "lexical_backfill": lexical,
        "visual_worker_rss_delta_mib": 1.0,
        "storage_mib": 90.0,
        "budgets": {
            "rows": 100_000,
            "metadata_p95_ms": 150.0,
            "visual_p95_ms": 75.0,
            "combined_p95_ms": 200.0,
            "lexical_p95_ms": 300.0,
            "backfill_regression_pct": 20.0,
            "backfill_regression_floor_ms": 15.0,
            "visual_worker_rss_mib": 64.0,
            "storage_mib": 100.0,
        },
    }


def _regression_status(tmp_path: Path, lexical: dict) -> str:
    (tmp_path / "related-assets-benchmark-report.json").write_text(
        json.dumps(_related_report(lexical)), encoding="utf-8"
    )
    checks = summarize(tmp_path)["reports"][0]["checks"]
    return next(check for check in checks if check["label"] == "lexical backfill regression")["status"]


def test_backfill_regression_needs_both_the_percentage_and_the_absolute_floor(tmp_path: Path) -> None:
    # CI after BL-13: an 11.3 ms baseline and 16.7 ms during backfill is 48% but only +5.4 ms.
    assert (
        _regression_status(tmp_path, {"during_p95_ms": 16.73, "regression_pct": 48.32, "regression_ms": 5.4}) == "pass"
    )
    # A real regression on a fast baseline: large percentage and above the floor.
    assert (
        _regression_status(tmp_path, {"during_p95_ms": 60.0, "regression_pct": 400.0, "regression_ms": 48.0}) == "fail"
    )
    # Above the floor but under the percentage budget (slow baseline).
    assert (
        _regression_status(tmp_path, {"during_p95_ms": 330.0, "regression_pct": 10.0, "regression_ms": 30.0}) == "pass"
    )
    # Old reports without regression_ms keep the percentage-only gate.
    assert _regression_status(tmp_path, {"during_p95_ms": 16.73, "regression_pct": 48.32}) == "fail"


def test_bench_backfill_gate_matches_the_summary_gate() -> None:
    budgets = {"backfill_regression_pct": 20, "backfill_regression_floor_ms": 15}
    assert (
        bench_related_assets.lexical_regression_failure({"regression_pct": 48.32, "regression_ms": 5.4}, budgets)
        is None
    )
    assert bench_related_assets.lexical_regression_failure({"regression_pct": 400.0, "regression_ms": 48.0}, budgets)
    assert (
        bench_related_assets.lexical_regression_failure({"regression_pct": 10.0, "regression_ms": 30.0}, budgets)
        is None
    )
    assert bench_related_assets.lexical_regression_failure({"regression_pct": 48.32}, budgets)


def test_count_workload_posts_the_canonical_request_and_rejects_low_totals(monkeypatch) -> None:
    posted: list[tuple[str, dict]] = []

    def fake_post(_base_url: str, path: str, body: dict) -> tuple[float, dict]:
        posted.append((path, body))
        return 2.0, {"total": 3, "has_more": True}

    monkeypatch.setattr(bench_search, "_post_json", fake_post)

    low = bench_search.bench_search_count_case("http://example.test", "count_short_free_a", "a", 2, 50)
    zero_ok = bench_search.bench_search_count_case("http://example.test", "count_short_fielded_name_i", "name:i", 2, 0)

    assert low["contract_ok"] is False
    assert zero_ok["contract_ok"] is True
    assert low["endpoint"] == "/api/search/count"
    assert posted[0][0] == "/api/search/count"
    assert posted[0][1]["text"] == "a"
    assert posted[0][1]["scope"] == {"kind": "all"}
    assert len(posted) == 4
