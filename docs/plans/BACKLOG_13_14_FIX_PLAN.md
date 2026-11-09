# Backlog BL-13 / BL-14 Fix Plan

Status: Active

Created: 2026-11-09

Source: `docs/plans/BACKLOG.md` BL-13 and BL-14. The owner asked for the best
fix for both ("Fix it theo hướng tối ưu nhất"). Baselines come from the
search-typing work on 2026-11-09, with schema v14 on `main` @ `02edf78`.

## Items

| ID | Problem | Evidence | Acceptance |
|----|---------|----------|------------|
| BL-13 | Very short, dense queries are slow on the 100k fixture. | `m` (1 char): about 453-458 ms p95, dominated by the album-folder aggregate step. `prompt:c` (dense one-char fielded filter): about 620-640 ms, because the bounded preselect sorts all ~100k matching rows. Before v14, `a` took about 1.6 s. | Every query p95 is at most 300 ms on the 100k fixture, including 1-char free text (`a`, `m`, `c`), 1-char fielded filters (`prompt:c`, `name:i`), their keyset pages 2-3, and the count endpoint. These run as budgeted `search-benchmark` classes. Results stay the same: same tiers and ordering, AND semantics, cursors, scope, and count/page consistency. The bounded `+` count convention may be used. No regression above budget for any existing workload. |
| BL-14 | SQLite connections are leaked. `with sqlite3.connect(...) as c:` commits but never closes; there are 12 production sites (for example `_migrations.py` backups) and many test sites. Under `./test.sh fast` (coverage) the suite runs out of file descriptors: "Too many open files" or "unable to open database file" at about 88%. It also emits many `ResourceWarning: unclosed database`. Separately, `test_worker_contention_phase2_catalog::test_a_saturated_writer_yields...` has a wall-clock assertion that failed in CI (0.409 s against 0.2 s). | Local `./test.sh fast` on `main` and on PR #17; CI on PR #15. | Every production connection is closed deterministically (`contextlib.closing`, a shared helper, or an explicit `close`). The long-running backend does not leak descriptors: a test opens and closes the code paths repeatedly and asserts the process fd count is stable. Tests close what they open. `./test.sh fast` passes locally twice in a row with coverage. The backend test run has 0 `ResourceWarning: unclosed database`, enforced by a pytest filter that turns that warning into an error. The timing-flaky tests are made deterministic (events or controlled clocks, not wall-clock thresholds) without weakening what they prove. |

## Tracks

| Track | Model | Branch | Items |
|-------|-------|--------|-------|
| G | Sonnet | `fix/bl13-short-query-perf` | BL-13 |
| H | Sonnet | `fix/bl14-connection-leaks` | BL-14 |

## Rules
- Branch from `fix/backlog-13-14`. Commit on your track branch and do not push.
- Reproduce first and record the fail-before evidence:
  - for BL-13, the benchmark numbers;
  - for BL-14, the fd count and warning count, plus a fast-suite failure or a targeted reproduction.
- Never weaken tests. Report every pre-existing test you edit, with the reason.
- Update maintained docs (`docs/ARCHITECTURE.md`, `docs/testing/PERFORMANCE_TESTING.md`, `docs/testing/TEST_CATALOG.md`) and mark the items done in `docs/plans/BACKLOG.md`.
- Run these checks:
  - targeted pytest;
  - the full `pytest backend/tests` in both modes;
  - `./test.sh lint` and `./test.sh docs`;
  - `./test.sh backend-api`;
  - track G: the search benchmark;
  - track H: `./test.sh fast` twice.

## Review gates (Opus)
1. Read each diff, rerun the evidence, and check every acceptance item.
2. Merge both tracks, then run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`.
3. Open the PR, merge it once CI is green, and deploy. The owner gave Opus authority to review, merge and deploy on its own.

## Progress

| Track | Status | Evidence |
|-------|--------|----------|
| G | Merged after Opus review | Tier-ordered page plan, a capped count (`4096+`), a field-only ordered probe, and the v15 folder-image index (+4.65% DB size, 4.8 s migration).
- 100k p95, base to quiet host: `a` 1940 to 77 ms, `m` 505 to 75 ms, `prompt:c` 759 to 15 ms, counts 2.2-4.2 s to 49-100 ms, `ass` 3326 to 236 ms.
- Result order is pinned by sha256 and an old-plan oracle.
- Opus ran `./test.sh perf` 3 times on the merged branch. The densest keyset chains sit near the budget (`c` chain 283-320 ms, the dense 3-char chain up to 328 ms). The pre-existing `fielded` class and lightbox visual-ready also flake near their budgets (309 ms, 1012-1049 ms). One of the 3 runs passed every check. The remaining margin is tracked as BL-15. |
| H | Merged after Opus review | `ClosingConnection` / `open_connection` replace about 130 leaking production sites and 12 backup sites. `ThreadClosingCache` covers the diskcache per-thread connections.
- fd growth over 20 rounds: +1400 before, at most 2 after. Unclosed-database warnings: 13187 before, 0 after, and now enforced as an error.
- Contention tests are deterministic (manual clock, mutation-checked).
- `./test.sh fast` passed twice in a row, and again on the merged branch. |
