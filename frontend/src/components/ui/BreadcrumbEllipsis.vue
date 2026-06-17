<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";
import { Ellipsis } from "lucide-vue-next";

defineProps<{
  class?: HTMLAttributes["class"];
}>();
</script>

<template>
  <span
    role="presentation"
    aria-hidden="true"
    :class="cn('flex size-9 items-center justify-center', $props.class)"
  >
    <Ellipsis class="size-4 text-muted-foreground" />
    <span class="sr-only">More</span>
  </span>
</template>
