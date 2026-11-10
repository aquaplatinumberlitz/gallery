"""SQLite connection lifecycle: the backend closes every connection it opens.

Purpose:
Guard BL-14. `with sqlite3.connect(...) as conn:` commits but never closes, so a leaked connection keeps
its file descriptor until garbage collection (a `ResourceWarning`, and "Too many open files" under
coverage). The metadata store must close every connection deterministically.

Guarantees:
* `ClosingConnection` commits on success, rolls back on error, and always closes when used in `with`.
* A connection that fails to configure is closed before the error escapes.
* Repeated runs of the migration backups, read helpers, search/browse/status stores, derivative and
  metadata-job paths leave zero open connections and a stable `/proc/self/fd` count, with the writer
  stopped and with it running.
* Starting and stopping the shared database writer repeatedly does not accumulate descriptors.
* The thumbnail diskcache closes each thread's connection when the thread ends, and when the cache is dropped
  while a pooled thread that used it is still alive; its connections keep diskcache's pragmas.

Run when:
Adding or changing any code that opens a SQLite connection, the `_db.py` connection helpers, the database
writer lifecycle, or the pytest `filterwarnings` policy for `ResourceWarning`.
"""

from __future__ import annotations

import gc
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.metadata_store import _db, _migrations

FD_DIR = Path("/proc/self/fd")
ROUNDS = 25

pytestmark = pytest.mark.skipif(not FD_DIR.is_dir(), reason="needs /proc/self/fd (Linux)")


def _fd_count() -> int:
    return len(os.listdir(FD_DIR))


def _is_open(conn: sqlite3.Connection) -> bool:
    try:
        conn.total_changes  # noqa: B018 - raises ProgrammingError on a closed connection
    except sqlite3.ProgrammingError:
        return False
    return True


@contextmanager
def _tracked_connections(monkeypatch: pytest.MonkeyPatch):
    """Record (and strongly reference) every connection opened through ``sqlite3.connect``.

    Holding a reference defeats CPython's refcount cleanup, so a connection the code forgot to close
    stays open, keeps its descriptor, and is counted: a leak cannot hide behind garbage collection.
    """
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    try:
        yield opened
    finally:
        monkeypatch.setattr(sqlite3, "connect", real_connect)


def _leaked(opened: list[sqlite3.Connection]) -> int:
    return sum(1 for conn in opened if _is_open(conn))


def _exercise_backend(library_id: int, root: Path) -> None:
    """Run the read, search, browse, status, derivative, metadata-job and backup paths once."""
    from backend import derivative_scheduler as ds
    from backend import facets
    from backend.metadata_store import (
        claim_next_metadata_job,
        get_catalog_browse_listing,
        get_gallery_stats,
        get_library,
        get_library_progress,
        get_metadata_index_status,
        list_active_jobs,
        list_jobs,
        list_libraries,
        search_index,
        search_index_count,
        search_metadata,
    )

    list_libraries()
    get_library(library_id)
    get_gallery_stats()
    get_library_progress(library_id)
    list_jobs()
    list_active_jobs(library_id)
    get_metadata_index_status()
    claim_next_metadata_job()
    get_catalog_browse_listing(library_id)
    search_metadata("mika")
    search_index("mika", "all", library_id=library_id)
    search_index("mika portrait", "all", library_id=library_id)
    search_index_count("mika", "all", library_id=library_id)
    facets.build_facets(scope="all", library_id=library_id)

    image = next(root.rglob("*.png"))
    asset_id = ds.scheduler.find_asset_id(image)
    assert asset_id is not None
    ds.scheduler.get_asset_path(asset_id)
    ds.scheduler.get_derivative_status(asset_id, "thumbnail", "missing")

    with _db._connect_read() as conn, pytest.raises(sqlite3.OperationalError):  # an error must not leak either
        conn.execute("SELECT * FROM no_such_table")
    with pytest.raises(RuntimeError, match="boom"), _db._connect_read():
        raise RuntimeError("boom")

    source = _db._connect_read()
    try:
        for backup in (
            _migrations._backup_v1_database,
            _migrations._backup_v8_database,
            _migrations._backup_v13_database,
        ):
            backup(source)
    finally:
        source.close()


