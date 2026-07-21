<script setup lang="ts">
import { computed, nextTick, shallowRef, toRef, useTemplateRef, watch } from "vue";
import "photoswipe/dist/photoswipe.css";
import { X, ZoomIn, ZoomOut, Info, ScanSearch } from "lucide-vue-next";
import type { FileNode } from "../types";
import { usePhotoSwipe } from "../composables/usePhotoSwipe";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = defineProps<{
  items: FileNode[];
  currentIndex: number;
  isOpen: boolean;
  metadataOpen?: boolean;
  canFindRelated?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "indexChange", index: number): void;
  (e: "toggleMetadata"): void;
  (e: "findRelated"): void;
}>();

const containerRef = useTemplateRef<HTMLElement>("container");
const metadataButtonRef = useTemplateRef<HTMLButtonElement>("metadataButton");
const isZoomed = shallowRef(false);

const counter = computed(() => `${props.currentIndex + 1} / ${props.items.length}`);

const { pswp } = usePhotoSwipe({
  containerRef,
  items: computed(() => props.items),
  currentIndex: toRef(props, "currentIndex"),
  isOpen: toRef(props, "isOpen"),
  photoSwipeOptions: {
    closeOnVerticalDrag: true,
    allowPanToNext: true,
    trapFocus: false,
    returnFocus: false,
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

watch(
  () => props.metadataOpen,
  async (isOpen, wasOpen) => {
    if (!wasOpen || isOpen) return;
    await nextTick();
    metadataButtonRef.value?.focus({ preventScroll: true });
  },
);
</script>

<template>
  <div ref="container" class="tablet-photoswipe-container" />

  <div class="tablet-photoswipe-counter">
    {{ counter }}
  </div>

  <div v-if="!metadataOpen" class="tablet-photoswipe-bar">
    <Tooltip v-if="canFindRelated">
      <TooltipTrigger as-child>
        <button class="lx-ctrl" aria-label="Find related" @click="emit('findRelated')">
          <ScanSearch :size="22" :stroke-width="2.2" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Find related</TooltipContent>
    </Tooltip>
    <Tooltip>
      <TooltipTrigger as-child>
        <button class="lx-ctrl" aria-label="Close" @click="emit('close')">
          <X :size="22" :stroke-width="2.2" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Close</TooltipContent>
    </Tooltip>
    <Tooltip>
      <TooltipTrigger as-child>
        <button class="lx-ctrl" :aria-label="isZoomed ? 'Zoom out' : 'Zoom in'" @click="toggleZoom">
          <ZoomOut v-if="isZoomed" :size="22" :stroke-width="2.2" />
          <ZoomIn v-else :size="22" :stroke-width="2.2" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{{ isZoomed ? "Zoom out" : "Zoom in" }}</TooltipContent>
    </Tooltip>
    <Tooltip>
      <TooltipTrigger as-child>
        <button ref="metadataButton" class="lx-ctrl" aria-label="View image info" @click="emit('toggleMetadata')">
          <Info :size="22" :stroke-width="2.2" />
        </button>
      </TooltipTrigger>
      <TooltipContent>View image info</TooltipContent>
    </Tooltip>
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
  z-index: calc(var(--gallery-z-lightbox, 100000) + 1);
}

.tablet-photoswipe-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: calc(var(--gallery-z-lightbox, 100000) + 1);
}
</style>

<style lang="scss">
@import "../styles/lightbox-shared";
</style>
