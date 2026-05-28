<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { useDevice } from "../composables/useDevice";
import { getImageUrl, getThumbnailUrl } from "../services/api";
import {
  Loader, Image, ChevronLeft, ChevronRight, Minimize, X,
  Info,
} from "lucide-vue-next";
import LightboxDesktopPanel from "./LightboxDesktopPanel.vue";
import LightboxTabletPanel from "./LightboxTabletPanel.vue";
import LightboxMobileSheet from "./LightboxMobileSheet.vue";

const { isDesktop, isTablet, isMobile } = useDevice();

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
const imageError = ref(false);
const manualOriginal = ref(false);
const fallbackOriginal = ref(false);
const useOriginal = computed(() => manualOriginal.value || fallbackOriginal.value);
const isAnimated = computed(() => {
  const name = lightbox.itemName || lightbox.metadata?.name || "";
  const ext = name.split(".").pop()?.toLowerCase();
  return ext === "gif" || ext === "webp";
});

// Mouse wheel navigation
let lastWheelTime = 0;
let swipeStartX = 0;
let swipeDeltaX = 0;
let isSwiping = false;
const SWIPE_THRESHOLD_PX = 100;
const SWIPE_THRESHOLD_RATIO = 0.3;

const prefersReducedMotion = ref(false);

onMounted(() => {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  prefersReducedMotion.value = mq.matches;
  mq.addEventListener('change', (e) => { prefersReducedMotion.value = e.matches; });
});

function handleSwipeStart(e: TouchEvent) {
  swipeStartX = e.touches[0].clientX;
  swipeDeltaX = 0;
  isSwiping = true;
}

function handleSwipeMove(e: TouchEvent) {
  if (!isSwiping) return;
  swipeDeltaX = e.touches[0].clientX - swipeStartX;
  const img = document.querySelector('.hero-image') as HTMLElement;
  if (img) {
    img.style.transition = prefersReducedMotion.value ? 'none' : 'transform 0.05s linear';
    img.style.transform = `translateX(${swipeDeltaX}px) scale(${1 - Math.abs(swipeDeltaX) * 0.001})`;
  }
}

function handleSwipeEnd() {
  if (!isSwiping) return;
  isSwiping = false;
  const img = document.querySelector('.hero-image') as HTMLElement;
  const viewportW = window.innerWidth;
  const threshold = Math.max(SWIPE_THRESHOLD_PX, viewportW * SWIPE_THRESHOLD_RATIO);

  if (Math.abs(swipeDeltaX) > threshold) {
    // Dismiss — navigate
    if (swipeDeltaX > 0) {
      handlePrev();
    } else {
      handleNext();
    }
    // Reset immediately
    if (img) {
      img.style.transition = 'none';
      img.style.transform = '';
    }
  } else {
    // Snap back with spring
    if (img) {
      img.style.transition = prefersReducedMotion.value 
        ? 'none' 
        : 'transform 0.4s cubic-bezier(0.2, 0, 0, 1)';
      img.style.transform = '';
    }
  }
  swipeDeltaX = 0;
}

const handleWheel = (e: WheelEvent) => {
  const now = Date.now();
  if (now - lastWheelTime < 60) return; // Throttle
  lastWheelTime = now;

  if (e.deltaY > 0) {
    handleNext();
  } else if (e.deltaY < 0) {
    handlePrev();
  }
};

// Navigation with announcements
const handlePrev = () => {
  if (hasPrev.value) {
    lightbox.prev();
  }
};

const handleNext = () => {
  if (hasNext.value) {
    lightbox.next();
  }
};

const handleClose = () => {
  if (isFullscreen.value) {
    exitFullscreen();
  }
  showSheet.value = false;
  lightbox.close();
};

