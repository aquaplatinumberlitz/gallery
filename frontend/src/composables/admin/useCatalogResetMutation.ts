import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { GRID_SIZE_KEY } from "@/composables/useColumnResize";
import { router } from "@/router";
import { resetCatalogDatabase } from "@/services/api";
import {
  ACTIVE_IMPORT_PATH_STORAGE_KEY,
  ACTIVE_LIBRARY_STORAGE_KEY,
  LEGACY_ROOT_PATH_STORAGE_KEY,
  SORT_STORAGE_KEY,
  useGalleryStore,
} from "@/stores/gallery";
import { LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY } from "@/utils/lightbox";

const HANDOFF_STORAGE_KEYS = [
  ACTIVE_LIBRARY_STORAGE_KEY,
  ACTIVE_IMPORT_PATH_STORAGE_KEY,
  LEGACY_ROOT_PATH_STORAGE_KEY,
  SORT_STORAGE_KEY,
  GRID_SIZE_KEY,
  LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY,
] as const;

function clearHandoffLocalState() {
  if (typeof window === "undefined") return;
  for (const key of HANDOFF_STORAGE_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export function useCatalogResetMutation() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const galleryStore = useGalleryStore();

  return useMutation({
    mutationFn: (confirmPhrase: string) => resetCatalogDatabase(confirmPhrase),
    onSuccess: async () => {
      clearHandoffLocalState();
      galleryStore.$reset();
      galleryStore.clearActiveLibrary();
      galleryStore.activeLibraryHydrated = true;
      queryClient.clear();
      await router.replace({ name: "gallery" });
      clearHandoffLocalState();
      toast.success("App data reset. Source files were not touched.");
    },
    onError: (error) => toast.error("Could not reset file catalog database", String(error)),
  });
}
