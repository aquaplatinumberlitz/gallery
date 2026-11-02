# Web-vitals harness

Manual lab tools for the user-facing numbers in
[`docs/testing/PERFORMANCE_TESTING.md`](../../../docs/testing/PERFORMANCE_TESTING.md):
home LCP and FCP, album open, the lightbox, and main-thread long tasks. They drive
Chromium through Playwright with CDP network and CPU throttling, against a backend on a
fixture library, behind a static server that mirrors the production nginx shape.

These are **manual tools, not CI gates**. They print numbers; they do not fail a build.
Use them to compare two builds in the same run, and keep the commit and date with any
number you record.

## Prerequisites

- Node.js (the harness was run with 22) and the frontend dependencies (`@playwright/test` is pinned in `frontend/`).
- Chromium for the pinned Playwright, installed into a directory you choose:

  ```bash
  cd frontend
  corepack pnpm install --frozen-lockfile
  PLAYWRIGHT_BROWSERS_PATH=/path/to/pwb corepack pnpm exec playwright install chromium
  ```

  Every script reads `PLAYWRIGHT_BROWSERS_PATH` from the environment, so set it on each
  command. The pinned `@playwright/test` 1.61 expects `chromium_headless_shell-1228`.
- A Python with the backend dependencies (PIL, FastAPI, uvicorn) for the backend and the
  fixture generator.
- `openssl` on `PATH` only if you use `serve_dist_h2.cjs` without `--cert`/`--key`.

Run the Node scripts **from `frontend/`** (`cd frontend && node ../scripts/perf/web_vitals/<script>.cjs`).
They resolve `@playwright/test` from the current directory, so the pinned version is used. If
you run them from elsewhere, set `NODE_PATH` to a directory that contains a `playwright` or
`@playwright/test` package.

Paths below use `ROOT`, a scratch directory you own (for example `/tmp/gallery-web-vitals`).
Keep it out of the repository.

## 1. Make a fixture library

`make_photo_fixture.py` writes photo-like PNGs (mixed portrait and landscape, 832–1216 px).
Put them in a folder named `real`: the scripts open the album `real` by default.

```bash
mkdir -p "$ROOT/library"
python3 scripts/perf/web_vitals/make_photo_fixture.py --out "$ROOT/library/real" --count 20 --seed 1
```

The first three images print their measured sizes:

```text
photo_000.png 1184x1184 thumb_512 webp q78 47.7 KB preview_1440 webp q86 260.9 KB
```

Target: thumb_512 about 35–50 KB, preview_1440 about 250 KB. The generator is deterministic:
the same `--seed` and `--count` write identical files.

## 2. Start the backend on the fixture

Start uvicorn directly, not `python -m backend.main`: that entry point binds `0.0.0.0`, and
the harness keeps every service on `127.0.0.1`.

```bash
mkdir -p "$ROOT/meta" "$ROOT/thumbs"
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$ROOT/proxy-secret"

PRODUCTION=1 \
GALLERY_TRUSTED_PROXY_SECRET="$(cat "$ROOT/proxy-secret")" \
PATH_SAFETY_ROOT="$ROOT" \
GALLERY_METADATA_DB="$ROOT/meta/gallery_metadata.db" \
GALLERY_THUMBNAIL_CACHE_DIR="$ROOT/thumbs" \
GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false \
<python-with-backend-deps> -m uvicorn backend.main:app --host 127.0.0.1 --port 4701
```

Run it from the repository root with the backend's Python (for example
`backend/.venv_linux/bin/python`).

- `PRODUCTION=1` turns on proxy authentication. Every `/api` request must carry
  `X-Gallery-Proxy-Secret`, and the backend refuses to start without a secret of at least
  32 characters. The static server and the scripts add the header; direct calls must add it
  themselves.
- `GALLERY_TRUSTED_PROXY_SECRET` is the secret. The same value goes in `$ROOT/proxy-secret`.
- `PATH_SAFETY_ROOT` is the boundary for library paths. Put the fixture under it.
- `GALLERY_METADATA_DB` and `GALLERY_THUMBNAIL_CACHE_DIR` keep the measurement database and
  derivative cache out of the repository and let you reset them between runs.
- `GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false` stops startup from queueing a scan of every
  registered library. Registration (below) queues the one scan you need.

### Register the library through the API

