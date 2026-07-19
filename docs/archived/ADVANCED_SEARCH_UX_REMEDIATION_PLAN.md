# Advanced Search UX Remediation Plan

Status: Proposed
Created: 2026-07-19
Source: `.impeccable/critique/2026-07-19T12-30-09Z__end-src-components-search-advancedsearchdrawer-vue.md`
(dual-agent UX critique — Nielsen 28/40 ≈ 7/10)

## Goal

Fix the 5 prioritized UX findings from the 2026-07-19 Advanced Search critique,
in order. Each task is independently shippable and has its own tests and
verification commands. Do not refactor anything outside the listed files.

| Task | Severity | What | Effort |
| ---- | -------- | ---- | ------ |
| 1 | P0 | Footer keyboard-hint text collides with status text at the Apply row | ~15 min |
| 2 | P1 | Filter form is buried below summary + recents + facets + 4 discovery sections | ~30 min |
| 3 | P1 | Facet suggestion field: broken `aria-describedby` binding + no listbox semantics/keyboard nav | ~45 min |
| 4 | P2 | Applied filter chips are invisible on mobile/tablet | ~45 min |
| 5 | P2 | Clickable and display-only facet pills look identical | ~15 min |
| 6 | P3 batch | Chip-remove touch target 32px → 44px; jump-to-field visible label | ~15 min |

## Ground rules

