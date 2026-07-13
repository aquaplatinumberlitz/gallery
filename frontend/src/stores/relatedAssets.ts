import { defineStore } from "pinia";
import type { RelatedProfileV1, SearchScopeV1 } from "@/types";

export interface RelatedReference {
  assetId: number;
  path: string;
  name: string;
  libraryId?: number | null;
}

export const useRelatedAssetsStore = defineStore("related-assets", {
  state: () => ({
    isOpen: false,
    reference: null as RelatedReference | null,
    scope: null as SearchScopeV1 | null,
    profile: "related" as RelatedProfileV1,
  }),
  actions: {
    open(reference: RelatedReference, scope: SearchScopeV1) {
      this.reference = { ...reference };
      this.scope = structuredClone(scope);
      this.profile = "related";
      this.isOpen = true;
    },
    setProfile(profile: RelatedProfileV1) {
      this.profile = profile;
    },
    close() {
      this.isOpen = false;
    },
  },
});
