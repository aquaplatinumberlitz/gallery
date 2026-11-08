# UX Review Fix Plan

Status: Active

Created: 2026-11-08

Source: a direct (Opus) UI/UX and pipeline review on `main` @ `796b17b`, done on
2026-11-08 with a 333-image AI-metadata fixture. It covered the 390, 768, 844x390,
1024 and 1440 viewports in light and dark themes. The owner approved every finding
and UX suggestion below. Evidence (screenshots and measurements) is in the session
scratchpad. Each track re-establishes its own fail-before.

## Findings

| ID | Sev | Problem | Evidence and root cause | Acceptance |
|----|-----|---------|-------------------------|------------|
| LP-01 | Medium | The landing page day/night toggle waits a fixed 250 ms, then reloads the whole iframe page. The scene blanks and the animations restart. Measured locally with a warm cache: 0.32-0.36 s desktop, 0.41-0.56 s 4G, 0.48-0.76 s slow 4G. In production, nginx `location /` sends `no-cache`, so every reload also revalidates about 22 files. | `frontend/public/landpage/{normal_angel,normal_mouse}/assets/js/script.js` (theme toggle calls `location.reload()`); `frontend/gallery-nginx-prod.conf` (no `/landpage/` location) | The theme switches in place with no reload and no 250 ms wait; visible feedback within 100 ms. "Back to auto" stays available without delaying a single click. The scenes look the same. `/landpage/` assets are cacheable. |
| LP-02 | Low | Automatic intro mode picks the birthday, Noel, Lunar and New Year pages and the developer `sample_test` page on ordinary days. | `IntroScreen.vue:68-70` picks randomly from all 8 pages that `/api/landing-pages` lists (`backend/static_files.py:23-40`) | Ordinary days pick only ordinary themes; seasonal pages only on their dates; `sample_test` is never picked or shipped. |
| LP-03 | Low | `frontend/public/landpage/doraemon theme_refactored.zip` (5.9 MB) and `sample_test` are copied into `dist` and served publicly. | `frontend/public/landpage/` | Neither is in the build output. |
| SR-01 | Medium | Prompt search cannot match CJK words of 1-2 characters (少女, 東京, 夜景) or Latin queries of 1-2 letters ("ch"). Any query that mixes such a word with others returns 0. Measured counts: 少女 0, 東京 0, 桜の 0, 桜の下 10, "ch" 0, "che" 291. | `backend/metadata_store/ranked_search.py:91-96`: trigram is used only for 3+ characters. Shorter queries use the exact-token `_unicode_match_query`, and unicode61 keeps an unspaced CJK run as one token. Filenames already use token prefix. | A 1-2 character CJK word matches prompts that contain it. A 1-2 letter Latin query prefix-matches prompt tokens. Mixed queries keep AND semantics. The `search-benchmark` budgets still pass (p95 ≤ 300 ms on the 100k fixture). |
| SR-02 | Low | The search results header shows how many results are loaded (60), not the total (237). The Advanced Search drawer shows "237+ matches". | `frontend/src/components/search/SearchResultsPanelImpl.vue:155` (`count: props.media.length`) | The header shows the total from the count query, with the same "+" convention as the drawer, and falls back to the loaded count while the total is pending. |
| MD-01 | Medium | Album covers can be unreadable files. The Landscapes album shows broken-image covers on the home page, on desktop and mobile. | Folder cover selection in `backend/metadata_store/browse_store.py` (cover query) does not skip assets whose metadata or derivatives failed. | Covers skip assets with failed metadata or terminal-failed derivatives. A folder whose only images are unreadable shows the empty-cover placeholder. |
| MD-02 | Low | The desktop toolbar "View" density button is clipped to "Vi…" at every desktop width. | `frontend/src/components/AppHeader.vue:486` (and `:636`): fixed `w-[74px]` | The label shows in full at 1024 and 1440 in light and dark, with no layout shift. |
| LC-01 | Medium | After PR #13, one unreadable file makes the library page show the Metadata stage as a red "✗ Failed" (331/333 ready), while the badge next to it says "Ready with issues". | `backend/metadata_store/status_store.py:451-452` (any failed asset sets the stage to `failed`) and the frontend stage label | When some assets are ready, the stage reads as an amber "Ready with issues" with "N ready · M can't be read". Red "Failed" is kept for a stage with no ready assets. The API contract stays compatible, or the docs and both sides change together. |

## Approved UX suggestions

| ID | Change | Acceptance |
|----|--------|------------|
| UX-1 | Phone landscape (`max-height: 500px`): compact the lightbox metadata panel header (filename and chips on one short row), so at least about 120 px of metadata shows in the 50dvh panel. | Screenshot at 844x390 shows the generation data and the start of the prompt without scrolling. |
| UX-2 | The breadcrumb starts at the library root, like the folder tree, not at the filesystem root (`tmp › … › data › library`). | Desktop, tablet and mobile breadcrumbs start with the library (or import-root) name. Navigation, the overflow menu and back/forward still work. |
| UX-3 | A folder that contains only subfolders gets covers from its descendants (for example Portraits, Sketches). | These album cards show up to 3 descendant covers, bounded and indexed, with no N+1 queries. |
| UX-4 | The folder tree shows "No subfolders" instead of "(Empty)" for a folder with media but no subfolders. | Copy updated; an empty folder still reads as empty. |
| UX-5 | The landing pages load only the assets of the scene that is shown (for example the night-only `mood.webp`, 143 KB, is not fetched by day), without visible change. | Day load does not fetch night-only images and vice versa. Measured bytes before and after. |

## Tracks

| Track | Model | Branch | Items |
|-------|-------|--------|-------|
| A | Sonnet | `fix/ux-search` | SR-01, SR-02 |
| B | Sonnet | `fix/ux-landing` | LP-01, LP-02, LP-03, UX-5 |
| C | Sonnet | `fix/ux-covers` | MD-01, UX-3 |
| D | Haiku | `fix/ux-frontend` | LC-01, MD-02, UX-1, UX-2, UX-4 |

## Rules
- Branch from `fix/ux-review`; commit on your track branch; do not push.
- Reproduce each finding first, add a failing regression test, then fix. Record the fail-before output.
- Never weaken tests. Report every pre-existing test you edit, with the reason.
- For any visible change, take before/after screenshots at 390, 768, 844x390, 1024 and 1440 (light and dark where relevant) and look at them yourself.
- Update maintained docs, `docs/UI_UX_GUIDELINES.md` where a UI rule changes, and `docs/testing/TEST_CATALOG.md`.
- Checks:
  - targeted tests;
  - `./test.sh lint`;
  - `./test.sh docs`;
  - `cd frontend && corepack pnpm run test:unit` for frontend work;
  - `./test.sh backend-api` for route changes;
  - the relevant Playwright specs;
  - for track A, the search benchmark.

## Review gates (Opus)
1. Read each diff, rerun the regression tests, and check every acceptance item.
2. Merge all tracks, then run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`.
3. Get the owner's approval for the PR and the deploy. The deploy also needs the in-place nginx `/landpage/` cache block on the VPS.

## Progress

| Track | Status | Evidence |
|-------|--------|----------|
| A | Pending | |
| B | Pending | |
| C | Pending | |
| D | Pending | |
