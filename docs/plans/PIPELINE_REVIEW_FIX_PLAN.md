# Pipeline Review Fix Plan

Status: Active

Created: 2026-11-10

Source: a read-only review of the image pipeline (lightbox, thumbnails, cache) and the search pipeline on `main` @ `c8907e3`,
run under `.agents/skills/audit-closure-protocol/SKILL.md`. The owner approved fixing every finding. The ledger is
frozen at five findings. The search pipeline had no new finding.

## Frozen ledger

| ID | Sev | Invariant | Evidence | Affected surface | Root cause | Acceptance | Verification |
|----|-----|-----------|----------|------------------|------------|------------|--------------|
| PR-01 | Medium | A burst of on-demand derivative requests must not starve unrelated API requests. | Real uvicorn, 6 MP PNG sources, `scope=all` search probe (baseline 8-16 ms). With 32 cold thumbnails in flight the probe took 270-750 ms. With 60 it took 817, 4250 and 829 ms, and the last thumbnail returned after 9.9 s (the wait deadline is 10 s). Script: `scripts/perf/cold_thumbnail_burst.py` (added by the fix from the review's scratch script). | `backend/thumbnails.py` `_serve_derivative` / `wait_for_derivative`; every sync endpoint that shares the thread pool (search, browse). | Each waiting request parks one thread of the shared 40-thread pool for up to 10 s and polls the catalog on a fresh connection up to 20 times a second. This is BL-9. | A waiting derivative request holds no thread-pool thread while it waits. With 60 cold thumbnails in flight, the search probe p95 is at most 300 ms on the review host; report the numbers if a CPU floor prevents that. Status codes, the 10 s deadline, the error mapping, the `source_changed` reschedule and the no-scheduler `run_once` path are unchanged. | A deterministic test: with derivatives that never complete, 50 waiting requests leave a sync endpoint answering promptly. The burst script, before and after. |
| PR-02 | Medium | Lightbox navigation covers the whole album or result set, not only the pages loaded when it opened. | Code path: `stores/lightbox.ts` snapshots `galleryItems` once in `open`; `usePhotoSwipe.ts` builds a fixed-length data source and leaves PhotoSwipe's default `loop: true`; nothing in the lightbox requests another page. Folders load 200 images per page and search 60. At the last loaded item, "next" wraps to the first. | `frontend/src/stores/lightbox.ts`, `composables/usePhotoSwipe.ts`, `utils/lightboxLazyList.ts`, `components/GalleryGrid.vue` (browse and search), `LibraryInspector.vue` where it pages. | The lightbox has no link to the owning infinite query. | Near the end of the loaded items, with more pages available, the lightbox asks the owner for the next page and navigation continues into it, by keyboard, buttons and swipe. It wraps only when every page is loaded. The opening item, index sync, dimensions and the Safari duplicate-image guard are unchanged. A failed page load leaves the lightbox usable on the loaded items. | A Playwright spec with a three-page search stub and a browse stub: walk past the first page, assert the next page is requested and shown, and assert there is no wrap before the last page. Vitest for the store and the growable list. |
| PR-03 | Low | No request handler blocks the event loop on catalog reads or file stats. | Scratch test: with the authorization read slowed by 500 ms, `/api/health` sent 50 ms later completed after 511 ms behind `/api/image`, and after 53 ms behind `/api/thumbnail`. | `backend/images.py` `api_image`. | The handler is `async def` and calls `require_media_path_allowed`, `exists`, `is_file` and `stat` inline. | Authorization and stat run off the event loop. Response bytes, headers, 304 and error codes are unchanged. | A regression test of the measurement above. |
| PR-04 | Low | One definition of "animated image" drives the grid and the lightbox. | Code path: `PhotoCard.vue` treats every `.webp` and `.gif` as animated, so hovering a static WebP for 150 ms downloads the original and shows "PLAYING". `utils/lightbox.ts` treats only `.gif` as animated (`apng` is not an accepted extension), so an animated WebP shows a static first-frame preview until it is zoomed. | `frontend/src/components/PhotoCard.vue`, `utils/lightbox.ts`, the browse, search and related row models, and the backend scan or index path. | Animation is guessed from the file extension in two places, differently. | The backend detects animation from the container header (GIF frames, WebP `ANIM` flag, PNG `acTL`), without a full decode, and exposes it on browse, search and related rows. The grid and the lightbox both use that value. A static WebP never downloads its original on hover. An animated WebP, GIF or APNG animates in the lightbox and on hover. Rows whose value is still unknown behave as static, except `.gif`. A schema change follows the existing migration pattern, with a backup and a bounded backfill. | Unit tests of the detector on small generated files, API tests of the field, Vitest for the card and the lightbox item, and a migration test. |
| PR-05 | Low | Every thumbnail and preview URL of a catalog asset carries its content version, so the browser can keep it without revalidating. | Code path: `LibraryInspector.vue` builds `getThumbnailUrl(path, 128)` with no version, and inspector rows carry no `content_version`. The lightbox opened from the inspector builds unversioned URLs too. | `backend/metadata_store/inspector_store.py`, the inspector response model, `frontend/src/components/LibraryInspector.vue`. | The image-pipeline work versioned browse, search and related rows and left the inspector out. | Inspector rows carry `content_version`. The inspector thumbnail and its lightbox items pass it as `v`, and the responses are immutable. | An API test of the field, and a Vitest or Playwright check that the inspector thumbnail URL carries `v`. |

Out of scope, recorded only: BL-10, BL-11 and BL-17 stay in `BACKLOG.md`.

## Tracks

| Track | Model | Branch | Findings |
|-------|-------|--------|----------|
| L | Sonnet | `fix/pr01-derivative-wait` | PR-01 |
| M | Sonnet | `fix/pr02-lightbox-paging` | PR-02 |
| N | Sonnet | `fix/pr04-animated-detection` | PR-04 |
| O | Haiku | `fix/pr03-pr05-small` | PR-03, PR-05 |

## Rules
- Branch from `fix/pipeline-review`; commit on the track branch; do not push.
- Follow the audit-closure protocol for each finding:
  - reproduce the recorded failure;
  - add a failing regression test;
  - apply the smallest complete root-cause fix;
  - run the focused test and the directly affected suites.
- Stay inside the finding. Record anything else you notice as a note for the hand-back; do not fix it.
- Never weaken tests, fixtures or budgets. Report every pre-existing test you edit, with the reason.
- Update the maintained docs the change touches (`docs/ARCHITECTURE.md`, `docs/UI_UX_GUIDELINES.md`,
  `docs/CONFIGURATION.md`, `docs/testing/TEST_CATALOG.md`, `docs/testing/PERFORMANCE_TESTING.md`), and mark BL-9 done
  in `BACKLOG.md` if PR-01 closes it.
- Checks:
  - backend tracks: targeted pytest, the full backend pytest in both modes, and `./test.sh backend-api`;
  - frontend tracks: `corepack pnpm run typecheck`, `corepack pnpm run test:unit`, and the relevant Playwright specs;
  - every track: `./test.sh lint` and `./test.sh docs`.

## Review gates
1. Read each diff, rerun the evidence, and check every acceptance item against the frozen ledger.
2. Merge the tracks, then run `./test.sh fast`, `./test.sh e2e` and `./test.sh perf`.
3. Publish one closure row per finding. Open the PR and merge once CI is green. The VPS deploy needs the owner's word in
   the VPS session.

## Progress

| Finding | Status | Evidence |
|---------|--------|----------|
| PR-01 | Pending | |
| PR-02 | Pending | |
| PR-03 | Pending | |
| PR-04 | Pending | |
| PR-05 | Pending | |
