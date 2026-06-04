<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import PhotoSwipe from "photoswipe";
import "photoswipe/dist/photoswipe.css";
import { X } from "lucide-vue-next";
import type { FileNode } from "../types";
import { buildPhotoSwipeItem } from "../utils/lightbox";

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
let pswp: PhotoSwipe | null = null;

const counter = computed(() => `${props.currentIndex + 1} / ${props.items.length}`);

// Build PhotoSwipe data source — tablet uses 2048px thumbnails
const pswpItems = computed(() =>
  props.items.map((item) => buildPhotoSwipeItem(item, 2048))
);

function initPhotoSwipe() {
  if (!containerRef.value || !props.isOpen || pswp) return;

  pswp = new PhotoSwipe({
    dataSource: pswpItems.value,
    index: props.currentIndex,
    appendToEl: containerRef.value,
    closeOnVerticalDrag: true,
    allowPanToNext: true,
    showHideAnimationType: "zoom",
    wheelToZoom: false,
    bgOpacity: 1,
  });

  pswp.on("change", () => {
    if (pswp) {
      emit("indexChange", pswp.currIndex);
    }
  });

  pswp.on("close", () => {
    destroyPhotoSwipe();
    emit("close");
  });

  pswp.on("uiRegister", () => {
    pswp!.ui!.registerElement({
      name: "metadata-info",
      order: 9,
      isButton: true,
      html: {
        isCustomSVG: true,
        inner:
          '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 16v-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 8h.01" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        size: 24,
      },
      onInit: (el: HTMLElement) => {
        el.classList.add("pswp__button--metadata-info");
        if (props.metadataOpen) {
          el.classList.add("active");
          el.setAttribute("aria-label", "Close image info");
        } else {
          el.setAttribute("aria-label", "View image info");
        }
      },
      onClick: () => emit("toggleMetadata"),
    });
  });

  pswp.init();

  // Move the info button outside .tablet-photoswipe-container into .lightbox-overlay
  const infoBtn = document.querySelector<HTMLElement>(
    ".pswp__button--metadata-info"
  );
  if (infoBtn) {
    infoBtn.classList.remove("pswp__hide-on-close");
    const overlay = document.querySelector<HTMLElement>(".lightbox-overlay");
    if (overlay) {
      overlay.appendChild(infoBtn);
    }
  }
}

function destroyPhotoSwipe() {
  if (pswp) {
    try {
      pswp.destroy();
    } catch (_) {
      // Already destroyed
    }
    pswp = null;
  }
}

// Watch isOpen — init when opening, destroy when closing
watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      setTimeout(() => initPhotoSwipe(), 0);
    } else {
      destroyPhotoSwipe();
    }
  }
);

// Watch currentIndex — sync PhotoSwipe if instance exists
watch(
  () => props.currentIndex,
  (index) => {
    if (pswp && pswp.currIndex !== index) {
      pswp.goTo(index);
    }
  }
);

// Watch metadataOpen — toggle active state on the info button
watch(() => props.metadataOpen, (isOpen) => {
  const btn = document.querySelector<HTMLElement>(
    ".pswp__button--metadata-info"
  );
  if (btn) {
    btn.classList.toggle("active", !!isOpen);
    btn.classList.toggle("hidden", !!isOpen);
    btn.setAttribute("aria-label", isOpen ? "Close image info" : "View image info");
  }
});

onMounted(() => {
  if (props.isOpen) {
    initPhotoSwipe();
  }
});

onUnmounted(() => {
  destroyPhotoSwipe();
});
</script>

<template>
  <div ref="containerRef" class="tablet-photoswipe-container"></div>
  <button
    class="tablet-photoswipe-close"
    aria-label="Close"
    @click="emit('close')"
  >
    <X :size="24" :stroke-width="1.5" />
  </button>
  <div class="tablet-photoswipe-counter">{{ counter }}</div>
</template>

<style scoped lang="scss">
.tablet-photoswipe-container {
  position: fixed;
  inset: 0;
  z-index: 1;
}

.tablet-photoswipe-close {
  position: fixed;
  top: 16px;
  right: 16px;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  padding: 0;
  background: rgba(0, 0, 0, 0.5);
  border: none;
  border-radius: 50%;
  color: #fff;
  cursor: pointer;
  z-index: 5000;
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
}

.tablet-photoswipe-counter {
  position: fixed;
  bottom: 24px;
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
</style>

<!-- Global PhotoSwipe 5 theme overrides — not scoped since PhotoSwipe DOM is generated by the library -->
<style lang="scss">
@import '../styles/lightbox-shared';

/* Theme the PhotoSwipe background to match our dark gallery theme */
.pswp {
  --pswp-bg: #000;
  --pswp-icon-color: #fff;
  --pswp-icon-color-secondary: #a09888;
}

/* Hide PhotoSwipe's own close/zoom — we use our own overlay controls */
.pswp__button--close,
.pswp__button--zoom {
  display: none !important;
}

/* Hide top bar (counter, close) — we have our own */
.pswp__top-bar {
  opacity: 0 !important;
  pointer-events: none !important;
}
</style>