- Work on a branch. Do not touch files other than the ones listed per task.
- After every task, run its **Verify** commands. All must pass before moving on.
- Frontend commands run in `/home/ubuntu/gallery-repo/frontend`.
- Unit tests: `corepack pnpm exec vitest run src/components/search/__tests__/<file>`
- All frontend unit tests: `corepack pnpm run test:unit`
- Lint: from repo root, `./test.sh lint`
- The existing e2e spec for this surface is
  `frontend/tests/e2e/library-inspector.spec.ts`; advanced-search interactions
  also appear in `frontend/tests/e2e/metadata-performance.spec.ts`. Run them
  only when a task says so (they need the app running; see AGENTS.md "Remote
  Access" for how the backend/frontend are started).

---

## Task 1 (P0) — Footer collision at the Apply row

**File:** `frontend/src/components/search/AdvancedSearchDrawer.vue`

**Root cause:** the `<kbd>Ctrl/⌘+Enter</kbd>` hint uses `hidden md:inline`
(Tailwind **viewport** breakpoint). The drawer is only ~640px wide even on a
1440px viewport, so at `md` and up the hint renders inside a crowded footer and
overlaps the "Unsaved changes" / "N fields need attention" status text
(evidence: critique screenshot `drawer-footer-crop.png`).

**Fix:** remove the standalone kbd hint and move the shortcut information onto
the Apply button itself (`aria-keyshortcuts` + native `title` tooltip). Also
let the status text truncate instead of colliding.

### Step 1.1 — delete the kbd hint span

Find (lines ~1010-1013, inside `<footer data-testid="advanced-search-footer">`):

```vue
          <div class="flex items-center justify-end gap-2 sm:gap-3">
            <span class="hidden text-xs text-muted-foreground md:inline"
              ><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd></span
            >
            <Button type="button" variant="ghost" size="sm" class="advanced-search-action" @click="handleCancel">
```

Replace with:

```vue
          <div class="flex items-center justify-end gap-2 sm:gap-3">
            <Button type="button" variant="ghost" size="sm" class="advanced-search-action" @click="handleCancel">
```

### Step 1.2 — put the shortcut on the Apply button

Find (lines ~1017-1019):

```vue
            <Button type="submit" size="sm" class="advanced-search-action" :disabled="!isDirty">
              <Search data-icon="inline-start" />{{ applyLabel }}
            </Button>
```

Replace with:

```vue
            <Button
              type="submit"
              size="sm"
              class="advanced-search-action"
              :disabled="!isDirty"
              aria-keyshortcuts="Control+Enter Meta+Enter"
              title="Apply (Ctrl/⌘ + Enter)"
            >
              <Search data-icon="inline-start" />{{ applyLabel }}
            </Button>
```

### Step 1.3 — make the status text truncate instead of colliding

Find (lines ~1005-1008):

```vue
            <span v-if="validationErrorCount" class="text-xs font-medium text-destructive" role="alert">
              {{ validationErrorCount }} field{{ validationErrorCount === 1 ? "" : "s" }} need attention
            </span>
            <span v-else-if="isDirty" class="text-xs text-muted-foreground">Unsaved changes</span>
```

Replace with:

```vue
            <span v-if="validationErrorCount" class="min-w-0 truncate text-xs font-medium text-destructive" role="alert">
              {{ validationErrorCount }} field{{ validationErrorCount === 1 ? "" : "s" }} need attention
            </span>
            <span v-else-if="isDirty" class="min-w-0 truncate text-xs text-muted-foreground">Unsaved changes</span>
```

### Step 1.4 — add a regression test

**File:** `frontend/src/components/search/__tests__/AdvancedSearchDrawer.test.ts`

Append this test inside the top-level `describe` block (mirror the mounting
style of the existing test `"applies a valid form with Ctrl+Enter"` at ~line 290):

```ts
  it("exposes the apply shortcut on the submit button without a footer kbd hint", () => {
    const wrapper = mountDrawer();
    const footer = wrapper.find('[data-testid="advanced-search-footer"]');
    expect(footer.find("kbd").exists()).toBe(false);
    const submit = footer.find('button[type="submit"]');
    expect(submit.attributes("aria-keyshortcuts")).toBe("Control+Enter Meta+Enter");
    expect(submit.attributes("title")).toContain("Ctrl");
  });
```

If `mountDrawer` is not the helper name used by neighboring tests, copy the
exact mounting call from the `"applies a valid form with Ctrl+Enter"` test.

### Verify (Task 1)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec vitest run src/components/search/__tests__/AdvancedSearchDrawer.test.ts
```

**Acceptance:** all tests in the file pass, including the new one. No `kbd`
element renders in the footer at any viewport; Apply button exposes
`aria-keyshortcuts`.

---

## Task 2 (P1) — Put the filter form first, discovery last

**File:** `frontend/src/components/search/AdvancedSearchDrawer.vue`

**Root cause:** inside the single `<Accordion data-testid="advanced-search-groups">`,
the four discovery `AccordionItem`s (`prompts`, `workflow`, `raw-workflow`,
`indexes`) come *before* the filter `AccordionItem`s (`content`, `generation`,
`dimensions`, `custom`). First viewport shows zero filter inputs; on mobile the
first filter field is a multi-screen scroll away.

**Fix:** reorder blocks **inside the same `<Accordion>` element** so the final
order is exactly:

1. `<p class="advanced-search-group-heading">Filters</p>` + the jump-to-field `<div class="advanced-search-jump-field …">`
2. `AccordionItem value="content"`, `value="generation"`, `value="dimensions"`, `value="custom"`
3. `<hr class="advanced-search-group-divider" />`
4. `<p class="advanced-search-group-heading">Discovery &amp; tools</p>`
5. `AccordionItem value="prompts"`, `value="workflow"`, `value="raw-workflow"` (keep its `v-if`), `value="indexes"`

### Step 2.1 — delete the old "Discovery & tools" heading

Find and delete this line (~line 456, directly above `<Accordion type="multiple"`):

```vue
          <p class="advanced-search-group-heading">Discovery &amp; tools</p>
```

### Step 2.2 — move the "Filters" heading + jump field above the filter items

Find this block (~lines 532-544, currently between the `indexes` and `content`
AccordionItems):

```vue
            <hr class="advanced-search-group-divider" />
            <p class="advanced-search-group-heading">Filters</p>

            <div class="advanced-search-jump-field mb-3">
              <Search class="advanced-search-jump-icon" aria-hidden="true" />
              <Input
                v-model="jumpQuery"
                class="advanced-search-jump-input"
                placeholder="Jump to a field (e.g. seed, steps, model)…"
                aria-label="Jump to filter field"
                @keydown.enter.prevent="handleJumpToField"
              />
            </div>
```

Cut it. Paste it **immediately after** the `<Accordion … data-testid="advanced-search-groups">`
opening tag (i.e. directly before `<AccordionItem value="prompts">`), **but
remove the `<hr … />` line** from the moved block. Result:

```vue
            data-testid="advanced-search-groups"
          >
            <p class="advanced-search-group-heading">Filters</p>

            <div class="advanced-search-jump-field mb-3">
              <Search class="advanced-search-jump-icon" aria-hidden="true" />
              <Input
                v-model="jumpQuery"
                class="advanced-search-jump-input"
                placeholder="Jump to a field (e.g. seed, steps, model)…"
                aria-label="Jump to filter field"
                @keydown.enter.prevent="handleJumpToField"
              />
            </div>

            <AccordionItem value="content">
```

### Step 2.3 — move the filter AccordionItems above the discovery items

Cut the four filter `AccordionItem` blocks — `value="content"`,
`value="generation"`, `value="dimensions"`, `value="custom"` (each block runs
from its `<AccordionItem …>` line to its matching `</AccordionItem>`) — and
paste them **after the jump-field div you pasted in Step 2.2, before
`<AccordionItem value="prompts">`**.

### Step 2.4 — re-insert the divider and the discovery heading

Immediately before `<AccordionItem value="prompts">`, insert:

```vue
            <hr class="advanced-search-group-divider" />
            <p class="advanced-search-group-heading">Discovery &amp; tools</p>
```

### Step 2.5 — sanity-check the final template order

Inside `<Accordion data-testid="advanced-search-groups">` the order must now be:
Filters heading → jump field → content → generation → dimensions → custom →
hr → Discovery & tools heading → prompts → workflow → raw-workflow → indexes.
Nothing else may move. The default-open section (`activeAccordionSections`)
already contains `content`; do not change it.

### Verify (Task 2)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec vitest run src/components/search/__tests__/AdvancedSearchDrawer.test.ts
```

The existing test `"opens Content and files by default and collapses advanced
groups"` must still pass. If any test asserts the *order* of accordion items,
update the expected order to the new one (that is an intended change, not a
regression).

**Acceptance:** opening the drawer shows the "Content and files" filter fields
in the first viewport on desktop and within the first screen on mobile;
discovery sections are reachable below the filter sections.

---

## Task 3 (P1) — Facet field accessibility

**File:** `frontend/src/components/search/AdvancedSearchFacetField.vue`

### Step 3.1 — fix the broken `aria-describedby` binding (one character)

Find (line 67):

```vue
          aria-describedby="statusText ? `${id}-status` : undefined"
```

Replace with (note the leading `:`):

```vue
          :aria-describedby="statusText ? `${id}-status` : undefined"
```

Why: without `:`, Vue renders the literal string
`statusText ? `${id}-status` : undefined` as the attribute value, so screen
readers never announce the loading/unavailable status that
`FieldDescription id="…-status"` carries (line 120).

### Step 3.2 — add listbox semantics to the suggestion list

Find (lines ~101-116):

```vue
        <ul
          v-if="filteredOptions.length"
          class="advanced-search-facet-list max-h-60 overflow-y-auto"
          :aria-label="`${label} suggestions`"
        >
          <li v-for="entry in filteredOptions" :key="entry.value">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
              @click="selectOption(entry.value)"
            >
```

Replace with:

```vue
        <ul
          v-if="filteredOptions.length"
          :id="`${id}-listbox`"
          ref="listEl"
          role="listbox"
          class="advanced-search-facet-list max-h-60 overflow-y-auto"
          :aria-label="`${label} suggestions`"
        >
          <li v-for="entry in filteredOptions" :key="entry.value" role="presentation">
            <button
              type="button"
              role="option"
              :aria-selected="entry.value === modelValue"
              class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
              @click="selectOption(entry.value)"
              @keydown="handleOptionKeydown"
            >
```

### Step 3.3 — keyboard navigation + focus return

In `<script setup>`:

1. Make sure `shallowRef` is imported from `vue` (add it to the existing
   `import { … } from "vue"` line if missing).
2. Add, next to the other refs:

```ts
const listEl = shallowRef<HTMLUListElement | null>(null);

function handleOptionKeydown(event: KeyboardEvent) {
  const key = event.key;
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(key)) return;
  event.preventDefault();
  const buttons = Array.from(listEl.value?.querySelectorAll("button") ?? []) as HTMLElement[];
  const index = buttons.indexOf(event.currentTarget as HTMLElement);
  let next = index;
  if (key === "ArrowDown") next = Math.min(index + 1, buttons.length - 1);
  else if (key === "ArrowUp") next = Math.max(index - 1, 0);
  else if (key === "Home") next = 0;
  else next = buttons.length - 1;
  buttons[next]?.focus();
}

function handleFilterInputKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowDown") return;
  event.preventDefault();
  listEl.value?.querySelector("button")?.focus();
}
```

3. On the popover filter `<input>` (the one with
   `:placeholder="`Filter ${label}…`"`, ~line 92), add:

```vue
              @keydown="handleFilterInputKeydown"
```

4. Find the existing `selectOption` function. At its end (after the popover is
   closed), return focus to the text input:

```ts
import { nextTick } from "vue"; // merge into the existing vue import

// inside selectOption(value: string), as the last statement:
  void nextTick(() => document.getElementById(id)?.focus());
```

### Step 3.4 — add a unit test

**New file:** `frontend/src/components/search/__tests__/AdvancedSearchFacetField.test.ts`

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import AdvancedSearchFacetField from "../AdvancedSearchFacetField.vue";

const baseProps = {
  id: "advanced-search-model",
  label: "Model",
  modelValue: "",
  options: [
    { value: "sdxl", count: 12 },
    { value: "pony", count: 3 },
  ],
};

describe("AdvancedSearchFacetField", () => {
  it("points aria-describedby at the status element only when status exists", () => {
    const withStatus = mount(AdvancedSearchFacetField, {
      props: { ...baseProps, statusText: "Suggestions unavailable" },
    });
    expect(withStatus.find("input").attributes("aria-describedby")).toBe("advanced-search-model-status");
    const withoutStatus = mount(AdvancedSearchFacetField, { props: baseProps });
    expect(withoutStatus.find("input").attributes("aria-describedby")).toBeUndefined();
  });

  it("exposes listbox semantics and arrow-key navigation", async () => {
    const wrapper = mount(AdvancedSearchFacetField, { props: baseProps, attachTo: document.body });
    await wrapper.find("button[aria-label^='Browse']").trigger("click");
    const listbox = wrapper.find('[role="listbox"]');
    expect(listbox.exists()).toBe(true);
    const options = wrapper.findAll('[role="option"]');
    expect(options).toHaveLength(2);
    options[0].element.focus();
    await options[0].trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[1].element);
    wrapper.unmount();
  });
});
```

Adjust prop names/shape if the component's actual props differ (check the
`defineProps` block at the top of the file first).

### Verify (Task 3)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec vitest run src/components/search/__tests__/AdvancedSearchFacetField.test.ts src/components/search/__tests__/AdvancedSearchDrawer.test.ts
```

