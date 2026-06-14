<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";

interface BreadcrumbProps {
  class?: HTMLAttributes["class"];
}

defineProps<BreadcrumbProps>();
</script>

<template>
  <nav :class="cn('', $props.class)" aria-label="breadcrumb">
    <slot />
  </nav>
</template>
