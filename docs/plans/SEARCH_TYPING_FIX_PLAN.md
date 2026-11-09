# Search-As-You-Type Fix Plan

Status: Active

Created: 2026-11-09

Source: a direct (Opus) review of search-as-you-type on `main` @ `f27f610`, done on
2026-11-09. It used the production build and the 333-image fixture. Key-by-key UI logs
were sampled every 40 ms, plus API counts per prefix, Japanese IME simulation through
CDP `Input.imeSetComposition`, and SQLite tokenizer probes. The owner approved every
item below, including the optional normalization work.

## Findings

| ID | Sev | Problem | Evidence and root cause | Acceptance |
|----|-----|---------|-------------------------|------------|
| SE-01 | Medium | On every keystroke after results are shown, they disappear: the folder view and the "Keep typing" hint return for about 650 ms, then a skeleton, then the new results. | UI log for "night": `SEARCHPANEL -> HINT BROWSE -> skeleton -> SEARCHPANEL` at each key. `useUnifiedSearchQuery.ts` returns `EMPTY_SEARCH_RESULTS` while `trimmed != debounced` and keeps no previous data. `GalleryGrid.vue:195-200` (`hasSearchQuery`) is false while the query settles, so the grid falls back to browse. | Once a search is showing, typing more keeps the previous results visible (dimmed, with the existing loading indicator) until the new page arrives. There is no browse view, hint or skeleton in between. Clearing the box, or going below the minimum without Enter, still returns to browse. |
| SE-02 | Medium | The debounce is 650 ms although the API answers in 15-50 ms (p95 at most 250 ms on 100k). Enter does not skip the debounce: the request leaves about 600 ms after Enter. | `constants.ts:4`. `galleryStore.submitSearch()` only sets `submittedSearchQuery`; `useUnifiedSearchQuery` still waits for `refDebounced`. | Debounce is 250 ms (one constant, shared with the drawer preview). Enter sends the request at once (under 50 ms after the key). Fast typing still sends one request per pause. |
| SE-05 | Low | Enter fires an extra `/api/search/count` with empty text. | Log: `REQ search/count ""` right after Enter. `GalleryGrid.vue:203-208` builds the count request from the stale settled text (added by SR-02). | No count request with empty or stale text. |
| CJ-01 | Medium | Uncommitted IME text is searched. Typing さくら to convert to 桜 with pauses sends `さk`, `さく`, `さくr`, `さくら` before 桜, so each one flashes results. | CDP IME log; `searchQuery` is `"さく"` mid-composition. Desktop: `components/ui/input/Input.vue` (the v-model composition guard is not active: `el.composing` is undefined, and `input` events arrive with `isComposing=true`). Mobile: `MobileHeader.vue:118` uses a raw `@input`. | While composing, the query does not change. It updates on `compositionend` with the committed text. This holds on desktop, tablet and mobile inputs. |
| CJ-02 | Medium | The Enter that confirms an IME candidate is treated as submit. On mobile it also blurs the input, which closes the keyboard and commits the raw kana. | Mobile value became `桜しょうじょ少女` and the input lost focus. `MobileHeader.vue:91-93`, `HeaderSearchBox.vue:40`. | Enter with `isComposing` (or `keyCode 229`) neither submits nor blurs. A plain Enter after composition still submits. |
| SE-03 | Medium | Matching changes at 3 characters: 1-2 characters match the start of a word, 3 or more match a substring anywhere. Typing more can therefore give more results, and the top results jump. | API: `o` 323, `or` 0, `ort` 286. `mi` matches only words starting with "mi", while `mik` also matches "ka**mik**aze". `ranked_search.py:91-96` (`_can_use_trigram_candidates`) and `_short_match_params`. | Word-prefix matching is the first relevance tier at every length, for prompts, filenames and model/sampler. Substring (trigram) matches, at 3 or more characters, rank below every prefix match. For a Latin query q and its extension q+c, the prefix-tier results of q+c are a subset of those of q, and the top results stay stable from `mi` to `mika`. CJK keeps its substring semantics, which are already monotonic. AND semantics, keyset paging and the count stay consistent with the page results. |
| SE-04 | Medium | Accent-insensitive search is inconsistent and fails for Vietnamese. `ca` and `caf` match "café", but `cafe` returns 0. `noi` does not find "Hà Nội", and `pho` does not find "Phố". | SQLite probe: the `trigram` tokenizer keeps diacritics by default, and `unicode61` (default `remove_diacritics 1`) does not fold characters with two marks (ộ, ố). `đ` is a separate letter. Tokenizers are in `_schema_ddl.py` and `_schema_ensure.py`. | Queries and indexed text are folded the same way: case, all combining marks (including Vietnamese stacked marks), `đ/Đ` to `d`, NFKC (full-width and half-width forms), and katakana to hiragana. `cafe`/`café`, `noi`/`Nội`, `pho`/`Phố`, `ﾈｵﾝ`/`ネオン`/`ねおん` each match both ways. Display text (names, prompts, snippets) is unchanged. |

## Advanced Search additions (2026-11-09)

The owner asked whether these fixes also apply to Advanced Search. They gave Opus full authority to decide.

- **Fielded "contains" filters** (`prompt:`, `negative:`, `name:`, `sampler:`, `model:`; `fielded_search_parser.py`) use `LIKE '%value%'`. That folds only ASCII case. Probe: `cafe`, `CAFÉ`, `noi` and `ねおん` each return 0 against "café", "Nội" and "ネオン".
  - Track F applies the same normalization to these filters.
  - They keep "contains" semantics, which are already consistent at every length.
