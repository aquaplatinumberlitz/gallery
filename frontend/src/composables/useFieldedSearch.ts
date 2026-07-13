import { computed, toValue, type MaybeRefOrGetter } from "vue";
import type { FieldFilter } from "@/types";
import {
  parseSearchQuery,
  replaceManagedFilters as replaceManagedQueryFilters,
  serializeManagedFilters,
} from "@/utils/searchQueryGrammar";

export function useFieldedSearch(rawQuery: MaybeRefOrGetter<string> = "") {
  const parsedQuery = computed(() => parseSearchQuery(toValue(rawQuery)));
  const fieldedFilters = computed(() => parsedQuery.value.managedFilters);
  const passThroughTokens = computed(() => parsedQuery.value.passThroughTokens);
  const residualText = computed(() => parsedQuery.value.residualText);
  const isActive = computed(() => fieldedFilters.value.length > 0);
  const queryString = computed(() => serializeManagedFilters(fieldedFilters.value));

  function applyFilters(filters: FieldFilter[]) {
    return replaceManagedQueryFilters(toValue(rawQuery), filters);
  }

  function removeFilter(index: number) {
    return applyFilters(fieldedFilters.value.filter((_filter, filterIndex) => filterIndex !== index));
  }

  function clearAll() {
    return applyFilters([]);
  }

  return {
    fieldedFilters,
    parsedQuery,
    passThroughTokens,
    residualText,
    isActive,
    queryString,
    applyFilters,
    removeFilter,
    clearAll,
  };
}
