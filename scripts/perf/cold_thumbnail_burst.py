#!/usr/bin/env python3
"""Manual load check: does a burst of cold thumbnails delay an unrelated API request?

Starts a real uvicorn on 127.0.0.1 with a throwaway catalog of ``count`` large PNG sources, fires ``count``
cold ``/api/thumbnail`` requests at once, and probes ``/api/search?scope=all`` every 250 ms while they are in
flight. A derivative request that parks a thread-pool thread while it waits makes the probe slow (PR-01 / BL-9).

Not a CI gate: timings depend on the host. Exit status is non-zero when any thumbnail request fails.

    backend/.venv_linux/bin/python scripts/perf/cold_thumbnail_burst.py 60 --port 4971 --size 2048x3072
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _setup_script(repo: Path, root: Path, album: Path, count: int, width: int, height: int) -> str:
    return f"""
import sys; sys.path.insert(0, {str(repo)!r})
from pathlib import Path
from PIL import Image
album = Path({str(album)!r})
base = Image.effect_noise(({width // 2}, {height // 2}), 40).convert("RGB").resize(({width}, {height}))
for i in range({count}):
    im = base.copy(); im.paste((i * 4 % 255, 80, 160), (0, 0, 64, 64)); im.save(album / f"img_{{i:03d}}.png", compress_level=1)
from backend.metadata_store import create_library, index_directory_tree
create_library([Path({str(root)!r})], name="cold")
index_directory_tree(Path({str(root)!r}))
"""


def _get(base_url: str, path: str, timeout: float = 60) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(base_url + path, timeout=timeout) as response:
            response.read()
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:  # noqa: BLE001 - a refused or timed-out request counts as a failure
        code = 0
    return code, (time.perf_counter() - started) * 1000


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def main() -> int:
    """Run the burst and return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("count", type=int, nargs="?", default=60, help="cold thumbnails fired at once (default 60)")
    parser.add_argument("--port", type=int, default=4971, help="port for the throwaway server (default 4971)")
    parser.add_argument("--size", default="2048x3072", help="source image WIDTHxHEIGHT (default 2048x3072, ~6 MP)")
    parser.add_argument("--tmp-dir", default=None, help="parent directory for the throwaway catalog")
    args = parser.parse_args()
    width, height = (int(part) for part in args.size.lower().split("x"))
    count = args.count

    tmp = Path(tempfile.mkdtemp(prefix="coldburst-", dir=args.tmp_dir))
    root = tmp / "gallery"
    album = root / "album"
    album.mkdir(parents=True)
    env = dict(
        os.environ,
        PATH_SAFETY_ROOT=str(root),
        GALLERY_METADATA_DB=str(tmp / "g.db"),
        GALLERY_THUMBNAIL_CACHE_DIR=str(tmp / "cache"),
        ENABLE_METRICS="false",
        GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED="false",
        GALLERY_SEARCH_INDEXER_ENABLED="false",
        GALLERY_METADATA_INDEXER_ENABLED="false",
        GALLERY_DERIVATIVE_RECONCILE_ENABLED="false",
        GALLERY_CATALOG_SERVICE_ENABLED="false",
        GALLERY_CATALOG_RECONCILE_ENABLED="false",
        GALLERY_CATALOG_WATCHER_ENABLED="false",
        GALLERY_INTEGRITY_CHECK_ENABLED="false",
    )
    server = None
    failures = 0
    try:
        subprocess.run(
            [sys.executable, "-c", _setup_script(REPO, root, album, count, width, height)],
            env=env,
            check=True,
            cwd=REPO,
        )
        with open(tmp / "server.log", "w") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(args.port)],
                env=env,
                cwd=REPO,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{args.port}"
            for _ in range(150):
                if _get(base_url, "/api/health", timeout=2)[0] == 200:
                    break
                time.sleep(0.2)
            else:
                print("server did not become healthy", file=sys.stderr)
                return 2
            search = "/api/search?" + urllib.parse.urlencode({"q": "img", "scope": "all", "limit": 50})
            baseline = [_get(base_url, search)[1] for _ in range(5)]
            print(f"baseline search ms: {sorted(round(x) for x in baseline)}")

            results: list[tuple[int, float]] = []

            def thumb(index: int) -> None:
                query = urllib.parse.urlencode({"path": str(album / f"img_{index:03d}.png"), "max_long_edge": 512})
                results.append(_get(base_url, "/api/thumbnail?" + query))

            threads = [threading.Thread(target=thumb, args=(i,)) for i in range(count)]
            started = time.perf_counter()
            for thread in threads:
                thread.start()
            probes: list[float] = []
            probe_codes: list[int] = []
            while any(thread.is_alive() for thread in threads):
                time.sleep(0.25)
                code, ms = _get(base_url, search)
                probes.append(ms)
                probe_codes.append(code)
            for thread in threads:
                thread.join()
            total = time.perf_counter() - started
            codes: dict[int, int] = {}
            for code, _ in results:
                codes[code] = codes.get(code, 0) + 1
            failures = sum(n for code, n in codes.items() if code != 200) + sum(1 for c in probe_codes if c != 200)
            print(
                f"{count} cold thumbnails: all answered after {total:.1f} s, status counts {codes}, "
                f"slowest {max(ms for _, ms in results):.0f} ms"
            )
            if probes:
                print(
                    f"search probes during the burst (n={len(probes)}): p50 {statistics.median(probes):.0f} ms, "
                    f"p95 {_percentile(probes, 95):.0f} ms, max {max(probes):.0f} ms"
                )
                print("probe ms in order:", [round(p) for p in probes])
            print(json.dumps({"count": count, "total_s": round(total, 2), "status_counts": codes}))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f"FAIL: {failures} request(s) did not return 200", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