```bash
SECRET="$(cat "$ROOT/proxy-secret")"
curl -s -X POST http://127.0.0.1:4701/api/libraries \
  -H "X-Gallery-Proxy-Secret: $SECRET" -H 'content-type: application/json' \
  -d "{\"root_path\": \"$ROOT/library\", \"name\": \"Fixture\"}"

# Wait until the scan finishes: state "ready" and asset_count 20
curl -s http://127.0.0.1:4701/api/libraries -H "X-Gallery-Proxy-Secret: $SECRET"
```

`root_path` must be inside `PATH_SAFETY_ROOT`. Thumbnails and previews are generated on
demand, so with a fresh `GALLERY_THUMBNAIL_CACHE_DIR` the first album open is the cold case.

Stop the backend by its PID (`kill <pid>`).

## 3. Build and serve `frontend/dist`

```bash
cd frontend && corepack pnpm run build && cd ..
```

Serve it with one of the two static servers. Both bind `127.0.0.1`, proxy `/api` to the
backend, and add the secret.

| Script | Transport | Use it for |
|--------|-----------|------------|
| `serve_dist.cjs --mode tuned` | HTTP/1.1, gzip for text assets, `immutable` under `/assets/` | Repeat-visit and cache numbers |
| `serve_dist_h2.cjs` | TLS + HTTP/2 (HTTP/1.1 also allowed), same caching | The production-shaped first-load profile |

```bash
# HTTP/1.1
node scripts/perf/web_vitals/serve_dist.cjs --secret-file "$ROOT/proxy-secret" \
  --port 8080 --backend-port 4701 --mode tuned

# TLS + HTTP/2, self-signed certificate generated into a temp directory
node scripts/perf/web_vitals/serve_dist_h2.cjs --secret-file "$ROOT/proxy-secret" \
  --port 8443 --backend-port 4701
```

`serve_dist.cjs` modes: `asis` (default; the nginx template as written: gzip for `text/html`
only, ETag, no `Cache-Control`), `tuned` (gzip for every text asset, immutable `/assets/`,
`no-cache` elsewhere), and `dev` (proxies non-API paths to a Vite server on `--vite-port`,
default 4833). Use `tuned` to match the production intent.

`serve_dist_h2.cjs` with no `--cert`/`--key` writes a two-day self-signed `localhost`
certificate into `os.tmpdir()` (set `TMPDIR` to choose the directory) and removes it on exit.
The equivalent command is:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 2 \
  -subj /CN=localhost -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Pass the result with `--cert cert.pem --key key.pem`. Keep key files outside the repository.

In the smoke run for this harness, a repeat visit over the self-signed HTTPS server
re-transferred the assets and thumbnails that the HTTP/1.1 server served from cache. Treat
repeat-visit numbers from `serve_dist_h2.cjs` with suspicion, and take them from
`serve_dist.cjs --mode tuned`.

## 4. Profiles

| Profile | Env value | Network | CPU | Viewport |
|---------|-----------|---------|-----|----------|
| Desktop | `desktop` | unthrottled | 1× | 1440×900, DPR 1 |
| Mobile, typical 4G | `4g` | 85 ms RTT, 9 Mbps down | 4× | 390×844, DPR 2 |
| Mobile, slow 4G (Lighthouse-like) | `slow4g` | 150 ms RTT, 1.6 Mbps down | 4× | 390×844, DPR 2 |

The env name is `NET` for `home_waterfall.cjs` and `PROFILE` for the other scripts. The upload
rates are the scratch values and differ between scripts (about 1 Mbps in the revisit and
open-profile scripts, 0.73–1.5 Mbps in the others), so compare like with like.

## 5. Scripts

Every script prints to stdout. Errors go to stderr with an `ERR` prefix and exit 1.

### `serve_dist.cjs`

```text
node scripts/perf/web_vitals/serve_dist.cjs --secret-file PATH
     [--dist DIR] [--port 8080] [--backend-port 4701] [--mode asis|tuned|dev] [--vite-port 4833]
```

The secret comes from `--secret-file` or the `GALLERY_PROXY_SECRET` environment variable; one of
the two is required. `--dist` defaults to `frontend/dist` in this checkout.
Output: `tuned on 8080 (dist …, backend 127.0.0.1:4701)`.

### `serve_dist_h2.cjs`

