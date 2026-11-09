# Scoped Search Perf and Lightbox Metric Plan

Status: Active

Created: 2026-11-09

Source: a direct (Opus) review on `main` @ `3f9945c`, after BL-13/BL-14 (PR #19).

Measurements:
- Search: the retained `./test.sh perf` fixture (100,032 assets), backend in-process
  over HTTP, 6 runs, median.
- Lightbox: a per-frame in-page trace against the same fixture.

The owner approved both fixes.

## Findings

| ID | Sev | Problem | Evidence | Acceptance |
|----|-----|---------|----------|------------|
| SC-01 | High (scalability, default UI path) | Searches with a scope filter skip the BL-13 page plan and the bounded FTS preselect. The UI default scope is "This folder", and the benchmark only measures `scope=all`. | `ranked_search.py:855-856` (`bounded_metadata_fts` / `dense_files` require `not scope_sql and not field_where`). `ranked_search.py:1405` (the page plan requires `not scope_sql and not field_where`). Page-1 medians, all / library / folder root: `a` 77 / 2128 / 2219 ms, `m` 64 / 2224 / 2324, `c` 224 / 2362 / 2368, `ass` 199 / 3229 / 3334. The text+fields `fielded` query is 195 / 338 / 347-366. Page 2 is similar. Counts are already fast (67-107 ms), and `prompt:c` is 40 ms. | p95 of at most 300 ms on 100k for the scoped variants (library, folder root, nested folder), for: 1-char free text (`a`, `m`, `c`), dense 2/3-char (`as`, `ass`), text plus field filters (`fielded`), keyset pages 2-3, and count. The results (set, order, cursors, count/page consistency) equal the current scoped results, pinned the same way BL-13 pinned unscoped ones. Scope semantics are unchanged, including import-path ownership, offline/visibility rules, and nested folder versus direct children as the scope defines them. These scoped classes are budgeted in `search-benchmark`, so the default UI path cannot regress unnoticed. `scope=all` classes do not regress. |
| LB-01 | Medium (measurement) | The lightbox `visual ready p95` (budget 1000 ms; CI 960, locally 1012-1049) measures when Playwright gets around to checking, not when the preview is actually ready. | Per-frame trace: click 0, overlay 24 ms, preview response done 61 ms, placeholder loaded 96 ms, main preview inserted and complete at 529 ms. The wait until 529 ms is the PhotoSwipe 333 ms zoom-in; PhotoSwipe appends heavy content after the opener animation. The report's `browserDecodeVisualReadyMs` is about 870-900 ms, with network 0-56 ms. `lightbox.perf.spec.ts` takes `readyAt` inside `waitForPreviewDecoded`, which only starts after `toBeVisible` and an `expect.poll` with 100/250 ms intervals. | Readiness is timed in-page by an observer armed before the click. It records when the active slide's non-placeholder preview `<img>` is in the DOM, complete, decoded, and visible, and that is reported against the click mark. Report it beside the old harness figure for one run, then keep only the correct one. The budget stays 1000 ms. Show before/after numbers. No app behaviour change. |

## Tracks

| Track | Model | Branch | Items |
|-------|-------|--------|-------|
| I | Sonnet | `fix/scoped-search-perf` | SC-01 |
| J | Haiku | `fix/lightbox-visual-ready-metric` | LB-01 |

## Rules
- Branch from `fix/scoped-search`; commit on your track branch; do not push.
- Reproduce first, record the fail-before, add the regression evidence, then fix.
- Never weaken tests or budgets. Report every pre-existing test you edit, with the reason.
- Update maintained docs (`docs/ARCHITECTURE.md` search planning, `docs/testing/PERFORMANCE_TESTING.md`, `docs/testing/TEST_CATALOG.md`).
- Run these checks:
  - targeted tests;
  - track I: full backend pytest in both modes, `./test.sh backend-api`, and the search benchmark;
  - track J: the lightbox perf spec, run three times;
  - `./test.sh lint` and `./test.sh docs`.

## Review gates (Opus)
1. Read each diff, rerun the evidence, and check every acceptance item.
2. Merge both tracks, then run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`.
3. PR, merge once CI is green, deploy. The VPS deploy still needs the owner's word in the VPS session.

## Progress

| Track | Status | Evidence |
|-------|--------|----------|
| I | Pending | |
| J | Pending | |
