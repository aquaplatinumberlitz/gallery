import { compareNatural } from "../composables/useNaturalSort";
import type { SortField, SortOrder } from "../types";

/** Orders gallery items the way the grid shows them: by natural name or by modification time. */
export function sortByPreference<T extends { name: string; mtime?: number }>(
  items: readonly T[],
  field: SortField,
  order: SortOrder,
): T[] {
  const sorted = [...items];
  sorted.sort((a, b) => {
    let cmp = 0;
    if (field === "name") {
      cmp = compareNatural(a.name, b.name);
    } else if (field === "date") {
      cmp = (a.mtime || 0) - (b.mtime || 0);
    }
    return order === "asc" ? cmp : -cmp;
  });
  return sorted;
}
