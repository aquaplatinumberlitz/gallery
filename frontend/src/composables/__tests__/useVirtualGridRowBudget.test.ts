/**
 * Purpose: Protect the row budget of the virtual grid, which lets a grid mount its first rows in steps.
 * Guarantees: the extractor keeps at most `budget` rows counted from the first row of the range, no budget
 * (or Infinity) leaves the default range untouched, and a changed budget changes the rendered rows.
 * Run when: Changing `useVirtualGridRows.ts` or the album-open staging in `GalleryGrid.vue`.
 */
import { describe, expect, it } from "vitest";
import { computed, nextTick, ref } from "vue";
import { defaultRangeExtractor } from "@tanstack/vue-virtual";
import { withSetup } from "@/test/withSetup";
import { budgetedRangeExtractor, useVirtualGridRows } from "../useVirtualGridRows";

const range = { startIndex: 4, endIndex: 9, overscan: 2, count: 30 };

describe("budgetedRangeExtractor", () => {
  it("keeps the first rows of the default range", () => {
    expect(defaultRangeExtractor(range)).toEqual([2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    expect(budgetedRangeExtractor(3)(range)).toEqual([2, 3, 4]);
    expect(budgetedRangeExtractor(0)(range)).toEqual([]);
  });

  it("does not limit the range for Infinity or a budget larger than the range", () => {
    expect(budgetedRangeExtractor(Infinity)(range)).toEqual(defaultRangeExtractor(range));
    expect(budgetedRangeExtractor(100)(range)).toEqual(defaultRangeExtractor(range));
  });
});

describe("useVirtualGridRows rowBudget", () => {
  const rows = computed(() => Array.from({ length: 40 }, (_, i) => ({ id: `row-${i}` })));
  const container = document.createElement("div");
  Object.defineProperty(container, "offsetHeight", { value: 500 });
  Object.defineProperty(container, "offsetWidth", { value: 300 });
  container.getBoundingClientRect = () => ({ width: 300, height: 500 }) as DOMRect;

  it("renders only the budgeted rows and more once the budget is raised", async () => {
    const rowBudget = ref(1);
    const { result: grid } = withSetup(() =>
      useVirtualGridRows({
        rows,
        scrollElement: ref<HTMLElement | null>(container),
        estimateSize: () => 100,
        overscan: 2,
        rowBudget,
      }),
    );
    await nextTick();
    const unlimited = grid.virtualizer.value.getVirtualIndexes().length;

    expect(grid.virtualItems.value).toHaveLength(1);

    rowBudget.value = 3;
    await nextTick();
    expect(grid.virtualItems.value).toHaveLength(3);

    rowBudget.value = Infinity;
    await nextTick();
    expect(grid.virtualItems.value.length).toBeGreaterThan(3);
    expect(unlimited).toBeGreaterThan(0);
  });

  it("renders no rows at budget 0 and keeps the full scroll height", async () => {
    const { result: grid } = withSetup(() =>
      useVirtualGridRows({
        rows,
        scrollElement: ref<HTMLElement | null>(container),
        estimateSize: () => 100,
        rowBudget: ref(0),
      }),
    );
    await nextTick();

    expect(grid.virtualItems.value).toHaveLength(0);
    expect(grid.totalSize.value).toBe(4000);
  });

  it("is unchanged without a budget", async () => {
    const { result: grid } = withSetup(() =>
      useVirtualGridRows({
        rows,
        scrollElement: ref<HTMLElement | null>(container),
        estimateSize: () => 100,
        overscan: 2,
      }),
    );
    await nextTick();

    expect(grid.virtualItems.value.length).toBeGreaterThan(3);
  });
});
