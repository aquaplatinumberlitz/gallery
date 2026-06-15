<script setup lang="ts">
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusDetailsPopover from "@/components/IndexStatusDetailsPopover.vue";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type {
  IndexStatusCounts,
  IndexStatusPresentation,
  IndexStatusProgressInfo,
} from "@/utils/indexStatus";
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
      <button
        type="button"
        class="index-status-card group-data-[collapsible=icon]:hidden"
        aria-label="Index Status"
      >
        <span class="index-status-card__top">
          <span class="index-status-card__title">Index</span>
          <IndexStatusBadge :presentation="presentation" />
        </span>

        <span class="index-status-card__body">
          <span v-if="presentation.status === 'indexing' && progress.total !== null">
            {{ formatCount(progress.indexed) }} / {{ formatCount(progress.total) }} indexed
          </span>
          <span v-else-if="presentation.status === 'indexing'">
            Indexing...
          </span>
          <span v-else>
            {{ formatCount(progress.indexed) }} indexed
          </span>
        </span>

        <span
          v-if="presentation.status === 'indexing' && progress.percent !== null"
          class="index-status-card__bar"
          aria-hidden="true"
        >
          <span :style="{ width: `${progress.percent}%` }" />
        </span>

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
  border: 1px solid var(--gallery-border-subtle);
  border-radius: var(--gallery-radius-md);
  background: var(--gallery-surface-elevated);
  color: var(--text-color);
  padding: 10px 11px;
  text-align: left;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease;
}

.index-status-card:hover {
  border-color: var(--gallery-border-hover);
  background: var(--gallery-surface-hover);
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
  color: var(--text-color);
  font-size: 13px;
  font-weight: 650;
}

.index-status-card__body {
  color: var(--muted-text);
  font-size: 12px;
  line-height: 1.25;
}

.index-status-card__bar {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
}

.index-status-card__bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--gallery-warning);
  transition: width 300ms ease;
}

.index-status-card__details {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
}
</style>
