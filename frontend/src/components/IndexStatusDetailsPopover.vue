<script setup lang="ts">
import Button from "@/components/ui/Button.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
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

function formatUpdatedAt(value: number | null | undefined) {
  if (!value) return null;
  return new Date(value * 1000).toLocaleString();
}
</script>

<template>
  <div class="index-details" aria-label="Index Status">
    <div class="index-details__header">
      <div>
        <p class="index-details__eyebrow">Index</p>
        <p class="index-details__title">Status details</p>
      </div>
      <IndexStatusBadge :presentation="presentation" />
    </div>

    <div v-if="isLoading" class="index-details__muted">
      Loading index status...
    </div>

    <div v-else-if="isError" class="index-details__error">
      {{ errorMessage || "Failed to load status" }}
    </div>

    <template v-else>
      <div class="index-details__rows">
        <div class="index-details__row">
          <span>Status</span>
          <strong>{{ presentation.label }}</strong>
        </div>

        <div class="index-details__row">
          <span>Metadata indexed</span>
          <strong>{{ formatCount(progress.indexed) }}</strong>
        </div>

        <div v-if="progress.pending > 0" class="index-details__row">
          <span>Pending</span>
          <strong>{{ formatCount(progress.pending) }}</strong>
        </div>

        <div v-if="counts.failed > 0 || counts.stagedPathFailed > 0" class="index-details__row">
          <span>Failed jobs</span>
          <strong>{{ formatCount(counts.failed + counts.stagedPathFailed) }}</strong>
        </div>

        <div v-if="formatUpdatedAt(data?.updated_at)" class="index-details__row">
          <span>Last scan</span>
          <strong>{{ formatUpdatedAt(data?.updated_at) }}</strong>
        </div>

        <div v-if="data?.path || path" class="index-details__row index-details__row--path">
          <span>Scope</span>
          <strong :title="data?.path || path">{{ data?.path || path }}</strong>
        </div>

        <div v-if="data?.path || path" class="index-details__row">
          <span>Recursive</span>
          <strong>Yes</strong>
        </div>
      </div>

      <div v-if="presentation.status === 'indexing'" class="index-details__progress">
        <div class="index-details__progress-label">
          <span>Progress</span>
          <strong v-if="progress.total !== null">
            {{ formatCount(progress.indexed) }} / {{ formatCount(progress.total) }} metadata indexed
          </strong>
          <strong v-else>Indexing...</strong>
        </div>
        <div v-if="progress.percent !== null" class="index-details__bar" aria-hidden="true">
          <div :style="{ width: `${progress.percent}%` }" />
        </div>
      </div>

      <div v-if="data?.last_error" class="index-details__last-error">
        <strong>Last error</strong>
        <span>{{ data.last_error.message }}</span>
      </div>
    </template>

    <div v-if="actionError" class="index-details__error">
      {{ actionError }}
    </div>

    <p class="index-details__warning">
      Warning: Rebuild clears this folder's index and extracted metadata cache before indexing again. Source image files are not deleted.
    </p>

    <div class="index-details__actions">
      <Button
        variant="outline"
        size="sm"
        :disabled="!path || !!actionPending"
        @click="emit('rescan')"
      >
        {{ actionPending === "rescan" ? "Rescanning..." : "Rescan" }}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="!path || !!actionPending"
        @click="emit('rebuild')"
      >
        {{ actionPending === "rebuild" ? "Rebuilding..." : "Rebuild index" }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.index-details {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.index-details__header,
.index-details__row,
.index-details__progress-label,
.index-details__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.index-details__eyebrow {
  margin: 0;
  color: var(--muted-text);
  font-size: 11px;
  font-weight: 600;
}

.index-details__title {
  margin: 2px 0 0;
  color: var(--text-color);
  font-size: 14px;
  font-weight: 650;
}

.index-details__rows {
  display: grid;
  gap: 8px;
}

.index-details__row {
  min-width: 0;
  color: var(--muted-text);
  font-size: 12px;
}

.index-details__row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-color);
  font-weight: 600;
  text-align: right;
}

.index-details__muted {
  color: var(--muted-text);
  font-size: 13px;
}

.index-details__error {
  overflow-wrap: anywhere;
  overflow: hidden;
  border-radius: var(--gallery-radius-md);
  background: var(--gallery-error-bg);
  color: var(--gallery-error);
  padding: 8px 10px;
  font-size: 12px;
}

.index-details__progress {
  display: grid;
  gap: 7px;
}

.index-details__progress-label {
  color: var(--muted-text);
  font-size: 12px;
}

.index-details__progress-label strong {
  color: var(--text-color);
  font-weight: 600;
}

.index-details__bar {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
}

.index-details__bar > div {
  height: 100%;
  border-radius: inherit;
  background: var(--gallery-warning);
  transition: width 300ms ease;
}

.index-details__last-error {
  display: grid;
  gap: 4px;
  overflow-wrap: anywhere;
  overflow: hidden;
  border-radius: var(--gallery-radius-md);
  background: var(--gallery-error-bg);
  color: var(--muted-text);
  padding: 8px 10px;
  font-size: 12px;
}

.index-details__last-error strong {
  color: var(--gallery-error);
}

.index-details__warning {
  margin: 0;
  border-radius: var(--gallery-radius-md);
  background: var(--gallery-warning-bg);
  color: #92400e;
  padding: 7px 9px;
  font-size: 11px;
  line-height: 1.35;
}

.index-details__actions {
  padding-top: 2px;
}
</style>
