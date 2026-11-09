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
| BL-16 | Pending | |
| BL-15 A | Pending | |
| BL-15 B | Pending | |
