"""Result-pinning tests for very short, dense search queries (BL-13).

Purpose:
Pin the exact result sets, orders, album suggestions and counts of one-character free text and
one-character fielded searches over a dense deterministic corpus, so a latency optimisation of the
short-query planner (tier-ordered sources, ordered probes, capped counts, folder aggregates) can never
change what a query returns.

Guarantees:
* every pinned query returns the same ordered media list across all keyset pages (sha256 pinned)
* the first page carries the same album suggestions with the same aggregates (image counts and covers)
* `search_index_count` equals the paged total while the total is under the count cap
* the count stops at the cap (`COUNT_CAP`) for dense queries instead of scanning every match
* pages never repeat or omit a row, and every cursor stays request-bound

Run when:
* changing `ranked_search.py`, the fielded parser's short-value conditions, folder aggregates, or the
  ordered assets index (schema v15)

The pinned hashes were recorded against the pre-optimisation planner (schema v14, `67bc7d4`); this file is
the oracle that the optimised planner has to match, so never re-record them to make a change pass.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend.metadata_store import _connect, register_library, search_index, search_index_count, search_index_fielded
from backend.metadata_store.search_text_index import rebuild_search_text_index

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")

BASE_MTIME_NS = 1_760_000_000_000_000_000
PAGE_LIMIT = 25
IMAGE_ROWS = 720

_PROMPT_WORDS = (
    "cat",
    "castle",
    "cinematic",
    "mountain",
    "misty",
    "art",
    "ancient",
    "city",
    "cozy",
    "moon",
    "ocean",
    "garden",
    "portrait",
    "neon",
    "amber",
    "river",
)
_NEGATIVE = ("blurry, ugly", "cartoon, mutated hands", "low quality", "", "cropped, watermark")
_MODELS = ("model-a", "cobalt-xl", "mix-v2", "perf-model-3", "")
_SAMPLERS = ("euler a", "dpm++ 2m", "ddim", "")
_NAME_STEMS = ("alpha", "mango", "cedar", "river", "silver", "image", "ink", "oasis", "plum", "stone")
_FOLDER_NAMES = ("alpha_album", "misty_mountains", "cats_and_castles", "ocean_set", "city_lights", "plain")


def _prompt(rng: random.Random, index: int) -> str:
    words = [rng.choice(_PROMPT_WORDS) for _ in range(rng.randint(1, 7))]
    if index % 11 == 0:
        words.append(words[0])  # repeated term: a second bm25 rank class
    return ", ".join(words)


def _build_corpus(root: Path) -> None:
    """Insert a deterministic dense corpus with raw rows (as the perf fixture does) and fold it."""
    library = register_library(root, name="Short query pins")
    library_id = int(library["id"])
    resolved = root.resolve()
    rng = random.Random(20260509)
    folders = [resolved / name for name in _FOLDER_NAMES]
    now = 1_760_000_000.0
    with closing(_connect()) as conn:
        for folder in folders:
            conn.execute(
                "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, library_id) "
                "VALUES (?, ?, ?, 'folder', ?, ?, NULL, ?, ?)",
                (str(folder), folder.name, str(resolved), now, int(now * 1e9), now, library_id),
            )
            conn.execute(
                "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'folder', ?)",
                (folder.name, str(folder), str(resolved)),
            )
        for index in range(IMAGE_ROWS + 6):
            is_video = index >= IMAGE_ROWS
            folder = folders[index % len(folders)]
            stem = _NAME_STEMS[index % len(_NAME_STEMS)]
            suffix = "mp4" if is_video else "png"
            name = f"{stem}_{index:04d}.{suffix}"
            path = str(folder / name)
            # Mostly unique mtimes, plus small deliberate tie groups, in a shuffled (non id-ordered) order.
            slot = (index * 7919) % 1009
            mtime_ns = BASE_MTIME_NS + (slot // 5 if index % 37 == 0 else slot) * 1_000
            size = 4096 + index % 97
            conn.execute(
                "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
                "indexed_at, metadata_state, offline) VALUES (?, ?, ?, ?, ?, ?, ?, 64, 64, ?, 'ready', 0)",
                (library_id, path, str(folder), name, "video" if is_video else "image", mtime_ns, size, now),
            )
            conn.execute(
                "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
                "indexed_at, library_id) VALUES (?, ?, ?, ?, ?, ?, ?, 64, 64, ?, ?)",
                (
                    path,
                    name,
                    str(folder),
                    "video" if is_video else "image",
                    mtime_ns / 1e9,
                    mtime_ns,
                    size,
                    now,
                    library_id,
                ),
            )
            conn.execute(
                "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, ?, ?)",
                (name, path, "video" if is_video else "image", str(folder)),
            )
            if is_video:
                continue
            conn.execute(
                "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
                "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
                "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, ?, 64, 64, 'PNG', 'RGB', 0, ?, ?, ?, ?, "
                "?, 20, 7.0, '', '', ?, ?)",
                (
                    path,
                    name,
                    mtime_ns / 1e9,
                    mtime_ns,
                    size,
                    _prompt(rng, index),
                    rng.choice(_NEGATIVE),
                    rng.choice(_MODELS),
                    rng.choice(_SAMPLERS),
                    str(1000 + index),
                    now,
                    now,
                ),
            )
        rebuild_search_text_index(conn)
        conn.commit()


def _search(query: str, cursor: str | None = None, limit: int = PAGE_LIMIT) -> dict:
    fn = search_index_fielded if ":" in query else search_index
    return fn(query, "all", None, limit, cursor)


def _walk(query: str) -> tuple[list[dict], dict]:
    """Return every media row across all keyset pages plus the first page payload."""
    first = _search(query)
    rows = list(first["media"])
    page = first
    seen_cursors: set[str] = set()
    while page["next_cursor"]:
        assert page["next_cursor"] not in seen_cursors, "cursor repeated"
        seen_cursors.add(page["next_cursor"])
        page = _search(query, page["next_cursor"])
        assert page["albums"] == [], "albums belong to the first page only"
        rows.extend(page["media"])
    return rows, first


def _digest(rows: list[dict]) -> str:
    text = "\n".join(f"{row['name']}|{row['match_type']}|{row['type']}" for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _album_digest(first: dict) -> str:
    albums = [
        {
            "name": album["name"],
            "match_type": album["match_type"],
            "image_count": album["image_count"],
            "has_children": album["has_children"],
            "covers": [Path(cover).name for cover in album["cover_images"]],
        }
        for album in first["albums"]
    ]
    return hashlib.sha256(json.dumps(albums, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# query -> (media rows across all pages, media digest, album digest, head of the order)
PINNED: dict[str, tuple[int, str, str, tuple[str, ...]]] = {
    "a": (
        686,
        "503502df7842bebf",
        "71f2fb66b8e6f322",
        ("alpha_0310.png", "alpha_0620.png", "alpha_0020.png", "alpha_0330.png"),
    ),
    "m": (
        932,
        "d32d3c6e1d5c50e1",
        "0b936c8bed6166e0",
        ("mango_0521.png", "mango_0231.png", "mango_0541.png", "mango_0251.png"),
    ),
    "c": (
        921,
        "a747949c93a04bc7",
        "195c2a17f9a43937",
        ("cedar_0132.png", "cedar_0442.png", "cedar_0152.png", "cedar_0462.png"),
    ),
    "s": (
        145,
        "aa709eb39ca3cb43",
        "4c8339a050fffe85",
        ("silver_0554.png", "stone_0099.png", "stone_0409.png", "stone_0719.png"),
    ),
    "i": (
        145,
        "a110b50aa18f859a",
        "b51ab22be712c843",
        ("ink_0066.png", "ink_0376.png", "image_0165.png", "ink_0686.png"),
    ),
    "ca": (
        446,
        "ece58f411f8c029f",
        "fa5c115505773bc2",
        ("oasis_0327.png", "cedar_0682.png", "plum_0648.png", "stone_0389.png"),
    ),
    "mi": (
        280,
        "e1c26b99b6e9f206",
        "23d9f7b2d6803ee6",
        ("river_0433.png", "oasis_0017.png", "alpha_0110.png", "plum_0498.png"),
    ),
    "prompt:c": (
        603,
        "e94738011c0e7fb4",
        "4f53cda18c2baa0c",
        ("mango_0521.png", "oasis_0277.png", "river_0033.png", "silver_0554.png"),
    ),
    "prompt:ca": (
        299,
        "3d63983c47e117c6",
        "4f53cda18c2baa0c",
        ("river_0033.png", "silver_0554.png", "ink_0376.png", "stone_0409.png"),
    ),
    "negative:c": (
        289,
        "ce88b5d892d85c5a",
        "4f53cda18c2baa0c",
        ("river_0033.png", "silver_0554.png", "alpha_0310.png", "river_0343.png"),
    ),
    "name:i": (
        360,
        "09f6d364fbe7fafe",
        "4f53cda18c2baa0c",
        ("oasis_0277.png", "river_0033.png", "silver_0554.png", "ink_0066.png"),
    ),
    "name:a": (
        360,
        "fc1bc5f445c2c746",
        "4f53cda18c2baa0c",
        ("mango_0521.png", "oasis_0277.png", "alpha_0310.png", "oasis_0587.png"),
    ),
    "model:m": (
        455,
        "785ff114b1883e46",
        "4f53cda18c2baa0c",
        ("mango_0521.png", "silver_0554.png", "alpha_0310.png", "oasis_0587.png"),
    ),
    "sampler:e": (
        173,
        "f136569960cfae89",
        "4f53cda18c2baa0c",
        ("alpha_0310.png", "oasis_0587.png", "river_0053.png", "river_0363.png"),
    ),
}


@pytest.fixture
def corpus(isolated_gallery_root: Path) -> Path:
    _build_corpus(isolated_gallery_root)
    return isolated_gallery_root


QUERIES = (
    "a",
    "m",
    "c",
    "s",
    "i",
    "ca",
    "mi",
    "prompt:c",
    "prompt:ca",
    "negative:c",
    "name:i",
    "name:a",
    "model:m",
    "sampler:e",
)


def _record(query: str) -> tuple[int, str, str, tuple[str, ...]]:
    rows, first = _walk(query)
    return len(rows), _digest(rows), _album_digest(first), tuple(row["name"] for row in rows[:4])


@pytest.mark.parametrize("query", QUERIES)
def test_short_query_results_are_pinned(corpus: Path, query: str) -> None:
    expected = PINNED.get(query)
    actual = _record(query)
    assert expected is not None, f"unpinned query {query!r}: {actual!r}"
    assert actual == expected, f"{query!r}: {actual!r} != {expected!r}"


# Queries whose rows match in only one source. A row that matches in two sources of different tiers (a prompt
# word that is also a model/negative word, or a filename that is also a prompt word) can come back once per
# tier on later keyset pages: the bounded per-source cursor pre-filter runs before the cross-source dedup. That
# long-standing behaviour is pinned as it is (the recorded counts above include those repeats).
SINGLE_SOURCE_QUERIES = (
    "s",
    "i",
    "prompt:c",
    "prompt:ca",
    "negative:c",
    "name:i",
    "name:a",
    "model:m",
    "sampler:e",
)


@pytest.mark.parametrize("query", SINGLE_SOURCE_QUERIES)
def test_pages_have_no_duplicates_and_page_size_does_not_change_the_order(corpus: Path, query: str) -> None:
    rows, _first = _walk(query)
    ids = [row["asset_id"] for row in rows]
    assert len(ids) == len(set(ids)), "a row repeated across pages"
    small = [row["asset_id"] for row in _walk_with_limit(query, 7)]
    assert small == ids, "page size must not change the order"


def _walk_with_limit(query: str, limit: int) -> list[dict]:
    page = _search(query, None, limit)
    rows = list(page["media"])
    while page["next_cursor"]:
        page = _search(query, page["next_cursor"], limit)
        rows.extend(page["media"])
    return rows


@pytest.mark.parametrize("query", SINGLE_SOURCE_QUERIES)
def test_count_equals_paged_total_below_the_cap(corpus: Path, query: str) -> None:
    rows, _first = _walk(query)
    assert len(rows) < 4096
    assert search_index_count(query, "all") == len(rows)


@pytest.mark.parametrize("query", QUERIES)
def test_count_is_the_distinct_asset_total_below_the_cap(corpus: Path, query: str) -> None:
    rows, _first = _walk(query)
    assert search_index_count(query, "all") == len({row["asset_id"] for row in rows})


def test_count_is_capped_for_dense_queries(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.metadata_store import ranked_search

    cap = getattr(ranked_search, "COUNT_CAP", None)
    if cap is None:
        pytest.skip("pre-optimisation planner has no count cap")
    monkeypatch.setattr(ranked_search, "COUNT_CAP", 100)
    assert search_index_count("c", "all") == 100
    assert search_index_count("prompt:c", "all") == 100
    # A selective query stays exact under the cap.
    selective = {row["asset_id"] for row in _walk("alph")[0]}
    assert 0 < len(selective) < 100
    assert search_index_count("alph", "all") == len(selective)


def test_connection_state_is_readable_after_search(corpus: Path) -> None:
    _search("c")
    with closing(_connect()) as conn:
        assert isinstance(conn, sqlite3.Connection)
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 14


def test_all_scope_resolution_does_not_list_libraries(monkeypatch: pytest.MonkeyPatch) -> None:
    """`scope=all` searches every library, so resolving it must not pay the per-library asset count."""
    from backend import search_scope
    from backend.models import SearchAllScopeV1

    def forbidden(*_args: object, **_kwargs: object) -> list:
        raise AssertionError("list_libraries must not run for the all scope")

    monkeypatch.setattr(search_scope, "list_libraries", forbidden)
    assert search_scope.resolve_search_scope("all", library_id=None, path=None).kind == "all"
    assert search_scope.resolve_search_v2_scope(SearchAllScopeV1(kind="all")).kind == "all"


def _first_appearance_order(rows: list[dict]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for row in rows:
        if row["asset_id"] not in seen:
            seen.add(row["asset_id"])
            ordered.append(row["asset_id"])
    return ordered


@pytest.mark.parametrize("query", ("a", "m", "c", "s", "i", "ca", "mi"))
def test_dense_filename_variants_match_the_whole_read_filename_sources(
    corpus: Path, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    """Large filename match sets are read through bounded hi/lo variants; the result must not change."""
    from backend.metadata_store import ranked_search

    whole_rows, whole_first = _walk(query)
    monkeypatch.setattr(ranked_search, "FILE_SOURCE_SMALL_LIMIT", 3)
    dense_rows, dense_first = _walk(query)
    assert [row["asset_id"] for row in dense_first["media"]] == [row["asset_id"] for row in whole_first["media"]]
    assert dense_first["albums"] == whole_first["albums"]
    assert _first_appearance_order(dense_rows) == _first_appearance_order(whole_rows)


def test_page_plan_skips_sources_that_rank_below_a_full_page(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.metadata_store import ranked_search

    executed: list[int] = []
    original = ranked_search.build_candidate_page_query

    def recording(selects: list, **kwargs: object) -> str:
        executed.extend(getattr(select, "max_tier", -1) for select in selects)
        return original(selects, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ranked_search, "build_candidate_page_query", recording)
    page = _search("m", None, 100)
    assert len(page["media"]) == 100
    assert page["media"][-1]["match_type"] == "prompt_phrase"
    # The prompt-phrase tier (80) fills the page: the metadata (65) and negative-prompt (40) sources never run.
    assert executed
    assert min(executed) >= 80


@pytest.mark.parametrize("query", ("prompt:c", "prompt:ca", "name:i", "name:a", "negative:c", "model:m", "sampler:e"))
def test_field_only_probe_and_sorting_plan_return_the_same_pages(
    corpus: Path, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    from backend.metadata_store import ranked_search

    probed_rows, _ = _walk(query)
    monkeypatch.setattr(ranked_search, "_probe_field_only_ids", lambda *_args, **_kwargs: None)
    sorted_rows, _ = _walk(query)
    assert [row["asset_id"] for row in sorted_rows] == [row["asset_id"] for row in probed_rows]


@pytest.mark.parametrize("query", ("prompt:c", "name:a", "negative:c", "model:m", "name:i", "sampler:e"))
def test_field_only_count_probe_and_set_plan_agree(corpus: Path, monkeypatch: pytest.MonkeyPatch, query: str) -> None:
    from backend.metadata_store import ranked_search

    probed = search_index_count(query, "all")
    monkeypatch.setattr(ranked_search, "COUNT_PROBE_ROWS", 30)  # far fewer rows than matches: the set plan answers
    assert search_index_count(query, "all") == probed


def _build_tie_corpus(root: Path, rows: int) -> None:
    """`rows` images that tie on tier, rank and mtime for the query `z`: only the asset id orders them."""
    library_id = int(register_library(root, name="Ties")["id"])
    folder = root.resolve() / "ties"
    now = 1_760_000_000.0
    with closing(_connect()) as conn:
        for index in range(rows):
            name = f"item_{index:04d}.png"
            path = str(folder / name)
            conn.execute(
                "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
                "indexed_at, metadata_state, offline) VALUES (?, ?, ?, ?, 'image', ?, 4096, 64, 64, ?, 'ready', 0)",
                (library_id, path, str(folder), name, BASE_MTIME_NS, now),
            )
            conn.execute(
                "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
                "indexed_at, library_id) VALUES (?, ?, ?, 'image', ?, ?, 4096, 64, 64, ?, ?)",
                (path, name, str(folder), BASE_MTIME_NS / 1e9, BASE_MTIME_NS, now, library_id),
            )
            conn.execute(
                "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
                (name, path, str(folder)),
            )
            conn.execute(
                "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
                "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
                "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, 4096, 64, 64, 'PNG', 'RGB', 0, "
                "'zeta portrait', '', '', '', ?, 20, 7.0, '', '', ?, ?)",
                (path, name, BASE_MTIME_NS / 1e9, BASE_MTIME_NS, str(index), now, now),
            )
        rebuild_search_text_index(conn)
        conn.commit()


@pytest.mark.parametrize("limit", (50, 64, 200))
def test_keyset_paging_walks_through_more_tied_rows_than_the_preselect_holds(
    isolated_gallery_root: Path, limit: int
) -> None:
    rows = 700
    _build_tie_corpus(isolated_gallery_root, rows)
    page = search_index("z", "all", None, limit, None)
    ids = [row["asset_id"] for row in page["media"]]
    while page["next_cursor"]:
        page = search_index("z", "all", None, limit, page["next_cursor"])
        ids.extend(row["asset_id"] for row in page["media"])
    assert len(ids) == len(set(ids)) == rows
    assert ids == sorted(ids)  # equal tier, rank and mtime: ascending asset id
    assert search_index_count("z", "all") == rows


def _single_statement_page(conn: sqlite3.Connection, query: str, limit: int, cursor: dict | None) -> list[sqlite3.Row]:
    """One page of the original plan: every source in one UNION ALL statement (the planner's oracle)."""
    from backend.metadata_store import ranked_search as rs

    params = {
        "page_limit": limit + 1,
        **rs._text_match_params(query),
        "fts_candidate_limit": max(256, (limit + 1) * 4),
        "field_candidate_limit": max(256, (limit + 1) * 4),
    }
    if cursor is not None:
        params.update(
            cursor_tier=cursor["tier"],
            cursor_rank=cursor["rank"],
            cursor_rank_bin=round(cursor["rank"] * 1_000_000),
            cursor_mtime_ns=cursor["mtime_ns"],
            cursor_asset_id=cursor["asset_id"],
        )
    selects = rs._candidate_selects(
        query, "", include_fts=True, include_videos=True, bounded_candidates=True, has_cursor=cursor is not None
    )
    return list(
        conn.execute(rs.build_candidate_page_query(selects, has_cursor=cursor is not None, legacy_offset=False), params)
    )


def _encode_cursor(cursor: dict, query: str) -> str:
    from backend.metadata_store import ranked_search as rs

    row = {
        "asset_id": cursor["asset_id"],
        "mtime_ns": cursor["mtime_ns"],
        "rank": cursor["rank"],
        "relevance_tier": cursor["tier"],
    }
    return rs.encode_search_cursor(row, rs.request_fingerprint(query, "all", None, fielded=False))  # type: ignore[arg-type]


@pytest.mark.parametrize("query", ("a", "m", "c", "s", "i", "ca", "mi", "alph", "mang", "cedar river"))
@pytest.mark.parametrize("dense_files", (False, True))
def test_page_plan_returns_the_pages_of_the_single_statement_plan(
    corpus: Path, monkeypatch: pytest.MonkeyPatch, query: str, dense_files: bool
) -> None:
    from backend.metadata_store import _connect_read
    from backend.metadata_store import ranked_search as rs

    if dense_files:
        monkeypatch.setattr(rs, "FILE_SOURCE_SMALL_LIMIT", 3)
    limit = 30
    with closing(_connect_read()) as conn:
        cursor = None
        for page_number in range(40):
            oracle = _single_statement_page(conn, query, limit, cursor)
            planned, _more, _fingerprint = rs.search_ranked_media_page(
                conn, query, "all", None, limit, None if cursor is None else _encode_cursor(cursor, query)
            )
            expected = [(r["asset_id"], r["relevance_tier"], r["rank"], r["mtime_ns"]) for r in oracle[:limit]]
            assert [(r["asset_id"], r["relevance_tier"], r["rank"], r["mtime_ns"]) for r in planned] == expected, (
                query,
                page_number,
            )
            if len(oracle) <= limit or dense_files:
                # Bounded filename variants pre-filter by the cursor (see ARCHITECTURE.md, Search planning): their
                # rows before the cursor no longer shadow later rows of the same asset, so only page 1 is exact.
                break
            last = oracle[limit - 1]
            cursor = {
                "tier": int(last["relevance_tier"]),
                "rank": float(last["rank"]),
                "mtime_ns": int(last["mtime_ns"]),
                "asset_id": int(last["asset_id"]),
            }


@pytest.mark.parametrize(
    ("query", "scan_marker", "probe_marker"),
    (
        ("prompt:c", "m.id IN (SELECT scan_f.metadata_id", "EXISTS (SELECT 1 FROM image_metadata_fold AS fold_f"),
        ("name:i", "m.path IN (SELECT scan_fi.path", "EXISTS (SELECT 1 FROM file_index AS fold_fi"),
    ),
)
def test_probe_friendly_short_filters_render_per_row_probes_not_scan_sets(
    query: str, scan_marker: str, probe_marker: str
) -> None:
    from backend.fielded_search_parser import build_fielded_conditions, parse_fielded_query

    parsed = parse_fielded_query(query)
    scan_conditions, scan_params = build_fielded_conditions(parsed)
    probe_conditions, probe_params = build_fielded_conditions(parsed, probe_friendly=True)
    assert scan_marker in " ".join(scan_conditions)
    assert probe_marker in " ".join(probe_conditions)
    assert scan_marker not in " ".join(probe_conditions)
    assert scan_params == probe_params  # the same named parameters serve both renderings
