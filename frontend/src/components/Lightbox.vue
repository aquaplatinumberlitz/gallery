<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { useDevice } from "../composables/useDevice";
import { DESKTOP_METADATA_WIDTH } from "../constants";
import { usePhotoMetadataQuery } from "../composables/usePhotoMetadataQuery";
import { lightboxItemAt, logLightboxNavDebug } from "../debug/lightboxNavDebug";
import {
  Minimize, X,
} from "lucide-vue-next";
import LightboxDesktopPanel from "./LightboxDesktopPanel.vue";
import LightboxTabletPanel from "./LightboxTabletPanel.vue";
import LightboxMobileSheet from "./LightboxMobileSheet.vue";
import MobilePhotoSwipe from "./MobilePhotoSwipe.vue";
import TabletPhotoSwipe from "./TabletPhotoSwipe.vue";
import PhotoSwipeViewer from "./PhotoSwipeViewer.vue";

const { isDesktop, isTablet, isMobile, isWide } = useDevice();

const lightbox = useLightboxStore();
const { copyStatus, copyText } = useClipboard();

// Refs for focus management
const lightboxRef = ref<HTMLElement | null>(null);
const desktopPhotoSwipeRef = ref<{ loadOriginalForCurrent: (reason?: "fullscreen") => Promise<void> } | null>(null);

// Focus trap (auto-detects first focusable element)
const focusTrap = useFocusTrap(lightboxRef, {
  returnFocus: true,
});

const show = computed(() => lightbox.isOpen);
const metadataPath = computed(() => lightbox.itemPath);
const metadataQuery = usePhotoMetadataQuery(show, metadataPath);
const isLoading = computed(() => metadataQuery.isLoading.value);
const meta = computed(() => metadataQuery.data.value ?? null);
const isFullscreen = ref(false);
let pendingArrowKeydown: { key: string; indexBefore: number; timeStamp: number } | null = null;

// Bottom sheet toggle state (shared for tablet + mobile)
const showSheet = ref(false);

const sizeText = computed(() => {
  if (meta.value?.width && meta.value?.height) return `${meta.value.width} x ${meta.value.height}`;
  return "";
});

const imageName = computed(() => meta.value?.name || lightbox.itemName);

const dateText = computed(() => {
  if (meta.value?.date) return meta.value.date;
  return "";
});

const genTimeText = computed(() => {
  if (meta.value?.generation_time) return meta.value.generation_time;
  return "";
});

const sidebarWidthStyle = computed(() =>
  (isDesktop.value || isWide.value) && !isFullscreen.value
    ? `${DESKTOP_METADATA_WIDTH}px`
    : "0px"
);

const desktopPaddingFn = (_viewportSize: { x: number; y: number }, _itemData: unknown, _index: number) => ({
  top: 0,
  bottom: 0,
  left: 0,
  right: isFullscreen.value ? 0 : DESKTOP_METADATA_WIDTH,
});

function handleClose() {
  if (isFullscreen.value) {
    exitFullscreen();
  }
  showSheet.value = false;
  lightbox.close();
}

// PhotoSwipe handlers (mobile only)
function handlePhotoSwipeClose() {
  handleClose();
}

function handlePhotoSwipeIndexChange(newIndex: number) {
  const item = lightbox.galleryItems[newIndex];
  logLightboxNavDebug("lightbox-mobile-index-change", {
    newIndex,
    eventItem: lightboxItemAt(lightbox.galleryItems, newIndex),
    beforeIndex: lightbox.currentIndex,
    beforeItemPath: lightbox.itemPath,
    willUpdateStore: Boolean(item && item.path !== lightbox.itemPath),
  });
  if (item && item.path !== lightbox.itemPath) {
    // Update store to reflect PhotoSwipe's new index for metadata fetching
    lightbox.currentIndex = newIndex;
    lightbox.itemPath = item.path;
    lightbox.itemName = item.name || '';
  }
}

// Index change handler for desktop/tablet PhotoSwipeViewer
function handleIndexChange(newIndex: number) {
  const item = lightbox.galleryItems[newIndex];
  logLightboxNavDebug("lightbox-index-change", {
    newIndex,
    eventItem: lightboxItemAt(lightbox.galleryItems, newIndex),
    beforeIndex: lightbox.currentIndex,
    beforeItemPath: lightbox.itemPath,
    willUpdateStore: Boolean(item && item.path !== lightbox.itemPath),
  });
  if (item && item.path !== lightbox.itemPath) {
    lightbox.currentIndex = newIndex;
    lightbox.itemPath = item.path;
    lightbox.itemName = item.name || '';
  }
}

