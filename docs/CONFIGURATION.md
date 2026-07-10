# Configuration

Status: Maintained

Last verified against `backend/config.py`, `frontend/vite.config.ts`, frontend
environment reads, and the server nginx site config: 2026-07-08.

Boolean flags parsed by `_env_flag()` treat `0`, `false`, `no`, and `off`
case-insensitively as false; any other provided value is true. Flags documented as
`== "1"` or `== "true"` use the stricter comparison shown.

## Server runtime topology

The VPS public entrypoint is nginx on `150.230.56.153`. Port 80 redirects to
HTTPS. In production, nginx serves the built SPA from `frontend/dist/` and
proxies only API traffic to FastAPI.

| Public path | nginx behavior | Service | Standard purpose |
| ----------- | -------------- | ------- | ---------------- |
| `/api` | Proxy to `http://127.0.0.1:4180` | Backend | FastAPI/uvicorn API server for `backend.main:app`. |
| `/` | Serve `frontend/dist/` with SPA fallback | Frontend | Production Vue build. |

For development-only Vite access, run the frontend on `127.0.0.1:4173` or the
default Vite port and let the Vite dev proxy forward `/api` to the backend.

Standard backend command from the repo root:

```bash
cd /home/ubuntu/gallery-repo
PORT=4180 FRONTEND_PORT=4173 backend/.venv_linux/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 4180
```

Development frontend command from `frontend/`:

```bash
cd /home/ubuntu/gallery-repo/frontend
VITE_PORT=4173 corepack pnpm exec vite --host 127.0.0.1 --port 4173
```

Do not set `VITE_API_URL` for the public VPS nginx path unless deliberately
bypassing same-origin routing. With `VITE_API_URL` unset, browser API calls use
same-origin `/api`, and nginx forwards them to `127.0.0.1:4180`. The Vite dev
proxy also defaults `/api` to `http://localhost:4180` for direct local access to
the frontend dev server.

Useful health checks:

```bash
curl http://127.0.0.1:4180/api/health
curl https://150.230.56.153/api/health
curl -I https://150.230.56.153/
```

## Backend environment variables

