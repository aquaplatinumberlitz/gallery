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
    class="album-card" 
    @click="emit('click')"
    @keydown.enter="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <div class="album-cover-diagonal">
      <div class="album-layer album-layer-back">
        <img v-if="node.cover_images?.[1]" :src="getThumbnailUrl(node.cover_images[1])" loading="lazy" alt="" />
        <div v-else class="placeholder"></div>
      </div>
      <div class="album-layer album-layer-front">
        <img v-if="node.cover_images?.[0]" :src="getThumbnailUrl(node.cover_images[0])" loading="lazy" alt="" />
        <div v-else class="placeholder flex-center"><span class="fa-placeholder-svg" v-html="placeholderSvg"></span></div>
      </div>
    </div>

    <div class="album-info">
      <h3 class="album-name">{{ node.name }}</h3>
      <div class="album-meta">
        <FolderOpen :size="11" class="album-meta-icon" />
        <span>Album<span v-if="node.image_count !== undefined && node.image_count !== null"> · {{ node.image_count }} {{ node.image_count === 1 ? 'photo' : 'photos' }}</span></span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.album-card {
  width: 100%;
  cursor: pointer;
  perspective: 1000px; // Important for 3D transforms
  border-radius: 12px;
  padding-top: 20px; // Space above for hover animation
  padding-left: 20px; // Space on left for hover animation (layers fan out left)
  transition: 
    transform 280ms cubic-bezier(0.4, 0, 0.2, 1), 
    box-shadow 280ms cubic-bezier(0.4, 0, 0.2, 1);
  /* MD3 Elevation Level 1 - disabled */
  box-shadow: none;

  .album-cover-diagonal {
    position: relative;
    height: 280px; // Standard height
    transform-style: preserve-3d;
    transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); // Elastic bounce
  }

  @media (max-width: 767px) {
    .album-cover-diagonal {
      height: 200px;
    }
  }

  @media (max-width: 480px) {
    .album-cover-diagonal {
      height: 130px;
    }

    .album-name {
      font-size: 14px;
    }

    .album-meta {
      font-size: 10px;
    }
  }

  .album-layer {
    position: absolute;
    width: 70%;
    height: 75%;
    border-radius: 1px;
    overflow: hidden;
    transition: all 0.4s ease;
    border: 4px solid var(--album-border-color); // Separate border color
    background: var(--surface-color);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .placeholder {
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.1);
      display: grid;
      place-items: center;
      font-size: 2rem;
      color: var(--muted-text);
    }
  }

  .album-layer-back {
    top: 15px;
    left: 15px;
    transform: rotate(-12deg) translateZ(0); // Standard rotation from original design
    opacity: 0.9;
    z-index: 1;
    box-shadow: var(--shadow-card);
  }

  .album-layer-front {
    top: 5px;
    right: 15px;
    transform: rotate(8deg) translateZ(20px); // Standard rotation angle
    z-index: 10;
    box-shadow: var(--shadow-card-level2);
  }

  .album-info {
    margin-top: 12px;
    padding: 0 12px 12px;
    position: relative;
    z-index: 20;

    .album-name {
      font-family: var(--font-body); // Inter font
      font-weight: 600;
      font-size: 16px;
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
      font-family: var(--font-code); // JetBrains Mono
      font-size: 11px;
      color: var(--muted-text);
      margin: 4px 0 0;
      letter-spacing: 0.5px;
    }
    .album-meta-icon {
      flex-shrink: 0;
      color: var(--muted-text);
    }
  }

  // HOVER EFFECT & DARK MODE
  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-card-hover);

    .album-cover-diagonal {
      transform: translateY(-10px);
    }

    .album-layer-back {
      transform: translate(-20px, 5px) rotate(-15deg); // Fan out to the left
    }

    .album-layer-front {
      transform: translate(10px, -5px) rotate(12deg) scale(1.05);
      box-shadow: var(--shadow-card-level4);
    }
  }

  // Dark mode hover - using html attribute selector within scoped style
  html[data-theme="dark"] & {
    box-shadow: none;

    .album-layer-back {
      box-shadow: var(--shadow-dark-layer-back);
    }

    .album-layer-front {
      box-shadow: var(--shadow-dark-layer-front);
    }

    .album-name {
      color: var(--neon-color);
    }

    &:hover {
      box-shadow: var(--glow-card-hover);

      .album-layer-front {
        box-shadow: var(--glow-card-hover-front);
      }

      .album-layer-back {
        box-shadow: var(--glow-card-hover-back);
      }
    }

    &:active {
      box-shadow: var(--glow-card-active);
    }
  }

  &:active {
    transform: translateY(0);
    box-shadow: var(--shadow-card-level2);
  }
}

.flex-center {
  display: grid;
  place-items: center;
}

// Focus styles for keyboard navigation
.album-card:focus {
  outline: none;
}

.album-card:focus-visible {
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
