<script setup lang="ts">
import { computed, type Component, type HTMLAttributes } from "vue";
import { Check, Copy } from "lucide-vue-next";
import { cn } from "@/lib/utils";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    copied?: boolean;
    class?: HTMLAttributes["class"];
    iconClass?: HTMLAttributes["class"];
    defaultIcon?: Component | null;
    strokeWidth?: number | string;
    checkTestId?: string;
  }>(),
  {
    copied: false,
    class: undefined,
    iconClass: undefined,
    defaultIcon: null,
    strokeWidth: 1.5,
    checkTestId: undefined,
  },
);

const DefaultIcon = computed(() => props.defaultIcon || Copy);
</script>

<template>
  <span
    v-bind="$attrs"
    :class="cn('copy-state-icon relative inline-grid size-4 place-items-center', props.class)"
    :data-copied="copied ? 'true' : 'false'"
  >
    <Check
      aria-hidden="true"
      :data-testid="checkTestId"
      :stroke-width="strokeWidth"
      :class="
        cn(
          'copy-state-icon__icon copy-state-icon__check col-start-1 row-start-1 size-full text-[var(--gallery-success)] transition-all duration-200',
          copied ? 'scale-100 opacity-100' : 'scale-75 opacity-0',
          props.iconClass,
        )
      "
    />
    <component
      :is="DefaultIcon"
      aria-hidden="true"
      :stroke-width="strokeWidth"
      :class="
        cn(
          'copy-state-icon__icon copy-state-icon__default col-start-1 row-start-1 size-full transition-all duration-200',
          copied ? 'scale-75 opacity-0' : 'scale-100 opacity-100',
          props.iconClass,
        )
      "
    />
  </span>
</template>

<style scoped>
@media (prefers-reduced-motion: reduce) {
  .copy-state-icon__icon {
    transition: none;
  }
}
</style>
