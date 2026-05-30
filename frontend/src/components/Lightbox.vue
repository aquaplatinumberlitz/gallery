<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { useDevice } from "../composables/useDevice";
import { getImageUrl } from "../services/api";
import {
  Loader, Image, ChevronLeft, ChevronRight, Minimize, X,
  Info,
} from "lucide-vue-next";
import LightboxDesktopPanel from "./LightboxDesktopPanel.vue";
import LightboxTabletPanel from "./LightboxTabletPanel.vue";
import LightboxMobileSheet from "./LightboxMobileSheet.vue";
import MobilePhotoSwipe from "./MobilePhotoSwipe.vue";

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

// Mouse wheel navigation
let lastWheelTime = 0;

// Swipe / 3-slide track state
let swipeStartX = 0;
let swipeStartY = 0;
let swipeDeltaX = 0;
let swipeDeltaY = 0;
let isHorizontalSwipe: boolean | undefined = undefined;
const isSwiping = ref(false);
const isResettingSlide = ref(false);
const trackOffset = ref(0);
const SWIPE_THRESHOLD_PX = 100;
const SWIPE_THRESHOLD_RATIO = 0.3;
let animFrameId = 0;

// Vertical swipe-to-dismiss state
const dismissY = ref(0);
const isDismissSnapping = ref(false);
const backdropOpacity = ref(0.95);
const DISMISS_THRESHOLD = 80;

// Controls visibility (tap-to-toggle + auto-hide)
const controlsVisible = ref(true);
let controlsTimer: ReturnType<typeof setTimeout> | null = null;

function toggleControls() {
  controlsVisible.value = !controlsVisible.value;
  if (controlsTimer) clearTimeout(controlsTimer);
  if (controlsVisible.value) {
    controlsTimer = setTimeout(() => {
      controlsVisible.value = false;
    }, 3000);
  }
}

function resetTrackPosition() {
  const vw = window.innerWidth || 1;
  trackOffset.value = -vw;
}

// Computed URLs for adjacent images (for 3-slide track)
const prevSrc = computed(() => {
  if (lightbox.galleryItems.length <= 1) return null;
  const prevIdx = lightbox.currentIndex - 1;
  if (prevIdx < 0) return null;
  return getImageUrl(lightbox.galleryItems[prevIdx].path);
});

const nextSrc = computed(() => {
  if (lightbox.galleryItems.length <= 1) return null;
  const nextIdx = lightbox.currentIndex + 1;
  if (nextIdx >= lightbox.galleryItems.length) return null;
  return getImageUrl(lightbox.galleryItems[nextIdx].path);
});

// Preload adjacent images for smooth transitions on iOS Safari.
// We use <link rel="preload"> instead of new Image() because iOS Safari
// does not reliably share the JavaScript Image() object cache with
// <img> element rendering, causing a blank flash on src change.
// Link rel=preload populates the browser's shared resource cache.
let preloadLinks: HTMLLinkElement[] = [];

function preloadAdjacent() {
  // Clean up stale preload links
  preloadLinks.forEach(link => {
    try { link.remove(); } catch (_) {}
  });
  preloadLinks = [];

  const addLink = (url: string | null) => {
    if (!url) return;
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'image';
    link.href = url;
    document.head.appendChild(link);
    preloadLinks.push(link);
  };
  addLink(prevSrc.value);
  addLink(nextSrc.value);
}

const prefersReducedMotion = ref(false);

onMounted(() => {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  prefersReducedMotion.value = mq.matches;
  mq.addEventListener('change', (e) => { prefersReducedMotion.value = e.matches; });
  resetTrackPosition();
});

function handleSwipeStart(e: TouchEvent) {
  swipeStartX = e.touches[0].clientX;
  swipeStartY = e.touches[0].clientY;
  swipeDeltaX = 0;
  swipeDeltaY = 0;
  isHorizontalSwipe = undefined;
  isSwiping.value = false; // Wait for direction detection
}

