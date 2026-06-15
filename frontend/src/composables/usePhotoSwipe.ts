import { ref, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";
import PhotoSwipe from "photoswipe";
import type { FileNode, MetadataResponse } from "../types";
import { fetchMetadata, getImageUrl, getPreviewUrl } from "../services/api";
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
  const initTimer = ref<ReturnType<typeof setTimeout> | null>(null);
  const initRunId = ref(0);
  const pendingDimensions = new Map<string, Promise<LightboxDimensions | null>>();
  const originalLoadPromises = new Map<string, Promise<void>>();
  const originalLoadingPath = ref<string | null>(null);

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

  function __galleryLightboxDOMReport() {
    const pswpRoots = document.querySelectorAll(".pswp");
    console.group("%c Gallery Lightbox DOM Report", "font-weight:bold;font-size:1.1em;");

    console.log("---- .pswp roots ----");
    console.log("Count:", pswpRoots.length);
    if (pswpRoots.length !== 1) {
      console.warn("EXPECTED exactly 1 .pswp root, found", pswpRoots.length);
    }
    pswpRoots.forEach((el, i) => {
      console.log(`  [${i}]`, el, `(parent: ${(el.parentElement?.className ?? "none").slice(0, 60)})`);
    });

    console.log("---- .pswp__item ----");
    const items = document.querySelectorAll(".pswp__item");
    console.log("Count:", items.length);
    items.forEach((el, i) => {
      console.log(`  [${i}]`, el);
    });

    console.log("---- .pswp__img ----");
    const images = document.querySelectorAll<HTMLImageElement>(".pswp__img");
    console.log("Total count:", images.length);
    const visibleImages: HTMLImageElement[] = [];
    images.forEach((img, i) => {
      const rect = img.getBoundingClientRect();
      const style = getComputedStyle(img);
      const isVisible =
        style.display !== "none" &&
        parseFloat(style.opacity) > 0 &&
        style.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0;
      if (isVisible) visibleImages.push(img);

      console.group(`  .pswp__img [${i}]`);
      console.log("  src:", img.src.slice(0, 120));
      console.log("  currentSrc:", img.currentSrc.slice(0, 120));
      console.log(
        "  boundingClientRect:",
        JSON.stringify({ x: rect.x.toFixed(1), y: rect.y.toFixed(1), w: rect.width.toFixed(1), h: rect.height.toFixed(1) })
      );
      console.log(
        "  computed:",
        JSON.stringify({ display: style.display, opacity: style.opacity, visibility: style.visibility, transform: style.transform.slice(0, 60) })
      );
      console.log("  parent classes:", img.parentElement?.className.slice(0, 120) ?? "none");
      console.log("  visible (heuristic):", isVisible);
      console.groupEnd();
    });

    console.log("---- .pswp__img--placeholder ----");
    const placeholders = document.querySelectorAll(".pswp__img--placeholder");
    console.log("Count:", placeholders.length);
    placeholders.forEach((el, i) => {
      console.log(`  [${i}]`, el, "boundingClientRect:", JSON.stringify(el.getBoundingClientRect()));
    });

    console.log("---- .pswp active-slide ----");
    const activeSlide = document.querySelector(".pswp__item--active, [aria-selected=\"true\"]");
    console.log("Found:", !!activeSlide, activeSlide);

    console.log("---- Summary ----");
    console.log("pswp roots:", pswpRoots.length, "(expected 1)");
    console.log("total .pswp__img:", images.length);
    console.log("visible .pswp__img:", visibleImages.length);

    console.groupEnd();
  }

  if (typeof window !== "undefined") {
    (window as any).__galleryLightboxDOMReport = __galleryLightboxDOMReport;
  }

  return {
    pswp,
    destroyPhotoSwipe,
    loadOriginalForCurrent,
    originalLoadingPath,
  };
}