```text
node scripts/perf/web_vitals/serve_dist_h2.cjs --secret-file PATH
     [--dist DIR] [--port 8443] [--backend-port 4701] [--cert CERT --key KEY]
```

Output: `h2 on 8443 (dist …, backend 127.0.0.1:4701, https)`.

### `home_waterfall.cjs`

```text
BASE=http://127.0.0.1:8080 NET=slow4g|4g|desktop [LIST=1] node scripts/perf/web_vitals/home_waterfall.cjs
```

`BASE` defaults to `http://127.0.0.1:8080`, `NET` to `slow4g`. It loads home twice in one
context: `cold`, then `repeat`.

Output, one line per run:

```text
== cold: fcp 2880 lcp 3908 (IMG.) requests 76 bytes 530768
== repeat: fcp 892 lcp 1316 (IMG.) requests 76 bytes 2583
```

`fcp` and `lcp` are milliseconds from navigation. `bytes` is the encoded transfer size of
the requests that finished. With `LIST=1`, each request also prints its start and end (ms
from the first request), encoded bytes, status, `cache` if served from cache,
`content-encoding`, and path. Use `LIST=1` to find what sits before the LCP image.

### `album_flow.cjs`

```text
BASE=http://127.0.0.1:8080 PROFILE=slow4g|4g|desktop ALBUM=real \
  node scripts/perf/web_vitals/album_flow.cjs [label]
```

`ALBUM` is the album folder name (`data-album-name`), default `real`. The optional positional
argument is a label copied into the output.

Output: one JSON object on one line:

- `album`: `firstCardMs`, `visibleThumbsMs` (click until every visible thumbnail has loaded),
  `visible`, `net` (thumbnail request counts and bytes), `clickINP`.
- `scroll1`, `scroll2`: two fast scrolls of eight viewports. `frames`, `p50`, `p95`, `over50`
  (frame gaps in ms, from `requestAnimationFrame`), `settleMs`, `longtasks`, `net`.
- `lightbox`: `visibleMs`, `firstImageMs`, `previewMs` (preview loaded), `clickINP`, `net`,
  `previewReqTimes`.
- `previewReqs`, `next` (three ArrowRight steps: `slideMs`, `previewMs`, `net`), `longtasksTotal`.

### `album_revisit.cjs`

```text
BASE=http://127.0.0.1:8080 PROFILE=4g|slow4g|desktop ALBUM=real node scripts/perf/web_vitals/album_revisit.cjs
```

Opens the album on a first visit and again in a new page of the same context.

Output, one line per visit:

```text
4g first visibleThumbsMs 790 thumbnail responses {"200":11}
4g revisit visibleThumbsMs 459 thumbnail responses {"cache":11}
```

The revisit should show only `cache` responses (no thumbnail network requests).

### `album_open_profile.cjs`

```text
BASE=http://127.0.0.1:8080 PROFILE=4g|slow4g|desktop ALBUM=real node scripts/perf/web_vitals/album_open_profile.cjs
```

Output: one JSON object: `firstCard` (ms from click to the first photo card), `lt`
(`[start, duration]` of each long task after the click, relative to the click), `api`
(`[path, start, duration, transferSize]` for each non-thumbnail `/api` request), `cards`, and
`dom` (element count). Use it to attribute the album-open long task.

### `make_photo_fixture.py`

```text
python3 scripts/perf/web_vitals/make_photo_fixture.py --out DIR [--count 20] [--seed 1]
```

Writes `photo_000.png` … into `DIR` and prints the thumb_512 (WebP q78) and preview_1440
(WebP q86) sizes for the first three images. Needs PIL only.

### `lib.cjs`

Shared helpers for the Node scripts: argument parsing, the proxy-secret lookup, the
self-signed certificate, and the Playwright resolver. It has no command line of its own.

## Notes for measurements

- Run each profile at least three times and report the median. Use the same machine, the same
  fixture, and the same commit for both sides of a comparison.
- Headless Chromium rasterises on the CPU, so frame times from `album_flow.cjs` are only a
  rough guide. Check scroll smoothness on a real phone.
- `album_flow.cjs` waits up to 60 s for the visible thumbnails after each scroll. If they do not
  settle, `settleMs` is `"timeout"`. A first album open that never settles fails with `ERR` after
  120 s.
- Stop the servers and the backend by PID when you are done.