**Acceptance:** new tests pass; no `aria-describedby` literal string in the
rendered DOM; ArrowDown/ArrowUp/Home/End move focus across suggestion options;
selecting an option returns focus to the text input.

---

## Task 4 (P2) — Show applied filter chips on mobile and tablet

**Files:**
- `frontend/src/components/MobileHeader.vue`
- `frontend/src/components/TabletHeader.vue`

**Root cause:** `SearchFilterChips` is rendered only in `AppHeader.vue`
(desktop, line ~400). After applying advanced filters on mobile/tablet, the
only visible evidence is the word "Relevance".

**Fix:** reuse the exact wiring AppHeader already uses
(`useFieldedSearch(() => props.searchQuery)` + emit `update:searchQuery`).

### Step 4.1 — MobileHeader script

In `MobileHeader.vue` `<script setup>`:

1. Add imports (merge with existing lines):

```ts
import SearchFilterChips from "@/components/SearchFilterChips.vue";
import { useFieldedSearch } from "@/composables/useFieldedSearch";
```

(Check the composable's real path/name against the import AppHeader.vue uses at
its own script top — copy that import path exactly.)

2. Add (mirroring AppHeader.vue lines ~73-79 and ~216-222):

```ts
const {
  fieldedFilters,
  removeFilter,
  clearAll,
} = useFieldedSearch(() => props.searchQuery);

function handleRemoveFilter(index: number) {
  emit("update:searchQuery", removeFilter(index));
}

function handleClearAll() {
  emit("update:searchQuery", clearAll());
}
```

