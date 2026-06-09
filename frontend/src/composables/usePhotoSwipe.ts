import { ref, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";
import PhotoSwipe from "photoswipe";
import type { FileNode, MetadataResponse } from "../types";
import { fetchMetadata, getThumbnailUrl } from "../services/api";
import { queryClient } from "../query";
import { queryKeys } from "../query/keys";
import { useLightboxStore } from "../stores/lightbox";
import {
  buildPhotoSwipeItem,
  hasValidDimensions,
  type LightboxDimensions,
  type PhotoSwipeImageItem,
} from "../utils/lightbox";

export interface UsePhotoSwipeOptions {
  containerRef: Ref<HTMLElement | null>;
  items: ComputedRef<FileNode[]>;
  currentIndex: Ref<number>;
  isOpen: Ref<boolean>;
  photoSwipeOptions?: Record<string, unknown>;
  thumbnailSize?: number | null;
  onIndexChange?: (index: number) => void;
  onClose?: () => void;
  onRegisterUi?: (pswp: PhotoSwipe) => void;
  onAfterInit?: (pswp: PhotoSwipe) => void;
}

export function usePhotoSwipe(options: UsePhotoSwipeOptions) {
  const {
    containerRef,
    items,
    currentIndex,
    isOpen,
    photoSwipeOptions = {},
    onIndexChange,
    onClose,
    onRegisterUi,
    onAfterInit,
  } = options;

  const pswp = ref<PhotoSwipe | null>(null);
  const lightboxStore = useLightboxStore();
  const pendingDimensions = new Map<string, Promise<LightboxDimensions | null>>();

  const scanDimensions = (item: FileNode): LightboxDimensions | null =>
    hasValidDimensions(item)
      ? { width: item.width, height: item.height, source: "scan" }
      : null;

  const thumbnailDimensions = (item: FileNode): LightboxDimensions | null =>
    lightboxStore.getRememberedDimensions(item.path) ?? null;

  const cachedMetadataDimensions = (path: string): LightboxDimensions | null => {
    const metadata = queryClient.getQueryData<MetadataResponse>(queryKeys.metadata(path));
    return hasValidDimensions(metadata)
      ? { width: metadata.width, height: metadata.height, source: "metadata" }
      : null;
  };

  const bestKnownDimensions = (item: FileNode): LightboxDimensions | null =>
    scanDimensions(item) ?? thumbnailDimensions(item) ?? cachedMetadataDimensions(item.path);

  const fetchMetadataDimensions = async (path: string): Promise<LightboxDimensions | null> => {
    const metadata = await queryClient.fetchQuery({
      queryKey: queryKeys.metadata(path),
      queryFn: () => fetchMetadata(path),
      staleTime: 10 * 60_000,
      gcTime: 30 * 60_000,
    });

    return hasValidDimensions(metadata)
      ? { width: metadata.width, height: metadata.height, source: "metadata" }
      : null;
  };

  const loadThumbnailDimensions = (path: string): Promise<LightboxDimensions | null> =>
    new Promise((resolve) => {
      if (typeof Image === "undefined") {
        resolve(null);
        return;
      }

      const image = new Image();
      image.onload = () => {
        resolve(
          image.naturalWidth && image.naturalHeight
            ? {
                width: image.naturalWidth,
                height: image.naturalHeight,
                source: "fallback",
              }
            : null
        );
      };
      image.onerror = () => resolve(null);
      image.src = getThumbnailUrl(path);
    });

  const resolveDimensions = (item: FileNode): Promise<LightboxDimensions | null> => {
    const known = scanDimensions(item) ?? thumbnailDimensions(item);
    if (known) return Promise.resolve(known);

    const cachedMetadata = cachedMetadataDimensions(item.path);
    if (cachedMetadata) return Promise.resolve(cachedMetadata);

    const pending = pendingDimensions.get(item.path);
    if (pending) return pending;

    const promise = fetchMetadataDimensions(item.path)
      .catch(() => null)
      .then((metadataDimensions) => metadataDimensions ?? loadThumbnailDimensions(item.path))
      .finally(() => {
        pendingDimensions.delete(item.path);
      });

    pendingDimensions.set(item.path, promise);
    return promise;
  };

  function applyResolvedDimensions(index: number, dimensions: LightboxDimensions) {
    const instance = pswp.value;
    if (!instance) return;

    const dataSource = instance.options.dataSource;
    if (!Array.isArray(dataSource)) return;

    const itemData = dataSource[index] as PhotoSwipeImageItem | undefined;
    if (!itemData || (itemData.width === dimensions.width && itemData.height === dimensions.height)) {
      return;
    }

    itemData.width = dimensions.width;
    itemData.height = dimensions.height;
    lightboxStore.rememberDimensions(itemData.path, dimensions);
    instance.refreshSlideContent(index);
  }

  function resolveAndRefresh(index: number) {
    const item = items.value[index];
    if (!item) return;

    void resolveDimensions(item).then((dimensions) => {
      if (!dimensions || !pswp.value) return;
      applyResolvedDimensions(index, dimensions);
    });
  }

  function initPhotoSwipe() {
    if (!containerRef.value || !isOpen.value || pswp.value) return;

    const dataSource = items.value.map((item) =>
      buildPhotoSwipeItem(item, bestKnownDimensions(item))
    );

    const instance = new PhotoSwipe({
      dataSource,
      index: currentIndex.value,
      appendToEl: containerRef.value,
      showHideAnimationType: "zoom",
      wheelToZoom: false,
      bgOpacity: 1,
      ...photoSwipeOptions,
    });
    pswp.value = instance;

    instance.on("change", () => {
      onIndexChange?.(instance.currIndex);
      resolveAndRefresh(instance.currIndex);
    });

    instance.on("close", () => {
      destroyPhotoSwipe();
      onClose?.();
    });

    if (onRegisterUi) {
      instance.on("uiRegister", () => {
        onRegisterUi(instance);
      });
    }

    instance.init();
    onAfterInit?.(instance);
    resolveAndRefresh(currentIndex.value);
  }

  function destroyPhotoSwipe() {
    if (pswp.value) {
      try {
        pswp.value.destroy();
      } catch (_) {
        // Already destroyed
      }
      pswp.value = null;
    }
  }

  watch(
    () => isOpen.value,
    (open) => {
      if (open) {
        setTimeout(() => initPhotoSwipe(), 0);
      } else {
        destroyPhotoSwipe();
      }
    }
  );

  watch(
    () => currentIndex.value,
    (index) => {
      if (pswp.value && pswp.value.currIndex !== index) {
        pswp.value.goTo(index);
      }
      resolveAndRefresh(index);
    }
  );

  onMounted(() => {
    if (isOpen.value) {
      initPhotoSwipe();
    }
  });

  onUnmounted(() => {
    destroyPhotoSwipe();
  });

  return {
    pswp,
    destroyPhotoSwipe,
  };
}
