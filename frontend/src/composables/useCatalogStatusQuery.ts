import { useQuery } from "@tanstack/vue-query";
import { computed, onMounted, onUnmounted, ref, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeBrowsePath, queryKeys } from "@/query/keys";
import { fetchCatalogStatus } from "@/services/api";
import { assertStatusEnvelope, isStatusContractError } from "@/lib/catalog/contractGuard";
import { statusRefetchInterval } from "@/lib/catalog/polling";

export function useCatalogStatusQuery(
  libraryId: MaybeRefOrGetter<number | null | undefined>,
  scopePath: MaybeRefOrGetter<string | null | undefined> = null,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const isDocumentHidden = ref(false);
  const resolvedLibraryId = computed(() => toValue(libraryId) ?? null);
  const resolvedPath = computed(() => toValue(scopePath) ?? null);
  const normalizedPath = computed(() => normalizeBrowsePath(resolvedPath.value));
  const queryEnabled = computed(() => Boolean(resolvedLibraryId.value) && toValue(enabled) && !isDocumentHidden.value);

  const queryKey = computed(() => {
    const id = resolvedLibraryId.value;
    if (id === null) return ["status", "disabled"] as const;
    return normalizedPath.value ? queryKeys.statusPath(id, normalizedPath.value) : queryKeys.statusLibrary(id);
  });

  const query = useQuery({
    queryKey,
    queryFn: () => {
      const id = resolvedLibraryId.value;
      if (id === null) {
        throw new Error("Catalog status requires a library id");
      }
      return fetchCatalogStatus(id, normalizedPath.value).then((value) => {
        assertStatusEnvelope(value);
        return value;
      });
    },
    enabled: queryEnabled,
    staleTime: 5_000,
    retry: (failureCount, error) => {
      if (isStatusContractError(error)) return false;
      return failureCount < 1;
    },
    refetchInterval: (q) => statusRefetchInterval(q.state.data?.status, queryEnabled.value),
    refetchOnWindowFocus: () => typeof document === "undefined" || document.visibilityState !== "hidden",
  });

  const contractError = computed(() => (isStatusContractError(query.error.value) ? query.error.value : null));

  let focusTimer: number | undefined;

  function updateDocumentHidden() {
    isDocumentHidden.value = typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  function debouncedFocusRefetch() {
    if (!queryEnabled.value || isDocumentHidden.value || typeof window === "undefined") return;
    window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(() => {
      void query.refetch();
    }, 300);
  }

  function onVisibilityChange() {
    updateDocumentHidden();
    if (!isDocumentHidden.value) debouncedFocusRefetch();
  }

  onMounted(() => {
    updateDocumentHidden();
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", debouncedFocusRefetch);
  });

  onUnmounted(() => {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("focus", debouncedFocusRefetch);
    window.clearTimeout(focusTimer);
  });

  return { ...query, contractError };
}
