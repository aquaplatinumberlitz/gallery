import { computed } from "vue";
import { useGalleryStore } from "../stores/gallery";
import { useScanQuery } from "./useScanQuery";

export function useCurrentScanQuery() {
  const galleryStore = useGalleryStore();
  const scanPath = computed(() => galleryStore.currentPath || galleryStore.rootPath);
  const scanQuery = useScanQuery(scanPath);

  const folders = computed(() => scanQuery.data.value?.folders ?? []);
  const firstPageImages = computed(() => scanQuery.data.value?.images ?? []);
  const nextCursor = computed(() => scanQuery.data.value?.next_cursor ?? null);
  const totalImages = computed(() => scanQuery.data.value?.total_images ?? 0);

  return {
    ...scanQuery,
    scanPath,
    folders,
    firstPageImages,
    nextCursor,
    totalImages,
  };
}
