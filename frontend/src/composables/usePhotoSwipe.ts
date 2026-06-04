import { ref, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";
import PhotoSwipe from "photoswipe";
import type { FileNode } from "../types";
import { buildPhotoSwipeItem } from "../utils/lightbox";

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
    thumbnailSize = null,
    onIndexChange,
    onClose,
    onRegisterUi,
    onAfterInit,
  } = options;

  const pswp = ref<PhotoSwipe | null>(null);

  function initPhotoSwipe() {
    if (!containerRef.value || !isOpen.value || pswp.value) return;

    const dataSource = items.value.map((item) =>
      buildPhotoSwipeItem(item, thumbnailSize ?? null)
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
