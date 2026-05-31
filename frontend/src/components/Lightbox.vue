<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { useDevice } from "../composables/useDevice";
import {
  Minimize, X,
} from "lucide-vue-next";
import LightboxDesktopPanel from "./LightboxDesktopPanel.vue";
import LightboxTabletPanel from "./LightboxTabletPanel.vue";
import LightboxMobileSheet from "./LightboxMobileSheet.vue";
import MobilePhotoSwipe from "./MobilePhotoSwipe.vue";
import PhotoSwipeViewer from "./PhotoSwipeViewer.vue";

const { isDesktop, isTablet, isMobile, isWide } = useDevice();

const lightbox = useLightboxStore();
const { copyStatus, copyText } = useClipboard();

// Refs for focus management
const lightboxRef = ref<HTMLElement | null>(null);

// Focus trap (auto-detects first focusable element)
const focusTrap = useFocusTrap(lightboxRef, {
  returnFocus: true,
});

const show = computed(() => lightbox.isOpen);
const isLoading = computed(() => lightbox.isLoading);
const meta = computed(() => lightbox.metadata);
const isFullscreen = ref(false);

// Bottom sheet toggle state (shared for tablet + mobile)
const showSheet = ref(false);

const sizeText = computed(() => {
  if (lightbox.width && lightbox.height) return `${lightbox.width} x ${lightbox.height}`;
  return "";
});

const dateText = computed(() => {
  if (meta.value?.date) return meta.value.date;
  return "";
});

const genTimeText = computed(() => {
  if (meta.value?.generation_time) return meta.value.generation_time;
  return "";
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
  if (item && item.path !== lightbox.itemPath) {
    // Update store to reflect PhotoSwipe's new index for metadata fetching
    lightbox.currentIndex = newIndex;
    lightbox.itemPath = item.path;
    lightbox.itemName = item.name || '';
    lightbox.loadMetadata(item.path);
  }
}

// Index change handler for desktop/tablet PhotoSwipeViewer
function handleIndexChange(newIndex: number) {
  const item = lightbox.galleryItems[newIndex];
  if (item && item.path !== lightbox.itemPath) {
    lightbox.currentIndex = newIndex;
    lightbox.itemPath = item.path;
    lightbox.itemName = item.name || '';
    lightbox.loadMetadata(item.path);
  }
}

// Keyboard navigation
const handleKeydown = (e: KeyboardEvent) => {
  if (!show.value) return;

  // Ignore if focus is on an input
  const target = e.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

  // Skip arrow keys on mobile — PhotoSwipe handles swipe/keyboard navigation
  if (isMobile.value && (e.key === "ArrowLeft" || e.key === "ArrowRight")) return;

  switch (e.key) {
    case "Escape":
      handleClose();
      break;
    case "ArrowLeft":
      lightbox.prev();
      break;
    case "ArrowRight":
      lightbox.next();
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
  window.addEventListener("keydown", handleKeydown);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  focusTrap.deactivate();
});

// Fullscreen
const canFullscreen = computed(() => typeof document !== "undefined" && document.fullscreenEnabled !== false);

const handleFullscreenChange = () => {
  const active = !!document.fullscreenElement;
  isFullscreen.value = active;
};

const enterFullscreen = async () => {
  if (!canFullscreen.value || !lightboxRef.value || isFullscreen.value) return;
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
        class="lightbox-overlay"
      >
        <!-- Desktop/Wide: PhotoSwipe + Sidebar -->
        <template v-if="isDesktop || isWide">
          <PhotoSwipeViewer
            :items="lightbox.galleryItems"
            :current-index="lightbox.currentIndex"
            :is-open="show"
            :close-on-vertical-drag="false"
            :allow-pan-to-next="false"
            :thumbnail-size="2400"
            @close="handleClose"
            @index-change="handleIndexChange"
          />
          <!-- Image counter for screen readers -->
          <div class="sr-only">
            Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
          </div>
          <!-- Sidebar -->
          <LightboxDesktopPanel
            v-if="!isFullscreen"
            :meta="meta"
            :is-loading="isLoading"
            :image-name="lightbox.itemName"
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
              <Minimize :size="20" :stroke-width="1.5" />
            </button>
            <button class="fs-btn" @click="handleClose" title="Close">
              <X :size="20" :stroke-width="1.5" />
            </button>
          </div>
        </template>

        <!-- Tablet: PhotoSwipe + Bottom Sheet -->
        <template v-if="isTablet">
          <PhotoSwipeViewer
            :items="lightbox.galleryItems"
            :current-index="lightbox.currentIndex"
            :is-open="show"
            :close-on-vertical-drag="false"
            :allow-pan-to-next="true"
            :thumbnail-size="2048"
            :show-info-button="true"
            :metadata-open="showSheet"
            @close="handleClose"
            @index-change="handleIndexChange"
            @toggle-metadata="toggleSheet"
          />
          <div class="mobile-photo-counter">
            {{ lightbox.currentIndex + 1 }} / {{ lightbox.galleryItems.length }}
          </div>
          <LightboxTabletPanel
            v-if="showSheet && !isFullscreen"
            :meta="meta"
            :is-loading="isLoading"
            :image-name="lightbox.itemName"
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
</style>

<!-- Lightbox CSS variable definitions + PhotoSwipe right arrow fix -->
<style lang="scss">
/*
  The sidebar .lightbox-right sits in front of PhotoSwipe, covering the right
  ~400px of the viewport. This makes PhotoSwipe's native next arrow (which
  PhotoSwipe positions near the right edge) unclickable.

  Instead of z-index hacks, we simply offset the next arrow left of the sidebar
  by the sidebar width + a gap. CSS variables keep sidebar and arrow in sync.
*/
.lightbox-overlay {
  --lightbox-sidebar-width: 400px;
  --lightbox-arrow-gap: 16px;
}

.pswp__button--arrow--next {
  right: calc(var(--lightbox-sidebar-width) + var(--lightbox-arrow-gap));
}
</style>
