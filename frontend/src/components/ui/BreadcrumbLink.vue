<script setup lang="ts">
import { Primitive, type PrimitiveProps } from "reka-ui";
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";

const props = withDefaults(defineProps<PrimitiveProps & { class?: HTMLAttributes["class"] }>(), { as: "a" });
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    data-reka-collection-item
    :class="cn('transition-colors hover:text-foreground', props.class)"
    v-bind="$attrs"
  >
    <slot />
  </Primitive>
</template>
