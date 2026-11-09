"""Prefix-first matching and accent/kana folding regressions (search-typing plan SE-03, SE-04).

Purpose:
Lock the contract that word-prefix matches are the first relevance tier at every query length with
substring matches ranking below them, that indexed text and queries share one folding function, and that
the folded index stays consistent with the stored text.

Guarantees:
* m -> mi -> mik -> mika keeps prefix matches ahead of substring matches ("kamikaze" never leads)
* negative-prompt prefix matches outrank positive-prompt substring matches
* cafe/cafe-acute, noi/Noi-dot, pho/Pho-acute, half-width/full-width katakana/hiragana match both ways
* filenames, model and sampler fold too; display text (names, snippets) keeps the original characters
* fielded contains filters (prompt:, negative:, name:, model:, sampler:) fold the same way
* the incremental folded index equals a full rebuild after writes, rewrites and deletes
* the v13-to-v14 migration backs up, backfills from stored text and sets user_version 14

Run when:
* changing ranked search, `backend/text_fold.py`, `search_text_index`, the v14 migration or prompt/filename writers
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from backend.metadata_store import (
    _connect,
    index_directory_tree,
    index_file,
    register_library,
    search_index,
    search_index_count,
    search_index_fielded,
    upsert_metadata_result,
)

from .conftest import create_test_png

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")


def _seed(
    root: Path,
    name: str,
    prompt: str = "",
    negative_prompt: str = "",
    *,
    model: str = "",
    sampler: str = "",
    mtime_ns: int | None = None,
) -> int:
    image = root / name
    image.parent.mkdir(parents=True, exist_ok=True)
    create_test_png(image)
    if mtime_ns is not None:
        os.utime(image, ns=(mtime_ns, mtime_ns))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    params = {"Model": model, "Sampler": sampler} if model or sampler else {}
    assert upsert_metadata_result(
        image,
        {"prompt": prompt, "negative_prompt": negative_prompt, "width": 64, "height": 64, "params": params},
    )
    with _connect() as conn:
        return int(conn.execute("SELECT id FROM assets WHERE path = ?", (str(image.resolve()),)).fetchone()["id"])


def _ordered(query: str) -> list[int]:
    return [int(row["asset_id"]) for row in search_index(query, "all", limit=100)["media"]]


def _ids(query: str) -> set[int]:
    return set(_ordered(query))


def _fielded(query: str) -> set[int]:
    return {int(row["asset_id"]) for row in search_index_fielded(query, "all", limit=100)["media"]}


def _prefix_corpus(root: Path) -> dict[str, int]:
    register_library(root, name="Prefix")
    base = 1_760_000_000_000_000_000
    return {
        "mika": _seed(root, "p1.png", "mika portrait", mtime_ns=base + 1),
        "mikan": _seed(root, "p2.png", "mikan orange", mtime_ns=base + 2),
        "midnight": _seed(root, "p3.png", "midnight sun", mtime_ns=base + 3),
        # newest, so a flat tier would list it first
        "kamikaze": _seed(root, "p4.png", "kamikaze pilot", mtime_ns=base + 9),
    }


def test_prefix_matches_outrank_substring_matches_as_the_query_grows(isolated_gallery_root: Path) -> None:
    ids = _prefix_corpus(isolated_gallery_root)
    assert _ids("mi") == {ids["mika"], ids["mikan"], ids["midnight"]}
    for query in ("mik", "mika"):
        ordered = _ordered(query)
        assert set(ordered[:2]) == {ids["mika"], ids["mikan"]}, query
        assert ordered[2:] == [ids["kamikaze"]], query
    assert _ordered("mikan") == [ids["mikan"]]
    assert _ids("mid") == {ids["midnight"]}


def test_top_results_are_stable_from_two_to_four_characters(isolated_gallery_root: Path) -> None:
    ids = _prefix_corpus(isolated_gallery_root)
    two, three, four = (_ordered(q) for q in ("mi", "mik", "mika"))
    assert set(three[:2]) <= set(two)
    assert set(three[:2]) == set(four[:2]) == {ids["mika"], ids["mikan"]}


def test_negative_prefix_outranks_positive_substring(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Neg")
    positive_substring = _seed(isolated_gallery_root, "a.png", "kamikaze", mtime_ns=1_760_000_000_000_000_009)
    negative_prefix = _seed(isolated_gallery_root, "b.png", "plain", "mikan", mtime_ns=1_760_000_000_000_000_001)
    assert _ordered("mik") == [negative_prefix, positive_substring]


def test_filename_and_model_prefix_outrank_substrings(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Names")
    base = 1_760_000_000_000_000_000
    sub_file = _seed(isolated_gallery_root, "kamikaze.png", "x", mtime_ns=base + 9)
    prefix_file = _seed(isolated_gallery_root, "mikan.png", "y", mtime_ns=base + 1)
    sub_model = _seed(isolated_gallery_root, "m1.png", "z", model="kamikaze-mix", mtime_ns=base + 8)
    prefix_model = _seed(isolated_gallery_root, "m2.png", "z", model="mikado-mix", mtime_ns=base + 2)
    ordered = _ordered("mik")
    assert set(ordered[:2]) == {prefix_file, prefix_model}
    assert set(ordered[2:]) == {sub_file, sub_model}


def test_mixed_short_and_long_tokens_match_by_prefix(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Mixed")
    blossom = _seed(isolated_gallery_root, "a.png", "cherry blossoms in spring")
    girl = _seed(isolated_gallery_root, "b.png", "a girl smiling")
    _seed(isolated_gallery_root, "c.png", "boy, then girl")
    assert _ids("ch blossoms") == {blossom}
    assert _ids("a girl") == {girl}


def test_count_matches_paged_total_for_prefix_and_folded_queries(isolated_gallery_root: Path) -> None:
    ids = _prefix_corpus(isolated_gallery_root)
    _seed(isolated_gallery_root, "q.png", "Phố cổ Hà Nội")
    for query in ("mi", "mik", "mika", "noi", "pho co"):
        assert search_index_count(query, "all") == len(_ordered(query)), query
    assert len(ids) == 4


FOLD_CASES = [
    ("cafe", "a café au lait"),
    ("café", "a cafe au lait"),
    ("CAFÉ", "a cafe au lait"),
    ("noi", "Phố cổ Hà Nội"),
    ("Nội", "ha noi old town"),
    ("pho", "Phố cổ Hà Nội"),
    ("Phố", "pho co"),
    ("ha noi", "Hà Nội"),
    ("duong", "Đường phố"),
    ("Đường", "duong pho"),
    ("ねおん", "ネオン sign"),
    ("ネオン", "ねおん sign"),
    ("ﾈｵﾝ", "ネオン sign"),
    ("ネオン", "ﾈｵﾝ sign"),
    ("ﾈｵﾝ", "ねおん sign"),
    ("ｶﾞｲﾄﾞ", "がいど"),
    ("少女", "桜の下の少女"),
    ("東京", "夜の東京"),
    ("桜", "桜の下の少女"),
    ("cherry 東京", "cherry 夜の東京"),
    ("ｃａｆé", "cafe"),
]


@pytest.mark.parametrize(("query", "prompt"), FOLD_CASES)
def test_folded_queries_match_prompts(isolated_gallery_root: Path, query: str, prompt: str) -> None:
    register_library(isolated_gallery_root, name="Fold")
    asset = _seed(isolated_gallery_root, "f.png", prompt)
    _seed(isolated_gallery_root, "other.png", "unrelated words")
    assert _ids(query) == {asset}, (query, prompt)
    assert search_index_count(query, "all") == 1


def test_kana_voicing_is_not_folded_away(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Voicing")
    ga = _seed(isolated_gallery_root, "ga.png", "がっこう")
    _seed(isolated_gallery_root, "ka.png", "かっこう")
    assert _ids("がっこう") == {ga}
    assert _ids("ｶﾞｯｺｳ") == {ga}


def test_folding_covers_filename_model_sampler_and_negative(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Fields")
    named = _seed(isolated_gallery_root, "Café Nội.png", "x1")
    modeled = _seed(isolated_gallery_root, "m.png", "x2", model="Phố-Mix")
    sampled = _seed(isolated_gallery_root, "s.png", "x3", sampler="Đường a")
    negative = _seed(isolated_gallery_root, "n.png", "x4", "blurry, café")
    assert named in _ids("cafe noi")
    assert _ids("pho") == {modeled}
    assert _ids("duong") == {sampled}
    assert _ids("cafe") == {named, negative}


def test_display_text_keeps_original_characters(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Display")
    _seed(isolated_gallery_root, "Café Nội.png", "Phố cổ Hà Nội, ネオン")
    by_prompt = search_index("noi neon", "all", limit=5)["media"]
    assert by_prompt == [] or by_prompt[0]["prompt_snippet"] == "Phố cổ Hà Nội, ネオン"
    row = search_index("ねおん", "all", limit=5)["media"][0]
    assert row["prompt_snippet"] == "Phố cổ Hà Nội, ネオン"
    by_name = search_index("cafe", "all", limit=5)["media"][0]
    assert by_name["name"] == "Café Nội.png"


@pytest.mark.parametrize(
    ("query", "field_text"),
    [
        ("prompt:cafe", "café au lait"),
        ("prompt:CAFÉ", "cafe au lait"),
        ("prompt:noi", "Phố cổ Hà Nội"),
        ("prompt:pho", "Phố cổ Hà Nội"),
        ("prompt:ねおん", "ネオン"),
        ("prompt:ネオン", "ﾈｵﾝ"),
        ("prompt:ﾈｵﾝ", "ネオン"),
        ("prompt:ca", "café"),
        ("prompt:少女", "桜の下の少女"),
        ("prompt:桜", "桜の下の少女"),
        ("prompt:chee", "cheese cake"),
    ],
)
def test_fielded_prompt_contains_folds(isolated_gallery_root: Path, query: str, field_text: str) -> None:
    register_library(isolated_gallery_root, name="Fielded")
    asset = _seed(isolated_gallery_root, "f.png", field_text)
    _seed(isolated_gallery_root, "other.png", "unrelated words")
    assert _fielded(query) == {asset}, query


def test_fielded_other_text_fields_fold(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="FieldedOthers")
    negative = _seed(isolated_gallery_root, "a.png", "x1", "café")
    named = _seed(isolated_gallery_root, "Hà Nội.png", "x2")
    modeled = _seed(isolated_gallery_root, "c.png", "x3", model="Phố-Mix")
    sampled = _seed(isolated_gallery_root, "d.png", "x4", sampler="Đường a")
    assert _fielded("negative:cafe") == {negative}
    assert _fielded("name:noi") == {named}
    assert _fielded("model:pho") == {modeled}
    assert _fielded("sampler:duong") == {sampled}
    assert _fielded("model:PHỐ") == {modeled}


def test_album_suggestions_fold_folder_names(isolated_gallery_root: Path) -> None:
    register_library(isolated_gallery_root, name="Albums")
    album = isolated_gallery_root / "Phố cổ Hà Nội"
    album.mkdir()
    create_test_png(album / "cover.png")
    index_directory_tree(isolated_gallery_root, include_metadata=False)
    for query in ("noi", "pho co", "Nội", "ha noi"):
        albums = search_index(query, "all", limit=20)["albums"]
        assert [item["name"] for item in albums] == ["Phố cổ Hà Nội"], query


def _fold_dump(conn: sqlite3.Connection) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    meta = [
        tuple(row)
        for row in conn.execute(
            "SELECT metadata_id, prompt, negative_prompt, model, sampler FROM image_metadata_fold ORDER BY 1"
        )
    ]
    names = [tuple(row) for row in conn.execute("SELECT file_rowid, name FROM file_index_fold ORDER BY 1")]
    return meta, names


def test_incremental_folded_index_equals_full_rebuild(isolated_gallery_root: Path) -> None:
    from backend.metadata_store.search_text_index import rebuild_search_text_index

    register_library(isolated_gallery_root, name="Consistency")
    _seed(isolated_gallery_root, "a.png", "Phố cổ", "café", model="Đ-Mix", sampler="Euler a")
    _seed(isolated_gallery_root, "b.png", "ネオン sign")
    _seed(isolated_gallery_root, "c.png", "temporary")
    _seed(isolated_gallery_root, "a.png", "Hà Nội rewritten", "")  # same path rewritten
    _seed(isolated_gallery_root, "Ñandú.png", "plain")
    with _connect() as conn:
        conn.execute("DELETE FROM image_metadata WHERE name = 'c.png'")
        conn.execute("DELETE FROM file_index WHERE name = 'c.png'")
        incremental = _fold_dump(conn)
        rebuild_search_text_index(conn)
        assert _fold_dump(conn) == incremental
        for table in (
            "image_metadata_fold_fts",
            "image_metadata_fold_fts_trigram",
            "file_index_fold_fts",
            "file_index_fold_fts_trigram",
        ):
            conn.execute(f"INSERT INTO {table}({table}, rank) VALUES ('integrity-check', 1)")
    assert incremental[0], "fold rows exist"
    assert all(row[1].islower() or not row[1].isalpha() for row in incremental[0])


def test_rebuild_repairs_raw_sql_text_changes(isolated_gallery_root: Path) -> None:
    from backend.metadata_store.search_text_index import rebuild_search_text_index

    register_library(isolated_gallery_root, name="Raw")
    asset = _seed(isolated_gallery_root, "r.png", "plain")
    with _connect() as conn:
        conn.execute("UPDATE image_metadata SET prompt = 'Phố cổ'")
        assert _ids("pho") == set()
        rebuild_search_text_index(conn)
    assert _ids("pho") == {asset}


def test_v13_database_migrates_to_v14_with_backup_and_backfill(
    isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    register_library(isolated_gallery_root, name="Migrate")
    asset = _seed(isolated_gallery_root, "Café.png", "Phố cổ Hà Nội")
    with _connect() as conn:
        for trigger in (
            "image_metadata_fold_cleanup",
            "file_index_fold_cleanup",
        ):
            conn.execute(f"DROP TRIGGER {trigger}")
        for table in (
            "image_metadata_fold_fts",
            "image_metadata_fold_fts_trigram",
            "image_metadata_fold",
            "file_index_fold_fts",
            "file_index_fold_fts_trigram",
            "file_index_fold",
        ):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version = 13")
    from backend.metadata_store import _db

    _db._DB_INITIALIZED = False
    assert _ids("noi") == {asset}
    assert _ids("cafe") == {asset}
    with sqlite3.connect(isolated_metadata_db) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 14
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v13.bak").exists()


def test_fold_text_contract() -> None:
    from backend.text_fold import fold_text

    assert fold_text("Hà Nội") == "ha noi"
    assert fold_text("Đường") == "duong"
    assert fold_text("ﾈｵﾝ") == fold_text("ネオン") == fold_text("ねおん") == "ねおん"
    assert fold_text("ｃａｆÉ") == "cafe"
    assert fold_text("が") == "が"
    assert fold_text("") == ""
