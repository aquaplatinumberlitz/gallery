import { computed, nextTick, shallowRef, toValue, watch, type MaybeRefOrGetter } from "vue";
import { watchDebounced } from "@vueuse/core";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";
import { useGalleryStore } from "@/stores/gallery";
import type { RegisteredLibrary, SearchQueryRequestV1 } from "@/types";
import { buildSearchRequestV1, emptySearchFilters } from "@/utils/searchRequest";
import { decodeSearchUrlQuery, encodeSearchUrlQuery, SEARCH_URL_KEYS } from "@/utils/searchUrlCodec";

const joinCatalogPath = (root: string, relativePath: string): string => {
  if (!relativePath) return root;
  return `${root.replace(/[\\/]+$/, "")}/${relativePath}`.replace(/\\/g, "/").replace(/\/+/g, "/");
};

const searchQuerySignature = (query: Record<string, unknown>): string =>
  SEARCH_URL_KEYS.map((key) => `${key}=${String(query[key] ?? "")}`).join("&");

export function useSearchUrlSync(libraries: MaybeRefOrGetter<RegisteredLibrary[]>, ready: MaybeRefOrGetter<boolean>) {
  const route = useRoute();
  const router = useRouter();
  const store = useGalleryStore();
  const hydrated = shallowRef(false);
  const applyingRoute = shallowRef(false);
  const writingRoute = shallowRef(false);
  const sawSearchState = shallowRef(false);

  const currentRequest = computed(() =>
    buildSearchRequestV1({
      text: store.searchQuery,
      scope: store.searchScope,
      libraryId: store.activeLibraryId,
      importPathId: store.activeImportPathId,
      importRootPath: store.activeImportRootPath,
      folderPath: store.currentBrowsePath || store.activeImportRootPath,
      mode: store.searchMode,
      filters: store.searchFilters,
    }),
  );

  const queryWithoutSearch = (): LocationQueryRaw => {
    const query: LocationQueryRaw = { ...route.query };
    for (const key of SEARCH_URL_KEYS) delete query[key];
    return query;
  };

  const writeRequest = async (method: "push" | "replace") => {
    if (!hydrated.value || applyingRoute.value || writingRoute.value) return;
    const encoded = currentRequest.value ? encodeSearchUrlQuery(currentRequest.value) : {};
    sawSearchState.value = currentRequest.value !== null;
    const nextQuery = { ...queryWithoutSearch(), ...encoded };
    if (method === "replace" && searchQuerySignature(nextQuery) === searchQuerySignature(route.query)) return;
    writingRoute.value = true;
    try {
      await router[method]({ name: "gallery", query: nextQuery });
    } finally {
      await nextTick();
      writingRoute.value = false;
    }
  };

  const applyRequest = (request: SearchQueryRequestV1): boolean => {
    const availableLibraries = toValue(libraries);
    const scope = request.scope;
    if (scope.kind === "folder") {
      const library = availableLibraries.find((item) => item.id === scope.library_id);
      const importPath = library?.import_paths.find((item) => item.id === scope.import_path_id);
      if (!library || !importPath) return false;
      store.applyActiveSelection(library, importPath, joinCatalogPath(importPath.path, scope.relative_path));
      store.setSearchScope("current", false);
    } else if (scope.kind === "library") {
      const library = availableLibraries.find((item) => item.id === scope.library_id);
      if (!library) return false;
      if (store.activeLibraryId !== library.id && library.import_paths[0]) store.setActiveLibrary(library);
      store.setSearchScope("library", false);
    } else {
      store.setSearchScope("all", false);
    }
    store.setSearchMode(request.mode, false);
    store.setSearchFilters(request.filters, false);
    store.setSearchQuery(request.text);
    store.submittedSearchQuery = request.text.trim();
    return true;
  };

  const applyRoute = async (initial = false) => {
    if (!toValue(ready) || writingRoute.value) return;
    const decoded = decodeSearchUrlQuery(route.query);
    applyingRoute.value = true;
    try {
      if (decoded.invalid || (decoded.request && !applyRequest(decoded.request))) {
        store.clearSearch();
        store.setSearchMode("lexical", false);
        store.setSearchFilters(emptySearchFilters(), false);
        sawSearchState.value = false;
        await router.replace({ name: "gallery", query: queryWithoutSearch() });
      } else if (decoded.request) {
        sawSearchState.value = true;
      } else if (!initial && sawSearchState.value) {
        store.clearSearch();
        store.setSearchMode("lexical", false);
        store.setSearchFilters(emptySearchFilters(), false);
        sawSearchState.value = false;
      }
    } finally {
      applyingRoute.value = false;
      hydrated.value = true;
    }
  };

  watch(
    () => toValue(ready),
    (isReady) => {
      if (isReady && !hydrated.value) void applyRoute(true);
    },
    { immediate: true },
  );

  watch(
    () => route.fullPath,
    () => {
      if (hydrated.value && !writingRoute.value && !applyingRoute.value) void applyRoute();
    },
  );

  watchDebounced(
    () => store.searchQuery,
    () => void writeRequest("replace"),
    { debounce: 250, maxWait: 750 },
  );

  watch(
    () => store.searchNavigationVersion,
    () => void writeRequest("push"),
  );

  watch(
    [() => store.currentBrowsePath, () => store.activeLibraryId, () => store.activeImportPathId],
    () => void writeRequest("replace"),
  );

  return { hydrated, currentRequest };
}
