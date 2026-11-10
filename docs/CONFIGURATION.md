# Configuration

Status: Maintained

Last verified against `backend/config.py`, `frontend/vite.config.ts`, frontend
environment reads, and the server nginx site config: 2026-11-02.

Boolean flags parsed by `_env_flag()` treat `0`, `false`, `no`, and `off`
case-insensitively as false; any other provided value is true. Flags documented as
`== "1"` or `== "true"` use the stricter comparison shown.

## Server runtime topology

The VPS forwards ports `4701-4800` to the internet. Gallery reserves fixed port
`4701` for the FastAPI backend and fixed port `4702` for the Vite development
server. Both must bind `127.0.0.1`: the public nginx entrypoint on
`150.230.56.153` (HTTPS, Basic Auth, proxy secret) is the only way in. A backend
bound to `0.0.0.0` without `PRODUCTION=1` and `GALLERY_TRUSTED_PROXY_SECRET`
answers every API request from the internet without authentication, and the
Vite dev server forwards `/api` to the backend the same way.

Production topology (`frontend/gallery-nginx-prod.conf`), used for real users:

| Public path | nginx behavior | Service | Standard purpose |
| ----------- | -------------- | ------- | ---------------- |
| `/api` | Proxy to `http://127.0.0.1:4701` | Backend | FastAPI/uvicorn API server for `backend.main:app`. |
| `/assets/` | Static files from `frontend/dist/assets/`, `Cache-Control: public, max-age=31536000, immutable` | Built SPA | Content-hashed JS, CSS and font files. |
| `/landpage/` | Static `frontend/dist/landpage/`, `Cache-Control: public, max-age=86400` | Built SPA | Intro landing pages. File names are not hashed, so they are cacheable for a day and then revalidated with ETag; never `immutable`. |
| `/` | Static `frontend/dist/`, SPA fallback to `index.html`, `Cache-Control: no-cache` | Built SPA | Revalidated entry document, so a new build is picked up on the next visit. |

The production template also enables HTTP/2 (`listen 443 ssl http2`) and gzip
for `text/css`, `text/javascript`, `application/javascript`,
`application/json` and `image/svg+xml` (the default `nginx.conf` compresses
only `text/html`). `text/event-stream` is not compressed, so `/api/events`
keeps streaming.

**Pre-compressed assets (Brotli).** `pnpm run build` writes `<file>.br` (Brotli
quality 11) and `<file>.gz` (gzip level 9) next to every text file under
`dist/assets/` (`js`, `css`, `svg`, `json`, `html`, `txt`, `xml`; woff2 fonts and
images are skipped, and a sibling is only written when it is smaller). The
`/assets/` location of the template serves them with `gzip_static on;` (stock
nginx) and `brotli_static on;` (needs the Brotli module). On the mount-critical
chunks Brotli is about 12% smaller than gzip. Dynamic `gzip on` stays the fallback
for any file without a pre-compressed copy and for clients that do not send `br`.

To enable Brotli on the Ubuntu VPS (a separate, manual step; the repository never
changes the VPS):

1. Install the modules. The packages add `load_module` snippets under
   `/etc/nginx/modules-enabled/`, which the stock `nginx.conf` includes:
   `sudo apt install libnginx-mod-http-brotli-static libnginx-mod-http-brotli-filter`.
   If your `nginx.conf` does not include that directory, add these two lines at the
   top, outside `http {}`: `load_module modules/ngx_http_brotli_filter_module.so;`
   and `load_module modules/ngx_http_brotli_static_module.so;`.
2. Back up `/etc/nginx/sites-enabled/gallery`, then edit it in place (never copy the
   template over it) and add `brotli_static on;` and `gzip_static on;` to its
   `location /assets/` block. Install the modules first: nginx refuses to start on a
   `brotli_static` directive it does not know.
3. `sudo nginx -t && sudo systemctl reload nginx`.
4. Rebuild the frontend on the VPS (the deploy steps in `AGENTS.md`), so the `.br` and
   `.gz` files exist, and check the result:
   `curl -sI -H 'Accept-Encoding: br' -u USER https://150.230.56.153/assets/<file>.js`
   must show `Content-Encoding: br` and `Vary: Accept-Encoding`.