function handleSwipeMove(e: TouchEvent) {
  const deltaX = e.touches[0].clientX - swipeStartX;
  const deltaY = e.touches[0].clientY - swipeStartY;

  // Direction lock on first significant move
  if (isHorizontalSwipe === undefined && (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5)) {
    isHorizontalSwipe = Math.abs(deltaX) > Math.abs(deltaY);
    if (isHorizontalSwipe) {
      // Horizontal: lock body scroll for iOS
      isSwiping.value = true;
      document.body.style.overflow = 'hidden';
      document.body.style.position = 'fixed';
      document.body.style.width = '100%';
    } else {
      // Vertical gesture
      isSwiping.value = true;
    }
  }

  if (isHorizontalSwipe === undefined) return;
  e.preventDefault();

  if (isHorizontalSwipe) {
    // Horizontal swipe → image navigation (existing logic)
    swipeDeltaX = deltaX;
    if (animFrameId) cancelAnimationFrame(animFrameId);
    animFrameId = requestAnimationFrame(() => {
      const vw = window.innerWidth || 1;
      trackOffset.value = -vw + deltaX;
      animFrameId = 0;
    });
  } else {
    // Vertical gesture
    if (showSheet.value) {
      // Sheet is open — track gesture for sheet interaction
      isSwiping.value = true;
      swipeDeltaY = deltaY;
      if (animFrameId) cancelAnimationFrame(animFrameId);
      animFrameId = requestAnimationFrame(() => {
        // Subtle drag feedback but less than dismiss (no full dismiss animation)
        dismissY.value = Math.max(0, deltaY * 0.3); // Only track downward, dampened
        if (deltaY > 0) {
          backdropOpacity.value = Math.max(0.85, 0.95 - (deltaY / DISMISS_THRESHOLD) * 0.15);
        }
        animFrameId = 0;
      });
    } else {
      // Sheet is closed
      isSwiping.value = true;
      swipeDeltaY = deltaY;
      if (deltaY > 0) {
        // Downward → dismiss lightbox
        if (animFrameId) cancelAnimationFrame(animFrameId);
        animFrameId = requestAnimationFrame(() => {
          dismissY.value = deltaY;
          backdropOpacity.value = Math.max(0.65, 0.95 - (deltaY / DISMISS_THRESHOLD) * 0.3);
          animFrameId = 0;
        });
      }
      // Upward (deltaY < 0) — just track, will open sheet on end
    }
  }
}

function handleSwipeEnd() {
  if (isHorizontalSwipe === true) {
    // Horizontal end: existing image nav logic
    if (!isSwiping.value) { isHorizontalSwipe = undefined; return; }
    isSwiping.value = false;
    if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = 0; }

    const viewportW = window.innerWidth;
    const threshold = Math.max(SWIPE_THRESHOLD_PX, viewportW * SWIPE_THRESHOLD_RATIO);

    if (Math.abs(swipeDeltaX) > threshold) {
      if (swipeDeltaX > 0) {
        // Swiped right → go to prev
        trackOffset.value = 0;
        setTimeout(() => {
          isResettingSlide.value = true;
          lightbox.prev();
          resetTrackPosition();
          requestAnimationFrame(() => { isResettingSlide.value = false; });
        }, 280);
      } else {
        // Swiped left → go to next
        trackOffset.value = -(viewportW * 2);
        setTimeout(() => {
          isResettingSlide.value = true;
          lightbox.next();
          resetTrackPosition();
          requestAnimationFrame(() => { isResettingSlide.value = false; });
        }, 280);
      }
    } else {
      resetTrackPosition();
    }

    // Restore body scroll
    document.body.style.overflow = '';
    document.body.style.position = '';
    document.body.style.width = '';
    swipeDeltaX = 0;
  } else if (isHorizontalSwipe === false) {
    // Vertical gesture end
    isSwiping.value = false;

    if (showSheet.value) {
      // Sheet is open — sheet interaction on the image area
      isDismissSnapping.value = true;
      if (swipeDeltaY > DISMISS_THRESHOLD) {
        // Downward → close sheet
        handleSheetClosed();
      }
      // Snap back
      dismissY.value = 0;
      backdropOpacity.value = 0.95;
      setTimeout(() => { isDismissSnapping.value = false; }, 280);
    } else {
      // Sheet is closed
      if (swipeDeltaY > DISMISS_THRESHOLD) {
        // Downward → dismiss lightbox
        isDismissSnapping.value = true;
        dismissY.value = window.innerHeight;
        setTimeout(() => {
          handleClose();
          dismissY.value = 0;
          backdropOpacity.value = 0.95;
          isDismissSnapping.value = false;
        }, 240);
      } else if (swipeDeltaY < -DISMISS_THRESHOLD) {
        // Upward → open metadata sheet
        toggleSheet();
        dismissY.value = 0;
        backdropOpacity.value = 0.95;
      } else {
        // Insufficient distance → snap back
        isDismissSnapping.value = true;
        dismissY.value = 0;
        backdropOpacity.value = 0.95;
        setTimeout(() => { isDismissSnapping.value = false; }, 280);
      }
    }
    swipeDeltaY = 0;
  }

  isHorizontalSwipe = undefined;
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
    // Reset dismiss state when opening
    dismissY.value = 0;
    backdropOpacity.value = 0.95;
    isDismissSnapping.value = false;
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
  // Clean up any lingering preload links
  preloadLinks.forEach(link => {
    try { link.remove(); } catch (_) {}
  });
  preloadLinks = [];
});

watch(
  () => lightbox.itemPath,
  () => {
    imageError.value = false;
  },
);

// Preload adjacent images when current index changes
watch(
  () => lightbox.currentIndex,
  () => {
    preloadAdjacent();
  },
  { immediate: true },
);

const handleImageError = () => {
  imageError.value = true;
};

