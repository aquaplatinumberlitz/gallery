# Backend Audit Findings Remediation Plan

Status: Completed

Last reviewed: 2026-07-13

## Summary

Remediate every confirmed backend audit finding through five independently
reviewable PRs. Preserve the single-process SQLite architecture and current
frontend behavior, except where insecure legacy absolute-path access must be
removed.

Locked decisions:

- Production authentication: nginx Basic Auth plus a secret header injected by
  nginx and required by FastAPI.
- Media access: catalog-only; unregistered, offline, deleted, excluded, or
  wrong-type paths cannot be served.
- Delivery: phased PRs with full test gates after every phase.

## Public API And Configuration Changes

- `PRODUCTION=1` requires `GALLERY_TRUSTED_PROXY_SECRET` of at least 32
  characters; startup fails closed otherwise.
- nginx protects the SPA and `/api` with Basic Auth and injects
  `X-Gallery-Proxy-Secret`. Secrets and `.htpasswd` files remain outside the
  repository.
- Direct backend requests with a missing or invalid proxy secret return `403`.
- File routes keep their current URLs but return `404` for paths not owned by an
  active registered-library asset or folder.
- Allowed HTTP derivative sizes become:
  - thumbnail: `128`, `512`
  - preview: `1440`
  - unsupported values return `422`; the deprecated `max_size` alias remains but
    must resolve to an allowed value.
- Oversized metadata sidecars return `413`; background jobs record a bounded
  failure.
- Capacity refusal returns `507`, poster saturation returns `503`, and
  unexpected internal failures return generic `500` responses without
  filesystem or SQLite details.
- Catalog status metadata counts images only. Runtime status gains additive
  catalog-supervisor health fields.
- New documented settings:
  - `GALLERY_TRUSTED_PROXY_SECRET`
  - `GALLERY_METADATA_SIDECAR_MAX_BYTES=1048576`
  - `GALLERY_VIDEO_POSTER_MAX_CONCURRENCY=2`
  - `GALLERY_VIDEO_POSTER_QUEUE_TIMEOUT_SECONDS=5`
  - `GALLERY_VIDEO_POSTER_QUOTA_BYTES=1073741824`
  - existing undocumented CORS and catalog-shutdown settings

## Phase 1 - Public Security And Filesystem Boundary

- Add a shared FastAPI dependency to all API routers that validates the trusted
  proxy header using constant-time comparison. Development remains
  unauthenticated only when `PRODUCTION=0` and no proxy secret is configured.
- Update both nginx templates:
  - enable server-wide Basic Auth;
  - include a root-owned secret snippet that sets the proxy header;
  - set `client_max_body_size 1m`;
  - retain SSE buffering and timeouts.
- Replace the current safety-root-only helper with catalog authorization:
  - resolve and validate `PATH_SAFETY_ROOT`;
  - require an active catalog asset of the expected type for images, videos,
    metadata, and derivatives;
  - require registered, non-excluded library ownership for folders, facets,
    current-scope search, and open-folder;
  - return `404` for catalog-invisible paths and `403` only for safety-root
    escapes.
- Stop following nested file and directory symlinks during discovery so scans
  cannot escape a registered import root.
- Catch `ValueError`, embedded NUL, and resolution failures as validation errors
  rather than unhandled `500`s.
- Bound library inputs to 32 import paths, 128 exclusion patterns, 4,096
  characters per path, and 512 characters per pattern. Replace pairwise
  same-library overlap validation with sorted adjacent containment checks.

## Phase 2 - Metadata And Catalog Convergence

- Make sidecar identity part of `_current_metadata_is_complete()`. Modification,
  replacement, or deletion of a same-stem `.txt` must queue fresh extraction.
- When completion detects a sidecar mismatch, return a requeue or stale outcome
  to the caller rather than incrementing `skipped`. Startup recovery must demote
  stale sidecar jobs to `queued`.
- Check sidecar size before reading. Do not truncate: raise a typed error, map
  API reads to `413`, and persist a bounded background-job failure.
- Restrict every metadata-status query to active image assets. Video-only
  libraries must report metadata complete with zero metadata assets.
- During a whole-library or scoped scan, reconcile each offline import root with
  an empty discovered set so its existing assets become offline tombstones
  without deleting source files.
- Protect import-path updates and unregister operations with the
  producer/maintenance gate. Recheck active metadata, derivative, and catalog
  work after acquiring the gate; return `409 maintenance_busy` instead of
  allowing in-flight workers to recreate deleted metadata or cache rows.
- Ensure metadata persistence rolls back if no active owning asset remains.

## Phase 3 - Watcher, Refresh, And Catalog Service Ownership

- Change watcher draining to accept a maximum count and remove only the selected
  folders. Order deterministically by debounce timestamp and path; overflow
  stays pending for the next tick.
- Remove the unused `affected_image_paths` collection and its tests because the
  maintained architecture queues folder-scoped catalog work only.
- Clamp watcher debounce to at least `0.1` seconds to prevent `Event.wait(0)`
  busy-spins.
- Make scheduled refresh durable and fair by ordering eligible libraries by
  their most recent scheduled-job timestamp, with never-scheduled libraries
  first and library ID as the tie-breaker. Repeated ticks must eventually visit
  every library.
