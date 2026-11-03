# Pipeline Audit Fix Plan

Status: Active

Created: 2026-11-03

Source: read-only audit of the catalog, metadata and derivative pipeline on
`main` @ `7b251d0` (2026-11-03), run under
`.agents/skills/audit-closure-protocol/SKILL.md`. Five repro tests were run
again independently: CP-01 (both tests), CP-02, CP-03 and CP-04 fail on
`main` as recorded.

The owner approved the scope below on 2026-11-03. CP-03 uses option (a).

## Frozen finding ledger (7)

| ID | Sev | Invariant | Evidence | Root cause | Acceptance |
|----|-----|-----------|----------|------------|------------|
| CP-01 | High | A rebuilt catalog serves the same API contracts as a scanned one (`SearchMediaResult.mtime: float`) | After `POST /api/maintenance/imported-data/rebuild`, `POST /api/search/query` and `GET /api/search` return 500 (`mtime` None) | `activate_rebuild_staging` writes `file_index.mtime` as literal `NULL` (`backend/metadata_store/rebuild_store.py:250`) | After a rebuild, `file_index.mtime` is non-NULL for every row; filename search returns 200 with correct order; regression test |
| CP-02 | Medium | The catalog records video `duration_ms`, `codec`, `width`, `height` (scan: `file_index.py:491-527`) | After a rebuild these are all NULL; scan gives `64x48, 2000 ms, h264` | The rebuild staging walker has no ffprobe step (`rebuild_store.py:94-171`) | After a rebuild, video rows equal a scan of the same file; regression test |
| CP-03 | Medium | `ARCHITECTURE.md:102`: "Parse and format errors (unreadable image ...) fail immediately" | An unreadable or corrupt PNG completes its metadata job as `done` with an empty `Unknown` row; status shows 0 failed | `extract_metadata` swallows `UnidentifiedImageError`/`OSError` (`metadata_extract.py:938-941`) | Option (a): unreadable image yields a `failed` job and asset state visible in the failed counts; the lightbox shows a clear "cannot read this file" state, not a crash or a blank panel; transient errors keep the retry path |
| CP-04 | Low | A succeeded catalog job does not leave the library in progress | Full scan then watcher-scoped scan gives `['ready','indexing']` | `scan_worker.py:422,569` set `indexing` whenever the scan was scoped | After a scoped scan, a previously `ready` library stays `ready`; a never fully scanned one may stay `indexing` |
| CP-05 | Low | `GET /api/video/poster` serves a poster for a cataloged video | Clips of 0.5 s and 1.0 s return 422 `video_poster_failed` | Fixed `-ss 1` seek (`video.py:262-267`), no fallback | A clip of ≤ 1 s returns a poster (first-frame fallback); test |
| CP-06 | Low | Maintained docs match code | (a) `ARCHITECTURE.md:645` omits edge 256; (b) `ARCHITECTURE.md:1055,1065` query keys outdated vs `keys.ts`; (c) `METADATA_PARSING.md:62` LRU key omits sidecar identity; (d) scan-time video ffprobe undocumented | Doc drift | The four statements are corrected |
| CP-07 | Low | UI and docs describe real ordering | `MaintenancePipelineFlow.vue` arrows and copy plus `docs/README.md` main flow imply a strict, eager 1→2→3 chain | Real shape is 1 → (2 ‖ 3); 3 is eager only with the warm policy, otherwise on first view | Copy and README updated (below) |

## Approved improvements (same pass)

| ID | Item | Acceptance |
|----|------|------------|
| IM-1 | One shared catalog record writer for scan and rebuild (root cause of CP-01/CP-02) | Scan and rebuild build `file_index`/`assets` rows through the same code path; a parity test compares the two for an image, a video and a folder |
| IM-2 | Frontend metadata query key includes `content_version` | Key is `["metadata", path, contentVersion]` (or equivalent) at every call site (`usePhotoMetadataQuery`, `usePhotoSwipe` dimension reads); a changed version refetches; unchanged keeps the 10 min cache |
| IM-3 | Remove the dead staged metadata queue (always 0) | UI row, API field, status plumbing and legacy env vars removed together; docs updated; no API consumer left reading it |
| IM-4 | Auto-build the `prompt_values` and `workflow_properties` search indexes | Measure the backfill on a 10k-image synthetic library first. If cheap, schedule it automatically once a library's metadata completes (`workflow_raw` stays opt-in), and show the index state as an unnumbered note under the pipeline. If not cheap, show state plus a build action only, and report |