def test_exercised_backend_paths_close_every_connection(temp_gallery_with_metadata, no_active_writer, monkeypatch):
    from backend.metadata_store import list_libraries

    root = temp_gallery_with_metadata
    library_id = list_libraries()[0]["id"]
    _exercise_backend(library_id, root)  # warm up outside the measurement
    gc.collect()
    baseline = _fd_count()

    with _tracked_connections(monkeypatch) as opened:
        for _ in range(ROUNDS):
            _exercise_backend(library_id, root)
        grown = _fd_count() - baseline
        leaked = _leaked(opened)

    assert opened, "the tracker must see the connections the paths open"
    assert grown <= 2, f"the fd count grew by {grown} over {ROUNDS} rounds ({leaked} connections stayed open)"
    assert leaked == 0, f"{leaked} of {len(opened)} connections stayed open"


def test_exercised_backend_paths_close_every_connection_with_the_writer_running(
    temp_gallery_with_metadata, started_writer, monkeypatch
):
    from backend.metadata_store import list_libraries

    root = temp_gallery_with_metadata
    library_id = list_libraries()[0]["id"]
    _exercise_backend(library_id, root)
    gc.collect()

    with _tracked_connections(monkeypatch) as opened:
        for _ in range(ROUNDS):
            _exercise_backend(library_id, root)
        # The writer owns exactly one long-lived connection; everything else must be closed.
        started_writer.reset()
        leaked = _leaked(opened)

    assert leaked == 0, f"{leaked} of {len(opened)} connections stayed open after the writer stopped"


def test_database_writer_start_stop_cycles_do_not_accumulate_descriptors(isolated_metadata_db, monkeypatch):
    from backend.metadata_store.db_writer import database_writer, run_write

    database_writer.reset()

    def cycle() -> None:
        database_writer.start()
        run_write(lambda conn: conn.execute("SELECT 1").fetchone())
        database_writer.reset()

    cycle()
    gc.collect()
    baseline = _fd_count()
    with _tracked_connections(monkeypatch) as opened:
        for _ in range(ROUNDS):
            cycle()
        leaked = _leaked(opened)
    assert opened
    assert leaked == 0
    assert _fd_count() <= baseline + 2


def test_direct_write_path_closes_its_connection(isolated_metadata_db, no_active_writer, monkeypatch):
    from backend.metadata_store.db_writer import run_write

    with _tracked_connections(monkeypatch) as opened:
        for _ in range(ROUNDS):
            run_write(lambda conn: conn.execute("SELECT 1").fetchone())
        with pytest.raises(RuntimeError, match="op failed"):
            run_write(lambda conn: (_ for _ in ()).throw(RuntimeError("op failed")))
        leaked = _leaked(opened)
    assert opened
    assert leaked == 0


def test_closing_connection_commits_rolls_back_and_closes(tmp_path):
    db = tmp_path / "closing.db"
    with _db.open_connection(db) as conn:
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    assert not _is_open(conn), "leaving the with block must close the connection"

    with pytest.raises(RuntimeError, match="abort"), _db.open_connection(db) as failing:
        failing.execute("INSERT INTO t VALUES (2)")
        raise RuntimeError("abort")
    assert not _is_open(failing)

    with _db.open_connection(db) as reader:
        assert [row[0] for row in reader.execute("SELECT v FROM t")] == [1], "commit kept, rollback dropped"


