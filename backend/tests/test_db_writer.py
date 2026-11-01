"""Phase 2.1 regression: the single database writer core (`DatabaseWriter`).

Purpose:
Pin the writer-core contract of the worker lifecycle hardening plan (Phase 2, task 2.1). Background
workers must be able to hand short SQLite writes to one thread that owns one write connection and
applies them in short batched transactions. (Phase 3 retired the process-wide ``_DB_LOCK`` and the
``GALLERY_DB_WRITER_ENABLED`` flag; the writer is the only write path while it runs.)

Guarantees:
Every op runs on one dedicated thread and one connection configured like ``_connect()``; ops are FIFO
within a lane and the ``priority`` lane is drained before ``normal``; ops queued behind a running batch
share one ``BEGIN IMMEDIATE`` transaction bounded by the batch size and the batch time budget, and the
writer never waits for more ops when its queue is empty; an op runs under its own savepoint so a
failing op rolls back only itself and surfaces its own exception while the rest of the batch commits;
a transient ``BEGIN``/``COMMIT`` failure retries the whole batch, an exhausted or non-transient one
fails every op of it, and no Future is ever left unresolved (not even for a ``BaseException``); the
queue is bounded with a blocking, timing-out ``submit``; ``stop()`` drains pending ops within a deadline
and later submits raise immediately; ``submit`` from the writer thread runs inline in the current
transaction; a raising op does not disturb its batch neighbours, the writer commits while a reader holds a
WAL snapshot, ``get_active_writer`` follows the writer lifecycle and never starts it, ``run_write`` never
falls back to the direct path when the writer fails; the app lifespan starts the writer before startup
recovery and every worker and stops it after them; the removed flag is ignored.

Run when:
Changing ``backend/metadata_store/db_writer.py``, the ``GALLERY_DB_WRITER_*`` settings, or the writer
registration in the app lifespan.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.worker_contention_support import wait_until

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


class ScriptedConnection:
    """Delegate to a real connection, recording statements and optionally raising scripted errors.

    ``script(sql)`` returns an exception to raise instead of executing ``sql`` (or ``None``).
    """

    def __init__(self, real: sqlite3.Connection, script: Callable[[str], BaseException | None] | None) -> None:
        self._real = real
        self._script = script
        self.statements: list[str] = []

    def execute(self, sql: str, *params: Any) -> sqlite3.Cursor:
        self.statements.append(sql)
        if self._script is not None:
            error = self._script(sql)
            if error is not None:
                raise error
        return self._real.execute(sql, *params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class Blocker:
    """An op that parks the writer thread inside a transaction until released."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, _conn: sqlite3.Connection) -> str:
        self.entered.set()
        assert self.release.wait(30), "the blocking op was never released"
        return "unblocked"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    path = tmp_path / "writer.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT UNIQUE)")
    return path


@pytest.fixture
def make_writer(db_file: Path):
    """Build started writers over ``db_file``; every connection is a recording ``ScriptedConnection``."""
    writers: list[Any] = []

    def factory(*, script: Callable[[str], BaseException | None] | None = None, **kwargs: Any):
        connections: list[ScriptedConnection] = []

        def connect() -> ScriptedConnection:
            real = sqlite3.connect(db_file, timeout=5, isolation_level=None)
            real.row_factory = sqlite3.Row
            conn = ScriptedConnection(real, script)
            connections.append(conn)
            return conn

        kwargs.setdefault("retry_delays", (0.0, 0.0))
        kwargs.setdefault("batch_ms", 3_600_000)
        kwargs.setdefault("sleep", lambda _seconds: None)
        writer = _module().DatabaseWriter(connect=connect, path_provider=lambda: db_file, **kwargs)
        writer.test_connections = connections
        writer.start()
        writers.append(writer)
        return writer

    yield factory
    for writer in writers:
        writer.stop(timeout=5)


def insert(value: str) -> Callable[[sqlite3.Connection], str]:
    def op(conn: sqlite3.Connection) -> str:
        conn.execute("INSERT INTO t (v) VALUES (?)", (value,))
        return value

    return op


def rows(db_file: Path) -> list[str]:
    with sqlite3.connect(db_file) as conn:
        return [row[0] for row in conn.execute("SELECT v FROM t ORDER BY id")]


