<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { FileNode } from "../types";
import { ArrowLeft, ArrowRight, ChevronDown, FolderOpen } from "lucide-vue-next";
import AlbumCard from "./AlbumCard.vue";

const props = defineProps<{
  folders: FileNode[];
}>();

const emit = defineEmits<{
  (e: "open-folder", path: string): void;
}>();

// ── Collapse state — persist to localStorage ──
const COLLAPSE_KEY = "gallery-albums-collapsed";
const collapsed = ref(false);

onMounted(() => {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    if (saved !== null) collapsed.value = saved === "true";
  } catch {
    /* localStorage unavailable */
  }
});

function toggleCollapsed() {
  collapsed.value = !collapsed.value;
  try {
    localStorage.setItem(COLLAPSE_KEY, String(collapsed.value));
  } catch {
    /* localStorage unavailable */
  }
}

// ── Refs ──
const gridRef = ref<HTMLElement | null>(null);
const showLeftArrow = ref(false);
const showRightArrow = ref(false);

// ── ResizeObserver for realtime overflow tracking ──
let resizeObserver: ResizeObserver | null = null;
let scrollTick = false; // RAF throttle

const updateArrows = (grid: HTMLElement) => {
  const { scrollLeft, scrollWidth, clientWidth } = grid;
  showLeftArrow.value = scrollLeft > 4;
  showRightArrow.value = scrollLeft < scrollWidth - clientWidth - 4;
};

// Called by both scroll event and ResizeObserver
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

// ── Scroll logic (thay vì đọc children[0], dùng querySelector) ──
const scrollAlbums = (direction: number) => {
  const grid = gridRef.value;
  if (!grid) return;

  // Safer: querySelector thay children[0] (tránh Vue component wrapper issue)
  const card = grid.querySelector<HTMLElement>('[class*="album-card"]');
  if (!card) return;

  const cardWidth = card.offsetWidth || 200;
  const gap = parseInt(getComputedStyle(grid).gap) || 24;
  const scrollAmount = (cardWidth + gap) * direction;

  grid.scrollBy({ left: scrollAmount, behavior: "smooth" });

  // Update arrows after scroll animation completes
  setTimeout(() => scheduleArrowsUpdate(grid), 350);
};