| Variable                                               | Type                    | Default                                               | Behavior                                                                                                 |
| ------------------------------------------------------ | ----------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `PRODUCTION`                                           | boolean (`"1"`)         | `0`                                                   | Enables production mode; also changes the default for metrics.                                           |
| `PORT`                                                 | integer                 | `8000` in `backend/main.py` fallback                  | Uvicorn port when running `python3 -m backend.main` directly.                                            |
| `FRONTEND_ORIGIN`                                      | URL/string              | unset                                                 | Extra CORS origin; trailing slash is stripped.                                                           |
| `FRONTEND_PORT`                                        | integer/string          | unset                                                 | Adds localhost and 127.0.0.1 CORS origins for the active frontend port.                                  |
| `ENABLE_METRICS`                                       | boolean flag            | true unless `PRODUCTION=1`                            | Enables optional Prometheus instrumentation.                                                             |
| `ENABLE_PROFILER`                                      | boolean flag            | false                                                 | Enables pyinstrument middleware where configured.                                                        |
| `PROFILE_ENDPOINTS`                                    | comma-separated strings | `/api/browse,/api/metadata,/api/thumbnail,/api/preview` | Endpoints selected for profiling.                                                                        |
| `SCAN_PERF_LOGS`                                       | boolean-like flag       | true unless `PRODUCTION=1`                            | Enables legacy scan performance logging; false values are `0`, `false`, and `no`.                        |
| `GALLERY_THUMBNAIL_CACHE_DIR`                          | path                    | `backend/.cache/thumbnails`                           | Persistent derivative cache directory.                                                                   |
| `DERIVATIVE_WORKER_COUNT`                              | integer, clamped 1–8    | `3`                                                   | Target derivative worker count. A supervisor restores dead worker slots; claims use an internal 15-minute lease and three-attempt limit. |
| `GALLERY_DERIVATIVE_QUOTA_BYTES`                       | integer, minimum 0      | `10737418240`                                         | Maximum derivative cache quota in bytes.                                                                 |
| `GALLERY_DERIVATIVE_RECONCILE_ENABLED`                 | boolean                 | `true`                                                | Enables automatic scan-completion, startup, and periodic configured-derivative reconciliation.          |
| `GALLERY_DERIVATIVE_RECONCILE_INTERVAL_SECONDS`        | integer, minimum 300   | `21600`                                               | Interval for warm-library desired-state catch-up.                                                         |
| `GALLERY_DERIVATIVE_RECONCILE_BATCH_SIZE`              | integer, 25–2000       | `250`                                                 | Assets classified in each short derivative reconciliation transaction.                                  |
| `GALLERY_DERIVATIVE_RECONCILE_YIELD_SECONDS`           | float, minimum 0       | `0.02`                                                | Cooperative pause between background reconciliation batches.                                             |
| `PATH_SAFETY_ROOT`                                     | path                    | `/`                                                   | Resolved path-safety boundary; does not create or imply a registered library.                            |
| `GALLERY_ROOT`                                         | path                    | unset                                                 | Deprecated fallback for `PATH_SAFETY_ROOT`; emits a warning when used.                                   |
| `GALLERY_OPEN_FOLDER`                                  | boolean (`"true"`)      | `false`                                               | Enables the OS "open folder" operation.                                                                  |
| `GALLERY_METADATA_DB`                                  | path                    | `backend/.cache/gallery_metadata.db`                  | SQLite metadata/index database.                                                                          |
| `GALLERY_INDEX_EXCLUDE_DIRS`                           | comma-separated names   | unset                                                 | Additional directory names excluded from indexing.                                                       |
| `GALLERY_INDEX_EXCLUDE_PATTERNS`                       | comma-separated globs   | unset                                                 | Additional path/name patterns excluded from indexing.                                                    |
| `GALLERY_METADATA_INDEXER_ENABLED`                     | boolean flag            | true                                                  | Enables durable metadata job dispatch and worker processing.                                             |
| `GALLERY_METADATA_INDEXER_BATCH_SIZE`                  | integer, clamped 1–64   | `8`                                                   | Legacy metadata batch-size setting; the current DB-claim worker processes one claimed job per worker loop. |
| `GALLERY_METADATA_INDEXER_WORKER_SLEEP_SECONDS`        | float, minimum 0        | `0.01`                                                | Worker sleep interval.                                                                                   |
| `GALLERY_METADATA_INDEXER_STAGE_BATCH_SIZE`            | integer, clamped 1–1000 | `100`                                                 | Parsed compatibility setting from the removed staged-path worker. Falls back to `METADATA_INDEXER_STAGE_BATCH_SIZE`. |
| `METADATA_INDEXER_STAGE_BATCH_SIZE`                    | integer                 | `100`                                                 | Legacy fallback for the prefixed stage batch variable.                                                   |
| `GALLERY_METADATA_INDEXER_STAGE_SLEEP_SECONDS`         | float, minimum 0        | `0.2`                                                 | Parsed compatibility setting from the removed staged-path worker. Falls back to `METADATA_INDEXER_STAGE_SLEEP_SECONDS`. |
| `METADATA_INDEXER_STAGE_SLEEP_SECONDS`                 | float                   | `0.2`                                                 | Legacy fallback for the prefixed stage sleep variable.                                                   |
| `GALLERY_METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS`      | float, minimum 0        | `5.0`                                                 | Parsed compatibility setting from the removed staged-path worker. Falls back to `METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS`. |
| `METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS`              | float                   | `5.0`                                                 | Legacy fallback for the prefixed stage max-wait variable.                                                |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_SECONDS`          | float, minimum 0        | `0.05`                                                | Parsed compatibility setting from the removed scan-yield path. Falls back to `METADATA_INDEXER_SCAN_YIELD_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_SECONDS`                  | float                   | `0.05`                                                | Legacy fallback for the prefixed scan-yield variable.                                                    |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`      | float, minimum 0        | `1.0`                                                 | Parsed compatibility setting from the removed scan-yield path. Falls back to `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`              | float                   | `1.0`                                                 | Legacy fallback for the prefixed scan-yield maximum.                                                     |
| `GALLERY_METADATA_INDEXER_SQLITE_BUSY_RETRIES`         | integer, minimum 0      | `3`                                                   | Parsed compatibility setting from the removed staged writer. Falls back to `METADATA_INDEXER_SQLITE_BUSY_RETRIES`. |
| `METADATA_INDEXER_SQLITE_BUSY_RETRIES`                 | integer                 | `3`                                                   | Legacy fallback for the prefixed busy-retry variable.                                                    |
| `GALLERY_METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS` | float, minimum 0        | `0.1`                                                 | Parsed compatibility setting from the removed staged writer. Falls back to `METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS`. |
| `METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS`         | float                   | `0.1`                                                 | Legacy fallback for the prefixed busy-backoff variable.                                                  |
| `GALLERY_INTEGRITY_CHECK_ENABLED`                      | boolean flag            | true                                                  | Starts the periodic cross-table integrity checker during backend startup.                                |
| `GALLERY_INTEGRITY_CHECK_INTERVAL_SECONDS`             | integer, minimum 60     | `3600`                                                | Integrity checker interval in seconds.                                                                  |
| `ENABLE_WARM_INDEXED_LISTING`                          | boolean flag            | false                                                 | Enables legacy warm SQLite listing helpers where still used by tests/diagnostics.                        |
| `GALLERY_CATALOG_WORKERS`                              | integer, clamped 1–8    | `1`                                                   | Number of concurrent catalog worker threads.                                                             |
| `GALLERY_CATALOG_SERVICE_ENABLED`                      | boolean flag            | true                                                  | Starts the catalog worker service during backend startup.                                                |
| `GALLERY_CATALOG_WATCHER_ENABLED`                      | boolean flag            | true                                                  | Enables filesystem watcher for registered library import paths.                                          |
| `ENABLE_FILE_WATCHER`                                  | boolean flag            | true                                                  | Legacy fallback for `GALLERY_CATALOG_WATCHER_ENABLED`.                                                   |
| `WATCHER_ROOTS`                                        | comma-separated paths   | unset                                                 | Optional watcher root filter; when unset, enabled registered library import paths are watched.            |
| `GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS`             | float, minimum 0        | `2.0`                                                 | Filesystem event debounce interval for catalog scan triggers.                                            |
| `WATCHER_DEBOUNCE_SECONDS`                             | float                   | `2.0`                                                 | Legacy fallback for `GALLERY_CATALOG_WATCHER_DEBOUNCE_SECONDS`.                                          |
| `WATCHER_MAX_EVENTS_PER_TICK`                          | integer, minimum 1      | `500`                                                 | Maximum filesystem events processed per watcher tick.                                                    |
| `GALLERY_CATALOG_RECONCILE_ENABLED`                    | boolean flag            | true                                                  | Enables scheduled catalog reconciliation for missed events.                                              |
| `ENABLE_SCHEDULED_REFRESH`                             | boolean flag            | true                                                  | Legacy fallback for `GALLERY_CATALOG_RECONCILE_ENABLED`.                                                 |
| `GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS`           | integer, minimum 60     | `21600`                                               | Catalog reconciliation interval (default 6 hours).                                                       |
| `SCHEDULED_REFRESH_INTERVAL_SECONDS`                   | integer                 | `21600`                                               | Legacy fallback for `GALLERY_CATALOG_RECONCILE_INTERVAL_SECONDS`.                                        |
| `SCHEDULED_REFRESH_ROOTS`                              | comma-separated paths   | unset                                                 | Optional reconciliation filter; when unset, every registered library is eligible.                         |
| `SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK`               | integer, minimum 1      | `20`                                                  | Maximum registered libraries queued per reconciliation tick.                                             |
| `SCHEDULED_REFRESH_ALLOW_ALL_INDEXED`                  | boolean flag            | false                                                 | Parsed for compatibility; current reconciliation queues registered libraries directly.                    |
| `GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED`              | boolean flag            | true                                                  | Enables low-priority startup scan for every registered library.                                          |
| `GALLERY_CATALOG_JOB_MAX_QUEUE_WAIT_SECONDS`           | integer, minimum 0      | `600`                                                 | Max queue wait before a queued catalog job is priority-promoted.                                         |
| `GALLERY_CATALOG_WRITE_BATCH_SIZE`                     | integer, minimum 1      | `500`                                                 | Catalog write batch size for discovery/staging.                                                          |