**Landing-page cache (`/landpage/`).** The intro iframe loads about 20 files from
`/landpage/<theme>/`. They keep their original names (no content hash), so the template gives them
their own `location /landpage/` with `Cache-Control: public, max-age=86400`; after a day the browser
revalidates and nginx answers `304` from the ETag and `Last-Modified` it already sends. `immutable`
is deliberately not used: a changed page would stay stale for a year. Before this block the `/` location
applied `no-cache` to the landing pages, so every revalidation re-requested all of them. The day/night
toggle in `normal_angel` and `normal_mouse` now switches in place and no longer reloads the iframe.
The live VPS site file is not replaced by the template: add the block to
`/etc/nginx/sites-enabled/gallery` in place, next to `location /assets/` (back up first, then
`sudo nginx -t && sudo systemctl reload nginx`), and check with
`curl -sIk -u USER https://150.230.56.153/landpage/normal_angel/assets/css/style.css`, which must show
`Cache-Control: public, max-age=86400` and an `ETag`.

The web-vitals lab servers (`scripts/perf/web_vitals/serve_dist.cjs --mode tuned` and
`serve_dist_h2.cjs`) serve the same files the same way: `.br` when the client accepts
`br`, else `.gz`, else dynamic gzip; `--no-brotli` mimics a server without the module. Both send
`public, max-age=86400` under `/landpage/` and, like nginx, an ETag with `304` answers for unchanged
files; `--no-landpage-cache` restores the old template (`no-cache`) to measure the before.

The development template (`frontend/gallery-nginx-dev.conf`) proxies `/` to
the Vite dev server on `127.0.0.1:4702` instead. Use it only while editing the
frontend on the VPS: the dev server serves hundreds of unbundled, uncompressed
modules (a cold mobile load measured about 40 s on a throttled 4G profile,
against about 3 s for the production template).

Both nginx templates require HTTP Basic Auth for the whole site and include the
root-owned `/etc/nginx/snippets/gallery-proxy-secret.conf` inside `/api`. That
snippet must set `X-Gallery-Proxy-Secret` to the same value as
`GALLERY_TRUSTED_PROXY_SECRET`; keep it and the `.htpasswd` file outside the
repository. Requests are limited to 1 MiB bodies.

Deploy on the VPS (the backend runs as the systemd unit `gallery-backend.service`):

```bash
cd /home/ubuntu/gallery-repo && git pull --ff-only origin main
cd frontend && corepack pnpm install --frozen-lockfile && corepack pnpm run build
sudo systemctl restart gallery-backend
```

The unit runs `backend/.venv_linux/bin/python -m uvicorn backend.main:app
--host 127.0.0.1 --port 4701` as `ubuntu`. It reads
`EnvironmentFile=/etc/gallery/backend.env` (root:ubuntu, mode 640), which holds
`PRODUCTION=1` and `GALLERY_TRUSTED_PROXY_SECRET`. The same secret is set by the
root-only nginx snippet `/etc/nginx/snippets/gallery-proxy-secret.conf`. The
unit uses `KillSignal=SIGINT` so the lifespan shutdown (database writer) completes.

The live VPS site (`/etc/nginx/sites-enabled/gallery`) differs from the template:
- It serves HTTPS with HTTP/2 on `https://150.230.56.153`, using a Let's Encrypt
  IP-address certificate (short-lived profile, about 6 days).
- It has Basic Auth on the 443 server block.
- Port 80 only keeps the ACME challenge and `/git/`; everything else is a 301 redirect to HTTPS.

Certificates are managed by certbot 5.9 in `/opt/certbot-ip` with config in
`/etc/letsencrypt-ip`. The `gallery-cert-renew.timer` runs every 6 hours, and
a deploy hook reloads nginx after renewal.

When the template changes, port its gallery locations into the live file in
place. Back up first, then run `sudo nginx -t && sudo systemctl reload nginx`.
Never copy the whole template over the live file, which would drop the ACME
location and the other routes.

Development frontend command from `frontend/` (dev template only):

```bash
cd /home/ubuntu/gallery-repo/frontend
VITE_PORT=4702 corepack pnpm exec vite --host 127.0.0.1 --port 4702
```

