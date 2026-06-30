<script setup lang="ts">
import { computed } from "vue";
import { formatAssetCount } from "@/utils/libraryStatus";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = defineProps<{ status?: UnifiedStatus | null }>();

const totalAssets = computed(() => props.status?.metadata.total_assets ?? null);
const readyAssets = computed(() => props.status?.metadata.ready_assets ?? null);
const failedAssets = computed(() => props.status?.metadata.failed_assets ?? 0);
const issueCount = computed(() => props.status?.issue_count ?? 0);
const metadataReadyLabel = computed(() => {
  const total = totalAssets.value ?? 0;
  const ready = readyAssets.value ?? 0;
  if (total === 0) return failedAssets.value > 0 ? `${formatAssetCount(failedAssets.value)} failed` : "No photos";
  const base =
    ready >= total ? "All metadata ready" : `${formatAssetCount(ready)} / ${formatAssetCount(total)} metadata ready`;
  return failedAssets.value > 0 ? `${base} · ${formatAssetCount(failedAssets.value)} failed` : base;
});
</script>

<template>
  <div class="min-w-40 space-y-2">
    <template v-if="status">
      <div class="text-sm font-medium">{{ formatAssetCount(totalAssets ?? 0) }} photos</div>
      <div class="text-xs text-muted-foreground">
        {{ metadataReadyLabel }}
      </div>
      <div v-if="issueCount > 0" class="text-xs text-destructive">{{ issueCount }} issue(s)</div>
    </template>
    <span v-else class="text-xs text-muted-foreground">Status unavailable</span>
    <LibraryProgressBar :status="status" compact />
  </div>
</template>