const handleKeydownCapture = (e: KeyboardEvent) => {
  if (!show.value) return;
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;

  const target = e.target as HTMLElement;
  if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

  pendingArrowKeydown = {
    key: e.key,
    indexBefore: lightbox.currentIndex,
    timeStamp: e.timeStamp,
  };
};

// Keyboard navigation
const handleKeydown = (e: KeyboardEvent) => {
  if (!show.value) return;

  // Ignore if focus is on an input
  const target = e.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    const pending = pendingArrowKeydown;
    pendingArrowKeydown = null;
    const photoSwipeHandled =
      pending !== null &&
      pending.key === e.key &&
      pending.timeStamp === e.timeStamp &&
      lightbox.currentIndex !== pending.indexBefore;

    if (photoSwipeHandled) {
      logLightboxNavDebug("lightbox-keyboard-ignored", {
        key: e.key,
        currentIndex: lightbox.currentIndex,
        indexBefore: pending?.indexBefore,
        currentItem: lightboxItemAt(lightbox.galleryItems, lightbox.currentIndex),
      });
      return;
    }

    logLightboxNavDebug("lightbox-keyboard-fallback", {
      key: e.key,
      currentIndex: lightbox.currentIndex,
      indexBefore: pending?.indexBefore ?? lightbox.currentIndex,
      currentItem: lightboxItemAt(lightbox.galleryItems, lightbox.currentIndex),
    });
    e.preventDefault();
    if (e.key === "ArrowLeft") {
      lightbox.prev();
    } else {
      lightbox.next();
    }
    return;
  }

  switch (e.key) {
    case "Escape":
      handleClose();
      break;
  }
};

// Activate focus trap when lightbox opens
watch(show, (isOpen) => {
  if (isOpen) {
    showSheet.value = false;
    focusTrap.activate();
  } else {
    focusTrap.deactivate();
    if (document.fullscreenElement) {
      exitFullscreen();
    }
  }
});

function toggleSheet() {
  showSheet.value = !showSheet.value;
}

function handleSheetClosed() {
  showSheet.value = false;
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydownCapture, { capture: true });
  window.addEventListener("keydown", handleKeydown);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydownCapture, { capture: true });
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  focusTrap.deactivate();
});

// Fullscreen
const canFullscreen = computed(() => typeof document !== "undefined" && document.fullscreenEnabled !== false);

const handleFullscreenChange = () => {
  const active = !!document.fullscreenElement;
  isFullscreen.value = active;
  window.dispatchEvent(new Event("resize"));
};

const enterFullscreen = async () => {
  if (!canFullscreen.value || !lightboxRef.value || isFullscreen.value) return;
  void desktopPhotoSwipeRef.value?.loadOriginalForCurrent("fullscreen").catch(() => undefined);
  try {
    await lightboxRef.value.requestFullscreen();
  } catch (e) {
    console.error("Failed to enter fullscreen", e);
  }
};

const exitFullscreen = async () => {
  if (!document.fullscreenElement) return;
  try {
    await document.exitFullscreen();
  } catch (e) {
    console.error("Failed to exit fullscreen", e);
  }
};

