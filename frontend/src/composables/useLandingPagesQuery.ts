import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchLandingPages } from "@/services/api";
import { isSelectableLandingPage } from "@/utils/introPage";

export interface LandingPage {
  url: string;
  index: number;
}

/**
 * Keep the first occurrence of each landing-page URL, preserving its position in the API response.
 *
 * `/api/landing-pages` returns the complete list in display order; the explicit `index` keeps that
 * order available to consumers that re-sort or filter the rows. Pages that are not real themes
 * (the developer `sample_test` page) are dropped, so Settings never offers them.
 */
export function normalizeLandingPages(urls: readonly string[]): LandingPage[] {
  const seenUrls = new Set<string>();
  return urls.flatMap((url, index) => {
    if (seenUrls.has(url) || !isSelectableLandingPage(url)) return [];
    seenUrls.add(url);
    return [{ url, index }];
  });
}

export function useLandingPagesQuery() {
  return useQuery({
    queryKey: queryKeys.landingPages(),
    queryFn: async (): Promise<LandingPage[]> => normalizeLandingPages(await fetchLandingPages()),
  });
}
