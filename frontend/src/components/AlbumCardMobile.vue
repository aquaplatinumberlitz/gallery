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
  <article
    class="album-card-mobile"
    data-testid="album-card"
    :data-album-name="node.name"
    @click="emit('click')"
    @keydown.enter="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <div class="cover">
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
      <div v-else class="placeholder">
        <span class="fa-placeholder-svg" v-html="placeholderSvg" />
      </div>

      <!-- Bottom gradient scrim — always rendered so the overlay title stays legible -->
      <div class="scrim" aria-hidden="true" />

      <!-- Top-right count chip with backdrop blur -->
      <div
        v-if="node.image_count !== undefined && node.image_count !== null"
        class="count-chip"
      >
        <FolderOpen class="count-chip-icon" />
        <span class="count-chip-text">{{ node.image_count }} {{ node.image_count === 1 ? "photo" : "photos" }}</span>
      </div>

      <!-- Bottom title block — editorial accent bar + magazine-style title -->
      <div class="title-block">
        <span class="title-accent" aria-hidden="true" />
        <h3 class="album-name">{{ node.name }}</h3>
      </div>
    </div>
  </article>
</template>

<style scoped lang="scss">
.album-card-mobile {
  // Local tokens — fall back to brand palette but allow override
  --acm-paper: var(--brand-album-paper);
  --acm-paper-border: var(--brand-album-paper-border);
  --acm-title: #ffffff; // Title is always white — it sits on a scrim over the image
  --acm-muted: var(--brand-album-muted);
  --acm-accent: var(--brand-album-accent, #ff6b35);
  --acm-radius: 14px;

  position: relative;
  display: block;
  width: 100%;
  min-height: 44px; // Tap target safety net
  cursor: pointer;
  border-radius: var(--acm-radius);
  overflow: hidden;
  background: var(--acm-paper);
  border: none; // Editorial style — no border, let the shadow do the framing
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.08),
    0 6px 16px rgba(0, 0, 0, 0.07);
  transition:
    transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1),
    box-shadow 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
  -webkit-tap-highlight-color: transparent;

  .cover {
    position: relative;
    width: 100%;
    aspect-ratio: 4 / 5; // Portrait — magazine cover feel
    overflow: hidden;
    background: var(--acm-paper);
    // Subtle inner frame so the image edge feels intentional, not floating
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      // Slow Ken Burns zoom on hover/tap — the editorial signature
      transform: scale(1) translateZ(0);
      transition: transform 700ms cubic-bezier(0.2, 0.8, 0.2, 1), opacity 240ms ease;
      opacity: 1;
      will-change: transform;
    }

    .placeholder {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      // Warm cream gradient (light) — replaced in dark mode below
      background:
        radial-gradient(120% 120% at 30% 20%, color-mix(in srgb, var(--acm-muted) 10%, var(--acm-paper)) 0%, var(--acm-paper) 60%),
        var(--acm-paper);
      color: color-mix(in srgb, var(--acm-muted) 55%, transparent);
    }

    // Loading skeleton — same shape as the cover, hidden once the image loads
    .cover-skeleton {
      position: absolute;
      inset: 0;
      background: linear-gradient(
        90deg,
        color-mix(in srgb, var(--acm-muted) 10%, transparent),
        color-mix(in srgb, var(--acm-muted) 6%, transparent),
        color-mix(in srgb, var(--acm-muted) 10%, transparent)
      );
      overflow: hidden;
      pointer-events: none;
      z-index: 1;
    }
  }

  // Bottom-to-top dark gradient — guarantees the overlay title is readable on any photo
  .scrim {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(
      180deg,
      rgba(0, 0, 0, 0) 0%,
      rgba(0, 0, 0, 0) 42%,
      rgba(0, 0, 0, 0.45) 72%,
      rgba(0, 0, 0, 0.82) 100%
    );
    z-index: 2;
  }

  // Top-right count chip — frosted glass, mono caption
  .count-chip {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 3;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px 4px 7px;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.42);
    -webkit-backdrop-filter: blur(10px) saturate(160%);
    backdrop-filter: blur(10px) saturate(160%);
    color: rgba(255, 255, 255, 0.95);
    font-family: var(--font-code);
    font-size: 10px;
    line-height: 1;
    letter-spacing: 0.3px;
    white-space: nowrap;
    // Hairline ring so the chip separates from bright photo areas
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);

    .count-chip-icon {
      width: 11px;
      height: 11px;
      flex-shrink: 0;
      opacity: 0.85;
    }

    .count-chip-text {
      transform: translateY(0.5px); // Optical alignment with the icon
    }
  }

  // Bottom title block — accent bar + magazine title
  .title-block {
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 10px;
    z-index: 3;
    display: flex;
    flex-direction: column;
    gap: 6px;
    pointer-events: none; // Clicks fall through to the card
  }

  .title-accent {
    width: 18px;
    height: 2px;
    border-radius: 1px;
    background: var(--acm-accent);
    // Subtle glow on the accent bar for a premium "printed" feel
    box-shadow: 0 0 8px color-mix(in srgb, var(--acm-accent) 60%, transparent);
  }

  .album-name {
    font-family: var(--font-body);
    font-weight: 700;
    font-size: 14px;
    line-height: 1.22;
    letter-spacing: -0.01em; // Tighter — editorial display feel
    color: var(--acm-title);
    margin: 0;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35); // Extra legibility on top of the scrim
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    text-overflow: ellipsis;
    word-break: break-word;
    overflow-wrap: break-word;
  }

  // Hover only on devices that actually hover (desktop/trackpad preview)
  @media (hover: hover) {
    &:hover {
      transform: translateY(-2px);
      box-shadow:
        0 2px 4px rgba(0, 0, 0, 0.1),
        0 12px 28px rgba(0, 0, 0, 0.14);

      .cover img {
        transform: scale(1.04) translateZ(0);
      }
    }
  }

  // Tap feedback — gentle press + continued Ken Burns
  &:active {
    transform: scale(0.985);
    box-shadow:
      0 1px 2px rgba(0, 0, 0, 0.1),
      0 2px 6px rgba(0, 0, 0, 0.06);

    .cover img {
      transform: scale(1.03) translateZ(0);
    }
  }

  // Dark mode — deep shadow + subtle ring instead of light shadow
  html[data-theme="dark"] & {
    background: var(--acm-paper);
    box-shadow:
      0 0 0 1px rgba(255, 255, 255, 0.04),
      0 6px 16px rgba(0, 0, 0, 0.45);

    .cover {
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.05);

      .placeholder {
        background:
          radial-gradient(120% 120% at 30% 20%, color-mix(in srgb, var(--acm-muted) 14%, var(--acm-paper)) 0%, var(--acm-paper) 60%),
          var(--acm-paper);
        color: color-mix(in srgb, var(--acm-muted) 65%, transparent);
      }
    }

    // Count chip stays legible on dark imagery either way — keep the dark frosted bg
    .count-chip {
      background: rgba(0, 0, 0, 0.5);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
    }

    @media (hover: hover) {
      &:hover {
        box-shadow:
          0 0 0 1px rgba(255, 255, 255, 0.08),
          0 12px 28px rgba(0, 0, 0, 0.55);
      }
    }

    &:active {
      box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.06),
        0 2px 6px rgba(0, 0, 0, 0.4);
    }
  }
}

// ── Shimmer animation (skeleton) ────────────────────────────────────────────
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

// Disable shimmer on touch / no-hover devices — keep the soft static gradient
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
    color-mix(in srgb, var(--brand-album-muted) 16%, transparent),
    color-mix(in srgb, var(--brand-album-muted) 10%, transparent),
    color-mix(in srgb, var(--brand-album-muted) 16%, transparent)
  );
}

// ── Focus rings (keyboard nav) ──────────────────────────────────────────────
.album-card-mobile:focus {
  outline: none;
}

.album-card-mobile:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow), 0 6px 16px rgba(0, 0, 0, 0.07);
  border-radius: 14px;
}

// ── FA placeholder SVG (v-html needs :deep for scoped styles) ────────────────
.fa-placeholder-svg :deep(svg) {
  width: 36px;
  height: 36px;
  display: block;
  color: currentColor;
  opacity: 0.7;
}
</style>
