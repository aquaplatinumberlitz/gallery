import { computed, ref, watch, type ComponentPublicInstance, type Ref } from "vue";
import { useResizeObserver, useLocalStorage } from "@vueuse/core";

const GAP = 20;
export const GRID_SIZE_KEY = "gallery-grid-size";

/**
 * Apple HIG-inspired 5-level thumbnail size / grid density mapping.
 * Level 1 (Compact) = 8 columns (smallest thumbnails)
 * Level 5 (Largest) = 4 columns (largest thumbnails)
 * Default: Level 3 (Medium) = 6 columns
 */
export const PHOTO_GRID_LEVELS = [
  { level: 1, label: "Compact", columns: 8 },
  { level: 2, label: "Small", columns: 7 },
  { level: 3, label: "Medium", columns: 6 },
  { level: 4, label: "Large", columns: 5 },
  { level: 5, label: "Largest", columns: 4 },
] as const;

export type PhotoGridLevel = (typeof PHOTO_GRID_LEVELS)[number]["level"];
export const DEFAULT_PHOTO_GRID_LEVEL: PhotoGridLevel = 3;

/**
 * Responsive column mapping by device category.
 * Maps slider level (1-5) to actual column count per device category.
 */
export const GRID_COLUMN_MAP = {
  desktop: [8, 7, 6, 5, 4],
  tablet: [5, 5, 4, 3, 3],
  mobile: [3, 3, 2, 2, 2],
} as const;

export type DeviceCategory = keyof typeof GRID_COLUMN_MAP;

/**
 * Migrate old localStorage value (1–8 raw column count) to new level-based value.
 * Old values 1,2,3 → default level 3 (6 cols, Medium).
 * Old values > 8 → clamp to 8 → level 1 (Compact).
 * Valid old values 4–8 map to the appropriate level.
 */
function migrateColumnsToLevel(stored: number): number {
  if (stored >= 1 && stored <= 3) return DEFAULT_PHOTO_GRID_LEVEL;
  const clamped = Math.min(stored, 8);
  const entry = PHOTO_GRID_LEVELS.find((l) => l.columns === clamped);
  return entry?.level ?? DEFAULT_PHOTO_GRID_LEVEL;
}

export function useColumnResize(deviceCategory: DeviceCategory | Ref<DeviceCategory> = "desktop") {
  // Read raw value with migration + Safari Private Browsing safety
  let initialLevel: PhotoGridLevel = DEFAULT_PHOTO_GRID_LEVEL;
  if (typeof window !== "undefined") {
    try {
      const rawStored = localStorage.getItem(GRID_SIZE_KEY);
      if (rawStored !== null) {
        const num = Number(rawStored);
        if (!Number.isNaN(num)) {
          if (num >= 1 && num <= PHOTO_GRID_LEVELS.length) {
            initialLevel = num as PhotoGridLevel;
          } else {
            initialLevel = migrateColumnsToLevel(num) as PhotoGridLevel;
          }
        }
      }
      // Clear so useLocalStorage uses our computed initialLevel
      localStorage.removeItem(GRID_SIZE_KEY);
    } catch {
      // Safari Private Browsing — localStorage throws; use default
    }
  }

  // useLocalStorage syncs changes back automatically, wraps try/catch for Safari
  const sliderLevel = useLocalStorage<number>(GRID_SIZE_KEY, initialLevel);

  const rowHeight = ref(0);
  const gridRef = ref<HTMLElement | null>(null);
  const lastGridWidth = ref(0);

  /** Reactive device category — works with plain string, ref, or computed ref */
  const _deviceCategory = typeof deviceCategory === "string" ? ref(deviceCategory) : deviceCategory;

  /**
   * Effective photo grid column count derived from slider level,
   * mapped through the responsive grid column map for the current device category.
   */
  const effectiveColumnCount = computed(() => {
    const map = GRID_COLUMN_MAP[_deviceCategory.value] ?? GRID_COLUMN_MAP.desktop;
    const idx = Math.min(Math.max(sliderLevel.value - 1, 0), 4);
    return map[idx];
  });

  /** Alias for backward compatibility with template bindings */
  const columnCount = effectiveColumnCount;

  const recomputeRowHeight = (width: number) => {
    if (!width) return;
    lastGridWidth.value = width;
    const totalGap = GAP * (effectiveColumnCount.value - 1);
    const itemWidth = (width - totalGap) / effectiveColumnCount.value;
    rowHeight.value = itemWidth + GAP; // include vertical gap
  };

  // VueUse useResizeObserver handles lifecycle (disconnect on ref change / unmount)
  useResizeObserver(gridRef, (entries) => {
    const entry = entries[0];
    if (entry) {
      recomputeRowHeight(entry.contentRect.width);
    }
  });

  const setGridRef = (el: Element | ComponentPublicInstance | null) => {
    if (el && el instanceof HTMLElement) {
      gridRef.value = el;
      const initialWidth = el.getBoundingClientRect().width;
      if (initialWidth) {
        recomputeRowHeight(initialWidth);
      }
    } else {
      gridRef.value = null;
    }
  };

  watch(sliderLevel, (_val: number) => {
    if (lastGridWidth.value) {
      recomputeRowHeight(lastGridWidth.value);
    }
  });

  return {
    /** Slider level (1-5) for UI binding */
    sliderLevel,
    /** Effective column count derived from slider level */
    effectiveColumnCount,
    /** Alias for backward compatibility */
    columnCount,
    rowHeight,
    setGridRef,
    GAP,
  };
}
