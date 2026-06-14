<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { FileNode } from "../types";
import { FolderOpen } from "lucide-vue-next";
import GallerySectionHeader from "./GallerySectionHeader.vue";
import AlbumCarouselDesktop from "./AlbumCarouselDesktop.vue";
import AlbumScrollerNative from "./AlbumScrollerNative.vue";
import { useDevice } from "../composables/useDevice";

defineProps<{
  folders: FileNode[];
}>();

const emit = defineEmits<{
  (e: "open-folder", path: string): void;
}>();

// ── Collapse state — persist to localStorage ──
const COLLAPSE_KEY = "gallery-albums-collapsed";
const collapsed = ref(true);

onMounted(() => {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    if (saved !== null) collapsed.value = saved === "true";
  } catch {
    /* localStorage unavailable */
  }
});

function toggleCollapsed() {
  collapsed.value = !collapsed.value;
  try {
    localStorage.setItem(COLLAPSE_KEY, String(collapsed.value));
  } catch {
    /* localStorage unavailable */
  }
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
    <Transition name="album-collapse">
      <div v-show="!collapsed">
        <AlbumCarouselDesktop
          v-if="!isMobile && !isTablet"
          :folders="folders"
          @open-folder="(path: string) => emit('open-folder', path)"
        />
        <AlbumScrollerNative
          v-else
          :folders="folders"
          @open-folder="(path: string) => emit('open-folder', path)"
        />
      </div>
    </Transition>
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

/* ── Collapse animation ── */
.album-collapse-enter-active,
.album-collapse-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.album-collapse-enter-from,
.album-collapse-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.album-collapse-enter-to,
.album-collapse-leave-from {
  max-height: 600px;
  opacity: 1;
}
</style>
