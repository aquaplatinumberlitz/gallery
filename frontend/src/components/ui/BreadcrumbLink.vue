<script setup lang="ts">
import { Primitive, type PrimitiveProps } from "reka-ui";
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";

const props = withDefaults(defineProps<PrimitiveProps & { class?: HTMLAttributes["class"] }>(), {
  as: "a",
  class: undefined,
});
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    data-reka-collection-item
    :class="cn('breadcrumb-link transition-colors hover:text-foreground', props.class)"
    v-bind="$attrs"
  >
    <slot />
  </Primitive>
</template>

<style scoped>
@media (max-width: 1023px) {
  .breadcrumb-link {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    padding-inline: 0.375rem;
    margin-inline: -0.125rem;
    border-radius: 0.375rem;
    -webkit-tap-highlight-color: transparent;
  }
}
</style>
