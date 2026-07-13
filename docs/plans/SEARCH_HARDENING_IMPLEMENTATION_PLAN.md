# Search Hardening Implementation Plan for OpenCode

Status: Active

Last reviewed: 2026-07-13

Owner: OpenCode

Priority: P0-P1

Execution: Sequential and phase-gated

Depends on: `AGENTS.md`, maintained project documentation, and the current implementation

Follow-up plans:

- [Search Discovery Evolution](SEARCH_DISCOVERY_EVOLUTION_IMPLEMENTATION_PLAN.md)
- [Related Assets and Generation Discovery](RELATED_ASSETS_IMPLEMENTATION_PLAN.md)

## Objective

Harden the existing FastAPI, SQLite FTS5, Vue 3, and TanStack Query search
system without replacing its architecture.

The audit rated the current implementation at approximately **7.9/10 as a
general search system and 8.5/10 for this product**. Immich was approximately
8.2/10 overall, while DiffusionToolkit was approximately 6.3/10 overall and
8.5/10 for diffusion-metadata filter breadth. The conclusion is that the
gallery already has the right architecture for a local AI-art browser. This
plan fixes correctness, latency, pagination, API, and UX gaps before adding new
search capabilities.

Research files and archived plans are evidence only. Current behavior must be
verified against code, maintained docs, and tests:

- [Architecture](../ARCHITECTURE.md)
- [Third-Party Libraries](../THIRD_PARTY_LIBRARIES.md)
- [Testing](../testing/README.md)
- [DiffusionToolkit Metadata Search Analysis](../research/DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md)
- [Historical Search Pattern Adaptation](../archived/SEARCH_PATTERN_ADAPTATION.md)
- [Historical Immich/DT Audit](../archived/IMMICH_DT_ADAPTATION_AUDIT_AND_ROADMAP.md)

## Non-goals

- Do not replace SQLite with PostgreSQL or an external search server.
- Do not add Redis, BullMQ, OCR, faces, people, or location search.
- Do not add related-asset ranking, visual fingerprints, or semantic ML in this plan.
- Do not remove the legacy grouped response fields.
- Do not refactor unrelated gallery, lightbox, admin, or metadata-inspector UI.
- Do not make filesystem scanning part of a search request.

## OpenCode execution rules

1. Read `AGENTS.md` and the maintained docs listed above before editing.
2. Record `git rev-parse HEAD` and `git status --short`. The worktree may be
   dirty; never reset or overwrite unrelated changes.
3. Execute phases in order. Do not start a phase until the preceding phase's
   acceptance gates pass.
4. Add `Purpose:`, `Guarantees:`, and `Run when:` headers to new important test
   modules and scripts as required by the repository checker.
5. Update `docs/testing/TEST_CATALOG.md` when test guarantees change.
6. Update maintained API, architecture, configuration, and third-party-library
   docs whenever their contracts change.
7. Mark a checklist item complete only after implementation and evidence both
   exist. Keep evidence concise in the execution log.
8. Stop and report a blocker if implementation requires destructive migration,
   removal of compatibility fields, or a new externally exposed service.

## H0 - Baseline and contract lock

**Goal:** Establish a reproducible baseline before changing search behavior.

### Tasks

- [x] Capture HEAD, dirty files, Python/Node versions, and SQLite version.
- [x] Run the current targeted backend search/facet/parser tests.
- [x] Run the current targeted frontend search composable, parser, and drawer tests.
- [x] Run the current managed fielded-search Playwright specs.
- [x] Run `scripts/bench_search.py` against the deterministic fixture and one
      representative local database when available.
- [x] Capture `EXPLAIN QUERY PLAN` for the active-catalog predicate, filename
      search, prompt search, and album suggestion query.
- [x] Record current API shapes for `/api/search`, `/api/search-metadata`, and
      `/api/facets` in tests before refactoring them.

### Baseline commands

```bash
backend/.venv_linux/bin/python -m pytest -q \
  backend/tests/test_metadata_store_search.py \
  backend/tests/test_search_coverage.py \
  backend/tests/test_api_integration_metadata_search_facets.py \
  backend/tests/test_fielded_search_parser.py \
  backend/tests/test_facets.py

cd frontend && corepack pnpm exec vitest run \
  src/composables/__tests__/useFieldedSearch.test.ts \
  src/composables/__tests__/useUnifiedSearchQuery.test.ts \
  src/composables/__tests__/useFacetsQuery.test.ts \
  src/utils/__tests__/serializeAdvancedSearchToQuery.test.ts \
  src/components/search/__tests__/AdvancedSearchDrawer.test.ts

GALLERY_TEST_SKIP_BUILD=1 ./test.sh e2e \
  frontend/tests/e2e/search-fielded-ui.spec.ts \
  frontend/tests/e2e/advanced-search-drawer.spec.ts
```

