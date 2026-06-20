<script setup lang="ts">
import GalleryGrid from "@/components/GalleryGrid.vue";
import { useDevice } from "@/composables/useDevice";

const { isMobile } = useDevice();
</script>

<template>
  <GalleryGrid :is-mobile="isMobile" :bars-visible="isMobile" />
</template>
