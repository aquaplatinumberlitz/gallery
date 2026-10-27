<script setup lang="ts">
import { albumCountLabel } from "@/utils/albumCountLabel";
import type { FileNode } from "../types";
import { getThumbnailUrl } from "../services/api";
import { FolderOpen } from "lucide-vue-next";
import { useCoverImageLoad } from "../composables/useCoverImageLoad";
import { ALBUM_PLACEHOLDER_SVG } from "../utils/albumCardPlaceholder";

const emit = defineEmits<{
  (e: "click"): void;
}>();

defineProps<{
  node: FileNode;
}>();

// Skeleton shimmer shown over the cover until the cover image finishes loading.
const { loaded, markCoverSettled } = useCoverImageLoad();
</script>

<template>
  <div
    class="album-card-tablet"
    data-testid="album-card"
    :data-album-name="node.name"
    @click="emit('click')"
    @keydown.enter="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <div class="album-cover">
      <div v-if="node.cover_images?.[0] && !loaded" class="cover-skeleton" aria-hidden="true">
        <div class="shimmer-wave" />
      </div>
      <img
        v-if="node.cover_images?.[0]"
        :src="getThumbnailUrl(node.cover_images[0])"
        loading="lazy"
        alt=""
        @load="markCoverSettled"
        @error="markCoverSettled"
      />
      <div v-else class="placeholder flex-center">
        <span class="fa-placeholder-svg" v-html="ALBUM_PLACEHOLDER_SVG" />
      </div>
    </div>

    <div class="album-info">
      <h3 class="album-name">
        {{ node.name }}
      </h3>
      <div class="album-meta">
        <FolderOpen class="gallery-icon-meta album-meta-icon" />
        <span class="album-count-badge"
          >Album<span v-if="albumCountLabel(node)"> · {{ albumCountLabel(node) }}</span></span
        >
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.album-card-tablet {
  --album-frame-bg: var(--brand-album-paper);
  --album-frame-border: var(--brand-album-paper-border);
  --album-title-color: var(--brand-album-title);
  --album-meta-color: var(--brand-album-muted);

  width: 100%;
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  background: var(--album-frame-bg);
  border: 1px solid var(--album-frame-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;

  .album-cover {
    position: relative; // Anchor for the in-card skeleton overlay (no visual change)
    width: 100%;
    height: 130px;
    overflow: hidden;
    background: var(--album-frame-bg);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 1;
      transition: opacity 200ms ease;
    }

    .placeholder {
      width: 100%;
      height: 100%;
      background: color-mix(in srgb, var(--album-meta-color) 14%, transparent);
      display: grid;
      place-items: center;
      color: var(--album-meta-color);
    }

    // Card-shape loading skeleton shown transiently until the cover image loads.
    .cover-skeleton {
      position: absolute;
      inset: 0;
      background: linear-gradient(
        90deg,
        color-mix(in srgb, var(--album-meta-color) 10%, transparent),
        color-mix(in srgb, var(--album-meta-color) 6%, transparent),
        color-mix(in srgb, var(--album-meta-color) 10%, transparent)
      );
      overflow: hidden;
      pointer-events: none;
    }
  }

  .album-info {
    padding: 10px 10px 10px;
    margin-top: 0;

    .album-name {
      font-family: var(--font-body);
      font-weight: 600;
      font-size: 15px;
      color: var(--album-title-color);
      margin: 0;
      text-overflow: ellipsis;
      overflow: hidden;
      white-space: nowrap;
    }

    .album-meta {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-family: var(--font-code);
      font-size: 12px;
      color: var(--album-meta-color);
      margin: 4px 0 0;
      letter-spacing: 0.5px;
    }

    .album-meta-icon {
      flex-shrink: 0;
      color: var(--album-meta-color);
    }
    .gallery-icon-meta {
      width: var(--gallery-icon-meta);
      height: var(--gallery-icon-meta);
    }
  }

  // Dark mode
  html[data-theme="dark"] & {
    box-shadow: none;

    .album-name {
      color: var(--album-title-color);
    }
  }

  // Touch-friendly active state
  &:active {
    transform: scale(0.97);
    box-shadow: none;
  }
}

.flex-center {
  display: grid;
  place-items: center;
}

.album-card-tablet:focus {
  outline: none;
}

.album-card-tablet:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
  border-radius: 8px;
}

// FA placeholder SVG - :deep needed because v-html lacks scoped attr
.fa-placeholder-svg :deep(svg) {
  width: 32px;
  height: 32px;
  display: block;
  color: var(--album-meta-color);
}

// Shimmer animation reused from SkeletonLoader pattern — kept local & lightweight
@keyframes album-shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.cover-skeleton .shimmer-wave {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.18) 50%, transparent 100%);
  transform: translateX(-100%);
  animation: album-shimmer 1.5s infinite;
}

@media (hover: none) {
  .cover-skeleton .shimmer-wave {
    animation: none;
    background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.08) 50%, transparent 100%);
    transform: translateX(0);
  }
}

// Dark theme skeleton — Vue scoped adds the data-v attribute to the last
// selector in the chain, so this matches `.cover-skeleton` rendered here.
html[data-theme="dark"] .cover-skeleton {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--album-meta-color) 16%, transparent),
    color-mix(in srgb, var(--album-meta-color) 10%, transparent),
    color-mix(in srgb, var(--album-meta-color) 16%, transparent)
  );
}
html[data-theme="dark"] .cover-skeleton .shimmer-wave {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.08) 50%, transparent 100%);
}

// ── Mobile/tablet-only refinements (<1024px) — desktop styles left unchanged ──
@media (max-width: 1023px) {
  .album-card-tablet {
    border-radius: 12px;

    // Count/stat badge — pill shape, subtle tinted background, clearer hierarchy
    .album-count-badge {
      display: inline-flex;
      align-items: center;
      padding: 1px 8px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--album-meta-color) 12%, transparent);
      color: var(--album-meta-color);
      font-size: 11px;
      line-height: 1.55;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }

    // Subtle lift on hover-capable devices (trackpad/mouse)
    @media (hover: hover) {
      &:hover {
        transform: translateY(-2px);
        box-shadow:
          0 4px 10px rgba(0, 0, 0, 0.08),
          0 8px 18px rgba(0, 0, 0, 0.06);
        border-color: color-mix(in srgb, var(--album-meta-color) 28%, var(--album-frame-border));
      }
    }

    // Refined tap feedback — subtle press scale, tightened border, keep depth
    &:active {
      transform: scale(0.97);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
      border-color: color-mix(in srgb, var(--album-meta-color) 40%, var(--album-frame-border));
    }
  }

  html[data-theme="dark"] .album-card-tablet {
    .album-count-badge {
      background: color-mix(in srgb, var(--album-meta-color) 18%, transparent);
    }

    @media (hover: hover) {
      &:hover {
        box-shadow: 0 0 14px rgba(255, 255, 255, 0.08);
      }
    }
  }
}
</style>
