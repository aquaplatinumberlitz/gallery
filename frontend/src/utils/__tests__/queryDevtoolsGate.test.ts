import { afterEach, describe, expect, it, vi } from "vitest";
import { QUERY_DEVTOOLS_STORAGE_KEY, shouldShowQueryDevtools } from "../queryDevtoolsGate";

describe("shouldShowQueryDevtools", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stays hidden in plain dev mode so the floating button cannot cover mobile controls", () => {
    expect(shouldShowQueryDevtools({}, "")).toBe(false);
  });

  it("shows when VITE_DEVTOOLS is true", () => {
    expect(shouldShowQueryDevtools({ VITE_DEVTOOLS: "true" }, "")).toBe(true);
  });

  it("persists ?devtools=1 and clears it with ?devtools=0", () => {
    expect(shouldShowQueryDevtools({}, "?devtools=1")).toBe(true);
    expect(localStorage.getItem(QUERY_DEVTOOLS_STORAGE_KEY)).toBe("1");
    expect(shouldShowQueryDevtools({}, "")).toBe(true);

    expect(shouldShowQueryDevtools({}, "?devtools=0")).toBe(false);
    expect(localStorage.getItem(QUERY_DEVTOOLS_STORAGE_KEY)).toBeNull();
    expect(shouldShowQueryDevtools({}, "")).toBe(false);
  });

  it("falls back to the query param when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(shouldShowQueryDevtools({}, "")).toBe(false);
    expect(shouldShowQueryDevtools({}, "?devtools=1")).toBe(true);
  });
});
