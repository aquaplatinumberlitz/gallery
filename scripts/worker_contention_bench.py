#!/usr/bin/env python3
"""Measure background-worker starvation caused by status polling and write-lock hogging.

Purpose:
Reproduce and gate the worker-lifecycle audit findings (WK-01..WK-06) against a
real backend subprocess: status endpoint latency over a large `derivative_jobs`
table, metadata throughput with and without UI-style status polling, the longest
continuous SQLite write-lock hold during a touch + rescan, `database is locked`
log lines, catalog scans lost to lease expiry, orphaned `running` metadata jobs,
and superseded `ready` derivatives.

Guarantees:
* builds an isolated fixture (`create_perf_fixture.py`), isolated metadata DB,
  thumbnail cache, and `PATH_SAFETY_ROOT`; the backend runs as a subprocess on a
  free port with `GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false`
* seeds synthetic `asset_derivatives`/`derivative_jobs` rows (documented in the
  report under `synthetic_seed`) until `derivative_jobs` holds at least
  `min_derivative_jobs` rows; the rows describe superseded source identities of
  the real fixture assets and are used for status and capacity measurements only
* prints one JSON report on stdout (progress goes to stderr) and exits 0 only when
  every budget enforced for the selected `--phase` passes
* exits 1 on a budget failure and 2 when a workload did not actually run (for
  example zero metadata jobs processed); an empty workload is never a success
* `--phase 0` enforces the Phase 0 exit-gate metrics; `--phase 1` additionally
  enforces `orphan_running_metadata_jobs` and `superseded_ready_derivatives`,
  which are always measured and reported

Run when:
* changing status aggregate SQL, `_DB_LOCK` usage, reconcile/capacity batching, or
  worker lease/heartbeat behavior
* validating a worker-lifecycle hardening phase (see
  `docs/plans/WORKER_LIFECYCLE_HARDENING_PLAN.md`)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from perf_lib import budget_for, percentile  # noqa: E402

from backend.config import DERIVATIVE_VARIANTS  # noqa: E402

DERIVATIVE_VARIANT_NAMES = [v["name"] for group in DERIVATIVE_VARIANTS.values() for v in group]
EXIT_BUDGET_FAILURE = 1
EXIT_EMPTY_WORKLOAD = 2

POLL_INTERVAL_SECONDS = 2.5
PROBE_INTERVAL_SECONDS = 0.02
REQUEST_TIMEOUT_SECONDS = 180
STATUS_SAMPLES_PER_ENDPOINT = 20
STATUS_ABORT_MS = 5_000
STATUS_ABORT_AFTER_SAMPLES = 3
# Failure texts the catalog service writes when a running scan lost its claim: the stale-job
# recovery reason, the abandoned-claim fence-fail reason, and the claim-fencing exception text.
LEASE_LOSS_MARKERS = (
    "stopped before completing the job",
    "exited before writing a terminal state",
    "claim was lost",
    "claim lost",
)

# metric -> (env override, TOML field, comparison)
METRIC_BUDGETS: dict[str, tuple[str, str, str]] = {
    "status_p95_ms": ("GALLERY_PERF_WORKER_STATUS_P95_BUDGET_MS", "status_p95_ms", "max"),
    "polling_throughput_ratio": ("GALLERY_PERF_WORKER_POLLING_RATIO_BUDGET", "polling_throughput_ratio", "min"),
    "max_write_lock_hold_ms": ("GALLERY_PERF_WORKER_LOCK_HOLD_BUDGET_MS", "max_write_lock_hold_ms", "max"),
    "database_locked_log_lines": ("GALLERY_PERF_WORKER_LOCKED_LINES_BUDGET", "database_locked_log_lines", "max"),
    "lease_loss_failed_scans": ("GALLERY_PERF_WORKER_LEASE_LOSS_BUDGET", "lease_loss_failed_scans", "max"),
    "orphan_running_metadata_jobs": ("GALLERY_PERF_WORKER_ORPHAN_BUDGET", "orphan_running_metadata_jobs", "max"),
    "superseded_ready_derivatives": ("GALLERY_PERF_WORKER_SUPERSEDED_BUDGET", "superseded_ready_derivatives", "max"),
}


class EmptyWorkload(RuntimeError):
    """Raised when a measured workload did not run; the benchmark must not report success."""


def log(message: str) -> None:
    """Print a timestamped progress line to stderr."""
    print(f"[worker_contention] {time.strftime('%H:%M:%S')} {message}", file=sys.stderr, flush=True)


def _env_number(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else float(default)


def load_budgets() -> dict[str, Any]:
    """Return TOML budgets with `GALLERY_PERF_WORKER_*` overrides applied."""
    section = dict(budget_for("worker_contention"))
    for env_name, field, _mode in METRIC_BUDGETS.values():
        section[field] = _env_number(env_name, float(section[field]))
    return section


# ---------------------------------------------------------------------------
# HTTP + SQLite helpers
# ---------------------------------------------------------------------------


def free_port() -> int:
    """Return a currently free localhost TCP port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_request(url: str, *, method: str = "GET", body: bytes | None = None) -> tuple[int, bytes]:
    """Issue one HTTP request and return `(status, body)` without raising on HTTP errors."""
    request = urllib.request.Request(url, method=method, data=body)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def ro_connect(db_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection that never blocks the backend's writers."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def scalar(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> int:
    """Run a read-only query and return its first column as an int (0 when empty)."""
    conn = ro_connect(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    return int(row[0] or 0) if row else 0


# ---------------------------------------------------------------------------
# Backend subprocess
# ---------------------------------------------------------------------------


class Backend:
    """One uvicorn subprocess with an isolated environment and its own log file."""

    def __init__(self, *, python: str, fixture_root: Path, db_path: Path, cache_dir: Path, log_path: Path) -> None:
        """Remember the isolated paths and reserve a free port."""
        self.python = python
        self.fixture_root = fixture_root
        self.db_path = db_path
        self.cache_dir = cache_dir
        self.log_path = log_path
        self.port = free_port()
        self.process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None

    @property
    def base_url(self) -> str:
        """Return the backend's base URL."""
        return f"http://127.0.0.1:{self.port}"

    def start(self, extra_env: dict[str, str] | None = None) -> None:
        """Launch uvicorn and wait for `/api/health`."""
        env = os.environ.copy()
        env.update(
            {
                "PATH_SAFETY_ROOT": str(self.fixture_root),
                "GALLERY_METADATA_DB": str(self.db_path),
                "GALLERY_THUMBNAIL_CACHE_DIR": str(self.cache_dir),
                "GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED": "false",
                "ENABLE_METRICS": "false",
                "PYTHONUNBUFFERED": "1",
            }
        )
        env.update(extra_env or {})
        self._log_handle = self.log_path.open("ab")
        self.process = subprocess.Popen(
            [self.python, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"backend exited during startup (code {self.process.returncode}); see {self.log_path}"
                )
            with contextlib.suppress(OSError, urllib.error.URLError):
                if http_request(f"{self.base_url}/api/health")[0] == 200:
                    return
            time.sleep(0.5)
        raise RuntimeError("backend did not become healthy within 120 s")

    def alive(self) -> bool:
        """Return whether the subprocess is still running."""
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        """Terminate the subprocess and close its log."""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        self.process = None

    def locked_log_lines(self) -> int:
        """Count `database is locked` lines in the backend log."""
        if not self.log_path.exists():
            return 0
        count = 0
        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "database is locked" in line.lower():
                    count += 1
        return count


# ---------------------------------------------------------------------------
# Measurement threads
# ---------------------------------------------------------------------------


class LockProbe(threading.Thread):
    """Continuously try `BEGIN IMMEDIATE` (timeout 0) and record continuous blocked spans."""

    def __init__(self, db_path: Path) -> None:
        """Prepare an external probe against the metadata DB."""
        super().__init__(daemon=True, name="write-lock-probe")
        self.db_path = db_path
        self.stop_event = threading.Event()
        self.spans: list[tuple[float, float]] = []
        self.attempts = 0

    def run(self) -> None:
        """Probe the SQLite write lock every 20 ms until stopped."""
        conn = sqlite3.connect(self.db_path, timeout=0, isolation_level=None)
        blocked_since: float | None = None
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("ROLLBACK")
                    if blocked_since is not None:
                        self.spans.append((blocked_since, now))
                        blocked_since = None
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if "locked" not in message and "busy" not in message:
                        raise
                    if blocked_since is None:
                        blocked_since = now
                self.attempts += 1
                self.stop_event.wait(PROBE_INTERVAL_SECONDS)
        finally:
            if blocked_since is not None:
                self.spans.append((blocked_since, time.monotonic()))
            conn.close()

    def stop(self) -> None:
        """Stop the probe and close any open blocked span."""
        self.stop_event.set()
        self.join(timeout=30)

    def max_hold_ms(self, start: float | None = None, end: float | None = None) -> float:
        """Return the longest continuous blocked span overlapping the optional window."""
        longest = 0.0
        for span_start, span_end in self.spans:
            lo = max(span_start, start) if start is not None else span_start
            hi = min(span_end, end) if end is not None else span_end
            if hi > lo:
                longest = max(longest, (hi - lo) * 1000.0)
        return round(longest, 1)

    def summary(self) -> dict[str, Any]:
        """Summarize blocked spans for the report."""
        durations = [(end - start) * 1000.0 for start, end in self.spans]
        return {
            "attempts": self.attempts,
            "blocked_spans": len(durations),
            "spans_over_250ms": sum(1 for value in durations if value > 250),
            "spans_over_1000ms": sum(1 for value in durations if value > 1000),
            "blocked_total_ms": round(sum(durations), 1),
            "max_hold_ms": round(max(durations), 1) if durations else 0.0,
        }


class StatusPollers:
    """Three UI-style pollers: one GET per endpoint, then a 2.5 s pause, repeated."""

    def __init__(self, base_url: str, library_id: int) -> None:
        """Configure the three polled endpoints."""
        self.paths = [
            f"/api/libraries/{library_id}/status",
            "/api/maintenance/runtime",
            "/api/libraries/status",
        ]
        self.base_url = base_url
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.samples: list[tuple[str, float, int]] = []
        self._lock = threading.Lock()

    def _loop(self, path: str) -> None:
        while not self.stop_event.is_set():
            started = time.perf_counter()
            status = 0
            try:
                status = http_request(f"{self.base_url}{path}")[0]
            except (OSError, urllib.error.URLError):
                status = -1
            with self._lock:
                self.samples.append((path, (time.perf_counter() - started) * 1000.0, status))
            self.stop_event.wait(POLL_INTERVAL_SECONDS)

    def start(self) -> None:
        """Start one polling thread per endpoint."""
        self.stop_event.clear()
        self.threads = [threading.Thread(target=self._loop, args=(path,), daemon=True) for path in self.paths]
        for thread in self.threads:
            thread.start()

    def stop(self) -> dict[str, Any]:
        """Stop the pollers and summarize their request latencies."""
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=REQUEST_TIMEOUT_SECONDS + 5)
        with self._lock:
            durations = [duration for _path, duration, _status in self.samples]
            errors = sum(1 for _path, _duration, status in self.samples if status != 200)
        return {
            "requests": len(durations),
            "errors": errors,
            "p95_ms": round(percentile(durations, 95), 1),
            "max_ms": round(max(durations), 1) if durations else 0.0,
        }


# ---------------------------------------------------------------------------
# Fixture + synthetic seed
# ---------------------------------------------------------------------------


def create_fixture(python: str, workdir: Path, images: int) -> dict[str, Any]:
    """Create the isolated PNG fixture, metadata DB, and thumbnail cache directories."""
    fixture_root = workdir / "gallery-fixture"
    db_path = workdir / "gallery.db"
    cache_dir = workdir / "thumbnail-cache"
    result = subprocess.run(
        [
            python,
            str(SCRIPTS_DIR / "create_perf_fixture.py"),
            "--root",
            str(fixture_root),
            "--album-name",
            "a1111",
            "--images",
            str(images),
            "--metadata-db",
            str(db_path),
            "--thumbnail-cache",
            str(cache_dir),
            "--clean",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fixture creation failed:\n{result.stdout}\n{result.stderr}")
    return {"root": fixture_root, "album": fixture_root / "a1111", "db": db_path, "cache": cache_dir}


def seed_synthetic_derivatives(db_path: Path, *, min_jobs: int, stale_identities: int) -> dict[str, Any]:
    """Seed superseded-identity `ready` derivatives and `done` jobs for the real fixture assets.

    The rows mimic what repeated rescans leave behind: for every active image asset and
    configured variant, `stale_identities` older source identities (older `mtime_ns`, same
    size) each with a `ready` derivative and one or more `done` jobs. They never describe a
    current source identity, so they affect table sizes, status aggregates, and capacity
    accounting but not which real derivatives must be rendered.
    """
    variants = [
        (kind, str(variant["name"]), int(variant["max_long_edge"]), int(variant["quality"]))
        for kind, group in DERIVATIVE_VARIANTS.items()
        for variant in group
    ]
    conn = sqlite3.connect(db_path, timeout=60)
    try:
        assets = conn.execute(
            "SELECT id, mtime_ns, size FROM assets WHERE type = 'image' AND deleted_at IS NULL AND offline = 0"
        ).fetchall()
        if not assets:
            raise EmptyWorkload("fixture produced no active image assets; nothing to seed against")
        existing_jobs = int(conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0])
        derivative_rows = [
            (asset_id, kind, variant, int(mtime_ns) - (offset + 1) * 1_000_000_000, int(size), max_edge, quality)
            for asset_id, mtime_ns, size in assets
            for kind, variant, max_edge, quality in variants
            for offset in range(stale_identities)
        ]
        first_id = int(conn.execute("SELECT COALESCE(max(id), 0) FROM asset_derivatives").fetchone()[0]) + 1
        conn.executemany(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format, quality,
              max_long_edge, status, cache_path, byte_size
            ) VALUES (?, ?, ?, ?, ?, 'webp', ?, ?, 'ready', NULL, 2048)
            """,
            [(a, k, v, m, s, q, e) for a, k, v, m, s, e, q in derivative_rows],
        )
        last_id = int(conn.execute("SELECT max(id) FROM asset_derivatives").fetchone()[0])
        if last_id - first_id + 1 != len(derivative_rows):
            raise RuntimeError("synthetic derivative ids were not contiguous; refusing to seed jobs")
        needed_jobs = max(min_jobs - existing_jobs, len(derivative_rows))
        extra = needed_jobs - len(derivative_rows)
        job_rows = [(derivative_id,) for derivative_id in range(first_id, last_id + 1)]
        job_rows += [(first_id + (index % len(derivative_rows)),) for index in range(extra)]
        conn.executemany(
            """
            INSERT INTO derivative_jobs (derivative_id, priority, state, attempts, completed_at)
            VALUES (?, 3, 'done', 1, julianday('now'))
            """,
            job_rows,
        )
        conn.commit()
        total_jobs = int(conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0])
        last_job_id = int(conn.execute("SELECT max(id) FROM derivative_jobs").fetchone()[0])
    finally:
        conn.close()
    if total_jobs < min_jobs:
        raise EmptyWorkload(f"seeded only {total_jobs} derivative_jobs rows (< {min_jobs})")
    return {
        "assets": len(assets),
        "stale_identities_per_variant": stale_identities,
        "synthetic_asset_derivatives": len(derivative_rows),
        "synthetic_derivative_jobs": len(job_rows),
        "derivative_jobs_total": total_jobs,
        "last_seeded_job_id": last_job_id,
        "description": (
            "ready/done rows for superseded source identities of the real fixture assets; "
            "used for status and capacity measurements only"
        ),
    }


# ---------------------------------------------------------------------------
# Scenario steps
# ---------------------------------------------------------------------------


def active_work(db_path: Path, *, include_metadata_running: bool) -> dict[str, int]:
    """Count queued/running work per subsystem straight from the SQLite job tables."""
    metadata_states = "('queued', 'running')" if include_metadata_running else "('queued')"
    return {
        "metadata": scalar(db_path, f"SELECT count(*) FROM metadata_index_jobs WHERE state IN {metadata_states}"),
        "catalog": scalar(db_path, "SELECT count(*) FROM library_jobs WHERE state IN ('queued', 'running')"),
        "derivative": scalar(db_path, "SELECT count(*) FROM derivative_jobs WHERE state IN ('queued', 'running')"),
    }


def count_current_ready(db_path: Path) -> int:
    """Count `ready` derivatives that match the current source identity of an active asset."""
    return scalar(
        db_path,
        """
        SELECT count(*) FROM asset_derivatives d
        JOIN assets a ON a.id = d.asset_id
        WHERE d.status = 'ready' AND a.deleted_at IS NULL AND a.offline = 0
          AND d.source_mtime_ns = a.mtime_ns AND d.source_size = a.size
        """,
    )


def wait_until_idle(
    db_path: Path,
    *,
    timeout: float,
    include_metadata_running: bool = True,
    stable_polls: int = 3,
    min_current_ready: int = 0,
) -> dict[str, Any]:
    """Block until the job tables stay empty for several polls, or the timeout elapses."""
    started = time.monotonic()
    stable = 0
    last: dict[str, int] = {}
    while time.monotonic() - started < timeout:
        last = active_work(db_path, include_metadata_running=include_metadata_running)
        if min_current_ready:
            last["current_ready_missing"] = max(0, min_current_ready - count_current_ready(db_path))
        if not any(last.values()):
            stable += 1
            if stable >= stable_polls:
                return {"idle": True, "seconds": round(time.monotonic() - started, 1), "remaining": last}
        else:
            stable = 0
        time.sleep(2.0)
    return {"idle": False, "seconds": round(time.monotonic() - started, 1), "remaining": last}


def touch_fixture_images(album: Path) -> int:
    """Give every fixture PNG a new, distinct mtime so the next scan sees each as changed."""
    base = time.time_ns()
    count = 0
    for index, path in enumerate(sorted(album.glob("*.png"))):
        stamp = base + index * 1_000
        os.utime(path, ns=(stamp, stamp))
        count += 1
    return count


def trigger_scan(backend: Backend, library_id: int) -> str:
    """POST a library scan; an already-active scan counts as accepted."""
    deadline = time.monotonic() + 120
    while True:
        status, body = http_request(f"{backend.base_url}/api/libraries/{library_id}/scan", method="POST", body=b"{}")
        if status == 202:
            return "queued"
        if status == 409:
            return "already_active"
        if time.monotonic() > deadline:
            raise EmptyWorkload(f"POST scan never accepted (last HTTP {status}: {body[:200]!r})")
        time.sleep(1.0)


def metadata_done_since(db_path: Path, since: float) -> int:
    """Count metadata jobs that reached `done` at or after `since` (epoch seconds)."""
    return scalar(
        db_path, "SELECT count(*) FROM metadata_index_jobs WHERE state = 'done' AND finished_at >= ?", (since,)
    )


def wait_for_queued_metadata(db_path: Path, since: float, minimum: int, timeout: float) -> int:
    """Wait until at least `minimum` metadata jobs were queued after `since`; fail as an empty workload otherwise."""
    started = time.monotonic()
    seen = 0
    while time.monotonic() - started < timeout:
        seen = scalar(db_path, "SELECT count(*) FROM metadata_index_jobs WHERE queued_at >= ?", (since,))
        if seen >= minimum:
            return seen
        time.sleep(0.5)
    raise EmptyWorkload(f"only {seen} metadata jobs were queued after the rescan (need >= {minimum})")


def run_cycle(
    label: str,
    *,
    backend: Backend,
    fixture: dict[str, Any],
    library_id: int,
    budgets: dict[str, Any],
    window_seconds: float,
    with_pollers: bool,
    drain_timeout: float,
) -> dict[str, Any]:
    """Touch every image, rescan, then count metadata jobs completed in the window."""
    cycle_start = time.monotonic()
    touched_at = time.time()
    touched = touch_fixture_images(fixture["album"])
    log(f"{label}: touched {touched} images, triggering scan")
    scan_request = trigger_scan(backend, library_id)
    queued = wait_for_queued_metadata(fixture["db"], touched_at, int(budgets["min_metadata_jobs_queued"]), 600)
    poller_summary: dict[str, Any] | None = None
    pollers = StatusPollers(backend.base_url, library_id) if with_pollers else None
    if pollers is not None:
        pollers.start()
    window_start = time.time()
    done_before = metadata_done_since(fixture["db"], touched_at)
    log(f"{label}: {queued} metadata jobs queued; measuring {window_seconds:.0f} s (pollers={with_pollers})")
    end_at = time.monotonic() + window_seconds
    while time.monotonic() < end_at:
        if not backend.alive():
            raise RuntimeError(f"backend died during {label}; see {backend.log_path}")
        time.sleep(1.0)
    done_after = metadata_done_since(fixture["db"], touched_at)
    if pollers is not None:
        poller_summary = pollers.stop()
    completed = done_after - done_before
    log(f"{label}: {completed} metadata jobs completed in window; draining")
    drain = wait_until_idle(fixture["db"], timeout=drain_timeout, include_metadata_running=False)
    return {
        "label": label,
        "with_pollers": with_pollers,
        "images_touched": touched,
        "scan_request": scan_request,
        "metadata_jobs_queued": queued,
        "window_seconds": window_seconds,
        "window_started_at": window_start,
        "metadata_jobs_completed_in_window": completed,
        "pollers": poller_summary,
        "drain": drain,
        "monotonic_start": cycle_start,
        "monotonic_end": time.monotonic(),
    }


def sample_status_latency(backend: Backend, library_id: int, samples: int) -> dict[str, Any]:
    """Time the four status endpoints and report per-endpoint and worst-endpoint p95."""
    endpoints = [
        f"/api/libraries/{library_id}/status",
        "/api/libraries/status",
        f"/api/derivatives/status?library_id={library_id}",
        "/api/maintenance/runtime",
    ]
    per_endpoint: dict[str, Any] = {}
    p95_values: list[float] = []
    pooled: list[float] = []
    for path in endpoints:
        durations: list[float] = []
        failures = 0
        aborted = False
        for _ in range(samples):
            started = time.perf_counter()
            status, _body = http_request(f"{backend.base_url}{path}")
            durations.append((time.perf_counter() - started) * 1000.0)
            failures += int(status != 200)
            if len(durations) >= STATUS_ABORT_AFTER_SAMPLES and all(
                value > STATUS_ABORT_MS for value in durations[-STATUS_ABORT_AFTER_SAMPLES:]
            ):
                aborted = True
                break
        endpoint_p95 = percentile(durations, 95)
        p95_values.append(endpoint_p95)
        pooled.extend(durations)
        per_endpoint[path] = {
            "samples": len(durations),
            "http_failures": failures,
            "aborted_early": aborted,
            "p50_ms": round(percentile(durations, 50), 1),
            "p95_ms": round(endpoint_p95, 1),
            "max_ms": round(max(durations), 1),
        }
        log(f"status {path}: p95 {endpoint_p95:.1f} ms over {len(durations)} samples")
    if not pooled:
        raise EmptyWorkload("no status samples were collected")
    return {
        "per_endpoint": per_endpoint,
        "status_p95_ms": round(max(p95_values), 1),
        "pooled_p95_ms": round(percentile(pooled, 95), 1),
    }


def lease_loss_run(
    *,
    backend: Backend,
    fixture: dict[str, Any],
    library_id: int,
    lease_seconds: int,
    drain_timeout: float,
    scan_timeout: float,
) -> dict[str, Any]:
    """Restart with a short catalog lease, poll like the UI, rescan, and count lease-loss failures."""
    backend.stop()
    backend.start({"GALLERY_CATALOG_JOB_LEASE_SECONDS": str(lease_seconds)})
    log(f"lease run: backend restarted with {lease_seconds} s catalog lease")
    wait_until_idle(fixture["db"], timeout=drain_timeout, include_metadata_running=False)
    first_job_id = scalar(fixture["db"], "SELECT COALESCE(max(id), 0) FROM library_jobs")
    pollers = StatusPollers(backend.base_url, library_id)
    pollers.start()
    touch_fixture_images(fixture["album"])
    scan_request = trigger_scan(backend, library_id)
    started = time.monotonic()
    timed_out = True
    while time.monotonic() - started < scan_timeout:
        scans = scalar(
            fixture["db"],
            "SELECT count(*) FROM library_jobs WHERE id > ? AND type IN ('scan', 'rebuild')",
            (first_job_id,),
        )
        active = scalar(
            fixture["db"],
            "SELECT count(*) FROM library_jobs WHERE id > ? AND type IN ('scan', 'rebuild') "
            "AND state IN ('queued', 'running')",
            (first_job_id,),
        )
        if scans > 0 and active == 0:
            timed_out = False
            break
        time.sleep(2.0)
    poller_summary = pollers.stop()
    conn = ro_connect(fixture["db"])
    try:
        rows = conn.execute(
            """
            SELECT id, type, state, COALESCE(error, ''), COALESCE(message, '')
            FROM library_jobs WHERE id > ? AND type IN ('scan', 'rebuild')
            ORDER BY id
            """,
            (first_job_id,),
        ).fetchall()
        library_state = conn.execute("SELECT state FROM libraries WHERE id = ?", (library_id,)).fetchone()
    finally:
        conn.close()
    if not rows:
        raise EmptyWorkload("lease-loss run created no scan job")
    failed = [row for row in rows if row[2] == "failed"]
    lease_loss = [row for row in failed if any(marker in f"{row[3]} {row[4]}".lower() for marker in LEASE_LOSS_MARKERS)]
    return {
        "lease_seconds": lease_seconds,
        "scan_request": scan_request,
        "scan_jobs": len(rows),
        "failed_scan_jobs": len(failed),
        "lease_loss_failed_scans": len(lease_loss),
        "timed_out_waiting_for_scan": timed_out,
        "library_state_after": library_state[0] if library_state else None,
        "failures": [{"id": row[0], "state": row[2], "error": row[3], "message": row[4]} for row in failed][:10],
        "pollers": poller_summary,
    }


def count_superseded_ready(db_path: Path) -> int:
    """Count `ready` derivatives whose source identity no longer matches an active asset."""
    return scalar(
        db_path,
        """
        SELECT count(*) FROM asset_derivatives d
        JOIN assets a ON a.id = d.asset_id
        WHERE d.status = 'ready' AND a.deleted_at IS NULL AND a.offline = 0
          AND (d.source_mtime_ns != a.mtime_ns OR d.source_size != a.size)
        """,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def enforced_metrics(budgets: dict[str, Any], phase: int) -> list[str]:
    """Return the metric names enforced for the selected phase."""
    selected = list(budgets["phase0_metrics"])
    if phase >= 1:
        selected += list(budgets["phase1_metrics"])
    return selected


def evaluate(metrics: dict[str, float], budgets: dict[str, Any], phase: int) -> dict[str, Any]:
    """Compare each metric with its budget and mark which budgets the selected phase enforces."""
    enforced = set(enforced_metrics(budgets, phase))
    results: dict[str, Any] = {}
    for name, (_env, field, mode) in METRIC_BUDGETS.items():
        limit = float(budgets[field])
        value = metrics[name]
        passed = value >= limit if mode == "min" else value <= limit
        results[name] = {
            "value": value,
            "budget": limit,
            "comparison": ">=" if mode == "min" else "<=",
            "enforced": name in enforced,
            "passed": passed,
        }
    return results


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the whole scenario and return the JSON-serializable report."""
    budgets = load_budgets()
    sizing_overrides = {
        field: value
        for field, value in (
            ("min_derivative_jobs", args.min_derivative_jobs),
            ("min_metadata_jobs_queued", args.min_metadata_jobs),
            ("throughput_window_seconds", args.window_seconds),
        )
        if value
    }
    budgets.update(sizing_overrides)
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="gallery-worker-contention-"))
    workdir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    report: dict[str, Any] = {
        "benchmark": "worker_contention",
        "phase": args.phase,
        "workdir": str(workdir),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "images": args.images,
        },
        "budgets": {field: budgets[field] for _env, field, _mode in METRIC_BUDGETS.values()},
        "sizing": {
            field: budgets[field]
            for field in ("min_derivative_jobs", "min_metadata_jobs_queued", "throughput_window_seconds")
        },
        "sizing_overridden": sorted(sizing_overrides),
    }
    backend: Backend | None = None
    probe: LockProbe | None = None
    try:
        log(f"building {args.images}-image fixture in {workdir}")
        fixture = create_fixture(args.python, workdir, args.images)
        report["synthetic_seed"] = seed_synthetic_derivatives(
            fixture["db"],
            min_jobs=int(budgets["min_derivative_jobs"]),
            stale_identities=args.stale_identities,
        )
        library_id = scalar(fixture["db"], "SELECT min(id) FROM libraries")
        if library_id <= 0:
            raise EmptyWorkload("fixture did not register a library")
        log(f"seeded {report['synthetic_seed']['derivative_jobs_total']} derivative_jobs rows")

        backend = Backend(
            python=args.python,
            fixture_root=fixture["root"],
            db_path=fixture["db"],
            cache_dir=fixture["cache"],
            log_path=workdir / "backend.log",
        )
        backend.start()
        probe = LockProbe(fixture["db"])
        probe.start()

        expected_ready = scalar(
            fixture["db"], "SELECT count(*) FROM assets WHERE type = 'image' AND deleted_at IS NULL AND offline = 0"
        ) * len(DERIVATIVE_VARIANT_NAMES)
        settle = wait_until_idle(
            fixture["db"],
            timeout=args.settle_timeout,
            include_metadata_running=False,
            min_current_ready=expected_ready,
        )
        settle["expected_current_ready_derivatives"] = expected_ready
        report["initial_settle"] = settle
        log(f"initial settle: {settle}")

        report["status_latency"] = sample_status_latency(backend, library_id, STATUS_SAMPLES_PER_ENDPOINT)

        window = float(budgets["throughput_window_seconds"])
        cycles: list[dict[str, Any]] = []
        for label, with_pollers in (("cycle_without_pollers", False), ("cycle_with_pollers", True)):
            cycles.append(
                run_cycle(
                    label,
                    backend=backend,
                    fixture=fixture,
                    library_id=library_id,
                    budgets=budgets,
                    window_seconds=window,
                    with_pollers=with_pollers,
                    drain_timeout=args.drain_timeout,
                )
            )
        report["cycles"] = cycles
        baseline_jobs = cycles[0]["metadata_jobs_completed_in_window"]
        polled_jobs = cycles[1]["metadata_jobs_completed_in_window"]
        if baseline_jobs <= 0:
            raise EmptyWorkload("zero metadata jobs completed in the no-poller window; cannot compute a ratio")

        orphan_wait = wait_until_idle(
            fixture["db"], timeout=args.drain_timeout, include_metadata_running=False, stable_polls=2
        )
        log("waiting 60 s after the queue drained before counting orphan running metadata jobs")
        time.sleep(60)
        orphans = scalar(fixture["db"], "SELECT count(*) FROM metadata_index_jobs WHERE state = 'running'")
        superseded = count_superseded_ready(fixture["db"])
        metadata_done = scalar(fixture["db"], "SELECT count(*) FROM metadata_index_jobs WHERE state = 'done'")
        derivative_done = scalar(
            fixture["db"],
            "SELECT count(*) FROM derivative_jobs WHERE id > ? AND state = 'done'",
            (int(report["synthetic_seed"]["last_seeded_job_id"]),),
        )
        if metadata_done <= 0:
            raise EmptyWorkload("no metadata job finished during the run")
        if derivative_done <= 0:
            raise EmptyWorkload("no real derivative job finished during the run")

        locked_before_lease_run = backend.locked_log_lines()

        lease = lease_loss_run(
            backend=backend,
            fixture=fixture,
            library_id=library_id,
            lease_seconds=int(args.lease_seconds),
            drain_timeout=args.drain_timeout,
            scan_timeout=args.scan_timeout,
        )
        report["lease_loss_run"] = lease
        probe.stop()
        locked_total = backend.locked_log_lines()

        metrics = {
            "status_p95_ms": report["status_latency"]["status_p95_ms"],
            "polling_throughput_ratio": round(polled_jobs / baseline_jobs, 4),
            "max_write_lock_hold_ms": probe.max_hold_ms(cycles[0]["monotonic_start"]),
            "database_locked_log_lines": locked_total,
            "lease_loss_failed_scans": lease["lease_loss_failed_scans"],
            "orphan_running_metadata_jobs": orphans,
            "superseded_ready_derivatives": superseded,
        }
        report["metrics"] = metrics
        report["diagnostics"] = {
            "write_lock_probe": probe.summary(),
            "write_lock_max_hold_ms_whole_run": probe.max_hold_ms(),
            "database_locked_log_lines_before_lease_run": locked_before_lease_run,
            "metadata_jobs_per_window_without_pollers": baseline_jobs,
            "metadata_jobs_per_window_with_pollers": polled_jobs,
            "orphan_wait": orphan_wait,
            "real_derivative_jobs_done": derivative_done,
            "metadata_jobs_done": metadata_done,
            "backend_log": str(backend.log_path),
        }
        report["results"] = evaluate(metrics, budgets, args.phase)
        failing = [name for name, item in report["results"].items() if item["enforced"] and not item["passed"]]
        report["failed_metrics"] = failing
        report["ok"] = not failing
        report["exit_code"] = 0 if not failing else EXIT_BUDGET_FAILURE
    except EmptyWorkload as exc:
        report["ok"] = False
        report["empty_workload"] = str(exc)
        report["exit_code"] = EXIT_EMPTY_WORKLOAD
        log(f"EMPTY WORKLOAD: {exc}")
    finally:
        if probe is not None and probe.is_alive():
            probe.stop()
        if backend is not None:
            backend.stop()
        report["duration_seconds"] = round(time.time() - started_at, 1)
        if not args.keep_workdir and not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)
            report["workdir_removed"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the benchmark, print the report, and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--phase",
        type=int,
        choices=(0, 1),
        default=0,
        help="0 enforces the Phase 0 gate; 1 also enforces the Phase 1 metrics (all metrics are always reported)",
    )
    parser.add_argument("--images", type=int, default=1500, help="real PNG files in the fixture (default 1500)")
    parser.add_argument("--stale-identities", type=int, default=6, help="synthetic superseded identities per variant")
    parser.add_argument("--python", default=sys.executable, help="interpreter used for the fixture and the backend")
    parser.add_argument("--workdir", default="", help="keep all artifacts in this directory (default: temp dir)")
    parser.add_argument("--keep-workdir", action="store_true", help="do not delete the temp directory afterwards")
    parser.add_argument("--output", default="", help="also write the JSON report to this file")
    parser.add_argument(
        "--min-derivative-jobs", type=int, default=0, help="override [worker_contention] sizing (smoke runs)"
    )
    parser.add_argument(
        "--min-metadata-jobs", type=int, default=0, help="override [worker_contention] sizing (smoke runs)"
    )
    parser.add_argument("--window-seconds", type=float, default=0, help="override the throughput window (smoke runs)")
    parser.add_argument("--lease-seconds", type=int, default=30, help="catalog lease for the lease-loss run")
    parser.add_argument("--settle-timeout", type=float, default=1800, help="seconds to wait for startup work to settle")
    parser.add_argument("--drain-timeout", type=float, default=900, help="seconds to wait for a queue to drain")
    parser.add_argument("--scan-timeout", type=float, default=900, help="seconds to wait for the lease-loss scan")
    args = parser.parse_args(argv)
    # Let `finally` blocks stop the backend subprocess when the benchmark itself is terminated.
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(143))

    report = run_benchmark(args)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    if report.get("empty_workload"):
        return EXIT_EMPTY_WORKLOAD
    if not report.get("ok"):
        failed = ", ".join(report.get("failed_metrics", [])) or "unknown"
        log(f"BUDGET FAILURE: {failed}")
        return EXIT_BUDGET_FAILURE
    log("all enforced budgets passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
