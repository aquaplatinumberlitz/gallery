<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { FileNode } from "../types";
import { ArrowLeft, ArrowRight } from "lucide-vue-next";
import AlbumCardMobile from "./AlbumCardMobile.vue";
import AlbumCardTablet from "./AlbumCardTablet.vue";
import { useDevice } from "../composables/useDevice";

const props = defineProps<{
  folders: FileNode[];
}>();

const emit = defineEmits<{
  (e: "open-folder", path: string): void;
}>();

// ── Refs ──
const gridRef = ref<HTMLElement | null>(null);
const showLeftArrow = ref(false);
const showRightArrow = ref(false);
const { isMobile } = useDevice();

// ── ResizeObserver for realtime overflow tracking ──
let resizeObserver: ResizeObserver | null = null;
let scrollTick = false;

const updateArrows = (grid: HTMLElement) => {
  const { scrollLeft, scrollWidth, clientWidth } = grid;
  showLeftArrow.value = scrollLeft > 4;
  showRightArrow.value = scrollLeft < scrollWidth - clientWidth - 4;
};

const scheduleArrowsUpdate = (grid: HTMLElement) => {
  if (scrollTick) return;
  scrollTick = true;
  requestAnimationFrame(() => {
    scrollTick = false;
    updateArrows(grid);
  });
};

const onGridScroll = () => {
  if (gridRef.value) scheduleArrowsUpdate(gridRef.value);
};

// ── Scroll logic ──
const scrollAlbums = (direction: number) => {
  const grid = gridRef.value;
  if (!grid) return;

  const card = grid.querySelector<HTMLElement>('[class*="album-card"]');
  if (!card) return;

  const cardWidth = card.offsetWidth || 200;
  const gap = parseInt(getComputedStyle(grid).gap) || 24;
  const scrollAmount = (cardWidth + gap) * direction;

  grid.scrollBy({ left: scrollAmount, behavior: "smooth" });

  setTimeout(() => scheduleArrowsUpdate(grid), 350);
};

// ── Lifecycle ──
const init = () => {
  if (!gridRef.value) return;
  updateArrows(gridRef.value);

  if (resizeObserver) resizeObserver.disconnect();
  resizeObserver = new ResizeObserver(([entry]) => {
    if (entry && gridRef.value) {
      updateArrows(gridRef.value);
    }
  });
  resizeObserver.observe(gridRef.value);
};

onMounted(() => {
  nextTick(() => init());
});

onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect();
  resizeObserver = null;
});

watch(() => props.folders.length, () => {
  nextTick(() => init());
});

let resizeHandler: (() => void) | null = null;
onMounted(() => {
  resizeHandler = () => {
    if (gridRef.value) updateArrows(gridRef.value);
  };
  window.addEventListener("resize", resizeHandler);
});
onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener("resize", resizeHandler);
});
</script>

<template>
  <div
    class="album-grid-wrapper"
    :class="{ 'has-overflow': showLeftArrow || showRightArrow }"
  >
    <button
      v-show="showLeftArrow"
      class="album-scroll-btn album-scroll-btn--left"
      :class="{ 'album-scroll-btn--disabled': !showLeftArrow }"
      :disabled="!showLeftArrow"
      @click="scrollAlbums(-1)"
      aria-label="Scroll left"
    >
      <ArrowLeft class="gallery-icon-nav" />
    </button>
    <button
      v-show="showRightArrow"
      class="album-scroll-btn album-scroll-btn--right"
      :class="{ 'album-scroll-btn--disabled': !showRightArrow }"
      :disabled="!showRightArrow"
      @click="scrollAlbums(1)"
      aria-label="Scroll right"
    >
      <ArrowRight class="gallery-icon-nav" />
    </button>
    <div
      ref="gridRef"
      class="album-grid"
      @scroll="onGridScroll"
    >
      <component
        :is="isMobile ? AlbumCardMobile : AlbumCardTablet"
        v-for="item in folders"
        :key="item.path"
        :node="item"
        @click="emit('open-folder', item.path)"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
@import "../styles/breakpoints";

/* ── Album Grid ── */
.album-grid-wrapper {
  position: relative;
  overflow: visible;
}

/* Edge fade overlays */
.album-grid-wrapper.has-overflow::before,
.album-grid-wrapper.has-overflow::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  width: 48px;
  pointer-events: none;
  z-index: 2;
}

.album-grid-wrapper.has-overflow::before {
  left: 0;
  background: linear-gradient(to right, var(--surface-color), transparent);
}

.album-grid-wrapper.has-overflow::after {
  right: 0;
  background: linear-gradient(to left, var(--surface-color), transparent);
}

.album-grid {
  display: flex;
  flex-wrap: nowrap;
  gap: 24px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 24px 12px;
  scrollbar-width: none;
  -ms-overflow-style: none;
  touch-action: pan-x;
  overscroll-behavior-x: contain;
  scroll-behavior: smooth;
}

.album-grid::-webkit-scrollbar {
  display: none;
}

.album-grid > * {
  flex-shrink: 0;
  min-width: 180px;
  max-width: 240px;
  will-change: transform, opacity;
}