### Step 4.2 — MobileHeader template

Find the closing of the search-focus wrapper — this exact sequence
(~lines 215-218):

```vue
      </motion.div>
    </div>

    <RouterLink v-if="!isSearchActive && showBackToGallery" to="/" class="mh-btn" aria-label="Back to gallery">
```

Insert between `</div>` and `<RouterLink`:

```vue
    <SearchFilterChips
      v-if="fieldedFilters.length"
      :filters="fieldedFilters"
      class="mh-filter-chips"
      @remove="handleRemoveFilter"
      @clear-all="handleClearAll"
    />
```

### Step 4.3 — MobileHeader style

In the `<style>` section, add (horizontal scroll row, doesn't wrap the header
taller than needed):

```css
.mh-filter-chips {
  order: 3;
  flex-basis: 100%;
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  padding-inline: 4px;
}

.mh-filter-chips::-webkit-scrollbar {
  display: none;
}
```

If the chips render stacked/awkward, check the header's `display`/`flex-wrap`
in the existing `.gallery-header`-equivalent rules in this file and add
`width: 100%` to `.mh-filter-chips`.

### Step 4.4 — TabletHeader: repeat Steps 4.1-4.3

`TabletHeader.vue` has the same props (`searchQuery`) and emits
(`update:searchQuery`) — apply the identical script changes, then render the
chips row immediately before its `</header>` closing tag (~line 247), with the
same class name pattern (`th-filter-chips` or reuse `mh-filter-chips` styles
copied over).

