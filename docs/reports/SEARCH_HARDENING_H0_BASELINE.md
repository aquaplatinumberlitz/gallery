# Search Hardening H0 Baseline

Status: Measurement snapshot

Captured: 2026-07-13 UTC

This report records the pre-hardening search contract and performance baseline
required by `SEARCH_HARDENING_IMPLEMENTATION_PLAN.md`. It is historical
evidence, not the source of truth for current behavior after later phases.

## Environment

| Item | Value |
| --- | --- |
| Git HEAD | `70e839c867f915194284487db659d982052c490c` |
| Branch/worktree | `main`, clean, tracking `origin/main` |
| Python | `3.11.15` |
| Node.js | `22.22.2` |
| pnpm | `11.5.2` |
| SQLite | `3.50.4` |
| Catalog schema | `3` |

## Contract baseline

The integration contract test locks these additive-compatible shapes before
the hardening refactor:

- `GET /api/search`: legacy grouped `albums`, `photos`, `videos`, and `prompt`
  arrays, canonical `media`, numeric-or-null `next_cursor`, pagination fields,
  and the current media metadata fields.
- `GET /api/search-metadata`: `query`, global `total`, and legacy metadata rows.
- `GET /api/facets`: the current tool/model/sampler/scheduler/folder/orientation,
  availability, and LoRA arrays with `{value, count}` items.

The H4 contract intentionally replaces new search cursors with opaque strings
while preserving the grouped response fields.

## Test baseline

| Suite | Result |
| --- | --- |
| Targeted backend search/facet/parser pytest | 157 passed in 7.36 s |
| Targeted frontend search/parser/drawer Vitest | 77 passed in 11.52 s |
| Managed fielded-search Playwright specs | 18 passed in 42.2 s |

## Performance baseline

Both measurements used 10 warm iterations and the maintained 300 ms search p95
budget.

| Dataset | Query | Search p50 | Search p95 | Result |
| --- | --- | ---: | ---: | --- |
| Deterministic 240-asset fixture | `perf` | 110.83 ms | 131.00 ms | Pass |
| Representative local catalog | `a` | 103.63 ms | 108.09 ms | Pass |

The deterministic fixture also measured the inspector metadata endpoint at
14.46 ms p95. The representative catalog measured it at 3.00 ms p95.

## Query-plan baseline

Plans were captured against the deterministic fixture for the shared active
catalog predicate and the active filename, prompt, and album queries.

- Active asset ownership: `SEARCH catalog_asset USING INDEX
  sqlite_autoindex_assets_1 (library_id=? AND path=?)`.
- Filename FTS: scans the FTS virtual index, looks up `file_index` by its path
  key, then uses the composite asset ownership index.
- Prompt FTS: scans the metadata FTS virtual index, looks up metadata by rowid
  and `file_index` by path, then uses the composite asset ownership index.
- Album suggestion: scans the filename FTS virtual index, looks up the folder
  row by path, and searches visible assets through a library-prefixed asset
  index.

No active-catalog query plan reported a full scan of `assets` for the
correlated ownership predicate.
