<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from "vue";
import { getThumbnailUrl, getImageUrl } from "../services/api";
import { Image } from "lucide-vue-next";

const props = defineProps<{
  src?: string;
  name?: string;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const isLoaded = ref(false);
const hasError = ref(false);
const isHovering = ref(false);
let hoverTimer: ReturnType<typeof setTimeout> | null = null;

// Check if image is potentially animated based on extension
const isAnimated = computed(() => {
  if (!props.name) return false;
  const ext = props.name.split('.').pop()?.toLowerCase();
  return ext === 'webp' || ext === 'gif';
});

const shouldPlay = ref(false);
const previewSrc = ref("");

const onMouseEnter = () => {
  // Guard: skip hover animation on touch devices (prevents sticky hover state)
  if (window.matchMedia('(hover: none)').matches) return;

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

const onImageLoad = () => {
  isLoaded.value = true;
};

const onImageError = () => {
  hasError.value = true;
};

watch(
  () => props.src,
  () => {
    isLoaded.value = false;
    hasError.value = false;
    shouldPlay.value = false;
    previewSrc.value = "";
  },
);

onBeforeUnmount(() => {
  if (hoverTimer) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }
});
</script>

<template>
  <div 
    class="photo-card" 
    :class="{ loaded: isLoaded }" 
    @click="emit('click')"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @keydown.enter="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <!-- Shimmer placeholder -->
    <div v-if="!isLoaded && !hasError" class="shimmer-placeholder">
      <div class="shimmer-wave"></div>
    </div>
    
    <!-- Static Thumbnail (Always visible initially) -->
    <img 
      v-if="props.src && !hasError" 
      :src="getThumbnailUrl(props.src)" 
      loading="lazy"
      @load="onImageLoad"
      @error="onImageError"
      :alt="props.name || 'Gallery image'"
      class="thumbnail-img"
    />

    <!-- Animated Preview (Overlay on hover) -->
    <transition name="fade">
      <img 
        v-if="shouldPlay && previewSrc && !hasError" 
        :src="previewSrc" 
        class="preview-overlay"
        alt=""
      />
    </transition>

    <!-- Badge for animated files -->
    <div v-if="isAnimated && isLoaded" class="type-badge">
      <span v-if="shouldPlay">PLAYING</span>
      <span v-else>GIF</span>
    </div>

    <div v-if="!props.src || hasError" class="placeholder">
      <Image :size="22" />
      <span class="placeholder-text">{{ hasError ? "Preview unavailable" : "" }}</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.photo-card {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface-color, #fff);
  /* Facebook-inspired: no shadow */
  box-shadow: none;
  transition: 
    transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
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
  // Uses --photocard-border from tokens.css (set via data-theme attribute)
  border: 1px solid var(--photocard-border, transparent);
  box-shadow: none;

  /* ── Mobile overrides ── */
  @media (max-width: 767px) {
    &:active {
      transform: scale(0.97);
    }
  }
}

.thumbnail-img {
  opacity: 0;
  transition: opacity 0.3s ease, transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
}

.photo-card.loaded .thumbnail-img {
  opacity: 1;
}

.preview-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: var(--surface-color, #fff);
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
  color: var(--muted-text);
  font-size: 22px;
  text-align: center;
  gap: 6px;
  padding: 10px;
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
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.5) 50%,
    transparent 100%
  );
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
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.2) 50%,
    transparent 100%
  );
}
</style>