Invalid numeric strings raise during configuration import; the code does not provide a
fallback for malformed numbers.

## Frontend/build environment variables

| Variable                          | Type               | Default                                                                        | Behavior                                                              |
| --------------------------------- | ------------------ | ------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `VITE_API_URL`                    | URL/string         | empty in `frontend/.env`; dev proxy target defaults to `http://localhost:4180` | Browser API base URL and Vite `/api` proxy target.                    |
| `VITE_PORT`                       | number             | `5173`                                                                         | Vite development-server port.                                         |
| `VITE_COVERAGE`                   | boolean (`"true"`) | false                                                                          | Enables Istanbul instrumentation and coverage-specific test behavior. |
| `VITE_MOBILE_NO_HMR`              | boolean (`"1"`)    | false                                                                          | Disables Vite HMR for the `dev:mobile` workflow.                      |
| `VITE_EXPOSE_LIGHTBOX_TEST_HOOKS` | boolean (`"1"`)    | false                                                                          | Exposes lightbox test hooks outside Vite test mode.                   |
| `VITE_DEVTOOLS`                   | boolean (`"true"`) | false                                                                          | Shows TanStack Query Devtools outside normal Vite dev mode.           |

Vite built-ins such as `DEV` and `MODE` are read by the frontend but are supplied by
Vite rather than configured by this repository.
