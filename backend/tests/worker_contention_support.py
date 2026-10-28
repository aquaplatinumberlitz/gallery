"""Shared seeding and capture helpers for the worker-contention regression modules.

Not a test module: pytest does not collect it (name does not start with ``test_``).
Used by the ``test_worker_contention_wk0*.py`` modules. Everything here is
deterministic: rows are seeded with explicit values, SQL is observed through
``sqlite3.Connection.set_trace_callback``, and time is a controllable fake clock,
never a sleep.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

VARIANTS: tuple[tuple[str, str, int, int], ...] = (
    ("thumbnail", "thumb_128", 128, 82),
    ("thumbnail", "thumb_512", 512, 85),
    ("preview", "preview_1440", 1440, 85),
)
SEED_MTIME_BASE_NS = 1_700_000_000_000_000_000


def seed_library(root: Path, *, name: str = "Contention") -> int:
    """Create one library through the public API and return its id."""
    from backend.metadata_store import create_library

    return int(create_library([root], name=name)["id"])


def seed_assets(
    db_path: Path,
    library_id: int,
    root: Path,
    count: int,
    *,
    start: int = 0,
    metadata_state: str = "pending",
) -> list[tuple[int, str, int, int]]:
    """Insert ``count`` active image assets and return ``(id, path, mtime_ns, size)``."""
    rows: list[tuple[int, str, int, int]] = []
    with sqlite3.connect(db_path) as conn:
        for index in range(start, start + count):
            path = str(root / f"seed_{index:05d}.png")
            mtime_ns = SEED_MTIME_BASE_NS + index * 1_000_000
            size = 1_000 + index
            cursor = conn.execute(
                """
                INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, metadata_state)
                VALUES (?, ?, ?, ?, 'image', ?, ?, ?)
                """,
                (library_id, path, str(root), Path(path).name, mtime_ns, size, metadata_state),
            )
            rows.append((int(cursor.lastrowid), path, mtime_ns, size))
    return rows


def seed_derivative_corpus(
    db_path: Path,
    assets: list[tuple[int, str, int, int]],
    *,
    jobs_per_derivative: int,
    latest_states: tuple[str, ...] = ("done", "queued", "running", "failed", "skipped"),
    derivative_status: str | Mapping[str, str] = "ready",
    byte_size: int = 4_096,
) -> tuple[int, dict[str, int]]:
    """Seed ``asset_derivatives`` + ``derivative_jobs`` for every asset and variant.

    Each derivative receives ``jobs_per_derivative`` job rows; every row but the
    last is ``done``/``failed`` history and the last row (highest id) carries a
    state rotated through ``latest_states``. Returns the total job-row count and
    the expected ``{state: count}`` of the *latest* job per current derivative,
    which is what ``build_global_runtime`` aggregates.
    """
    expected_latest: dict[str, int] = {}
    total_jobs = 0
    with sqlite3.connect(db_path) as conn:
        counter = 0
        for asset_id, _path, mtime_ns, size in assets:
            for kind, variant, max_edge, quality in VARIANTS:
                latest = latest_states[counter % len(latest_states)]
                counter += 1
                status = derivative_status if isinstance(derivative_status, str) else derivative_status[latest]
                cursor = conn.execute(
                    """
                    INSERT INTO asset_derivatives (
                      asset_id, kind, variant, source_mtime_ns, source_size, format, quality,
                      max_long_edge, status, cache_path, byte_size
                    ) VALUES (?, ?, ?, ?, ?, 'webp', ?, ?, ?, NULL, ?)
                    """,
                    (asset_id, kind, variant, mtime_ns, size, quality, max_edge, status, byte_size),
                )
                derivative_id = int(cursor.lastrowid)
                history = [("done" if n % 2 == 0 else "failed") for n in range(jobs_per_derivative - 1)]
                for state in [*history, latest]:
                    conn.execute(
                        "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, ?)",
                        (derivative_id, state),
                    )
                    total_jobs += 1
                expected_latest[latest] = expected_latest.get(latest, 0) + 1
    return total_jobs, expected_latest


@contextmanager
def capture_sql(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every statement executed on connections opened while the context is active."""
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", traced_connect)
        yield statements