/* ── Arrow Buttons ── */
.album-scroll-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 3;
  width: 46px;
  height: 46px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(20, 61, 96, 0.22);
  color: var(--text-color);
  box-shadow:
    0 10px 24px rgba(20, 61, 96, 0.14),
    inset 0 0 0 1px rgba(255, 255, 255, 0.48);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.25s, transform 0.2s, border-color 0.2s, box-shadow 0.2s, background 0.2s, color 0.2s;
  pointer-events: auto;
  opacity: 1;
}

.album-scroll-btn--left {
  left: 12px;
}

.album-scroll-btn--right {
  right: 12px;
}

.album-scroll-btn .gallery-icon-nav {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
  stroke-width: 2.45;
  flex-shrink: 0;
}

.album-scroll-btn--left .gallery-icon-nav {
  transform: translateX(-1px);
}

.album-scroll-btn--right .gallery-icon-nav {
  transform: translateX(1px);
}

.album-scroll-btn:not(:disabled):hover {
  transform: translateY(-50%) scale(1.035);
  color: var(--primary-color);
  border-color: rgba(255, 184, 77, 0.48);
  background: rgba(255, 248, 238, 0.96);
}

.album-scroll-btn:not(:disabled):active {
  transform: translateY(-50%) scale(0.97);
}

.album-scroll-btn--disabled,
.album-scroll-btn:disabled {
  opacity: 0;
  pointer-events: none;
}

/* Dark theme */
:root[data-theme="dark"] .album-scroll-btn {
  background: rgba(32, 28, 24, 0.96);
  border-color: rgba(255, 184, 77, 0.38);
  box-shadow:
    0 12px 30px rgba(0, 0, 0, 0.52),
    inset 0 0 0 1px rgba(255, 216, 138, 0.08);
}

:root[data-theme="dark"] .album-scroll-btn:not(:disabled):hover {
  box-shadow:
    0 12px 30px rgba(0, 0, 0, 0.52),
    inset 0 0 0 1px rgba(255, 184, 77, 0.24);
}

@supports (background: color-mix(in srgb, white 90%, black 10%)) {
  .album-scroll-btn {
    background: color-mix(in srgb, var(--surface-color, #ffffff) 94%, var(--text-color, #143d60) 6%);
    border: 1px solid color-mix(in srgb, var(--text-color, #143d60) 22%, transparent);
    box-shadow:
      var(--gallery-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.12)),
      inset 0 0 0 1px color-mix(in srgb, #ffffff 48%, transparent);
  }

  :root[data-theme="dark"] .album-scroll-btn {
    background: color-mix(in srgb, var(--surface-color, #1a1918) 88%, var(--primary-color, #ffb84d) 12%);
    border-color: color-mix(in srgb, var(--primary-color, #ffb84d) 40%, transparent);
    box-shadow:
      var(--gallery-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.4)),
      inset 0 0 0 1px color-mix(in srgb, #ffffff 12%, transparent);
  }

  .album-scroll-btn:not(:disabled):hover {
    border-color: color-mix(in srgb, var(--primary-color, #ffb84d) 48%, transparent);
    background: color-mix(in srgb, var(--surface-color, #ffffff) 88%, var(--primary-color, #ffb84d) 12%);
  }

  :root[data-theme="dark"] .album-scroll-btn:not(:disabled):hover {
    box-shadow:
      var(--gallery-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.4)),
      inset 0 0 0 1px color-mix(in srgb, var(--primary-color, #ffb84d) 24%, transparent);
  }
}

/* ── Tablet (768px–1199px) ── */
@include tablet {
  .album-grid {
    gap: 12px;
    padding: 4px 8px 20px;
  }
  .album-grid > * {
    min-width: 150px;
    max-width: 200px;
  }

  .album-grid-wrapper.has-overflow::before,
  .album-grid-wrapper.has-overflow::after {
    width: 48px;
  }

  .album-scroll-btn {
    width: 46px;
    height: 46px;
  }

  .album-scroll-btn--left {
    left: 8px;
  }

  .album-scroll-btn--right {
    right: 8px;
  }
}

/* ── Mobile (<768px) ── */
@media (max-width: 767px) {
  .album-grid-wrapper {
    padding: 0;
    margin: 0;
  }

  .album-grid-wrapper.has-overflow::before,
  .album-grid-wrapper.has-overflow::after {
    display: none;
  }

  .album-grid-wrapper .album-grid {
    gap: 12px;
    padding: 4px 0 8px;
    scroll-snap-type: x mandatory;
  }
  .album-grid > * {
    min-width: 130px;
    max-width: 170px;
    scroll-snap-align: start;
  }
  .album-scroll-btn {
    display: none;
  }
  .album-grid-wrapper .album-grid {
    padding: 4px 0 8px;
  }
}

@media (max-width: 480px) {
  .album-grid-wrapper {
    padding: 0;
    margin: 0;
  }
  .album-grid-wrapper .album-grid { gap: 6px; }
  .album-grid > * { min-width: 110px; max-width: 140px; }
}
</style>