def test_helpers_return_closing_connections_that_close_when_configuration_fails(isolated_metadata_db, monkeypatch):
    for opener in (_db._connect, _db._connect_read, _db._connect_readonly):
        with opener() as conn:
            assert isinstance(conn, _db.ClosingConnection)
        assert not _is_open(conn)

    original = _db._configure_or_close

    def failing_configure(conn, _configure):
        def explode(_conn):
            raise sqlite3.OperationalError("configuration failed")

        return original(conn, explode)

    monkeypatch.setattr(_db, "_configure_or_close", failing_configure)
    with _tracked_connections(monkeypatch) as opened:
        for opener in (_db._connect, _db._connect_read, _db._connect_readonly):
            with pytest.raises(sqlite3.OperationalError, match="configuration failed"):
                opener()
        assert len(opened) == 3
        assert _leaked(opened) == 0, "a connection that failed to configure must be closed before the error escapes"


def test_thumbnail_disk_cache_connections_are_closed_when_their_threads_end(tmp_path, monkeypatch):
    import threading

    from backend.disk_cache import ThreadClosingCache

    cache = ThreadClosingCache(str(tmp_path / "cache"), size_limit=1024 * 1024)
    try:
        with _tracked_connections(monkeypatch) as opened:

            def worker(n: int) -> None:
                cache.set(f"key-{n}", b"value")
                assert cache.get(f"key-{n}") == b"value"

            for n in range(10):
                thread = threading.Thread(target=worker, args=(n,))
                thread.start()
                thread.join()
            assert len(opened) == 10, "each thread opens its own diskcache connection"
            assert _leaked(opened) == 0, "a connection must be closed by the thread that ends"
    finally:
        cache.close()


def test_thumbnail_disk_cache_dropped_while_its_threads_live_closes_their_connections(tmp_path, monkeypatch):
    """A cache dropped while a pooled thread that used it is still alive closes that thread's connection.

    The thread-local storage is then torn down by the dropping thread, not the owner. With diskcache's default
    ``check_same_thread=True`` the close failed and the connection was freed with ``ResourceWarning: unclosed
    database`` (an error under the pytest filter), at whatever test the garbage collector happened to run in.
    """
    import threading

    from backend.disk_cache import ThreadClosingCache

    holder = [ThreadClosingCache(str(tmp_path / "cache"), size_limit=1024 * 1024)]
    with _tracked_connections(monkeypatch) as opened:
        used, release = threading.Event(), threading.Event()

        def pooled_worker() -> None:
            # The thread keeps running but holds no reference to the cache once it has used it.
            holder[0].set("key", b"value")
            used.set()
            release.wait(10)

        thread = threading.Thread(target=pooled_worker)
        thread.start()
        try:
            assert used.wait(10)
            assert len(opened) == 1
            holder.clear()
            gc.collect()
            assert _leaked(opened) == 0, "dropping the cache must close a live thread's connection"
        finally:
            release.set()
            thread.join()


def test_thumbnail_disk_cache_connections_keep_diskcache_pragmas(tmp_path):
    """The connection `ThreadClosingCache._con` opens is configured as diskcache configures its own."""
    import threading

    from backend.disk_cache import ThreadClosingCache

    cache = ThreadClosingCache(str(tmp_path / "cache"), size_limit=1024 * 1024)
    seen: dict[str, object] = {}

    def worker() -> None:
        cache.set("key", b"value")
        seen["journal_mode"] = cache._con.execute("PRAGMA journal_mode").fetchone()[0]
        seen["synchronous"] = cache._con.execute("PRAGMA synchronous").fetchone()[0]
        seen["value"] = cache.get("key")

    try:
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
    finally:
        cache.close()
    assert seen == {"journal_mode": "wal", "synchronous": 1, "value": b"value"}


def test_pytest_turns_unclosed_database_warnings_into_errors(request):
    filters = request.config.getini("filterwarnings")
    assert "error:unclosed database:ResourceWarning" in filters
    assert any(entry.startswith("error:Exception ignored in") and "sqlite3.Connection" in entry for entry in filters)
