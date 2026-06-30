<script setup lang="ts">
import { computed } from "vue";
import Button from "@/components/ui/Button.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexProgressBar from "@/components/IndexProgressBar.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatLibraryTimestamp } from "@/utils/libraryStatus";
import type { CatalogStatusPresentation } from "@/lib/catalog/labels";
import { STATUS_CONTRACT_ERROR_MESSAGE } from "@/lib/catalog/contractGuard";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = defineProps<{
  status: UnifiedStatus | null;
  presentation: CatalogStatusPresentation;
  path?: string;
  isLibraryScope?: boolean;
  scopeLabel?: string;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  globalWorkOutsideScope?: boolean;
  actionPending?: "scan" | null;
  actionError?: string;
  contractError?: boolean;
}>();

const emit = defineEmits<{
  (e: "scan"): void;
}>();

const updateLabel = computed(() => (props.isLibraryScope ? "Update library" : "Update current folder"));

const photosFound = computed(() => props.status?.metadata.total_assets ?? 0);
const photoDetailsReady = computed(() => props.status?.metadata.ready_assets ?? 0);
const metadataProgress = computed(() => props.status?.metadata.progress_percent ?? null);
const isIndexing = computed(
  () => props.status?.metadata.state === "queued" || props.status?.metadata.state === "indexing",
);
const failedAssets = computed(() => props.status?.metadata.failed_assets ?? 0);
const issueCount = computed(() => props.status?.issue_count ?? 0);

function formatCount(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <div class="index-details" aria-label="Catalog Status">
    <div class="index-details__header">
      <div>
        <p class="index-details__eyebrow">Catalog</p>
      </div>
      <IndexStatusBadge :presentation="presentation" />
    </div>
    <p v-if="globalWorkOutsideScope" class="index-details__muted" style="margin: 0; font-size: 12px">
      Metadata extraction running in another folder
    </p>

    <div v-if="contractError" class="index-details__error">{{ STATUS_CONTRACT_ERROR_MESSAGE }}</div>

    <div v-else-if="isLoading" class="index-details__muted">Loading catalog status...</div>

    <div v-else-if="isError" class="index-details__error">
      {{ errorMessage || "Failed to load status" }}
    </div>

    <template v-else-if="status">
      <div class="index-details__section">
        <p class="index-details__section-label">Library</p>

        <Tooltip :delay-duration="800">
          <TooltipTrigger as-child>
            <div class="index-details__row has-tooltip">
              <span class="index-details__row-key">Photos</span>
              <strong>{{ formatCount(photosFound) }}</strong>
            </div>
          </TooltipTrigger>
          <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
            Cataloged photos in this scope.
          </TooltipContent>
        </Tooltip>

        <Tooltip :delay-duration="800">
          <TooltipTrigger as-child>
            <div class="index-details__row has-tooltip">
              <span class="index-details__row-key">Metadata ready</span>
              <strong>{{ formatCount(photoDetailsReady) }}</strong>
            </div>
          </TooltipTrigger>
          <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
            Photos with current metadata ready for search and inspection.
          </TooltipContent>
        </Tooltip>
      </div>

      <div v-if="isIndexing && metadataProgress !== null" class="index-details__section">
        <p class="index-details__section-label">Processing</p>
        <p class="index-details__muted" style="margin: 0; font-size: 12px">
          {{ Math.round(metadataProgress) }}% metadata processed
        </p>
        <IndexProgressBar :percent="Math.round(metadataProgress)" />
      </div>

      <div class="index-details__section">
        <p class="index-details__section-label">Location</p>

        <div class="index-details__row index-details__row--path">
          <span class="index-details__row-key">Scope</span>
          <OverflowTooltip as="strong" :text="path || 'Library root'" align="end">
            {{ path || "Library root" }}
          </OverflowTooltip>
        </div>

        <div class="index-details__row">
          <span class="index-details__row-key">Including subfolders</span>
          <strong>{{ isLibraryScope ? "All folders" : "Yes" }}</strong>
        </div>
      </div>

      <div v-if="failedAssets > 0 || issueCount > 0" class="index-details__section">
        <p class="index-details__section-label">Health</p>
        <div v-if="failedAssets > 0" class="index-details__row">
          <span class="index-details__row-key index-details__row-key--error">Failed metadata</span>
          <strong>{{ formatCount(failedAssets) }}</strong>
        </div>
        <div class="index-details__row">
          <span class="index-details__row-key">Total health issues</span>
          <strong>{{ formatCount(issueCount) }}</strong>
        </div>
      </div>

      <div class="index-details__section">
        <p class="index-details__section-label">Timestamps</p>
        <div class="index-details__row">
          <span class="index-details__row-key">Catalog updated</span>
          <strong>{{ formatLibraryTimestamp(status.last_scan_at) }}</strong>
        </div>
        <div class="index-details__row">
          <span class="index-details__row-key">Metadata updated</span>
          <strong>{{ formatLibraryTimestamp(status.last_index_at) }}</strong>
        </div>
      </div>

      <div v-if="status.latest_issue" class="index-details__last-error">
        <strong>Latest issue</strong>
        <span>{{ status.latest_issue.message }}</span>
      </div>
    </template>

    <div v-if="actionError" class="index-details__error">
      {{ actionError }}
    </div>

    <div class="index-details__actions">
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="inline-flex">
            <Button
              variant="outline"
              size="sm"
              :disabled="(!path && !isLibraryScope) || !!actionPending"
              @click="emit('scan')"
            >
              {{ actionPending === "scan" ? "Updating..." : updateLabel }}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent> Refresh this scope and queue new metadata work. </TooltipContent>
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
