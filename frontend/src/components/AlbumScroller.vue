<script setup lang="ts">
import { useStorage } from "@vueuse/core";
import type { FileNode } from "../types";
import { FolderOpen } from "lucide-vue-next";
import GallerySectionHeader from "./GallerySectionHeader.vue";
import AlbumCarouselDesktop from "./AlbumCarouselDesktop.vue";
import AlbumScrollerNative from "./AlbumScrollerNative.vue";
import { useDevice } from "../composables/useDevice";
import { motion } from "motion-v";

defineProps<{
  folders: FileNode[];
}>();

const emit = defineEmits<{
  (e: "open-folder", path: string): void;
}>();

// ── Collapse state — persist to localStorage via VueUse ──
// v2 resets the first-run default to expanded so albums are visibly present.
const COLLAPSE_KEY = "gallery-albums-collapsed-v2";
const collapsed = useStorage(COLLAPSE_KEY, false);

function toggleCollapsed() {
  collapsed.value = !collapsed.value;
}

// ── Device branching ──
const { isMobile, isTablet } = useDevice();
</script>

<template>
  <section v-if="folders.length" class="album-scroller">
    <button
      class="album-toggle"
      @click="toggleCollapsed"
      :aria-expanded="!collapsed"
      :aria-label="collapsed ? 'Expand albums' : 'Collapse albums'"
    >
      <GallerySectionHeader
        title="Albums"
        :count="folders.length"
        :badge-icon="FolderOpen"
        :clickable="true"
        :collapsed="collapsed"
      />
    </button>
    <motion.div
      :initial="false"
      :animate="{
        height: collapsed ? 0 : 'auto',
        opacity: collapsed ? 0 : 1,
        y: collapsed ? -6 : 0,
      }"
      :transition="{
        type: 'spring',
        stiffness: 380,
        damping: 34,
        opacity: { type: 'tween', duration: 0.18, ease: [0.4, 0, 0.6, 1] },
      }"
      :style="{ overflow: 'hidden' }"
      :aria-hidden="collapsed"
      :inert="collapsed"
    >
      <AlbumCarouselDesktop
        v-if="!isMobile && !isTablet"
        :folders="folders"
        @open-folder="(path: string) => emit('open-folder', path)"
      />
      <AlbumScrollerNative v-else :folders="folders" @open-folder="(path: string) => emit('open-folder', path)" />
    </motion.div>
  </section>
</template>

<style scoped lang="scss">
.album-scroller {
  position: relative;
  margin-bottom: 8px;
  pointer-events: auto; /* restore interactivity — GlowContainer sets pointer-events:none */
}

/* ── Collapsible toggle button ── */
.album-toggle {
  cursor: pointer;
  border: none;
  background: transparent;
  padding: 0;
  font: inherit;
  color: inherit;
  width: 100%;
  text-align: left;
  position: relative;
  z-index: 3;
}
</style>
