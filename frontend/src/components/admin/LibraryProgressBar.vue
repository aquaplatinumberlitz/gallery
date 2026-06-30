<script setup lang="ts">
import { computed } from "vue";
import { formatAssetCount } from "@/utils/libraryStatus";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = defineProps<{ status?: UnifiedStatus | null; compact?: boolean }>();

const isScanning = computed(() => props.status?.scan.state === "queued" || props.status?.scan.state === "scanning");
const isIndexing = computed(
  () => props.status?.metadata.state === "queued" || props.status?.metadata.state === "indexing",
);
const isActive = computed(() => isScanning.value || isIndexing.value);

const percent = computed(() => {
  const status = props.status;
  if (!status) return 0;
  if (isScanning.value) {
    if (status.scan.progress_percent !== null) return Math.round(status.scan.progress_percent);
    return 0;
  }
  if (status.metadata.progress_percent !== null) return Math.round(status.metadata.progress_percent);
  if (status.scan.state === "complete") return 100;
  return 0;
});

const indeterminate = computed(() => Boolean(isActive.value && percent.value === 0));

const indexedLabel = computed(() => {
  const status = props.status;
  if (!status) return "";
  const ready = status.metadata.ready_assets ?? 0;
  const total = status.metadata.total_assets ?? 0;
  if (isScanning.value && total === 0) {
    return `${formatAssetCount(status.scan.completed_units ?? 0)} updated`;
  }
  if (total > 0) {
    return `Metadata ${formatAssetCount(ready)} / ${formatAssetCount(total)}`;
  }
  return `Metadata ${formatAssetCount(ready)}`;
});
</script>

<template>
  <div v-if="status" class="space-y-1.5">
    <div class="flex justify-between gap-3 text-xs text-muted-foreground">
      <span>{{ indexedLabel }}</span>
      <span v-if="!compact && !indeterminate">{{ percent }}%</span>
    </div>
    <div
      class="h-2 overflow-hidden rounded-full bg-muted"
      role="progressbar"
      :aria-valuenow="indeterminate ? undefined : percent"
    >
      <div
        class="h-full rounded-full bg-primary transition-[width]"
        :class="{ 'animate-pulse': indeterminate }"
        :style="{ width: indeterminate ? '40%' : `${percent}%` }"
      />
    </div>
  </div>
</template>
