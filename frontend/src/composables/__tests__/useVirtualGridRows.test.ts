import { describe, expect, it } from "vitest";
import { chunkGridRows, chunkItems } from "../useVirtualGridRows";

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
