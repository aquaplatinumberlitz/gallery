import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY,
  LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD,
  LIGHTBOX_PREVIEW_EDGE,
  LIGHTBOX_THUMBNAIL_EDGE,
  buildPhotoSwipeItem,
  hasValidDimensions,
  shouldAlwaysLoadOriginal,
} from "../lightbox";
import type { FileNode } from "@/types";

function makeNode(overrides: Partial<FileNode> = {}): FileNode {
  return {
    name: "photo.png",
    path: "/album/photo.png",
    type: "image",
    ...overrides,
  };
}

describe("constants", () => {
  it("exposes stable lightbox edge sizes and zoom threshold", () => {
    expect(LIGHTBOX_THUMBNAIL_EDGE).toBe(512);
    expect(LIGHTBOX_PREVIEW_EDGE).toBe(1440);
    expect(LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD).toBe(1.2);
    expect(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY).toBe("gallery-lightbox-always-load-original");
  });
});

describe("hasValidDimensions", () => {
  it("returns true for positive width and height numbers", () => {
    expect(hasValidDimensions({ width: 100, height: 200 })).toBe(true);
  });

  it("returns false when width or height is 0", () => {
    expect(hasValidDimensions({ width: 0, height: 200 })).toBe(false);
    expect(hasValidDimensions({ width: 100, height: 0 })).toBe(false);
  });

  it("returns false when width or height is negative", () => {
    expect(hasValidDimensions({ width: -1, height: 200 })).toBe(false);
  });

  it("returns false when width or height is missing", () => {
    expect(hasValidDimensions({ width: 100 })).toBe(false);
    expect(hasValidDimensions({ height: 200 })).toBe(false);
    expect(hasValidDimensions({})).toBe(false);
  });

  it("returns false for null or undefined input", () => {
    expect(hasValidDimensions(null)).toBe(false);
    expect(hasValidDimensions(undefined)).toBe(false);
  });

  it("returns false for non-number values", () => {
    expect(hasValidDimensions({ width: "100" as unknown as number, height: "200" as unknown as number })).toBe(false);
  });

  it("narrows the type so width/height are usable as numbers after a truthy check", () => {
    const dims: { width?: number | null; height?: number | null } | null = { width: 10, height: 20 };
    if (hasValidDimensions(dims)) {
      // Type narrowing makes these `number` inside the block.
      expect(dims.width + dims.height).toBe(30);
    } else {
      throw new Error("should have been valid");
    }
  });
});

describe("shouldAlwaysLoadOriginal", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns false by default when the localStorage key is absent", () => {
    expect(shouldAlwaysLoadOriginal()).toBe(false);
  });

  it("returns true when the localStorage key is set to 'true'", () => {
    window.localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, "true");
    expect(shouldAlwaysLoadOriginal()).toBe(true);
  });

  it("returns false when the localStorage key is set to any other value", () => {
    window.localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, "false");
    expect(shouldAlwaysLoadOriginal()).toBe(false);
    window.localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, "1");
    expect(shouldAlwaysLoadOriginal()).toBe(false);
  });

  it("returns false and swallows errors when localStorage.getItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("localStorage unavailable");
    });
    expect(shouldAlwaysLoadOriginal()).toBe(false);
    spy.mockRestore();
  });
});

describe("buildPhotoSwipeItem", () => {
  it("uses the provided dimensions when supplied", () => {
    const item = buildPhotoSwipeItem(makeNode(), { width: 800, height: 600, source: "metadata" });
    expect(item.width).toBe(800);
    expect(item.height).toBe(600);
  });

  it("falls back to 1200x1200 when dimensions are missing", () => {
    const item = buildPhotoSwipeItem(makeNode());
    expect(item.width).toBe(1200);
    expect(item.height).toBe(1200);
  });

  it("falls back to 1200x1200 when dimensions are null", () => {
    const item = buildPhotoSwipeItem(makeNode(), null);
    expect(item.width).toBe(1200);
    expect(item.height).toBe(1200);
  });

  it("builds preview and thumbnail src from the item path with the configured edge sizes", () => {
    const item = buildPhotoSwipeItem(makeNode({ path: "/album/photo.png" }));
    expect(item.src).toContain("/api/preview");
    expect(item.src).toContain(encodeURIComponent("/album/photo.png"));
    expect(item.src).toContain(`max_long_edge=${LIGHTBOX_PREVIEW_EDGE}`);
    expect(item.msrc).toContain("/api/thumbnail");
    expect(item.msrc).toContain(`max_long_edge=${LIGHTBOX_THUMBNAIL_EDGE}`);
    expect(item.previewSrc).toBe(item.src);
  });

  it("copies name into alt and path into path", () => {
    const item = buildPhotoSwipeItem(makeNode({ name: "kitten.png", path: "/pets/kitten.png" }));
    expect(item.alt).toBe("kitten.png");
    expect(item.path).toBe("/pets/kitten.png");
  });

  it("uses an empty alt when the file has no name", () => {
    const item = buildPhotoSwipeItem(makeNode({ name: "" }));
    expect(item.alt).toBe("");
  });

  it("flags animated assets with isAnimatedAsset: a detected value wins, an unknown value is animated only for .gif", () => {
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.gif" })).isAnimatedAsset).toBe(true);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.png" })).isAnimatedAsset).toBe(false);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.webp" })).isAnimatedAsset).toBe(false);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.webp", animated: null })).isAnimatedAsset).toBe(false);
  });

  it("treats an animated WebP, APNG or GIF as animated and a static WebP or GIF as static", () => {
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.webp", animated: true })).isAnimatedAsset).toBe(true);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.png", animated: true })).isAnimatedAsset).toBe(true);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.gif", animated: true })).isAnimatedAsset).toBe(true);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.webp", animated: false })).isAnimatedAsset).toBe(false);
    expect(buildPhotoSwipeItem(makeNode({ path: "/x.gif", animated: false })).isAnimatedAsset).toBe(false);
  });

  it("falls back to the name when path is empty for animated-asset detection", () => {
    expect(buildPhotoSwipeItem(makeNode({ path: "", name: "anim.gif" })).isAnimatedAsset).toBe(true);
  });

  it("does not set original-load flags by default", () => {
    const item = buildPhotoSwipeItem(makeNode());
    expect(item.isOriginalLoaded).toBeUndefined();
    expect(item.originalLoadReason).toBeUndefined();
  });
});
