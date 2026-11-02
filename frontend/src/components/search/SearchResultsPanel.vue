<script setup lang="ts">
/**
 * Purpose: Lazy boundary for the search results panel. The panel (and what only it uses) is a separate chunk
 * that the home route does not download before it mounts; `utils/searchChunks.ts` warms it after load + idle, on the
 * first text-field focus and for URLs that carry a search.
 * Guarantees: Props, attributes and listeners are forwarded unchanged to `SearchResultsPanelImpl.vue`, which owns the
 * props/emits contract. The wrapper renders nothing until the chunk has arrived.
 * Run when: Changing how the results panel loads. Change the panel itself in SearchResultsPanelImpl.vue.
 */
import { defineAsyncComponent, type Component } from "vue";
import { loadSearchResultsPanel } from "@/utils/searchChunks";

defineOptions({ inheritAttrs: false });

const SearchResultsPanelImpl: Component = defineAsyncComponent(loadSearchResultsPanel);
</script>

<template>
  <component :is="SearchResultsPanelImpl" v-bind="$attrs" />
</template>
