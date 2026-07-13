"""
Purpose:
Exercise uncovered search_metadata branches in metadata_store.py — the FTS
OperationalError fallback, the CJK "< 3 chars" shortcut, the
"not rows and not contains_cjk" LIKE fallback, and the FTS happy path — so
backend line coverage stays above the release threshold.

Guarantees:
* search_metadata returns a well-formed result shape with total/results when the
  FTS table is missing (OperationalError fallback to LIKE).
* search_metadata with a short CJK query skips the trigram FTS and falls back
  to LIKE.
* search_metadata with a non-CJK substring that FTS cannot tokenize falls back
  to LIKE via the "not rows and not contains_cjk" branch.
* search_metadata returns rows on a normal FTS match (happy path).

Run when:
* changing search_metadata FTS/LIKE fallback logic
* changing _search_fts / _count_fts / _search_like / _count_like helpers
* switching FTS tokenizers (unicode61 / trigram)
"""

from __future__ import annotations

from pathlib import Path

from backend.metadata_store import (
    _connect,
    index_file,
    initialize_database,
    register_library,
    search_metadata,
    upsert_metadata_result,
)


def _seed_image_with_prompt(tmp_path: Path, filename: str, prompt: str) -> Path:
    """Create a fake image file and upsert metadata with the given prompt."""
    register_library(tmp_path)
    image = tmp_path / filename
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, None, None)
    assert upsert_metadata_result(image, {"prompt": prompt}) is True
    return image


# ---------------------------------------------------------------------------
# sqlite3.OperationalError fallback — drop FTS table, then search
# ---------------------------------------------------------------------------


def test_search_metadata_falls_back_to_like_when_fts_table_missing(isolated_metadata_db: Path, tmp_path: Path):
    """Dropping image_metadata_fts forces _search_fts to raise OperationalError,
    which search_metadata catches and falls back to _search_like."""
    _seed_image_with_prompt(tmp_path, "fts_missing.png", "hello world")

    # Drop the FTS table after initialization so initialize_database() won't
    # recreate it (it early-returns because _DB_INITIALIZED is already True).
    initialize_database()
    with _connect() as conn:
        conn.execute("DROP TABLE image_metadata_fts")

    result = search_metadata("hello")
    assert result["query"] == "hello"
    assert result["total"] >= 1
    assert any(r["path"].endswith("fts_missing.png") for r in result["results"])


# ---------------------------------------------------------------------------
# CJK "< 3 chars" branch — skip trigram FTS, use LIKE directly
# ---------------------------------------------------------------------------


def test_search_metadata_short_cjk_skips_trigram_fts(isolated_metadata_db: Path, tmp_path: Path):
    """A single-char CJK query (len < 3) skips the trigram FTS branch and
    falls back to LIKE."""
    _seed_image_with_prompt(tmp_path, "cjk_short.png", "猫猫图片画廊")

    result = search_metadata("猫")
    assert result["query"] == "猫"
    assert result["total"] >= 1
    assert any(r["path"].endswith("cjk_short.png") for r in result["results"])


# ---------------------------------------------------------------------------
# "not rows and not contains_cjk" LIKE fallback
# ---------------------------------------------------------------------------


def test_search_metadata_non_cjk_substring_falls_back_to_like(isolated_metadata_db: Path, tmp_path: Path):
    """A non-CJK substring that the unicode61 tokenizer cannot match as a whole
    token (e.g. "ello" against indexed "hello world") returns 0 FTS rows,
    triggering the "not rows and not contains_cjk" LIKE fallback."""
    _seed_image_with_prompt(tmp_path, "substring.png", "hello world")

    result = search_metadata("ello")
    assert result["query"] == "ello"
    # FTS won't match the token "ello" but LIKE %ello% matches "hello world"
    assert result["total"] >= 1
    assert any(r["path"].endswith("substring.png") for r in result["results"])


# ---------------------------------------------------------------------------
# FTS happy path — non-CJK query matches via FTS
# ---------------------------------------------------------------------------


def test_search_metadata_fts_match_returns_rows(isolated_metadata_db: Path, tmp_path: Path):
    """A normal non-CJK query that matches an indexed token returns rows via
    FTS without needing the LIKE fallback."""
    _seed_image_with_prompt(tmp_path, "happy.png", "masterpiece landscape")

    result = search_metadata("masterpiece")
    assert result["query"] == "masterpiece"
    assert result["total"] >= 1
    assert any(r["path"].endswith("happy.png") for r in result["results"])
    # The prompt snippet should contain the matched text
    assert "masterpiece" in result["results"][0]["prompt_snippet"]


# ---------------------------------------------------------------------------
# CJK >= 3 chars — trigram FTS path
# ---------------------------------------------------------------------------


def test_search_metadata_long_cjk_uses_trigram_fts(isolated_metadata_db: Path, tmp_path: Path):
    """A CJK query with >= 3 chars exercises the trigram FTS branch."""
    _seed_image_with_prompt(tmp_path, "cjk_long.png", "猫猫图片画廊")

    result = search_metadata("猫图片")
    assert result["query"] == "猫图片"
    assert result["total"] >= 1
    assert any(r["path"].endswith("cjk_long.png") for r in result["results"])


# ---------------------------------------------------------------------------
# Empty / whitespace query early-return
# ---------------------------------------------------------------------------


def test_search_metadata_empty_query_returns_empty(isolated_metadata_db: Path):
    result = search_metadata("")
    assert result == {"query": "", "total": 0, "results": []}


def test_search_metadata_whitespace_query_returns_empty(isolated_metadata_db: Path):
    result = search_metadata("   ")
    assert result == {"query": "   ", "total": 0, "results": []}
