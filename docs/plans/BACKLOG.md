# Backlog

Status: Maintained

Last reviewed: 2026-11-08

Deferred work that no active plan owns. Each item names where it came from; the
source document has the evidence and the reason it was deferred. Pick an item up
by writing a plan in `docs/plans/` and removing it here when that plan ships.

| ID | Item | Source |
|----|------|--------|
| BL-1 | Video poster cache has no supersede cleanup (`backend/video.py`) | [Pipeline audit](../archived/PIPELINE_AUDIT_FIX_PLAN.md#backlog-out-of-scope-recorded-only) |
| BL-2 | `mtime` unit differs: browse emits `mtime_ns`, search and inspector emit seconds | Pipeline audit |
| BL-3 | The 409 "Image changed while its derivative was generated" message misleads for a changed but unscanned file; the frontend image retry is status-blind | Pipeline audit |
| BL-4 | `parse_metadata` holds `_metadata_cache_lock` across the DB read | Pipeline audit |
| BL-5 | Scan holds all records in memory before the first write and runs ffprobe serially; measure on a large library first | Pipeline audit |
| BL-6 | Offline assets keep ready derivatives; a move is delete plus create (re-extract, re-render) | Pipeline audit |
| BL-7 | `visual_fingerprints` reported `skipped_count` 4 with skip reasons summing to 2 | Pipeline audit |
| BL-8 | `METADATA_INDEXER_SCAN_YIELD_*` env vars are parsed but unused | Pipeline audit |
| BL-9 | An on-demand derivative request waits up to 10 s in a sleep loop inside the threadpool (default 40 threads); measure under load before moving to an async wait | Pipeline audit (OR-02) |
| BL-10 | `_served_paths` is a set, not a refcount, so a deferred unlink can race a second concurrent response for the same file | Pipeline audit (OR-03) |
| BL-11 | `_serve_derivative` has an unreachable `asset_id is None` branch | Pipeline audit (OR-04) |
| BL-12 | Per-library catalog rebuild. The maintenance Rebuild (`POST /api/maintenance/imported-data/rebuild`) clears and rebuilds every library; `scan_worker.queue_rebuild(library_id)` already supports one library, but no route or UI exposes it. Today a per-library rescan (`POST /api/libraries/{id}/scan`) covers the common case | Idea from an old VPS stash (2026-06-21, dropped 2026-11-08) |
