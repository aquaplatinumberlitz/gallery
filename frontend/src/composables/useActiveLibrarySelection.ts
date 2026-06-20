import { computed } from "vue";
import { useLibrariesQuery } from "@/composables/admin/useLibrariesQuery";
import { resolveActiveImportPath, useGalleryStore } from "@/stores/gallery";

export function useActiveLibrarySelection() {
  const galleryStore = useGalleryStore();
  const librariesQuery = useLibrariesQuery();
  const libraries = computed(() => librariesQuery.data.value ?? []);
  const activeLibrary = computed(
    () => libraries.value.find((library) => library.id === galleryStore.activeLibraryId) ?? null,
  );
  const activeImportPath = computed(() =>
    resolveActiveImportPath(libraries.value, galleryStore.activeLibraryId, galleryStore.activeImportPathId),
  );
  const activeImportRootPath = computed(() => activeImportPath.value?.path ?? "");

  return { librariesQuery, libraries, activeLibrary, activeImportPath, activeImportRootPath };
}