Do not set `VITE_API_URL` for the public VPS nginx path unless deliberately
bypassing same-origin routing. With `VITE_API_URL` unset, browser API calls use
same-origin `/api`, and nginx forwards them to `127.0.0.1:4701`. The Vite dev
proxy also defaults `/api` to `http://localhost:4701` for direct local access to
the frontend dev server.

`python3 start.py` uses exactly `4701` and `4702`. It checks both ports before
setup and again before launching the services. If either port is occupied, it
prints the conflicting service and exits with status `1`; it never increments
to another port.

Useful health checks:

```bash
curl http://127.0.0.1:4701/api/health
curl http://150.230.56.153/api/health
curl -I http://150.230.56.153/
```

## Backend environment variables

| Variable                                               | Type                    | Default                                               | Behavior                                                                                                 |
| ------------------------------------------------------ | ----------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `PRODUCTION`                                           | boolean (`"1"`)         | `0`                                                   | Enables production mode; also changes the default for metrics.                                           |
| `GALLERY_TRUSTED_PROXY_SECRET`                         | secret string            | unset                                                 | Required at 32+ characters when `PRODUCTION=1`. Protected `/api` routes require the matching `X-Gallery-Proxy-Secret` header; configuring a secret in development also enables the check. |
| `PORT`                                                 | integer                 | `4701` in `backend/main.py` fallback                  | Uvicorn port when running `python3 -m backend.main` directly.                                            |
| `FRONTEND_ORIGIN`                                      | URL/string              | unset                                                 | Extra CORS origin; trailing slash is stripped.                                                           |
| `FRONTEND_PORT`                                        | integer/string          | unset                                                 | Adds localhost and 127.0.0.1 CORS origins for the active frontend port.                                  |
| `GALLERY_CORS_ORIGINS`                                 | comma-separated URLs    | unset                                                 | Additional exact HTTP(S) CORS origins. Invalid URLs and origins containing credentials, paths, queries, or fragments are ignored. |
| `GALLERY_CORS_ALLOW_CREDENTIALS`                       | boolean-like flag       | `0`                                                   | Allows credentialed CORS requests when set to `1`, `true`, or `yes`; nginx Basic Auth normally uses same-origin requests. |
| `ENABLE_METRICS`                                       | boolean flag            | true unless `PRODUCTION=1`                            | Enables optional Prometheus instrumentation.                                                             |
| `ENABLE_PROFILER`                                      | boolean flag            | false                                                 | Enables pyinstrument middleware where configured.                                                        |
| `PROFILE_ENDPOINTS`                                    | comma-separated strings | `/api/browse,/api/metadata,/api/thumbnail,/api/preview` | Endpoints selected for profiling.                                                                        |
| `SCAN_PERF_LOGS`                                       | boolean-like flag       | true unless `PRODUCTION=1`                            | Enables legacy scan performance logging; false values are `0`, `false`, and `no`.                        |
| `GALLERY_THUMBNAIL_CACHE_DIR`                          | path                    | `backend/.cache/thumbnails`                           | Persistent derivative cache directory.                                                                   |
| `DERIVATIVE_WORKER_COUNT`                              | integer, clamped 1–8    | `3`                                                   | Target derivative worker count. A supervisor restores dead worker slots; claims use an internal lease and three-attempt limit. |
| `GALLERY_DERIVATIVE_JOB_LEASE_SECONDS`                 | integer, minimum 30     | `900`                                                 | Derivative job claim lease in seconds. A fenced heartbeat (one third of the lease) renews the lease during long renders so expired-claim recovery cannot duplicate an in-flight job. |
| `GALLERY_DERIVATIVE_LEASE_HEARTBEAT_SECONDS`           | float, minimum 5        | `300`                                                 | Lease heartbeat interval in seconds. Clamped to at most one third of `GALLERY_DERIVATIVE_JOB_LEASE_SECONDS`. |
| `GALLERY_DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS`          | integer, minimum 1      | `30`                                                  | One absolute deadline shared by all derivative worker, supervisor, and reconciler joins in `stop()`. A timeout leaves in-flight renders running and is recorded as an incomplete (not clean) shutdown. |
| `GALLERY_DERIVATIVE_QUOTA_BYTES`                       | integer, minimum 0      | `10737418240`                                         | Maximum derivative cache quota in bytes.                                                                 |
| `GALLERY_VIDEO_POSTER_MAX_CONCURRENCY`                 | integer, minimum 1      | `2`                                                   | Global maximum concurrent ffmpeg poster generations.                                                     |
| `GALLERY_VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS`           | float, minimum 0        | `5`                                                   | Maximum wait for a poster-generation slot before returning `503`.                                        |
| `GALLERY_VIDEO_POSTER_QUOTA_BYTES`                     | integer, minimum 0      | `1073741824`                                          | Poster cache quota; least-recently-used files are evicted without touching posters being generated or served. |
| `GALLERY_DERIVATIVE_RECONCILE_ENABLED`                 | boolean                 | `true`                                                | Enables automatic scan-completion, startup, and periodic configured-derivative reconciliation.          |
| `GALLERY_DERIVATIVE_RECONCILE_INTERVAL_SECONDS`        | integer, minimum 300   | `21600`                                               | Interval for warm-library desired-state catch-up.                                                         |
| `GALLERY_DERIVATIVE_RECONCILE_BATCH_SIZE`              | integer, 25–2000       | `250`                                                 | Assets classified in each short derivative reconciliation transaction.                                  |
| `GALLERY_DERIVATIVE_RECONCILE_YIELD_SECONDS`           | float, minimum 0       | `0.02`                                                | Cooperative pause between background reconciliation batches.                                             |
| `GALLERY_DERIVATIVE_FASTPATH_ENTRIES`                  | integer, minimum 0      | `4096`                                                | Capacity of the in-process LRU that lets a warm `/api/thumbnail` or `/api/preview` request skip the catalog lookups (validated by the source `stat()` on every hit). `0` disables the fast path. |
| `GALLERY_DERIVATIVE_FASTPATH_TTL_SECONDS`              | float, minimum 0        | `5`                                                   | Lifetime of a fast-path entry. Bounds how long a catalog-side deactivation (library removed, asset offline or deleted) can go unnoticed for an already-cached derivative; file changes are detected immediately. `0` disables the fast path. |
| `PATH_SAFETY_ROOT`                                     | path                    | `/`                                                   | Resolved path-safety boundary; does not create or imply a registered library.                            |
| `GALLERY_ROOT`                                         | path                    | unset                                                 | Deprecated fallback for `PATH_SAFETY_ROOT`; emits a warning when used.                                   |
| `GALLERY_OPEN_FOLDER`                                  | boolean (`"true"`)      | `false`                                               | Enables the OS "open folder" operation for directories within `PATH_SAFETY_ROOT`.                        |
| `GALLERY_METADATA_DB`                                  | path                    | `backend/.cache/gallery_metadata.db`                  | SQLite metadata/index database.                                                                          |
| `GALLERY_METADATA_SIDECAR_MAX_BYTES`                   | integer, minimum 0      | `1048576`                                             | Maximum same-stem `.txt` metadata sidecar size. Larger sidecars are not truncated: API reads return `413` and background jobs fail with a bounded error. |
| `GALLERY_INDEX_EXCLUDE_DIRS`                           | comma-separated names   | unset                                                 | Additional directory names excluded from indexing.                                                       |
| `GALLERY_INDEX_EXCLUDE_PATTERNS`                       | comma-separated globs   | unset                                                 | Additional path/name patterns excluded from indexing.                                                    |

