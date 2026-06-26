import { describe, it, expect } from "vitest";
import { prefetchMetadataRoute, prefetchLibrariesRoute } from "../index";

describe("router helpers", () => {
  // Dynamic imports may complete after environment teardown so we await them
  // to prevent unhandled rejections.

  it("prefetchMetadataRoute returns a Promise", async () => {
    const p = prefetchMetadataRoute();
    expect(p).toBeInstanceOf(Promise);
    try {
      await p;
    } catch {
      /* dynamic import may fail in test env */
    }
  });

  it("prefetchLibrariesRoute returns a Promise", async () => {
    const p = prefetchLibrariesRoute();
    expect(p).toBeInstanceOf(Promise);
    try {
      await p;
    } catch {
      /* dynamic import may fail in test env */
    }
  });

  it("prefetchMetadataRoute memoizes", () => {
    expect(prefetchMetadataRoute()).toBe(prefetchMetadataRoute());
  });

  it("prefetchLibrariesRoute memoizes", () => {
    expect(prefetchLibrariesRoute()).toBe(prefetchLibrariesRoute());
  });
});
