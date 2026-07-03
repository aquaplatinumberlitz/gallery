<script setup lang="ts">
import { computed } from "vue";
import Badge from "@/components/ui/Badge.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = defineProps<{
  status?: UnifiedStatus | null;
}>();

const presentation = computed(() => getCatalogStatusPresentation(props.status?.summary_state ?? null));

const toneClass = computed(() => {
  if (presentation.value.tone !== "green") return undefined;
  return "border-[rgba(34,197,94,0.18)] bg-[rgba(34,197,94,0.10)] text-[#15803d] hover:bg-[rgba(34,197,94,0.10)] dark:text-[#86efac]";
});
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Badge :variant="presentation.variant" :class="toneClass">{{ presentation.label }}</Badge>
    </TooltipTrigger>
    <TooltipContent side="top" align="center" class="max-w-[220px]">
      {{ presentation.meaning }}
    </TooltipContent>
  </Tooltip>
</template>
