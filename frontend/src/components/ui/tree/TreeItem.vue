<script setup lang="ts" generic="T extends Record<string, any>">
import { cn } from "@/lib/utils";
import { TreeItem, type TreeItemProps } from "reka-ui";
import type { HTMLAttributes } from "vue";

const props = defineProps<TreeItemProps<T> & { hasChildren?: boolean; class?: HTMLAttributes["class"] }>();
</script>

<template>
  <TreeItem
    :class="
      cn(
        'z-10 ps-(--tree-padding) outline-hidden select-none not-last:pb-0.5 focus:z-20 data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        props.class,
      )
    "
    :style="{
      '--tree-padding': `min(calc(${props.level - 1} * var(--tree-indent)), var(--tree-indent-max))`,
    }"
    :data-folder="props.hasChildren ?? false"
    v-bind="props"
    v-slot="slotProps"
  >
    <slot v-bind="slotProps" />
  </TreeItem>
</template>