### Verify (Task 4)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm run test:unit
```

Then manual/e2e check with the app running (AGENTS.md lists the two `screen`
commands): open a mobile viewport (≤767px), apply any advanced filter, confirm
a horizontally scrollable chip row appears under the header and that removing a
chip rewrites the search query. If Playwright is set up, extend
`frontend/tests/e2e/library-inspector.spec.ts` with:

```ts
test("mobile header shows applied advanced filter chips", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // …reuse the spec's existing "apply an advanced filter" steps…
  await expect(page.locator(".mh-filter-chips")).toBeVisible();
});
```

**Acceptance:** chips visible and removable on mobile and tablet after Apply;
desktop header unchanged; unit suite green.

---

## Task 5 (P2) — Distinguish clickable facet pills from display-only ones

**File:** `frontend/src/components/search/IndexedFacetSummary.vue`

**Root cause:** groups with a mapped filter field (Model, Sampler, LoRA —
clickable) and groups without one (Tools, Orientation, Seed — display-only)
render the same `bg-muted` pill chrome (lines ~87-117).

**Fix:** strip pill chrome from display-only items; keep it only on buttons.

Find (lines ~87-92):

```vue
            <li
              v-for="entry in group.visibleEntries"
              :key="entry.value"
              class="inline-flex max-w-full items-baseline gap-1.5 rounded-md bg-muted px-2 py-1 text-xs"
              :class="group.field ? 'p-0 bg-transparent' : ''"
            >
```

Replace with:

```vue
            <li
              v-for="entry in group.visibleEntries"
              :key="entry.value"
              class="inline-flex max-w-full items-baseline gap-1.5 text-xs"
              :class="group.field ? 'rounded-md bg-transparent p-0' : 'px-0 py-0.5'"
            >
```

### Verify (Task 5)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec vitest run src/components/search/__tests__/IndexedFacetSummary.test.ts
```

