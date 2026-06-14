<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";

interface Props {
  class?: HTMLAttributes["class"];
  type?: string;
}

withDefaults(defineProps<Props>(), {
  type: "text",
});
</script>

<template>
  <input
    :type="type"
    :class="
      cn(
        'flex h-10 w-full rounded-[10px] border border-border bg-surface px-3 py-2 text-sm text-foreground file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-primary focus-visible:shadow-[var(--focus-ring-shadow)] disabled:cursor-not-allowed disabled:opacity-50 transition-colors',
        $props.class,
      )
    "
  />
</template>
