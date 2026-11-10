"""BL-15 A: the ranked-window cache behind keyset search pages never changes a page and never goes stale.

Purpose:
Pin that a keyset page served from the in-process ranked-window cache (`search_window_cache.py`, filled by the
first page of a chain and filtered after the cursor by later pages) equals the page the plan returns without any
cache, that every kind of write that can change a search page invalidates it through the `search_generation`
triggers, and that the cache stays bounded and thread-safe.

Guarantees:
* a chain walked with the cache equals the same chain walked with the cache off, page by page, for the unscoped
  plan and the scoped (exact) plan, with a bound small enough that the cached list runs out mid-chain
* a write of each kind (metadata update, insert and delete; file index size and delete; asset offline, deleted,
  size and mtime; library rename; import path removal; folded text) makes the next page miss the cache and equal
  the exact statement's page; the page really changed, so the check cannot pass vacuously
* the generation bumps on every write to the watched tables (insert, update, delete) and not on writes of columns
  a search never reads (job state, timestamps, scan stamps)
* the cache honours its entry and byte caps with least-recently-used eviction, drops entries of an older
  generation, refuses an entry larger than the byte cap, and survives concurrent readers, writers and searches
* a database re-created at the same path gets a new epoch, so it can never match an older cache entry

Run when:
* changing `search_window_cache.py`, the window code of `ranked_search.py`, the `search_generation` triggers in
  `_schema_ddl.py`, or any writer of the watched tables
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from backend.metadata_store import _connect, _connect_read, update_library
from backend.metadata_store import ranked_search as rs
from backend.metadata_store._schema_ddl import SEARCH_GENERATION_TRIGGER_NAMES
from backend.metadata_store.search_text_index import rebuild_search_text_index
from backend.metadata_store.search_window_cache import SearchWindowCache, WindowEntry, estimate_rows_size

from .test_search_scoped_pins import ORACLE_QUERIES, ORACLE_SCOPES, _exact_page
from .test_search_scoped_pins import _walk as _walk_public
from .test_search_scoped_pins import corpus as scoped_corpus  # noqa: F401  (the SC-01 corpus fixture)
from .test_search_unscoped_tie_cover import BASE_MTIME_NS, NOW, _tied_corpus

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")

LIMIT = 5
SCOPES = ("all", "folder")


@pytest.fixture
def cache(monkeypatch: pytest.MonkeyPatch) -> SearchWindowCache:
    """A fresh process-wide cache and a candidate bound of 24 rows (limit 5), so the cached list is cut short."""
    fresh = SearchWindowCache(64, 16 * 1024 * 1024)
    monkeypatch.setattr(rs, "SEARCH_WINDOW_CACHE", fresh)
    monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)
    return fresh


def _scope_arguments(scope: str, folder: Path, library_id: int) -> tuple[str, str | None, int | None]:
    return ("all", None, None) if scope == "all" else ("folder", str(folder), library_id)


def _page(
    query: str, scope_args: tuple[str, str | None, int | None], cursor_row: sqlite3.Row | None
) -> tuple[list[sqlite3.Row], bool, str]:
    kind, root, library_id = scope_args
    fingerprint = rs.request_fingerprint(query, kind, root, fielded=False, library_id=library_id)
    encoded = None if cursor_row is None else rs.encode_search_cursor(cursor_row, fingerprint)
    with closing(_connect_read()) as conn:
        return rs.search_ranked_media_page(conn, query, kind, root, LIMIT, encoded, library_id=library_id)


def _oracle(query: str, scope_args: tuple[str, str | None, int | None], cursor_row: sqlite3.Row | None):
    cursor = (
        None
        if cursor_row is None
        else {
            "tier": int(cursor_row["relevance_tier"]),
            "rank": float(cursor_row["rank"]),
            "mtime_ns": int(cursor_row["mtime_ns"]),
            "asset_id": int(cursor_row["asset_id"]),
        }
    )
    with closing(_connect_read()) as conn:
        return _exact_page(conn, query, scope_args, LIMIT, cursor)


_COLUMNS = (
    "path",
    "name",
    "type",
    "parent_path",
    "mtime",
    "mtime_ns",
    "asset_size",
    "width",
    "height",
    "duration_ms",
    "mime_type",
    "asset_id",
    "library_id",
    "library_name",
    "relevance_tier",
    "rank",
    "match_type",
    "prompt_snippet",
    "model",
    "sampler",
    "seed",
)


def _full(rows: list[sqlite3.Row]) -> list[tuple]:
    """Every column of the candidate rows (the exact statement adds a dedup column the plan does not carry)."""
    return [tuple(row[column] for column in _COLUMNS) for row in rows]


def _walk(query: str, scope_args: tuple[str, str | None, int | None], pages: int = 12) -> list[list[tuple]]:
    result: list[list[tuple]] = []
    cursor_row = None
    for _ in range(pages):
        rows, more, _fingerprint = _page(query, scope_args, cursor_row)
        result.append(_full(rows))
        if not more:
            break
        cursor_row = rows[-1]
    return result


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("query", ("cat", "c", "ca"))
def test_chain_with_the_cache_equals_the_chain_without_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache: SearchWindowCache, scope: str, query: str
) -> None:
    library_id, folder, _paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    scope_args = _scope_arguments(scope, folder, library_id)
    cached_chain = _walk(query, scope_args)
    assert cache.stats()["hits"] > 0  # the chain really was served from the cache
    assert len(cached_chain) == 12
    cache.clear()
    monkeypatch.setattr(rs, "SEARCH_WINDOW_CACHE", SearchWindowCache(0, 0))
    assert cached_chain == _walk(query, scope_args)
    # and both equal the exact statement, page by page
    cursor_row = None
    for page in cached_chain:
        oracle = _oracle(query, scope_args, cursor_row)
        assert page == _full(oracle[:LIMIT])
        cursor_row = oracle[LIMIT - 1] if len(oracle) > LIMIT else None


def test_a_cut_short_source_that_lost_rows_to_the_strict_joins_is_never_cached_as_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache: SearchWindowCache
) -> None:
    """Offline matches inside the bound shorten the unscoped statement's rows below the bound.

    The unscoped plan cannot see that its preselect was cut short (a documented limit), but a cache must not turn
    that into a wrong page: the chain with the cache equals the chain the plan returns without it.
    """
    library_id, folder, paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    with closing(_connect()) as conn:
        for index in (59, 57, 40, 36):  # newest rows: inside the first bound of 24
            conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (paths[index],))
        conn.commit()
    scope_args = _scope_arguments("all", folder, library_id)
    cached_chain = _walk("cat", scope_args)
    monkeypatch.setattr(rs, "SEARCH_WINDOW_CACHE", SearchWindowCache(0, 0))
    assert cached_chain == _walk("cat", scope_args)


@pytest.mark.parametrize("tight", (False, True), ids=("default-bound", "tiny-bound"))
def test_public_chains_over_the_scoped_corpus_equal_the_uncached_chains(
    scoped_corpus: tuple[Path, dict[int, int]],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tight: bool,
) -> None:
    """Every (scope, query) chain of the SC-01 corpus through the public API: cache on equals cache off."""
    root, library_ids = scoped_corpus
    if tight:
        monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)
        monkeypatch.setattr(rs, "FILE_SOURCE_SMALL_LIMIT", 3)
    limit = 5 if tight else 40
    queries = (*ORACLE_QUERIES, "ca", "mount", "an")
    scopes = (*ORACLE_SCOPES, "library2", "deep")
    fresh = SearchWindowCache(256, 64 * 1024 * 1024)
    cached: dict[tuple[str, str], list[dict]] = {}
    monkeypatch.setattr(rs, "SEARCH_WINDOW_CACHE", fresh)
    for scope_name in scopes:
        for query in queries:
            cached[(scope_name, query)] = _walk_public(root, library_ids, scope_name, query, limit)[0]
    assert fresh.stats()["hits"] > 0
    monkeypatch.setattr(rs, "SEARCH_WINDOW_CACHE", SearchWindowCache(0, 0))
    for scope_name in scopes:
        for query in queries:
            plain = _walk_public(root, library_ids, scope_name, query, limit)[0]
            assert cached[(scope_name, query)] == plain, (scope_name, query, tight)


def test_cursor_before_the_cached_bound_reads_again(tmp_path: Path, cache: SearchWindowCache) -> None:
    """Going back to an earlier cursor after a later page replaced the entry is a miss, not a wrong page."""
    library_id, folder, _paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    scope_args = _scope_arguments("all", folder, library_id)
    first, _more, _fp = _page("cat", scope_args, None)
    second, _more, _fp = _page("cat", scope_args, first[-1])
    # Walk far enough that the cached list (24 rows) is exhausted and replaced by a list that starts later.
    cursor_row = second[-1]
    for _ in range(6):
        rows, more, _fp = _page("cat", scope_args, cursor_row)
        if not more:
            break
        cursor_row = rows[-1]
    again, _more, _fp = _page("cat", scope_args, first[-1])
    assert _full(again) == _full(second)


def _add_image(conn: sqlite3.Connection, library_id: int, folder: Path, name: str, mtime_ns: int) -> str:
    path = str(folder / name)
    conn.execute(
        "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
        "indexed_at, metadata_state, offline, deleted_at) "
        "VALUES (?, ?, ?, ?, 'image', ?, 100, 64, 64, ?, 'ready', 0, NULL)",
        (library_id, path, str(folder), name, mtime_ns, NOW),
    )
    conn.execute(
        "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
        "indexed_at, library_id) VALUES (?, ?, ?, 'image', ?, ?, 100, 64, 64, ?, ?)",
        (path, name, str(folder), mtime_ns / 1e9, mtime_ns, NOW, library_id),
    )
    conn.execute(
        "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
        (name, path, str(folder)),
    )
    conn.execute(
        "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
        "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
        "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, 100, 64, 64, 'PNG', 'RGB', 0, "
        "'cat castle', '', 'model-a', 'euler a', '1', 20, 7.0, '', '', ?, ?)",
        (path, name, mtime_ns / 1e9, mtime_ns, NOW, NOW),
    )
    return path


class _Context:
    def __init__(self, library_id: int, folder: Path, target: str, neighbour_mtime_ns: int) -> None:
        self.library_id = library_id
        self.folder = folder
        self.target = target  # a path on the second page
        self.neighbour_mtime_ns = neighbour_mtime_ns  # an mtime inside the second page's range


def _w_metadata_update(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE image_metadata SET prompt = 'dog castle' WHERE path = ?", (ctx.target,))


def _w_metadata_delete(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("DELETE FROM image_metadata WHERE path = ?", (ctx.target,))


def _w_metadata_insert(conn: sqlite3.Connection, ctx: _Context) -> None:
    _add_image(conn, ctx.library_id, ctx.folder, "img_new.png", ctx.neighbour_mtime_ns + 1)
    rebuild_search_text_index(conn)  # the folded text rows a real indexer writes with the metadata


def _w_file_index_size(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE file_index SET size = size + 1 WHERE path = ?", (ctx.target,))


def _w_file_index_delete(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("DELETE FROM file_index_fts WHERE path = ?", (ctx.target,))
    conn.execute("DELETE FROM file_index WHERE path = ?", (ctx.target,))


def _w_asset_offline(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (ctx.target,))


def _w_asset_deleted(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE assets SET deleted_at = ? WHERE path = ?", (NOW, ctx.target))


def _w_asset_size(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE assets SET size = size + 1 WHERE path = ?", (ctx.target,))


def _w_asset_mtime(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE assets SET mtime_ns = mtime_ns + 1 WHERE path = ?", (ctx.target,))


def _w_library_rename(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("UPDATE libraries SET name = 'Renamed' WHERE id = ?", (ctx.library_id,))


def _w_import_path_removed(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute("DELETE FROM library_import_paths WHERE library_id = ?", (ctx.library_id,))


def _w_fold_text(conn: sqlite3.Connection, ctx: _Context) -> None:
    conn.execute(
        "UPDATE image_metadata_fold SET prompt = 'zzz' "
        "WHERE metadata_id = (SELECT id FROM image_metadata WHERE path = ?)",
        (ctx.target,),
    )


WRITES = {
    "metadata-update": _w_metadata_update,
    "metadata-delete": _w_metadata_delete,
    "metadata-insert": _w_metadata_insert,
    "file-index-size": _w_file_index_size,
    "file-index-delete": _w_file_index_delete,
    "asset-offline": _w_asset_offline,
    "asset-deleted": _w_asset_deleted,
    "asset-size": _w_asset_size,
    "asset-mtime": _w_asset_mtime,
    "library-rename": _w_library_rename,
    "import-path-removed": _w_import_path_removed,
    "folded-text": _w_fold_text,
}


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("kind", sorted(WRITES))
def test_every_kind_of_write_invalidates_the_cached_window(
    tmp_path: Path, cache: SearchWindowCache, scope: str, kind: str
) -> None:
    library_id, folder, _paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    scope_args = _scope_arguments(scope, folder, library_id)
    first, _more, _fp = _page("cat", scope_args, None)
    cursor_row = first[-1]
    before, _more, _fp = _page("cat", scope_args, cursor_row)
    hits = cache.stats()["hits"]
    again, _more, _fp = _page("cat", scope_args, cursor_row)
    assert cache.stats()["hits"] > hits  # served from the cache until something is written
    assert _full(again) == _full(before)

    ctx = _Context(library_id, folder, str(before[1]["path"]), int(before[1]["mtime_ns"]))
    with closing(_connect()) as conn:
        WRITES[kind](conn, ctx)
        conn.commit()

    hits = cache.stats()["hits"]
    after, _more, _fp = _page("cat", scope_args, cursor_row)
    assert cache.stats()["hits"] == hits  # the stale window was not served
    oracle = _oracle("cat", scope_args, cursor_row)
    assert _full(after) == _full(oracle[:LIMIT])
    assert _full(after) != _full(before), "the write must change the page, or this proves nothing"


def test_a_rename_through_the_store_api_invalidates(tmp_path: Path, cache: SearchWindowCache) -> None:
    """The same proof through a real writer path (the database writer when it is on)."""
    library_id, folder, _paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    scope_args = _scope_arguments("all", folder, library_id)
    first, _more, _fp = _page("cat", scope_args, None)
    before, _more, _fp = _page("cat", scope_args, first[-1])
    assert {row["library_name"] for row in before} == {"Ties"}
    assert update_library(library_id, name="Renamed") is not None
    after, _more, _fp = _page("cat", scope_args, first[-1])
    assert {row["library_name"] for row in after} == {"Renamed"}


def _generation() -> tuple[str, int]:
    with closing(_connect_read()) as conn:
        value = rs._read_search_generation(conn)
    assert value is not None
    return value


def _write(*statements: tuple[str, tuple[Any, ...]]) -> None:
    with closing(_connect()) as conn:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()


def test_triggers_exist_for_every_watched_table_and_operation() -> None:
    with closing(_connect_read()) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert set(SEARCH_GENERATION_TRIGGER_NAMES) <= names
    tables = {name.removeprefix("trg_search_generation_").rsplit("_", 1)[0] for name in SEARCH_GENERATION_TRIGGER_NAMES}
    assert tables == {
        "image_metadata",
        "image_metadata_fold",
        "image_metadata_cjk",
        "file_index_fold",
        "library_import_paths",
        "libraries",
        "file_index",
        "assets",
    }
    for table in tables:
        for operation in ("insert", "update", "delete"):
            assert f"trg_search_generation_{table}_{operation}" in names


def test_generation_bumps_on_insert_update_and_delete_of_every_watched_table(tmp_path: Path) -> None:
    library_id, folder, paths = _tied_corpus(tmp_path.resolve(), count=4, distinct_mtimes=True)
    path = paths[0]
    metadata_id = _scalar("SELECT id FROM image_metadata WHERE path = ?", (path,))
    file_rowid = _scalar("SELECT rowid FROM file_index WHERE path = ?", (path,))
    other_root = tmp_path.resolve() / "other"
    other_root.mkdir()
    steps: list[tuple[str, tuple[tuple[str, tuple[Any, ...]], ...]]] = [
        ("image_metadata update", (("UPDATE image_metadata SET model = 'm2' WHERE id = ?", (metadata_id,)),)),
        (
            "image_metadata_fold update",
            (("UPDATE image_metadata_fold SET model = 'm2' WHERE metadata_id = ?", (metadata_id,)),),
        ),
        ("image_metadata_fold delete", (("DELETE FROM image_metadata_fold WHERE metadata_id = ?", (metadata_id,)),)),
        (
            "image_metadata_fold insert",
            (("INSERT INTO image_metadata_fold(metadata_id, prompt) VALUES (?, 'cat')", (metadata_id,)),),
        ),
        (
            "image_metadata_cjk insert",
            (
                (
                    "INSERT INTO image_metadata_cjk(metadata_id, prompt, negative_prompt) VALUES (?, 'ab', '')",
                    (metadata_id,),
                ),
            ),
        ),
        (
            "image_metadata_cjk update",
            (("UPDATE image_metadata_cjk SET prompt = 'cd' WHERE metadata_id = ?", (metadata_id,)),),
        ),
        ("image_metadata_cjk delete", (("DELETE FROM image_metadata_cjk WHERE metadata_id = ?", (metadata_id,)),)),
        (
            "file_index_fold update",
            (("UPDATE file_index_fold SET name = 'renamed' WHERE file_rowid = ?", (file_rowid,)),),
        ),
        ("file_index_fold delete", (("DELETE FROM file_index_fold WHERE file_rowid = ?", (file_rowid,)),)),
        (
            "file_index_fold insert",
            (("INSERT INTO file_index_fold(file_rowid, name) VALUES (?, 'img')", (file_rowid,)),),
        ),
        ("file_index update", (("UPDATE file_index SET size = size + 1 WHERE path = ?", (path,)),)),
        ("assets animated update", (("UPDATE assets SET animated = 1 WHERE path = ?", (path,)),)),
        ("assets update", (("UPDATE assets SET size = size + 1 WHERE path = ?", (path,)),)),
        (
            "library_import_paths update",
            (("UPDATE library_import_paths SET path = ? WHERE library_id = ?", (str(other_root), library_id)),),
        ),
        (
            "library_import_paths insert",
            (
                (
                    "INSERT INTO library_import_paths(library_id, path, position, created_at, updated_at) "
                    "VALUES (?, ?, 1, 0, 0)",
                    (library_id, str(folder)),
                ),
            ),
        ),
        ("library_import_paths delete", (("DELETE FROM library_import_paths WHERE path = ?", (str(folder),)),)),
        ("libraries update", (("UPDATE libraries SET name = 'N' WHERE id = ?", (library_id,)),)),
        (
            "libraries insert",
            (("INSERT INTO libraries(name, state, created_at, updated_at) VALUES ('Two', 'idle', 0, 0)", ()),),
        ),
        ("libraries delete", (("DELETE FROM libraries WHERE name = 'Two'", ()),)),
        ("image_metadata delete", (("DELETE FROM image_metadata WHERE id = ?", (metadata_id,)),)),
        ("file_index delete", (("DELETE FROM file_index WHERE path = ?", (path,)),)),
        ("assets delete", (("DELETE FROM assets WHERE path = ?", (path,)),)),
    ]
    for label, statements in steps:
        before = _generation()
        _write(*statements)
        after = _generation()
        assert after[0] == before[0], label
        assert after[1] > before[1], f"{label} did not bump the search generation"
    # inserts into the remaining watched tables
    before = _generation()
    _add_row_and_commit(library_id, folder)
    assert _generation()[1] > before[1]


def _scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
    with closing(_connect_read()) as conn:
        return conn.execute(sql, params).fetchone()[0]


def _add_row_and_commit(library_id: int, folder: Path) -> None:
    with closing(_connect()) as conn:
        _add_image(conn, library_id, folder, "img_extra.png", BASE_MTIME_NS + 99)
        conn.commit()


def test_generation_does_not_bump_for_columns_a_search_never_reads(tmp_path: Path) -> None:
    library_id, _folder, paths = _tied_corpus(tmp_path.resolve(), count=4, distinct_mtimes=True)
    path = paths[0]
    before = _generation()
    _write(
        (
            "UPDATE assets SET metadata_state = 'queued', indexed_at = indexed_at + 1, orientation = 6 WHERE path = ?",
            (path,),
        ),
        ("UPDATE file_index SET indexed_at = indexed_at + 1, last_seen_scan_job_id = NULL WHERE path = ?", (path,)),
        (
            "UPDATE libraries SET updated_at = updated_at + 1, last_scan_at = 1, state = 'scanning' WHERE id = ?",
            (library_id,),
        ),
        (
            "UPDATE library_import_paths SET position = position, updated_at = updated_at + 1 WHERE library_id = ?",
            (library_id,),
        ),
        # a rescan that rewrites a file row with the values it already has
        (
            "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
            "indexed_at, library_id) SELECT path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
            "indexed_at + 5, library_id FROM file_index WHERE path = ? "
            "ON CONFLICT(path) DO UPDATE SET name=excluded.name, parent_path=excluded.parent_path, "
            "type=excluded.type, mtime=excluded.mtime, mtime_ns=excluded.mtime_ns, size=excluded.size, "
            "width=excluded.width, height=excluded.height, indexed_at=excluded.indexed_at, "
            "library_id=excluded.library_id",
            (path,),
        ),
    )
    assert _generation() == before


def test_a_database_recreated_at_the_same_path_gets_a_new_epoch(isolated_metadata_db: Path) -> None:
    import backend.metadata_store as ms

    first = _generation()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{isolated_metadata_db}{suffix}").unlink(missing_ok=True)
    ms._db._DB_INITIALIZED = False
    ms.initialize_database()
    second = _generation()
    assert second[0] != first[0]


def test_ensure_is_idempotent_and_keeps_the_generation() -> None:
    from backend.metadata_store._schema_ensure import _ensure_search_generation

    before = _generation()
    with closing(_connect()) as conn:
        _ensure_search_generation(conn)
        _ensure_search_generation(conn)
        conn.commit()
    assert _generation() == before


def _entry(generation: int, rows: int, text: str = "x") -> WindowEntry:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    built = connection.execute("SELECT ? AS text, 1 AS number", (text,)).fetchall() * rows
    connection.close()
    return WindowEntry(
        generation=generation,
        bound=None,
        rows=tuple(built),
        cut_short=False,
        cover=None,
        size=estimate_rows_size(built),
    )


def test_cache_caps_entries_and_bytes_with_least_recently_used_eviction() -> None:
    small = SearchWindowCache(max_entries=3, max_bytes=10_000_000)
    for index in range(3):
        small.put(("e", index), _entry(1, 1))
    assert small.get(("e", 0), 1) is not None  # touch 0: 1 is now the oldest
    small.put(("e", 3), _entry(1, 1))
    assert small.get(("e", 1), 1) is None
    assert [small.get(("e", key), 1) is not None for key in (0, 2, 3)] == [True] * 3
    assert small.stats()["entries"] == 3 and small.stats()["evictions"] == 1

    one = _entry(1, 4).size
    sized = SearchWindowCache(max_entries=100, max_bytes=one * 2 + 1)
    for index in range(5):
        sized.put(("s", index), _entry(1, 4))
    stats = sized.stats()
    assert stats["entries"] == 2 and stats["bytes"] <= one * 2 + 1
    assert sized.get(("s", 4), 1) is not None and sized.get(("s", 0), 1) is None

    assert SearchWindowCache(10, one - 1).enabled
    refuse = SearchWindowCache(10, one - 1)
    refuse.put("big", _entry(1, 4))
    assert refuse.stats()["entries"] == 0  # larger than the byte cap: not stored

    off = SearchWindowCache(0, 100)
    off.put("a", _entry(1, 1))
    assert not off.enabled and off.stats()["entries"] == 0


def test_cache_drops_an_entry_of_another_generation_and_replaces_by_key() -> None:
    store = SearchWindowCache(10, 10_000_000)
    store.put("k", _entry(1, 2))
    assert store.get("k", 2) is None  # stale: dropped, not served
    assert store.stats()["entries"] == 0 and store.stats()["bytes"] == 0
    store.put("k", _entry(2, 2))
    store.put("k", _entry(2, 3))  # replaces, byte accounting stays exact
    assert store.stats()["entries"] == 1
    assert store.stats()["bytes"] == _entry(2, 3).size
    store.clear()
    assert store.stats()["entries"] == 0 and store.stats()["bytes"] == 0


def test_cache_is_thread_safe() -> None:
    store = SearchWindowCache(max_entries=16, max_bytes=2_000_000)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(seed: int) -> None:
        try:
            barrier.wait()
            for index in range(400):
                key = ("t", (seed * 7 + index) % 40)
                generation = 1 + (index // 100) % 2
                if store.get(key, generation) is None:
                    store.put(key, _entry(generation, 2))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(seed,)) for seed in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    stats = store.stats()
    assert stats["entries"] <= 16 and stats["bytes"] <= 2_000_000
    assert stats["bytes"] == sum(entry.size for entry in store._entries.values())


def test_concurrent_searches_and_writes_never_return_a_stale_page(tmp_path: Path, cache: SearchWindowCache) -> None:
    """Readers walking chains while a writer toggles assets: every page equals the exact statement at that moment."""
    library_id, folder, paths = _tied_corpus(tmp_path.resolve(), count=60, distinct_mtimes=True)
    scope_args = _scope_arguments("all", folder, library_id)
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            toggle = 0
            while not stop.is_set():
                path = paths[10 + (toggle % 40)]
                with closing(_connect()) as conn:
                    conn.execute("UPDATE assets SET offline = ? WHERE path = ?", (toggle % 2, path))
                    conn.commit()
                toggle += 1
                time.sleep(0.002)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(15):
                cursor_row = None
                for _page_number in range(6):
                    kind, root, lib = scope_args
                    fingerprint = rs.request_fingerprint("cat", kind, root, fielded=False, library_id=lib)
                    encoded = None if cursor_row is None else rs.encode_search_cursor(cursor_row, fingerprint)
                    # one connection: its snapshot is the instant the planned page and the oracle must agree on
                    with closing(_connect_read()) as conn:
                        conn.execute("BEGIN")
                        rows, more, _fp = rs.search_ranked_media_page(
                            conn, "cat", kind, root, LIMIT, encoded, library_id=lib
                        )
                        cursor = (
                            None
                            if cursor_row is None
                            else {
                                "tier": int(cursor_row["relevance_tier"]),
                                "rank": float(cursor_row["rank"]),
                                "mtime_ns": int(cursor_row["mtime_ns"]),
                                "asset_id": int(cursor_row["asset_id"]),
                            }
                        )
                        oracle = _exact_page(conn, "cat", scope_args, LIMIT, cursor)
                        conn.execute("COMMIT")
                    assert _full(rows) == _full(oracle[:LIMIT])
                    if not more:
                        break
                    cursor_row = rows[-1]
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    write_thread = threading.Thread(target=writer)
    readers = [threading.Thread(target=reader) for _ in range(3)]
    write_thread.start()
    for thread in readers:
        thread.start()
    for thread in readers:
        thread.join()
    stop.set()
    write_thread.join()
    assert not errors, errors[0]
