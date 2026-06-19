# Configuration

Last verified against `backend/config.py`, `frontend/.env`, `frontend/vite.config.ts`,
and frontend environment reads: 2026-06-18.

Boolean flags parsed by `_env_flag()` treat `0`, `false`, `no`, and `off`
case-insensitively as false; any other provided value is true. Flags documented as
`== "1"` or `== "true"` use the stricter comparison shown.

## Backend environment variables

| Variable | Type | Default | Behavior |
|---|---|---|---|
| `PRODUCTION` | boolean (`"1"`) | `0` | Enables production mode; also changes defaults for metrics and scan perf logs. |
| `ENABLE_METRICS` | boolean flag | true unless `PRODUCTION=1` | Enables optional Prometheus instrumentation. |
| `ENABLE_PROFILER` | boolean flag | false | Enables pyinstrument middleware where configured. |
| `PROFILE_ENDPOINTS` | comma-separated strings | `/api/scan,/api/metadata,/api/thumbnail,/api/preview` | Endpoints selected for profiling. |
| `GALLERY_THUMBNAIL_CACHE_DIR` | path | `backend/.cache/thumbnails` | Persistent derivative cache directory. |
| `SCAN_PERF_LOGS` | boolean-like | `1` unless `PRODUCTION=1`, then `0` | Values `0`, `false`, and `no` disable scan performance logs. |
| `PATH_SAFETY_ROOT` | path | `/` | Resolved root boundary for gallery paths. |
| `GALLERY_DB_REQUIRED` | boolean flag | false | Requires `/api/scan` paths to belong to a registered library and disables filesystem listing fallback. |
| `GALLERY_OPEN_FOLDER` | boolean (`"true"`) | `false` | Enables the OS “open folder” operation. |
| `GALLERY_METADATA_DB` | path | `backend/.cache/gallery_metadata.db` | SQLite metadata/index database. |
| `GALLERY_METADATA_INDEXER_ENABLED` | boolean flag | true | Enables metadata path staging and worker processing. |
| `GALLERY_METADATA_INDEXER_BATCH_SIZE` | integer, clamped 1–64 | `8` | Metadata worker batch size. |
| `GALLERY_METADATA_INDEXER_WORKER_SLEEP_SECONDS` | float, minimum 0 | `0.01` | Worker sleep interval. |
| `GALLERY_METADATA_INDEXER_STAGE_BATCH_SIZE` | integer, clamped 1–1000 | `100` | Staged-path batch size. Falls back to `METADATA_INDEXER_STAGE_BATCH_SIZE`. |
| `METADATA_INDEXER_STAGE_BATCH_SIZE` | integer | `100` | Legacy fallback for the prefixed stage batch variable. |
| `GALLERY_METADATA_INDEXER_STAGE_SLEEP_SECONDS` | float, minimum 0 | `0.2` | Staging idle/yield interval. Falls back to `METADATA_INDEXER_STAGE_SLEEP_SECONDS`. |
| `METADATA_INDEXER_STAGE_SLEEP_SECONDS` | float | `0.2` | Legacy fallback for the prefixed stage sleep variable. |
| `GALLERY_METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS` | float, minimum 0 | `5.0` | Maximum staging wait before a forced flush. Falls back to `METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS`. |
| `METADATA_INDEXER_STAGE_MAX_WAIT_SECONDS` | float | `5.0` | Legacy fallback for the prefixed stage max-wait variable. |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_SECONDS` | float, minimum 0 | `0.05` | SQLite retry/yield delay while scan work is active. Falls back to `METADATA_INDEXER_SCAN_YIELD_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_SECONDS` | float | `0.05` | Legacy fallback for the prefixed scan-yield variable. |
| `GALLERY_METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS` | float, minimum 0 | `1.0` | Maximum cumulative scan-yield duration. Falls back to `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS`. |
| `METADATA_INDEXER_SCAN_YIELD_MAX_SECONDS` | float | `1.0` | Legacy fallback for the prefixed scan-yield maximum. |
| `GALLERY_METADATA_INDEXER_SQLITE_BUSY_RETRIES` | integer, minimum 0 | `3` | SQLite busy retry count. Falls back to `METADATA_INDEXER_SQLITE_BUSY_RETRIES`. |
| `METADATA_INDEXER_SQLITE_BUSY_RETRIES` | integer | `3` | Legacy fallback for the prefixed busy-retry variable. |
| `GALLERY_METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS` | float, minimum 0 | `0.1` | SQLite busy retry backoff. Falls back to `METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS`. |
| `METADATA_INDEXER_SQLITE_BUSY_BACKOFF_SECONDS` | float | `0.1` | Legacy fallback for the prefixed busy-backoff variable. |
| `ENABLE_WARM_INDEXED_LISTING` | boolean flag | false | Allows `/api/scan` to use a complete, fresh SQLite folder listing. |
| `ENABLE_SCHEDULED_REFRESH` | boolean flag | false | Starts the scheduled folder-index refresh thread. |
| `SCHEDULED_REFRESH_INTERVAL_SECONDS` | integer, minimum 60 | `300` | Refresh interval. |
| `SCHEDULED_REFRESH_ROOTS` | comma-separated paths | empty | Restricts scheduled refresh to configured roots. |
| `SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK` | integer, minimum 1 | `20` | Maximum refreshed folders per tick. |
| `SCHEDULED_REFRESH_ALLOW_ALL_INDEXED` | boolean flag | false | Allows refresh of all indexed folders when no roots are configured. |
| `ENABLE_FILE_WATCHER` | boolean flag | true | Starts the watchdog observer for registered, watch-enabled libraries. |
| `WATCHER_ROOTS` | comma-separated paths | empty | Optionally filters the registered library roots watched recursively. |
| `WATCHER_DEBOUNCE_SECONDS` | float, minimum 0 | `2.0` | Filesystem event debounce interval. |
| `WATCHER_MAX_EVENTS_PER_TICK` | integer, minimum 1 | `500` | Maximum folder/image events processed per watcher tick. |

Invalid numeric strings raise during configuration import; the code does not provide a
fallback for malformed numbers.

## Frontend/build environment variables

| Variable | Type | Default | Behavior |
|---|---|---|---|
| `VITE_API_URL` | URL/string | empty in `frontend/.env`; dev proxy target defaults to `http://localhost:4180` | Browser API base URL and Vite `/api` proxy target. |
| `VITE_PORT` | number | `5173` | Vite development-server port. |
| `VITE_COVERAGE` | boolean (`"true"`) | false | Enables Istanbul instrumentation and coverage-specific test behavior. |
| `VITE_MOBILE_NO_HMR` | boolean (`"1"`) | false | Disables Vite HMR for the `dev:mobile` workflow. |
| `VITE_EXPOSE_LIGHTBOX_TEST_HOOKS` | boolean (`"1"`) | false | Exposes lightbox test hooks outside Vite test mode. |

Vite built-ins such as `DEV` and `MODE` are read by the frontend but are supplied by
Vite rather than configured by this repository.
