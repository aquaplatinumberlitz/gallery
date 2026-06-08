import { createCollection, queryCollectionOptions, queryClient } from "../index";
import { fetchLandingPages } from "../../services/api";

export interface LandingPage {
  url: string;
}

export const landingPagesQueryKey = ["landing-pages"] as const;

export const landingPagesCollection = createCollection(
  queryCollectionOptions({
    id: "landing-pages",
    queryKey: landingPagesQueryKey,
    queryFn: async (): Promise<LandingPage[]> => {
      const pages = await fetchLandingPages();
      return pages.map((url) => ({ url }));
    },
    queryClient,
    getKey: (page) => page.url,
  }),
);
