import { describe, it, expect } from "vitest";
import { prefetchMetadataRoute, prefetchLibrariesRoute } from "../index";

describe("router helpers", () => {
  it("prefetchMetadataRoute", () => {
    const r = prefetchMetadataRoute();
    expect(r).toBeInstanceOf(Promise);
  });

  it("prefetchLibrariesRoute", () => {
    const r = prefetchLibrariesRoute();
    expect(r).toBeInstanceOf(Promise);
  });

  it("prefetchMetadataRoute memoizes", () => {
    expect(prefetchMetadataRoute()).toBe(prefetchMetadataRoute());
  });

  it("prefetchLibrariesRoute memoizes", () => {
    expect(prefetchLibrariesRoute()).toBe(prefetchLibrariesRoute());
  });
});
