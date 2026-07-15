import { defineStore } from "pinia";
import type { SearchScopeV1 } from "@/types";

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
  }),
  actions: {
    open(reference: RelatedReference, scope: SearchScopeV1) {
      this.reference = { ...reference };
      this.scope = structuredClone(scope);
      this.isOpen = true;
    },
    close() {
      this.isOpen = false;
    },
    reopen() {
      if (this.reference && this.scope) this.isOpen = true;
    },
  },
});
