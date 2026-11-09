"""BL-16: the unscoped page plan must not trust a cut-short preselect's boundary tie group.

Purpose:
A bounded preselect breaks ties on (tier, rank, mtime) by its own row id (metadata id or file rowid) while the page
orders them by asset id. The exact (scoped and fielded) plan covers only the rows strictly before a cut-short
source's last (tier, rank, mtime) and falls back to the exact statement otherwise (SC-01). The unscoped plan has the
same cover rule, derived from the rows its single-statement sources already return.

Guarantees:
* with a tiny bound and 60 rows tied on tier, rank and mtime (metadata ids reversed against asset ids), `cat`, `c`
  and `ca` page exactly like the exact single statement over every keyset page; the corpus is single-source on
  purpose, so the documented cross-source repeats of the unscoped plan cannot appear
* the cover costs no extra statement: distinct mtimes keep the first pages on the bounded plan

Run when:
* changing the unscoped page plan, `_run_page_plan` covers, or the preselect tie-breaks in `ranked_search.py`
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from backend.metadata_store import _connect, register_library
from backend.metadata_store.search_text_index import rebuild_search_text_index

from .test_search_scoped_pins import _exact_page, _row_identity

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")

BASE_MTIME_NS = 1_760_000_000_000_000_000
NOW = 1_760_000_000.0


def _tied_corpus(root: Path, *, count: int = 60, distinct_mtimes: bool = False) -> None:
    (root / "lib").mkdir()
    library_id = int(register_library(root / "lib", name="Ties")["id"])
    folder = root / "lib" / "batch"
    paths = [str(folder / f"img_{index:03d}.png") for index in range(count)]
    mtimes = {
        path: BASE_MTIME_NS + (index * 1_000_000_000 if distinct_mtimes else 0) for index, path in enumerate(paths)
    }
    with closing(_connect()) as conn:
        for path in paths:
            name = Path(path).name
            conn.execute(
                "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
                "indexed_at, metadata_state, offline, deleted_at) "
                "VALUES (?, ?, ?, ?, 'image', ?, 100, 64, 64, ?, 'ready', 0, NULL)",
                (library_id, path, str(folder), name, mtimes[path], NOW),
            )
            conn.execute(
                "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
                "indexed_at, library_id) VALUES (?, ?, ?, 'image', ?, ?, 100, 64, 64, ?, ?)",
                (path, name, str(folder), mtimes[path] / 1e9, mtimes[path], NOW, library_id),
            )
            conn.execute(
                "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
                (name, path, str(folder)),
            )
        for path in reversed(paths):  # metadata ids run against asset ids
            conn.execute(
                "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
                "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
                "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, 100, 64, 64, 'PNG', 'RGB', 0, "
                "'cat castle', '', 'model-a', 'euler a', '1', 20, 7.0, '', '', ?, ?)",
                (path, Path(path).name, mtimes[path] / 1e9, mtimes[path], NOW, NOW),
            )
        rebuild_search_text_index(conn)
        conn.commit()


@pytest.mark.parametrize("query", ("cat", "c", "ca"))
def test_unscoped_cut_short_preselect_keeps_page_order_when_rows_tie_on_rank_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    """Rows tied on tier, rank and mtime past the bound: each unscoped page equals the exact statement's page."""
    from backend.metadata_store import _connect_read
    from backend.metadata_store import ranked_search as rs

    _tied_corpus(tmp_path.resolve())
    monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)  # with limit 5 the bound is 24 rows: the tie group is cut
    limit = 5
    fingerprint = rs.request_fingerprint(query, "all", None, fielded=False, library_id=None)
    with closing(_connect_read()) as conn:
        cursor = None
        pages = 0
        for page_number in range(20):
            oracle = _exact_page(conn, query, ("all", None, None), limit, cursor)
            encoded = (
                None
                if cursor is None
                else rs.encode_search_cursor(
                    {
                        "asset_id": cursor["asset_id"],
                        "mtime_ns": cursor["mtime_ns"],
                        "rank": cursor["rank"],
                        "relevance_tier": cursor["tier"],
                    },  # type: ignore[arg-type]
                    fingerprint,
                )
            )
            planned, more, _fp = rs.search_ranked_media_page(conn, query, "all", None, limit, encoded)
            assert [_row_identity(r) for r in planned] == [_row_identity(r) for r in oracle[:limit]], page_number
            assert more == (len(oracle) > limit), page_number
            pages += 1
            if len(oracle) <= limit:
                break
            last = oracle[limit - 1]
            cursor = {
                "tier": int(last["relevance_tier"]),
                "rank": float(last["rank"]),
                "mtime_ns": int(last["mtime_ns"]),
                "asset_id": int(last["asset_id"]),
            }
        assert pages == 12  # 60 tied rows, five per page


def test_unscoped_cover_does_not_fall_back_when_no_tie_group_is_cut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cover costs no extra statement: distinct mtimes keep the first pages on the bounded plan."""
    from backend.metadata_store import _connect_read
    from backend.metadata_store import ranked_search as rs

    _tied_corpus(tmp_path.resolve(), distinct_mtimes=True)
    monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)
    fallbacks: list[int] = []
    original = rs._run_page_plan

    def recording(*args: object, **kwargs: object):
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        if result is None:
            fallbacks.append(1)
        return result

    monkeypatch.setattr(rs, "_run_page_plan", recording)
    fingerprint = rs.request_fingerprint("cat", "all", None, fielded=False, library_id=None)
    with closing(_connect_read()) as conn:
        cursor = None
        for _page in range(3):
            planned, more, _fp = rs.search_ranked_media_page(conn, "cat", "all", None, 5, cursor)
            assert more and len(planned) == 5
            last = planned[-1]
            cursor = rs.encode_search_cursor(last, fingerprint)
    assert not fallbacks
