"""Related Assets managed performance fixture and budget contracts.

Purpose:
Lock the 100k precomputed fixture groups, visual neighbors, shared budget
registry, and aggregate report coverage without generating 100k files in unit
tests.

Guarantees:
The reference has exact/recipe/family, prompt-overlap, unrelated same-model,
and visual neighbor cohorts; all R5 budgets are declared at 100k scale.

Run when:
Changing the Related Assets performance fixture, benchmark script, budget
registry, or report summary.
"""

from __future__ import annotations

from scripts.create_perf_fixture import _synthetic_search_values, _visual_bytes
from scripts.perf_lib import budget_for


def _distance(left: bytes, right: bytes) -> int:
    return (int.from_bytes(left, "big") ^ int.from_bytes(right, "big")).bit_count()


def test_related_fixture_groups_are_deterministic_and_nonsemantic() -> None:
    reference = _synthetic_search_values(0)
    exact = _synthetic_search_values(20)
    recipe_seed_change = _synthetic_search_values(40)
    family_recipe_change = _synthetic_search_values(80)
    prompt_overlap = _synthetic_search_values(120)
    same_model_unrelated = _synthetic_search_values(200)

    assert exact["seed"] == reference["seed"]
    assert recipe_seed_change["seed"] != reference["seed"]
    assert recipe_seed_change["sampler"] == reference["sampler"]
    assert family_recipe_change["sampler"] != reference["sampler"]
    assert "cobalt fox" in str(prompt_overlap["prompt"])
    assert same_model_unrelated["model"] == reference["model"]
    assert "cobalt fox" not in str(same_model_unrelated["prompt"])


def test_related_visual_fixture_has_controlled_neighbors_and_limits() -> None:
    reference_h = _visual_bytes(0, "h")
    reference_v = _visual_bytes(0, "v")
    assert _distance(reference_h, _visual_bytes(20, "h")) == 0
    assert _distance(reference_v, _visual_bytes(20, "v")) == 0
    assert _distance(reference_h, _visual_bytes(70, "h")) == 1
    assert _distance(reference_v, _visual_bytes(70, "v")) == 1
    assert _distance(reference_h, _visual_bytes(90, "h")) == 4
    assert _distance(reference_v, _visual_bytes(90, "v")) == 4
    assert _distance(reference_h, _visual_bytes(900, "h")) + _distance(reference_v, _visual_bytes(900, "v")) > 16


def test_related_performance_budgets_lock_100k_plan_limits() -> None:
    budgets = budget_for("related_assets")
    assert budgets == {
        "rows": 100_000,
        "metadata_p95_ms": 150,
        "visual_p95_ms": 75,
        "combined_p95_ms": 200,
        "lexical_p95_ms": 300,
        "backfill_regression_pct": 10,
        "visual_worker_rss_mib": 64,
        "storage_mib": 100,
        "description": "100k Related Assets latency, lexical isolation, worker RSS, and SQLite growth",
    }
