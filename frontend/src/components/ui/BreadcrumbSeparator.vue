<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";
import { ChevronRight } from "lucide-vue-next";

defineProps<{
  class?: HTMLAttributes["class"];
}>();
</script>

<template>
  <li role="presentation" aria-hidden="true" :class="cn('', $props.class)">
    <slot>
      <ChevronRight class="size-3.5 text-muted-foreground opacity-60" />
    </slot>
  </li>
</template>
