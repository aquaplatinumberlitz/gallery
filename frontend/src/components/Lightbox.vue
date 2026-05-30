<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { useDevice } from "../composables/useDevice";
import {
  ChevronLeft, ChevronRight, Minimize, X,
  Info,
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

const hasPrev = computed(() => lightbox.currentIndex > 0);
const hasNext = computed(() => lightbox.currentIndex < lightbox.galleryItems.length - 1);

// Controls visibility (tap-to-toggle + auto-hide)
const controlsVisible = ref(true);
let controlsTimer: ReturnType<typeof setTimeout> | null = null;

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
    controlsVisible.value = true;
    // Start auto-hide timer
    if (controlsTimer) clearTimeout(controlsTimer);
    controlsTimer = setTimeout(() => {
      controlsVisible.value = false;
    }, 3000);
    focusTrap.activate();
  } else {
    focusTrap.deactivate();
    if (document.fullscreenElement) {
      exitFullscreen();
    }
    // Clean up auto-hide timer
    if (controlsTimer) clearTimeout(controlsTimer);
    controlsTimer = null;
  }
});

function toggleSheet() {
  showSheet.value = !showSheet.value;
  if (showSheet.value) {
    controlsVisible.value = true;
  }
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
  if (controlsTimer) clearTimeout(controlsTimer);
  controlsTimer = null;
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
            :thumbnail-size="null"
            @close="handleClose"
            @index-change="handleIndexChange"
          />
          <!-- Nav buttons -->
          <button class="nav-btn prev" :disabled="!hasPrev" @click.stop="lightbox.prev()">
            <ChevronLeft :size="24" :stroke-width="1.5" />
          </button>
          <button class="nav-btn next" :disabled="!hasNext" @click.stop="lightbox.next()">
            <ChevronRight :size="24" :stroke-width="1.5" />
          </button>
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
            @close="handleClose"
            @index-change="handleIndexChange"
          />
          <button class="mobile-info-btn" v-show="controlsVisible"
            @click.stop="toggleSheet" title="Image Info">
            <Info :size="20" :stroke-width="1.5" />
          </button>
          <div v-show="controlsVisible" class="mobile-photo-counter">
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
          @close="handlePhotoSwipeClose"
          @index-change="handlePhotoSwipeIndexChange"
        />
        <template v-if="isMobile">
          <button
            class="mobile-info-btn"
            v-show="controlsVisible"
            @click.stop="toggleSheet"
            title="Image Info"
          >
            <Info :size="20" :stroke-width="1.5" />
          </button>
          <div v-show="controlsVisible" class="mobile-photo-counter">
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

.nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #f5f7fb;
  width: 48px;
  height: 80px;
  font-size: 24px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  backdrop-filter: blur(6px);
  opacity: 0; /* Hidden by default */

  &:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.35);
    color: var(--primary-color);
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    transform: translateY(-50%) scale(1.02);
  }

  &.prev { left: 12px; }
  &.next { right: 12px; }

  &:disabled {
    opacity: 0;
    pointer-events: none;
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
    opacity: 1;
  }
}

.lightbox-overlay:hover .nav-btn:not(:disabled) {
  opacity: 1;
}

/* Info button for tablet + mobile devices */
.mobile-info-btn {
  position: absolute;
  bottom: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2000;
  backdrop-filter: blur(6px);
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.5);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
  }
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
