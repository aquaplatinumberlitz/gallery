import { ref, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";
import PhotoSwipe from "photoswipe";
import type { FileNode, MetadataResponse } from "../types";
import { fetchMetadata, getImageUrl, getPreviewUrl } from "../services/api";
import { queryClient } from "../query";
import { queryKeys } from "../query/keys";
import { useLightboxStore } from "../stores/lightbox";
import { registerLightboxDOMReport } from "../debug/lightboxDomReport";
import { logLightboxNavDebug, summarizeLightboxItems } from "../debug/lightboxNavDebug";
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
  const initTimer = ref<ReturnType<typeof setTimeout> | null>(null);
  const initRunId = ref(0);
  const pendingDimensions = new Map<string, Promise<LightboxDimensions | null>>();
  const originalLoadPromises = new Map<string, Promise<void>>();
  const originalLoadingPath = ref<string | null>(null);
  let lastReportedPhotoSwipeIndex = -1;

  const scanDimensions = (item: FileNode): LightboxDimensions | null =>
    hasValidDimensions(item)
      ? { width: item.width, height: item.height, source: "scan" }
      : null;

  const rememberedDimensions = (item: FileNode): LightboxDimensions | null => {
    const dimensions = lightboxStore.getRememberedDimensions(item.path);
    return dimensions?.source === "thumbnail" ? null : dimensions ?? null;
  };

  const cachedMetadataDimensions = (path: string): LightboxDimensions | null => {
    const metadata = queryClient.getQueryData<MetadataResponse>(queryKeys.metadata(path));
    return hasValidDimensions(metadata)
      ? { width: metadata.width, height: metadata.height, source: "metadata" }
      : null;
  };

  const bestKnownDimensions = (item: FileNode): LightboxDimensions | null =>
    scanDimensions(item) ?? rememberedDimensions(item) ?? cachedMetadataDimensions(item.path);

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
      image.decoding = "async";
      image.onload = () => {
        const resolveNaturalDimensions = () => {
          resolve(
            image.naturalWidth && image.naturalHeight
              ? {
                  width: image.naturalWidth,
                  height: image.naturalHeight,
                  source: "preview",
                }
              : null
          );
        };

        if (typeof image.decode === "function") {
          void image.decode().catch(() => undefined).then(resolveNaturalDimensions);
        } else {
          resolveNaturalDimensions();
        }
      };
      image.onerror = () => resolve(null);
      image.src = getPreviewUrl(path, LIGHTBOX_PREVIEW_EDGE);
    });

  const resolveOpeningSlideDimensions = async (item: FileNode): Promise<LightboxDimensions | null> => {
    const known = bestKnownDimensions(item);
    if (known) return known;

    const previewDimensions = await loadPreviewDimensions(item.path);
    if (previewDimensions) {
      lightboxStore.rememberDimensions(item.path, previewDimensions);
      return previewDimensions;
    }

    const metadataDimensions = await fetchMetadataDimensions(item.path).catch(() => null);
    if (metadataDimensions) {
      lightboxStore.rememberDimensions(item.path, metadataDimensions);
      return metadataDimensions;
    }

    return null;
  };

  const resolveDimensions = (item: FileNode): Promise<LightboxDimensions | null> => {
    const known = scanDimensions(item) ?? rememberedDimensions(item);
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

    // Do not refresh the current visible slide — it can create a duplicate img
    // on mobile Safari during the opening animation.  Non-current neighbour
    // slides are safe to refresh.
    if (index !== instance.currIndex) {
      instance.refreshSlideContent(index);
    }
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

    const originalSrc = getImageUrl(itemData.path);
    const content = instance.currSlide?.content;
    const imageElement = content?.element instanceof HTMLImageElement ? content.element : null;
    itemData.src = originalSrc;
    if (content) {
      content.data.src = originalSrc;
    }
    if (instance.currSlide) {
      instance.currSlide.data.src = originalSrc;
    }
    if (imageElement && imageElement.src !== originalSrc) {
      imageElement.removeAttribute("srcset");
      imageElement.src = originalSrc;
    }
  }

  function loadOriginalForIndex(
    index: number,
    reason: NonNullable<PhotoSwipeImageItem["originalLoadReason"]>,
    options: { refresh?: boolean } = {}
  ): Promise<void> {
    const itemData = getPhotoSwipeItem(index);
    if (!itemData?.path) return Promise.resolve();

    const originalSrc = getImageUrl(itemData.path);

    if (itemData.isOriginalLoaded || itemData.src === originalSrc) {
      itemData.isOriginalLoaded = true;
      itemData.originalLoadReason = reason;
      swapCurrentSlideToOriginal(index, itemData, Boolean(options.refresh));
      return Promise.resolve();
    }

    const existing = originalLoadPromises.get(originalSrc);
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
        itemData.src = originalSrc;
        itemData.isOriginalLoaded = true;
        itemData.originalLoadReason = reason;
        swapCurrentSlideToOriginal(index, itemData, Boolean(options.refresh));
        resolve();
      };
      image.onerror = () => {
        reject(new Error("Original image failed to load"));
      };
      image.src = originalSrc;
    }).finally(() => {
      originalLoadPromises.delete(originalSrc);
      if (originalLoadingPath.value === itemData.path) {
        originalLoadingPath.value = null;
      }
    });

    originalLoadPromises.set(originalSrc, promise);
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

  async function initPhotoSwipe() {
    if (!containerRef.value || !isOpen.value || pswp.value) return;

    if (initTimer.value) {
      clearTimeout(initTimer.value);
      initTimer.value = null;
    }

    const runId = ++initRunId.value;
    const openingIndex = currentIndex.value;
    const openingItem = items.value[openingIndex];
    logLightboxNavDebug("pswp-init-start", {
      openingIndex,
      openingItem: openingItem ? { path: openingItem.path, name: openingItem.name } : null,
      items: summarizeLightboxItems(items.value, openingIndex),
    });
    const openingDimensions = openingItem
      ? await resolveOpeningSlideDimensions(openingItem)
      : null;

    if (!containerRef.value || !isOpen.value || pswp.value || runId !== initRunId.value) return;

    const dataSource = items.value.map((item, index) =>
      buildPhotoSwipeItem(
        item,
        index === openingIndex
          ? openingDimensions ?? bestKnownDimensions(item)
          : bestKnownDimensions(item)
      )
    );
    const initialItem = dataSource[currentIndex.value];
    if (initialItem?.isAnimatedAsset) {
      const originalSrc = getImageUrl(initialItem.path);
      initialItem.src = originalSrc;
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
    lastReportedPhotoSwipeIndex = instance.currIndex;
    logLightboxNavDebug("pswp-instance-created", {
      currIndex: instance.currIndex,
      optionIndex: currentIndex.value,
      dataSource: summarizeLightboxItems(dataSource, currentIndex.value),
    });
    if (shouldExposeLightboxTestHooks) {
      (window as any).__pswp = instance;
      (window as any).__loadOriginalForCurrent = (reason: string) => {
        maybeLoadOriginalForCurrent(reason as any);
      };
    }

    instance.on("change", () => {
      const previousIndex = lastReportedPhotoSwipeIndex;
      lastReportedPhotoSwipeIndex = instance.currIndex;
      const itemData = getPhotoSwipeItem(instance.currIndex);
      logLightboxNavDebug("pswp-change", {
        previousIndex,
        currIndex: instance.currIndex,
        delta: previousIndex >= 0 ? instance.currIndex - previousIndex : null,
        item: itemData ? { path: itemData.path, name: itemData.alt } : null,
        propCurrentIndex: currentIndex.value,
        storeCurrentIndex: lightboxStore.currentIndex,
        storeItemPath: lightboxStore.itemPath,
      });
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
    logLightboxNavDebug("pswp-init-complete", {
      currIndex: instance.currIndex,
      propCurrentIndex: currentIndex.value,
      storeCurrentIndex: lightboxStore.currentIndex,
    });
    onAfterInit?.(instance);
    resolveAndRefresh(currentIndex.value);
    if (shouldAlwaysLoadOriginal()) {
      maybeLoadOriginalForCurrent("preference");
    }
  }

  function destroyPhotoSwipe() {
    initRunId.value++;
    if (initTimer.value) {
      clearTimeout(initTimer.value);
      initTimer.value = null;
    }
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
        if (initTimer.value) clearTimeout(initTimer.value);
        initTimer.value = setTimeout(() => {
          initTimer.value = null;
          void initPhotoSwipe();
        }, 0);
      } else {
        destroyPhotoSwipe();
      }
    }
  );

  watch(
    () => currentIndex.value,
    (index) => {
      const pswpIndex = pswp.value?.currIndex ?? null;
      const willGoTo = Boolean(pswp.value && pswp.value.currIndex !== index);
      logLightboxNavDebug("pswp-watch-current-index", {
        index,
        pswpIndex,
        willGoTo,
        storeCurrentIndex: lightboxStore.currentIndex,
        storeItemPath: lightboxStore.itemPath,
      });
      if (pswp.value && pswp.value.currIndex !== index) {
        pswp.value.goTo(index);
      }
      resolveAndRefresh(index);
    }
  );

  onMounted(() => {
    if (isOpen.value) {
      void initPhotoSwipe();
    }
  });

  onUnmounted(() => {
    destroyPhotoSwipe();
  });

  registerLightboxDOMReport();

  return {
    pswp,
    destroyPhotoSwipe,
    loadOriginalForCurrent,
    originalLoadingPath,
  };
}
