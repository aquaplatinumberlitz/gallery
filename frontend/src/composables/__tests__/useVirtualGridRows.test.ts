import { describe, expect, it } from "vitest";
import { computed, ref, type Ref } from "vue";
import { withSetup } from "@/test/withSetup";
import { chunkGridRows, chunkItems, useVirtualGridRows } from "../useVirtualGridRows";

describe("virtual grid row helpers", () => {
  it("chunks items using a minimum chunk size of one", () => {
    expect(chunkItems([1, 2, 3], 0)).toEqual([[1], [2], [3]]);
    expect(chunkItems([1, 2, 3], 2)).toEqual([[1, 2], [3]]);
  });

  it("builds keyed grid rows from chunked items", () => {
    const rows = chunkGridRows(["a", "b", "c", "d", "e"], 2, (_items, rowIndex, startIndex) => {
      return `row-${rowIndex}-${startIndex}`;
    });

    expect(rows).toEqual([
      { id: "row-0-0", items: ["a", "b"] },
      { id: "row-1-2", items: ["c", "d"] },
      { id: "row-2-4", items: ["e"] },
    ]);
  });
});

describe("useVirtualGridRows scroll margin", () => {
  const rows = computed(() => Array.from({ length: 10 }, (_, i) => ({ id: `row-${i}` })));
  const build = (scrollMargin?: Ref<number>) =>
    withSetup(() =>
      useVirtualGridRows({
        rows,
        scrollElement: ref<HTMLElement | null>(null),
        estimateSize: () => 100,
        scrollMargin,
      }),
    ).result;

  it("positions rows from the top of the spacer, ignoring the content above the list", () => {
    const grid = build(ref(300));
    // TanStack's item.start includes the margin; the row sits `start - margin` inside the spacer.
    expect(grid.getVirtualRowStyle(300).transform).toBe("translateY(0px)");
    expect(grid.getVirtualRowStyle(500).transform).toBe("translateY(200px)");
    expect(grid.virtualizer.value.options.scrollMargin).toBe(300);
  });

  it("keeps the desktop behaviour without a margin", () => {
    const grid = build();
    expect(grid.getVirtualRowStyle(500).transform).toBe("translateY(500px)");
    expect(grid.virtualizer.value.options.scrollMargin).toBe(0);
  });

  it("does not count the margin into the spacer height", () => {
    const grid = build(ref(300));
    expect(grid.totalSize.value).toBe(1000);
  });
});
