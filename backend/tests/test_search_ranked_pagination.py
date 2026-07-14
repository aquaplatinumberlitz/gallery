"""Unified search relevance and opaque keyset pagination regressions.

Purpose:
Lock the tiered relevance order and request-bound keyset cursor contract used
by the active gallery search stream.

Guarantees:
* exact filenames and prompt phrases follow the documented tier order
* equal-score rows use mtime_ns then asset_id for deterministic ordering
* opaque pages have no duplicates/omissions and reject incompatible cursors
* insertion/deletion between pages cannot repeat an already returned asset
* decimal GET cursors remain a deprecated offset-only compatibility input
* the active keyset SQL contains no OFFSET clause

Run when:
* changing search ranking, candidate CTEs, cursor encoding/fingerprints,
  pagination ordering, or the legacy GET search adapter
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.metadata_store import _connect, index_file, register_library, search_index, upsert_metadata_result
from backend.metadata_store.ranked_search import (
    _candidate_selects,
    build_candidate_page_query,
    decode_search_cursor,
    request_fingerprint,
)

from .conftest import create_test_png


def _seed_search_image(
    root: Path,
    name: str,
    *,
    prompt: str = "",
    negative_prompt: str = "",
    mtime_ns: int = 1_760_000_000_000_000_000,
) -> dict[str, int | str]:
    image = root / name
    create_test_png(image)
    os.utime(image, ns=(mtime_ns, mtime_ns))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    if prompt or negative_prompt:
        assert upsert_metadata_result(
            image,
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": 64,
                "height": 64,
            },
        )
    with _connect() as conn:
        row = conn.execute("SELECT id FROM assets WHERE path = ?", (str(image.resolve()),)).fetchone()
    return {"asset_id": int(row["id"]), "path": str(image.resolve())}


def test_strong_prompt_phrase_outranks_weak_filename_match(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Ranking")
    filename = _seed_search_image(isolated_gallery_root, "notes blue hair weak.png")
    prompt = _seed_search_image(
        isolated_gallery_root,
        "unrelated.png",
        prompt="portrait, blue hair, studio light",
    )

    result = search_index("blue hair", "all", limit=10)
    assert [row["asset_id"] for row in result["media"][:2]] == [prompt["asset_id"], filename["asset_id"]]
    assert result["media"][0]["match_type"] == "prompt_phrase"


def test_trigram_metadata_candidates_preserve_noncontiguous_token_and_semantics(
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Token AND")
    matched = _seed_search_image(
        isolated_gallery_root,
        "noncontiguous.png",
        prompt="blue atmospheric forest with distant constellation",
    )

    result = search_index("blue constellation", "all", limit=10)

    assert [row["asset_id"] for row in result["media"]] == [matched["asset_id"]]


def test_mixed_length_cjk_tokens_preserve_noncontiguous_and_semantics(
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="CJK Token AND")
    separated = _seed_search_image(
        isolated_gallery_root,
        "separated.png",
        prompt="星空 atmospheric 猫 distant 風景",
    )
    phrase = _seed_search_image(isolated_gallery_root, "phrase.png", prompt="星空 猫 風景")

    result = search_index("星空 猫 風景", "all", limit=10)

    assert {row["asset_id"] for row in result["media"]} == {separated["asset_id"], phrase["asset_id"]}


def test_exact_filename_is_first_relevance_tier(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Exact")
    exact = _seed_search_image(isolated_gallery_root, "target.png")
    _seed_search_image(isolated_gallery_root, "other.png", prompt="target.png in prompt")

    result = search_index("target.png", "all", limit=10)
    assert result["media"][0]["asset_id"] == exact["asset_id"]
    assert result["media"][0]["match_type"] == "filename_exact"


def test_fts_candidates_do_not_hide_filename_substring_matches(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Substring union")
    exact = _seed_search_image(isolated_gallery_root, "auditunionneedle.png")
    substring = _seed_search_image(isolated_gallery_root, "xxauditunionneedle.png")

    result = search_index("auditunionneedle", "all", limit=10)

    assert [row["asset_id"] for row in result["media"]] == [exact["asset_id"], substring["asset_id"]]
    assert result["media"][1]["match_type"] == "filename"


def test_legacy_photo_file_index_type_is_normalized_in_response(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Photo normalization")
    seeded = _seed_search_image(isolated_gallery_root, "legacy_photo.png")
    with _connect() as conn:
        conn.execute("UPDATE file_index SET type = 'photo' WHERE path = ?", (seeded["path"],))

    result = search_index("legacy_photo", "all", limit=10)

    assert result["media"][0]["type"] == "image"


def test_equal_score_rows_order_by_mtime_then_asset_id(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Ties")
    older = _seed_search_image(
        isolated_gallery_root,
        "tie_c.png",
        mtime_ns=1_760_000_000_000_000_000,
    )
    newer_a = _seed_search_image(
        isolated_gallery_root,
        "tie_a.png",
        mtime_ns=1_760_000_100_000_000_000,
    )
    newer_b = _seed_search_image(
        isolated_gallery_root,
        "tie_b.png",
        mtime_ns=1_760_000_100_000_000_000,
    )

    result = search_index("tie_", "all", limit=10)
    assert [row["asset_id"] for row in result["media"]] == [
        newer_a["asset_id"],
        newer_b["asset_id"],
        older["asset_id"],
    ]


def test_opaque_pages_have_no_duplicates_or_omissions_for_equal_scores(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Pages")
    expected = [_seed_search_image(isolated_gallery_root, f"page_equal_{index}.png")["asset_id"] for index in range(7)]

    seen: list[int] = []
    cursor: str | None = None
    while True:
        page = search_index("page_equal_", "all", limit=2, cursor=cursor)
        seen.extend(int(row["asset_id"]) for row in page["media"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert isinstance(cursor, str)
        assert not cursor.isdecimal()

    assert seen == expected
    assert len(seen) == len(set(seen))


def test_catalog_mutation_between_pages_does_not_repeat_returned_asset(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Mutation")
    for index in range(5):
        _seed_search_image(isolated_gallery_root, f"mutation_equal_{index}.png")

    first = search_index("mutation_equal_", "all", limit=2)
    first_ids = {int(row["asset_id"]) for row in first["media"]}
    assert first["next_cursor"] is not None

    with _connect() as conn:
        conn.execute("DELETE FROM assets WHERE id = ?", (min(first_ids),))
    _seed_search_image(isolated_gallery_root, "mutation_equal_new.png")

    second = search_index("mutation_equal_", "all", limit=3, cursor=first["next_cursor"])
    second_ids = {int(row["asset_id"]) for row in second["media"]}
    assert first_ids.isdisjoint(second_ids)


def test_cursor_is_request_bound_and_malformed_values_return_400(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Cursor validation")
    for index in range(3):
        _seed_search_image(isolated_gallery_root, f"cursor_query_{index}.png")

    first = isolated_app.get("/api/search", params={"q": "cursor_query_", "scope": "all", "limit": 1})
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str)

    wrong_query = isolated_app.get(
        "/api/search",
        params={"q": "different_query", "scope": "all", "limit": 1, "cursor": cursor},
    )
    assert wrong_query.status_code == 400

    malformed = isolated_app.get(
        "/api/search",
        params={"q": "cursor_query_", "scope": "all", "limit": 1, "cursor": "%%%"},
    )
    assert malformed.status_code == 400

    fingerprint = request_fingerprint("cursor_query_", "all", None, fielded=False)
    payload = {
        "version": 99,
        "fingerprint": fingerprint,
        "tier": 90,
        "rank": 0.0,
        "mtime_ns": 1,
        "asset_id": 1,
    }
    wrong_version = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    )
    response = isolated_app.get(
        "/api/search",
        params={"q": "cursor_query_", "scope": "all", "limit": 1, "cursor": wrong_version},
    )
    assert response.status_code == 400


def test_cursor_rejects_sqlite_overflow_and_json_type_coercion(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Cursor ranges")
    _seed_search_image(isolated_gallery_root, "cursor_range.png")

    decimal_overflow = isolated_app.get(
        "/api/search",
        params={"q": "cursor_range", "scope": "all", "cursor": str(2**63)},
    )
    assert decimal_overflow.status_code == 400

    fingerprint = request_fingerprint("cursor_range", "all", None, fielded=False)
    for override in ({"asset_id": 10**100}, {"tier": "90"}, {"rank": "0.0"}, {"version": True}):
        payload = {
            "version": 1,
            "fingerprint": fingerprint,
            "tier": 90,
            "rank": 0.0,
            "mtime_ns": 1,
            "asset_id": 1,
            **override,
        }
        cursor = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )
        response = isolated_app.get(
            "/api/search",
            params={"q": "cursor_range", "scope": "all", "cursor": cursor},
        )
        assert response.status_code == 400


def test_cursor_payload_contains_complete_ordering_tuple(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Payload")
    for index in range(3):
        _seed_search_image(isolated_gallery_root, f"payload_equal_{index}.png")
    first = search_index("payload_equal_", "all", limit=1)
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)

    fingerprint = request_fingerprint("payload_equal_", "all", None, fielded=False)
    decoded = decode_search_cursor(cursor, fingerprint)
    assert set(decoded) == {"tier", "rank", "mtime_ns", "asset_id"}


def test_decimal_cursor_uses_deprecated_offset_adapter_and_returns_opaque_cursor(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Legacy cursor")
    for index in range(6):
        _seed_search_image(isolated_gallery_root, f"legacy_equal_{index}.png")

    response = isolated_app.get(
        "/api/search",
        params={"q": "legacy_equal_", "scope": "all", "limit": 2, "cursor": "2"},
    )
    assert response.status_code == 200
    assert response.headers["deprecation"] == "true"
    assert "deprecated" in response.headers["warning"].lower()
    cursor = response.json()["next_cursor"]
    assert isinstance(cursor, str)
    assert not cursor.isdecimal()


def test_active_keyset_query_contains_no_offset() -> None:
    sql = build_candidate_page_query(
        [
            """
            SELECT 1 AS asset_id, 1 AS relevance_tier, 0.0 AS rank,
                   1 AS mtime_ns
            """
        ],
        has_cursor=True,
        legacy_offset=False,
    )
    assert "OFFSET" not in sql.upper()
    assert "cursor_asset_id" in sql


def test_normal_substring_queries_use_trigram_instead_of_full_like_scan() -> None:
    sql = "\n".join(
        _candidate_selects(
            "needle",
            "",
            include_fts=True,
            field_where="",
            include_videos=True,
        )
    )
    assert "file_index_fts_trigram MATCH :filename_substring_match" in sql
    assert "image_metadata_fts_trigram MATCH :positive_substring_match" in sql
    assert "fi.name LIKE :filename_like" not in sql
    assert "WHERE m.prompt LIKE :text_like" not in sql


def test_mixed_short_tokens_use_unicode_fts_without_full_like_scan() -> None:
    sql = "\n".join(
        _candidate_selects(
            "Euler a",
            "",
            include_fts=True,
            field_where="",
            include_videos=True,
        )
    )
    assert "image_metadata_fts MATCH :metadata_match" in sql
    assert "file_index_fts_trigram" not in sql
    assert "fi.name LIKE :filename_like" not in sql
    assert "WHERE m.prompt LIKE :text_like" not in sql


def test_ranked_candidate_plan_uses_fts_and_catalog_ownership_indexes(
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Plan")
    _seed_search_image(isolated_gallery_root, "plan_needle.png", prompt="plan needle prompt")
    sql = build_candidate_page_query(
        _candidate_selects(
            "needle",
            "",
            include_fts=True,
            field_where="",
            include_videos=True,
        ),
        has_cursor=False,
        legacy_offset=False,
    )
    params = {
        "filename_like": "%needle%",
        "filename_match": '"needle"',
        "filename_substring_match": '"needle"',
        "filename_prefix": "needle%",
        "metadata_match": '(model : ("needle")) OR (sampler : ("needle"))',
        "metadata_substring_match": '(model : ("needle")) OR (sampler : ("needle"))',
        "negative_match": 'negative_prompt : ("needle")',
        "negative_substring_match": 'negative_prompt : ("needle")',
        "page_limit": 51,
        "positive_match": 'prompt : ("needle")',
        "positive_substring_match": 'prompt : ("needle")',
        "query": "needle",
        "text_like": "%needle%",
    }
    with _connect() as conn:
        plan = [str(row["detail"]) for row in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)]

    assert any("VIRTUAL TABLE INDEX" in detail for detail in plan)
    assert any("assets" in detail and "INDEX" in detail for detail in plan)
    assert any("library_import_paths" in detail and "INDEX" in detail for detail in plan)
