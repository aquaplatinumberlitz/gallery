<script setup lang="ts">
import { computed } from "vue";
import { Database } from "lucide-vue-next";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusDetailsPopover from "@/components/IndexStatusDetailsPopover.vue";
import IndexProgressBar from "@/components/IndexProgressBar.vue";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { CatalogStatusPresentation } from "@/lib/catalog/labels";
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

const photosFound = computed(() => props.status?.metadata.total_assets ?? 0);
const photoDetailsReady = computed(() => props.status?.metadata.ready_assets ?? 0);
const metadataProgress = computed(() => props.status?.metadata.progress_percent ?? null);
const isIndexing = computed(
  () => props.status?.metadata.state === "queued" || props.status?.metadata.state === "indexing",
);
const isScanning = computed(() => props.status?.scan.state === "queued" || props.status?.scan.state === "scanning");
const notReadyAssets = computed(() => props.status?.metadata.not_ready_assets ?? 0);
const summaryState = computed(() => props.status?.summary_state ?? null);

const bodyText = computed(() => {
  if (!props.status) return "Loading...";
  if (isScanning.value) {
    const completed = props.status.scan.completed_units ?? 0;
    const total = props.status.scan.total_units;
    if (total !== null) return `${completed.toLocaleString()} / ${total.toLocaleString()} catalog items updated`;
    return completed > 0 ? `${completed.toLocaleString()} catalog items updated` : "Updating catalog...";
  }
  if (isIndexing.value) {
    if (metadataProgress.value !== null) {
      return `${photoDetailsReady.value.toLocaleString()} / ${photosFound.value.toLocaleString()} metadata ready`;
    }
    return "Updating metadata...";
  }
  if (props.globalWorkOutsideScope) return "Metadata extraction running in another folder";
  if (summaryState.value === "needs_update" && notReadyAssets.value > 0) {
    return `${notReadyAssets.value.toLocaleString()} photos need metadata updates`;
  }
  if (summaryState.value === "error") return "Catalog needs attention";
  if (summaryState.value === "offline") return "Offline";
  if (summaryState.value === "needs_scan") return "Needs update";
  return photoDetailsReady.value >= photosFound.value && photosFound.value > 0
    ? "All metadata ready"
    : `${photoDetailsReady.value.toLocaleString()} / ${photosFound.value.toLocaleString()} metadata ready`;
});
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        class="index-status-card group-data-[collapsible=icon]:hidden"
        aria-label="Catalog Status"
        data-testid="index-status-card"
      >
        <span class="index-status-card__top">
          <span class="index-status-card__title" data-testid="catalog-database-icon">
            <Database class="size-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
            <span>Catalog</span>
          </span>
          <IndexStatusBadge :presentation="presentation" />
        </span>

        <span class="index-status-card__body">
          {{ bodyText }}
        </span>

        <IndexProgressBar v-if="isIndexing && metadataProgress !== null" :percent="Math.round(metadataProgress)" />

        <span class="index-status-card__details">Details</span>
      </button>
    </PopoverTrigger>

    <PopoverContent class="w-80 p-4" align="end" :side-offset="8" aria-label="Catalog Status">
      <IndexStatusDetailsPopover
        :status="status"
        :presentation="presentation"
        :path="path"
        :is-library-scope="isLibraryScope"
        :scope-label="scopeLabel"
        :is-loading="isLoading"
        :is-error="isError"
        :error-message="errorMessage"
        :global-work-outside-scope="globalWorkOutsideScope"
        :action-pending="actionPending"
        :action-error="actionError"
        :contract-error="contractError"
        @scan="emit('scan')"
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
