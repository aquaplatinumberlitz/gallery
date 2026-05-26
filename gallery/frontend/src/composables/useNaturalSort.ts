import { computed, type Ref } from 'vue'
import type { FileNode } from '../types'

export function naturalSortKey(s: string): (string | number)[] {
  return s.split(/(\d+)/).map(part => {
    const num = parseInt(part, 10);
    return isNaN(num) ? part.toLowerCase() : num;
  });
}

export function compareNatural(a: string, b: string): number {
  const aParts = naturalSortKey(a);
  const bParts = naturalSortKey(b);
  for (let i = 0; i < Math.max(aParts.length, bParts.length); i++) {
    const aPart = aParts[i] ?? "";
    const bPart = bParts[i] ?? "";
    if (typeof aPart === "number" && typeof bPart === "number") {
      if (aPart !== bPart) return aPart - bPart;
    } else {
      const cmp = String(aPart).localeCompare(String(bPart));
      if (cmp !== 0) return cmp;
    }
  }
  return 0;
}

export function useNaturalSort(items: Ref<FileNode[]>) {
  const sorted = computed(() => {
    return [...items.value].sort((a, b) => compareNatural(a.name, b.name))
  })
  return { sorted }
}
