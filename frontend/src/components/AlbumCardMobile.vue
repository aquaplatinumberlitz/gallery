<script setup lang="ts">
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
</script>

<template>
  <div 
    class="album-card-mobile"
    @click="emit('click')"
    @keydown.enter="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <div class="album-cover">
      <img v-if="node.cover_images?.[0]" :src="getThumbnailUrl(node.cover_images[0])" loading="lazy" alt="" />
      <div v-else class="placeholder flex-center"><span class="fa-placeholder-svg" v-html="placeholderSvg"></span></div>
    </div>

    <div class="album-info">
      <h3 class="album-name">{{ node.name }}</h3>
      <div class="album-meta">
        <FolderOpen :size="11" class="album-meta-icon" />
        <span v-if="node.image_count !== undefined && node.image_count !== null">{{ node.image_count }} {{ node.image_count === 1 ? 'photo' : 'photos' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.album-card-mobile {
  width: 100%;
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;            // Outer card clips content — clean straight edge at bottom
  background: var(--gallery-surface-elevated, #ffffff);
  border: 1px solid var(--gallery-border-default, #e5ddd4);
  box-shadow: none;
  transition: transform 160ms ease, opacity 160ms ease;

  .album-cover {
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 8px 8px 0 0;  // Only top corners rounded — bottom is straight horizontal edge
    overflow: hidden;
    border: none;                  // Removed border for cleaner look (Apple Photos style)
    background: var(--surface-color);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);  // Subtle depth (Google Photos style)

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .placeholder {
      width: 100%;
      height: 100%;
      background: var(--placeholder-bg);
      display: grid;
      place-items: center;
      color: var(--muted-text);
    }
  }

  .album-info {
    padding: 0 8px 8px;
    margin-top: 6px;

    .album-name {
      font-family: var(--font-body);
      font-weight: 600;
      font-size: 13px;
      line-height: 1.25;
      color: var(--title-color);
      margin: 0;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      line-clamp: 2;
      overflow: hidden;
      text-overflow: ellipsis;
      word-break: break-word;      // Prevent long words breaking layout
      overflow-wrap: break-word;   // Fallback for word-break
    }

    .album-meta {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-family: var(--font-code);
      font-size: 11px;             // Increased from 10px → 11px (better readability)
      color: var(--muted-text);
      margin: 4px 0 0;
      letter-spacing: 0.5px;
    }
    .album-meta-icon {
      flex-shrink: 0;
      color: var(--muted-text);
    }
  }

  // Hover only for devices with hover capability (desktop/trackpad)
  @media (hover: hover) {
    &:hover {
      .album-cover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        transform: translateY(-2px);
        transition: transform 200ms ease, box-shadow 200ms ease;
      }
    }
  }

  html[data-theme="dark"] & {
    box-shadow: none;

    .album-cover {
      box-shadow: 0 0 8px rgba(255, 255, 255, 0.04);  // Subtle glow in dark mode
      border: none;
    }

    .album-name {
      color: var(--gallery-accent-default, var(--neon-color));
    }

    @media (hover: hover) {
      &:hover .album-cover {
        box-shadow: 0 0 12px rgba(255, 255, 255, 0.08);
      }
    }
  }

  &:active {
    transform: scale(0.97);
    opacity: 0.85;
    box-shadow: none;
  }
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
  color: var(--muted-text);
}
</style>
