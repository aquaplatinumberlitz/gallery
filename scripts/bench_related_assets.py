#!/usr/bin/env python3
"""Benchmark 100k Related Assets requests, storage, and worker overhead.

Purpose:
Measure metadata-only, visual, combined, lexical-under-backfill, storage, and
Pillow worker memory budgets on the managed precomputed relation fixture.

Guarantees:
* every request uses the public version-1 Related Assets API
* the fixture contains no 100k image-file expansion or request-time decoding
* all R5 latency, lexical-regression, RSS, and SQLite growth budgets fail closed

Run when:
* changing related candidate SQL, fingerprints, signatures, fixture scale, or
  the shared performance budget registry
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import budget_for, emit_report, summarize_samples  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
RELATION_TABLES = (
    "asset_generation_signatures",
    "asset_visual_fingerprints",
    "asset_visual_hash_bands",
    "asset_search_extractions",
)


def _request_json(request: Request) -> tuple[float, dict]:
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, payload


def _post_json(base_url: str, path: str, payload: dict) -> tuple[float, dict]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    return _request_json(request)


def _get_json(base_url: str, path: str, params: dict[str, str]) -> tuple[float, dict]:
    request = Request(
        f"{base_url.rstrip('/')}{path}?{urlencode(params)}",
        headers={"Accept": "application/json"},
    )
    return _request_json(request)


def _related_request(reference_asset_id: int, library_id: int, profile: str) -> dict:
    return {
        "schema_version": 1,
        "reference_asset_id": reference_asset_id,
        "profile": profile,
        "scope": {"kind": "library", "library_id": library_id},
        "limit": 60,
    }


def bench_related_profile(
    base_url: str,
    reference_asset_id: int,
    library_id: int,
    profile: str,
    *,
    iterations: int,
) -> dict:
    """Warm and benchmark one public relation profile."""
    request = _related_request(reference_asset_id, library_id, profile)
    for _ in range(2):
        _post_json(base_url, "/api/search/related", request)
    durations: list[float] = []
    last_payload: dict = {}
    for _ in range(max(1, iterations)):
        duration, last_payload = _post_json(base_url, "/api/search/related", request)
        durations.append(duration)
    stats = summarize_samples(durations)
    return {
        "profile": profile,
        "requests": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "returned": int(last_payload.get("returned") or 0),
        "asset_ids": [int(item["asset_id"]) for item in last_payload.get("items", [])],
    }


def bench_visual_candidates(
    reference_asset_id: int,
    library_id: int,
    *,
    iterations: int,
) -> dict:
    """Benchmark persisted hash-band retrieval without HTTP or image decode."""
    from backend.search_scope import SearchScopeContext
    from backend.visual_fingerprints import query_visual_variants

    context = SearchScopeContext(kind="library", library_id=library_id, library_name="Related perf fixture")
    for _ in range(2):
        query_visual_variants(reference_asset_id, context, limit=60)
    durations: list[float] = []
    last_items = []
    for _ in range(max(1, iterations)):
        started = time.perf_counter()
        last_items = query_visual_variants(reference_asset_id, context, limit=60)
        durations.append((time.perf_counter() - started) * 1000)
    stats = summarize_samples(durations)
    return {
        "profile": "visual-candidates",
        "requests": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "returned": len(last_items),
        "asset_ids": [item.asset_id for item in last_items],
    }


def bench_metadata_candidates(
    reference_asset_id: int,
    library_id: int,
    *,
    iterations: int,
) -> dict:
    """Benchmark metadata relation ranking without visual work or HTTP overhead."""
    from backend.related_ranking import rank_related_metadata
    from backend.search_scope import SearchScopeContext

    context = SearchScopeContext(kind="library", library_id=library_id, library_name="Related perf fixture")
    for _ in range(2):
        rank_related_metadata(reference_asset_id, context, profile="related", limit=60)
    durations: list[float] = []
    last_items = []
    for _ in range(max(1, iterations)):
        started = time.perf_counter()
        last_items = rank_related_metadata(reference_asset_id, context, profile="related", limit=60)
        durations.append((time.perf_counter() - started) * 1000)
    stats = summarize_samples(durations)
    return {
        "profile": "metadata-candidates",
        "requests": int(stats["count"]),
        "min_ms": stats["min_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "max_ms": stats["max_ms"],
        "returned": len(last_items),
        "asset_ids": [item.asset_id for item in last_items],
    }


def _lexical_samples(base_url: str, iterations: int) -> dict[str, float]:
    for _ in range(3):
        _get_json(base_url, "/api/search", {"q": "search_asset_000", "scope": "all", "limit": "50"})
    durations = [
        _get_json(base_url, "/api/search", {"q": "search_asset_000", "scope": "all", "limit": "50"})[0]
        for _ in range(max(1, iterations))
    ]
    return summarize_samples(durations)


def _backfill_writer(db_path: Path, stop: threading.Event, stats: dict[str, int]) -> None:
    connection = sqlite3.connect(db_path, timeout=30)
    try:
        row = connection.execute("SELECT min(asset_id), max(asset_id) FROM asset_generation_signatures").fetchone()
        lower, upper = int(row[0] or 0), int(row[1] or 0)
        cursor = lower
        while not stop.is_set() and cursor <= upper:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE asset_generation_signatures
                SET indexed_at = indexed_at + 0.000001
                WHERE asset_id BETWEEN ? AND ?
                """,
                (cursor, min(cursor + 199, upper)),
            )
            connection.execute(
                """
                UPDATE asset_visual_fingerprints
                SET indexed_at = indexed_at + 0.000001
                WHERE asset_id BETWEEN ? AND ?
                """,
                (cursor, min(cursor + 199, upper)),
            )
            connection.execute(
                """
                UPDATE asset_visual_hash_bands
                SET band_value = band_value
                WHERE asset_id BETWEEN ? AND ?
                """,
                (cursor, min(cursor + 199, upper)),
            )
            connection.execute(
                """
                UPDATE asset_search_extractions
                SET indexed_at = indexed_at + 0.000001
                WHERE asset_id BETWEEN ? AND ?
                  AND index_name IN ('generation_signatures', 'visual_fingerprints')
                """,
                (cursor, min(cursor + 199, upper)),
            )
            connection.commit()
            stats["batches"] = stats.get("batches", 0) + 1
            stats["assets"] = stats.get("assets", 0) + min(200, upper - cursor + 1)
            cursor += 200
            time.sleep(0.004)
    finally:
        connection.close()


