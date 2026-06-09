import { useLiveQuery } from "../index";
import { landingPagesCollection } from "../collections/landingPagesCollection";

export function useLandingPagesLiveQuery() {
  return useLiveQuery((query) =>
    query
      .from({ landingPage: landingPagesCollection })
      .orderBy(({ landingPage }) => landingPage.index, "asc")
      .select(({ landingPage }) => ({
        url: landingPage.url,
        index: landingPage.index,
      })),
  );
}
