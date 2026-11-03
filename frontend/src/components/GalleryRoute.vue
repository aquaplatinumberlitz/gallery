<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import GalleryGrid from "@/components/GalleryGrid.vue";
import { useDevice } from "@/composables/useDevice";
import { startSearchChunkWarmup } from "@/utils/searchChunks";

const { isMobile } = useDevice();

// The results panel and fuse.js are separate chunks; fetch them once the page is idle (or earlier on search intent).
let stopSearchWarmup: (() => void) | null = null;
onMounted(() => {
  stopSearchWarmup = startSearchChunkWarmup();
});
onBeforeUnmount(() => stopSearchWarmup?.());
</script>

<template>
  <GalleryGrid :is-mobile="isMobile" :bars-visible="isMobile" :show-desktop-toolbar="isMobile" />
</template>
