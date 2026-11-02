<script lang="ts">
// Thumbnail URLs that finished loading at least once in this session (module scope, shared by every
// card). A card mounted again for one of them, e.g. when a virtual row scrolls back into range, skips
// the visibility dwell: the browser serves it from cache, so there is nothing worth cancelling.
const seenThumbnailUrls = new Set<string>();
</script>

<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from "vue";
import { getThumbnailUrl, getThumbnailSrcset, getImageUrl } from "../services/api";
import { Image } from "lucide-vue-next";
import AssetActionMenu from "@/components/AssetActionMenu.vue";
import { useVisibleLoadGate } from "../composables/useVisibleLoadGate";
import { useRenderedWidth } from "../composables/useRenderedWidth";
import { coverAspectRatio, thumbnailSizes } from "../utils/thumbnailSizes";

// ── Global image load cache ──
// Persists across virtualized mount/unmount cycles so shimmer doesn't re-appear
const loadedImages = new Set<string>();

const props = withDefaults(
  defineProps<{
    src?: string;
    name?: string;
    /** Backend `content_version`; appended as `v` so the thumbnail URLs are immutable-cacheable. */
    version?: string | null;
    /** Asset dimensions (when known) so `sizes` accounts for the `object-fit: cover` crop. */
    imageWidth?: number | null;
    imageHeight?: number | null;
    thumbnailSize?: number;
    fetchPriority?: "auto" | "high" | "low";
    loadDelayMs?: number;
    canFindRelated?: boolean;
  }>(),
  {
    src: undefined,
    name: undefined,
    version: undefined,
    imageWidth: undefined,
    imageHeight: undefined,
    thumbnailSize: 512,
    fetchPriority: "auto",
    loadDelayMs: 0,
    canFindRelated: false,
  },
);

const emit = defineEmits<{
  (e: "click"): void;
  (e: "dimensions", dimensions: { path: string; width: number; height: number }): void;
  (e: "find-related"): void;
}>();

const isLoaded = ref(props.src ? loadedImages.has(props.src) : false);
const hasError = ref(false);
const isHovering = ref(false);
const thumbnailSrc = ref("");
const cardShell = ref<HTMLElement | null>(null);
const thumbnailEl = ref<HTMLImageElement | null>(null);

// The thumbnail request only starts once the card has rested in view (see useVisibleLoadGate) and is
// cancelled by clearing `src` when the card leaves first. First-row cards (fetchPriority="high") and
// thumbnails already loaded in this session skip the gate so the initial viewport and revisits stay instant.
const { shouldLoad, reset: resetLoadGate } = useVisibleLoadGate({
  target: cardShell,
  settled: () => isLoaded.value || hasError.value,
  immediate: () => props.fetchPriority === "high" || seenThumbnailUrls.has(thumbnailSrc.value),
});

// `srcset` offers the 256 and 512 px derivatives (the `src` fallback is the largest). `sizes` is the card's
// measured rendered width, so the browser picks 256 only where it has enough pixels for the covered box.
// Without a measured width (not laid out yet) only `src` is used, exactly as before srcset existed.
const cardWidth = useRenderedWidth(cardShell);
const thumbnailSrcset = computed(() =>
  props.src && props.thumbnailSize === 512 && cardWidth.value > 0
    ? getThumbnailSrcset(props.src, props.version)
    : undefined,
);
const thumbnailSizesAttr = computed(() =>
  thumbnailSrcset.value
    ? thumbnailSizes(cardWidth.value, coverAspectRatio(props.imageWidth, props.imageHeight))
    : undefined,
);
let hoverTimer: ReturnType<typeof setTimeout> | null = null;
let thumbnailTimer: ReturnType<typeof setTimeout> | null = null;

// Check if image is potentially animated based on extension
const isAnimated = computed(() => {
  if (!props.name) return false;
  const ext = props.name.split(".").pop()?.toLowerCase();
  return ext === "webp" || ext === "gif";
});

const shouldPlay = ref(false);
const previewSrc = ref("");

const clearThumbnailTimer = () => {
  if (thumbnailTimer) {
    clearTimeout(thumbnailTimer);
    thumbnailTimer = null;
  }
};

