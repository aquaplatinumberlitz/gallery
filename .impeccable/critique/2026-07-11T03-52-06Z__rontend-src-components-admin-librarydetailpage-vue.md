---
target: /admin/libraries/19 — Overview, Status, Generated images
total_score: 24
p0_count: 0
p1_count: 2
timestamp: 2026-07-11T03-52-06Z
slug: rontend-src-components-admin-librarydetailpage-vue
---
# UI/UX critique — Library detail cards

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of system status | 3/4 | Badge, progress and refresh feedback are present, but query failures can look like endless loading. |
| 2 | Match system / real world | 3/4 | Most labels are clear; cache terms such as deferred, units and generated images need clearer user impact. |
| 3 | User control and freedom | 2/4 | Refresh and back actions exist, but queued updates/generation have no visible cancellation path. |
| 4 | Consistency and standards | 3/4 | Component vocabulary is consistent; Ready/All systems available conflicts with 2 unavailable files. |
| 5 | Error prevention | 2/4 | Generate missing images does not explain storage or queue impact clearly enough. |
| 6 | Recognition rather than recall | 3/4 | Labels are visible, but users must mentally reconcile Overview and Status. |
| 7 | Flexibility and efficiency | 2/4 | Section refresh exists, but there is no direct path from an issue count to affected files. |
| 8 | Aesthetic and minimalist design | 3/4 | Calm and readable, but nested borders and always-visible zero counters add noise. |
| 9 | Error recovery | 2/4 | Warnings exist, but worker/query failures lack a concrete recovery path. |
| 10 | Help and documentation | 1/4 | Only local tooltips explain file/cache semantics. |
| **Total** |  | **24/40** | **Acceptable — meaningful improvements needed** |

## Anti-patterns verdict

The page does not strongly look AI-generated. It uses a familiar, restrained shadcn-vue product vocabulary. The main template-like trait is repeated card-inside-card composition: four identical Overview metrics, three Status tiles, derivative rows, and three Generated images tiles all carry similar visual weight.

The source detector returned 0 findings. The live DOM overlay reported nested-card signals across Overview, Status, and Generated images. Its other shell-level findings were false positives or outside the target: gradient text, dark glow, violet palette, flat product typography, app overflow, and layout transitions. The useful overlap is the repeated bordered groups inside bordered parent cards.

## Overall impression

The foundation is calm, technical, responsive, and trustworthy at first glance. The biggest opportunity is to make health semantics internally consistent and collapse non-actionable cache detail so the user can understand the library in five seconds.

## What's working

- Clear page order: identity and actions, Overview, then operational Status and Generated images.
- State is conveyed through icon, text, and color together; numeric data uses tabular figures.
- Skeletons, refresh feedback, tooltips, responsive stacking, and accessible refresh labels are already present.

## Priority issues

### [P1] Ready contradicts unavailable files

Overview shows 208 available and 2 unavailable, while the header and Status say Ready and All systems available. For a filesystem tool, this undermines trust.

Fix: separate Source folders from Catalog coverage. If offline assets exist, use a warning summary such as Library available — 2 cataloged files unavailable. Reserve Ready for Ready to browse, not No issues.

Suggested command: `$impeccable clarify`.

### [P1] Query errors can masquerade as infinite loading

Overview and Generated images distinguish data from no data, but an error also falls through to a skeleton. Users cannot tell whether to wait or retry.

Fix: implement pending, stale-data, error, and unmeasured states separately. Keep last-known values when possible, show Try again and the last update time, and place errors inside the affected card.

Suggested command: `$impeccable harden`.

### [P2] Generated images is too dense when healthy

Two complete progress bars, eight zero counters, three tiles, and explanatory copy repeat the same healthy conclusion.

Fix: default to Thumbnails 208/208 and Previews 208/208. Reveal queued/running/failed/deferred only when non-zero or under Details. Combine cache usage into one line and move On demand to a header badge with Created on first view.

Suggested command: `$impeccable distill`.

### [P2] Visual hierarchy does not reflect importance

Overview metrics are visually flat, while Status and Generated images use many nested borders with nearly equal emphasis. The two desktop cards stretch to the same row height even when Status has less content.

Fix: use a divided metric strip for Overview; emphasize values over labels and highlight unavailable. Let Status and Generated images size to content or stack them. When there is an issue, let Status span full width and lead.

Suggested command: `$impeccable layout`.

### [P2] Actions do not explain consequences or recovery

Generate missing images may queue work and consume storage, but the CTA is generic. Worker unavailable describes the failure without giving a next step. Small icon refresh targets are also weak for touch.

Fix: use policy-aware copy such as Prepare 51 images now, state storage/job impact, show queued count and progress after action, link worker failure to Maintenance, and use at least 44×44px touch targets on coarse pointers.

Suggested command: `$impeccable clarify`.

## Persona red flags

- Alex, power user: must scan many green tiles and zero counters but cannot jump from 2 unavailable to affected files; no refetch-all or compact issue path.
- Sam, accessibility-dependent: heading and definition-list structure are good, but async refresh/queue changes need aria-live feedback, progress needs an accessible name, and the file tooltip must not be the only explanation.
- Riley, stress tester: will immediately find Ready versus 2 unavailable, 0/0 cached ambiguity, errors rendered as skeletons, and worker failure without recovery.

## Minor observations

- Clarify whether Photos includes every image format; Images may be more accurate.
- Storage in Overview appears to mean source media while storage in Generated images means cache; qualify both labels.
- A full progress bar at 100% adds little; show progress primarily during incomplete work.
- All systems available is too absolute; Library is ready to browse is safer and more precise.

## Questions to consider

- If Ready does not mean every cataloged file is available, should it remain the highest overall state?
- Is the primary purpose of this page health diagnosis or cache management, and which card should answer that within five seconds?
- When every queue counter is zero, why does that information occupy more space than the two unavailable files that need attention?
