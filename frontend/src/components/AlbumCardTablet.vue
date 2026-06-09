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
    class="album-card-tablet"
    data-testid="album-card"
    :data-album-name="node.name"
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
        <FolderOpen class="gallery-icon-meta album-meta-icon" />
        <span>Album<span v-if="node.image_count !== undefined && node.image_count !== null"> · {{ node.image_count }} {{ node.image_count === 1 ? 'photo' : 'photos' }}</span></span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.album-card-tablet {
  width: 100%;
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  background: var(--gallery-surface-elevated, #ffffff);
  border: 1px solid var(--gallery-border-default, #e5ddd4);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: transform 160ms ease, box-shadow 160ms ease;

  .album-cover {
    width: 100%;
    height: 130px;
    overflow: hidden;
    background: var(--surface-color);

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
    padding: 10px 10px 10px;
    margin-top: 0;

    .album-name {
      font-family: var(--font-body);
      font-weight: 600;
      font-size: 15px;
      color: var(--title-color);
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
      color: var(--muted-text);
      margin: 4px 0 0;
      letter-spacing: 0.5px;
    }

    .album-meta-icon {
      flex-shrink: 0;
      color: var(--muted-text);
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
      color: var(--gallery-accent-default, var(--neon-color));
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
  color: var(--muted-text);
}
</style>
