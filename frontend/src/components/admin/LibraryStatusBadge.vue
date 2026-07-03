<script setup lang="ts">
import { computed } from "vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
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
      <IndexStatusBadge :presentation="presentation" />
    </TooltipTrigger>
    <TooltipContent side="top" align="center" class="max-w-[220px]">
      {{ presentation.meaning }}
    </TooltipContent>
  </Tooltip>
</template>
