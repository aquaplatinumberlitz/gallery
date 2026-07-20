import { defineStore } from "pinia";
import { toRaw } from "vue";
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
      // toRaw() unwraps Vue reactive Proxy before structuredClone.
      // Without this, scope from item.relation_scope (a reactive computed)
      // causes DataCloneError: Proxy objects are not structuredClone-able.
      this.reference = { ...toRaw(reference) };
      this.scope = structuredClone(toRaw(scope));
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