### Default repository index exclusions

Gallery ships repository-specific default excluded path segments so mutable
build and test-output directories never enter a default library catalog:

- `frontend/coverage`
- `frontend/test-results`
- `frontend/playwright-report`

These are path *segments* (the exact `frontend/<segment>` sequence), not a global
ban on any directory named `coverage`, `test-results`, or `playwright-report`
elsewhere in the filesystem. A `coverage` directory outside `frontend/`, or
`frontend/<other>/coverage`, is still indexed. The segments are normalized for
POSIX and Windows-style (backslash) paths.

`GALLERY_INDEX_EXCLUDE_PATTERNS` appends additional glob patterns, and each
registered library may carry its own per-library exclusion patterns; both apply
alongside the defaults. Reconciliation marks already-cataloged paths that now
match an exclusion (default or per-library) as offline catalog rows without
deleting the source files on disk, so they no longer contribute to expected or
desired derivative coverage.
| `GALLERY_METADATA_INDEXER_ENABLED`                     | boolean flag            | true                                                  | Enables durable metadata job dispatch and worker processing.                                             |
| `GALLERY_METADATA_INDEXER_BATCH_SIZE`                  | integer, clamped 1–64   | `8`                                                   | Legacy metadata batch-size setting; the current DB-claim worker processes one claimed job per worker loop. |
| `GALLERY_METADATA_JOB_LEASE_SECONDS`                   | float, minimum 5        | `300`                                                 | Metadata job claim lease in seconds. A heartbeat (one third of the lease) renews it while a job extracts; an expired or ownerless `running` job is requeued by the supervisor, the integrity checker, and metadata dispatch. |
| `GALLERY_METADATA_SUPERVISOR_INTERVAL_SECONDS`         | float, minimum 1        | `30`                                                  | Interval of the metadata supervisor thread that requeues expired or ownerless `running` metadata jobs and restores dead metadata worker threads. Stopped with the metadata worker during shutdown. |
| `GALLERY_METADATA_RETRY_BASE_SECONDS`                  | float, minimum 0        | `2`                                                   | Base backoff before retrying a metadata job after a transient error (SQLite locked/busy, `EAGAIN`/`EBUSY`/`EINTR`): base x 2^(attempts-1), capped at 60 s, until three attempts. Parse errors never retry. |
| `GALLERY_METADATA_CLAIM_BATCH_SIZE`                    | integer, clamped 1–16   | `1`                                                   | Jobs one metadata worker claims per claim transaction. Above 1 the extra claims wait in that worker's buffer: the running job's heartbeat renews their leases too and a stopping worker gives them back without consuming an attempt. Claims keep queue order (`priority`, `queued_at`, `path`). |
| `GALLERY_SEARCH_WINDOW_CACHE_ENTRIES`                  | integer, minimum 0      | `128`                                                 | Entries of the in-process ranked-window cache that serves keyset search pages 2 and later (see Search planning in `ARCHITECTURE.md`). One entry holds the candidate rows of one bounded source of one search request. `0` turns the cache off: every page then ranks its sources, as before BL-15. |
| `GALLERY_SEARCH_WINDOW_CACHE_MB`                       | integer, minimum 0      | `32`                                                  | Upper bound, in MiB of estimated row memory, of the ranked-window cache; least recently used entries go first. `0` turns the cache off. |
| `GALLERY_DB_WRITER_BATCH_MAX`                          | integer, minimum 1      | `50`                                                  | Maximum ops the writer applies in one `BEGIN IMMEDIATE` transaction. The database writer is the only write path while the app runs and has no on/off switch: `GALLERY_DB_WRITER_ENABLED` and the `_DB_LOCK` direct-transaction fallbacks were removed in Phase 3, and the variable is ignored. Op sizes are fixed (reconcile ops of 25 assets, scan ops of 50 rows, integrity repair chunks of 250 rows) and need no setting. |
| `GALLERY_DB_WRITER_BATCH_MS`                           | float, minimum 1        | `100`                                                 | Time budget of one writer transaction: once a batch has been open this long it takes no further ops. The writer never waits for more ops when its queue is empty, so this bounds write-lock hold time and adds no latency. |
| `GALLERY_DB_WRITER_YIELD_MS`                           | float, minimum 0        | `25`                                                  | After a stretch of at least `GALLERY_DB_WRITER_BATCH_MS` of back-to-back batches the writer sleeps this long with the write lock released, so a saturated writer never holds SQLite's write lock continuously (a writer outside it, such as an external connection or a script, would otherwise starve behind SQLite's sleeping busy handler). Sparse traffic is never delayed; `0` disables the pause. |
| `GALLERY_DB_WRITER_QUEUE_MAX`                          | integer, minimum 1      | `1000`                                                | Capacity of each writer lane (`priority`, `normal`). A full lane blocks `submit` for `GALLERY_DB_WRITER_SUBMIT_TIMEOUT_SECONDS` and then raises (backpressure). |
| `GALLERY_DB_WRITER_SUBMIT_TIMEOUT_SECONDS`             | float, minimum 0        | `30`                                                  | How long `submit` waits for room in a full lane before raising `DatabaseWriterBackpressure`. |
| `GALLERY_DB_WRITER_RESULT_TIMEOUT_SECONDS`             | float, minimum 1        | `120`                                                 | How long a caller waits for its op's result before raising `DatabaseWriterTimeout`. The op may still run later; every metadata job write is fenced by its claim token. |
| `GALLERY_DB_WRITER_SHUTDOWN_TIMEOUT_SECONDS`           | float, minimum 0        | `10`                                                  | Deadline for the writer to drain queued ops when the app stops; ops still queued after it fail with `DatabaseWriterClosed`. |
| `GALLERY_METADATA_INDEXER_WORKER_SLEEP_SECONDS`        | float, minimum 0        | `0.01`                                                | Worker sleep interval.                                                                                   |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_SECONDS`          | float, minimum 0        | `0.05`                                                | Parsed compatibility setting from the removed scan-yield path. Falls back to `METADATA_INDEXER_SCAN_YIELD_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_SECONDS`                  | float                   | `0.05`                                                | Legacy fallback for the prefixed scan-yield variable.                                                    |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`      | float, minimum 0        | `1.0`                                                 | Parsed compatibility setting from the removed scan-yield path. Falls back to `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`              | float                   | `1.0`                                                 | Legacy fallback for the prefixed scan-yield maximum.                                                     |
| `GALLERY_INTEGRITY_CHECK_ENABLED`                      | boolean flag            | true                                                  | Starts the periodic cross-table integrity checker during backend startup.                                |
| `GALLERY_INTEGRITY_CHECK_INTERVAL_SECONDS`             | integer, minimum 60     | `3600`                                                | Integrity checker interval in seconds.                                                                  |
| `ENABLE_WARM_INDEXED_LISTING`                          | boolean flag            | false                                                 | Enables legacy warm SQLite listing helpers where still used by tests/diagnostics.                        |
| `GALLERY_CATALOG_WORKERS`                              | integer, clamped 1–8    | `1`                                                   | Number of concurrent catalog worker threads.                                                             |
| `GALLERY_CATALOG_SERVICE_ENABLED`                      | boolean flag            | true                                                  | Starts the catalog worker service during backend startup.                                                |
| `GALLERY_CATALOG_WATCHER_ENABLED`                      | boolean flag            | true                                                  | Enables filesystem watcher for registered library import paths.                                          |
| `ENABLE_FILE_WATCHER`                                  | boolean flag            | true                                                  | Legacy fallback for `GALLERY_CATALOG_WATCHER_ENABLED`.                                                   |
| `WATCHER_ROOTS`                                        | comma-separated paths   | unset                                                 | Optional watcher root filter; when unset, enabled registered library import paths are watched.            |
| `GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS`             | float, minimum 0.1      | `2.0`                                                 | Filesystem event debounce interval for catalog scan triggers; clamped above zero to prevent busy-spins.  |
| `WATCHER_DEBOUNCE_SECONDS`                             | float                   | `2.0`                                                 | Legacy fallback for `GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS`.                                          |
| `WATCHER_MAX_EVENTS_PER_TICK`                          | integer, minimum 1      | `500`                                                 | Maximum debounced folders removed and processed per watcher tick; overflow remains pending.              |
| `GALLERY_CATALOG_RECONCILE_ENABLED`                    | boolean flag            | true                                                  | Enables scheduled catalog reconciliation for missed events.                                              |
| `ENABLE_SCHEDULED_REFRESH`                             | boolean flag            | true                                                  | Legacy fallback for `GALLERY_CATALOG_RECONCILE_ENABLED`.                                                 |
| `GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS`           | integer, minimum 60     | `21600`                                               | Catalog reconciliation interval (default 6 hours).                                                       |
| `SCHEDULED_REFRESH_INTERVAL_SECONDS`                   | integer                 | `21600`                                               | Legacy fallback for `GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS`.                                        |
| `SCHEDULED_REFRESH_ROOTS`                              | comma-separated paths   | unset                                                 | Optional reconciliation filter; when unset, every registered library is eligible.                         |
| `SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK`               | integer, minimum 1      | `20`                                                  | Maximum registered libraries queued per reconciliation tick; durable least-recent scheduling keeps limited ticks fair. |
| `SCHEDULED_REFRESH_ALLOW_ALL_INDEXED`                  | boolean flag            | false                                                 | Parsed for compatibility; current reconciliation queues registered libraries directly.                    |
| `GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED`              | boolean flag            | true                                                  | Enables low-priority startup scan for every registered library.                                          |
| `GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS`           | integer, minimum 0      | `600`                                                 | Max queue wait before a queued catalog job is priority-promoted.                                         |
| `GALLERY_CATALOG_JOB_LEASE_SECONDS`                    | integer, minimum 30     | `900`                                                 | Durable catalog-worker claim lease. Dead-owner or expired claims are recovered by startup/supervisor policy. |
| `GALLERY_CATALOG_LEASE_HEARTBEAT_SECONDS`              | float, minimum 5        | `300`                                                 | Catalog claim heartbeat interval, clamped to at most one third of the catalog job lease.                 |
| `GALLERY_CATALOG_WRITE_BATCH_SIZE`                     | integer, minimum 1      | `500`                                                 | Catalog write batch size for discovery/staging.                                                          |
| `GALLERY_CATALOG_SHUTDOWN_TIMEOUT_SECONDS`             | float, minimum 0        | `30`                                                  | Absolute catalog-service stop deadline shared across worker and supervisor joins.                        |
| `GALLERY_SEARCH_INDEXER_ENABLED`                       | boolean flag            | true                                                  | Starts the single-writer durable derived-search-index worker during backend startup.                     |
| `GALLERY_SEARCH_INDEX_BATCH_SIZE`                      | integer, clamped 1–200  | `200`                                                 | Maximum asset-ID keyset batch read by one derived-index worker iteration.                                |
| `GALLERY_SEARCH_INDEX_JOB_LEASE_SECONDS`               | integer, minimum 30     | `300`                                                 | Fenced lease duration for one claimed derived search-index job.                                         |
| `GALLERY_SEARCH_INDEX_POLL_SECONDS`                    | float, minimum 0.1      | `1.0`                                                 | Idle poll interval for the derived search-index writer; enqueue/cancel also wake it immediately.         |
| `GALLERY_RELATED_VISUAL_ENABLED`                       | boolean flag            | true                                                  | Enables Pillow-only visual fingerprint indexing and the visual Related Assets profile; metadata and lexical search remain available when false. |
| `GALLERY_SEARCH_WORKFLOW_RAW_ENABLED`                  | boolean flag            | false                                                 | Enables the separately controlled raw-workflow index and API; normal search remains available when false. |
| `GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES`       | integer, minimum 1      | `1048576`                                             | Maximum compact canonical JSON bytes for one raw workflow; larger documents are skipped, never truncated. |
| `GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES`       | integer, minimum 1      | `536870912`                                           | Global canonical raw-workflow document budget; overflow is skipped and reported as degraded index state. |

