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
