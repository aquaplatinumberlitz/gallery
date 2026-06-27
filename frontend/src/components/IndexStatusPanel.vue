<script setup lang="ts">
import { computed, ref } from "vue";
import { Database, Loader, AlertCircle, ChevronDown, ChevronRight } from "lucide-vue-next";
import { useCatalogStatusQuery } from "@/composables/useCatalogStatusQuery";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import Button from "@/components/ui/Button.vue";
import Badge from "@/components/ui/Badge.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusCard from "@/components/IndexStatusCard.vue";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { queryClient } from "@/query";
import { queryKeys } from "@/query/keys";
import { rebuildLibrary, scanLibrary } from "@/services/api";
import { markScopeRebuildStarted } from "@/utils/indexMaintenance";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
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
const queryEnabled = computed(() => Boolean(libraryId.value));

const { data, isLoading, isError, error, refetch, contractError } = useCatalogStatusQuery(
  libraryId,
  pathRef,
  queryEnabled,
);

const status = computed<UnifiedStatus | null>(() => data.value?.status ?? null);
const presentation = computed(() => getCatalogStatusPresentation(status.value?.summary_state ?? null));
const isVirtualRoot = computed(() => !pathRef.value);
const globalWorkOutsideScope = computed(() => status.value?.metadata.global_active_outside_scope ?? false);
const photosFound = computed(() => status.value?.metadata.total_assets ?? 0);
const photoDetailsReady = computed(() => status.value?.metadata.ready_assets ?? 0);
const failedAssets = computed(() => status.value?.metadata.failed_assets ?? 0);
const notReadyAssets = computed(() => status.value?.metadata.not_ready_assets ?? 0);
const metadataProgress = computed(() => status.value?.metadata.progress_percent ?? null);
const isIndexing = computed(
  () => status.value?.metadata.state === "queued" || status.value?.metadata.state === "indexing",
);
const isScanning = computed(() => status.value?.scan.state === "queued" || status.value?.scan.state === "scanning");
const errorMessage = computed(() => {
  if (contractError.value) return STATUS_CONTRACT_ERROR_MESSAGE;
  return (error.value as Error | null)?.message || "Failed to load status";
});

const showDetails = ref(false);
const showRebuildConfirm = ref(false);
const actionPending = ref<"scan" | "rebuild" | null>(null);
const actionError = ref("");

const scopeLabel = computed(() =>
  isVirtualRoot.value ? "Entire library · All import paths" : "Current folder · Including subfolders",
);