def bench_lexical_backfill(base_url: str, db_path: Path, *, iterations: int) -> dict:
    """Compare lexical p95 before/during/after bounded relation writes."""
    before = _lexical_samples(base_url, iterations)
    stop = threading.Event()
    writer_stats: dict[str, int] = {}
    writer = threading.Thread(target=_backfill_writer, args=(db_path, stop, writer_stats), daemon=True)
    writer.start()
    during = _lexical_samples(base_url, iterations)
    stop.set()
    writer.join(timeout=30)
    after = _lexical_samples(base_url, iterations)
    baseline_p95 = max(float(before["p95_ms"]), float(after["p95_ms"]))
    regression_pct = max(0.0, (float(during["p95_ms"]) - baseline_p95) / max(baseline_p95, 0.01) * 100)
    return {
        "before": before,
        "during": during,
        "after": after,
        "baseline_p95_ms": round(baseline_p95, 2),
        "during_p95_ms": during["p95_ms"],
        "regression_pct": round(regression_pct, 2),
        "writer": writer_stats,
    }


def relation_storage_mib(db_path: Path) -> float:
    """Measure relation table and index pages through SQLite dbstat."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        table_placeholders = ",".join("?" for _ in RELATION_TABLES)
        names = {
            str(row[0])
            for row in connection.execute(
                f"""
                SELECT name FROM sqlite_master
                WHERE type IN ('table', 'index')
                  AND (tbl_name IN ({table_placeholders}) OR name IN ({table_placeholders}))
                """,
                (*RELATION_TABLES, *RELATION_TABLES),
            )
        }
        placeholders = ",".join("?" for _ in names)
        total = connection.execute(
            f"SELECT coalesce(sum(pgsize), 0) FROM dbstat WHERE name IN ({placeholders})",
            tuple(sorted(names)),
        ).fetchone()[0]
    finally:
        connection.close()
    return round(int(total or 0) / (1024 * 1024), 2)


def validate_fixture_contract(db_path: Path, reference_asset_id: int) -> dict[str, int]:
    """Fail closed unless all persisted relation-owned rows exist at matching scale."""
    connection = sqlite3.connect(db_path)
    try:
        reference_path = Path(
            str(connection.execute("SELECT path FROM assets WHERE id = ?", (reference_asset_id,)).fetchone()[0])
        )
        synthetic_root = reference_path.parents[1]
        fixture_prefix = f"{synthetic_root}{os.sep}%"
        signatures = int(
            connection.execute(
                """
                SELECT count(*) FROM asset_generation_signatures AS signature
                JOIN assets AS asset ON asset.id = signature.asset_id
                WHERE asset.path LIKE ?
                """,
                (fixture_prefix,),
            ).fetchone()[0]
        )
        fingerprints = int(
            connection.execute(
                """
                SELECT count(*) FROM asset_visual_fingerprints AS fingerprint
                JOIN assets AS asset ON asset.id = fingerprint.asset_id
                WHERE asset.path LIKE ?
                """,
                (fixture_prefix,),
            ).fetchone()[0]
        )
        bands = int(
            connection.execute(
                """
                SELECT count(*) FROM asset_visual_hash_bands AS band
                JOIN assets AS asset ON asset.id = band.asset_id
                WHERE asset.path LIKE ?
                """,
                (fixture_prefix,),
            ).fetchone()[0]
        )
        extractions = int(
            connection.execute(
                """
                SELECT count(*) FROM asset_search_extractions AS extraction
                JOIN assets AS asset ON asset.id = extraction.asset_id
                WHERE extraction.index_name IN ('generation_signatures', 'visual_fingerprints')
                  AND asset.path LIKE ?
                """,
                (fixture_prefix,),
            ).fetchone()[0]
        )
        reference_rows = int(
            connection.execute(
                """
                SELECT
                  EXISTS(SELECT 1 FROM asset_generation_signatures WHERE asset_id = ?)
                  + EXISTS(SELECT 1 FROM asset_visual_fingerprints WHERE asset_id = ?)
                """,
                (reference_asset_id, reference_asset_id),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return {
        "rows": min(signatures, fingerprints),
        "generation_signatures": signatures,
        "visual_fingerprints": fingerprints,
        "visual_hash_bands": bands,
        "search_extractions": extractions,
        "reference_components": reference_rows,
    }


def visual_worker_rss_delta_mib(image_path: Path) -> float:
    """Measure incremental RSS after Pillow fingerprint work in a fresh worker."""
    code = """