Invalid numeric strings raise during configuration import; the code does not provide a
fallback for malformed numbers.

## Frontend/build environment variables

| Variable                          | Type               | Default                                                                        | Behavior                                                              |
| --------------------------------- | ------------------ | ------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `VITE_API_URL`                    | URL/string         | empty in `frontend/.env`; dev proxy target defaults to `http://localhost:4701` | Browser API base URL and Vite `/api` proxy target.                    |
| `VITE_PORT`                       | number             | `4702`                                                                         | Vite development-server port; `strictPort` prevents automatic fallback. |
| `VITE_COVERAGE`                   | boolean (`"true"`) | false                                                                          | Enables Istanbul instrumentation and coverage-specific test behavior. |
| `VITE_MOBILE_NO_HMR`              | boolean (`"1"`)    | false                                                                          | Disables Vite HMR for the `dev:mobile` workflow.                      |
| `VITE_EXPOSE_LIGHTBOX_TEST_HOOKS` | boolean (`"1"`)    | false                                                                          | Exposes lightbox test hooks outside Vite test mode.                   |
| `VITE_DEVTOOLS`                   | boolean (`"true"`) | false                                                                          | Shows TanStack Query Devtools (dev or this build). Without it, Devtools stay hidden even in Vite dev mode unless opted in with `?devtools=1` (see `docs/testing/DEBUG_TOOLS.md`). |

Vite built-ins such as `DEV` and `MODE` are read by the frontend but are supplied by
Vite rather than configured by this repository.
