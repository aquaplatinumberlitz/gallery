"""Phase 3 regression: the process-global ``_DB_LOCK`` is retired; every write is a writer op.

Purpose:
Pin the end state of the write-contention work. Before Phase 3, the search-index worker, library
management, startup recovery and the integrity checker's repair passes still wrote under the process-wide
``_DB_LOCK`` in their own transactions, ``GALLERY_DB_WRITER_ENABLED`` switched every path back to direct
transactions, and the writer thread had to defend itself against the lock. Now the only write paths are
the database writer and the one-transaction "no active writer" path used by ``init_db``, migrations,
scripts and plain unit tests.

Guarantees:
No production module defines or takes a process-global database lock, wraps it, or reads the removed
writer flag; the search-index worker, library management (create, update, unregister, forget offline
assets), startup recovery (catalog jobs, metadata jobs, search-index jobs) and the integrity checker's
repair passes run every write statement on the writer thread, with the integrity repairs split into
bounded ops; ``run_write`` never takes the direct path while a writer is active, not even after an op
raised, after the writer was stopped or aborted, or when the writer closed underneath it, and the direct
path itself refuses to run next to an active writer; a context with no writer (fresh interpreter running
``init_db`` and a script-style write, nested ops, a failing op) still works, one transaction per op, and
rolls back as a unit.

Run when:
Changing the database writer, ``run_write``/``run_direct``, anything that opens a write transaction, the
search-index worker, library management, startup recovery, the integrity checker, or the lock-free
guarantees of the worker lifecycle.
"""

from __future__ import annotations

import ast
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from backend.integrity_checker import IntegrityChecker
from backend.metadata_store import _connect, create_library, initialize_database
from tests.conftest import create_test_png
from tests.worker_contention_support import (
    WRITER_THREAD_NAME,
    capture_write_threads,
    count_direct_transactions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
REMOVED_NAMES = frozenset({"_DB_LOCK", "_DatabaseLock", "WriterThreadLockError", "DB_WRITER_ENABLED"})


def _writer_module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


def _production_sources() -> list[Path]:
    return [
        path
        for path in sorted(BACKEND.rglob("*.py"))
        if "tests" not in path.relative_to(BACKEND).parts and "__pycache__" not in path.parts
    ]


def _off_writer(writes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(thread, text.split("(")[0][:70]) for thread, text in writes if thread != WRITER_THREAD_NAME]


def _tables_written_on_the_writer(writes: list[tuple[str, str]]) -> str:
    return " ".join(text for thread, text in writes if thread == WRITER_THREAD_NAME)


# ---------------------------------------------------------------------------
# (a) No process-global database lock
# ---------------------------------------------------------------------------


def test_no_production_module_takes_a_process_global_db_lock() -> None:
    offenders: list[str] = []
    for path in _production_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = {
                getattr(node, "id", None),
                getattr(node, "attr", None),
                getattr(node, "name", None),
            }
            if isinstance(node, ast.alias):
                names.add(node.name)
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "GALLERY_DB_WRITER_ENABLED" in node.value
            ):
                names.add("GALLERY_DB_WRITER_ENABLED")
            hit = (names & REMOVED_NAMES) or ({"GALLERY_DB_WRITER_ENABLED"} & names)
            if hit:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{getattr(node, 'lineno', 0)} {sorted(hit)}")
    assert not offenders, offenders


def test_the_lock_and_the_flag_are_not_importable_from_the_metadata_store() -> None:
    import backend.config as config
    import backend.metadata_store as store
    import backend.metadata_store._db as db_module

    for module in (store, db_module, _writer_module(), config):
        for name in REMOVED_NAMES:
            assert not hasattr(module, name), f"{module.__name__}.{name} still exists"
    assert not hasattr(_writer_module(), "DatabaseWriterDeadlock")


