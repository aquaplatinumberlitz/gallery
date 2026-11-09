# Backlog

Status: Maintained

Last reviewed: 2026-11-09

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
| BL-13 | ~~Single-letter Latin search (for example `a`) takes about 1.6 s on the 100k fixture, through the existing filename-prefix path (also about 1.8 s on `main`). It needs a prefix index or a minimum-selectivity rule~~ **Done** (2026-11-09, [fix plan](BACKLOG_13_14_FIX_PLAN.md)): every search class, including dense 1-3 character free text, 1-character fielded filters, their keyset pages and `/api/search/count`, is within the 300 ms p95 budget as budgeted `search-benchmark` classes; see Search planning in `docs/ARCHITECTURE.md` and the Search Bench section of `docs/testing/PERFORMANCE_TESTING.md` | UX review Track A (2026-11-08) |
| BL-14 | **Done (2026-11-09, [fix plan](BACKLOG_13_14_FIX_PLAN.md), branch `fix/bl14-connection-leaks`).** Every production connection now closes deterministically (`ClosingConnection`, `contextlib.closing`, `ThreadClosingCache`), tests close what they open, `ResourceWarning: unclosed database` is a pytest error, and the writer-yield test uses a manual clock. Original report: `test_worker_contention_phase2_*` tests are timing- or resource-flaky in a full run: "unable to open database file" in the derivative file under `./test.sh fast`, and a writer-yield timing assertion seen in CI. They pass alone, and the same failure occurs on `main` | UX review integration (2026-11-08) |
| BL-15 | Dense short-query keyset chains on the 100k fixture sit near the 300 ms p95 budget after BL-13: the `c` page 2-3 chain measures 283-320 ms and the dense 3-char chain up to 328 ms, both host-dependent. The remaining cost is a floor of about 150-165 ms of bm25 ranking plus the sort-key join per 100k matches, repeated on every page. Ideas: carry a ranked candidate window across pages, a single-token tier shortcut, or denormalize mtime | BL-13 review (2026-11-09) |
| BL-16 | The unscoped, unfiltered BL-13 page plan can order or skip rows when a large group ties on tier, bm25 rank and mtime past the preselect bound (about 215+ tied rows after the cursor with the default page) and metadata ids or file rowids run in a different order from asset ids. The bounded preselects break ties by their own row id; the page orders them by asset id. SC-01 fixed this for scoped and field-filtered searches: a cut-short source covers only the rows before its boundary tie group, otherwise the plan falls back to the exact statement. A scratch reproduction with 60 tied rows, a bound of 24 and reversed metadata ids fails `cat`, `c` and `ca` with scope all. Likely in practice only for a large batch with one prompt and identical mtimes, such as files extracted from an archive. Fix: give the unscoped plan the same cover check without the shadow check, after measuring its cost on the thin BL-15 margins | SC-01 Opus review (2026-11-09) |
