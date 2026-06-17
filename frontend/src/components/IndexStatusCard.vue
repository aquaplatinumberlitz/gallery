<script setup lang="ts">
import { Database } from "lucide-vue-next";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusDetailsPopover from "@/components/IndexStatusDetailsPopover.vue";
import IndexProgressBar from "@/components/IndexProgressBar.vue";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { IndexStatusCounts, IndexStatusPresentation, IndexStatusProgressInfo } from "@/utils/indexStatus";
import type { IndexStatusResponse } from "@/types";

defineProps<{
  data: IndexStatusResponse | null | undefined;
  counts: IndexStatusCounts;
  presentation: IndexStatusPresentation;
  progress: IndexStatusProgressInfo;
  path?: string;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  globalWorkOutsideScope?: boolean;
  actionPending?: "rescan" | "rebuild" | null;
  actionError?: string;
}>();

const emit = defineEmits<{
  (e: "rescan"): void;
  (e: "rebuild"): void;
}>();

function formatCount(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <button type="button" class="index-status-card group-data-[collapsible=icon]:hidden" aria-label="Index Status">
        <span class="index-status-card__top">
          <span class="index-status-card__title">
            <Database class="size-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
            <span>Index</span>
          </span>
          <IndexStatusBadge :presentation="presentation" />
        </span>

        <span class="index-status-card__body">
          <span v-if="presentation.status === 'indexing' && progress.total !== null">
            {{ formatCount(progress.indexed) }} / {{ formatCount(progress.total) }} details processed
          </span>
          <span v-else-if="presentation.status === 'indexing'"> Indexing... </span>
          <span v-else-if="globalWorkOutsideScope"> Indexer working in another folder </span>
          <span v-else-if="presentation.status === 'stale' && counts.stale > 0">
            {{ formatCount(counts.stale) }} known photos need updating
          </span>
          <span v-else-if="presentation.status === 'stale' && counts.missingMetadataRecords > 0">
            {{ formatCount(counts.missingMetadataRecords) }} photo details need updating
          </span>
          <span v-else> {{ formatCount(data?.metadata_records ?? 0) }} photo details ready </span>
        </span>

        <IndexProgressBar
          v-if="presentation.status === 'indexing' && progress.percent !== null"
          :percent="progress.percent"
        />

        <span class="index-status-card__details">Details</span>
      </button>
    </PopoverTrigger>

    <PopoverContent class="w-80 p-4" align="end" :side-offset="8" aria-label="Index Status">
      <IndexStatusDetailsPopover
        :data="data"
        :counts="counts"
        :presentation="presentation"
        :progress="progress"
        :path="path"
        :is-loading="isLoading"
        :is-error="isError"
        :error-message="errorMessage"
        :global-work-outside-scope="globalWorkOutsideScope"
        :action-pending="actionPending"
        :action-error="actionError"
        @rescan="emit('rescan')"
        @rebuild="emit('rebuild')"
      />
    </PopoverContent>
  </Popover>
</template>

<style scoped>
.index-status-card {
  display: grid;
  width: 100%;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--gallery-radius-md);
  background: var(--card);
  color: var(--foreground);
  padding: 10px 11px;
  text-align: left;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease;
}

.index-status-card:hover {
  border-color: var(--ring);
  background: var(--accent);
}

.index-status-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.index-status-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.index-status-card__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--foreground);
  font-size: 13px;
  font-weight: 650;
}

.index-status-card__body {
  color: var(--muted-foreground);
  font-size: 12px;
  line-height: 1.25;
}

.index-status-card__details {
  color: var(--primary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
}
</style>