def query_plan(db_path: Path, statement: str) -> str:
    """Return the joined ``EXPLAIN QUERY PLAN`` detail text for ``statement``."""
    with sqlite3.connect(db_path) as conn:
        return "\n".join(str(row[3]) for row in conn.execute(f"EXPLAIN QUERY PLAN {statement}"))


def run_while_db_lock_held(fn: Callable[[], Any], *, timeout: float = 2.0) -> tuple[bool, Any, BaseException | None]:
    """Run ``fn`` on a worker thread while another thread owns ``_DB_LOCK``.

    Returns ``(finished_within_timeout, result, error)``. The lock holder is
    released after ``timeout`` so a function that needs ``_DB_LOCK`` is observed
    as blocked (``finished_within_timeout`` is False) and then drains cleanly.
    """
    from backend.metadata_store import _DB_LOCK

    acquired = threading.Event()
    release = threading.Event()
    outcome: dict[str, Any] = {}
    finished = threading.Event()

    def holder() -> None:
        with _DB_LOCK:
            acquired.set()
            release.wait()

    def runner() -> None:
        try:
            outcome["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
            outcome["error"] = exc
        finally:
            finished.set()

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    assert acquired.wait(5), "lock holder never acquired _DB_LOCK"
    runner_thread = threading.Thread(target=runner, daemon=True)
    runner_thread.start()
    completed_in_time = finished.wait(timeout)
    release.set()
    holder_thread.join(10)
    runner_thread.join(30)
    return completed_in_time, outcome.get("result"), outcome.get("error")


class FakeClock:
    """Controllable replacement for the metadata queue clock (seconds since the epoch)."""

    def __init__(self, start: float | None = None) -> None:
        """Start at ``start`` (default: the real current time, so rows stay plausible)."""
        self.now = time.time() if start is None else float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        """Move the clock forward and return the new time."""
        self.now += seconds
        return self.now


def install_metadata_clock(monkeypatch: pytest.MonkeyPatch, start: float | None = None) -> FakeClock:
    """Replace ``metadata_queue.metadata_now`` so leases, backoff, and recovery are time-controlled."""
    import backend.metadata_store.metadata_queue as metadata_queue

    clock = FakeClock(start)
    monkeypatch.setattr(metadata_queue, "metadata_now", clock)
    return clock


def seed_queued_metadata_jobs(root: Path, count: int, *, library_name: str = "Contention") -> tuple[int, list[Path]]:
    """Create a library over ``root``, ``count`` indexed PNGs, and one queued metadata job per image."""
    from backend.metadata_store import _persist_metadata_index_jobs, create_library, index_file
    from tests.conftest import create_test_png

    root.mkdir(parents=True, exist_ok=True)
    library_id = int(create_library([root], name=library_name)["id"])
    images: list[Path] = []
    for index in range(count):
        image = root / f"job_{index:03d}.png"
        create_test_png(image, size=(16, 16))
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 16, 16)
        images.append(image.resolve())
    result = _persist_metadata_index_jobs(images, root)
    assert len(result.enqueued) == count
    return library_id, images


