<script setup lang="ts">
import { computed, ref } from "vue";
import { Database, Loader, AlertCircle, ChevronDown, ChevronRight } from "lucide-vue-next";
import { useCatalogStatusQuery } from "@/composables/useCatalogStatusQuery";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import Button from "@/components/ui/Button.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusCard from "@/components/IndexStatusCard.vue";
import PillIndicator from "@/components/ui/PillIndicator.vue";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { queryClient } from "@/query";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { scanLibrary } from "@/services/api";
import { CATALOG_STATUS_UNAVAILABLE_PRESENTATION, getCatalogStatusPresentation } from "@/lib/catalog/labels";
import { STATUS_CONTRACT_ERROR_MESSAGE, isStatusContractError } from "@/lib/catalog/contractGuard";
import { formatLibraryTimestamp } from "@/utils/libraryStatus";
import type { UnifiedStatus } from "@/lib/catalog/status";

const props = withDefaults(
  defineProps<{
    path?: string;
    variant?: "button" | "card";
  }>(),
  {
    path: "",
    variant: "button",
  },
);

const { activeLibrary } = useActiveLibrarySelection();
const libraryId = computed(() => activeLibrary.value?.id ?? null);
const pathRef = computed(() => props.path || null);
const normalizedPath = computed(() => normalizeQueryPath(pathRef.value));
const importPaths = computed(() => activeLibrary.value?.import_paths ?? []);
const isSingleImportPathRoot = computed(() => {
  if (!normalizedPath.value || importPaths.value.length !== 1) return false;
  return normalizeQueryPath(importPaths.value[0]?.path) === normalizedPath.value;
});
const isLibraryScope = computed(() => !normalizedPath.value || isSingleImportPathRoot.value);
const statusScopePath = computed(() => (isLibraryScope.value ? null : pathRef.value));
const queryEnabled = computed(() => Boolean(libraryId.value));

const { data, isLoading, error, refetch, contractError } = useCatalogStatusQuery(
  libraryId,
  statusScopePath,
  queryEnabled,
);

const status = computed<UnifiedStatus | null>(() => data.value?.status ?? null);
const presentation = computed(() => getCatalogStatusPresentation(status.value?.summary_state ?? null));
const statusLoadError = computed(() => contractError.value ?? (error.value as Error | null));
const hasStatusLoadError = computed(() => Boolean(statusLoadError.value));
const effectivePresentation = computed(() =>
  hasStatusLoadError.value ? CATALOG_STATUS_UNAVAILABLE_PRESENTATION : presentation.value,
);
const globalWorkOutsideScope = computed(() => status.value?.metadata.global_active_outside_scope ?? false);
const mediaFilesFound = computed(() => status.value?.metadata.total_assets ?? 0);
const mediaMetadataReady = computed(() => status.value?.metadata.ready_assets ?? 0);
const failedAssets = computed(() => status.value?.metadata.failed_assets ?? 0);
const notReadyAssets = computed(() => status.value?.metadata.not_ready_assets ?? 0);
const metadataProgress = computed(() => status.value?.metadata.progress_percent ?? null);
const isIndexing = computed(
  () => status.value?.metadata.state === "queued" || status.value?.metadata.state === "indexing",
);
const isScanning = computed(() => status.value?.scan.state === "queued" || status.value?.scan.state === "scanning");
const errorMessage = computed(() => {
  if (contractError.value) return STATUS_CONTRACT_ERROR_MESSAGE;
  return statusLoadError.value?.message || "Failed to load status";
});

const showDetails = ref(false);
const actionPending = ref<"scan" | null>(null);
const actionError = ref("");

const scopeLabel = computed(() =>
  isLibraryScope.value ? "Entire library · All folders" : "Current folder · Including subfolders",
);

const compactSummary = computed(() => {
  if (!status.value) return "";
  if (isScanning.value) {
    const completed = status.value.scan.completed_units ?? 0;
    if (status.value.scan.total_units !== null) {
      return `${completed.toLocaleString()} / ${status.value.scan.total_units.toLocaleString()} file catalog items updated`;
    }
    return completed > 0 ? `${completed.toLocaleString()} file catalog items updated` : "Updating file catalog...";
  }
  if (isIndexing.value) {
    if (metadataProgress.value !== null) {
      return `${mediaMetadataReady.value.toLocaleString()} / ${mediaFilesFound.value.toLocaleString()} metadata ready`;
    }
    return "Updating metadata...";
  }
  if (globalWorkOutsideScope.value) return "Metadata extraction running in another folder";
  if (status.value.summary_state === "needs_update" && notReadyAssets.value > 0) {
    return `${notReadyAssets.value.toLocaleString()} media files need metadata updates`;
  }
  if (status.value.summary_state === "error") return "File catalog needs attention";
  if (status.value.summary_state === "offline") return "Offline";
  if (status.value.summary_state === "needs_scan") return "Needs update";
  return mediaMetadataReady.value >= mediaFilesFound.value && mediaFilesFound.value > 0
    ? "All metadata ready"
    : `${mediaMetadataReady.value.toLocaleString()} / ${mediaFilesFound.value.toLocaleString()} metadata ready`;
});

const updateLabel = computed(() => (isLibraryScope.value ? "Update library" : "Update current folder"));

function onOpenChange(open: boolean) {
  if (!open) {
    showDetails.value = false;
  }
}

