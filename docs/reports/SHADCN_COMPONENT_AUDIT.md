# shadcn-vue Component Audit — 2026-06-14

Status: Audit snapshot; verify findings against current components before implementation.

Audit scope: `frontend/src/components/ui/`

This report records the findings from the shadcn-vue component audit completed on 2026-06-14. The comparison target is the official shadcn-vue component implementation for each audited component.

## Summary

| Component       | Status | Quick note                                                                                                                                  |
| --------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `dialog`        | ✅     | Matches official shadcn-vue across all 9 component files plus `index.ts`; `DialogClose` is present.                                         |
| `dropdown-menu` | ✅     | Matches official shadcn-vue across all 14 component files plus `index.ts`; Reka imports, animations, and portal export match.               |
| `popover`       | ✅     | Matches official shadcn-vue across `Popover.vue`, `PopoverTrigger.vue`, `PopoverContent.vue`, and `index.ts`; `bg-popover` is correct here. |
| `select`        | ✅     | Matches official shadcn-vue across all 11 component files plus `index.ts`; `ScrollUpButton` and `ScrollDownButton` are present.             |
| `tabs`          | ✅     | Matches official shadcn-vue across `Tabs.vue`, `TabsList.vue`, `TabsTrigger.vue`, `TabsContent.vue`, and `index.ts`.                        |
| `input`         | ✅     | Matches official shadcn-vue exactly.                                                                                                        |
| `button`        | ⚠️     | Local styling diverges from official border radius, sizing, and minimum width behavior.                                                     |
| `breadcrumb`    | ⚠️     | `BreadcrumbLink` is missing the official `data-reka-collection-item` attribute on its span wrapper.                                         |
| `badge`         | ⚠️     | Local component includes custom `loading` and `subtle` variants that are not part of official shadcn-vue.                                   |
| `separator`     | ⚠️     | Local component adds `decoration-slice`, which is not in official shadcn-vue.                                                               |
| `tooltip`       | ⚠️     | Intentionally user-approved visual deviation from official shadcn-vue, including custom colors, size, and `TooltipArrow`.                   |

## Components Matching Official shadcn-vue

### `dialog`

Status: ✅ Matches official.

Audited files:

- `Dialog.vue`
- `DialogClose.vue`
- `DialogContent.vue`
- `DialogDescription.vue`
- `DialogFooter.vue`
- `DialogHeader.vue`
- `DialogOverlay.vue`
- `DialogScrollContent.vue`
- `DialogTitle.vue`
- `index.ts`

Findings:

- All expected component files and exports are present.
- `DialogClose` is present.
- Imports match official shadcn-vue.
- Classes and animation data attributes match official shadcn-vue.

### `dropdown-menu`

Status: ✅ Matches official.

Audited files:

- All 14 dropdown menu component files.
- `index.ts`

Findings:

- Reka imports match official shadcn-vue.
- Animation classes match official shadcn-vue.
- Portal export is present and matches official shadcn-vue.
- No deviations were found.

### `popover`

Status: ✅ Matches official.

Audited files:

- `Popover.vue`
- `PopoverTrigger.vue`
- `PopoverContent.vue`
- `index.ts`

Findings:

- Component structure and exports match official shadcn-vue.
- `bg-popover` is correct for `PopoverContent`.
- No deviations were found.

### `select`

Status: ✅ Matches official.

Audited files:

- All 11 select component files.
- `index.ts`

Findings:

- `ScrollUpButton` and `ScrollDownButton` are present.
- Component structure, exports, and expected behavior match official shadcn-vue.
- No deviations were found.

### `tabs`

Status: ✅ Matches official.

Audited files:

- `Tabs.vue`
- `TabsList.vue`
- `TabsTrigger.vue`
- `TabsContent.vue`
- `index.ts`

Findings:

- Component structure and exports match official shadcn-vue.
- No deviations were found.

### `input`

Status: ✅ Matches official.

Current local behavior:

- Uses `h-9 w-full`.
- Includes the official class set:
  - `flex h-9 w-full rounded-md`
  - `border border-input`
  - `bg-transparent`
  - `px-3 py-1 text-sm shadow-sm transition-colors`
  - official file input classes
  - official focus-visible classes
  - official disabled classes

Official shadcn-vue behavior:

- Uses the same class set listed above.

Finding:

- Although `input` was initially listed for review, the audited local implementation matches official shadcn-vue exactly.

## Components with Deviations

### `button`

Status: ⚠️ Deviates from official shadcn-vue.

Current local behavior:

