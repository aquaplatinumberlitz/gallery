<script setup lang="ts">
import { ref } from "vue";
import type { FileNode } from "../types";
import { getThumbnailUrl } from "../services/api";
import { FolderOpen } from "lucide-vue-next";

// FA SVG placeholder icon
const placeholderSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M128 96L576 96L576 480L128 480L128 96zM80 192L80 528L480 528L480 576L32 576L32 192L80 192zM224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160C206.3 160 192 174.3 192 192C192 209.7 206.3 224 224 224zM272 272L176 416L528 416L400 208L318.1 341.1L272 272z"/></svg>`;

const emit = defineEmits<{
  (e: "click"): void;
}>();

defineProps<{
  node: FileNode;
}>();

// Skeleton shimmer shown over the cover until the cover image finishes loading.
const loaded = ref(false);
const onCoverLoad = () => {
  loaded.value = true;
};
const onCoverError = () => {
  loaded.value = true;
};
</script>

<template>
  <div
    class="album-card-mobile"
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
        @load="onCoverLoad"
        @error="onCoverError"
      />
      <div v-else class="placeholder flex-center">
        <span class="fa-placeholder-svg" v-html="placeholderSvg" />
      </div>
    </div>

    <div class="album-info">
      <h3 class="album-name">
        {{ node.name }}
      </h3>
      <div class="album-meta">
        <FolderOpen class="gallery-icon-meta album-meta-icon" />
        <span
          v-if="node.image_count !== undefined && node.image_count !== null"
          class="album-count-badge"
          >{{ node.image_count }} {{ node.image_count === 1 ? "photo" : "photos" }}</span
        >
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.album-card-mobile {
  --album-frame-bg: var(--brand-album-paper);
  --album-frame-border: var(--brand-album-paper-border);
  --album-title-color: var(--brand-album-title);
  --album-meta-color: var(--brand-album-muted);
  --album-card-radius: 10px;

  width: 100%;
  min-height: 44px; // Ensure tap target stays above 44px
  cursor: pointer;
  border-radius: var(--album-card-radius);
  overflow: hidden; // Outer card clips content — clean straight edge at bottom
  background: var(--album-frame-bg);
  border: 1px solid var(--album-frame-border);
  // Subtle layered elevation for visual hierarchy on small screens
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.05),
    0 2px 6px rgba(0, 0, 0, 0.04);
  transition:
    transform 160ms ease,
    box-shadow 160ms ease,
    border-color 160ms ease,
    opacity 160ms ease;

  .album-cover {
    position: relative; // Anchor for the in-card skeleton overlay
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: var(--album-card-radius) var(--album-card-radius) 0 0; // Only top corners rounded
    overflow: hidden;
    border: none; // Removed border for cleaner look (Apple Photos style)
    background: var(--album-frame-bg);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08); // Subtle depth (Google Photos style)

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      // Fade the cover in once it loads, hiding the swap from skeleton → image
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

    // Card-shape loading skeleton shown until the cover image finishes loading.
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
    padding: 0 10px 10px;
    margin-top: 7px;

    .album-name {
      font-family: var(--font-body);
      font-weight: 600;
      font-size: 13px;
      line-height: 1.3;
      color: var(--album-title-color);
      margin: 0;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      overflow: hidden;
      text-overflow: ellipsis;
      word-break: break-word; // Prevent long words breaking layout
      overflow-wrap: break-word; // Fallback for word-break
    }

    .album-meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-family: var(--font-code);
      font-size: 11px; // Increased from 10px → 11px (better readability)
      color: var(--album-meta-color);
      margin: 6px 0 0;
      letter-spacing: 0.4px;
    }
    .album-meta-icon {
      flex-shrink: 0;
      color: var(--album-meta-color);
    }
    .gallery-icon-meta {
      width: var(--gallery-icon-meta);
      height: var(--gallery-icon-meta);
    }

    // Count/stat badge — pill shape, subtle tinted background, clear hierarchy
    .album-count-badge {
      display: inline-flex;
      align-items: center;
      padding: 1px 8px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--album-meta-color) 12%, transparent);
      color: var(--album-meta-color);
      font-size: 10.5px;
      line-height: 1.55;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }
  }

  // Hover only for devices with hover capability (desktop/trackpad)
  @media (hover: hover) {
    &:hover {
      transform: translateY(-2px);
      box-shadow:
        0 4px 10px rgba(0, 0, 0, 0.08),
        0 8px 18px rgba(0, 0, 0, 0.06);
      border-color: color-mix(in srgb, var(--album-meta-color) 28%, var(--album-frame-border));

      .album-cover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        transition:
          box-shadow 200ms ease;
      }
    }
  }

  html[data-theme="dark"] & {
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.04);

    .album-cover {
      box-shadow: 0 0 8px rgba(255, 255, 255, 0.04); // Subtle glow in dark mode
      border: none;
    }

    .album-name {
      color: var(--album-title-color);
    }

    .album-count-badge {
      background: color-mix(in srgb, var(--album-meta-color) 18%, transparent);
    }

    @media (hover: hover) {
      &:hover {
        box-shadow: 0 0 14px rgba(255, 255, 255, 0.08);
        .album-cover {
          box-shadow: 0 0 12px rgba(255, 255, 255, 0.08);
        }
      }
    }
  }

  // Tap feedback — subtle press scale, slight border tighten
  &:active {
    transform: scale(0.97);
    opacity: 0.9;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    border-color: color-mix(in srgb, var(--album-meta-color) 40%, var(--album-frame-border));
  }
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

// Disable shimmer animation on touch devices (prefers reduced motion / no hover)
@media (hover: none) {
  .cover-skeleton .shimmer-wave {
    animation: none;
    background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.08) 50%, transparent 100%);
    transform: translateX(0);
  }
}

html[data-theme="dark"] .cover-skeleton .shimmer-wave {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.08) 50%, transparent 100%);
}

html[data-theme="dark"] .cover-skeleton {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--album-meta-color) 16%, transparent),
    color-mix(in srgb, var(--album-meta-color) 10%, transparent),
    color-mix(in srgb, var(--album-meta-color) 16%, transparent)
  );
}

.flex-center {
  display: grid;
  place-items: center;
}

.album-card-mobile:focus {
  outline: none;
}

.album-card-mobile:focus-visible {
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
</style>
