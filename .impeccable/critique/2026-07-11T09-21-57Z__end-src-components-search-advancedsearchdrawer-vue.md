---
target: Advanced Search modal
total_score: 16
p0_count: 0
p1_count: 4
timestamp: 2026-07-11T09-21-57Z
slug: end-src-components-search-advancedsearchdrawer-vue
---
# Advanced Search Drawer — UX/UI critique

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of system status | 2/4 | No facet loading/failure state, active-filter count, or apply progress. |
| 2 | Match system / real world | 2/4 | Technical labels such as Param, Advanced, Raw Query, and operators lack guidance. |
| 3 | User control and freedom | 2/4 | Cancel restores staged values, but Reset immediately clears applied filters and closes. |
| 4 | Consistency and standards | 2/4 | Familiar controls, but Reset semantics and modal=false with a blocking overlay conflict. |
| 5 | Error prevention | 1/4 | Validation misses date, ratio, numeric ranges, integer constraints, and conflicting dimensions. |
| 6 | Recognition rather than recall | 2/4 | Datalists and presets help, but most fields require metadata and query-syntax knowledge. |
| 7 | Flexibility and efficiency | 2/4 | Raw query supports experts, but actions require long scrolling and repeatable filters are flattened. |
| 8 | Aesthetic and minimalist design | 1/4 | Clean styling, but nearly every supported filter is visible at equal weight. |
| 9 | Error recognition and recovery | 2/4 | Errors are local but are not associated with controls or announced. |
| 10 | Help and documentation | 0/4 | No visible contextual help or syntax guidance. |
| **Total** | | **16/40** | **Poor — major UX restructuring needed.** |

## Anti-patterns verdict

This is functional rather than decorative slop. The restrained shadcn-style components fit the product, but the drawer reads like a schema dump: 24 criteria, repetitive uppercase legends, and no progressive disclosure.

The deterministic detector returned `[]` with zero findings. That is useful evidence that no bundled static anti-pattern was detected, but it does not cover runtime accessibility, semantics, or narrow viewport behavior.

No visual overlay was injected because no first-class mutable browser automation tool was available. A running Vite app was verified at `http://127.0.0.1:4702/`; static source, tests, and detector output were used as fallback evidence.

## Overall impression

The semantic baseline is stronger than the interaction design. The component feels dependable at the control level but intimidating and inefficient as a search-composition experience. The largest opportunity is to make common filters immediate and progressively reveal rare generation parameters and raw syntax.

## What works

- Real fieldsets, legends, visible labels, labeled operator selects, and a dialog title provide a sound semantic baseline.
- Cancel restores the opening state and inline validation preserves input.
- Facet-backed datalists and aspect-ratio presets reduce exact-value recall.

## Priority issues

### P1 — Exhaustive form dump and buried primary action

Every section is expanded and the action row lives inside the scrolling form. Common searches pay the cost of rare fields and Apply can sit several viewports away.

Fix: separate sticky header/body/footer; show an active-filter count and persistent `Apply N filters`; place common filters first and collapse generation parameters, dimensions, and raw syntax.

### P1 — Reset and repeated-filter behavior can lose intent

`filtersToValues()` stores only one value per field, so repeated filters overwrite one another. Reset emits an empty applied filter set and closes, which behaves like `Clear all and apply`, not a reversible form reset.

Fix: preserve repeatable filters as rows/chips or untouched tokens; rename the committed action `Clear all filters`, keep the drawer open, and apply only after confirmation through Apply.

### P1 — Mobile and accessibility behavior are weak

The drawer is at most 90vw while field grids remain two columns. Ratio buttons have tiny targets. Errors lack `aria-invalid`, `aria-describedby`, and a live announcement. `modal=false` conflicts with the blocking visual overlay.

Fix: full-width mobile sheet, single-column form below a content breakpoint, 44px touch targets, programmatically linked errors, and a coherent modal/focus model.

### P1 — Constraints allow invalid or contradictory searches

Most numeric inputs accept fractional or negative values, date and ratio are free text, and width/height/size/ratio coexist without precedence guidance.

Fix: field-specific integer/min/max rules, date/ratio format validation, appropriate input modes, and explicit handling of mutually overlapping dimension filters.

### P2 — Terminology and selected states do not teach the model

`Param`, `Advanced`, and `Raw Query` do not explain the syntax. Ratio presets expose `aria-pressed` without a visible pressed style.

Fix: rename fields around user intent, provide exact syntax examples, use a multiline code-style raw query field, and add a visible semantic selected state.

## Persona red flags

- **Alex, power user:** Apply is far from the working area, no Cmd/Ctrl+Enter shortcut exists, and repeated filters cannot be safely represented.
- **Sam, keyboard/screen-reader/low-vision:** the tab sequence is very long, errors are not announced, and tiny presets plus modal semantics create friction.
- **Casey, mobile:** two-column numeric rows become cramped inside 90vw; the primary action is not sticky or in the thumb zone.

## Minor observations

- Facet loading, failure, and genuinely empty suggestion states are indistinguishable.
- A change to `initialFilters` can reset in-progress edits.
- Apply can be disabled without explaining why.
- Section names describe implementation types instead of search goals.
- CSS contains a duplicate `display: flex` declaration in the form rule.
- Tests cover desktop happy paths but not mobile, keyboard focus, error announcements, repeated filters, or Reset semantics.

## Questions to consider

- Is this meant to help users compose a search, or expose every parser token?
- Which three filters represent 80% of advanced searches?
- Should repeated values, ranges, and OR logic be supported?
- Could a live active-filter summary or result-count preview make the experience iterative instead of form-like?

## Recommended actions

1. `$impeccable distill`: progressive disclosure, sticky actions, active-filter summary, and goal-based section hierarchy.
2. `$impeccable harden`: repeated-filter preservation, Reset semantics, validation, error association, and modal focus behavior.
3. `$impeccable adapt`: full-width mobile sheet, single-column reflow, and touch-target corrections.
