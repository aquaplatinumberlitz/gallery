<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";

defineProps<{
  class?: HTMLAttributes["class"];
}>();
</script>

<template>
  <span
    role="link"
    aria-disabled="true"
    aria-current="page"
    :class="cn('text-sm font-normal text-foreground max-w-[200px] truncate px-2 py-1', $props.class)"
  >
    <slot />
  </span>
</template>
