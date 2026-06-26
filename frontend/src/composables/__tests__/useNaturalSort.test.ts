import { describe, it, expect } from "vitest";
import { naturalSortKey, compareNatural } from "../useNaturalSort";

describe("naturalSortKey", () => {
  it("splits text and numbers", () => {
    expect(naturalSortKey("album10")).toEqual(["album", 10, ""]);
  });
  it("handles multiple numbers", () => {
    expect(naturalSortKey("page1of10")).toEqual(["page", 1, "of", 10, ""]);
  });
  it("handles no numbers", () => {
    expect(naturalSortKey("hello")).toEqual(["hello"]);
  });
  it("handles empty string", () => {
    expect(naturalSortKey("")).toEqual([""]);
  });
  it("lowercases text parts", () => {
    const result = naturalSortKey("HelloWorld");
    expect(result[0]).toBe("helloworld");
  });
});

describe("compareNatural", () => {
  it("sorts numbers naturally", () => {
    expect(compareNatural("album2", "album10")).toBeLessThan(0);
  });
  it("sorts alphabetically", () => {
    expect(compareNatural("apple", "banana")).toBeLessThan(0);
  });
  it("returns 0 for equal strings", () => {
    expect(compareNatural("same", "same")).toBe(0);
  });
});
