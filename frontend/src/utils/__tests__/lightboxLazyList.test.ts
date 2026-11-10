/**
 * Purpose: Protect the lazily built lightbox data source used to open a lightbox over a long album.
 * Guarantees: the list behaves like an array (length, isArray, index reads, iteration, map, JSON), an item is
 * built only when first read, is built once, and stays an ordinary mutable object afterwards, and the list grows
 * in place (new slots are lazy, built items keep their identity, it never shrinks).
 * Run when: Changing `lightboxLazyList.ts` or how `usePhotoSwipe` builds its PhotoSwipe data source.
 */
import { describe, expect, it, vi } from "vitest";
import { createLazyList, growLazyList } from "../lightboxLazyList";

const make = (count: number) => {
  const build = vi.fn((index: number) => ({ index, label: `item-${index}` }));
  return { build, list: createLazyList(count, build) };
};

describe("createLazyList", () => {
  it("looks like an array without building anything", () => {
    const { build, list } = make(300);

    expect(Array.isArray(list)).toBe(true);
    expect(list).toHaveLength(300);
    expect(5 in list).toBe(true);
    expect(300 in list).toBe(false);
    expect(build).not.toHaveBeenCalled();
  });

  it("builds an item on first read, once", () => {
    const { build, list } = make(300);

    expect(list[7]).toEqual({ index: 7, label: "item-7" });
    expect(list[7]).toBe(list[7]);

    expect(build).toHaveBeenCalledTimes(1);
    expect(build).toHaveBeenCalledWith(7);
  });

  it("returns undefined outside the list and does not build for it", () => {
    const { build, list } = make(3);

    expect(list[3]).toBeUndefined();
    expect(list[-1]).toBeUndefined();
    expect(list[1.5 as unknown as number]).toBeUndefined();
    expect(build).not.toHaveBeenCalled();
  });

  it("keeps built items mutable", () => {
    const { list } = make(10);

    list[2].label = "changed";

    expect(list[2].label).toBe("changed");
  });

  it("builds every item when it is mapped, iterated or serialised", () => {
    const { build, list } = make(4);

    expect(list.map((item) => item.index)).toEqual([0, 1, 2, 3]);
    expect(build).toHaveBeenCalledTimes(4);
    expect([...list].map((item) => item.label)).toEqual(["item-0", "item-1", "item-2", "item-3"]);
    expect(JSON.parse(JSON.stringify(list))).toHaveLength(4);
    expect(build).toHaveBeenCalledTimes(4);
  });

  it("supports an empty list", () => {
    const { build, list } = make(0);

    expect(list).toHaveLength(0);
    expect(list[0]).toBeUndefined();
    expect(build).not.toHaveBeenCalled();
  });
});

describe("growLazyList", () => {
  it("extends the length without building anything", () => {
    const { build, list } = make(3);

    growLazyList(list, 8);

    expect(list).toHaveLength(8);
    expect(7 in list).toBe(true);
    expect(8 in list).toBe(false);
    expect(build).not.toHaveBeenCalled();
  });

  it("builds the new slots lazily and keeps already built items as they are", () => {
    const { build, list } = make(3);
    const first = list[1];
    first.label = "edited";

    growLazyList(list, 6);

    expect(list[1]).toBe(first);
    expect(list[1].label).toBe("edited");
    expect(list[5]).toEqual({ index: 5, label: "item-5" });
    expect(build).toHaveBeenCalledTimes(2);
    expect(build).toHaveBeenLastCalledWith(5);
  });

  it("never shrinks the list", () => {
    const { list } = make(5);

    growLazyList(list, 2);

    expect(list).toHaveLength(5);
  });

  it("keeps iteration and map consistent after growth", () => {
    const { list } = make(2);
    growLazyList(list, 4);

    expect(list.map((item) => item.index)).toEqual([0, 1, 2, 3]);
  });
});