def statements(writer: Any) -> list[str]:
    return [sql for conn in writer.test_connections for sql in conn.statements]


def count(writer: Any, sql: str) -> int:
    return statements(writer).count(sql)


def park(writer: Any) -> tuple[Blocker, concurrent.futures.Future]:
    """Park the writer thread inside a running batch; returns the blocker and its Future."""
    blocker = Blocker()
    future = writer.submit(blocker)
    assert blocker.entered.wait(10), "the writer never started the blocking op"
    return blocker, future


# ---------------------------------------------------------------------------
# Threading and connection
# ---------------------------------------------------------------------------


def test_every_op_runs_on_one_dedicated_thread_with_one_connection(make_writer) -> None:
    writer = make_writer()
    seen = [
        writer.submit(lambda conn: (threading.get_ident(), threading.current_thread().name, id(conn))).result(10)
        for _ in range(5)
    ]
    assert len({entry[0] for entry in seen}) == 1
    assert len({entry[2] for entry in seen}) == 1
    assert seen[0][0] != threading.get_ident()
    assert seen[0][1] == "gallery-db-writer"


def test_default_connection_is_configured_like_connect(isolated_metadata_db: Path) -> None:
    writer = _module().DatabaseWriter()
    writer.start()
    try:
        pragmas = writer.run(
            lambda conn: (
                conn.execute("PRAGMA journal_mode").fetchone()[0],
                conn.execute("PRAGMA synchronous").fetchone()[0],
                conn.execute("PRAGMA busy_timeout").fetchone()[0],
                conn.execute("PRAGMA foreign_keys").fetchone()[0],
                conn.row_factory is sqlite3.Row,
                conn.isolation_level,
            ),
            lane="priority",
        )
    finally:
        writer.stop(timeout=5)
    assert pragmas == ("wal", 1, 5000, 1, True, None)


def test_writer_follows_the_configured_database_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.config as config

    first, second = tmp_path / "first.db", tmp_path / "second.db"
    writer = _module().DatabaseWriter()
    writer.start()
    try:
        monkeypatch.setattr(config, "GALLERY_METADATA_DB", first)
        assert Path(writer.run(lambda conn: conn.execute("PRAGMA database_list").fetchone()["file"])) == first
        monkeypatch.setattr(config, "GALLERY_METADATA_DB", second)
        assert Path(writer.run(lambda conn: conn.execute("PRAGMA database_list").fetchone()["file"])) == second
    finally:
        writer.stop(timeout=5)


def test_a_custom_connection_must_be_in_autocommit_mode(db_file: Path) -> None:
    writer = _module().DatabaseWriter(
        connect=lambda: sqlite3.connect(db_file), path_provider=lambda: db_file, retry_delays=()
    )
    writer.start()
    try:
        with pytest.raises(_module().DatabaseWriterError, match="autocommit"):
            writer.run(lambda conn: 1)
    finally:
        writer.stop(timeout=5)


# ---------------------------------------------------------------------------
# Ordering, lanes, batching
# ---------------------------------------------------------------------------


def test_ops_are_fifo_within_a_lane(make_writer) -> None:
    writer = make_writer()
    order: list[int] = []
    blocker, first = park(writer)
    futures = [writer.submit(lambda conn, n=n: order.append(n)) for n in range(10)]
    blocker.release.set()
    for future in [first, *futures]:
        future.result(10)
    assert order == list(range(10))


def test_priority_lane_preempts_ops_already_queued_in_the_normal_lane(make_writer) -> None:
    writer = make_writer()
    order: list[str] = []
    blocker, first = park(writer)
    futures = [
        writer.submit(lambda conn: order.append("n1"), lane="normal"),
        writer.submit(lambda conn: order.append("n2"), lane="normal"),
        writer.submit(lambda conn: order.append("p1"), lane="priority"),
        writer.submit(lambda conn: order.append("p2"), lane="priority"),
    ]
    blocker.release.set()
    for future in [first, *futures]:
        future.result(10)
    assert order == ["p1", "p2", "n1", "n2"]


def test_unknown_lane_is_rejected(make_writer) -> None:
    with pytest.raises(ValueError, match="lane"):
        make_writer().submit(lambda conn: None, lane="urgent")


