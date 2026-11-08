"""CJK bigram index for short prompt search terms.

Purpose:
SQLite's ``unicode61`` tokenizer keeps an unspaced CJK run (``桜の下の少女``) as one token, and the
``trigram`` tokenizer cannot answer substrings shorter than three characters. This module maintains
``image_metadata_cjk`` (one row per prompt that contains CJK text) and its external-content FTS5 table
``image_metadata_fts_cjk``. Each CJK run is stored as overlapping bigrams plus a one-character tail
token, so a 1-2 character CJK word becomes a bigram/unigram prefix lookup and a longer CJK token becomes a
bigram phrase.

Guarantees:
* ``cjk_runs``/``CJK_RUN_RE`` are the single definition of a CJK run for indexing and querying.
* Rows exist only for prompts with CJK text, so Latin-only libraries pay no storage.
* The FTS table follows ``image_metadata_cjk`` through triggers; ``image_metadata_cjk`` follows
  ``image_metadata`` deletes through a trigger and prompt writes through ``sync_cjk_row``.

Run when:
* writing ``image_metadata.prompt``/``negative_prompt`` outside ``metadata_persist`` (call
  ``rebuild_cjk_index`` afterwards), or changing short-token search semantics.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

# Han, kana, prolonged-sound mark, half-width katakana and ideographic iteration marks. Hangul is
# space-delimited, so Unicode FTS token prefixes already cover it. Punctuation (、。・) ends a run
# because it is not a word character in either the indexed text or a query token.
_CJK_CLASS = "々〆ぁ-ゖゝゞァ-ヺー-ヿㇰ-ㇿ㐀-䶿一-鿿豈-﫿ｦ-ﾝ\U00020000-\U0003134f"
CJK_RUN_RE = re.compile(f"[{_CJK_CLASS}]+")
_TOKEN_RE = re.compile(r"[\w.-]+", flags=re.UNICODE)

CJK_ROW_TABLE = "image_metadata_cjk"
CJK_FTS_TABLE = "image_metadata_fts_cjk"


def cjk_runs(text: str | None) -> list[str]:
    """Return the CJK runs of ``text`` in order."""
    return CJK_RUN_RE.findall(text) if text else []


def cjk_bigram_document(text: str | None) -> str:
    """Return the space-joined bigram/tail tokens that index ``text``'s CJK runs ('' when it has none)."""
    tokens: list[str] = []
    for run in cjk_runs(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        tokens.append(run[-1])
    return " ".join(tokens)


def _escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


@dataclass(frozen=True)
class ShortQueryPlan:
    """A query split into Latin prefix terms and CJK bigram terms (AND semantics across all of them)."""

    latin_terms: tuple[str, ...]
    cjk_terms: tuple[str, ...]

    @property
    def latin_match(self) -> str:
        """FTS5 expression of token prefixes for the Unicode FTS table."""
        return " AND ".join(f"{_escape(term)}*" for term in self.latin_terms)

    @property
    def cjk_match(self) -> str:
        """FTS5 expression of bigram phrases and one-character prefixes for the CJK FTS table."""
        parts: list[str] = []
        for run in self.cjk_terms:
            if len(run) == 1:
                parts.append(f"{_escape(run)}*")
            else:
                parts.append(_escape(cjk_bigram_document(run).rsplit(" ", 1)[0]))
        return " AND ".join(parts)


def plan_short_query(query: str) -> ShortQueryPlan | None:
    """Split a query whose tokens are not all trigram-length; ``None`` when it has no word tokens."""
    latin: list[str] = []
    cjk: list[str] = []
    for token in _TOKEN_RE.findall(query):
        cjk.extend(CJK_RUN_RE.findall(token))
        latin.extend(segment for segment in CJK_RUN_RE.split(token) if segment)
    if not latin and not cjk:
        return None
    return ShortQueryPlan(tuple(latin), tuple(cjk))


def sync_cjk_row(conn: sqlite3.Connection, metadata_id: int, prompt: str | None, negative_prompt: str | None) -> None:
    """Make ``image_metadata_cjk`` match one metadata row (insert, update or delete)."""
    prompt_doc = cjk_bigram_document(prompt)
    negative_doc = cjk_bigram_document(negative_prompt)
    if not prompt_doc and not negative_doc:
        conn.execute(f"DELETE FROM {CJK_ROW_TABLE} WHERE metadata_id = ?", (metadata_id,))
        return
    conn.execute(
        f"""
        INSERT INTO {CJK_ROW_TABLE}(metadata_id, prompt, negative_prompt) VALUES (?, ?, ?)
        ON CONFLICT(metadata_id) DO UPDATE SET prompt = excluded.prompt, negative_prompt = excluded.negative_prompt
        WHERE prompt IS NOT excluded.prompt OR negative_prompt IS NOT excluded.negative_prompt
        """,
        (metadata_id, prompt_doc, negative_doc),
    )


def sync_cjk_path(conn: sqlite3.Connection, path: str, prompt: str | None, negative_prompt: str | None) -> None:
    """``sync_cjk_row`` for the ``image_metadata`` row stored at ``path`` (the writer-path entry point)."""
    row = conn.execute("SELECT id FROM image_metadata WHERE path = ?", (path,)).fetchone()
    if row is not None:
        sync_cjk_row(conn, int(row[0]), prompt, negative_prompt)


def rebuild_cjk_index(conn: sqlite3.Connection, *, batch_size: int = 2000) -> int:
    """Reconcile ``image_metadata_cjk`` with every ``image_metadata`` row; return the CJK row count.

    Used by the v13 migration backfill and by writers that insert prompts with raw SQL (perf fixtures,
    tests). It is idempotent and only touches rows whose bigram document differs.
    """
    existing = {
        int(row[0]): (row[1], row[2])
        for row in conn.execute(f"SELECT metadata_id, prompt, negative_prompt FROM {CJK_ROW_TABLE}")
    }
    seen: set[int] = set()
    pending: list[tuple[int, str | None, str | None]] = []

    def flush() -> None:
        for metadata_id, prompt, negative_prompt in pending:
            sync_cjk_row(conn, metadata_id, prompt, negative_prompt)
        pending.clear()

    for row in conn.execute("SELECT id, prompt, negative_prompt FROM image_metadata"):
        metadata_id = int(row[0])
        prompt_doc = cjk_bigram_document(row[1])
        negative_doc = cjk_bigram_document(row[2])
        if prompt_doc or negative_doc:
            seen.add(metadata_id)
        if (prompt_doc, negative_doc) != existing.get(metadata_id, ("", "")):
            pending.append((metadata_id, row[1], row[2]))
            if len(pending) >= batch_size:
                flush()
    flush()
    for metadata_id in existing.keys() - seen:
        conn.execute(f"DELETE FROM {CJK_ROW_TABLE} WHERE metadata_id = ?", (metadata_id,))
    return len(seen)
