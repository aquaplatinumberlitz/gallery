<script setup lang="ts">
import { computed } from "vue";
import Badge from "@/components/ui/Badge.vue";
import PillIndicator from "@/components/ui/PillIndicator.vue";
import type { CatalogStatusPresentation } from "@/lib/catalog/labels";
import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    presentation: CatalogStatusPresentation;
    size?: "default" | "compact";
    class?: string;
  }>(),
  {
    size: "default",
    class: undefined,
  },
);

const badgeVariant = computed(() => {
  if (props.presentation.variant === "destructive") return "destructive";
  if (props.presentation.variant === "default") return "outline";
  return "secondary";
});

const sizeClass = computed(() =>
  props.size === "compact"
    ? "gap-1 px-1.5 py-0 text-[10px] leading-none"
    : "gap-1.5 px-2 py-1 text-[11px] leading-none",
);

const toneClass = computed(() => {
  if (props.presentation.tone === "green") {
    return "border-[rgba(34,197,94,0.18)] bg-[rgba(34,197,94,0.10)] text-[#15803d] hover:bg-[rgba(34,197,94,0.10)] dark:text-[#86efac]";
  }
  if (props.presentation.tone === "yellow") {
    return "border-[rgba(245,158,11,0.20)] bg-[rgba(245,158,11,0.12)] text-[#a16207] hover:bg-[rgba(245,158,11,0.12)] dark:text-[#fde68a]";
  }
  if (props.presentation.tone === "red") {
    return "border-[rgba(239,68,68,0.20)] bg-[rgba(239,68,68,0.10)] text-[#b91c1c] hover:bg-[rgba(239,68,68,0.10)] dark:text-[#fca5a5]";
  }
  return "border-[rgba(107,114,128,0.18)] bg-[rgba(107,114,128,0.10)] text-[#4b5563] hover:bg-[rgba(107,114,128,0.10)] dark:text-[#d1d5db]";
});
</script>

<template>
  <Badge
    :variant="badgeVariant"
    :class="
      cn(
        'index-status-badge min-w-0 whitespace-nowrap',
        `index-status-badge--${presentation.tone}`,
        sizeClass,
        toneClass,
        props.class,
      )
    "
    data-testid="index-status-badge"
  >
    <PillIndicator :variant="presentation.indicator" :pulse="presentation.showPulse" aria-hidden="true" />
    <span class="truncate">{{ presentation.label }}</span>
  </Badge>
</template>
