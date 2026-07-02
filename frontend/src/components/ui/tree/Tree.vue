<script setup lang="ts" generic="T extends Record<string, any>">
import { reactiveOmit } from "@vueuse/core";
import { cn } from "@/lib/utils";
import type { TreeRootEmits, TreeRootProps } from "reka-ui";
import { TreeRoot, useForwardPropsEmits } from "reka-ui";
import type { HTMLAttributes } from "vue";

const props = withDefaults(
  defineProps<
    TreeRootProps<T> & {
      indent?: number;
      indentMax?: number;
      class?: HTMLAttributes["class"];
    }
  >(),
  { indent: 20, indentMax: 120, class: undefined },
);
const delegatedProps = reactiveOmit(props, "class");
const emits = defineEmits<TreeRootEmits>();

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <TreeRoot
    data-slot="tree"
    :style="{
      '--tree-indent': `${props.indent}px`,
      '--tree-indent-max': `${props.indentMax}px`,
    }"
    :class="cn('flex flex-col', props.class)"
    v-bind="forwarded"
    v-slot="slotProps"
  >
    <slot v-bind="slotProps" />
  </TreeRoot>
</template>
