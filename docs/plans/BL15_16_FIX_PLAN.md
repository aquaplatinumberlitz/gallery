# BL-15 / BL-16 Fix Plan

Status: Active

Created: 2026-11-09

Source: `docs/plans/BACKLOG.md` BL-15 and BL-16, after SC-01 (PR #20, `main` @ `2ff6a53`). The owner approved the
proposal: BL-16 first, then BL-15 option A (cache a ranked window), then BL-15 option B (denormalize mtime).
Option C (newest-first ordering for 1-character queries) is not approved. It changes results, so do not do it.

## Items

| ID | Problem | Evidence | Acceptance |
|----|---------|----------|------------|
| BL-16 | The unscoped, unfiltered BL-13 page plan can mis-order or skip rows when a group tied on (tier, rank, mtime) crosses a cut-short preselect's bound and the preselect's tie-break id (metadata id or file rowid) disagrees with the page's asset id. SC-01 fixed the exact (scoped and field-filtered) plan with a cover check. The unscoped plan has no such check. | Scratch reproduction during the SC-01 review: 60 rows tied on rank and mtime, metadata ids reversed against asset ids, bound 24, `scope=all`. `cat`, `c` and `ca` diverge from the exact statement on page 1. | Regression test in the BL-13 pins file style: `scope=all`, tiny bound, tied rows, reversed ids, several queries. Every keyset page equals the exact single statement where the unscoped plan claims to. It fails before the fix. The fix detects a cut-short bounded source from the rows the plan already reads (no extra query in the common case). When the page reaches that source's boundary tie group, it falls back to the exact statement. BL-13 pins and the existing documented cross-source repeat behaviour are unchanged; the pins are never re-recorded. No unscoped bench class regresses more than noise (document the before and after). |
| BL-15 (A) | Dense 1-3 character keyset chains re-rank the whole FTS match set (about 100k rows) on every page. `c` page 2-3 chains are about 250-280 ms p95 against a 300 ms budget, for unscoped and scoped search alike. | SC-01 review bench: `short_free_c_keyset_pages` 255-264, `scoped_*_short_free_c_keyset_pages` 251-268, `dense_three_char_keyset_pages` 256-258. | Keyset pages 2-3 of the dense classes cost well under budget (target p95 at most 100 ms on 100k). Pages stay byte-identical to the current plan: BL-13 and SC-01 pins and oracles unchanged and never re-recorded. If a design would only differ by removing documented repeats, stop and report instead. Never stale: any write that can change a result invalidates. That covers metadata, file_index, assets (offline, deleted, size and mtime), library and import-path ownership, and the search text index. A test proves each kind of write invalidates. Memory is bounded (entry count and size), and the cache is thread-safe under concurrent requests. Production runs a single uvicorn process, but worker threads write in the same process. |
| BL-15 (B) | The dense preselects join `image_metadata` (and `file_index`) only to get the mtime sort key. | SC-01 analysis: the cost floor is bm25 over about 100k matches plus the sort-key join. | Prototype the saving on the 100k fixture first, by query plan and timing, before writing any migration. Go ahead only if page 1 of the dense classes saves at least 20 ms p95. Otherwise stop, report the numbers, and close B as not worth a schema change. If it goes ahead: a v16 migration with a `.v15.bak` backup, kept consistent on every write path (insert, update, rescan, delete, rebuild), with migration and consistency tests in the style of the v14/v15 tests. Report the migration time and the DB size change on the 100k fixture. Results identical (pins). |

## Track

| Track | Model | Branch | Items, in order |
|-------|-------|--------|-----------------|
| K | Sonnet | `fix/bl15-16-impl` | BL-16, then BL-15 A, then BL-15 B, with one commit or more per item |

## Rules
- Branch from `fix/bl15-16`; commit on the track branch; do not push.
- For each item:
  - reproduce first and record the fail-before;
  - add the regression evidence, then fix;
  - measure before and after on the 100k fixture.
- Never weaken tests or budgets. Report every pre-existing test you edit, with the reason.
- Update maintained docs:
  - `docs/ARCHITECTURE.md` search planning;
  - `docs/testing/PERFORMANCE_TESTING.md`;
  - `docs/testing/TEST_CATALOG.md`;
  - `docs/CONFIGURATION.md`, if a setting is added;
  - mark the items done in `docs/plans/BACKLOG.md`.
- Run these checks:
  - targeted tests;
  - the full backend pytest in both modes;
  - `./test.sh backend-api`;
  - `./test.sh lint` and `./test.sh docs`;
  - `bench_search` on 100k after each item.

## Review gates (Opus)
1. Read the diff after each item, rerun the evidence, and check every acceptance item.
2. Run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`.
3. Open the PR and merge once CI is green. The VPS deploy needs the owner's word in the VPS session.

## Progress

| Item | Status | Evidence |
|------|--------|----------|
| BL-16 | Merged after Opus review | The unscoped plan derives a cover from any bounded source that returned a full bound, using the rows it already read, so no extra query. It falls back to the exact statement when the page reaches that cover. Fail-before: `cat`, `c` and `ca` on page 1, planned asset 37 versus exact asset 1. A second test asserts no fallback when mtimes are distinct. The 99 bench classes are unchanged within noise. Documented limit: a cut-short preselect that loses rows to the strict joins is invisible to the single statement. |
| BL-15 A | Merged after Opus review | A bounded, thread-safe LRU (128 entries, 32 MiB, configurable, `0` turns it off) keeps each bounded source's rows. Keyset pages are served from it up to the entry's cover, and the plan reruns uncached when it cannot guarantee a page. Invalidation uses `search_generation(value, epoch)`, bumped by 24 triggers inside the writing transaction on 8 tables. The generation is read before any data, and fielded or filtered queries are never cached. 44 tests cover each write kind, the caps, concurrency, and cache-on versus cache-off equivalence on the SC-01 corpus. On 100k, page 2-3 p50 went from 170-230 ms to 8-17 ms, with p95 at most 33 ms. Page 1 is unchanged. Bulk insert costs about 10-20% more with the triggers (30k rows: 3.2-3.5 s became 3.7-4.0 s). Opus checked every column the search SQL reads against the trigger column lists. |
| BL-15 B | Closed, no-go | The prototype saved 19-31 ms at the median on unscoped dense page 1 only, gained nothing scoped, and its p95 moves were within jitter. That misses the 20 ms p95 bar, so no v16 migration was written. Opus agrees. The page-1 floor is now BL-17. |