def test_ops_queued_behind_a_running_batch_share_one_transaction(make_writer, db_file: Path) -> None:
    writer = make_writer()
    blocker, first = park(writer)
    futures = [writer.submit(insert(f"v{n}")) for n in range(12)]
    blocker.release.set()
    for future in [first, *futures]:
        future.result(10)

    assert rows(db_file) == [f"v{n}" for n in range(12)]
    assert count(writer, "BEGIN IMMEDIATE") == 1
    assert count(writer, "COMMIT") == 1
    assert count(writer, "SAVEPOINT gw_op") == 13, "every op runs under its own savepoint"
    assert writer.stats()["batches"] == 1


def test_batch_size_caps_the_ops_per_transaction(make_writer, db_file: Path) -> None:
    writer = make_writer(batch_max=3)
    blocker, first = park(writer)
    futures = [writer.submit(insert(f"v{n}")) for n in range(7)]
    blocker.release.set()
    for future in [first, *futures]:
        future.result(10)

    assert len(rows(db_file)) == 7
    assert count(writer, "COMMIT") == 3, "8 ops with a batch cap of 3 commit as 3 + 3 + 2"
    assert writer.stats()["batch_sizes"] == [3, 3, 2]


def test_batch_time_budget_closes_a_batch_early(make_writer, db_file: Path) -> None:
    clock = FakeClock()
    writer = make_writer(batch_ms=100, clock=clock)
    blocker, first = park(writer)
    futures = [writer.submit(insert("slow")), writer.submit(insert("after-1")), writer.submit(insert("after-2"))]
    clock.now += 0.2  # the parked op consumed more than the 100 ms budget
    blocker.release.set()
    for future in [first, *futures]:
        future.result(10)

    assert rows(db_file) == ["slow", "after-1", "after-2"]
    assert writer.stats()["batch_sizes"][0] == 1, "the batch closes once its time budget is spent"
    assert count(writer, "COMMIT") >= 2


def test_writer_never_waits_for_more_ops_when_its_queue_is_empty(make_writer, db_file: Path) -> None:
    writer = make_writer(batch_ms=3_600_000)  # an hour: any linger would time this test out
    assert writer.submit(insert("solo")).result(10) == "solo"
    assert writer.submit(insert("solo-2")).result(10) == "solo-2"
    assert rows(db_file) == ["solo", "solo-2"]
    assert writer.stats()["batch_sizes"] == [1, 1]


def test_a_cancelled_pending_op_is_skipped(make_writer, db_file: Path) -> None:
    writer = make_writer()
    blocker, first = park(writer)
    doomed = writer.submit(insert("doomed"))
    kept = writer.submit(insert("kept"))
    assert doomed.cancel() is True
    blocker.release.set()
    first.result(10)
    assert kept.result(10) == "kept"
    assert rows(db_file) == ["kept"]


# ---------------------------------------------------------------------------
# Savepoints and failures
# ---------------------------------------------------------------------------


