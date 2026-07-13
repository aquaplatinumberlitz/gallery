<script setup lang="ts">
import { ref, watch } from "vue";
import { Film, Play } from "lucide-vue-next";
import { getVideoPosterUrl } from "@/services/api";

const props = defineProps<{ src: string; name?: string; durationMs?: number | null }>();
const emit = defineEmits<{ click: [] }>();
const posterFailed = ref(false);
const posterLoaded = ref(false);

watch(
  () => props.src,
  () => {
    posterFailed.value = false;
    posterLoaded.value = false;
  },
);

const formatDuration = (durationMs?: number | null) => {
  if (!durationMs || durationMs < 0) return "";
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};
</script>

<template>
  <button
    type="button"
    data-testid="video-card"
    class="video-card"
    :aria-label="`Play video ${name || ''}`.trim()"
    @click="emit('click')"
  >
    <div v-if="!posterLoaded && !posterFailed" class="video-shimmer">
      <span class="video-shimmer-wave" />
    </div>
    <img
      v-if="!posterFailed"
      :src="getVideoPosterUrl(src)"
      :alt="name ? `Poster for ${name}` : 'Video poster'"
      loading="lazy"
      @load="posterLoaded = true"
      @error="posterFailed = true"
    />
    <div v-if="posterFailed" class="video-placeholder" data-testid="video-poster-fallback">
      <Film class="gallery-icon-xl" />
      <span>Preview unavailable</span>
    </div>
    <span class="play-button" aria-hidden="true"><Play class="gallery-icon-lg" fill="currentColor" /></span>
    <span v-if="formatDuration(durationMs)" class="duration-badge">{{ formatDuration(durationMs) }}</span>
  </button>
</template>

<style scoped lang="scss">
.video-card {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  border-radius: 12px;
  background: var(--card);
  color: white;
  cursor: pointer;
  contain: content;
  transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
  }

  @media (hover: hover) {
    &:hover {
      transform: translateY(-2px) scale(1.02);
    }
  }

  @media (max-width: 1023px) {
    -webkit-tap-highlight-color: transparent;

    &:active {
      transform: scale(0.97);
    }
  }
}

.video-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--muted) 25%, var(--accent) 50%, var(--muted) 75%);
  background-size: 200% 100%;
  animation: video-shimmer 1.5s infinite;
}

.video-shimmer-wave {
  display: none;
}

.video-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.4rem;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}

.play-button {
  position: absolute;
  inset: 50% auto auto 50%;
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  transform: translate(-50%, -50%);
  border-radius: 999px;
  background: rgb(0 0 0 / 65%);
  backdrop-filter: blur(4px);
}

.duration-badge {
  position: absolute;
  right: 0.5rem;
  bottom: 0.5rem;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  background: rgb(0 0 0 / 70%);
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
}

@keyframes video-shimmer {
  to {
    background-position: -200% 0;
  }
}

@keyframes mobile-video-shimmer {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100%);
  }
}

@media (max-width: 1023px) {
  .video-shimmer {
    overflow: hidden;
    background: linear-gradient(90deg, rgba(0, 0, 0, 0.06), rgba(0, 0, 0, 0.04), rgba(0, 0, 0, 0.06));
    background-size: auto;
    animation: none;
  }

  .video-shimmer-wave {
    position: absolute;
    inset: 0;
    display: block;
    background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.5) 50%, transparent 100%);
    transform: translateX(-100%);
    animation: mobile-video-shimmer 1.5s infinite;
  }

  :global(html[data-theme="dark"]) .video-shimmer {
    background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.08));
  }

  :global(html[data-theme="dark"]) .video-shimmer-wave {
    background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.2) 50%, transparent 100%);
  }
}

@media (max-width: 767px) {
  .play-button {
    background: rgb(0 0 0 / 55%);
  }

  .play-button :deep(svg) {
    transform: scale(0.84);
  }
}

@media (prefers-reduced-motion: reduce) {
  .video-card,
  .video-shimmer,
  .video-shimmer-wave {
    transition: none;
    animation: none;
  }
}
</style>