// ── Lifecycle ──
const init = () => {
  if (!gridRef.value) return;
  updateArrows(gridRef.value);

  // Set up ResizeObserver to recalculate when grid size changes
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

// Re-init when folders data changes
watch(() => props.folders.length, () => {
  nextTick(() => init());
});

// Re-init on window resize (phòng trường hợp sidebar toggle)
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
  <section v-if="folders.length" class="album-scroller">
    <button
      class="section-title album-toggle"
      @click="toggleCollapsed"
      :aria-expanded="!collapsed"
      :aria-label="collapsed ? 'Expand albums' : 'Collapse albums'"
    >
     <h3>Albums</h3>
     <span class="album-count-badge">
       <FolderOpen :size="13" />
       {{ folders.length }}
       <ChevronDown :size="14" class="toggle-chevron-inline" :class="{ collapsed }" />
     </span>
   </button>
    <div class="album-arrows" v-show="!collapsed">
      <button
        v-if="showLeftArrow"
        class="album-scroll-btn"
        @click="scrollAlbums(-1)"
        aria-label="Scroll left"
      >
        <ArrowLeft :size="24" />
      </button>
      <button
        v-if="showRightArrow"
        class="album-scroll-btn"
        @click="scrollAlbums(1)"
        aria-label="Scroll right"
      >
        <ArrowRight :size="24" />
      </button>
    </div>
    <Transition name="album-collapse">
      <div class="album-grid-wrapper" v-show="!collapsed">
        <div
          ref="gridRef"
          class="album-grid"
          @scroll="onGridScroll"
        >
          <AlbumCard
            v-for="item in folders"
            :key="item.path"
            :node="item"
            @click="emit('open-folder', item.path)"
          />
        </div>
      </div>
    </Transition>
  </section>
</template>

<style scoped>
.album-scroller {
  margin-bottom: 8px;
  padding-left: 10px;
  pointer-events: auto; /* restore interactivity — GlowContainer sets pointer-events:none */
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-title h3 {
  margin: 0;
  font-family: "Cinzel", serif;
  font-size: 16px;
  color: var(--primary-color);
  position: relative;
  display: inline-block;
}

.section-title h3::after {
  content: "";
  position: absolute;
  bottom: -4px;
  left: 0;
  width: 100%;
  height: 1.5px;
  background: linear-gradient(90deg, var(--primary-color, #d6a15d) 0%, transparent 100%);
  border-radius: 1px;
}

.album-count-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  font-size: 12px;
  font-family: var(--font-code);
  color: var(--primary-color);
}

.album-arrows {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
  margin-left: auto;
  margin-bottom: 4px;
}

/* ── Album Grid ── */
.album-grid-wrapper {
  position: relative;
  overflow: visible;
  padding: var(--glow-bleed-y, 56px) var(--glow-bleed-x, 50px) var(--glow-bleed-bottom, 32px);
  margin: calc(-1 * var(--glow-bleed-y, 56px)) calc(-1 * var(--glow-bleed-x, 50px)) calc(-1 * var(--glow-bleed-bottom, 32px));
}

.album-grid {
  display: flex;
  flex-wrap: nowrap;
  gap: 24px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 56px 50px;  /* 56px top/bottom = 50px glow + 6px margin; 50px left/right cho horizontal glow */
  scrollbar-width: none;
  -ms-overflow-style: none;
  /* Smooth scroll behavior */
  scroll-behavior: smooth;
}

.album-grid::-webkit-scrollbar {
  display: none;
}

.album-grid > * {
  flex-shrink: 0;
  min-width: 180px;
  max-width: 240px;
}

/* ── Arrow Buttons ── */
.album-scroll-btn {
  position: relative;
  top: auto;
  transform: none;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid var(--border-color, rgba(0,0,0,0.12));
  background: var(--surface-color, #fff);
  color: var(--text-color, #333);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s, transform 0.2s, border-color 0.2s, box-shadow 0.2s, background 0.2s;
  flex-shrink: 0;
  z-index: 2;
}

.album-scroll-btn:hover {
  transform: scale(1.15);
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, var(--surface-color));
  color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.album-scroller:hover .album-scroll-btn {
  opacity: 1;
}

.album-scroll-btn:active {
  transform: scale(0.95);
  box-shadow: none;
}

/* Dark theme: subtle glow on hover */
:root[data-theme="dark"] .album-scroll-btn:hover {
  box-shadow: 0 0 8px color-mix(in srgb, var(--primary-color) 40%, transparent),
              0 4px 12px color-mix(in srgb, var(--primary-color) 20%, transparent);
}

@media (max-width: 767px) {
  .album-grid-wrapper {
    --glow-bleed-x: 12px;
    --glow-bleed-y: 12px;
    --glow-bleed-bottom: 12px;
  }
  .album-grid {
    gap: 12px;
    padding: 4px 0 12px;
    scroll-snap-type: x mandatory;
  }
  .album-grid > * {
    min-width: 130px;
    max-width: 170px;
    scroll-snap-align: start;
  }
  .album-scroll-btn {
    opacity: 1;
    width: 42px;
    height: 42px;
  }
}

@media (max-width: 480px) {
  .album-grid-wrapper {
    --glow-bleed-x: 8px;
    --glow-bleed-y: 8px;
    --glow-bleed-bottom: 8px;
  }
  .album-grid { gap: 8px; }
  .album-grid > * { min-width: 110px; max-width: 140px; }
}

/* ── Collapsible toggle button ── */
.album-toggle {
  cursor: pointer;
  border: none;
  background: transparent;
  padding: 0;
  font: inherit;
  color: inherit;
  width: 100%;
  text-align: left;
  position: relative;
  z-index: 3;
}

.toggle-chevron-inline {
  margin-left: 4px;
  vertical-align: middle;
  transition: transform 0.3s ease;
  opacity: 0.6;
  flex-shrink: 0;
}

.toggle-chevron-inline.collapsed {
  transform: rotate(-90deg);
}

.album-toggle:hover .toggle-chevron-inline {
  opacity: 1;
}

/* ── Collapse animation ── */
.album-collapse-enter-active,
.album-collapse-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.album-collapse-enter-from,
.album-collapse-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.album-collapse-enter-to,
.album-collapse-leave-from {
  max-height: 600px;
  opacity: 1;
}

/* Mobile: hide album arrows (snap-scroll instead) */
@media (max-width: 767px) {
  .album-arrows { display: none; }
}
</style>