- **IME and debounce in the drawer.** Track E covers drawer inputs, the jump field's Enter and the match-preview request.

| ID | Sev | Problem | Acceptance | Track |
|----|-----|---------|------------|-------|
| AV-01 | Medium | At 768 px the drawer is about 322 px wide (`min(640px, 42vw)`). Its footer overlaps ("Revert e[Clear]all"), and Cancel is not visible. | All footer actions are fully visible from 390 to 1440 px. No overlap, clipping or horizontal overflow. Touch targets are at least 44 px. | E |
| AV-02 | Low | At 1440 px the status "Unsaved changes" is truncated to "Unsaved …". | Shown in full or wrapped. | E |
| AV-03 | UX (layout change, owner approved) | When the drawer opens, Recent searches and the 9-group Indexed facets table push the filters below the fold: about 1 screen on desktop and about 3 on mobile. | Filters come first. Recent searches (open when it has entries) and Indexed facets (collapsed, with a count) follow as accordions. Facet chips still apply filters. `#advanced-search-prompt` is visible on open at 390x844 and 1440x900. | E |

## Tracks

| Track | Model | Branch | Items |
|-------|-------|--------|-------|
| E | Haiku | `fix/search-typing-frontend` | SE-01, SE-02, SE-05, CJ-01, CJ-02, AV-01, AV-02, AV-03 |
| F | Sonnet | `fix/search-typing-backend` | SE-03, SE-04 (with NFKC and kana folding, also for fielded filters) |

## Track F constraints
- **Schema.** This is schema v14 with the usual pre-migration backup (`.v13.bak`). Backfill comes from stored text only, with no media decoding. The backfill must stream rows, never load them all at once.
- **SQLite version.** The design must not depend on the SQLite version: the VPS version is unknown, and `trigram remove_diacritics` needs 3.45. Prefer one Python normalization function, applied both to indexed text and to queries.
- **Storage.** Avoid storing a second full copy of every prompt where an index-only (contentless or external) table works. Measure the database size before and after on the 100k perf fixture and report it.
- **Writers.** Every path that writes prompt or filename search text must keep the folded index in step, as `cjk_index.sync_cjk_path` does today. Deletes and reused ids must not leave stale rows.
- **Budgets.** The `search-benchmark` budgets still pass (p95 at most 300 ms on 100k). Add workloads for prefix-stability and accent-folded queries. Record the migration time on the 100k fixture.

## Rules
- Branch from `fix/search-typing`; commit on your track branch; do not push.
- Reproduce each finding first and add a failing regression test, then fix. Record the fail-before output.
- Never weaken tests. Report every pre-existing test you edit, with the reason.
- **UI evidence.** Take key-by-key UI logs before and after with the review harness scripts, which run against a production build served by `scripts/perf/web_vitals/serve_dist.cjs`:
  - `typing.cjs` (Latin typing; `WORD`, `GAP` env);
  - `typing2.cjs` (`\n` presses Enter);
  - `ime.cjs` (IME; `MOBILE=1` for the phone layout).
  - They live in `/tmp/claude-0/-home-user-gallery/7ef502ed-3644-56aa-b068-4cbda454f8d3/scratchpad/integ/`. Copy them; do not edit them in place.
- **Screenshots.** For any visible change, take before/after screenshots at 390, 768 and 1440.
- **Docs.** Update maintained docs (`docs/ARCHITECTURE.md` search sections, `docs/UI_UX_GUIDELINES.md` search rules, `docs/METADATA_PARSING.md` if indexing changes) and `docs/testing/TEST_CATALOG.md`.
- **Checks.**
  - Targeted tests.
  - `./test.sh lint` and `./test.sh docs`.
  - `cd frontend && corepack pnpm run test:unit` for frontend work.
  - `./test.sh backend-api` for route changes.
  - The search Playwright specs.
  - For track F, the search benchmark.

## Review gates (Opus)
1. Read each diff, rerun the regression tests and the typing/IME logs, and check every acceptance item.
2. Merge both tracks, then run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`, and a real v13 to v14 migration on a copy.
3. Get the owner's approval for the PR and the deploy.

## Progress

| Track | Status | Evidence |
|-------|--------|----------|
| E | Merged after Opus review | Opus logs on the production build:
- Typing "night" at 1.2 s gaps: no browse, hint or skeleton between keys, and the header holds "298+". The flash to "60" was traced to vue-query's `hasNextPage` lagging behind `data` and fixed.
- Enter sends the query about 21 ms after the key, with no empty count request.
- IME, desktop and mobile: no request for uncommitted kana. The candidate Enter keeps focus and commits 桜少女.
- Drawer: filters come first, and the footer fits at 768 and 1440. |
| F | Merged after Opus review | 47 new tests: 36 failed before the fix. Prefix-first tiers. `fold_text` (NFKC, casefold, marks, đ, kana) is applied to free-text and fielded filters.
- Schema v14: a real v13 copy migrated cleanly (`.v13.bak`, 331 metadata and 344 file fold rows).
- 100k benchmark: all workloads at or under 300 ms p95. `prompt:ca` dropped from 649 to 71 ms.
- DB size +8.7% on the 100k fixture; the migration takes 14 s.
- Full backend suite: 1791 passed in both modes. |