The existing test `"shows indexed facet values as readable wrapped items"` (in
`AdvancedSearchDrawer.test.ts`) and the `IndexedFacetSummary.test.ts` suite must
stay green; if a test asserts `bg-muted` on non-clickable entries, update it to
assert the new plain-text rendering for display-only groups and pill chrome
only for clickable ones (intended change).

**Acceptance:** clickable values render as muted pills with hover; display-only
values render as plain text with a tabular count.

---

## Task 6 (P3 batch) — Touch target + jump-field label

**File:** `frontend/src/components/search/AdvancedSearchDrawer.vue`

### Step 6.1 — chip-remove touch target 32px → 44px

Find (lines ~1094-1097, inside the `max-width: 1023px` media query):

```css
  .advanced-search-chip-remove {
    min-width: 32px;
    min-height: 32px;
  }
```

Replace with:

```css
  .advanced-search-chip-remove {
    min-width: 44px;
    min-height: 44px;
  }
```

### Step 6.2 — visible label for the jump-to-field input

The project's own rule (PRODUCT.md / DESIGN.md) is "label always above", but
the jump input currently has only a placeholder + `aria-label` (~lines 535-544).
Find:

```vue
            <div class="advanced-search-jump-field mb-3">
              <Search class="advanced-search-jump-icon" aria-hidden="true" />
              <Input
                v-model="jumpQuery"
                class="advanced-search-jump-input"
                placeholder="Jump to a field (e.g. seed, steps, model)…"
                aria-label="Jump to filter field"
                @keydown.enter.prevent="handleJumpToField"
              />
            </div>
```

Replace with:

```vue
            <div class="mb-3">
              <label for="advanced-search-jump" class="mb-1.5 block text-sm font-medium">
                Jump to a field
              </label>
              <div class="advanced-search-jump-field">
                <Search class="advanced-search-jump-icon" aria-hidden="true" />
                <Input
                  id="advanced-search-jump"
                  v-model="jumpQuery"
                  class="advanced-search-jump-input"
                  placeholder="seed, steps, model…"
                  @keydown.enter.prevent="handleJumpToField"
                />
              </div>
            </div>
```

(`aria-label` is removed because the visible `<label>` now names the input;
the placeholder no longer duplicates the label.)

### Verify (Task 6)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec vitest run src/components/search/__tests__/AdvancedSearchDrawer.test.ts
```

**Acceptance:** suite green; chip remove buttons measure ≥44×44 CSS px at
mobile width; jump input has a programmatically associated visible label
(check `wrapper.find("#advanced-search-jump").attributes("aria-label")` is
undefined and the `<label for>` matches).

---

## Final verification (all tasks)

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm run test:unit
cd /home/ubuntu/gallery-repo
./test.sh lint
./test.sh docs
```

If drawer behavior changed visibly (Tasks 1-2, 4-5), also run:

```bash
cd /home/ubuntu/gallery-repo/frontend
corepack pnpm exec playwright test tests/e2e/library-inspector.spec.ts --project=chromium
```

## Explicitly out of scope (do not implement without a new plan)

- Moving "Index status" out of the drawer into Maintenance.
- Collapsing the "No filters selected" summary box when empty.
- A raw-query editor inside the drawer; the invisible `raw:` modeled slot
  (`advancedSearchModel.ts` `fieldIds.raw`).
- Date operator display in chips (`LITERAL_FIELDS` in
  `utils/searchQueryGrammar.ts`) — needs a grammar contract check first.
- Partial `between` (one bound empty) silently staging zero filters.
- `size` vs `width`/`height` precedence documentation.
- AppHeader brand/theme-toggle detector findings (10 literal colors, `Cinzel`
  font) — either document them in DESIGN.md or add ignore entries in
  `.impeccable/critique/ignore.md`; they are brand styling, not search drift.

## Done criteria

- All 6 tasks verified; unit suite + lint + docs gates green.
- Re-run the critique target and confirm the score improves and the P0/P1s are
  gone from the findings.
