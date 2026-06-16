<script setup lang="ts">
import { computed, ref } from "vue";
import { Database, Loader, AlertCircle, ChevronDown, ChevronRight } from "lucide-vue-next";
import { useIndexStatusQuery } from "@/composables/useIndexStatusQuery";
import Button from "@/components/ui/Button.vue";
import Badge from "@/components/ui/Badge.vue";
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import IndexStatusCard from "@/components/IndexStatusCard.vue";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { IMAGE_PAGE_SIZE } from "@/constants";
import { queryClient } from "@/query";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { rebuildIndex, scanDirectory } from "@/services/api";
import { markScopeRebuildStarted } from "@/utils/indexMaintenance";
import { getLibraryInspectorQueryDebug, logIndexRebuildDebug, isIndexRebuildDebugEnabled } from "@/utils/indexRebuildDebug";
import { getFieldTooltip } from "@/utils/indexStatusCopy";
import {
  getIndexStatusCounts,
  getIndexStatusPresentation,
  getIndexStatusProgressInfo,
} from "@/utils/indexStatus";
const props = withDefaults(defineProps<{
  path?: string;
  variant?: "button" | "card";
}>(), {
  path: "",
  variant: "button",
});

const legacyQueryEnabled = ref(false);
const pathRef = computed(() => props.path || undefined);
const queryEnabled = computed(() => props.variant === "card" ? Boolean(pathRef.value) : legacyQueryEnabled.value);

const { data, isLoading, isError, error, refetch } = useIndexStatusQuery(pathRef, queryEnabled);

const showDetails = ref(false);
const showRebuildConfirm = ref(false);
const actionPending = ref<"rescan" | "rebuild" | null>(null);
const actionError = ref("");

const photosFoundTooltip = computed(() => getFieldTooltip("indexed_photos"));
const photoDetailsReadyTooltip = computed(() => getFieldTooltip("metadata_records"));
const detailsProcessedTooltip = computed(() => getFieldTooltip("done"));
const folderTooltip = computed(() => getFieldTooltip("path"));

const counts = computed(() => getIndexStatusCounts(data.value));
const progressInfo = computed(() => getIndexStatusProgressInfo(data.value));
const statusPresentation = computed(() => getIndexStatusPresentation(data.value ?? null, {
  hasPath: !!props.path,
  isLoading: isLoading.value,
  isError: isError.value,
}));
const errorMessage = computed(() => (error.value as Error | null)?.message || "Failed to load status");
const isDebugEnabled = computed(() => isIndexRebuildDebugEnabled());

const compactReadySummary = computed(() => {
  const metadata = data.value?.metadata_records ?? 0;
  const indexed = data.value?.indexed_photos ?? 0;
  if (metadata === indexed || indexed === 0) {
    return `${metadata.toLocaleString()} photos ready`;
  }
  return `${metadata.toLocaleString()} / ${indexed.toLocaleString()} photos ready`;
});

const errorIssueCount = computed(() => (data.value?.failed ?? 0) + (data.value?.staged_path_failed ?? 0));

const compactErrorSummary = computed(() => {
  if (errorIssueCount.value > 0) {
    return `${errorIssueCount.value.toLocaleString()} items need attention`;
  }
  return "Index needs attention";
});

function onOpenChange(open: boolean) {
  if (open && !legacyQueryEnabled.value) {
    legacyQueryEnabled.value = true;
  }
  if (!open) {
    showDetails.value = false;
  }
}

async function triggerIndexAction(action: "rescan" | "rebuild") {
  const requestPath = normalizeQueryPath(pathRef.value || "");
  if (!requestPath || actionPending.value) return;

  actionPending.value = action;
  actionError.value = "";

  try {
    if (action === "rebuild") {
      const rebuild = await rebuildIndex(requestPath);
      markScopeRebuildStarted(rebuild.path || requestPath, rebuild.rebuild_started_at);
      logIndexRebuildDebug("rebuild-response", {
        path: rebuild.path || requestPath,
        rebuild_started_at: rebuild.rebuild_started_at,
        activeLibraryInspectorQueries: getLibraryInspectorQueryDebug(queryClient),
      });
    } else {
      await scanDirectory(requestPath, { imageLimit: 1, imageCursor: 0 });
    }
    const libraryInspectorKey = queryKeys.libraryInspectorRoot();
    logIndexRebuildDebug("invalidate-before", {
      path: requestPath,
      invalidatedLibraryInspectorQueryKey: libraryInspectorKey,
      activeLibraryInspectorQueries: getLibraryInspectorQueryDebug(queryClient),
    });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.indexStatus(requestPath) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.scan(requestPath, IMAGE_PAGE_SIZE) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.scanInfinite(requestPath, IMAGE_PAGE_SIZE) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.folderChildren(requestPath) }),
      queryClient.invalidateQueries({ queryKey: libraryInspectorKey, refetchType: "none" }),
      queryClient.invalidateQueries({ queryKey: queryKeys.libraryInspectorMetadataRoot() }),
      queryClient.invalidateQueries({ queryKey: ["search"] }),
      queryClient.invalidateQueries({ queryKey: ["facets"] }),
    ]);
    logIndexRebuildDebug("invalidate-after", {
      path: requestPath,
      invalidatedLibraryInspectorQueryKey: libraryInspectorKey,
      activeLibraryInspectorQueries: getLibraryInspectorQueryDebug(queryClient),
    });
    await refetch();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : "Unable to update the index.";
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
  triggerIndexAction("rebuild");
}

