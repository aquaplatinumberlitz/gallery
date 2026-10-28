"""Retirement of ``ready`` derivatives whose source identity has been superseded."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import suppress
from pathlib import Path

from ..catalog_maintenance_gate import maintenance_producer
from ..config import DERIVATIVE_RECONCILE_YIELD_SECONDS
from ..metadata_store import _connect
from ._common import _ensure_database, logger
from .capacity import CapacityLedger

SUPERSEDED_RESULT_CODE = "source_superseded"
_SUPERSEDED_MESSAGE = "superseded: source identity changed"
_ID_CHUNK = 400
# Rows retired per standalone write transaction; keeps each write-lock hold short even for huge backlogs.
_STANDALONE_ROW_LIMIT = 500

_Retired = tuple[int, str | None]


def _chunks(values: Sequence[int], size: int = _ID_CHUNK) -> Iterator[Sequence[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


class SupersedeMixin:
    """Move ``ready`` derivatives of an old source identity out of the ready set.

    A derivative is superseded when its asset is active and the asset's catalog identity
    (``mtime_ns``/``size``) no longer equals the derivative's ``source_mtime_ns``/``source_size``.
    Such a row stays ``ready`` forever otherwise: it counts toward quota and its file stays on
    disk although nothing can serve it.
    """

    @staticmethod
    def _retire_superseded_in_txn(
        conn: sqlite3.Connection,
        asset_ids: Sequence[int] | None,
        *,
        ledger: CapacityLedger | None = None,
        limit: int | None = None,
        library_id: int | None = None,
        scope_clause: str = "",
        scope_params: Sequence[object] = (),
    ) -> list[_Retired]:
        """Retire superseded ``ready`` rows inside the caller's write transaction.

        Rows become ``skipped`` with their cache fields cleared and their jobs (queued, running, and
        ``done`` history) become ``skipped`` with result code ``source_superseded``; a derivative
        without such a latest job gets one, so a source that later returns to the old identity is
        recognized as retriable. Every retired row's bytes are reported to ``ledger`` (the batch
        ``CapacityLedger``) so quota decisions later in the same transaction see them gone.

        The caller owns the transaction and must unlink the returned files only after it commits.
        Returns ``(derivative_id, cache_path_or_None)`` for every retired row.
        """
        base = """
            SELECT d.id, d.cache_path, d.byte_size
            FROM asset_derivatives d JOIN assets a ON a.id = d.asset_id
            WHERE d.status = 'ready' AND a.deleted_at IS NULL AND a.offline = 0
              AND a.mtime_ns IS NOT NULL AND a.size IS NOT NULL
              AND (d.source_mtime_ns != a.mtime_ns OR d.source_size != a.size)
        """
        rows: list[sqlite3.Row] = []
        if asset_ids is not None:
            for chunk in _chunks(list(asset_ids)):
                remaining = None if limit is None else limit - len(rows)
                if remaining is not None and remaining <= 0:
                    break
                rows.extend(
                    conn.execute(
                        f"{base} AND d.asset_id IN ({','.join('?' for _ in chunk)}) ORDER BY d.id"
                        f"{'' if remaining is None else f' LIMIT {int(remaining)}'}",
                        list(chunk),
                    ).fetchall()
                )
        else:
            params: list[object] = []
            where = ""
            if library_id is not None:
                where += " AND a.library_id = ?"
                params.append(library_id)
            where += scope_clause
            params.extend(scope_params)
            rows = conn.execute(
                f"{base}{where} ORDER BY d.id{'' if limit is None else f' LIMIT {int(limit)}'}", params
            ).fetchall()
        if not rows:
            return []
        ids = [int(row["id"]) for row in rows]
        for chunk in _chunks(ids):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"""
                UPDATE asset_derivatives
                SET status = 'skipped', cache_path = NULL, byte_size = NULL, last_error = ?,
                    updated_at = julianday('now')
                WHERE id IN ({placeholders}) AND status = 'ready'
                """,
                (_SUPERSEDED_MESSAGE, *chunk),
            )
            conn.execute(
                f"""
                UPDATE derivative_jobs
                SET state = 'skipped', result_code = ?, error = ?,
                    claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL,
                    completed_at = julianday('now'), updated_at = julianday('now')
                WHERE derivative_id IN ({placeholders}) AND state IN ('queued', 'running', 'done')
                """,
                (SUPERSEDED_RESULT_CODE, _SUPERSEDED_MESSAGE, *chunk),
            )
            conn.execute(
                f"""
                INSERT INTO derivative_jobs (derivative_id, priority, state, result_code, error, completed_at)
                SELECT d.id, 3, 'skipped', ?, ?, julianday('now')
                FROM asset_derivatives d
                WHERE d.id IN ({placeholders})
                  AND NOT EXISTS (
                    SELECT 1 FROM derivative_jobs j
                    WHERE j.id = (SELECT max(id) FROM derivative_jobs WHERE derivative_id = d.id)
                      AND j.result_code = ?
                  )
                """,
                (SUPERSEDED_RESULT_CODE, _SUPERSEDED_MESSAGE, *chunk, SUPERSEDED_RESULT_CODE),
            )
        if ledger is not None:
            for row in rows:
                ledger.ready_row_left(row["byte_size"])
        return [(int(row["id"]), str(row["cache_path"]) if row["cache_path"] else None) for row in rows]

    @maintenance_producer
    def retire_superseded_derivatives(
        self,
        *,
        library_id: int | None = None,
        scope_path: str | None = None,
        asset_ids: Sequence[int] | None = None,
    ) -> int:
        """Retire every superseded ``ready`` derivative in a scope (default: the whole catalog).

        Runs bounded write transactions (``_STANDALONE_ROW_LIMIT`` rows each) so a backlog of
        thousands of stale rows never holds the SQLite write lock for long, and unlinks each batch's
        files only after that batch committed. Independent of the library warm policy. Returns the
        number of retired rows.
        """
        _ensure_database()
        scope_clause, scope_params = "", ()
        if scope_path is not None:
            from ..metadata_store import get_library_for_path
            from ..metadata_store.path_utils import path_scope_sql

            library = get_library_for_path(scope_path)
            if library is None:
                raise KeyError(scope_path)
            library_id = int(library["id"])
            scope_clause, scope_params = path_scope_sql(
                str(Path(scope_path).resolve()), column="a.path", leading_and=True
            )
        selected_assets = None if asset_ids is None else [int(asset_id) for asset_id in asset_ids]
        self._flush_deferred_unlinks()
        retired_total = 0
        while True:
            with self._eviction_lock:
                with _connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    retired = self._retire_superseded_in_txn(
                        conn,
                        selected_assets,
                        limit=_STANDALONE_ROW_LIMIT,
                        library_id=library_id,
                        scope_clause=scope_clause,
                        scope_params=scope_params,
                    )
                self._discard_retired_files(path for _id, path in retired if path)
            retired_total += len(retired)
            if len(retired) < _STANDALONE_ROW_LIMIT:
                break
            if DERIVATIVE_RECONCILE_YIELD_SECONDS:
                time.sleep(DERIVATIVE_RECONCILE_YIELD_SECONDS)
        if retired_total:
            logger.info("Retired %s superseded ready derivative(s)", retired_total)
        return retired_total

    def _discard_retired_files(self, paths: Iterable[str]) -> None:
        """Unlink files of retired rows after their transaction committed, honouring serving protection.

        A file that is being served is kept and remembered; ``release_serving`` removes it once the
        lease is released. A file being (re)generated, or referenced again by any row, is left alone.
        """
        pending = list(dict.fromkeys(paths))
        if not pending:
            return
        referenced: set[str] = set()
        with _connect() as conn:
            for start in range(0, len(pending), _ID_CHUNK):
                chunk = pending[start : start + _ID_CHUNK]
                referenced.update(
                    str(row[0])
                    for row in conn.execute(
                        f"SELECT cache_path FROM asset_derivatives WHERE cache_path IN ({','.join('?' for _ in chunk)})",
                        chunk,
                    )
                )
        for path in pending:
            with self._file_lock:
                if path in referenced or path in self._generating_paths:
                    continue
                if path in self._served_paths:
                    self._deferred_unlinks.add(path)
                    continue
                with suppress(OSError):
                    Path(path).unlink(missing_ok=True)

    def _finish_deferred_unlink(self, cache_path: str) -> None:
        """Run a deferred unlink once the serving lease for ``cache_path`` has been released."""
        with self._file_lock:
            if cache_path not in self._deferred_unlinks or cache_path in self._served_paths:
                return
            self._deferred_unlinks.discard(cache_path)
            if cache_path in self._generating_paths:
                return
            with _connect() as conn:
                referenced = conn.execute(
                    "SELECT 1 FROM asset_derivatives WHERE cache_path = ? LIMIT 1", (cache_path,)
                ).fetchone()
            if referenced is None:
                with suppress(OSError):
                    Path(cache_path).unlink(missing_ok=True)

    def _flush_deferred_unlinks(self) -> None:
        """Retry deferred unlinks whose serving leases have been released in the meantime."""
        with self._file_lock:
            released = [path for path in self._deferred_unlinks if path not in self._served_paths]
        for path in released:
            self._finish_deferred_unlink(path)
