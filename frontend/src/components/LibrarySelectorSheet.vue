<script setup lang="ts">
import ResponsiveLibrarySelector from "./ResponsiveLibrarySelector.vue";

const open = defineModel<boolean>({ required: true });
</script>

<template>
  <ResponsiveLibrarySelector v-model="open" />
</template>
