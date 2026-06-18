import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { nextTick } from "vue";
import { ref } from "vue";
import {
  DEFAULT_PHOTO_GRID_LEVEL,
  GRID_COLUMN_MAP,
  PHOTO_GRID_LEVELS,
  useColumnResize,
  type DeviceCategory,
} from "../useColumnResize";
import { withSetup } from "@/test/withSetup";

describe("useColumnResize constants", () => {
  it("exposes 5 photo grid levels from Compact to Largest", () => {
    expect(PHOTO_GRID_LEVELS).toHaveLength(5);
    expect(PHOTO_GRID_LEVELS.map((l) => l.level)).toEqual([1, 2, 3, 4, 5]);
    expect(PHOTO_GRID_LEVELS.map((l) => l.columns)).toEqual([8, 7, 6, 5, 4]);
  });

  it("defaults to level 3 (Medium)", () => {
    expect(DEFAULT_PHOTO_GRID_LEVEL).toBe(3);
  });

  it("provides a responsive column map for desktop, tablet, and mobile", () => {
    expect(GRID_COLUMN_MAP.desktop).toEqual([8, 7, 6, 5, 4]);
    expect(GRID_COLUMN_MAP.tablet).toEqual([5, 5, 4, 3, 3]);
    expect(GRID_COLUMN_MAP.mobile).toEqual([3, 3, 2, 2, 2]);
  });
});