### Stop conditions

- A baseline failure is unrelated to search and prevents trustworthy validation.
- The schema version or public contract has already changed in overlapping
  dirty work and cannot be reconciled safely.

## H1 - Active catalog ownership and indexed lookup

**Goal:** Remove the measured correlated asset scan and strengthen ownership
correctness.

### Required implementation

- [x] Change the shared active file-index ownership predicate to require both:
  - `catalog_asset.library_id = fi.library_id`
  - `catalog_asset.path = fi.path`
- [x] Keep all current active-version checks: offline/deleted state, source
      mtime, size, media type, and registered-library ownership.
- [x] Add a versioned migration that backfills `file_index.library_id` only
      when exactly one catalog owner exists for the path.
- [x] Leave ambiguous or ownerless rows unowned and exclude them from active
      search. Surface them through existing integrity diagnostics rather than
      guessing an owner.
- [x] Use the existing unique asset index on `(library_id, path)`. Do not add a
      redundant `assets(path)` index.
- [x] Apply the corrected predicate consistently to search, facets, metadata
      search, and other current-file helpers.

### Acceptance gates

- [x] `EXPLAIN QUERY PLAN` reports indexed lookup on `(library_id, path)` and no
      full scan of `assets` for the correlated predicate.
- [x] Two libraries cannot satisfy each other's file-index rows even when test
      data deliberately reuses a path.
- [x] Null, mismatched, inactive, offline, deleted, stale-mtime, and stale-size
      rows are excluded.
- [x] Migration rollback/backup behavior follows the current schema migration
      pattern and passes foreign-key checks.

## H2 - DB-only album suggestions and response authorization

**Goal:** Remove filesystem enumeration and repeated path checks from the
search request hot path.

### Required implementation

- [x] Extract or reuse a batch catalog folder aggregation helper from the browse
      data layer.
- [x] Return album search rows with `library_id` and calculate, in bounded SQL:
  - direct image count;
  - up to three newest direct image covers;
  - whether the folder has visible catalog children when the response contract
    needs that value.
- [x] Preserve the current first-page-only and 12-album suggestion limits.
- [x] Remove search calls to `build_album_metadata()`, `Path.iterdir()`,
      `os.scandir()`, `Path.stat()`, and `Path.exists()`.
- [x] Join response rows to active assets, libraries, and import-path ownership.
      Use pure catalog path-containment helpers to protect against corrupted
      rows without resolving every filesystem path.
- [x] Remove the five separate `_filter_safe_paths()` passes from `/api/search`.
- [x] Do not schedule stale-index cleanup from a search response. Scan, watcher,
      offline-asset, and integrity workflows own catalog freshness.
- [x] Apply the same DB-only policy to `/api/search-metadata`.

### Compatibility rule

Search may reflect catalog state until watcher/scan reconciliation runs, just
as DB-first browse does. A missing source file must fail when the media-serving
route authorizes it; it must not force filesystem I/O into search.

### Acceptance gates

- [x] Monkeypatch all album filesystem helpers to raise; indexed search still succeeds.
- [x] Search performs no filesystem call proportional to album/result count.
- [x] Album count and cover semantics match DB-first browse for the same folder.
- [x] All-scope results include correct library context without exposing an
      unowned path.

## H3 - Unified relevance and opaque keyset pagination

**Goal:** Let strong prompt matches outrank weak filename matches and make deep
pagination stable and non-linear.

### Ranking policy

Use these descending relevance tiers:

| Tier | Match |
| ---: | --- |
| 100 | Exact filename |
| 90 | Filename prefix |
| 80 | Exact positive-prompt phrase |
| 70 | Filename FTS token match |
| 65 | Positive-prompt FTS or CJK trigram match |
| 50 | Filename substring fallback |
| 40 | Negative-prompt match |
| 30 | Structured-filter-only result |

Within one tier, order by FTS rank ascending, source `mtime_ns` descending,
then stable `asset_id` ascending. Use the same tuple for dedupe and pagination.

### Required implementation

- [x] Build one normalized candidate query/CTE for filename, video filename,
      prompt, negative prompt, and field-only candidates.
- [x] Join active assets directly so every row has stable `asset_id` and
      `library_id`.
- [x] Compute match tier/type in candidate rows. Remove
      `_count_filename_matches()` and `_prompt_match_kind()` preflight probes.
