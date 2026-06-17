<script setup lang="ts">
import { computed } from "vue";
import Button from "@/components/ui/Button.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexProgressBar from "@/components/IndexProgressBar.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getFieldTooltip } from "@/utils/indexStatusCopy";
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

const photosFoundTooltip = computed(() => getFieldTooltip("indexed_photos"));
const photoDetailsReadyTooltip = computed(() => getFieldTooltip("metadata_records"));
const detailsProcessedTooltip = computed(() => getFieldTooltip("done"));
const folderTooltip = computed(() => getFieldTooltip("path"));

function formatCount(value: number) {
  return value.toLocaleString();
}

function formatUpdatedAt(value: number | null | undefined) {
  if (!value) return null;
  return new Date(value * 1000).toLocaleString();
}
</script>

<template>
  <div
    class="index-details"
    aria-label="Index Status"
  >
    <div class="index-details__header">
      <div>
        <p class="index-details__eyebrow">
          Index
        </p>
      </div>
      <IndexStatusBadge :presentation="presentation" />
    </div>
    <p
      v-if="globalWorkOutsideScope"
      class="index-details__muted"
      style="margin: 0; font-size: 12px"
    >
      Indexer working in another folder
    </p>

    <div
      v-if="isLoading"
      class="index-details__muted"
    >
      Loading index status...
    </div>

    <div
      v-else-if="isError"
      class="index-details__error"
    >
      {{ errorMessage || "Failed to load status" }}
    </div>

    <template v-else>
      <div class="index-details__section">
        <p class="index-details__section-label">
          Library
        </p>

        <Tooltip
          v-if="photosFoundTooltip"
          :delay-duration="800"
        >
          <TooltipTrigger as-child>
            <div class="index-details__row has-tooltip">
              <span class="index-details__row-key">Photos found</span>
              <strong>{{ formatCount(data?.indexed_photos ?? 0) }}</strong>
            </div>
          </TooltipTrigger>
          <TooltipContent
            side="left"
            align="start"
            class="max-w-[220px] text-xs whitespace-pre-line"
          >
            {{ photosFoundTooltip }}
          </TooltipContent>
        </Tooltip>
        <div
          v-else
          class="index-details__row"
        >
          <span class="index-details__row-key">Photos found</span>
          <strong>{{ formatCount(data?.indexed_photos ?? 0) }}</strong>
        </div>

        <Tooltip
          v-if="photoDetailsReadyTooltip"
          :delay-duration="800"
        >
          <TooltipTrigger as-child>
            <div class="index-details__row has-tooltip">
              <span class="index-details__row-key">Photo details ready</span>
              <strong>{{ formatCount(data?.metadata_records ?? 0) }}</strong>
            </div>
          </TooltipTrigger>
          <TooltipContent
            side="left"
            align="start"
            class="max-w-[220px] text-xs whitespace-pre-line"
          >
            {{ photoDetailsReadyTooltip }}
          </TooltipContent>
        </Tooltip>
        <div
          v-else
          class="index-details__row"
        >
          <span class="index-details__row-key">Photo details ready</span>
          <strong>{{ formatCount(data?.metadata_records ?? 0) }}</strong>
        </div>
      </div>

      <div
        v-if="presentation.status === 'indexing'"
        class="index-details__section"
      >
        <p class="index-details__section-label">
          Processing
        </p>

        <Tooltip
          v-if="detailsProcessedTooltip"
          :delay-duration="800"
        >
          <TooltipTrigger as-child>
            <p
              class="index-details__muted has-tooltip"
              style="margin: 0; font-size: 12px; color: var(--muted-foreground)"
            >
              {{ formatCount(progress.indexed)
              }}<template v-if="progress.total !== null">
                / {{ formatCount(progress.total) }}
              </template> details
              processed
            </p>
          </TooltipTrigger>
          <TooltipContent
            side="left"
            align="start"
            class="max-w-[220px] text-xs whitespace-pre-line"
          >
            {{ detailsProcessedTooltip }}
          </TooltipContent>
        </Tooltip>
        <p
          v-else
          class="index-details__muted"
          style="margin: 0; font-size: 12px"
        >
          {{ formatCount(progress.indexed)
          }}<template v-if="progress.total !== null">
            / {{ formatCount(progress.total) }}
          </template> details processed
        </p>

        <IndexProgressBar
          v-if="progress.percent !== null"
          :percent="progress.percent"
        />
      </div>

      <div class="index-details__section">
        <p class="index-details__section-label">
          Location
        </p>

        <Tooltip
          v-if="folderTooltip"
          :delay-duration="800"
        >
          <TooltipTrigger as-child>
            <div class="index-details__row index-details__row--path has-tooltip">
              <span class="index-details__row-key">Folder</span>
              <strong :title="data?.path || path">{{ data?.path || path }}</strong>
            </div>
          </TooltipTrigger>
          <TooltipContent
            side="left"
            align="start"
            class="max-w-[220px] text-xs whitespace-pre-line"
          >
            {{ folderTooltip }}
          </TooltipContent>
        </Tooltip>
        <div
          v-else
          class="index-details__row index-details__row--path"
        >
          <span class="index-details__row-key">Folder</span>
          <strong :title="data?.path || path">{{ data?.path || path }}</strong>
        </div>

        <div class="index-details__row">
          <span class="index-details__row-key">Including subfolders</span>
          <strong>Yes</strong>
        </div>
      </div>

      <div
        v-if="counts.failed > 0"
        class="index-details__section"
      >
        <p class="index-details__section-label">
          Issues
        </p>
        <div class="index-details__row">
          <span class="index-details__row-key index-details__row-key--error">Failed jobs</span>
          <strong>{{ formatCount(counts.failed) }}</strong>
        </div>
      </div>

      <div
        v-if="formatUpdatedAt(data?.updated_at)"
        class="index-details__row"
      >
        <span class="index-details__row-key">Last scan</span>
        <strong>{{ formatUpdatedAt(data?.updated_at) }}</strong>
      </div>

      <div
        v-if="data?.last_error"
        class="index-details__last-error"
      >
        <strong>Last error</strong>
        <span>{{ data.last_error.message }}</span>
      </div>
    </template>

    <div
      v-if="actionError"
      class="index-details__error"
    >
      {{ actionError }}
    </div>

    <p class="index-details__warning">
      Warning: Rebuild clears this folder's index and extracted metadata cache before indexing again. Source image files
      are not deleted.
    </p>

    <div class="index-details__actions">
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="inline-flex">
            <Button
              variant="outline"
              size="sm"
              :disabled="!path || !!actionPending"
              @click="emit('rescan')"
            >
              {{ actionPending === "rescan" ? "Rescanning..." : "Rescan" }}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent> Refresh this folder and queue new metadata work. </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="inline-flex">
            <Button
              variant="secondary"
              size="sm"
              :disabled="!path || !!actionPending"
              @click="emit('rebuild')"
            >
              {{ actionPending === "rebuild" ? "Rebuilding..." : "Rebuild" }}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent> Clear this scope's index cache, then scan it again. </TooltipContent>
      </Tooltip>
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
  color: var(--foreground);
  font-size: 13px;
  font-weight: 650;
}

.index-details__rows {
  display: grid;
  gap: 8px;
}

.index-details__row {
  min-width: 0;
  color: var(--muted-foreground);
  font-size: 12px;
}

.index-details__row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--foreground);
  font-weight: 600;
  text-align: right;
}

.index-details__row-key {
  color: var(--muted-foreground);
}

.index-details__row-key--error {
  color: var(--gallery-error);
}

.index-details__section {
  display: grid;
  gap: 7px;
}

.index-details__section-label {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-top: 2px;
}

.has-tooltip {
  cursor: default;
}

.index-details__muted {
  color: var(--muted-foreground);
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
  color: var(--muted-foreground);
  font-size: 12px;
}

.index-details__progress-label strong {
  color: var(--foreground);
  font-weight: 600;
}

.index-details__last-error {
  display: grid;
  gap: 4px;
  overflow-wrap: anywhere;
  overflow: hidden;
  border-radius: var(--gallery-radius-md);
  background: var(--gallery-error-bg);
  color: var(--muted-foreground);
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
