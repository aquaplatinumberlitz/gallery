import { createCollection, queryCollectionOptions, queryClient } from "../index";
import { fetchLandingPages } from "../../services/api";
import { queryKeys } from "../../query/keys";

export interface LandingPage {
  url: string;
  index: number;
}

export const landingPagesQueryKey = queryKeys.landingPages();

export const landingPagesCollection = createCollection(
  queryCollectionOptions({
    id: "landing-pages",
    queryKey: landingPagesQueryKey,
    queryFn: async (): Promise<LandingPage[]> => {
      const pages = await fetchLandingPages();
      const seenUrls = new Set<string>();
      return pages.flatMap((url, index) => {
        if (seenUrls.has(url)) return [];
        seenUrls.add(url);
        return [{ url, index }];
      });
    },
    queryClient,
    getKey: (page) => page.url,
  }),
);
