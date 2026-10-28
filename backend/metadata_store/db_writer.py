"""Single database writer: one thread, one write connection, short batched transactions.

Workers do their CPU and I/O in parallel but hand SQLite writes to ``DatabaseWriter`` as small
functions (``op(conn)``). The writer thread applies them in batches: one ``BEGIN IMMEDIATE`` per batch,
one ``SAVEPOINT`` per op (a failing op rolls back only itself), one ``COMMIT``. Each op's ``Future``
resolves only after its batch committed, so a result a caller sees is durable.

Deadlock rules (the writer never takes ``_DB_LOCK``):

* Code running inside an op must never acquire ``_DB_LOCK`` (it raises ``WriterThreadLockError``) and
  must never wait on the writer. ``submit``/``run`` from the writer thread run the op inline, in the
  current transaction under a nested savepoint.
* A thread holding ``_DB_LOCK`` must not wait for the writer either: ``run`` refuses
  (``DatabaseWriterDeadlock``) and ``get_active_writer`` routes such a caller to its direct path.
* Side effects that may take ``_DB_LOCK`` (scheduling backfills, derivative reconciliation) run in the
  caller after the Future resolved, never inside an op.
"""

from __future__ import annotations

import concurrent.futures
import logging
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, TypeVar

from ..catalog_maintenance_gate import producer_gate
from ..config import (
    DB_WRITER_BATCH_MAX,
    DB_WRITER_BATCH_MS,
    DB_WRITER_ENABLED,
    DB_WRITER_QUEUE_MAX,
    DB_WRITER_RESULT_TIMEOUT_SECONDS,
    DB_WRITER_SHUTDOWN_TIMEOUT_SECONDS,
    DB_WRITER_SUBMIT_TIMEOUT_SECONDS,
)
from . import _db
from ._db import _connect, _gallery_metadata_db_path

_T = TypeVar("_T")
LOGGER = logging.getLogger(__name__)

LANE_PRIORITY = "priority"
LANE_NORMAL = "normal"
LANES = (LANE_PRIORITY, LANE_NORMAL)

# Pauses before retrying a whole batch whose BEGIN or COMMIT hit SQLite lock/busy contention.
_DEFAULT_RETRY_DELAYS = (0.05, 0.25, 1.0)
_OP_SAVEPOINT = "gw_op"
_LOCAL = threading.local()


class DatabaseWriterError(RuntimeError):
    """Base class of database writer failures that are not an op's own exception."""


class DatabaseWriterUnavailable(DatabaseWriterError):
    """The writer could not take or finish the op for lifecycle or load reasons (retry later)."""


class DatabaseWriterClosed(DatabaseWriterUnavailable):
    """The writer is not running: the op was rejected, or dropped before it ran, and was not applied."""


class DatabaseWriterBackpressure(DatabaseWriterUnavailable):
    """The lane stayed full for the whole submit timeout."""


class DatabaseWriterTimeout(DatabaseWriterUnavailable):
    """The op was not finished within the caller's wait (it may still run later; its writes are fenced)."""


class DatabaseWriterDeadlock(DatabaseWriterError):
    """A caller holding ``_DB_LOCK`` asked to wait for the writer, which could deadlock."""


@dataclass(slots=True)
class _Op:
    fn: Callable[[sqlite3.Connection], Any]
    future: Future
    lane: str