describe("useColumnResize", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts at the default slider level", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(DEFAULT_PHOTO_GRID_LEVEL);
  });

  it("exposes effectiveColumnCount === columnCount alias for backward compatibility", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.columnCount.value).toBe(result.effectiveColumnCount.value);
  });

  it("maps slider level 1 (Compact) to 8 columns on desktop", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = 1;
    expect(result.effectiveColumnCount.value).toBe(8);
  });

  it("maps slider level 5 (Largest) to 4 columns on desktop", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = 5;
    expect(result.effectiveColumnCount.value).toBe(4);
  });

  it("uses the tablet column map when deviceCategory is 'tablet'", () => {
    const { result } = withSetup(() => useColumnResize("tablet"));
    result.sliderLevel.value = 3;
    expect(result.effectiveColumnCount.value).toBe(GRID_COLUMN_MAP.tablet[2]);
  });

  it("uses the mobile column map when deviceCategory is 'mobile'", () => {
    const { result } = withSetup(() => useColumnResize("mobile"));
    result.sliderLevel.value = 1;
    expect(result.effectiveColumnCount.value).toBe(GRID_COLUMN_MAP.mobile[0]);
  });

  it("falls back to the desktop column map for an unknown device category", () => {
    const { result } = withSetup(() => useColumnResize("laptop" as DeviceCategory));
    result.sliderLevel.value = 1;
    expect(result.effectiveColumnCount.value).toBe(GRID_COLUMN_MAP.desktop[0]);
  });

  it("accepts a ref for deviceCategory and reacts to changes", () => {
    const device = ref<DeviceCategory>("desktop");
    const { result } = withSetup(() => useColumnResize(device));
    result.sliderLevel.value = 1;
    expect(result.effectiveColumnCount.value).toBe(8);
    device.value = "mobile";
    expect(result.effectiveColumnCount.value).toBe(3);
  });

  it("clamps slider level below 1 to the first column count", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = -1;
    expect(result.effectiveColumnCount.value).toBe(8);
  });

  it("clamps slider level above 5 to the last column count", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = 99;
    expect(result.effectiveColumnCount.value).toBe(4);
  });

  it("persists the slider level to localStorage when it changes", async () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = 2;
    await nextTick();
    expect(window.localStorage.getItem("gallery-grid-size")).toBe("2");
  });

  it("loads the saved slider level from localStorage on mount when valid (1-5)", () => {
    window.localStorage.setItem("gallery-grid-size", "5");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(5);
  });

  it("treats legacy raw column counts in the 1-5 range as new level values (no migration)", () => {
    // Values 1-5 are interpreted as new level-based values, not legacy column counts.
    window.localStorage.setItem("gallery-grid-size", "2");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(2);
  });

  it("migrates a legacy raw column count of 6 (outside 1-5) to level 3 (Medium, 6 cols)", () => {
    window.localStorage.setItem("gallery-grid-size", "6");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(3);
  });

  it("migrates a legacy raw column count of 7 to level 2 (Small, 7 cols)", () => {
    window.localStorage.setItem("gallery-grid-size", "7");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(2);
  });

  it("migrates a legacy raw column count (4-8) to the matching level for stored=8", () => {
    window.localStorage.setItem("gallery-grid-size", "8");
    const { result } = withSetup(() => useColumnResize("desktop"));
    // 8 columns maps to level 1 (Compact)
    expect(result.sliderLevel.value).toBe(1);
  });

  it("migrates a legacy raw column count > 8 by clamping to 8 then mapping to level 1", () => {
    window.localStorage.setItem("gallery-grid-size", "99");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(1);
  });

  it("migrates a legacy raw column count of 0 to the default level 3 (fallback)", () => {
    // 0 is outside 1-5 and migrateColumnsToLevel falls back to default.
    window.localStorage.setItem("gallery-grid-size", "0");
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(DEFAULT_PHOTO_GRID_LEVEL);
  });

  it("falls back to the default level when localStorage throws on read (Safari Private Browsing)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("localStorage unavailable");
    });
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.sliderLevel.value).toBe(DEFAULT_PHOTO_GRID_LEVEL);
  });

  it("does not throw when localStorage throws on write", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("localStorage unavailable");
    });
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(() => {
      result.sliderLevel.value = 4;
    }).not.toThrow();
  });

  it("recomputeRowHeight updates rowHeight based on width, column count, and gap", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    result.sliderLevel.value = 3; // 6 columns on desktop
    // We can't call recomputeRowHeight directly (it's not returned), but
    // setGridRef(el) calls it. Use a real HTMLElement to trigger the path.
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", {
      configurable: true,
      value: () => ({ width: 1024, height: 0, x: 0, y: 0, top: 0, left: 0, right: 1024, bottom: 0, toJSON: () => {} }),
    });
    result.setGridRef(el);
    // 6 columns, GAP=20: totalGap = 20*(6-1)=100; itemWidth = (1024-100)/6 = 154; rowHeight = 154+20 = 174
    expect(result.rowHeight.value).toBeCloseTo(174, 0);
  });

  it("setGridRef(null) disconnects any existing ResizeObserver without throwing", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    const el = document.createElement("div");
    result.setGridRef(el);
    expect(() => result.setGridRef(null)).not.toThrow();
  });

  it("recomputeRowHeight ignores zero-width reports from getBoundingClientRect but the ResizeObserver mock fires with 1024", () => {
    // The setup file's ResizeObserver mock fires synchronously with width=1024,
    // so setGridRef always recomputes rowHeight from that width regardless of
    // getBoundingClientRect. We verify the helper tolerates a zero bounding
    // rect without throwing and the observer-driven recompute still wins.
    const { result } = withSetup(() => useColumnResize("desktop"));
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", {
      configurable: true,
      value: () => ({ width: 0, height: 0, x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, toJSON: () => {} }),
    });
    expect(() => result.setGridRef(el)).not.toThrow();
    // The ResizeObserver mock reported 1024, so rowHeight is non-zero.
    expect(result.rowHeight.value).toBeGreaterThan(0);
  });

  it("reacts to slider level changes by recomputing rowHeight when a grid ref is set", async () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", {
      configurable: true,
      value: () => ({ width: 1024, height: 0, x: 0, y: 0, top: 0, left: 0, right: 1024, bottom: 0, toJSON: () => {} }),
    });
    result.setGridRef(el);
    result.sliderLevel.value = 3;
    await nextTick();
    const rowHeightAt6Cols = result.rowHeight.value;
    result.sliderLevel.value = 1; // 8 columns
    await nextTick();
    const rowHeightAt8Cols = result.rowHeight.value;
    expect(rowHeightAt8Cols).toBeLessThan(rowHeightAt6Cols);
  });

  it("exposes the GAP constant (20)", () => {
    const { result } = withSetup(() => useColumnResize("desktop"));
    expect(result.GAP).toBe(20);
  });
});
