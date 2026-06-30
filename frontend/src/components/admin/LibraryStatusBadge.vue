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
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Badge :variant="presentation.variant">{{ presentation.label }}</Badge>
    </TooltipTrigger>
    <TooltipContent side="top" align="center" class="max-w-[220px]">
      {{ presentation.meaning }}
    </TooltipContent>
  </Tooltip>
</template>