def _is_transient(exc: BaseException) -> bool:
    """Return whether ``exc`` is SQLite lock/busy contention that a retry of the batch can outlast."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _settle(future: Future, ok: bool, value: Any) -> None:
    """Resolve ``future`` with a result or an exception, ignoring one that was already settled."""
    try:
        if ok:
            future.set_result(value)
        else:
            future.set_exception(value)
    except concurrent.futures.InvalidStateError:
        pass


def _open_default_connection() -> sqlite3.Connection:
    """Open the write connection like ``_connect()`` (WAL, synchronous=NORMAL, busy_timeout), in autocommit mode."""
    conn = _connect()
    conn.isolation_level = None
    return conn


def current_writer() -> DatabaseWriter | None:
    """Return the writer whose thread is the calling thread, if any."""
    return getattr(_LOCAL, "writer", None)


def writer_connection() -> sqlite3.Connection | None:
    """Return the connection of the writer op running on this thread, or ``None`` outside a writer op.

    Store helpers that normally open their own connection under ``_DB_LOCK`` (small lookups such as
    ``get_library_for_path``) use it instead when called from inside an op: the writer thread must not
    take ``_DB_LOCK``, and reading through the op's own connection also sees the op's uncommitted rows.
    """
    writer = current_writer()
    return None if writer is None else writer._active_conn


class DatabaseWriter:
    """Apply write ops from many threads on one thread and one connection, in batched transactions."""

    def __init__(
        self,
        *,
        connect: Callable[[], sqlite3.Connection] | None = None,
        path_provider: Callable[[], object] | None = None,
        batch_max: int | None = None,
        batch_ms: float | None = None,
        queue_max: int | None = None,
        submit_timeout: float | None = None,
        result_timeout: float | None = None,
        shutdown_timeout: float | None = None,
        retry_delays: tuple[float, ...] = _DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
        name: str = "gallery-db-writer",
    ) -> None:
        """Configure a writer; ``start()`` launches its thread.

        ``connect`` returns an autocommit-mode connection (``isolation_level=None``); by default it is
        ``_connect()``. The connection is reopened whenever ``path_provider()`` (the configured database
        path) changes. ``batch_max``/``batch_ms`` bound one transaction by op count and by the time spent
        pulling more ops into it; the writer never waits for ops that are not yet queued.
        """
        self._connect_factory = connect or _open_default_connection
        self._path_provider = path_provider or _gallery_metadata_db_path
        self._batch_max = max(1, DB_WRITER_BATCH_MAX if batch_max is None else int(batch_max))
        self._batch_ms = max(0.0, DB_WRITER_BATCH_MS if batch_ms is None else float(batch_ms))
        self._queue_max = max(1, DB_WRITER_QUEUE_MAX if queue_max is None else int(queue_max))
        self._submit_timeout = DB_WRITER_SUBMIT_TIMEOUT_SECONDS if submit_timeout is None else float(submit_timeout)
        self._result_timeout = DB_WRITER_RESULT_TIMEOUT_SECONDS if result_timeout is None else float(result_timeout)
        self._shutdown_timeout = (
            DB_WRITER_SHUTDOWN_TIMEOUT_SECONDS if shutdown_timeout is None else float(shutdown_timeout)
        )
        self._retry_delays = tuple(retry_delays)
        self._wake = threading.Event()
        self._sleep = sleep or self._wake.wait
        self._clock = clock
        self._name = name

        self._lifecycle = threading.RLock()
        self._lock = threading.Lock()
        self._work = threading.Condition(self._lock)  # the writer waits here for ops
        self._space = threading.Condition(self._lock)  # submitters wait here for room in a full lane
        self._queues: dict[str, deque[_Op]] = {lane: deque() for lane in LANES}
        self._state = "idle"  # idle -> running -> stopping -> stopped
        self._thread: threading.Thread | None = None
        self._abort = False
        self._stop_deadline: float | None = None
        self._blocked = 0

        # Touched only by the writer thread.
        self._conn: sqlite3.Connection | None = None
        self._conn_path: object = None
        self._active_conn: sqlite3.Connection | None = None
        self._inline_depth = 0
        self._attempt_failures: dict[int, BaseException] = {}
        self._reset_stats()

    # -- state ---------------------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Lifecycle state: ``idle`` (never started), ``running``, ``stopping``, or ``stopped``."""
        return self._state

    def is_running(self) -> bool:
        """Return whether the writer accepts ops."""
        return self._state == "running"

    def in_writer_thread(self) -> bool:
        """Return whether the calling thread is this writer's thread."""
        return current_writer() is self

    def pending(self) -> int:
        """Return the number of queued (not yet started) ops."""
        with self._lock:
            return sum(len(queue) for queue in self._queues.values())

    def blocked_submitters(self) -> int:
        """Return how many threads are blocked in ``submit`` waiting for room in a full lane."""
        return self._blocked

    def stats(self) -> dict[str, Any]:
        """Return in-memory diagnostics: batches, ops, failed ops, batch retries, and recent batch sizes."""
        return {**self._stats, "batch_sizes": list(self._batch_sizes)}

    def _reset_stats(self) -> None:
        self._stats = {"batches": 0, "ops": 0, "op_failures": 0, "retries": 0}
        self._batch_sizes: deque[int] = deque(maxlen=256)

    # -- lifecycle -----------------------------------------------------------------------------

    def start(self) -> None:
        """Start the writer thread; a no-op while running, and a stopped writer may be started again."""
        with self._lifecycle:
            if self._state == "running":
                return
            previous = self._thread
            if self._state == "stopping" and previous is not None:
                previous.join(self._shutdown_timeout)
                if previous.is_alive():
                    raise DatabaseWriterError("the previous database writer thread is still shutting down")
            with self._lock:
                self._abort = False
                self._stop_deadline = None
                self._state = "running"
            self._wake.clear()
            self._thread = threading.Thread(target=self._thread_main, name=self._name, daemon=True)
            self._thread.start()

    def stop(self, timeout: float | None = None) -> bool:
        """Stop accepting ops, drain the queued ones within ``timeout`` seconds, and join the thread.

        Returns ``False`` when the thread did not finish in time (it may be stuck inside an op); the
        ops still queued then are failed with ``DatabaseWriterClosed`` instead of being left hanging.
        """
        if self.in_writer_thread():
            raise DatabaseWriterError("the database writer cannot be stopped from its own thread")
        limit = self._shutdown_timeout if timeout is None else float(timeout)
        with self._lifecycle:
            with self._lock:
                if self._state == "running":
                    self._state = "stopping"
                    self._stop_deadline = self._clock_monotonic() + limit
                self._work.notify_all()
                self._space.notify_all()
            thread = self._thread
            if thread is None:
                return True
            thread.join(limit)
            if thread.is_alive():
                self._abandon_queued("the database writer did not drain before its shutdown deadline")
                return False
            return True

    def abort(self) -> None:
        """Stop without draining: queued ops fail with ``DatabaseWriterClosed``; the running batch finishes.

        Simulates the writer dying between batches (used by crash-recovery tests).
        """
        with self._lock:
            if self._state not in {"running", "stopping"}:
                return
            self._abort = True
            self._state = "stopping"
            self._work.notify_all()
            self._space.notify_all()
        self._wake.set()
        self._abandon_queued("the database writer was aborted")

    def reset(self) -> None:
        """Return to the never-started state (tests): stop or abort the thread and clear diagnostics."""
        with self._lifecycle:
            if self._state in {"running", "stopping"} and not self.stop(timeout=5):
                self.abort()
            thread = self._thread
            if thread is not None:
                thread.join(5)
            with self._lock:
                self._state = "idle"
                self._abort = False
                self._stop_deadline = None
            self._thread = None
            self._reset_stats()

    @staticmethod
    def _clock_monotonic() -> float:
        return time.monotonic()

    # -- submitting ----------------------------------------------------------------------------

    def submit(
        self, op: Callable[[sqlite3.Connection], _T], *, lane: str = LANE_NORMAL, timeout: float | None = None
    ) -> Future:
        """Queue ``op(conn)`` and return its Future.

        The op runs inside the batch's ``BEGIN IMMEDIATE`` under its own savepoint; its Future resolves
        after the batch committed (result), or with the op's own exception, or with the commit failure.
        Blocks up to ``timeout`` seconds when the lane is full, then raises ``DatabaseWriterBackpressure``;
        raises ``DatabaseWriterClosed`` at once unless the writer is running. Called from the writer
        thread itself, the op runs inline in the current transaction and the returned Future is done.
        """
        if lane not in LANES:
            raise ValueError(f"unknown database writer lane: {lane!r}")
        if self.in_writer_thread():
            return self._run_inline(op)
        deadline = self._clock_monotonic() + (self._submit_timeout if timeout is None else float(timeout))
        with self._lock:
            while True:
                if self._state != "running":
                    raise DatabaseWriterClosed(f"the database writer is {self._state}")
                queue = self._queues[lane]
                if len(queue) < self._queue_max:
                    break
                remaining = deadline - self._clock_monotonic()
                if remaining <= 0:
                    raise DatabaseWriterBackpressure(f"the {lane} lane of the database writer is full")
                self._blocked += 1
                try:
                    self._space.wait(remaining)
                finally:
                    self._blocked -= 1
            future: Future = Future()
            queue.append(_Op(op, future, lane))
            self._work.notify()
        return future

    def run(
        self, op: Callable[[sqlite3.Connection], _T], *, lane: str = LANE_NORMAL, timeout: float | None = None
    ) -> _T:
        """Submit ``op`` and wait for its result; the one blocking entry point workers should use.

        Refuses (``DatabaseWriterDeadlock``) when the calling thread holds ``_DB_LOCK``; runs inline on
        the writer thread; raises ``DatabaseWriterTimeout`` if the op is not finished within the wait.
        """
        if self.in_writer_thread():
            return self._run_inline(op).result()
        if _db._DB_LOCK.is_owned():
            raise DatabaseWriterDeadlock("a thread holding _DB_LOCK must not wait for the database writer")
        future = self.submit(op, lane=lane)
        wait = self._result_timeout if timeout is None else float(timeout)
        try:
            return future.result(timeout=wait)
        except concurrent.futures.TimeoutError:
            if future.done():
                raise  # the op itself raised a TimeoutError
            future.cancel()
            raise DatabaseWriterTimeout(f"the database writer did not finish an op within {wait:g}s") from None

    def _run_inline(self, op: Callable[[sqlite3.Connection], Any]) -> Future:
        future: Future = Future()
        conn = self._active_conn
        if conn is None:
            _settle(future, False, DatabaseWriterError("inline writer op requested outside a running batch"))
            return future
        self._inline_depth += 1
        try:
            ok, value = self._run_in_savepoint(conn, f"gw_inline_{self._inline_depth}", op)
        finally:
            self._inline_depth -= 1
        _settle(future, ok, value)
        return future

    def _abandon_queued(self, reason: str) -> None:
        with self._lock:
            dropped = [queue.popleft() for lane in LANES for queue in [self._queues[lane]] for _ in range(len(queue))]
            self._space.notify_all()
        for op in dropped:
            _settle(op.future, False, DatabaseWriterClosed(reason))

    # -- the writer thread ---------------------------------------------------------------------

    def _thread_main(self) -> None:
        _db.mark_writer_thread(True)
        _LOCAL.writer = self
        try:
            while True:
                first = self._take_first()
                if first is None:
                    break
                self._run_batch(first)
        except BaseException:  # noqa: BLE001 - the thread must leave a consistent, closed writer behind
            LOGGER.exception("The database writer thread crashed")
        finally:
            self._finish()

    def _finish(self) -> None:
        self._drop_connection()
        with self._lock:
            dropped = [queue.popleft() for lane in LANES for queue in [self._queues[lane]] for _ in range(len(queue))]
            self._state = "stopped"
            self._work.notify_all()
            self._space.notify_all()
        for op in dropped:
            _settle(op.future, False, DatabaseWriterClosed("the database writer stopped before the op ran"))

    def _pop_locked(self) -> _Op | None:
        """Pop the next runnable op, priority lane first, FIFO inside a lane; skips cancelled Futures."""
        for lane in LANES:
            queue = self._queues[lane]
            while queue:
                op = queue.popleft()
                # An op put back after its batch ended early is already RUNNING.
                if op.future.running() or op.future.set_running_or_notify_cancel():
                    return op
        return None

    def _pop_nowait(self) -> _Op | None:
        with self._lock:
            op = self._pop_locked()
            if op is not None:
                self._space.notify_all()
            return op

    def _take_first(self) -> _Op | None:
        """Block for the next op; return ``None`` when the writer must exit (drained, aborted, or past deadline)."""
        with self._work:
            while True:
                if self._abort:
                    return None
                if (
                    self._state == "stopping"
                    and self._stop_deadline is not None
                    and self._clock_monotonic() > self._stop_deadline
                ):
                    return None
                op = self._pop_locked()
                if op is not None:
                    self._space.notify_all()
                    return op
                if self._state != "running":
                    return None
                self._work.wait()

    def _run_batch(self, first: _Op) -> None:
        ops = [first]
        attempt = 0
        while True:
            self._attempt_failures = {}
            try:
                outcomes = self._attempt(ops, pull=attempt == 0)
            except sqlite3.Error as exc:
                self._rollback_quietly()
                if _is_transient(exc) and attempt < len(self._retry_delays):
                    self._stats["retries"] += 1
                    self._sleep(self._retry_delays[attempt])
                    attempt += 1
                    continue
                self._fail_batch(ops, exc)
                return
            except Exception as exc:  # noqa: BLE001
                self._rollback_quietly()
                self._fail_batch(ops, exc)
                return
            except BaseException as exc:
                self._rollback_quietly()
                self._fail_batch(ops, exc)
                raise
            self._settle_outcomes(outcomes)
            return

    def _attempt(self, ops: list[_Op], *, pull: bool) -> list[tuple[_Op, bool, Any]]:
        """Run ``ops`` in one ``BEGIN IMMEDIATE`` transaction, pulling more queued ops while within budget."""
        conn = self._ensure_connection()
        conn.execute("BEGIN IMMEDIATE")
        self._active_conn = conn
        outcomes: list[tuple[_Op, bool, Any]] = []
        index = 0
        try:
            started = self._clock()
            while True:
                if index >= len(ops):
                    if not pull or len(ops) >= self._batch_max or (self._clock() - started) * 1000.0 >= self._batch_ms:
                        break
                    more = self._pop_nowait()
                    if more is None:
                        break
                    ops.append(more)
                op = ops[index]
                index += 1
                ok, value = self._run_in_savepoint(conn, _OP_SAVEPOINT, op.fn)
                if not ok:
                    self._attempt_failures[id(op)] = value
                outcomes.append((op, ok, value))
                if not conn.in_transaction:
                    break  # the op ended the batch transaction behind our back; nothing left to commit
        finally:
            self._active_conn = None
        if index < len(ops):
            self._requeue_unrun(ops[index:])
            del ops[index:]
        if conn.in_transaction:
            conn.execute("COMMIT")
        return outcomes

    def _run_in_savepoint(
        self, conn: sqlite3.Connection, name: str, fn: Callable[[sqlite3.Connection], Any]
    ) -> tuple[bool, Any]:
        """Run ``fn(conn)`` under savepoint ``name``; a failure rolls back only that savepoint."""
        conn.execute(f"SAVEPOINT {name}")
        try:
            value = fn(conn)
        except Exception as exc:  # noqa: BLE001 - delivered to the op's own Future
            try:
                conn.execute(f"ROLLBACK TO {name}")
                conn.execute(f"RELEASE {name}")
            except sqlite3.Error:
                pass  # the op ended the transaction; the batch loop notices and stops
            return False, exc
        try:
            conn.execute(f"RELEASE {name}")
        except sqlite3.Error as exc:
            return False, exc
        return True, value

    def _requeue_unrun(self, ops: list[_Op]) -> None:
        with self._lock:
            for op in reversed(ops):
                self._queues[op.lane].appendleft(op)
            self._work.notify()

    def _settle_outcomes(self, outcomes: list[tuple[_Op, bool, Any]]) -> None:
        self._stats["batches"] += 1
        self._stats["ops"] += len(outcomes)
        self._batch_sizes.append(len(outcomes))
        for op, ok, value in outcomes:
            if not ok:
                self._stats["op_failures"] += 1
            _settle(op.future, ok, value)

    def _fail_batch(self, ops: list[_Op], exc: BaseException) -> None:
        """Give every op of a batch that could not commit its failure (an op that failed alone keeps its own)."""
        self._stats["batches"] += 1
        self._stats["ops"] += len(ops)
        self._stats["op_failures"] += len(ops)
        self._batch_sizes.append(len(ops))
        for op in ops:
            _settle(op.future, False, self._attempt_failures.get(id(op), exc))

    # -- connection ----------------------------------------------------------------------------

    def _ensure_connection(self) -> sqlite3.Connection:
        path = self._path_provider()
        if self._conn is not None and self._conn_path != path:
            self._drop_connection()
        if self._conn is None:
            conn = self._connect_factory()
            if conn.isolation_level is not None:
                conn.close()
                raise DatabaseWriterError("the writer connection must use autocommit mode (isolation_level=None)")
            self._conn, self._conn_path = conn, path
        return self._conn

    def _rollback_quietly(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - a connection that cannot roll back is replaced
            LOGGER.warning("Database writer rollback failed; reopening the connection", exc_info=True)
            self._drop_connection()

    def _drop_connection(self) -> None:
        conn, self._conn, self._conn_path = self._conn, None, None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                LOGGER.debug("Closing the database writer connection failed", exc_info=True)


database_writer = DatabaseWriter()


def get_active_writer() -> DatabaseWriter | None:
    """Return the writer a write should go through, or ``None`` to use the direct transaction.

    ``None`` when the feature flag is off, when the calling thread holds ``_DB_LOCK`` (it must never
    wait on the writer), or when the shared writer was stopped (shutdown: the direct path takes over).
    A never-started shared writer is started on first use, so code running outside the app lifespan
    (tests, scripts) works unchanged. On the writer thread itself the running writer is returned.
    """
    current = current_writer()
    if current is not None:
        return current
    if not DB_WRITER_ENABLED or _db._DB_LOCK.is_owned():
        return None
    writer = database_writer
    if writer.state == "idle":
        writer.start()
    return writer if writer.is_running() else None


def run_write(op: Callable[[sqlite3.Connection], _T], *, lane: str = LANE_NORMAL, fallback: Callable[[], _T]) -> _T:
    """Run ``op`` through the writer, or ``fallback()`` (the direct transaction) when no writer applies.

    The submission is made while holding the shared producer gate, so destructive maintenance can
    quiesce writer-backed producers exactly like direct ones: an in-flight writer op keeps maintenance
    from starting, and active maintenance holds new ops back. ``DatabaseWriterClosed`` means the op was
    not applied, so the direct path takes over. On the writer thread the op runs inline, ungated.
    """
    writer = get_active_writer()
    if writer is None:
        return fallback()
    if writer.in_writer_thread():
        return writer.run(op, lane=lane)
    with producer_gate():
        try:
            return writer.run(op, lane=lane)
        except DatabaseWriterClosed:
            pass
    return fallback()
