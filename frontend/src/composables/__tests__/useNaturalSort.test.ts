import { describe, it, expect } from "vitest";
import { compareNatural, naturalSortKey } from "../useNaturalSort";

describe("naturalSortKey", () => {
  it("splits a string into alternating text/number chunks", () => {
    expect(naturalSortKey("img12.png")).toEqual(["img", 12, ".png"]);
  });

  it("lowercases text chunks so comparisons are case-insensitive", () => {
    expect(naturalSortKey("IMG12.PNG")).toEqual(["img", 12, ".png"]);
  });

  it("returns a single text chunk when there are no digits", () => {
    expect(naturalSortKey("abc")).toEqual(["abc"]);
  });

  it("returns a single number chunk surrounded by empty text chunks when the string is fully numeric", () => {
    // "123".split(/(\d+)/) -> ['', '123', '']. Empty strings parse to NaN and
    // are kept as '' chunks.
    expect(naturalSortKey("123")).toEqual(["", 123, ""]);
  });

  it("returns an array with a single empty text chunk for an empty string", () => {
    expect(naturalSortKey("")).toEqual([""]);
  });

  it("keeps leading and trailing text chunks", () => {
    expect(naturalSortKey("a1b2c")).toEqual(["a", 1, "b", 2, "c"]);
  });
});

describe("compareNatural", () => {
  it("returns 0 for equal strings", () => {
    expect(compareNatural("abc", "abc")).toBe(0);
  });

  it("compares text chunks lexicographically", () => {
    expect(compareNatural("abc", "abd")).toBeLessThan(0);
    expect(compareNatural("abd", "abc")).toBeGreaterThan(0);
  });

  it("compares numeric chunks by their numeric value, not as strings", () => {
    expect(compareNatural("img2.png", "img10.png")).toBeLessThan(0);
    expect(compareNatural("img10.png", "img2.png")).toBeGreaterThan(0);
  });

  it("compares equal numeric chunks as 0 and moves to the next chunk", () => {
    expect(compareNatural("img10a.png", "img10b.png")).toBeLessThan(0);
  });

  it("treats a missing chunk as an empty string", () => {
    expect(compareNatural("img", "img10.png")).toBeLessThan(0);
    expect(compareNatural("img10.png", "img")).toBeGreaterThan(0);
  });

  it("sorts a mixed list of names into natural order", () => {
    const list = ["img10.png", "img2.png", "img1.png", "img20.png", "img3.png"];
    const sorted = [...list].sort(compareNatural);
    expect(sorted).toEqual(["img1.png", "img2.png", "img3.png", "img10.png", "img20.png"]);
  });

  it("is case-insensitive on the text chunks", () => {
    expect(compareNatural("IMG.png", "img.png")).toBe(0);
  });

  it("returns 0 when both inputs are empty", () => {
    expect(compareNatural("", "")).toBe(0);
  });

  it("places shorter strings before longer strings when they share a prefix", () => {
    expect(compareNatural("img", "img1")).toBeLessThan(0);
  });
});