- [x] Use `LIMIT page_size + 1` for `has_more`; do not calculate an exact total
      for the active gallery stream.
- [x] Replace `LIMIT/OFFSET` pagination with a versioned base64url JSON cursor.
- [x] Cursor payload contains:
  - version;
  - canonical request fingerprint;
  - relevance tier;
  - FTS rank or deterministic fallback rank;
  - `mtime_ns`;
  - `asset_id`.
- [x] Reject malformed, wrong-version, or wrong-request cursors with a clear
      `400` response.
- [x] Keep decimal cursor input only on legacy `GET /api/search`; route it
      through the old offset path and emit a deprecation header. New responses
      and the active frontend use only opaque cursors.

### Acceptance gates

- [x] A strong prompt phrase outranks a weak filename substring.
- [x] Exact filenames remain first in the relevance goldens.
- [x] Tied results have deterministic order.
- [x] Pages have no duplicates or omissions, including equal-score rows.
- [x] Insertion/deletion between pages does not repeat an already returned row.
- [x] A cursor from query/scope A is rejected for query/scope B.
- [x] The active keyset query contains no `OFFSET`.

## H4 - Typed FastAPI contracts and scope parity

**Goal:** Make search APIs explicit, validated, documented, and consistent
with the frontend.

### Public contract changes

- [x] Add regular Pydantic models for search result, album result, legacy
      metadata result, search response, and facet response. Do not use
      `RootModel`.
- [x] Use explicit endpoint return types and `Annotated[..., Query(...)]`.
- [x] Change `next_cursor` from `number | null` to `string | null`.
- [x] Add `asset_id`, `library_id`, and `library_name` to canonical media rows.
- [x] Support three canonical scopes:
  - `folder`: one folder recursively;
  - `library`: one registered library;
  - `all`: all registered libraries.
- [x] Preserve `current` as the legacy GET alias for `folder`.
- [x] Give `/api/facets` the same scope, library, and folder semantics as search.
- [x] Keep `albums`, `photos`, `videos`, `prompt`, and `media`; derive the legacy
      arrays from canonical rows without additional queries or path validation.
- [x] Fix `/api/search-metadata.total` to report the real global match total.

### Error policy

| Condition | Status |
| --- | ---: |
| Malformed or incompatible cursor | 400 |
| Invalid scope/filter/value | 422 |
| Folder outside the selected library | 404 |
| Required index temporarily unavailable | 503 |
| Unexpected internal failure | Existing sanitized 500 contract |

Blocking SQLite or filesystem-compatible validation must not run directly in
an `async` path operation. Prefer a normal synchronous endpoint when the whole
operation is blocking, or use the existing threadpool boundary deliberately.

### Acceptance gates

- [x] OpenAPI shows the complete response and error schemas.
- [x] Legacy grouped arrays are projections of `media` and remain consistent.
- [x] Folder/library/all search and facets share the same context tests.
- [x] All-scope UI can identify the owning library without parsing paths.

## H5 - Vue search state, parser parity, and result UX

**Goal:** Fix correctness and error-state gaps while splitting only the search
responsibilities touched by this work.

### Component and data-flow map

| Unit | Responsibility | Contract |
| --- | --- | --- |
| `App.vue` | Compose layouts and the shared drawer | Typed props/events only; no parser mutation logic |
| `SearchResultsPanel.vue` | Virtualized search sections and page loading | Receives query state/results; emits retry/open actions |
| `SearchFeedback.vue` | Loading, blocking error, stale warning, pagination error, empty state | Presentational typed props/emits |
| `SearchResultMetadata.vue` | Match badge, snippet, model, sampler, seed, library context | Presentational; text interpolation only |
| `useFieldedSearch.ts` | Instance-local parsed query and explicit filter replacement | Accept `MaybeRefOrGetter<string>`; pure computed state |
| `searchQueryGrammar.ts` | Pure tokenizer/parser/serializer | No Vue state and no side effects |

### Required implementation

- [x] Keep the raw query as the single source of truth.
- [x] Parse into residual text, managed filters, and pass-through/unknown tokens.
- [x] Support the backend's single quotes, double quotes, escaping, operators,
      repeated fields, and Unicode behavior.
- [x] Applying Advanced Search replaces managed filters while preserving
      residual and pass-through text. `cat model:pony` must remain a `cat`
      search after adding another filter.
- [x] Remove module-level reactive state and computed getters that write state.
- [x] Use `shallowRef()` for new primitive local state and pure `computed()` for
      derivations; watchers are only for side effects.
- [x] Pass the TanStack Query `AbortSignal` into the API request.
- [x] Deduplicate canonical media by `library_id + asset_id`; use exact,
      case-preserved path only as a compatibility fallback.
