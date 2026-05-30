# Audit & Cleanup: Dead Code After PhotoSwipe Migration

Project at /home/ubuntu/gallery-repo/frontend/
Git ready (latest commit: dedab16, includes PS5 migration + breakpoint cleanup).

## CRITICAL RULES
- DO NOT delete code blindly.
- First inspect, classify, and report.
- Only remove items that are clearly unused and safe.
- If uncertain, mark as suspicious and ask before deleting.
- DO NOT delete PhotoSwipeViewer.vue, LightboxMobileSheet.vue, copy/clipboard fallback, breakpoint mixins, external PhotoSwipe CSS
- DO NOT delete anything dynamically referenced unless verified
- DO NOT delete anything needed by desktop lightbox/sidebar/metadata
- DO NOT install new npm packages (like knip) without asking

## Context
- PhotoSwipe 5 replaced old custom 3-slide lightbox track
- Lightbox.vue was reduced from ~1045 to ~500 lines
- PhotoSwipeViewer.vue created as shared PS5 wrapper
- Breakpoints standardized: compact<480, mobile<768, tablet 768–1199, desktop>=1200, wide>=1440
- _breakpoints.scss added
- Old 1024px breakpoint rules removed
- AlbumScroller now uses useDevice
- phone→mobile rename done

## Tasks

### A. Run existing checks
Run:
1. `npx vite build` — report pass/fail
2. If vue-tsc exists: `npx vue-tsc --noEmit` — report pass/fail
3. If lint script exists: run lint
4. If test script exists: run test

### B. Dead code scan
Search ALL .vue, .ts, .js, .scss files in src/ for these stale names:

Old lightbox track:
- lightbox-track
- trackOffset
- isResettingSlide
- handleSwipeStart
- handleSwipeMove
- handleSwipeEnd
- resetTrackPosition
- preloadAdjacent
- preloadExtended
- slot-prev, slot-current, slot-next

Old device/breakpoint:
- max-width: 1024px (as tablet breakpoint)
- min-width: 1025px
- isPhone (as exported/computed name)
- BREAKPOINTS.phone

For each match, classify: active-needed / legacy-referenced / dead-safe / suspicious

### C. Component reachability
List all .vue files in src/components/
For each, report if it's imported by another file.
Check specifically:
- MobilePhotoSwipe.vue — is it still imported? (was replaced by PhotoSwipeViewer for desktop/tablet but still used for mobile)
- PhotoSwipeViewer.vue — is it imported in Lightbox.vue?

### D. Unused imports scan
Manually check these files for imports that are no longer used:
- src/components/Lightbox.vue
- src/components/PhotoSwipeViewer.vue
- src/components/MobilePhotoSwipe.vue
- src/composables/useDevice.ts
- src/composables/useColumnResize.ts
- src/components/AlbumScroller.vue
- src/App.vue
- src/styles/main.scss

### E. SCSS dead selector audit
Search for these old selectors:
- .lightbox-track
- .lightbox-slide
- .lightbox-dismiss-wrapper
- .is-swiping
- .is-resetting
- .hero-image
- .lightbox-shell
- .lightbox-left
- .image-loading
- .is-dismiss-snapping
- .is-animating

For each: does it appear in any .vue template or runtime class binding?
If not, mark as dead CSS candidate.

### F. Breakpoint consistency re-check
Verify:
- No max-width: 1024px used as tablet breakpoint
- No min-width: 1025px
- No docs saying tablet 768–1024 or desktop >1024
- No separate matchMedia mobile detection

### G. Dependency audit
Check package.json:
- Is photoswipe dependency present?
- Any old/swipe libraries still installed?

## Final deliverables
1. Report: dead code candidates found
2. Report: safe removals
3. Report: suspicious items needing approval
4. Build/test results

If safe removals are obvious (clearly unused CSS, unused imports, dead comments, etc.), implement them:
- Remove dead imports
- Remove dead CSS selectors
- Remove dead code blocks
- Update stale comments
- Run build again to verify
- Report final diff summary

## Output format
Use this structure for the report:
```
## [Category]
### [File] — [Finding type]
- Location: line X
- Status: dead/safe/active/suspicious
- Action: remove/keep/review
- Note: ...
```
