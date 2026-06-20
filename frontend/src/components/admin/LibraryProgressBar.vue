<script setup lang="ts">
import { computed } from "vue";
import type { LibraryProgress } from "@/types";
import { formatAssetCount, getLibraryProgressPercent, isLibraryBusy } from "@/utils/libraryStatus";

const props = defineProps<{ progress?: LibraryProgress | null; compact?: boolean }>();
const percent = computed(() => getLibraryProgressPercent(props.progress));
const indeterminate = computed(() =>
  Boolean(props.progress && props.progress.estimated_assets <= 0 && isLibraryBusy(props.progress.library_state)),
);
</script>

<template>
  <div v-if="progress" class="space-y-1.5">
    <div class="flex justify-between gap-3 text-xs text-muted-foreground">
      <span>
        {{ formatAssetCount(progress.indexed_assets) }} indexed<span v-if="progress.estimated_assets > 0">
          / {{ formatAssetCount(progress.estimated_assets) }}</span
        >
      </span>
      <span v-if="!compact && progress.estimated_assets > 0">{{ percent }}%</span>
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