const displayUrl = computed(() => {
  if (!lightbox.itemPath) return "";
  // Always use the full original image in the lightbox for correct aspect ratio.
  // Thumbnail pipeline can produce stretched output on some mobile browsers.
  return getImageUrl(lightbox.itemPath);
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
        :style="{ background: `rgba(0, 0, 0, ${backdropOpacity})` }"
        @click.self="handleClose"
      >
        <!-- Mobile close button (visible on non-desktop) -->
        <button v-if="!isDesktop" class="lightbox-close-btn" v-show="!isSwiping" @click.stop="handleClose" title="Close">
          <X :size="20" :stroke-width="1.5" />
        </button>

        <!-- Mobile: PhotoSwipe image viewer -->
        <MobilePhotoSwipe
          v-if="isMobile"
          :items="lightbox.galleryItems"
          :current-index="lightbox.currentIndex"
          :is-open="show"
          @close="handlePhotoSwipeClose"
          @index-change="handlePhotoSwipeIndexChange"
        />

        <!-- Desktop/Tablet: dismiss wrapper with 3-slide track (unchanged) -->
        <div v-else
          class="lightbox-dismiss-wrapper"
          :style="{ transform: `translate3d(0, ${dismissY}px, 0)` }"
          :class="{ 'is-dismiss-snapping': isDismissSnapping }"
        >
          <div class="lightbox-shell">
            <!-- Left: Image Area -->
            <div 
              class="lightbox-left"
              :class="{ 'is-swiping': isSwiping }"
              @click.self="handleClose"
              @wheel.prevent="handleWheel"
              @touchstart="handleSwipeStart"
              @touchmove="handleSwipeMove"
              @touchend="handleSwipeEnd"
            >
              <div v-if="isLoading" class="image-loading">
                <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
              </div>

              <!-- 3-slide track for smooth swipe transitions -->
              <div class="lightbox-track"
                :style="{ transform: `translate3d(${trackOffset}px, 0, 0)` }"
                :class="{ 'is-animating': !isSwiping && !isResettingSlide }"
              >
                <!-- Previous slide -->
                <div class="lightbox-slide" v-if="prevSrc">
                  <img :src="prevSrc" alt="" decoding="async" />
                </div>
                <div class="lightbox-slide" v-else />

                <!-- Current slide -->
                <div class="lightbox-slide" @click.stop="toggleControls">
                  <img
                    v-if="lightbox.itemPath && !imageError"
                    :src="displayUrl"
                    class="hero-image"
                    :class="{ loading: isLoading }"
                    @error="handleImageError"
                    :alt="lightbox.itemName || 'Gallery image'"
                    decoding="async"
                    fetchpriority="high"
                  />
                  <div v-else class="hero-placeholder">
                    <Image :size="24" :stroke-width="1.5" />
                    <p>Unable to display this image.</p>
                  </div>
                </div>

                <!-- Next slide -->
                <div class="lightbox-slide" v-if="nextSrc">
                  <img :src="nextSrc" alt="" decoding="async" />
                </div>
                <div class="lightbox-slide" v-else />
              </div>

              <!-- Navigation Buttons (desktop only) -->
              <template v-if="isDesktop">
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
              </template>
              
              <!-- Image counter for screen readers -->
              <div class="sr-only">
                Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
              </div>

              <!-- Info button for tablet (mobile uses PhotoSwipe with separate overlay) -->
              <button 
                class="mobile-info-btn" 
                v-if="isTablet" 
                v-show="controlsVisible"
                @click.stop="toggleSheet" 
                title="Image Info"
              >
                <Info :size="20" :stroke-width="1.5" />
              </button>

              <!-- Tablet photo counter -->
              <div v-if="isTablet" v-show="controlsVisible" class="mobile-photo-counter">
                {{ lightbox.currentIndex + 1 }} / {{ lightbox.galleryItems.length }}
              </div>
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
        </div>

        <!-- Mobile: info button and photo counter overlay (on top of PhotoSwipe) -->
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
        </template>

        <!-- Tablet: Bottom Sheet with 2-column layout (outside dismiss wrapper to preserve fixed positioning) -->
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

        <!-- Mobile: Bottom Sheet (outside dismiss wrapper to preserve fixed positioning) -->
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
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Dismiss wrapper — slides down on vertical swipe */
.lightbox-dismiss-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  will-change: transform;

  &.is-dismiss-snapping {
    transition: transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
  }
}

/* Mobile close button (X) — top-left with safe-area-inset-top */
.lightbox-close-btn {
  position: fixed;
  top: calc(env(safe-area-inset-top) + 12px);
  left: 12px;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #fff;
  cursor: pointer;
  z-index: 60;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.16);
  }

  &:active {
    background: rgba(255, 255, 255, 0.12);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
  }
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
  transform: translateZ(0);
  backface-visibility: hidden;
  
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

// =============================================
// 3-SLIDE TRACK (mobile swipe)
// =============================================

.lightbox-left {
  overflow: hidden;

  &.is-swiping {
    // Hide expensive overlays/effects during drag for jank-free compositing
    .mobile-info-btn { display: none; }
    .mobile-photo-counter { opacity: 0; }
  }
}

.lightbox-track {
  display: flex;
  height: 100%;
  will-change: transform;


  &.is-animating {
    transition: transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
  }
}

.lightbox-slide {
  flex: 0 0 100%;
  height: 100%;
  width: 100%;
  display: grid;
  place-items: center;
  overflow: hidden;

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform: translateZ(0);
    backface-visibility: hidden;
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