def test_a_write_workload_never_acquires_an_rlock_shared_by_all_stores(
    isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavioural twin of the static check: a library create + scan job drains with no lock held by the caller.

    Every write goes through ``run_write``; while one is in flight no ``threading`` lock owned by the calling
    thread is a lock of the metadata store (``_INIT_LOCK`` only guards schema creation and is released first).
    """
    import backend.metadata_store._schema as schema

    seen: list[bool] = []
    real_run = started_writer.run

    def watching_run(op, **kwargs):
        seen.append(schema._INIT_LOCK._is_owned())  # noqa: SLF001 - RLock ownership probe
        return real_run(op, **kwargs)

    monkeypatch.setattr(started_writer, "run", watching_run)
    create_test_png(isolated_gallery_root / "a.png")
    create_library([isolated_gallery_root], name="No lock")
    assert seen and not any(seen)


# ---------------------------------------------------------------------------
# (b) Phase 3 writers run on the writer thread
# ---------------------------------------------------------------------------


@pytest.fixture
def _database(isolated_metadata_db: Path) -> Path:
    initialize_database()
    return isolated_metadata_db


def _seed_asset(conn: sqlite3.Connection, library_id: int, path: Path, state: str = "done") -> int:
    cursor = conn.execute(
        """
        INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
                            indexed_at, metadata_state, offline, deleted_at)
        VALUES (?, ?, ?, ?, 'image', 1000, 100, 1, ?, 0, NULL)
        """,
        (library_id, str(path), str(path.parent), path.name, state),
    )
    return int(cursor.lastrowid)


def test_search_index_worker_writes_only_on_the_writer_thread(
    _database: Path, isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.search_indexer as indexer_module
    from backend.metadata_store.search_index_store import (
        claim_next_search_index_job,
        create_search_index_job,
        get_search_index_job,
        recover_search_index_jobs,
        request_search_index_job_cancel,
    )
    from backend.search_indexer import SearchExtractionResult, SearchIndexDefinition, run_search_index_once

    definition = SearchIndexDefinition(
        name="phase3_probe",
        schema_version=1,
        extractor_version=1,
        enabled=True,
        required_mode="workflow",
        extractor=lambda asset: SearchExtractionResult(status="ready", payload={"asset_id": asset["id"]}),
        persist=lambda _conn, _asset, _payload: None,
    )
    monkeypatch.setitem(indexer_module._DEFINITIONS, definition.name, definition)
    library = create_library([isolated_gallery_root], name="Search")
    with _connect() as conn:
        for index in range(5):
            _seed_asset(conn, int(library["id"]), isolated_gallery_root / f"s{index}.png")

    with capture_write_threads(monkeypatch) as writes:
        job = create_search_index_job(
            definition.name, library["id"], mode="full", schema_version=1, extractor_version=1
        )
        assert run_search_index_once(worker_id="phase3") is True
        second = create_search_index_job(
            definition.name, library["id"], mode="full", schema_version=1, extractor_version=1
        )
        assert claim_next_search_index_job(worker_id="phase3-claim", lease_seconds=60) is not None
        request_search_index_job_cancel(int(second["id"]))
        recover_search_index_jobs()

    finished = get_search_index_job(int(job["id"]))
    assert finished is not None and finished["state"] == "succeeded" and finished["processed_count"] == 5
    assert not _off_writer(writes), _off_writer(writes)[:10]
    written = _tables_written_on_the_writer(writes)
    for table in ("search_index_jobs", "asset_search_extractions", "search_index_states"):
        assert table in written, f"no {table} write reached the writer"


def test_library_management_writes_only_on_the_writer_thread(
    _database: Path, isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.metadata_store import (
        forget_offline_library_assets,
        get_library,
        unregister_library,
        update_library,
        update_library_state,
    )

    first = isolated_gallery_root / "one"
    second = isolated_gallery_root / "two"
    first.mkdir()
    second.mkdir()
    create_test_png(first / "a.png")

    with capture_write_threads(monkeypatch) as writes:
        library = create_library([first], name="Managed")
        library_id = int(library["id"])
        update_library(library_id, name="Renamed")
        update_library(library_id, import_paths=[first, second], exclusion_patterns=["*.tmp"])
        update_library_state(library_id, "ready", scan_completed=True)
        with _connect() as conn:  # seeding is the test's own connection, not under observation
            conn.execute("UPDATE assets SET offline = 1 WHERE library_id = ?", (library_id,))
        forget_offline_library_assets(library_id)
        assert unregister_library(library_id) is True

    assert get_library(library_id) is None
    off = [item for item in _off_writer(writes) if "UPDATE assets SET offline" not in item[1]]
    assert not off, off[:10]
    written = _tables_written_on_the_writer(writes)
    for table in ("libraries", "library_import_paths"):
        assert table in written, f"no {table} write reached the writer"


def test_startup_recovery_writes_only_on_the_writer_thread(
    _database: Path, isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend import indexer, scan_worker
    from backend.metadata_store import claim_next_catalog_job, recover_stale_jobs
    from backend.metadata_store.search_index_store import recover_search_index_jobs

    root = isolated_gallery_root / "recover"
    root.mkdir()
    create_test_png(root / "r.png")
    library_id = int(create_library([root], name="Recover")["id"])
    scan_worker.queue_scan(library_id, trigger="manual")
    assert claim_next_catalog_job(worker_id="dead-worker", lease_seconds=60) is not None
    with _connect() as conn:
        conn.execute(
            """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, mtime_ns,
                                                size, state, attempts, queued_at, updated_at, claimed_by)
               VALUES (?, 'r.png', ?, ?, ?, 1.0, 1, 1, 'running', 1, 1.0, 1.0, 'dead')""",
            (str(root / "r.png"), str(root), str(root), str(root)),
        )

    with capture_write_threads(monkeypatch) as writes:
        failed = recover_stale_jobs()
        recovered = indexer.recover_metadata_index_jobs()
        recover_search_index_jobs()

    assert len(failed) == 1
    assert recovered["running_reset"] + recovered["running_failed_exhausted"] >= 1
    assert not _off_writer(writes), _off_writer(writes)[:10]
    written = _tables_written_on_the_writer(writes)
    assert "library_jobs" in written and "metadata_index_jobs" in written


def test_integrity_repair_passes_write_only_on_the_writer_thread_in_bounded_ops(
    _database: Path, isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = isolated_gallery_root
    library_id = int(create_library([root], name="Integrity")["id"])
    with _connect() as conn:
        for index in range(6):  # "done" assets without image_metadata: demoted by the repair pass
            _seed_asset(conn, library_id, root / f"i{index}.png", state="done")
    checker = IntegrityChecker(interval=3600)

    with capture_write_threads(monkeypatch) as writes:
        counts = checker.run_all_checks()
        checker.run_and_persist()

    assert counts["asset_done_but_no_metadata"] == 6
    assert not _off_writer(writes), _off_writer(writes)[:10]
    written = _tables_written_on_the_writer(writes)
    for table in ("assets", "metadata_index_jobs", "integrity_check_runs"):
        assert table in written, f"no {table} write reached the writer"
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM assets WHERE metadata_state = 'done'").fetchone()[0] == 0


def test_integrity_repairs_are_chunked_into_ops_of_bounded_size(
    _database: Path, isolated_gallery_root: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.integrity_checker as integrity_module

    submitted: list[str] = []
    real_run = started_writer.run

    def spy(op, **kwargs):
        submitted.append(getattr(op, "__qualname__", repr(op)))
        return real_run(op, **kwargs)

    monkeypatch.setattr(started_writer, "run", spy)
    monkeypatch.setattr(integrity_module, "_REPAIR_CHUNK_ROWS", 2)
    root = isolated_gallery_root
    library_id = int(create_library([root], name="Chunks")["id"])
    with _connect() as conn:
        for index in range(7):
            _seed_asset(conn, library_id, root / f"c{index}.png", state="done")
    submitted.clear()

    counts = IntegrityChecker(interval=3600).run_all_checks()

    assert counts["asset_done_but_no_metadata"] == 7
    assert len(submitted) >= 2, "a repair of 7 rows with a chunk size of 2 must be several writer ops"


def test_startup_recovery_decides_its_repairs_outside_the_write_lock_and_applies_them_in_bounded_ops(
    _database: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Margin regression: recovery used to run its per-job ``image_metadata``/sidecar lookups inside one op.

    On a bench database (1,500 done jobs) that single transaction held SQLite's write lock for ~900 ms. The
    lookups now run on a read snapshot and only the identity-fenced UPDATEs are ops of at most
    ``RECOVERY_OP_ROWS`` rows.
    """
    import backend.metadata_store.metadata_queue as metadata_queue
    from backend import indexer

    root = isolated_gallery_root
    library_id = int(create_library([root], name="Recovery ops")["id"])
    with _connect() as conn:
        for index in range(7):
            path = root / f"done{index}.png"
            _seed_asset(conn, library_id, path, state="pending")
            conn.execute(
                """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path, mtime, mtime_ns,
                                                    size, state, attempts, queued_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1.0, 1000, 100, 'done', 1, 1.0, 1.0)""",
                (str(path), path.name, str(root), str(root), str(root)),
            )
    real_lookup = metadata_queue._image_metadata_exists_for_job
    lookup_seconds = 0.03

    def slow_lookup(*args, **kwargs):
        time.sleep(lookup_seconds)  # stands for the sidecar stat and the image_metadata probe of a big library
        return real_lookup(*args, **kwargs)

    monkeypatch.setattr(metadata_queue, "_image_metadata_exists_for_job", slow_lookup)
    monkeypatch.setattr(indexer, "RECOVERY_OP_ROWS", 3, raising=False)
    op_seconds: list[float] = []
    real_run_write = indexer.run_write

    def timed_run_write(op, **kwargs):
        def timed(conn):
            started = time.monotonic()
            try:
                return op(conn)
            finally:
                op_seconds.append(time.monotonic() - started)

        return real_run_write(timed, **kwargs)

    monkeypatch.setattr(indexer, "run_write", timed_run_write)

    result = indexer.recover_metadata_index_jobs()

    assert result["done_demoted"] == 7
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM metadata_index_jobs WHERE state = 'queued'").fetchone()[0] == 7
    assert len(op_seconds) >= 1 + 3, f"expected the running reset plus three bounded repair ops, saw {op_seconds}"
    assert max(op_seconds) < 7 * lookup_seconds / 2, f"an op still contains the per-job lookups: {op_seconds}"