Pipeline copy (CP-07):
1. File catalog: "Finds images and videos in your libraries"
2. Metadata extraction: "Reads prompts and settings from images"
3. Image cache: "Builds thumbnails and previews, ahead of time or on first view"

Add the note: "Steps 2 and 3 start once files are cataloged and run side by side."

## Tracks

| Track | Model | Branch | Items | Main files |
|-------|-------|--------|-------|------------|
| S1 | Sonnet | `fix/pa-rebuild` | CP-01, CP-02, IM-1 | `metadata_store/rebuild_store.py`, `file_index.py`, rebuild path in `scan_worker.py` |
| S2 | Sonnet | `fix/pa-metadata` | CP-03, IM-4, CP-07 | `metadata_extract.py`, `indexer.py` (job completion), `search_indexer.py`, Lightbox metadata panel, `MaintenancePipelineFlow.vue`, `docs/README.md` |
| H1 | Haiku | `fix/pa-small` | CP-04, CP-05, IM-3 | `scan_worker.py:422,569`, `video.py`, staged-queue fields (`indexer.py:209`, `status_store.py:909`, `MaintenancePage.vue`), `CONFIGURATION.md` |
| H2 | Haiku | `fix/pa-docs-key` | CP-06, IM-2 | `ARCHITECTURE.md`, `METADATA_PARSING.md`, `usePhotoMetadataQuery.ts`, `usePhotoSwipe.ts`, `Lightbox.vue`, `queries/keys.ts` |

## Rules (all tracks)

- Branch from `fix/pipeline-audit`. Commit on your track branch; do not push.
- For each finding: reproduce first, write a failing regression test, apply the smallest root-cause fix, then run the focused test and the affected suites. Record the fail-before output.
- Never weaken a test, budget or validation to get green. Report every edit to a pre-existing test, with the reason.
- Stay inside your files. If you must touch another track's file, keep the edit minimal and say so in the report.
- Update maintained docs and `docs/testing/TEST_CATALOG.md` for changed behaviour or new test files.
- Checks before reporting:
  - targeted pytest or Vitest;
  - `./test.sh backend-api` for route contracts;
  - `./test.sh lint`;
  - `./test.sh docs`;
  - the relevant Playwright spec for UI changes.

## Review gates (Opus)

1. Per track: read the diff, rerun the regression tests (fail on `fix/pipeline-audit`, pass on the track), and check the acceptance criteria above.
2. After merging all tracks: `./test.sh fast`, `./test.sh backend-api`, `./test.sh e2e`, and the CP repro tests.
3. A direct Opus review of the whole metadata/thumbnail caching pipeline code, then an updated assessment for the owner.

## Backlog (out of scope, recorded only)

| ID | Item | Why deferred |
|----|------|--------------|
| BL-1 | Video poster cache has no supersede cleanup (`video.py`) | Bounded by the 1 GiB LRU; a changed file gets a new key, so no wrong poster is shown |
| BL-2 | `mtime` unit differs: browse emits `mtime_ns`, search/inspector emit seconds (`models.py:26`) | The frontend only sorts within one response |
| BL-3 | 409 message "Image changed while its derivative was generated" is misleading for a changed-but-unscanned file; the frontend retry is status-blind | The watcher heals within about 2 s; only lasting with watcher and scheduled refresh both off |
| BL-4 | `parse_metadata` holds `_metadata_cache_lock` across the DB read (`metadata_parse.py:90-98`) | Serializes concurrent cold requests; not measured |
| BL-5 | Scan holds all records in memory before the first write and runs ffprobe serially (`file_index.py:424,491-508,555`) | Measure on a large library before changing |
| BL-6 | Offline assets keep ready derivatives; a move is delete + create (re-extract, re-render) | Correct but wasteful; no user-visible error |
| BL-7 | `visual_fingerprints` showed `skipped_count 4` with skip reasons summing to 2 | Unexplained; needs a repro |

## Progress

| Track | Status | Evidence |
|-------|--------|----------|
| S1 | Pending | |
| S2 | Pending | |
| H1 | Pending | |
| H2 | Pending | |