function onRebuildCancelled() {
  showRebuildConfirm.value = false;
}
</script>

<template>
  <IndexStatusCard
    v-if="variant === 'card'"
    :data="data"
    :counts="counts"
    :presentation="statusPresentation"
    :progress="progressInfo"
    :path="path"
    :is-loading="isLoading"
    :is-error="isError"
    :error-message="errorMessage"
    :action-pending="actionPending"
    :action-error="actionError"
    @rescan="triggerIndexAction('rescan')"
    @rebuild="onRebuildRequested"
  />

  <Popover v-else @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        size="sm"
        class="h-8 gap-1.5 px-2.5 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center"
        aria-label="Index Status"
      >
        <span class="relative inline-flex">
          <Database class="size-3.5" />
          <span
            class="absolute -bottom-0.5 -right-0.5 size-1.5 rounded-full hidden group-data-[collapsible=icon]:block"
            :class="[
              statusPresentation.tone === 'green' ? 'bg-green-500' :
              statusPresentation.tone === 'yellow' ? 'bg-amber-500' :
              statusPresentation.tone === 'red' ? 'bg-red-500' :
              'bg-gray-400',
              statusPresentation.showPulse ? 'animate-pulse' : '',
            ]"
            aria-hidden="true"
          />
        </span>
        <Badge :variant="(data?.failed ?? 0) > 0 ? 'destructive' : statusPresentation.status === 'indexing' ? 'secondary' : 'outline'" class="px-1.5 py-0 text-[10px] leading-none group-data-[collapsible=icon]:hidden">
          {{ statusPresentation.label }}
        </Badge>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-4" align="end" :side-offset="8">
      <div v-if="isLoading" class="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader class="size-4 animate-spin" />
        Loading index status...
      </div>

      <div v-else-if="isError" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-destructive shrink-0 mt-0.5" />
        <span class="text-destructive">{{ (error as Error)?.message || "Failed to load status" }}</span>
      </div>

      <div v-else-if="data" class="space-y-3">
        <!-- Header row: icon + status badge -->
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Database class="size-4 text-muted-foreground" />
            <span class="text-sm font-medium">Index</span>
          </div>
          <IndexStatusBadge :presentation="statusPresentation" />
        </div>

        <!-- Compact summary -->
        <div class="space-y-1.5">
          <!-- Ready / Needs update state -->
          <p v-if="statusPresentation.status === 'ready' || statusPresentation.status === 'stale'" class="text-xs text-muted-foreground">
            {{ compactReadySummary }}
          </p>

          <!-- Updating state -->
          <p v-else-if="statusPresentation.status === 'indexing'" class="text-xs text-muted-foreground">
            Updating photo details…
          </p>

          <!-- Error state -->
          <p v-else-if="statusPresentation.status === 'error'" class="text-xs text-muted-foreground">
            {{ compactErrorSummary }}
          </p>

          <!-- Unknown / other -->
          <p v-else class="text-xs text-muted-foreground">
            Index status unavailable
          </p>
        </div>

        <!-- Details toggle -->
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

        <!-- Details content -->
        <div v-if="showDetails" class="space-y-3 border-t pt-2">

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Library</p>

            <Tooltip v-if="photosFoundTooltip" :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Photos found</span>
                  <span class="text-right font-medium">{{ (data.indexed_photos ?? 0).toLocaleString() }}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                {{ photosFoundTooltip }}
              </TooltipContent>
            </Tooltip>
            <div v-else class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Photos found</span>
              <span class="text-right font-medium">{{ (data.indexed_photos ?? 0).toLocaleString() }}</span>
            </div>

            <Tooltip v-if="photoDetailsReadyTooltip" :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Photo details ready</span>
                  <span class="text-right font-medium">
                    {{ (data.metadata_records ?? 0).toLocaleString() }}
                    <template v-if="statusPresentation.status === 'indexing'"> / {{ (data.indexed_photos ?? 0).toLocaleString() }}</template>
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                {{ photoDetailsReadyTooltip }}
              </TooltipContent>
            </Tooltip>
            <div v-else class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Photo details ready</span>
              <span class="text-right font-medium">
                {{ (data.metadata_records ?? 0).toLocaleString() }}
                <template v-if="statusPresentation.status === 'indexing'"> / {{ (data.indexed_photos ?? 0).toLocaleString() }}</template>
              </span>
            </div>
          </div>

          <div v-if="statusPresentation.status === 'indexing'" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Processing</p>

            <Tooltip v-if="detailsProcessedTooltip" :delay-duration="800">
              <TooltipTrigger as-child>
                <p class="text-xs text-muted-foreground cursor-default">
                  {{ progressInfo.indexed.toLocaleString() }}<template v-if="progressInfo.total !== null"> / {{ progressInfo.total.toLocaleString() }}</template> details processed
                </p>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                {{ detailsProcessedTooltip }}
              </TooltipContent>
            </Tooltip>
            <p v-else class="text-xs text-muted-foreground">
              {{ progressInfo.indexed.toLocaleString() }}<template v-if="progressInfo.total !== null"> / {{ progressInfo.total.toLocaleString() }}</template> details processed
            </p>

            <div v-if="progressInfo.percent !== null" class="h-1 w-full rounded-full bg-muted overflow-hidden" aria-hidden="true">
              <div
                class="h-full rounded-full bg-primary transition-all duration-500"
                :style="{ width: `${progressInfo.percent}%` }"
              />
            </div>
          </div>

          <div class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Location</p>

            <Tooltip v-if="folderTooltip" :delay-duration="800">
              <TooltipTrigger as-child>
                <div class="flex items-center justify-between text-xs">
                  <span class="text-muted-foreground cursor-default">Folder</span>
                  <span class="text-right font-medium truncate ml-2 max-w-[150px]" :title="data.path || path">{{ data.path || path }}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="start" class="max-w-[220px] text-xs whitespace-pre-line">
                {{ folderTooltip }}
              </TooltipContent>
            </Tooltip>
            <div v-else class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Folder</span>
              <span class="text-right font-medium truncate ml-2 max-w-[150px]" :title="data.path || path">{{ data.path || path }}</span>
            </div>

            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">Including subfolders</span>
              <span class="text-right font-medium">Yes</span>
            </div>
          </div>

          <div v-if="(data.failed ?? 0) > 0" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Issues</p>
            <div class="flex items-center justify-between text-xs">
              <span class="text-destructive">Failed jobs</span>
              <span class="text-right font-medium">{{ data.failed }}</span>
            </div>
          </div>

          <div v-if="isDebugEnabled" class="space-y-1.5">
            <p class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Debug</p>
            <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <span class="text-muted-foreground">Workers</span>
              <span class="text-right font-medium">{{ data.worker_count }}</span>

              <span class="text-muted-foreground">Active jobs</span>
              <span class="text-right font-medium">{{ counts.activeJobs }}</span>

              <span class="text-muted-foreground">Queue depth</span>
              <span class="text-right font-medium">{{ counts.runtimeQueueDepth }}</span>
            </div>
          </div>
        </div>

        <!-- Last error -->
        <div v-if="data.last_error" class="rounded-md bg-destructive/10 p-2 text-xs">
          <span class="font-medium text-destructive">Last Error:</span>
          <p class="text-muted-foreground mt-0.5">{{ data.last_error.message }}</p>
          <p class="text-muted-foreground mt-0.5 text-[10px]">{{ new Date(data.last_error.updated_at * 1000).toLocaleString() }}</p>
        </div>
      </div>

      <!-- Empty state when no data and not loading/error -->
      <div v-else class="text-sm text-muted-foreground text-center py-2">
        No index status available
      </div>
    </PopoverContent>
  </Popover>

  <Dialog v-model:open="showRebuildConfirm">
    <DialogContent role="alertdialog" aria-modal="true">
      <DialogTitle>Rebuild?</DialogTitle>
      <DialogDescription>
        Rebuild clears this folder's index and extracted metadata cache before indexing again. Source image files are not deleted.
      </DialogDescription>
      <div class="flex justify-end gap-2 mt-4">
        <Button variant="outline" size="sm" @click="onRebuildCancelled">Cancel</Button>
        <Button variant="secondary" size="sm" @click="onRebuildConfirmed">Rebuild</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
