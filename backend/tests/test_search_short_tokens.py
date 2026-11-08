"""Short-token and unspaced-CJK prompt search regressions (UX review SR-01).

Purpose:
Lock the contract that prompt search matches CJK words of one or two characters inside unspaced CJK
runs, prefix-matches one or two letter Latin tokens, and keeps AND semantics for mixed queries.

Guarantees:
* 少女, 東京, 夜景-style two-character words and the one-character 桜 match prompts that contain them
* a one-character query also matches the last character of a CJK run (女 in 少女)
* "ch" prefix-matches prompt tokens; mixed short/long queries stay AND
* negative prompts, folder scope, updates and deletes keep the bigram index consistent
* keyset pagination over short-token results has no duplicates or omissions
* the v12-to-v13 migration backs up the database and backfills existing prompts

Run when:
* changing ranked search, `cjk_index`, the v13 migration, or prompt persistence
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from backend.metadata_store import _connect, index_file, register_library, search_index, upsert_metadata_result
from backend.metadata_store.cjk_index import cjk_bigram_document, rebuild_cjk_index

from .conftest import create_test_png

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")


def _seed(root: Path, name: str, prompt: str = "", negative_prompt: str = "", *, mtime_ns: int | None = None) -> int:
    image = root / name
    image.parent.mkdir(parents=True, exist_ok=True)
    create_test_png(image)
    if mtime_ns is not None:
        os.utime(image, ns=(mtime_ns, mtime_ns))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    assert upsert_metadata_result(
        image, {"prompt": prompt, "negative_prompt": negative_prompt, "width": 64, "height": 64}
    )
    with _connect() as conn:
        return int(conn.execute("SELECT id FROM assets WHERE path = ?", (str(image.resolve()),)).fetchone()["id"])


def _ids(query: str, **kwargs: object) -> set[int]:
    return {int(row["asset_id"]) for row in search_index(query, "all", limit=100, **kwargs)["media"]}  # type: ignore[arg-type]


def _corpus(root: Path) -> dict[str, int]:
    register_library(root, name="Short tokens")
    return {
        "girl": _seed(root, "a.png", "桜の下の少女, masterpiece, cherry blossoms"),
        "tokyo": _seed(root, "b.png", "夜の東京、ネオン, cherry city"),
        "scenery": _seed(root, "c.png", "水彩画風の夜景, chair"),
        "latin": _seed(root, "d.png", "portrait, chrome armor, solo"),
        "neg": _seed(root, "e.png", "plain", negative_prompt="下手な少女"),
    }


def test_two_character_cjk_word_matches_inside_unspaced_run(isolated_gallery_root: Path) -> None:
    ids = _corpus(isolated_gallery_root)
    assert _ids("少女") == {ids["girl"], ids["neg"]}
    assert _ids("東京") == {ids["tokyo"]}
    assert _ids("夜景") == {ids["scenery"]}
    assert _ids("桜の") == {ids["girl"]}


def test_one_character_cjk_query_matches_any_position_including_run_end(isolated_gallery_root: Path) -> None:
    ids = _corpus(isolated_gallery_root)
    assert _ids("桜") == {ids["girl"]}
    assert _ids("女") == {ids["girl"], ids["neg"]}
    assert _ids("夜") == {ids["tokyo"], ids["scenery"]}


def test_three_character_cjk_run_is_a_substring_not_a_bag_of_bigrams(isolated_gallery_root: Path) -> None:
    ids = _corpus(isolated_gallery_root)
    assert _ids("桜の下") == {ids["girl"]}
    assert _ids("下桜の") == set()


def test_short_latin_query_prefix_matches_prompt_tokens(isolated_gallery_root: Path) -> None:
    ids = _corpus(isolated_gallery_root)
    assert _ids("ch") == {ids["girl"], ids["tokyo"], ids["scenery"], ids["latin"]}
    assert _ids("chr") == {ids["latin"]}  # trigram substring path is unchanged


def test_mixed_short_and_long_tokens_keep_and_semantics(isolated_gallery_root: Path) -> None:
    ids = _corpus(isolated_gallery_root)
    assert _ids("cherry 東京") == {ids["tokyo"]}
    assert _ids("cherry 少女") == {ids["girl"]}
    assert _ids("cherry 夜景") == set()
    assert _ids("ch 東京") == {ids["tokyo"]}
    assert _ids("少女 東京") == set()


def test_short_cjk_search_respects_folder_scope(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Scoped")
    inside = _seed(isolated_gallery_root, "inside/a.png", "桜の下の少女")
    _seed(isolated_gallery_root, "outside/b.png", "夜の東京の少女")
    scoped = search_index("少女", "folder", isolated_gallery_root / "inside", limit=50)
    assert {int(row["asset_id"]) for row in scoped["media"]} == {inside}


def test_prompt_rewrite_and_row_delete_keep_the_bigram_index_consistent(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Updates")
    asset = _seed(isolated_gallery_root, "x.png", "桜の下の少女")
    assert _ids("少女") == {asset}
    _seed(isolated_gallery_root, "x.png", "夜の東京")  # same path: prompt rewritten
    assert _ids("少女") == set()
    assert _ids("東京") == {asset}
    with _connect() as conn:
        conn.execute("DELETE FROM image_metadata")
        assert conn.execute("SELECT count(*) FROM image_metadata_cjk").fetchone()[0] == 0
    assert _ids("東京") == set()


def test_keyset_pagination_over_short_token_results_has_no_duplicates_or_omissions(
    isolated_gallery_root: Path,
) -> None:
    register_library(isolated_gallery_root, name="Pages")
    expected = [
        _seed(
            isolated_gallery_root, f"p{index}.png", f"桜の下の少女 {index}", mtime_ns=1_760_000_000_000_000_000 + index
        )
        for index in range(7)
    ]
    _seed(isolated_gallery_root, "other.png", "夜の東京")
    for query in ("少女", "桜", "cherry 少女"):
        seen: list[int] = []
        cursor: str | None = None
        while True:
            page = search_index(query, "all", limit=2, cursor=cursor)
            seen.extend(int(row["asset_id"]) for row in page["media"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert isinstance(cursor, str)
        if query == "cherry 少女":
            assert seen == []
        else:
            assert len(seen) == len(set(seen))
            assert set(seen) == set(expected)


def test_short_cjk_matches_rank_as_prompt_phrase_tier(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Tier")
    _seed(isolated_gallery_root, "t.png", "夜の東京")
    row = search_index("東京", "all", limit=5)["media"][0]
    assert row["match_type"] == "prompt_phrase"


def test_bigram_document_shape() -> None:
    assert cjk_bigram_document("夜の東京、ネオン") == "夜の の東 東京 京 ネオ オン ン"
    assert cjk_bigram_document("abc") == ""
    assert cjk_bigram_document("桜") == "桜"


def test_rebuild_reconciles_raw_sql_inserts(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Rebuild")
    asset = _seed(isolated_gallery_root, "r.png", "plain")
    with _connect() as conn:
        conn.execute("UPDATE image_metadata SET prompt = '古い神社と猫'")  # raw SQL bypasses the writer path
        assert _ids("神社") == set()
        assert rebuild_cjk_index(conn) == 1
    assert _ids("神社") == {asset}


def test_v12_database_migrates_to_v13_with_backup_and_backfill(
    isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    register_library(isolated_gallery_root, name="Migrate")
    asset = _seed(isolated_gallery_root, "m.png", "桜の下の少女")
    with _connect() as conn:
        conn.execute("DROP TRIGGER image_metadata_cjk_cleanup")
        conn.execute("DROP TABLE image_metadata_fts_cjk")
        conn.execute("DROP TABLE image_metadata_cjk")
        conn.execute("PRAGMA user_version = 12")
    from backend.metadata_store import _db

    _db._DB_INITIALIZED = False
    assert _ids("少女") == {asset}
    with sqlite3.connect(isolated_metadata_db) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 13
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v12.bak").exists()
