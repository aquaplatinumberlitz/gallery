<script setup lang="ts">
import { ref, computed, toRef } from "vue";
import "photoswipe/dist/photoswipe.css";
import { X, ZoomIn, ZoomOut, Info } from "lucide-vue-next";
import type { FileNode } from "../types";
import { usePhotoSwipe } from "../composables/usePhotoSwipe";

const props = defineProps<{
  items: FileNode[];
  currentIndex: number;
  isOpen: boolean;
  metadataOpen?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "indexChange", index: number): void;
  (e: "toggleMetadata"): void;
}>();

const containerRef = ref<HTMLElement | null>(null);
const isZoomed = ref(false);

const counter = computed(() => `${props.currentIndex + 1} / ${props.items.length}`);

const { pswp } = usePhotoSwipe({
  containerRef,
  items: computed(() => props.items),
  currentIndex: toRef(props, "currentIndex"),
  isOpen: toRef(props, "isOpen"),
  photoSwipeOptions: {
    closeOnVerticalDrag: true,
    allowPanToNext: true,
  },
  thumbnailSize: 2048,
  onIndexChange: (index) => {
    emit("indexChange", index);
    isZoomed.value = false;
  },
  onClose: () => emit("close"),
});

function toggleZoom() {
  if (!pswp.value || !pswp.value.currSlide) return;
  const slide = pswp.value.currSlide;
  const center = pswp.value.getViewportCenterPoint();
  if (slide.currZoomLevel > slide.zoomLevels.initial + 0.01) {
    pswp.value.zoomTo(slide.zoomLevels.initial, center);
    isZoomed.value = false;
  } else {
    pswp.value.zoomTo(slide.zoomLevels.secondary, center);
    isZoomed.value = true;
  }
}
</script>

<template>
  <div ref="containerRef" class="tablet-photoswipe-container"></div>

  <div class="tablet-photoswipe-counter">{{ counter }}</div>

  <div class="tablet-photoswipe-bar">
    <button
      class="tablet-photoswipe-btn"
      aria-label="Close"
      @click="emit('close')"
    >
      <X :size="24" :stroke-width="1.5" />
    </button>
    <button
      class="tablet-photoswipe-btn"
      :aria-label="isZoomed ? 'Zoom out' : 'Zoom in'"
      @click="toggleZoom"
    >
      <ZoomOut v-if="isZoomed" :size="24" :stroke-width="1.5" />
      <ZoomIn v-else :size="24" :stroke-width="1.5" />
    </button>
    <button
      class="tablet-photoswipe-btn"
      :class="{ active: metadataOpen }"
      :aria-label="metadataOpen ? 'Close image info' : 'View image info'"
      @click="emit('toggleMetadata')"
    >
      <Info :size="24" :stroke-width="1.5" />
    </button>
  </div>
</template>

<style scoped lang="scss">
.tablet-photoswipe-container {
  position: fixed;
  inset: 0;
  z-index: 1;
}

.tablet-photoswipe-counter {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: #fff;
  font-size: 15px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  padding: 4px 12px;
  border-radius: 100px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  pointer-events: none;
  white-space: nowrap;
  user-select: none;
  z-index: 5000;
}

.tablet-photoswipe-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 5000;
}

.tablet-photoswipe-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  padding: 0;
  background: rgba(0, 0, 0, 0.5);
  border: none;
  border-radius: 50%;
  color: #fff;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
  transition: background 0.2s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.7);
  }

  &:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.6);
  }

  &.active {
    background: rgba(255, 255, 255, 0.2);
  }
}
</style>

<style lang="scss">
@import '../styles/lightbox-shared';

.pswp {
  --pswp-bg: #000;
  --pswp-icon-color: #fff;
  --pswp-icon-color-secondary: #a09888;
}

.pswp__button--close,
.pswp__button--zoom {
  display: none !important;
}

.pswp__top-bar {
  opacity: 0 !important;
  pointer-events: none !important;
}
</style>
