import { useLiveQuery } from "../index";
import { landingPagesCollection } from "../collections/landingPagesCollection";

export function useLandingPagesLiveQuery() {
  return useLiveQuery((query) =>
    query.from({ landingPage: landingPagesCollection }).select(({ landingPage }) => ({
      url: landingPage.url,
    })),
  );
}