// Keyboard navigation
const handleKeydown = (e: KeyboardEvent) => {
  if (!show.value) return;
  
  // Ignore if focus is on an input
  const target = e.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
  
  switch (e.key) {
    case "Escape":
      handleClose();
      break;
    case "ArrowLeft":
      handlePrev();
      break;
    case "ArrowRight":
      handleNext();
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

watch(
  () => lightbox.itemPath,
  () => {
    imageError.value = false;
    manualOriginal.value = false;
    fallbackOriginal.value = false;
  },
);

const handleImageError = () => {
  // If using display image, try falling back to original once
  if (!useOriginal.value && lightbox.itemPath) {
    fallbackOriginal.value = true;
    return;
  }
  imageError.value = true;
};

const displayUrl = computed(() => {
  if (!lightbox.itemPath) return "";
  const forceOriginal = isAnimated.value || useOriginal.value;
  return forceOriginal
    ? getImageUrl(lightbox.itemPath)
    : getThumbnailUrl(lightbox.itemPath, 2048); // display size ~2K
});

// Fullscreen
const canFullscreen = computed(() => typeof document !== "undefined" && document.fullscreenEnabled !== false);

const handleFullscreenChange = () => {
  const active = !!document.fullscreenElement;
  isFullscreen.value = active;
  manualOriginal.value = active; // fullscreen prefers original image
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
        @click.self="handleClose"
      >
        <div class="lightbox-shell">
          <!-- Left: Image Area -->
          <div 
            class="lightbox-left"
            @click.self="handleClose"
            @wheel.prevent="handleWheel"
            @touchstart="handleSwipeStart"
            @touchmove="handleSwipeMove"
            @touchend="handleSwipeEnd"
          >
            <div v-if="isLoading" class="image-loading">
              <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
            </div>
            
            <img 
              v-if="lightbox.itemPath && !imageError" 
              :src="displayUrl" 
              class="hero-image" 
              :class="{ loading: isLoading }"
              @error="handleImageError"
              :alt="lightbox.itemName || 'Gallery image'"
            />
            <div v-else class="hero-placeholder">
              <Image :size="24" :stroke-width="1.5" />
              <p>Unable to display this image.</p>
            </div>

            <!-- Navigation Buttons -->
            <button 
              class="nav-btn prev" 
              :disabled="!hasPrev"
              @click.stop="handlePrev" 
              :title="hasPrev ? 'Previous (Left Arrow)' : 'No previous image'"
            >
              <ChevronLeft :size="24" :stroke-width="1.5" />
            </button>
            <button 
              class="nav-btn next" 
              :disabled="!hasNext"
              @click.stop="handleNext" 
              :title="hasNext ? 'Next (Right Arrow)' : 'No next image'"
            >
              <ChevronRight :size="24" :stroke-width="1.5" />
            </button>
            
            <!-- Image counter for screen readers -->
            <div class="sr-only">
              Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
            </div>

            <!-- Info button for bottom-sheet devices (tablet + mobile) -->
            <button 
              class="mobile-info-btn" 
              v-if="!isDesktop" 
              @click.stop="toggleSheet" 
              title="Image Info"
            >
              <Info :size="20" :stroke-width="1.5" />
            </button>
          </div>

          <!-- Desktop: Right Sidebar Metadata Panel -->
          <LightboxDesktopPanel
            v-if="isDesktop && !isFullscreen"
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
        </div>

        <!-- Fullscreen overlay controls -->
        <div v-if="isFullscreen" class="fs-controls">
          <button 
            class="fs-btn" 
            @click="exitFullscreen"
            title="Exit fullscreen"
          >
            <Minimize :size="20" :stroke-width="1.5" />
          </button>
          <button 
            class="fs-btn" 
            @click="handleClose"
            title="Close"
          >
            <X :size="20" :stroke-width="1.5" />
          </button>
        </div>

        <!-- Tablet: Bottom Sheet with 2-column layout -->
        <LightboxTabletPanel
          v-if="isTablet && showSheet && !isFullscreen"
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

        <!-- Mobile: Bottom Sheet -->
        <LightboxMobileSheet
          v-if="isMobile && showSheet && !isFullscreen"
          :meta="meta"
          :is-loading="isLoading"
          :copy-status="copyStatus"
          :copy-text="copyText"
          @close="handleSheetClosed"
        />
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

// === Component-unique styles (image viewer, navigation, fullscreen) ===

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
  background: rgba(0, 0, 0, 0.95);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-shell {
  width: 100%;
  height: 100%;
  display: flex;
  overflow: hidden;
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

/* Left Side: Image & Nav */
.lightbox-left {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%);
  user-select: none;
}

.hero-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: opacity 0.2s;
  
  &.loading {
    opacity: 0.5;
  }
}

.hero-placeholder {
  display: grid;
  place-items: center;
  gap: 10px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 24px;
  text-align: center;
}

.hero-placeholder p {
  margin: 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.image-loading {
  position: absolute;
  font-size: 48px;
  color: rgba(255, 255, 255, 0.2);
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

.lightbox-left:hover .nav-btn:not(:disabled) {
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
  z-index: 5;
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

// =============================================
// RESPONSIVE BREAKPOINTS
// =============================================

/* Phone/tablet: stack layout, nav always visible */
@media (max-width: 1024px) {
  .lightbox-shell {
    flex-direction: column;
  }

  .lightbox-left {
    flex: 1;
    min-height: 0;
  }

  .nav-btn {
    opacity: 0.8 !important;
  }

  .nav-btn.prev { left: 8px; }
  .nav-btn.next { right: 8px; }

  .nav-btn:disabled {
    opacity: 0.2 !important;
    pointer-events: none;
  }
}

/* Small phone: compact */
@media (max-width: 480px) {
  .nav-btn {
    width: 40px;
    height: 56px;
    font-size: 18px;
  }
}

/* Touch devices: bigger nav tap targets */
@media (pointer: coarse) {
  .nav-btn {
    min-width: 44px;
    min-height: 44px;
  }

  .nav-btn.prev { left: 4px; }
  .nav-btn.next { right: 4px; }
}
</style>
