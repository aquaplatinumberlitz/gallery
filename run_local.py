"""Run the gallery fully offline on one loopback port (Linux).

Unlike ``start.py`` (two development servers with hot reload), this builds the frontend once and starts only the
backend, which serves the built SPA itself (``GALLERY_MODE=local``). No nginx, no proxy secret, no network access.

    python3 run_local.py                 # build if needed, start, open the browser
    python3 run_local.py --port 4801     # another port
    python3 run_local.py --rebuild       # force a frontend rebuild
    python3 run_local.py --no-browser

The server listens on 127.0.0.1 only and has no authentication: do not expose it to other machines.
"""

from __future__ import annotations

import argparse
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import start  # reuse its venv and dependency setup; importing it only defines functions and prints the OS

ROOT_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = ROOT_DIR / "frontend"
DIST_INDEX = FRONTEND_DIR / "dist" / "index.html"
DEFAULT_PORT = 4701
HOST = "127.0.0.1"
HEALTH_TIMEOUT_SECONDS = 120
SHUTDOWN_TIMEOUT_SECONDS = 30

# Anything that changes the built output: the sources, the entry page, the lockfile and the Vite/TS config.
_BUILD_INPUT_DIRS = ("src", "public")
_BUILD_INPUT_FILES = ("index.html", "package.json", "pnpm-lock.yaml", "vite.config.ts", "tsconfig.json")


def newest_build_input_mtime(frontend_dir: Path) -> float:
    """Return the newest modification time among the files the frontend build depends on."""
    newest = 0.0
    for name in _BUILD_INPUT_FILES:
        path = frontend_dir / name
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
    for dirname in _BUILD_INPUT_DIRS:
        for root, _dirs, files in os.walk(frontend_dir / dirname):
            for filename in files:
                try:
                    newest = max(newest, os.stat(os.path.join(root, filename)).st_mtime)
                except OSError:
                    continue
    return newest


def needs_build(frontend_dir: Path, force: bool = False) -> bool:
    """Return True when ``dist/index.html`` is missing, older than its inputs, or a rebuild was requested."""
    if force:
        return True
    index = frontend_dir / "dist" / "index.html"
    if not index.is_file():
        return True
    return newest_build_input_mtime(frontend_dir) > index.stat().st_mtime


def port_is_free(port: int) -> bool:
    """Return True when the loopback port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def wait_until_healthy(port: int, process: subprocess.Popen, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    """Poll ``/api/health`` until it answers, the process exits, or the timeout passes."""
    deadline = time.monotonic() + timeout
    url = f"http://{HOST}:{port}/api/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - fixed loopback http URL
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    return False


def build_frontend(pkg_manager: str) -> None:
    """Build the SPA into ``frontend/dist`` with the repo's package manager."""
    print("\n[3/4] Building frontend (first run or sources changed)...")
    start.run_command([pkg_manager, "run", "build"], cwd=FRONTEND_DIR, shell=True)
    if not DIST_INDEX.is_file():
        print("ERROR: the frontend build did not produce frontend/dist/index.html")
        sys.exit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the gallery offline on one loopback port.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT") or DEFAULT_PORT))
    parser.add_argument("--rebuild", action="store_true", help="force a frontend rebuild")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if platform.system() != "Linux":
        print(f"WARNING: only Linux is supported; detected {platform.system()}. Continuing at your own risk.")
    if not port_is_free(args.port):
        print(f"ERROR: port {args.port} is already in use. Stop that process or pass --port.")
        return 1

    python_exec = start.setup_backend()
    pkg_manager = start.setup_frontend()
    if needs_build(FRONTEND_DIR, force=args.rebuild):
        build_frontend(pkg_manager)
    else:
        print("\n[3/4] Frontend build is up to date.")

    print(f"\n[4/4] Starting the gallery on http://{HOST}:{args.port} (offline, loopback only)...")
    env = os.environ.copy()
    env.pop("PRODUCTION", None)  # local mode and production are mutually exclusive
    env["GALLERY_MODE"] = "local"
    env["PORT"] = str(args.port)
    command = [str(python_exec), "-m", "uvicorn", "backend.main:app", "--host", HOST, "--port", str(args.port)]
    process = subprocess.Popen(command, cwd=ROOT_DIR, env=env)
    try:
        if not wait_until_healthy(args.port, process):
            print("ERROR: the backend did not become healthy; see its output above.")
            return 1
        url = f"http://{HOST}:{args.port}"
        print(f"\nGallery is running at {url}\nPress Ctrl+C to stop.")
        if not args.no_browser:
            webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0
    finally:
        if process.poll() is None:
            # SIGINT lets the lifespan shutdown (database writer, workers) finish cleanly.
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())
