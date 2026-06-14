<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";

defineProps<{
  class?: HTMLAttributes["class"];
}>();
</script>

<template>
  <ol
    :class="cn('flex flex-wrap items-center gap-1.5 sm:gap-2.5', $props.class)"
  >
    <slot />
  </ol>
</template>
