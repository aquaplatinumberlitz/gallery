/**
 * Purpose: Choose the count shown in the search results "Media" header.
 * Guarantees: Uses the total from the `search-count` query, with the Advanced Search drawer's `+` convention when the
 * count says more exist (`has_more`/capped) and more pages remain; falls back to the loaded count while the total is
 * pending or failed; and once every page is loaded the loaded count is exact, so no `+` is shown.
 * Run when: Changing the results header count or the count endpoint contract.
 */
export interface SearchMediaTotal {
  total: number;
  hasMore: boolean;
}

export function formatSearchMediaCount(
  loaded: number,
  total: SearchMediaTotal | null | undefined,
  hasNextPage: boolean,
): number | string {
  if (!hasNextPage || !total) return loaded;
  const shown = Math.max(total.total, loaded);
  return total.hasMore ? `${shown}+` : shown;
}
