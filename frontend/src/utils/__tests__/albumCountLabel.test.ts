import { describe, expect, it } from "vitest";
import { albumCountLabel } from "../albumCountLabel";

describe("albumCountLabel", () => {
  it("pluralizes direct photo counts", () => {
    expect(albumCountLabel({ image_count: 1, has_children: true })).toBe("1 photo");
    expect(albumCountLabel({ image_count: 18, has_children: true })).toBe("18 photos");
  });

  it("does not claim 0 photos for a folder that only holds subfolders or videos", () => {
    expect(albumCountLabel({ image_count: 0, has_children: true })).toBeNull();
  });

  it("marks folders without children as empty", () => {
    expect(albumCountLabel({ image_count: 0, has_children: false })).toBe("Empty");
  });

  it("hides the label when the count is unknown", () => {
    expect(albumCountLabel({ image_count: undefined, has_children: true })).toBeNull();
  });
});
