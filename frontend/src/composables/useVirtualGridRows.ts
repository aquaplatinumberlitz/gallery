import { computed, watch, type CSSProperties, type ComputedRef, type Ref, type WatchSource } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";

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
}

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
}: UseVirtualGridRowsOptions<TRow>) {
  const virtualizer = useVirtualizer<HTMLElement, HTMLElement>(
    computed(() => ({
      count: rows.value.length,
      getScrollElement: () => scrollElement.value,
      estimateSize,
      overscan,
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
    transform: `translateY(${start}px)`,
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