const compactSummary = computed(() => {
  if (!status.value) return "";
  if (isScanning.value) {
    const completed = status.value.scan.completed_units ?? 0;
    if (status.value.scan.total_units !== null) {
      return `${completed.toLocaleString()} / ${status.value.scan.total_units.toLocaleString()} units scanned`;
    }
    return completed > 0 ? `${completed.toLocaleString()} units scanned` : "Scanning...";
  }
  if (isIndexing.value) {
    if (metadataProgress.value !== null) {
      return `${photoDetailsReady.value.toLocaleString()} / ${photosFound.value.toLocaleString()} photo details ready`;
    }
    return "Updating photo details...";
  }
  if (globalWorkOutsideScope.value) return "Indexer working in another folder";
  if (status.value.summary_state === "needs_update" && notReadyAssets.value > 0) {
    return `${notReadyAssets.value.toLocaleString()} photo details need updating`;
  }
  if (status.value.summary_state === "error") return "Catalog needs attention";
  if (status.value.summary_state === "offline") return "Offline";
  if (status.value.summary_state === "needs_scan") return "Needs scan";
  return `${photoDetailsReady.value.toLocaleString()} photo details ready`;
});

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
    queryClient.invalidateQueries({ queryKey: queryKeys.browseRoot(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.browseInfiniteRoot(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
  ]);
  await refetch();
}

async function triggerAction(action: "scan" | "rebuild") {
  const id = libraryId.value;
  if (id === null || actionPending.value) return;
  actionPending.value = action;
  actionError.value = "";
  try {
    if (action === "rebuild") {
      await rebuildLibrary(id, pathRef.value ?? undefined);
      markScopeRebuildStarted(pathRef.value || "", Date.now());
    } else {
      await scanLibrary(id, pathRef.value ?? undefined);
    }
    await invalidateAfterAction(id);
  } catch (err) {
    if (isStatusContractError(err)) {
      actionError.value = STATUS_CONTRACT_ERROR_MESSAGE;
    } else {
      actionError.value = err instanceof Error ? err.message : "Unable to update the catalog.";
    }
  } finally {
    actionPending.value = null;
  }
}

function onRebuildRequested() {
  if (actionPending.value) return;
  showRebuildConfirm.value = true;
}

function onRebuildConfirmed() {
  showRebuildConfirm.value = false;
  void triggerAction("rebuild");
}

function onRebuildCancelled() {
  showRebuildConfirm.value = false;
}

function formatCount(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <IndexStatusCard
    v-if="variant === 'card'"
    :status="status"
    :presentation="presentation"
    :path="path"
    :is-virtual-root="isVirtualRoot"
    :scope-label="scopeLabel"
    :is-loading="isLoading"
    :is-error="isError"
    :error-message="errorMessage"
    :global-work-outside-scope="globalWorkOutsideScope"
    :action-pending="actionPending"
    :action-error="actionError"
    :contract-error="Boolean(contractError)"
    @scan="triggerAction('scan')"
    @rebuild="onRebuildRequested"
  />

  <Popover v-else @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        size="sm"
        class="h-8 gap-1.5 px-2.5 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center"
        aria-label="Catalog Status"
      >
        <span class="relative inline-flex">
          <Database class="size-3.5" data-testid="catalog-database-icon" />
          <span
            class="absolute -bottom-0.5 -right-0.5 size-1.5 rounded-full hidden group-data-[collapsible=icon]:block"
            :class="[
              presentation.tone === 'green'
                ? 'bg-green-500'
                : presentation.tone === 'yellow'
                  ? 'bg-amber-500'
                  : presentation.tone === 'red'
                    ? 'bg-red-500'
                    : 'bg-gray-400',
              presentation.showPulse ? 'animate-pulse' : '',
            ]"
            aria-hidden="true"
          />
        </span>
        <Badge
          :variant="
            presentation.variant === 'destructive'
              ? 'destructive'
              : presentation.variant === 'default'
                ? 'outline'
                : 'secondary'
          "
          class="px-1.5 py-0 text-[10px] leading-none group-data-[collapsible=icon]:hidden"
        >
          {{ presentation.label }}
        </Badge>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-4" align="end" :side-offset="8">
      <div v-if="isLoading" class="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader class="size-4 animate-spin" />
        Loading catalog status...
      </div>

      <div v-else-if="contractError" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-amber-600 shrink-0 mt-0.5" />
        <span>{{ STATUS_CONTRACT_ERROR_MESSAGE }}</span>
      </div>

      <div v-else-if="isError" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-destructive shrink-0 mt-0.5" />
        <span class="text-destructive">{{ errorMessage }}</span>
      </div>

      <div v-else-if="status" class="space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Database class="size-4 text-muted-foreground" />
            <span class="text-sm font-medium">Catalog</span>
          </div>
          <IndexStatusBadge :presentation="presentation" />
        </div>

        <div class="space-y-1.5">
          <p class="text-xs text-muted-foreground">{{ compactSummary }}</p>
          <p class="text-xs text-muted-foreground">{{ scopeLabel }}</p>
          <p v-if="globalWorkOutsideScope" class="text-xs text-muted-foreground">Indexer working in another folder</p>
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
                  <span class="text-muted-foreground cursor-default">Photos found</span>
                  <span class="text-right font-medium">{{ formatCount(photosFound) }}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                Online image and video assets found in this scope.
              </TooltipContent>
            </Tooltip>

            <Tooltip :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Photo details ready</span>
                  <span class="text-right font-medium">
                    {{ formatCount(photoDetailsReady) }}
                    <template v-if="isIndexing"> / {{ formatCount(photosFound) }}</template>
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                Assets with current metadata ready for search and inspection.
              </TooltipContent>
            </Tooltip>
          </div>

          <div v-if="isIndexing && metadataProgress !== null" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Processing</p>
            <p class="text-xs text-muted-foreground">{{ Math.round(metadataProgress) }}% details processed</p>
          </div>

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Location</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Scope</span>
              <span class="text-right font-medium truncate ml-2 max-w-[150px]" :title="path || 'Library root'">{{
                path || "Library root"
              }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Including subfolders</span>
              <span class="text-right font-medium">{{ isVirtualRoot ? "All paths" : "Yes" }}</span>
            </div>
          </div>

          <div v-if="failedAssets > 0" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Issues</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-destructive">Failed assets</span>
              <span class="text-right font-medium">{{ formatCount(failedAssets) }}</span>
            </div>
          </div>

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Timestamps</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Last scan</span>
              <span class="text-right font-medium">{{ formatLibraryTimestamp(status.last_scan_at) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Last index</span>
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
          <Button variant="outline" size="sm" :disabled="!!actionPending" @click="triggerAction('scan')">
            {{ actionPending === "scan" ? "Scanning..." : "Scan" }}
          </Button>
          <Button variant="secondary" size="sm" :disabled="!!actionPending" @click="onRebuildRequested">
            {{ actionPending === "rebuild" ? "Rebuilding..." : "Rebuild" }}
          </Button>
        </div>
      </div>

      <div v-else class="text-sm text-muted-foreground text-center py-2">No catalog status available</div>
    </PopoverContent>
  </Popover>

  <Dialog v-model:open="showRebuildConfirm">
    <DialogContent role="alertdialog" aria-modal="true">
      <DialogTitle>Rebuild?</DialogTitle>
      <DialogDescription>
        Rebuild will re-index this scope's files and re-extract metadata. Source image files are not deleted.
      </DialogDescription>
      <div class="flex justify-end gap-2 mt-4">
        <Button variant="outline" size="sm" @click="onRebuildCancelled"> Cancel </Button>
        <Button variant="secondary" size="sm" @click="onRebuildConfirmed"> Rebuild </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