# ---------------------------------------------------------------------------
# (d) run_write never uses the direct path while a writer is active
# ---------------------------------------------------------------------------


def _forbid_direct_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    module = _writer_module()
    opened: list[str] = []
    real = module._open_default_connection
    writer_thread = threading.current_thread().name

    def forbidden() -> sqlite3.Connection:
        opened.append(threading.current_thread().name)
        return real()

    monkeypatch.setattr(module, "_open_default_connection", forbidden)
    assert writer_thread  # the opened list records every caller thread
    return opened


def test_run_write_stays_on_the_writer_after_an_op_raised(
    _database: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _writer_module()
    started_writer.reset()
    started_writer.start()
    writer_connections = _forbid_direct_connections(monkeypatch)
    threads: list[str] = []

    def ok(conn: sqlite3.Connection) -> str:
        threads.append(threading.current_thread().name)
        return "ok"

    def boom(conn: sqlite3.Connection) -> None:
        threads.append(threading.current_thread().name)
        raise ValueError("op failed")

    assert module.run_write(ok, lane="priority") == "ok"
    with pytest.raises(ValueError, match="op failed"):
        module.run_write(boom, lane="normal")
    assert module.run_write(ok, lane="normal") == "ok"
    assert module.post_write(ok, lane="normal") is not None  # best-effort writes are queued, never run direct
    assert set(threads[:3]) == {WRITER_THREAD_NAME}
    # The writer's own connection is opened once by the writer thread; the direct path is never the caller.
    assert set(writer_connections) <= {WRITER_THREAD_NAME}, writer_connections


def test_run_write_never_falls_back_to_the_direct_path_when_the_writer_is_stopping_or_aborted(
    _database: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _writer_module()
    started_writer.stop(timeout=5)
    started_writer.start()
    opened = _forbid_direct_connections(monkeypatch)
    release = threading.Event()
    entered = threading.Event()

    def park(conn: sqlite3.Connection) -> str:
        entered.set()
        assert release.wait(20)
        return "parked"

    future = started_writer.submit(park)
    assert entered.wait(10)
    stopper = threading.Thread(target=lambda: started_writer.stop(timeout=15), daemon=True)
    stopper.start()
    deadline = time.monotonic() + 10
    while started_writer.state != "stopping" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert started_writer.state == "stopping"
    ran: list[int] = []

    with pytest.raises(module.DatabaseWriterClosed):
        module.run_write(lambda conn: ran.append(1), lane="priority")
    with pytest.raises(module.DatabaseWriterActive):
        module.run_direct(lambda conn: ran.append(2))
    assert module.post_write(lambda conn: ran.append(3)) is None
    release.set()
    assert future.result(10) == "parked"
    stopper.join(15)
    assert ran == [], "nothing may have run around the stopping writer"
    assert [thread for thread in opened if thread != WRITER_THREAD_NAME] == []


def test_the_direct_path_refuses_to_run_next_to_an_active_writer(started_writer) -> None:
    module = _writer_module()
    with pytest.raises(module.DatabaseWriterActive):
        module.run_direct(lambda conn: None)
    started_writer.stop(timeout=5)
    assert module.run_direct(lambda conn: "now allowed") == "now allowed"


def test_a_writer_that_closes_underneath_run_write_surfaces_the_error_and_runs_nothing(
    _database: Path, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _writer_module()
    real_run = started_writer.run
    ran: list[int] = []

    def closing_run(op, **kwargs):
        started_writer.stop(timeout=5)
        return real_run(op, **kwargs)

    monkeypatch.setattr(started_writer, "run", closing_run)
    with pytest.raises(module.DatabaseWriterClosed):
        module.run_write(lambda conn: ran.append(1), lane="priority")
    assert ran == []


# ---------------------------------------------------------------------------
# (e) Contexts with no writer still work
# ---------------------------------------------------------------------------


def test_with_no_active_writer_each_op_is_one_direct_transaction_that_rolls_back_as_a_unit(
    _database: Path, no_active_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _writer_module()
    with _connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS phase3_probe (v TEXT)")
    transactions = count_direct_transactions(monkeypatch)

    def write_two(conn: sqlite3.Connection) -> int:
        conn.execute("INSERT INTO phase3_probe (v) VALUES ('one')")
        return module.run_write(lambda inner: inner.execute("INSERT INTO phase3_probe (v) VALUES ('two')").rowcount)

    assert module.run_write(write_two) == 1
    assert len(transactions) == 1, "a nested op joins the outer direct transaction"

    def fail_after_write(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO phase3_probe (v) VALUES ('lost')")
        raise RuntimeError("rolled back")

    with pytest.raises(RuntimeError, match="rolled back"):
        module.run_write(fail_after_write)
    with _connect() as conn:
        assert [row[0] for row in conn.execute("SELECT v FROM phase3_probe ORDER BY rowid")] == ["one", "two"]
    assert module.database_writer.state == "idle", "run_write never starts a writer by itself"


def test_a_fresh_interpreter_can_initialize_the_database_and_write_like_a_cli_script(tmp_path: Path) -> None:
    """Startup/CLI context: ``init_db`` then a script-style write with no writer and no app lifespan."""
    db_path = tmp_path / "cli.db"
    root = tmp_path / "photos"
    root.mkdir()
    create_test_png(root / "cli.png")
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "from backend.metadata_store import create_library, initialize_database, list_libraries, update_library\n"
        "import backend.metadata_store.db_writer as w\n"
        "initialize_database()\n"
        "library = create_library([Path(sys.argv[1])], name='cli')\n"
        "update_library(int(library['id']), name='cli-renamed')\n"
        "assert w.database_writer.state == 'idle', w.database_writer.state\n"
        "assert w.get_active_writer() is None\n"
        "print([item['name'] for item in list_libraries()])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(root)],
        cwd=REPO_ROOT,
        env={**__import__("os").environ, "GALLERY_METADATA_DB": str(db_path), "GALLERY_CATALOG_SERVICE_ENABLED": "0"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cli-renamed" in result.stdout
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT name FROM libraries").fetchone()[0] == "cli-renamed"