def test_a_failing_op_rolls_back_only_its_savepoint(make_writer, db_file: Path) -> None:
    writer = make_writer()
    boom = ValueError("op failed after writing")

    def failing(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t (v) VALUES ('rolled-back')")
        raise boom

    def violating(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t (v) VALUES ('kept-1')")  # duplicate of the first op's value

    blocker, first = park(writer)
    ok_before = writer.submit(insert("kept-1"))
    bad = writer.submit(failing)
    bad_sql = writer.submit(violating)
    ok_after = writer.submit(insert("kept-2"))
    blocker.release.set()
    first.result(10)

    assert ok_before.result(10) == "kept-1"
    assert ok_after.result(10) == "kept-2"
    with pytest.raises(ValueError) as caught:
        bad.result(10)
    assert caught.value is boom, "the op's own exception object reaches its Future"
    with pytest.raises(sqlite3.IntegrityError):
        bad_sql.result(10)
    assert rows(db_file) == ["kept-1", "kept-2"]
    assert count(writer, "COMMIT") == 1, "the failing ops did not abort the batch"
    assert count(writer, "ROLLBACK TO gw_op") == 2


def test_an_op_that_ends_the_transaction_fails_alone_and_the_writer_survives(make_writer, db_file: Path) -> None:
    writer = make_writer()

    def sabotage(conn: sqlite3.Connection) -> None:
        conn.execute("COMMIT")  # code inside an op must never end the batch transaction

    with pytest.raises(sqlite3.Error):
        writer.run(sabotage)
    assert writer.run(insert("after")) == "after"
    assert rows(db_file) == ["after"]


# ---------------------------------------------------------------------------
# BEGIN / COMMIT failure handling
# ---------------------------------------------------------------------------


def test_exhausted_commit_failure_fails_every_op_of_the_batch(make_writer, db_file: Path) -> None:
    locked = sqlite3.OperationalError("database is locked")
    commits_failing = threading.Event()
    commits_failing.set()
    slept: list[float] = []

    def script(sql: str) -> BaseException | None:
        return locked if sql == "COMMIT" and commits_failing.is_set() else None

    writer = make_writer(script=script, retry_delays=(0.01, 0.02), sleep=slept.append)
    executed: list[str] = []

    def tracked(value: str) -> Callable[[sqlite3.Connection], str]:
        def op(conn: sqlite3.Connection) -> str:
            executed.append(value)
            return insert(value)(conn)

        return op

    blocker, first = park(writer)
    futures = [writer.submit(tracked(f"v{n}")) for n in range(4)]
    blocker.release.set()

    for future in [first, *futures]:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            future.result(10)
    assert rows(db_file) == [], "a batch that could not commit applies nothing"
    assert slept == [0.01, 0.02], "one pause per configured retry, then give up"
    assert count(writer, "BEGIN IMMEDIATE") == 3
    assert executed.count("v0") == 3, "each retry re-runs the batch from scratch"

    commits_failing.clear()
    assert writer.run(insert("recovered")) == "recovered", "the writer survives an exhausted commit"
    assert rows(db_file) == ["recovered"]


def test_a_transient_commit_failure_is_retried_and_the_ops_apply_exactly_once(make_writer, db_file: Path) -> None:
    attempts = {"commit": 0}

    def script(sql: str) -> BaseException | None:
        if sql == "COMMIT":
            attempts["commit"] += 1
            if attempts["commit"] == 1:
                return sqlite3.OperationalError("database is busy")
        return None

    writer = make_writer(script=script)
    blocker, first = park(writer)
    futures = [writer.submit(insert(f"v{n}")) for n in range(3)]
    blocker.release.set()

    assert first.result(10) == "unblocked"
    assert [future.result(10) for future in futures] == ["v0", "v1", "v2"]
    assert rows(db_file) == ["v0", "v1", "v2"], "no duplicates after the rerun"
    assert writer.stats()["retries"] == 1
    assert count(writer, "ROLLBACK") == 1


def test_a_non_transient_commit_failure_is_not_retried(make_writer, db_file: Path) -> None:
    def script(sql: str) -> BaseException | None:
        return sqlite3.OperationalError("disk I/O error") if sql == "COMMIT" else None

    writer = make_writer(script=script, retry_delays=(0.0, 0.0, 0.0))
    blocker, first = park(writer)
    futures = [writer.submit(insert("a")), writer.submit(insert("b"))]
    blocker.release.set()

    for future in [first, *futures]:
        with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
            future.result(10)
    assert count(writer, "BEGIN IMMEDIATE") == 1
    assert rows(db_file) == []


def test_begin_failure_after_retries_fails_the_ops_in_hand_without_running_them(make_writer) -> None:
    def script(sql: str) -> BaseException | None:
        return sqlite3.OperationalError("database is locked") if sql == "BEGIN IMMEDIATE" else None

    writer = make_writer(script=script, retry_delays=(0.0, 0.0))
    ran: list[int] = []
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        writer.run(lambda conn: ran.append(1))
    assert ran == []
    assert count(writer, "BEGIN IMMEDIATE") == 3


def test_failure_outside_sqlite_still_resolves_every_future(make_writer, db_file: Path) -> None:
    def script(sql: str) -> BaseException | None:
        return RuntimeError("connection exploded") if sql == "COMMIT" else None

    writer = make_writer(script=script)
    blocker, first = park(writer)
    futures = [writer.submit(insert("a")), writer.submit(insert("b"))]
    blocker.release.set()
    for future in [first, *futures]:
        with pytest.raises(RuntimeError, match="exploded"):
            future.result(10)
    assert rows(db_file) == []


class _Fatal(BaseException):
    """Stands in for KeyboardInterrupt/SystemExit raised inside an op."""


def test_a_baseexception_in_an_op_resolves_all_futures_and_closes_the_writer(make_writer) -> None:
    writer = make_writer()

    def fatal(conn: sqlite3.Connection) -> None:
        raise _Fatal("stop the world")

    blocker, first = park(writer)
    bystander = writer.submit(lambda conn: "never runs")
    dying = writer.submit(fatal)
    blocker.release.set()

    with pytest.raises(_Fatal):
        dying.result(10)
    assert first.done() and bystander.done(), "no Future may be left unresolved"
    assert wait_until(lambda: writer.state == "stopped")
    with pytest.raises(_module().DatabaseWriterClosed):
        writer.submit(lambda conn: None)


# ---------------------------------------------------------------------------
# Backpressure
# ---------------------------------------------------------------------------


def test_a_full_lane_blocks_submit_and_then_raises(make_writer) -> None:
    writer = make_writer(queue_max=2)
    blocker, first = park(writer)
    queued = [writer.submit(lambda conn: None, lane="normal") for _ in range(2)]

    with pytest.raises(_module().DatabaseWriterBackpressure):
        writer.submit(lambda conn: None, lane="normal", timeout=0.05)
    urgent = writer.submit(lambda conn: "priority still accepted", lane="priority", timeout=0.05)

    blocker.release.set()
    assert urgent.result(10) == "priority still accepted"
    for future in [first, *queued]:
        future.result(10)


def test_a_blocked_submit_proceeds_when_space_frees_up(make_writer, db_file: Path) -> None:
    writer = make_writer(queue_max=1)
    blocker, first = park(writer)
    queued = writer.submit(insert("queued"))
    outcome: dict[str, Any] = {}

    def late_submitter() -> None:
        outcome["future"] = writer.submit(insert("late"), timeout=30)

    thread = threading.Thread(target=late_submitter, daemon=True)
    thread.start()
    assert wait_until(lambda: writer.blocked_submitters() == 1), "the submitter never blocked on the full lane"

    blocker.release.set()
    thread.join(10)
    assert not thread.is_alive()
    first.result(10)
    queued.result(10)
    assert outcome["future"].result(10) == "late"
    assert rows(db_file) == ["queued", "late"]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_submit_before_start_and_after_stop_raises_immediately(db_file: Path) -> None:
    module = _module()
    writer = module.DatabaseWriter(connect=lambda: sqlite3.connect(db_file, isolation_level=None))
    with pytest.raises(module.DatabaseWriterClosed):
        writer.submit(lambda conn: None)
    writer.start()
    assert writer.run(lambda conn: 1) == 1
    assert writer.stop(timeout=5) is True
    assert writer.state == "stopped"
    with pytest.raises(module.DatabaseWriterClosed):
        writer.submit(lambda conn: None)
    with pytest.raises(module.DatabaseWriterClosed):
        writer.run(lambda conn: None)


def test_stop_drains_pending_ops_and_rejects_new_ones(make_writer, db_file: Path) -> None:
    module = _module()
    writer = make_writer()
    blocker, first = park(writer)
    pending = [writer.submit(insert(f"v{n}")) for n in range(5)]
    stopped: dict[str, Any] = {}
    stopper = threading.Thread(target=lambda: stopped.update(result=writer.stop(timeout=30)), daemon=True)
    stopper.start()
    assert wait_until(lambda: writer.state == "stopping")

    with pytest.raises(module.DatabaseWriterClosed):
        writer.submit(lambda conn: None)
    assert not any(future.done() for future in pending), "pending ops are still queued, not dropped"

    blocker.release.set()
    stopper.join(10)
    assert stopped == {"result": True}
    assert first.result(1) == "unblocked"
    assert [future.result(1) for future in pending] == [f"v{n}" for n in range(5)]
    assert rows(db_file) == [f"v{n}" for n in range(5)]
    assert writer.state == "stopped"


def test_stop_deadline_fails_the_ops_it_cannot_drain(make_writer, db_file: Path) -> None:
    module = _module()
    writer = make_writer()
    blocker, first = park(writer)
    pending = [writer.submit(insert(f"v{n}")) for n in range(3)]

    assert writer.stop(timeout=0.1) is False, "a writer stuck inside an op reports an incomplete shutdown"
    for future in pending:
        with pytest.raises(module.DatabaseWriterClosed):
            future.result(5)

    blocker.release.set()
    assert first.result(10) == "unblocked", "the in-flight batch still commits"
    assert wait_until(lambda: writer.state == "stopped")
    assert rows(db_file) == []


def test_abort_between_batches_leaves_queued_ops_unapplied(make_writer, db_file: Path) -> None:
    module = _module()
    writer = make_writer()
    blocker, first = park(writer)
    pending = [writer.submit(insert(f"v{n}")) for n in range(3)]
    writer.abort()
    blocker.release.set()

    assert first.result(10) == "unblocked"
    for future in pending:
        with pytest.raises(module.DatabaseWriterClosed):
            future.result(10)
    assert rows(db_file) == []
    assert wait_until(lambda: writer.state == "stopped")


def test_a_stopped_writer_can_be_started_again(make_writer, db_file: Path) -> None:
    writer = make_writer()
    writer.run(insert("one"))
    assert writer.stop(timeout=5)
    writer.start()
    assert writer.run(insert("two")) == "two"
    assert rows(db_file) == ["one", "two"]


# ---------------------------------------------------------------------------
# Deadlock rules
# ---------------------------------------------------------------------------


def test_submit_from_the_writer_thread_runs_inline_in_the_same_transaction(make_writer, db_file: Path) -> None:
    writer = make_writer()

    def outer(conn: sqlite3.Connection) -> tuple[bool, bool]:
        conn.execute("INSERT INTO t (v) VALUES ('outer')")

        def inner_ok(inner_conn: sqlite3.Connection) -> bool:
            return inner_conn is conn and inner_conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1

        def inner_bad(inner_conn: sqlite3.Connection) -> None:
            inner_conn.execute("INSERT INTO t (v) VALUES ('inner-rolled-back')")
            raise ValueError("inner failed")

        seen_uncommitted = writer.submit(inner_ok).result(timeout=5)  # would hang forever if queued
        with pytest.raises(ValueError):
            writer.submit(inner_bad).result(timeout=5)
        return seen_uncommitted, writer.in_writer_thread()

    assert writer.run(outer) == (True, True)
    assert rows(db_file) == ["outer"], "an inline op failure rolls back only its own savepoint"
    assert count(writer, "COMMIT") == 1


def test_run_from_the_writer_thread_is_inline_too(make_writer) -> None:
    writer = make_writer()
    assert writer.run(lambda conn: writer.run(lambda inner: "nested", lane="priority")) == "nested"


def test_a_raising_op_does_not_disturb_the_ops_queued_around_it(make_writer, db_file: Path) -> None:
    """Converted from the retired ``..._writer_thread_cannot_acquire_the_global_db_lock`` (no lock exists any more).

    What survives of that test: an op that fails on the writer thread surfaces its own error while the ops
    queued before and after it still commit in the same batch.
    """
    writer = make_writer()

    def offender(conn: sqlite3.Connection) -> None:
        raise RuntimeError("offender failed")

    blocker, first = park(writer)
    failing = writer.submit(offender)
    bystander = writer.submit(insert("still-commits"))
    blocker.release.set()
    first.result(10)

    with pytest.raises(RuntimeError, match="offender failed"):
        failing.result(10)
    assert bystander.result(10) == "still-commits"
    assert rows(db_file) == ["still-commits"]


def test_the_writer_commits_while_another_connection_holds_an_open_read_snapshot(make_writer, db_file: Path) -> None:
    """Converted from ``test_the_writer_never_needs_the_global_db_lock``.

    The writer used to be proven independent of ``_DB_LOCK``; with the lock gone, the equivalent is that a
    reader parked inside a long WAL read transaction never delays the writer, and the reader keeps its snapshot.
    """
    writer = make_writer()
    reader = sqlite3.connect(db_file, timeout=5, isolation_level=None)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM t").fetchone()[0] == 0
        future = writer.submit(insert("while-reading"))
        assert future.result(timeout=10) == "while-reading", "the writer must not queue behind a reader"
        assert reader.execute("SELECT count(*) FROM t").fetchone()[0] == 0, "the reader keeps its snapshot"
        reader.execute("COMMIT")
    finally:
        reader.close()
    assert rows(db_file) == ["while-reading"]


def test_get_active_writer_follows_the_writer_lifecycle(make_writer, monkeypatch: pytest.MonkeyPatch) -> None:
    """Converted from ``test_get_active_writer_honours_the_flag_the_db_lock_and_the_lifecycle``.

    The flag and the ``_DB_LOCK`` branches no longer exist. The lifecycle contract is kept and tightened: a
    running writer is active, a stopping one still counts as active (so callers are refused instead of
    writing around it), and an idle or stopped one means "no active writer" (the direct path). Nothing
    auto-starts a writer any more.
    """
    module = _module()
    writer = make_writer()
    monkeypatch.setattr(module, "database_writer", writer)
    assert module.get_active_writer() is writer

    writer.stop(timeout=5)
    assert module.get_active_writer() is None, "a stopped writer is no active writer"

    fresh = module.DatabaseWriter(connect=lambda: sqlite3.connect(":memory:", isolation_level=None))
    monkeypatch.setattr(module, "database_writer", fresh)
    assert fresh.state == "idle"
    assert module.get_active_writer() is None, "an idle writer is no active writer"
    assert fresh.state == "idle", "get_active_writer never starts the writer"

    fresh.start()
    try:
        assert module.get_active_writer() is fresh
        blocker, parked = park(fresh)  # a writer that is draining counts as active until it stopped
        stopper = threading.Thread(target=lambda: fresh.stop(timeout=10), daemon=True)
        stopper.start()
        wait_until(lambda: fresh.state == "stopping", timeout=5)
        assert module.get_active_writer() is fresh
        blocker.release.set()
        parked.result(10)
        stopper.join(10)
    finally:
        fresh.stop(timeout=5)
    assert module.get_active_writer() is None


def test_run_write_never_falls_back_to_the_direct_path_when_the_writer_fails(
    make_writer, db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Converted from ``test_run_write_falls_back_when_the_writer_closes_underneath_it``.

    Before: a writer that closed between routing and submission made ``run_write`` run the op through the
    ``fallback=`` callable. Now the error propagates and the op does not run anywhere.
    """
    module = _module()
    writer = make_writer()
    monkeypatch.setattr(module, "database_writer", writer)
    real_run = writer.run

    def racing_run(op, **kwargs):
        writer.stop(timeout=5)  # the writer shuts down between routing and submission
        return real_run(op, **kwargs)

    monkeypatch.setattr(writer, "run", racing_run)
    with pytest.raises(module.DatabaseWriterClosed):
        module.run_write(insert("never-written"), lane="priority")
    assert rows(db_file) == []


# ---------------------------------------------------------------------------
# Configuration and app lifespan
# ---------------------------------------------------------------------------


def _config_values(expression: str, **env: str) -> list[str]:
    """Evaluate ``expression`` against ``backend.config`` in a fresh interpreter (config reads env at import)."""
    clean = {key: value for key, value in os.environ.items() if not key.startswith("GALLERY_DB_WRITER_")}
    result = subprocess.run(
        [sys.executable, "-c", f"import backend.config as c; print({expression})"],
        cwd=REPO_ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout.split()


def test_configuration_defaults_and_overrides() -> None:
    expression = "c.DB_WRITER_BATCH_MAX, c.DB_WRITER_BATCH_MS"
    assert _config_values(expression) == ["50", "100.0"]
    overridden = _config_values(
        expression,
        GALLERY_DB_WRITER_BATCH_MAX="7",
        GALLERY_DB_WRITER_BATCH_MS="12",
    )
    assert overridden == ["7", "12.0"]
    clamped = _config_values(
        "c.DB_WRITER_BATCH_MAX, c.DB_WRITER_BATCH_MS",
        GALLERY_DB_WRITER_BATCH_MAX="0",
        GALLERY_DB_WRITER_BATCH_MS="-5",
    )
    assert clamped == ["1", "1.0"], "nonsensical values are clamped, never zero or negative"


def _record_lifespan(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import backend.app as app_module

    events: list[str] = []

    def recorder(name: str) -> Callable[[], None]:
        return lambda: events.append(name)

    monkeypatch.setattr(app_module, "GALLERY_CATALOG_SERVICE_ENABLED", True)
    monkeypatch.setattr(app_module, "GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED", False)
    monkeypatch.setattr(app_module, "GALLERY_SEARCH_INDEXER_ENABLED", True)
    monkeypatch.setattr(app_module, "INTEGRITY_CHECK_ENABLED", True)
    monkeypatch.setattr(app_module, "validate_trusted_proxy_configuration", lambda: None)
    monkeypatch.setattr(app_module, "recover_stale_jobs", recorder("recover-stale"))
    monkeypatch.setattr(app_module, "recover_metadata_index_jobs", recorder("recover-metadata"))
    monkeypatch.setattr(app_module, "start", recorder("start:catalog"))
    monkeypatch.setattr(app_module, "stop", recorder("stop:catalog"))
    monkeypatch.setattr(app_module.metadata_indexer, "METADATA_INDEXER_ENABLED", True)
    monkeypatch.setattr(app_module.metadata_worker, "start", recorder("start:metadata"))
    monkeypatch.setattr(app_module.metadata_worker, "stop", recorder("stop:metadata"))
    monkeypatch.setattr(app_module.search_index_worker, "start", recorder("start:search"))
    monkeypatch.setattr(app_module.search_index_worker, "stop", recorder("stop:search"))
    monkeypatch.setattr(app_module.integrity_checker, "start", recorder("start:integrity"))
    monkeypatch.setattr(app_module.integrity_checker, "stop", recorder("stop:integrity"))
    monkeypatch.setattr(app_module.scheduler, "start", recorder("start:derivative"))
    monkeypatch.setattr(app_module.scheduler, "stop", recorder("stop:derivative"))
    monkeypatch.setattr(app_module, "_start_refresh", recorder("start:refresh"))
    monkeypatch.setattr(app_module, "_stop_refresh", recorder("stop:refresh"))
    monkeypatch.setattr(app_module, "_start_watcher", recorder("start:watcher"))
    monkeypatch.setattr(app_module, "_stop_watcher", recorder("stop:watcher"))
    monkeypatch.setattr(app_module.database_writer, "start", recorder("start:db-writer"))
    monkeypatch.setattr(app_module.database_writer, "stop", recorder("stop:db-writer"))

    async def exercise() -> None:
        async with app_module._lifespan(app_module.app):
            events.append("serving")

    asyncio.run(exercise())
    return events


def test_lifespan_starts_the_writer_before_every_worker_and_stops_it_after_all_of_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _record_lifespan(monkeypatch)

    starts = [event for event in events if event.startswith("start:")]
    stops = [event for event in events if event.startswith("stop:")]
    assert starts[0] == "start:db-writer", starts
    assert stops[-1] == "stop:db-writer", stops
    assert {"start:catalog", "start:metadata", "start:derivative"} <= set(starts)
    assert events.index("serving") > max(events.index(start) for start in starts)
    assert events.index("serving") < min(events.index(stop) for stop in stops)
    assert stops == [f"stop:{name.split(':')[1]}" for name in reversed(starts)], "strict reverse unwind"


def test_lifespan_starts_the_writer_before_startup_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replaces ``test_lifespan_without_the_flag_never_touches_the_writer`` (the flag no longer exists).

    Startup recovery writes, so with no flag-off mode the writer must already run when it executes.
    """
    events = _record_lifespan(monkeypatch)
    writer_up = events.index("start:db-writer")
    assert writer_up < events.index("recover-stale")
    assert writer_up < events.index("recover-metadata")


def test_the_writer_flag_no_longer_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app as app_module
    import backend.config as config_module

    assert not hasattr(config_module, "DB_WRITER_ENABLED")
    assert not hasattr(app_module, "DB_WRITER_ENABLED")
    assert not hasattr(_module(), "DB_WRITER_ENABLED")
    values = _config_values("hasattr(c, 'DB_WRITER_ENABLED')", GALLERY_DB_WRITER_ENABLED="false")
    assert values == ["False"], "GALLERY_DB_WRITER_ENABLED is ignored: the writer is the only write path"
