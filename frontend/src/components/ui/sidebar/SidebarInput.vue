<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

const props = defineProps<{
  class?: HTMLAttributes["class"];
}>();
</script>

<template>
  <Input
    data-sidebar="input"
    :class="
      cn(
        'h-8 w-full bg-background shadow-none focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50',
        props.class,
      )
    "
  >
    <slot />
  </Input>
</template>
