import { describe, it, expect } from "vitest";
import { isMediaAssetType, normalizeAssetType } from "../assetType";

describe("normalizeAssetType", () => {
  it("maps the canonical AssetType values through unchanged", () => {
    expect(normalizeAssetType("folder")).toBe("folder");
    expect(normalizeAssetType("image")).toBe("image");
    expect(normalizeAssetType("video")).toBe("video");
  });

  it("normalizes legacy 'photo' and 'file' from the file_index response shape to 'image'", () => {
    expect(normalizeAssetType("photo")).toBe("image");
    expect(normalizeAssetType("file")).toBe("image");
  });

  it("falls back to 'image' for unknown or missing values", () => {
    expect(normalizeAssetType(undefined)).toBe("image");
    expect(normalizeAssetType("")).toBe("image");
    expect(normalizeAssetType("application")).toBe("image");
  });
});

describe("isMediaAssetType", () => {
  it("returns true for image and video (in any legacy spelling)", () => {
    expect(isMediaAssetType("image")).toBe(true);
    expect(isMediaAssetType("video")).toBe(true);
    expect(isMediaAssetType("photo")).toBe(true);
    expect(isMediaAssetType("file")).toBe(true);
  });

  it("returns false for folders and unknown values", () => {
    expect(isMediaAssetType("folder")).toBe(false);
    expect(isMediaAssetType(undefined)).toBe(false);
    expect(isMediaAssetType("application")).toBe(false);
  });
});
