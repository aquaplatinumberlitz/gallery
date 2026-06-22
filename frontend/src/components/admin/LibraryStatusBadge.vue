<script setup lang="ts">
import { computed } from "vue";
import Badge from "@/components/ui/Badge.vue";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = defineProps<{
  status?: UnifiedStatus | null;
}>();

const presentation = computed(() => getCatalogStatusPresentation(props.status?.summary_state ?? null));
</script>

<template>
  <Badge :variant="presentation.variant" :title="presentation.meaning">{{ presentation.label }}</Badge>
</template>