import json, resource, sys
import backend.config
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
from backend.visual_fingerprints import compute_visual_fingerprint
for _ in range(12):
    compute_visual_fingerprint(sys.argv[1])
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"delta_mib": max(0, after - before) / 1024}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(image_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return round(float(json.loads(result.stdout)["delta_mib"]), 2)


def _reference_ids(db_path: Path, configured_reference: int) -> tuple[int, int, int | None]:
    connection = sqlite3.connect(db_path)
    try:
        reference = configured_reference or int(
            connection.execute("SELECT asset_id FROM asset_generation_signatures ORDER BY asset_id LIMIT 1").fetchone()[
                0
            ]
        )
        library_id = int(connection.execute("SELECT library_id FROM assets WHERE id = ?", (reference,)).fetchone()[0])
        unrelated = connection.execute("SELECT id FROM assets WHERE name = 'search_asset_00151.png' LIMIT 1").fetchone()
    finally:
        connection.close()
    return reference, library_id, int(unrelated[0]) if unrelated is not None else None


def main() -> int:
    """Run all Related Assets performance budgets and emit one report."""
    base_url = os.getenv("GALLERY_API_BASE_URL", "http://localhost:4701")
    db_path = Path(os.environ["GALLERY_METADATA_DB"])
    configured_fixture_rows = int(os.getenv("GALLERY_PERF_RELATED_ROWS", "0"))
    configured_reference = int(os.getenv("GALLERY_PERF_RELATED_REFERENCE_ASSET_ID", "0"))
    iterations = int(os.getenv("GALLERY_PERF_RELATED_ITERATIONS", "12"))
    reference_asset_id, library_id, same_model_unrelated_id = _reference_ids(db_path, configured_reference)
    fixture_contract = validate_fixture_contract(db_path, reference_asset_id)
    fixture_rows = int(fixture_contract["rows"])

    metadata = bench_metadata_candidates(reference_asset_id, library_id, iterations=iterations)
    visual = bench_visual_candidates(reference_asset_id, library_id, iterations=iterations)
    combined = bench_related_profile(base_url, reference_asset_id, library_id, "related", iterations=iterations)
    lexical = bench_lexical_backfill(base_url, db_path, iterations=iterations)
    storage_mib = relation_storage_mib(db_path)
    album_path = Path(os.environ["GALLERY_PERF_ALBUM_PATH"])
    image_path = next(iter(sorted(album_path.glob("*.png"))))
    rss_mib = visual_worker_rss_delta_mib(image_path)

    budgets = budget_for("related_assets")
    report = {
        "fixture_rows": fixture_rows,
        "configured_fixture_rows": configured_fixture_rows,
        "fixture_contract": fixture_contract,
        "reference_asset_id": reference_asset_id,
        "metadata": metadata,
        "visual": visual,
        "combined": combined,
        "lexical_backfill": lexical,
        "storage_mib": storage_mib,
        "visual_worker_rss_delta_mib": rss_mib,
        "budgets": budgets,
        "budget_source": "scripts/perf_budgets.toml[related_assets]",
    }
    print(emit_report(report))

    failures: list[str] = []
    if fixture_rows < int(budgets["rows"]):
        failures.append(f"fixture rows {fixture_rows} < {int(budgets['rows'])}")
    if configured_fixture_rows != fixture_rows:
        failures.append(f"configured fixture rows {configured_fixture_rows} != persisted rows {fixture_rows}")
    if fixture_contract["visual_hash_bands"] != fixture_rows * 8:
        failures.append("visual hash-band fixture is incomplete")
    if fixture_contract["search_extractions"] != fixture_rows * 2:
        failures.append("search extraction fixture is incomplete")
    if fixture_contract["reference_components"] != 2:
        failures.append("reference asset is missing a persisted relation component")
    for label, value, budget_key in (
        ("metadata related p95", metadata["p95_ms"], "metadata_p95_ms"),
        ("visual candidate p95", visual["p95_ms"], "visual_p95_ms"),
        ("combined related p95", combined["p95_ms"], "combined_p95_ms"),
        ("lexical p95", lexical["during_p95_ms"], "lexical_p95_ms"),
    ):
        if float(value) > float(budgets[budget_key]):
            failures.append(f"{label} {value}ms > {budgets[budget_key]}ms")
    if float(lexical["regression_pct"]) >= float(budgets["backfill_regression_pct"]):
        failures.append(
            f"lexical backfill regression {lexical['regression_pct']}% >= {budgets['backfill_regression_pct']}%"
        )
    if int(lexical["writer"].get("batches", 0)) == 0:
        failures.append("relation backfill writer performed no batches")
    if rss_mib >= float(budgets["visual_worker_rss_mib"]):
        failures.append(f"visual worker RSS {rss_mib}MiB >= {budgets['visual_worker_rss_mib']}MiB")
    if storage_mib >= float(budgets["storage_mib"]):
        failures.append(f"relation storage {storage_mib}MiB >= {budgets['storage_mib']}MiB")
    if metadata["returned"] == 0 or visual["returned"] == 0 or combined["returned"] == 0:
        failures.append("one or more related profiles returned no controlled neighbors")
    if same_model_unrelated_id is not None and same_model_unrelated_id in combined["asset_ids"]:
        failures.append("unrelated same-model fixture asset leaked into combined results")

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
