import { computed, type Ref } from "vue";
import { useFacetsQuery } from "@/composables/useFacetsQuery";
import { useGalleryStore } from "@/stores/gallery";
import type { PromptPresenceFilter, SearchScope } from "@/types";

interface UseLibraryInspectorFiltersOptions {
  scope: Ref<SearchScope>;
  currentPath: Ref<string>;
}

export function useLibraryInspectorFilters({ scope, currentPath }: UseLibraryInspectorFiltersOptions) {
  const galleryStore = useGalleryStore();

  const modelFilter = computed({
    get: () => galleryStore.metadataInspector.modelFilter,
    set: (value: string) => {
      galleryStore.metadataInspector.modelFilter = value;
    },
  });
  const promptFilter = computed<PromptPresenceFilter>({
    get: () => galleryStore.metadataInspector.promptFilter,
    set: (value) => {
      galleryStore.metadataInspector.promptFilter = value;
    },
  });

  const facetPath = computed(() => (scope.value === "all" ? null : currentPath.value || undefined));
  const facetsQuery = useFacetsQuery(facetPath, true, true);
  const modelOptions = computed(() => {
    const options = new Set(facetsQuery.data.value?.model?.map((entry) => entry.value) ?? []);
    if (modelFilter.value !== "all") options.add(modelFilter.value);
    return Array.from(options).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  });
  const activeFilterCount = computed(() => Number(modelFilter.value !== "all") + Number(promptFilter.value !== "all"));

  return {
    modelFilter,
    promptFilter,
    modelOptions,
    activeFilterCount,
  };
}