- Uses `rounded-full`.
- Adds `min-w-36`, creating a local minimum width behavior.
- Uses `size-[80px]` for one of the sizing paths.

Official shadcn-vue behavior:

- Uses `rounded-md`.
- Does not apply a default minimum width; button width fits content unless callers add their own width constraints.
- Uses official `data-[size]` variants rather than a hard-coded `size-[80px]`.

Impact:

- Local buttons have a stronger pill-shaped visual style than official shadcn-vue.
- The minimum width can make compact actions wider than expected.
- The hard-coded `size-[80px]` does not align with the official sizing API and may cause inconsistent layout behavior.

Recommendation:

- Decide whether the pill shape and minimum width are intentional product-level styling.
- If the goal is strict shadcn-vue parity, change `rounded-full` to `rounded-md`, remove `min-w-36`, and replace `size-[80px]` with the official `data-[size]` variant behavior.

### `breadcrumb`

Status: ⚠️ Minor deviation from official shadcn-vue.

Current local behavior:

- `BreadcrumbLink` is missing the official `data-reka-collection-item` attribute on its span wrapper.
- `BreadcrumbSeparator` uses `chevron-right` as the default separator icon.

Official shadcn-vue behavior:

- `BreadcrumbLink` includes `data-reka-collection-item` on the span wrapper.
- `BreadcrumbSeparator` also uses `chevron-right` as the default separator icon.

Impact:

- The missing `data-reka-collection-item` attribute is the confirmed difference.
- The separator icon is not a deviation; local and official both default to `chevron-right`.

Recommendation:

- Add `data-reka-collection-item` to the `BreadcrumbLink` span wrapper if strict parity is required.
- No change is needed for `BreadcrumbSeparator` based on this audit.

### `badge`

Status: ⚠️ Deviates from official shadcn-vue.

Current local behavior:

- Includes custom `loading` variant.
- Includes custom `subtle` variant.
- Also includes official variants.

Official shadcn-vue behavior:

- Provides only these variants:
  - `default`
  - `secondary`
  - `destructive`
  - `outline`

Impact:

- The local component is a superset of official shadcn-vue.
- Existing product code may depend on `loading` or `subtle`.
- This is not necessarily a bug, but it is a parity deviation.

Recommendation:

- Keep `loading` and `subtle` if they are intentional product variants.
- If strict shadcn-vue parity is required, remove the custom variants and update all call sites that depend on them.

### `separator`

Status: ⚠️ Minor deviation from official shadcn-vue.

Current local behavior:

- Uses `bg-border`.
- Uses official `data-[orientation]` classes.
- Adds `decoration-slice`.

Official shadcn-vue behavior:

- Uses `bg-border`.
- Uses the same official `data-[orientation]` classes.
- Does not include `decoration-slice`.

Impact:

- The local implementation mostly matches official shadcn-vue.
- `decoration-slice` is extra and does not belong to the official component.

Recommendation:

- Remove `decoration-slice` if strict parity is required.
- Keep it only if there is a documented local reason for this utility class.

### `tooltip`

Status: ⚠️ Intentional user-approved visual deviation.

Current local behavior:

- Uses `bg-primary`.
- Uses `text-primary-foreground`.
- Uses `text-xs`.
- Includes `TooltipArrow`.

Official shadcn-vue behavior:

- Uses `bg-popover`.
- Uses `text-popover-foreground`.
- Uses `text-sm`.
- Uses `overflow-hidden`.
- Does not include the local visual treatment with `TooltipArrow`.

Important audit notes:

- `TooltipProvider` is present in `App.vue`.
- `TooltipArrow` is present in `TooltipContent.vue`.
- These are not missing implementation items.

Impact:

- Tooltip styling intentionally differs from official shadcn-vue for local visual style.
- The component should not be treated as accidentally broken or incomplete based on the official style mismatch alone.

Recommendation:

- Preserve the current tooltip implementation unless the product direction changes back to strict shadcn-vue parity.
- Document this as an intentional local component fork so future audits do not repeatedly flag it as accidental drift.

## Final Recommendations

1. Treat `dialog`, `dropdown-menu`, `popover`, `select`, `tabs`, and `input` as clean shadcn-vue matches.
2. For strict parity, update `button`, `breadcrumb`, `badge`, and `separator` to remove the listed local deviations.
3. Keep `tooltip` as-is unless there is a new design decision to restore official shadcn-vue styling.
4. Add a short local convention note for intentionally forked shadcn-vue components, especially `tooltip` and any retained `badge` variants.
5. When future shadcn-vue components are updated, separate intentional product styling from accidental implementation drift in the audit notes.