- [x] Never lowercase Linux paths. `/A.png` and `/a.png` may be distinct rows.
- [x] Prefer canonical `media`; consume legacy arrays only when `media` is absent.
- [x] Render five search states distinctly:
  1. initial pending;
  2. blocking error with retry;
  3. stale data plus background-error warning;
  4. next-page error with footer retry;
  5. successful empty result.
- [x] Render `match_type`, prompt snippet, model, sampler, seed, and library
      context. Never use `v-html` for snippets.
- [x] While search is active, replace/disable generic gallery sort with a
      visible `Relevance` label. Restore the prior browse sort after clearing.
- [x] Facet requests use the exact same folder/library/all context and query key.
- [x] Expose the existing tool, orientation, availability, and LoRA facets in
      addition to model, sampler, and scheduler.

### Acceptance gates

- [x] Multiple `useFieldedSearch()` instances do not share state.
- [x] Parser/serializer round-trips preserve meaning and residual text.
- [x] Search errors never render as `No results`.
- [x] Retrying a failed next page preserves earlier pages.
- [x] Prompt snippets are HTML-escaped by Vue interpolation.
- [x] Desktop, tablet, and mobile share semantics even when layouts differ.

## H6 - Regression, benchmark, and documentation gates

**Goal:** Turn the audit findings into durable correctness and performance
contracts.

### Required implementation

- [ ] Add one shared JSON grammar fixture under a neutral test-data directory;
      consume it from pytest and Vitest.
- [ ] Extend `scripts/create_perf_fixture.py` with synthetic search rows so the
      managed fixture can seed 5,000 searchable assets without generating
      thousands of expensive image files.
- [ ] Run `scripts/bench_search.py` from the managed `./test.sh perf` flow after
      its fixture backend is healthy.
- [ ] Keep 5,000 rows as the CI profile and support an opt-in 25,000-row local
      or scheduled profile.
- [ ] Extend the benchmark report with broad filename, prompt-heavy,
      album-heavy, fielded, CJK, and repeated keyset-page query classes.
- [ ] Keep the existing lexical search p95 budget at **300 ms**.
- [ ] Add query-plan assertions instead of wall-clock assertions to unit tests.
- [ ] Update the performance budget registry and report summarizer.
- [ ] Update maintained architecture, third-party, testing, and test-catalog docs.

### Final gates

```bash
./test.sh backend-api
./test.sh lint
./test.sh perf
./test.sh docs
./test.sh fast
```

Run the two managed search E2E specs again after the final build. Use
`./test.sh full` before release-style handoff when time and environment permit.

## Completion criteria

- Active-catalog lookup uses indexed library/path ownership.
- Normal search performs no filesystem enumeration or per-result existence checks.
- Strong prompt matches can outrank weak filename matches.
- The active frontend uses opaque keyset cursors.
- API responses and FastAPI signatures are typed.
- Query/filter text is lossless across the Advanced Search drawer.
- Case-sensitive paths remain distinct.
- Search and facet errors have visible retry paths.
- Managed CI exercises the 300 ms search budget.

When complete, move this file to `docs/archived/` and update
`docs/plans/README.md`. Do not leave a completed plan in `docs/plans/`.

## Execution log

| Date | Phase | Result | Evidence |
| --- | --- | --- | --- |
| 2026-07-13 | H0 | Complete | `docs/reports/SEARCH_HARDENING_H0_BASELINE.md`; 157 backend, 77 frontend, and 18 E2E tests passed; deterministic/live p95 stayed below 300 ms. |
| 2026-07-13 | H1 | Complete | Schema v4 ownership backfill and rollback tests; shared predicate remains indexed by `(library_id, path)` and rejects cross-library same-path rows. |
| 2026-07-13 | H2 | Complete | DB-only search joins and browse-shared album aggregation; 82 focused backend tests passed with filesystem hot-path guards and library/import ownership coverage. |
| 2026-07-13 | H3 | Complete | Unified tiered candidate CTE and request-bound opaque keyset cursors; 176 focused search tests plus 9 ranking/cursor goldens passed. |
| 2026-07-13 | H4 | Complete | Typed Pydantic/OpenAPI contracts and shared canonical scope resolver; 7 contract goldens plus 183 focused backend tests and 74 frontend cursor/API tests passed. |
| 2026-07-13 | H5 | Complete | Instance-local lossless query grammar, canonical case-sensitive result merging, scoped facets, five-state search feedback, metadata rendering, and Relevance UI; 164 focused unit tests and 18 managed search E2E tests passed. |