function handleToggleFullscreen() {
  if (isFullscreen.value) {
    exitFullscreen();
  } else {
    enterFullscreen();
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="show"
        ref="lightboxRef"
        data-testid="lightbox"
        class="lightbox-overlay"
        :style="{ '--lightbox-sidebar-width': sidebarWidthStyle }"
      >
        <!-- Desktop/Wide: PhotoSwipe + Sidebar -->
        <template v-if="isDesktop || isWide">
          <PhotoSwipeViewer
            ref="desktopPhotoSwipeRef"
            :items="lightbox.galleryItems"
            :current-index="lightbox.currentIndex"
            :is-open="show"
            :close-on-vertical-drag="false"
            :allow-pan-to-next="false"
            :thumbnail-size="2400"
            :padding-fn="desktopPaddingFn"
            @close="handleClose"
            @index-change="handleIndexChange"
          />
          <div
            v-if="lightbox.galleryItems.length > 1"
            class="desktop-lightbox-counter"
          >
            {{ lightbox.currentIndex + 1 }} / {{ lightbox.galleryItems.length }}
          </div>
          <!-- Image counter for screen readers -->
          <div class="sr-only">
            Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
          </div>
          <!-- Sidebar -->
          <LightboxDesktopPanel
            v-if="!isFullscreen"
            :meta="meta"
            :is-loading="isLoading"
            :image-name="imageName"
            :size-text="sizeText"
            :date-text="dateText"
            :gen-time-text="genTimeText"
            :can-fullscreen="canFullscreen"
            :is-fullscreen="isFullscreen"
            :copy-status="copyStatus"
            :copy-text="copyText"
            @close="handleClose"
            @toggle-fullscreen="handleToggleFullscreen"
          />
          <!-- Fullscreen overlay controls -->
          <div v-if="isFullscreen" class="fs-controls">
            <button class="fs-btn" @click="exitFullscreen" title="Exit fullscreen">
              <Minimize class="gallery-icon-xl" :stroke-width="1.5" />
            </button>
            <button class="fs-btn" @click="handleClose" title="Close">
              <X class="gallery-icon-xl" :stroke-width="1.5" />
            </button>
          </div>
        </template>

        <!-- Tablet: PhotoSwipe + Bottom Sheet -->
        <template v-if="isTablet">
          <TabletPhotoSwipe
            :items="lightbox.galleryItems"
            :current-index="lightbox.currentIndex"
            :is-open="show"
            :metadata-open="showSheet"
            @close="handleClose"
            @index-change="handleIndexChange"
            @toggle-metadata="toggleSheet"
          />
          <LightboxTabletPanel
            v-if="showSheet && !isFullscreen"
            :meta="meta"
            :is-loading="isLoading"
            :image-name="imageName"
            :size-text="sizeText"
            :date-text="dateText"
            :gen-time-text="genTimeText"
            :copy-status="copyStatus"
            :copy-text="copyText"
            @close="handleSheetClosed"
          />
          <!-- Image counter for screen readers -->
          <div class="sr-only">
            Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
          </div>
        </template>

        <!-- Mobile: PhotoSwipe (giữ nguyên) -->
        <MobilePhotoSwipe
          v-if="isMobile"
          :items="lightbox.galleryItems"
          :current-index="lightbox.currentIndex"
          :is-open="show"
          :metadata-open="showSheet"
          @close="handlePhotoSwipeClose"
          @index-change="handlePhotoSwipeIndexChange"
          @toggle-metadata="toggleSheet"
        />
        <template v-if="isMobile">
          <div class="mobile-photo-counter">
            {{ lightbox.currentIndex + 1 }} / {{ lightbox.galleryItems.length }}
          </div>
          <LightboxMobileSheet
            v-if="showSheet && !isFullscreen"
            :meta="meta"
            :is-loading="isLoading"
            :copy-status="copyStatus"
            :copy-text="copyText"
            @close="handleSheetClosed"
          />
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
// ============================================
// Lightbox SCSS — modular partials
// Shared styles imported for loading/error states
// Desktop/Mobile/Tablet styles are scoped to their respective components
// ============================================
@import '../styles/lightbox-shared';

// === Component-unique styles (overlay, navigation, fullscreen) ===

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
}

.fs-controls {
  position: absolute;
  top: 20px;
  right: 20px;
  display: inline-flex;
  gap: 8px;
  z-index: 10;
}

.fs-btn {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.fs-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.5);
}

.fs-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* ── Token-based icon sizes ────────────────────────────────── */
.gallery-icon-lg {
  width: var(--gallery-icon-lg);
  height: var(--gallery-icon-lg);
}
.gallery-icon-xl {
  width: var(--gallery-icon-xl);
  height: var(--gallery-icon-xl);
}


/* Mobile photo counter (shown on non-desktop) */
.mobile-photo-counter {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: white;
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  padding: 4px 12px;
  border-radius: 100px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  pointer-events: none;
  white-space: nowrap;
  user-select: none;
  z-index: 2000;
}

/* Desktop image counter — top-center of image viewport */
.desktop-lightbox-counter {
  position: absolute;
  top: 18px;
  left: calc(50% - var(--lightbox-sidebar-width, 400px) / 2);
  transform: translateX(-50%);
  z-index: 20;
  pointer-events: none;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.52);
  color: rgba(255, 255, 255, 0.94);
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.24);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  white-space: nowrap;
  user-select: none;
}
</style>

<!-- Lightbox CSS variable definitions + PhotoSwipe right arrow fix -->
<style lang="scss">
/*
  CSS variables for desktop lightbox layout.
  --lightbox-sidebar-width is set via inline :style on .lightbox-overlay
  (400px when sidebar visible, 0px when fullscreen or non-desktop).
  Fallback declared here for non-desktop contexts.
*/
.lightbox-overlay {
  --lightbox-sidebar-width: 0px;
  --lightbox-arrow-gap: 16px;
}

/*
  Offset PhotoSwipe's next arrow left of the sidebar so it remains clickable
  and visually belongs to the image viewport. When sidebar is hidden (fullscreen
  or non-desktop), --lightbox-sidebar-width is 0px, restoring the default position.
*/
.pswp__button--arrow--next {
  right: calc(var(--lightbox-sidebar-width) + var(--lightbox-arrow-gap));
}
</style>