- Remove worker recovery and spawning from GET status builders. Catalog workers
  gain an owned supervisor loop that restores configured worker count and
  recovers orphaned runtime jobs independently of monitoring requests.
- Runtime and status endpoints become observational only and execute blocking
  SQLite work in the threadpool or as synchronous FastAPI routes.

## Phase 4 - Derivative, Poster, And Lease Correctness

- Require every HTTP derivative request to resolve an active catalog asset and
  pass through the durable scheduler; delete the direct unregistered-path render
  branch.
- Reserve quota before creating every runnable derivative job:
  - automatic work becomes `deferred_capacity`;
  - interactive work returns `507`;
  - waiter logic handles `evicted` immediately and never converts capacity
    failure into a 10-second `503` timeout.
- Restrict public derivative variants to the approved sizes. Integrity
  reconciliation terminalizes legacy unsupported variants and removes their
  cache files after commit.
- Eliminate duplicate derivative-byte storage:
  - the file cache is authoritative and quota-counted;
  - diskcache stores only small key-to-path metadata, capped at 64 MiB;
  - bump the cache version and clear legacy byte-valued entries once.
- Recheck lease expiry in the same `UPDATE` that reclaims a derivative job, in
  both integrity repair and supervisor recovery. A heartbeat renewal between
  snapshot and transition must make the transition affect zero rows.
- Add global poster concurrency control and bounded queue waiting. Enforce the
  poster quota with LRU eviction while protecting files currently being
  generated or served.
- Limit poster subprocess output, preserve the 30-second execution timeout, and
  guarantee temporary-file cleanup on all failure paths.

## Phase 5 - HTTP Semantics, Startup, Migrations, And Diagnostics

- Replace derivative `immutable` caching with
  `public, max-age=0, must-revalidate`; retain identity-aware ETags and `304`
  responses.
- Correct video Range handling:
  - clamp a satisfiable end beyond EOF;
  - preserve `416` for invalid start, empty, and multi-range requests;
  - support strong ETag and HTTP-date `If-Range`;
  - send the full `200` representation when the validator mismatches.
- Make lifespan startup exception-safe with an `ExitStack`-style service
  registry:
  - register cleanup immediately after each successful start;
  - unwind in reverse order on startup failure;
  - attempt every stop even if an earlier stop raises;
  - log incomplete shutdowns without skipping later services.
- Convert the nanosecond schema migration to an explicit versioned `v1 -> v2`
  migration:
  - create a SQLite backup before destructive work;
  - disable foreign keys before `BEGIN IMMEDIATE`;
  - execute rename, copy, drop, and index statements inside one transaction;
  - run `foreign_key_check`;
  - roll back fully on injected failure and only then set `user_version=2`.
- Log unexpected exceptions with traceback and return generic public error
  messages. Preserve detailed information in server logs and durable job error
  fields only.
- Document every live environment variable and update architecture, metadata
  parsing, third-party cache roles, and test catalog documentation.

## Test Plan And Acceptance Criteria

Each new backend test module must include the required `Purpose`, `Guarantees`,
and `Run when` header.

### Security

- Direct production API without proxy secret returns `403`.
- nginx returns `401` without Basic Auth and succeeds with credentials.
- SSE works through authenticated nginx.
- Unregistered, offline, and excluded paths return `404`.
- File symlinks outside import roots are never cataloged.

### Metadata And Catalog

- Sidecar create, change, and delete reindex without changing the image.
- Oversized sidecars fail deterministically.
- Video-only and mixed-media status converges correctly.
- Offline import roots produce tombstones.
- Concurrent unregister versus extraction cannot recreate orphan rows.

### Watcher And Refresh

- Overflow remains pending and is processed on later ticks.
- Zero debounce cannot busy-spin.
- Repeated limited refresh ticks cover every library.
- GET status never creates threads or mutates jobs.

### Derivatives

- Unsupported sizes return `422`.
- Quota zero returns `507` without rendering.
- No HTTP path bypasses scheduler or quota.
- Heartbeat-renewed claims cannot be reclaimed.
- Legacy diskcache bytes are cleared.
- Poster concurrency and quota are enforced.

### HTTP And Runtime

- Cache revalidation observes source changes immediately.
- Range and If-Range cases match the documented behavior.
- NUL paths return `400`.
- Startup failure unwinds all prior services.
- Injected migration failure restores the exact pre-migration schema and data.
- Unexpected errors are logged but not disclosed.

Required gates after every PR:

1. Targeted pytest files for the changed subsystem.
2. `./test.sh backend-api`
3. `./test.sh lint`
4. `./test.sh docs`

Final integration gate:

- `./test.sh fast`
- authenticated nginx smoke tests
- catalog, metadata, and derivative recovery tests against a copied real
  database
- `./test.sh full`

## Rollout And Assumptions

- Deploy nginx Basic Auth and the proxy-secret include before deploying the
  backend that requires the secret.
- Back up the live metadata database and derivative cache before the v2
  migration.
- Catalog-only behavior is intentionally not feature-flagged in production;
  callers relying on unregistered absolute paths must register those folders
  first.
- No frontend login screen is added because browser authentication is owned by
  nginx.
- Source files are never modified or deleted by remediation work.
- After all phases pass the full gate, move this plan to `docs/archived/` and
  update maintained documentation dates.
