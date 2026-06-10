import { ref, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";
import PhotoSwipe from "photoswipe";
import type { FileNode, MetadataResponse } from "../types";
import { fetchMetadata, getPreviewUrl } from "../services/api";
import { queryClient } from "../query";
import { queryKeys } from "../query/keys";
import { useLightboxStore } from "../stores/lightbox";
import {
  buildPhotoSwipeItem,
  hasValidDimensions,
  LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD,
  LIGHTBOX_PREVIEW_EDGE,
  shouldAlwaysLoadOriginal,
  type LightboxDimensions,
  type PhotoSwipeImageItem,
} from "../utils/lightbox";

const shouldExposeLightboxTestHooks =
  import.meta.env.MODE === "test" ||
  import.meta.env.VITE_EXPOSE_LIGHTBOX_TEST_HOOKS === "1";

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
  const originalLoadPromises = new Map<string, Promise<void>>();
  const originalLoadingPath = ref<string | null>(null);

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

  const loadPreviewDimensions = (path: string): Promise<LightboxDimensions | null> =>
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
      image.src = getPreviewUrl(path, LIGHTBOX_PREVIEW_EDGE);
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
      .then((metadataDimensions) => metadataDimensions ?? loadPreviewDimensions(item.path))
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

  function getPhotoSwipeItem(index: number): PhotoSwipeImageItem | null {
    const dataSource = pswp.value?.options.dataSource;
    if (!Array.isArray(dataSource)) return null;
    return (dataSource[index] as PhotoSwipeImageItem | undefined) ?? null;
  }

  function swapCurrentSlideToOriginal(index: number, itemData: PhotoSwipeImageItem, refresh: boolean) {
    const instance = pswp.value;
    if (!instance || instance.currIndex !== index) return;

    if (refresh) {
      instance.refreshSlideContent(index);
      return;
    }

    const content = instance.currSlide?.content;
    const imageElement = content?.element instanceof HTMLImageElement ? content.element : null;
    itemData.src = itemData.originalSrc;
    if (content) {
      content.data.src = itemData.originalSrc;
    }
    if (instance.currSlide) {
      instance.currSlide.data.src = itemData.originalSrc;
    }
    if (imageElement && imageElement.src !== itemData.originalSrc) {
      imageElement.removeAttribute("srcset");
      imageElement.src = itemData.originalSrc;
    }
  }

  function loadOriginalForIndex(
    index: number,
    reason: NonNullable<PhotoSwipeImageItem["originalLoadReason"]>,
    options: { refresh?: boolean } = {}
  ): Promise<void> {
    const itemData = getPhotoSwipeItem(index);
    if (!itemData?.originalSrc) return Promise.resolve();

    if (itemData.isOriginalLoaded || itemData.src === itemData.originalSrc) {
      itemData.isOriginalLoaded = true;
      itemData.originalLoadReason = reason;
      swapCurrentSlideToOriginal(index, itemData, Boolean(options.refresh));
      return Promise.resolve();
    }

    const existing = originalLoadPromises.get(itemData.originalSrc);
    if (existing) return existing;

    if (pswp.value?.currIndex === index) {
      originalLoadingPath.value = itemData.path;
    }

    const promise = new Promise<void>((resolve, reject) => {
      if (typeof Image === "undefined") {
        reject(new Error("Image API unavailable"));
        return;
      }

      const image = new Image();
      image.onload = () => {
        itemData.src = itemData.originalSrc;
        itemData.isOriginalLoaded = true;
        itemData.originalLoadReason = reason;
        swapCurrentSlideToOriginal(index, itemData, Boolean(options.refresh));
        resolve();
      };
      image.onerror = () => {
        reject(new Error("Original image failed to load"));
      };
      image.src = itemData.originalSrc;
    }).finally(() => {
      originalLoadPromises.delete(itemData.originalSrc);
      if (originalLoadingPath.value === itemData.path) {
        originalLoadingPath.value = null;
      }
    });

    originalLoadPromises.set(itemData.originalSrc, promise);
    return promise;
  }

  function loadOriginalForCurrent(
    reason: NonNullable<PhotoSwipeImageItem["originalLoadReason"]> = "fullscreen"
  ): Promise<void> {
    const instance = pswp.value;
    if (!instance) return Promise.resolve();
    return loadOriginalForIndex(instance.currIndex, reason);
  }

  function maybeLoadOriginalForCurrent(reason: NonNullable<PhotoSwipeImageItem["originalLoadReason"]>) {
    const instance = pswp.value;
    if (!instance) return;
    void loadOriginalForIndex(instance.currIndex, reason).catch(() => undefined);
  }

  function maybeLoadOriginalForZoom() {
    const instance = pswp.value;
    const slide = instance?.currSlide;
    if (!instance || !slide || slide.index !== instance.currIndex) return;

    const initialZoom = slide.zoomLevels.initial || 1;
    if (slide.currZoomLevel / initialZoom > LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD) {
      maybeLoadOriginalForCurrent("zoom");
    }
  }

  function maybeLoadOriginalForZoomLevel(destZoomLevel: number) {
    const instance = pswp.value;
    const slide = instance?.currSlide;
    if (!instance || !slide || slide.index !== instance.currIndex) return;

    const initialZoom = slide.zoomLevels.initial || 1;
    if (destZoomLevel / initialZoom > LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD) {
      maybeLoadOriginalForCurrent("zoom");
    }
  }

  function maybeLoadCurrentAnimatedOriginal() {
    const instance = pswp.value;
    if (!instance) return;

    const itemData = getPhotoSwipeItem(instance.currIndex);
    if (itemData?.isAnimatedAsset) {
      maybeLoadOriginalForCurrent("animated");
    }
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
    const initialItem = dataSource[currentIndex.value];
    if (initialItem?.isAnimatedAsset) {
      initialItem.src = initialItem.originalSrc;
      initialItem.isOriginalLoaded = true;
      initialItem.originalLoadReason = "animated";
    }

    const instance = new PhotoSwipe({
      dataSource,
      index: currentIndex.value,
      appendToEl: containerRef.value,
      showHideAnimationType: "zoom",
      wheelToZoom: false,
      bgOpacity: 1,
      preload: [1, 1],
      ...photoSwipeOptions,
    });
    pswp.value = instance;
    if (shouldExposeLightboxTestHooks) {
      (window as any).__pswp = instance;
      (window as any).__loadOriginalForCurrent = (reason: string) => {
        maybeLoadOriginalForCurrent(reason as any);
      };
    }

    instance.on("change", () => {
      onIndexChange?.(instance.currIndex);
      resolveAndRefresh(instance.currIndex);
      maybeLoadCurrentAnimatedOriginal();
      if (shouldAlwaysLoadOriginal()) {
        maybeLoadOriginalForCurrent("preference");
      }
    });

    instance.on("zoomPanUpdate", () => {
      maybeLoadOriginalForZoom();
    });

    instance.on("beforeZoomTo", (event) => {
      maybeLoadOriginalForZoomLevel(event.destZoomLevel);
    });

    instance.on("loadError", (event) => {
      if (event.slide.index !== instance.currIndex) return;
      const itemData = getPhotoSwipeItem(event.slide.index);
      if (!itemData || event.content.data.src !== itemData.previewSrc) return;
      void loadOriginalForIndex(event.slide.index, "fallback", { refresh: true }).catch(() => undefined);
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
    if (shouldAlwaysLoadOriginal()) {
      maybeLoadOriginalForCurrent("preference");
    }
  }

  function destroyPhotoSwipe() {
    if (pswp.value) {
      try {
        pswp.value.destroy();
      } catch (_) {
        // Already destroyed
      }
      if (shouldExposeLightboxTestHooks) {
        if ((window as any).__pswp === pswp.value) {
          delete (window as any).__pswp;
        }
        delete (window as any).__loadOriginalForCurrent;
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
    loadOriginalForCurrent,
    originalLoadingPath,
  };
}