const queueThumbnailLoad = () => {
  clearThumbnailTimer();
  thumbnailSrc.value = "";
  if (!props.src) return;

  const load = () => {
    thumbnailSrc.value = props.src ? getThumbnailUrl(props.src, props.thumbnailSize, props.version) : "";
  };

  if (props.loadDelayMs > 0) {
    thumbnailTimer = setTimeout(load, props.loadDelayMs);
  } else {
    load();
  }
};

const onMouseEnter = () => {
  // Guard: skip hover animation on touch devices (prevents sticky hover state)
  if (window.matchMedia("(hover: none)").matches) return;

  isHovering.value = true;
  if (!isAnimated.value) return;

  // Small delay to avoid loading full image on quick mouse hover
  hoverTimer = setTimeout(() => {
    shouldPlay.value = true;
    previewSrc.value = props.src ? getImageUrl(props.src) : "";
  }, 150);
};

const onMouseLeave = () => {
  isHovering.value = false;
  if (hoverTimer) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }
  shouldPlay.value = false;
  // Stop loading full image when hover ends
  previewSrc.value = "";
};

const onImageLoad = (event: Event) => {
  isLoaded.value = true;
  // Register in global cache so shimmer doesn't re-appear on recycle
  if (props.src) loadedImages.add(props.src);
  if (thumbnailSrc.value) seenThumbnailUrls.add(thumbnailSrc.value);

  const img = event.target instanceof HTMLImageElement ? event.target : null;
  if (props.src && img?.naturalWidth && img.naturalHeight) {
    emit("dimensions", {
      path: props.src,
      width: img.naturalWidth,
      height: img.naturalHeight,
    });
  }
};

const onImageError = (event: Event) => {
  // Clearing `src` to cancel a request can surface as an error event; that is not a failed image.
  const img = event.target instanceof HTMLImageElement ? event.target : null;
  if (img && !img.getAttribute("src")) return;
  hasError.value = true;
};

watch(
  () => [props.src, props.thumbnailSize, props.loadDelayMs, props.version] as const,
  ([newSrc]) => {
    hasError.value = false;
    shouldPlay.value = false;
    previewSrc.value = "";
    // If image was already loaded in a previous render cycle, skip shimmer
    if (newSrc && loadedImages.has(newSrc)) {
      isLoaded.value = true;
    } else {
      isLoaded.value = false;
    }
    queueThumbnailLoad();
    resetLoadGate();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  clearThumbnailTimer();
  // Desktop/tablet/mobile grids unmount cards that scroll far away: abort an unfinished request now,
  // detached images keep downloading otherwise.
  if (!isLoaded.value) thumbnailEl.value?.removeAttribute("src");
  if (hoverTimer) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }
});
</script>

<template>
  <div
    ref="cardShell"
    class="photo-card-shell"
    data-testid="photo-card-shell"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <div
      data-testid="photo-card"
      class="photo-card"
      :class="{ loaded: isLoaded }"
      @click="emit('click')"
      @keydown.enter="emit('click')"
      @keydown.space.prevent="emit('click')"
      role="button"
      tabindex="0"
      :aria-label="props.name ? `Open ${props.name}` : 'Open gallery image'"
    >
      <!-- Shimmer placeholder -->
      <div v-if="!isLoaded && !hasError" class="shimmer-placeholder">
        <div class="shimmer-wave" />
      </div>

      <!-- Static Thumbnail (Always visible initially) -->
      <img
        v-if="thumbnailSrc && !hasError"
        ref="thumbnailEl"
        :srcset="shouldLoad ? thumbnailSrcset : undefined"
        :sizes="thumbnailSizesAttr"
        :src="shouldLoad ? thumbnailSrc : undefined"
        :loading="props.fetchPriority === 'high' ? 'eager' : 'lazy'"
        decoding="async"
        :fetchpriority="props.fetchPriority"
        @load="onImageLoad"
        @error="onImageError"
        :alt="props.name || 'Gallery image'"
        class="thumbnail-img"
      />

      <!-- Animated Preview (Overlay on hover) -->
      <transition name="fade">
        <img v-if="shouldPlay && previewSrc && !hasError" :src="previewSrc" class="preview-overlay" alt="" />
      </transition>

      <!-- Badge for animated files -->
      <div v-if="isAnimated && isLoaded" class="type-badge">
        <span v-if="shouldPlay">PLAYING</span>
        <span v-else>GIF</span>
      </div>

      <div v-if="!props.src || hasError" class="placeholder">
        <Image class="gallery-icon-xl" />
        <span class="placeholder-text" data-testid="placeholder-text">{{ hasError ? "Preview unavailable" : "" }}</span>
      </div>
    </div>

    <AssetActionMenu
      v-if="props.canFindRelated"
      class="photo-action-menu"
      :label="props.name ? `Image actions for ${props.name}` : 'Image actions'"
      @find-related="emit('find-related')"
      @click.stop
    />
  </div>