async function invalidateAfterAction(id: number) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.statusLibrary(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.statusPathRoot(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.statusBatch() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.generatedImages(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.browseRoot(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.browseInfiniteRoot(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
  ]);
  await refetch();
}

async function triggerAction() {
  const id = libraryId.value;
  if (id === null || actionPending.value) return;
  actionPending.value = "scan";
  actionError.value = "";
  try {
    await scanLibrary(id, statusScopePath.value ?? undefined);
    await invalidateAfterAction(id);
  } catch (err) {
    if (isStatusContractError(err)) {
      actionError.value = STATUS_CONTRACT_ERROR_MESSAGE;
    } else {
      actionError.value = err instanceof Error ? err.message : "Unable to update the file catalog.";
    }
  } finally {
    actionPending.value = null;
  }
}

function formatCount(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <IndexStatusCard
    v-if="variant === 'card'"
    :status="status"
    :presentation="effectivePresentation"
    :path="path"
    :is-library-scope="isLibraryScope"
    :scope-label="scopeLabel"
    :is-loading="isLoading"
    :is-error="hasStatusLoadError"
    :error-message="errorMessage"
    :global-work-outside-scope="globalWorkOutsideScope"
    :action-pending="actionPending"
    :action-error="actionError"
    :contract-error="Boolean(contractError)"
    @scan="triggerAction"
  />

  <Popover v-else @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <span class="inline-flex">
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              variant="outline"
              size="sm"
              class="h-8 gap-1.5 px-2.5 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center"
              aria-label="File catalog status"
            >
              <span class="relative inline-flex">
                <Database class="size-3.5" data-testid="catalog-database-icon" />
                <PillIndicator
                  :variant="effectivePresentation.indicator"
                  :pulse="effectivePresentation.showPulse"
                  class="absolute -bottom-0.5 -right-0.5 hidden group-data-[collapsible=icon]:flex"
                  aria-hidden="true"
                  data-testid="catalog-status-icon-indicator"
                />
              </span>
              <IndexStatusBadge
                :presentation="effectivePresentation"
                size="compact"
                class="group-data-[collapsible=icon]:hidden"
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">File catalog status</TooltipContent>
        </Tooltip>
      </span>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-4" align="end" :side-offset="8">
      <div v-if="isLoading" class="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader class="size-4 animate-spin" />
        Loading file catalog status...
      </div>

      <div v-else-if="contractError" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-amber-600 shrink-0 mt-0.5" />
        <span>{{ STATUS_CONTRACT_ERROR_MESSAGE }}</span>
      </div>

      <div v-else-if="hasStatusLoadError" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-destructive shrink-0 mt-0.5" />
        <span class="text-destructive">{{ errorMessage }}</span>
      </div>

      <div v-else-if="status" class="space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Database class="size-4 text-muted-foreground" />
            <span class="text-sm font-medium">File catalog</span>
          </div>
          <IndexStatusBadge :presentation="effectivePresentation" />
        </div>

        <div class="space-y-1.5">
          <p class="text-xs text-muted-foreground">{{ compactSummary }}</p>
          <p class="text-xs text-muted-foreground">{{ scopeLabel }}</p>
          <p v-if="globalWorkOutsideScope" class="text-xs text-muted-foreground">
            Metadata extraction running in another folder
          </p>
        </div>

        <button
          type="button"
          class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
          :aria-expanded="showDetails"
          @click="showDetails = !showDetails"
        >
          <ChevronRight v-if="!showDetails" class="size-3" />
          <ChevronDown v-else class="size-3" />
          Details
        </button>

        <div v-if="showDetails" class="space-y-3 border-t pt-2">
          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Library</p>

            <Tooltip :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Media files</span>
                  <span class="text-right font-medium">{{ formatCount(mediaFilesFound) }}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                Cataloged image and video files in this scope.
              </TooltipContent>
            </Tooltip>

            <Tooltip :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Metadata ready</span>
                  <span class="text-right font-medium">
                    {{ formatCount(mediaMetadataReady) }}
                    <template v-if="isIndexing"> / {{ formatCount(mediaFilesFound) }}</template>
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                Media files with current metadata ready for search and inspection.
              </TooltipContent>
            </Tooltip>
          </div>

          <div v-if="isIndexing && metadataProgress !== null" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Processing</p>
            <p class="text-xs text-muted-foreground">{{ Math.round(metadataProgress) }}% metadata processed</p>
          </div>

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Location</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Scope</span>
              <OverflowTooltip
                :text="path || 'Library root'"
                class="ml-2 max-w-[150px] text-right font-medium"
                align="end"
              >
                {{ path || "Library root" }}
              </OverflowTooltip>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Including subfolders</span>
              <span class="text-right font-medium">{{ isLibraryScope ? "All folders" : "Yes" }}</span>
            </div>
          </div>

          <div v-if="failedAssets > 0" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Health</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-destructive">Failed metadata</span>
              <span class="text-right font-medium">{{ formatCount(failedAssets) }}</span>
            </div>
          </div>

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Timestamps</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Media files updated</span>
              <span class="text-right font-medium">{{ formatLibraryTimestamp(status.last_scan_at) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Metadata updated</span>
              <span class="text-right font-medium">{{ formatLibraryTimestamp(status.last_index_at) }}</span>
            </div>
          </div>

          <div v-if="status.latest_issue" class="rounded-md bg-destructive/10 p-2 text-xs">
            <span class="font-medium text-destructive">Latest issue:</span>
            <p class="text-muted-foreground mt-0.5">{{ status.latest_issue.message }}</p>
          </div>
        </div>

        <div v-if="actionError" class="text-xs text-destructive">{{ actionError }}</div>

        <div class="flex gap-2 pt-1">
          <Button variant="outline" size="sm" :disabled="!!actionPending" @click="triggerAction">
            {{ actionPending === "scan" ? "Updating..." : updateLabel }}
          </Button>
        </div>
      </div>

      <div v-else class="text-sm text-muted-foreground text-center py-2">No file catalog status available</div>
    </PopoverContent>
  </Popover>
</template>
