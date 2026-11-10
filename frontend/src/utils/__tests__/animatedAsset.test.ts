/**
 * Purpose: Pin the single definition of "animated image" the grid hover preview and the lightbox share.
 * Guarantees: A detected value (`animated` true or false) always wins over the file extension; an unknown value
 * (null or absent) is animated only for `.gif`, and a `.webp`, `.png` or `.apng` is never guessed animated.
 * Run when: Changing `isAnimatedAsset`, the row `animated` field, or its callers (PhotoCard, buildPhotoSwipeItem).
 */
import { describe, expect, it } from "vitest";
import { isAnimatedAsset } from "../animatedAsset";

describe("isAnimatedAsset", () => {
  it("trusts a detected value over the extension", () => {
    expect(isAnimatedAsset({ animated: true, path: "/a/moving.webp" })).toBe(true);
    expect(isAnimatedAsset({ animated: true, path: "/a/moving.png" })).toBe(true);
    expect(isAnimatedAsset({ animated: false, path: "/a/still.webp" })).toBe(false);
    expect(isAnimatedAsset({ animated: false, path: "/a/still.gif" })).toBe(false);
  });

  it("treats an unknown value as animated only for .gif", () => {
    for (const animated of [null, undefined]) {
      expect(isAnimatedAsset({ animated, path: "/a/x.gif" })).toBe(true);
      expect(isAnimatedAsset({ animated, path: "/a/x.GIF" })).toBe(true);
      expect(isAnimatedAsset({ animated, path: "/a/x.webp" })).toBe(false);
      expect(isAnimatedAsset({ animated, path: "/a/x.png" })).toBe(false);
      expect(isAnimatedAsset({ animated, path: "/a/x.apng" })).toBe(false);
      expect(isAnimatedAsset({ animated, path: "/a/x.jpg" })).toBe(false);
    }
  });

  it("falls back to the name when the path is empty or missing", () => {
    expect(isAnimatedAsset({ path: "", name: "anim.gif" })).toBe(true);
    expect(isAnimatedAsset({ name: "anim.webp" })).toBe(false);
  });

  it("strips query strings and fragments and reads the last segment's extension", () => {
    expect(isAnimatedAsset({ path: "photo.gif?width=100" })).toBe(true);
    expect(isAnimatedAsset({ path: "photo.gif#frag" })).toBe(true);
    expect(isAnimatedAsset({ path: "photo.png?v=2" })).toBe(false);
    expect(isAnimatedAsset({ path: "/my.album/photo.gif" })).toBe(true);
    expect(isAnimatedAsset({ path: "/my.album/photo.png" })).toBe(false);
  });

  it("is false for no path, no name and no extension", () => {
    expect(isAnimatedAsset({})).toBe(false);
    expect(isAnimatedAsset({ path: "" })).toBe(false);
    expect(isAnimatedAsset({ path: "photo" })).toBe(false);
  });
});
