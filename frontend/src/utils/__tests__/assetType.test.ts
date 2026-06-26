import { describe, it, expect } from "vitest";
import { normalizeAssetType, isMediaAssetType } from "../assetType";

describe("normalizeAssetType", () => {
  it("normalizes image to image", () => expect(normalizeAssetType("image")).toBe("image"));
  it("normalizes photo to image", () => expect(normalizeAssetType("photo")).toBe("image"));
  it("normalizes file to image", () => expect(normalizeAssetType("file")).toBe("image"));
  it("normalizes video to video", () => expect(normalizeAssetType("video")).toBe("video"));
  it("normalizes folder to folder", () => expect(normalizeAssetType("folder")).toBe("folder"));
  it("normalizes undefined to image", () => expect(normalizeAssetType(undefined)).toBe("image"));
  it("normalizes unknown to image", () => expect(normalizeAssetType("unknown")).toBe("image"));
});

describe("isMediaAssetType", () => {
  it("returns true for image", () => expect(isMediaAssetType("image")).toBe(true));
  it("returns true for photo", () => expect(isMediaAssetType("photo")).toBe(true));
  it("returns true for file", () => expect(isMediaAssetType("file")).toBe(true));
  it("returns true for video", () => expect(isMediaAssetType("video")).toBe(true));
  it("returns false for folder", () => expect(isMediaAssetType("folder")).toBe(false));
  it("returns false for undefined", () => expect(isMediaAssetType(undefined)).toBe(false));
  it("returns false for unknown", () => expect(isMediaAssetType("unknown")).toBe(false));
});
