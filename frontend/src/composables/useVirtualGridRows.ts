import { computed, watch, type CSSProperties, type ComputedRef, type Ref, type WatchSource } from "vue";
import { defaultRangeExtractor, useVirtualizer, type Range } from "@tanstack/vue-virtual";

export interface VirtualGridRow {
  id: string;
}

export interface ChunkedGridRow<T> extends VirtualGridRow {
  items: T[];
}

interface UseVirtualGridRowsOptions<TRow extends VirtualGridRow> {
  rows: ComputedRef<readonly TRow[]>;
  scrollElement: Ref<HTMLElement | null>;
  estimateSize: (index: number) => number;
  overscan?: number;
  measureDeps?: WatchSource[];
  /**
   * Distance between the top of the scroll content and the first row, for lists that sit below other
   * content (album strip, section header) inside the scroll element. Rows are positioned relative to
   * the spacer, so `getVirtualRowStyle` subtracts it again.
   */
  scrollMargin?: Ref<number>;
  /**
   * Caps how many rows are rendered, counted from the first row of the range (default: no cap). A grid that
   * mounts many cards at once raises the cap in steps, one task each, so no single task renders them all.
   * `Infinity` removes the cap.
   */
  rowBudget?: Ref<number>;
}

/** Range extractor that keeps at most `budget` rows, counted from the first row of the range. */
export const budgetedRangeExtractor =
  (budget: number) =>
  (range: Range): number[] => {
    const indexes = defaultRangeExtractor(range);
    return Number.isFinite(budget) ? indexes.slice(0, Math.max(0, budget)) : indexes;
  };

export const chunkItems = <T>(items: readonly T[], chunkSize: number): T[][] => {
  const size = Math.max(1, chunkSize);
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    rows.push(items.slice(i, i + size));
  }
  return rows;
};

export const chunkGridRows = <T>(
  items: readonly T[],
  chunkSize: number,
  createId: (items: readonly T[], rowIndex: number, startIndex: number) => string,
): ChunkedGridRow<T>[] =>
  chunkItems(items, chunkSize).map((rowItems, rowIndex) => ({
    id: createId(rowItems, rowIndex, rowIndex * Math.max(1, chunkSize)),
    items: rowItems,
  }));

export function useVirtualGridRows<TRow extends VirtualGridRow>({
  rows,
  scrollElement,
  estimateSize,
  overscan = 5,
  measureDeps = [],
  scrollMargin,
  rowBudget,
}: UseVirtualGridRowsOptions<TRow>) {
  const virtualizer = useVirtualizer<HTMLElement, HTMLElement>(
    computed(() => ({
      count: rows.value.length,
      getScrollElement: () => scrollElement.value,
      estimateSize,
      overscan,
      rangeExtractor: rowBudget ? budgetedRangeExtractor(rowBudget.value) : defaultRangeExtractor,
      scrollMargin: scrollMargin?.value ?? 0,
      getItemKey: (index: number) => rows.value[index]?.id ?? index,
    })),
  );

  watch(
    [() => rows.value.length, ...measureDeps],
    () => {
      virtualizer.value.measure();
    },
    { flush: "post" },
  );

  const virtualItems = computed(() => virtualizer.value.getVirtualItems());
  const totalSize = computed(() => virtualizer.value.getTotalSize());
  const virtualSpacerStyle = computed<CSSProperties>(() => ({
    height: `${totalSize.value}px`,
    position: "relative",
  }));

  const getVirtualRowStyle = (start: number, extraStyle: CSSProperties = {}): CSSProperties => ({
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    transform: `translateY(${start - (scrollMargin?.value ?? 0)}px)`,
    ...extraStyle,
  });

  return {
    virtualizer,
    virtualItems,
    totalSize,
    virtualSpacerStyle,
    getVirtualRowStyle,
  };
}