def metadata_job_row(db_path: Path, path: Path | str) -> dict[str, Any]:
    """Return the ``metadata_index_jobs`` row for ``path`` as a plain dict."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM metadata_index_jobs WHERE path = ?", (str(path),)).fetchone()
    assert row is not None, f"no metadata_index_jobs row for {path}"
    return dict(row)


def set_metadata_job(db_path: Path, path: Path | str, **columns: Any) -> None:
    """Overwrite columns of one ``metadata_index_jobs`` row (test seeding only)."""
    assignments = ", ".join(f"{name} = ?" for name in columns)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE metadata_index_jobs SET {assignments} WHERE path = ?", (*columns.values(), str(path)))


def wait_until(predicate: Callable[[], Any], *, timeout: float = 10.0, interval: float = 0.002) -> bool:
    """Poll ``predicate`` until it is truthy or ``timeout`` elapses; returns the final truthiness.

    Only used to observe that another thread reached a known state (for example "is blocked in
    submit"); correctness never depends on how long the wait took.
    """
    deadline = time.monotonic() + timeout
    pause = threading.Event()
    while time.monotonic() < deadline:
        if predicate():
            return True
        pause.wait(interval)
    return bool(predicate())


# ---------------------------------------------------------------------------
# Database writer observation (Phase 2 modules)
# ---------------------------------------------------------------------------

WRITER_THREAD_NAME = "gallery-db-writer"
_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def install_submit_spy(monkeypatch: pytest.MonkeyPatch) -> list[SimpleNamespace]:
    """Record every external submission to the shared writer: caller thread, lane, `_DB_LOCK` ownership."""
    import backend.metadata_store.db_writer as db_writer
    from backend.metadata_store import _DB_LOCK

    writer = db_writer.database_writer
    writer.start()
    log: list[SimpleNamespace] = []
    real_submit = writer.submit

    def spy(op: Callable[[sqlite3.Connection], Any], *, lane: str = "normal", **kwargs: Any) -> Any:
        if not writer.in_writer_thread():
            log.append(
                SimpleNamespace(
                    thread=threading.current_thread().name,
                    lane=lane,
                    holds_db_lock=_DB_LOCK.is_owned(),
                    op=getattr(op, "__qualname__", repr(op)),
                )
            )
        return real_submit(op, lane=lane, **kwargs)

    monkeypatch.setattr(writer, "submit", spy)
    return log


class RecordingConnection:
    """Delegate to a real writer connection and record the statements of every writer op.

    Statements between ``SAVEPOINT gw_op`` and its release or rollback form one op; ``executemany``
    contributes one entry per row so "rows written by one op" can be bounded. ``commits`` counts
    ``COMMIT`` statements. ``fail_commit`` (a callable returning an exception or ``None``) injects
    commit failures.
    """

    def __init__(self, real: sqlite3.Connection, owner: RecordingWriter) -> None:
        self._real = real
        self._owner = owner

    def execute(self, sql: str, *params: Any) -> sqlite3.Cursor:
        text = sql.strip()
        upper = text.upper()
        if upper == "COMMIT":
            error = self._owner.commit_error()
            if error is not None:
                raise error
            self._owner.commits += 1
        self._owner.record(text)
        return self._real.execute(sql, *params)

    def executemany(self, sql: str, seq: Any) -> sqlite3.Cursor:
        rows = list(seq)
        for _ in rows:
            self._owner.record(sql.strip())
        return self._real.executemany(sql, rows)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class RecordingWriter:
    """A private ``DatabaseWriter`` whose connection records statements per op (see ``RecordingConnection``)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, batch_max: int | None = None) -> None:
        import backend.metadata_store.db_writer as db_writer
        from backend.metadata_store._db import _connect

        self.ops: list[list[str]] = []
        self.commits = 0
        self.commit_failures: list[BaseException] = []
        self._current: list[str] | None = None

        def connect() -> RecordingConnection:
            conn = _connect()
            conn.isolation_level = None
            return RecordingConnection(conn, self)

        kwargs: dict[str, Any] = {} if batch_max is None else {"batch_max": batch_max}
        self.writer = db_writer.DatabaseWriter(connect=connect, retry_delays=(), sleep=lambda _s: None, **kwargs)
        self.writer.start()
        monkeypatch.setattr(db_writer, "database_writer", self.writer)

    def commit_error(self) -> BaseException | None:
        return self.commit_failures.pop(0) if self.commit_failures else None

    def record(self, text: str) -> None:
        upper = text.upper()
        if upper == "SAVEPOINT GW_OP":
            self._current = []
            self.ops.append(self._current)
        elif upper in {"RELEASE GW_OP", "ROLLBACK TO GW_OP"}:
            self._current = None
        elif self._current is not None:
            self._current.append(text)

    def writes_per_op(self, *needles: str) -> list[int]:
        """Return, per op, the number of write statements whose text contains every needle."""
        return [
            sum(
                1
                for statement in statements
                if statement.upper().startswith(_WRITE_VERBS) and all(needle in statement for needle in needles)
            )
            for statements in self.ops
        ]

    def stop(self) -> None:
        self.writer.stop(timeout=5)


@contextmanager
def capture_write_threads(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str]]]:
    """Record ``(thread name, statement)`` for every write statement run on a connection opened meanwhile."""
    writes: list[tuple[str, str]] = []
    real_connect = sqlite3.connect

    def traced_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)

        def trace(statement: str) -> None:
            text = statement.strip()
            if text.upper().startswith(_WRITE_VERBS):
                writes.append((threading.current_thread().name, text))

        conn.set_trace_callback(trace)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", traced_connect)
        yield writes