</template>

<style scoped lang="scss">
.photo-card-shell {
  position: relative;
  width: 100%;
  /* Enable container queries so child elements can respond to card width */
  container-type: inline-size;
  container-name: photo-card;
}

.photo-card {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 12px;
  overflow: hidden;
  background: var(--card);
  /* Facebook-inspired: no shadow */
  box-shadow: none;
  contain: content; /* Isolate layout/paint — prevents reflows during scroll */
  transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  /* Desktop hover only — not sticky on touch */
  @media (hover: hover) {
    &:hover {
      transform: translateY(-2px) scale(1.02);

      .thumbnail-img {
        transform: scale(1.05);
        transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
      }
    }
  }

  &:active {
    transform: translateY(0) scale(1.01);
  }

  /* Focus styles for keyboard navigation */
  &:focus {
    outline: none;
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
  }

  // Dark mode - Apple Style
  // Content-first: image fills 100%, no padding
  // Subtle border glow for hover feedback
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  box-shadow: none;

  /* ── Mobile overrides ── */
  @media (max-width: 767px) {
    &:active {
      transform: scale(0.97);
    }
  }
}

.photo-action-menu {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 5;
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 180ms cubic-bezier(0.4, 0, 0.2, 1),
    transform 180ms cubic-bezier(0.4, 0, 0.2, 1);
}

.photo-card-shell:hover .photo-action-menu,
.photo-card-shell:focus-within .photo-action-menu {
  opacity: 1;
  transform: translateY(0);
}

/* Mobile: icon circle sits bottom-right, always visible, no animation */
@media (hover: none) {
  .photo-action-menu {
    top: auto;
    bottom: 6px;
    right: 6px;
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/*
  Container query: hide pill text when card < 200px wide.
  Covers tablet multi-column layouts (4–5 cols) and any small-grid desktop.
  The button collapses to icon-only circle automatically — no JS needed.
  :deep() pierces scoped boundary to target AssetActionMenu internals.
*/
@container photo-card (max-width: 199px) {
  :deep(.action-label) {
    display: none;
  }

  :deep(.asset-action-trigger) {
    width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    gap: 0;
  }
}

.thumbnail-img {
  opacity: 0;
  transition:
    opacity 0.3s ease,
    transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
}

.photo-card.loaded .thumbnail-img {
  opacity: 1;
}

.preview-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: var(--card);
}

.type-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  color: white;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  z-index: 3;
  pointer-events: none;
  letter-spacing: 0.5px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--muted-foreground);
  font-size: 22px;
  text-align: center;
  gap: 6px;
  padding: 10px;
}

.gallery-icon-xl {
  width: var(--gallery-icon-xl);
  height: var(--gallery-icon-xl);
}

.placeholder-text {
  font-size: 12px;
}

/* Shimmer placeholder styles */
.shimmer-placeholder {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0.06), rgba(0, 0, 0, 0.04), rgba(0, 0, 0, 0.06));
  overflow: hidden;
}

.photo-card.loaded .shimmer-placeholder {
  display: none;
}

.shimmer-wave {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.5) 50%, transparent 100%);
  transform: translateX(-100%);
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

/* Dark mode shimmer overrides via CSS variable (set by tokens.css data-theme) */
html[data-theme="dark"] .shimmer-placeholder {
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.08));
}

html[data-theme="dark"] .shimmer-wave {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.2) 50%, transparent 100%);
}
</style>
