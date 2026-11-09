"""Folded search text index maintenance (schema v14).

Purpose:
Keep ``image_metadata_fold`` (folded prompt, negative prompt, model, sampler) and ``file_index_fold``
(folded file name) equal to ``text_fold.fold_text`` of the stored text, so the folded FTS tables that
ranked and fielded search read answer accent-, width- and kana-insensitive queries. Also owns the CJK
bigram rows (``cjk_index``), which are built from the same folded text.

Guarantees:
* ``sync_search_text_*`` are the writer entry points: call them in the transaction that writes
  ``image_metadata`` prompt/negative_prompt/model/sampler or a ``file_index`` name
* rows are removed by triggers when the parent ``image_metadata``/``file_index`` row is deleted, so a
  reused id never inherits stale text
* ``rebuild_search_text_index`` reconciles everything from stored text only (streamed in keyset batches,
  idempotent, touches only rows that differ); it is the v14 backfill and the repair for raw SQL writes

Run when:
* adding a writer of prompt/negative_prompt/model/sampler/file names, or inserting those with raw SQL
  (perf fixtures, tests): call ``rebuild_search_text_index`` afterwards
* changing ``text_fold.fold_text`` (new schema version plus a rebuild)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from ..text_fold import fold_text
from .cjk_index import rebuild_cjk_index, sync_cjk_row

META_FOLD_TABLE = "image_metadata_fold"
FILE_FOLD_TABLE = "file_index_fold"


def _meta_fold(prompt: str | None, negative_prompt: str | None, model: str | None, sampler: str | None) -> tuple:
    return fold_text(prompt), fold_text(negative_prompt), fold_text(model), fold_text(sampler)


def _write_meta_fold(conn: sqlite3.Connection, metadata_id: int, folded: tuple) -> None:
    if not any(folded):
        conn.execute(f"DELETE FROM {META_FOLD_TABLE} WHERE metadata_id = ?", (metadata_id,))
        return
    conn.execute(
        f"""
        INSERT INTO {META_FOLD_TABLE}(metadata_id, prompt, negative_prompt, model, sampler) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(metadata_id) DO UPDATE SET prompt = excluded.prompt,
          negative_prompt = excluded.negative_prompt, model = excluded.model, sampler = excluded.sampler
        WHERE prompt IS NOT excluded.prompt OR negative_prompt IS NOT excluded.negative_prompt
          OR model IS NOT excluded.model OR sampler IS NOT excluded.sampler
        """,
        (metadata_id, *folded),
    )


def sync_search_text_row(
    conn: sqlite3.Connection,
    metadata_id: int,
    prompt: str | None,
    negative_prompt: str | None,
    model: str | None = None,
    sampler: str | None = None,
) -> None:
    """Make the folded and CJK rows match one ``image_metadata`` row (insert, update or delete)."""
    _write_meta_fold(conn, metadata_id, _meta_fold(prompt, negative_prompt, model, sampler))
    sync_cjk_row(conn, metadata_id, prompt, negative_prompt)


def sync_search_text_path(
    conn: sqlite3.Connection,
    path: str,
    prompt: str | None,
    negative_prompt: str | None,
    model: str | None = None,
    sampler: str | None = None,
) -> None:
    """``sync_search_text_row`` for the ``image_metadata`` row stored at ``path`` (the writer entry point)."""
    row = conn.execute("SELECT id FROM image_metadata WHERE path = ?", (path,)).fetchone()
    if row is not None:
        sync_search_text_row(conn, int(row[0]), prompt, negative_prompt, model, sampler)


def sync_file_name_fold(conn: sqlite3.Connection, entries: Iterable[tuple[str, str]]) -> None:
    """Fold the names of existing ``file_index`` rows; ``entries`` are ``(path, name)`` pairs."""
    conn.executemany(
        f"""
        INSERT INTO {FILE_FOLD_TABLE}(file_rowid, name)
        SELECT rowid, ? FROM file_index WHERE path = ?
        ON CONFLICT(file_rowid) DO UPDATE SET name = excluded.name WHERE name IS NOT excluded.name
        """,
        ((fold_text(name), path) for path, name in entries),
    )


def _rebuild_metadata_fold(conn: sqlite3.Connection, batch_size: int) -> int:
    last_id = 0
    count = 0
    while True:
        rows = conn.execute(
            f"""
            SELECT m.id, m.prompt, m.negative_prompt, m.model, m.sampler,
                   f.prompt, f.negative_prompt, f.model, f.sampler
            FROM image_metadata AS m
            LEFT JOIN {META_FOLD_TABLE} AS f ON f.metadata_id = m.id
            WHERE m.id > ?
            ORDER BY m.id
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break
        for row in rows:
            folded = _meta_fold(row[1], row[2], row[3], row[4])
            if any(folded):
                count += 1
            if folded != (tuple(row[5:9]) if row[5] is not None else ("", "", "", "")):
                _write_meta_fold(conn, int(row[0]), folded)
        last_id = int(rows[-1][0])
    conn.execute(f"DELETE FROM {META_FOLD_TABLE} WHERE metadata_id NOT IN (SELECT id FROM image_metadata)")
    return count


def _rebuild_file_fold(conn: sqlite3.Connection, batch_size: int) -> int:
    last_rowid = 0
    count = 0
    while True:
        rows = conn.execute(
            f"""
            SELECT fi.rowid, fi.name, f.name
            FROM file_index AS fi
            LEFT JOIN {FILE_FOLD_TABLE} AS f ON f.file_rowid = fi.rowid
            WHERE fi.rowid > ?
            ORDER BY fi.rowid
            LIMIT ?
            """,
            (last_rowid, batch_size),
        ).fetchall()
        if not rows:
            break
        updates = []
        for row in rows:
            count += 1
            folded = fold_text(row[1])
            if folded != row[2]:
                updates.append((int(row[0]), folded))
        conn.executemany(
            f"""
            INSERT INTO {FILE_FOLD_TABLE}(file_rowid, name) VALUES (?, ?)
            ON CONFLICT(file_rowid) DO UPDATE SET name = excluded.name
            """,
            updates,
        )
        last_rowid = int(rows[-1][0])
    conn.execute(f"DELETE FROM {FILE_FOLD_TABLE} WHERE file_rowid NOT IN (SELECT rowid FROM file_index)")
    return count


def rebuild_search_text_index(conn: sqlite3.Connection, *, batch_size: int = 2000) -> dict[str, int]:
    """Reconcile the folded, CJK and file-name rows with the stored text; return row counts."""
    return {
        "image_metadata_fold": _rebuild_metadata_fold(conn, batch_size),
        "image_metadata_cjk": rebuild_cjk_index(conn, batch_size=batch_size),
        "file_index_fold": _rebuild_file_fold(conn, batch_size),
    }
