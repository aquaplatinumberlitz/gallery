<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    type?: "album" | "photo";
  }>(),
  {
    type: "photo",
  }
);
</script>

<template>
  <div class="skeleton" :class="`skeleton--${props.type}`">
    <div class="skeleton-block">
      <div class="shimmer-wave"></div>
    </div>
    <div v-if="props.type === 'album'" class="skeleton-meta">
      <div class="skeleton-line">
        <div class="shimmer-wave"></div>
      </div>
      <div class="skeleton-line short">
        <div class="shimmer-wave"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton--photo .skeleton-block {
  aspect-ratio: 1;
}

.skeleton--album .skeleton-block {
  aspect-ratio: 4 / 5;
}

.skeleton-block {
  width: 100%;
  border-radius: 12px;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0.05), rgba(0, 0, 0, 0.035), rgba(0, 0, 0, 0.05));
  overflow: hidden;
  position: relative;
}

.skeleton-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 12px;
  width: 100%;
  border-radius: 8px;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0.05), rgba(0, 0, 0, 0.035), rgba(0, 0, 0, 0.05));
  position: relative;
}

.skeleton-line.short {
  width: 60%;
}

/* Shimmer wave - sử dụng div thực thay vì ::after */
.shimmer-wave {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.22) 50%,
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

/* Disable shimmer animation on touch devices — use static gradient */
@media (hover: none) {
  .shimmer-wave {
    animation: none;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.11) 50%,
      transparent 100%
    );
    transform: translateX(0);
  }

  :global(html[data-theme="dark"]) .shimmer-wave {
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.06) 50%,
      transparent 100%
    );
  }
}

:global(html[data-theme="dark"]) .skeleton-block,
:global(html[data-theme="dark"]) .skeleton-line {
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.08));
}

:global(html[data-theme="dark"]) .shimmer-wave {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.12) 50%,
    transparent 100%
  );
}
</style>
