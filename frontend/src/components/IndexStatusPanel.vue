<script setup lang="ts">
import { computed, ref } from "vue";
import { Database, Loader, AlertCircle, ChevronDown, ChevronRight } from "lucide-vue-next";
import { useIndexStatusQuery } from "@/composables/useIndexStatusQuery";
import Button from "@/components/ui/Button.vue";
import Badge from "@/components/ui/Badge.vue";
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
import { IMAGE_PAGE_SIZE } from "@/constants";
import { queryClient } from "@/query";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { rebuildIndex, scanDirectory } from "@/services/api";
import { markScopeRebuildStarted } from "@/utils/indexMaintenance";
import {
  getIndexStatusState,
  getIndexStatusCounts,
  getIndexStatusProgress,
  getIndexStatusPresentation,
  getIndexStatusProgressInfo,
} from "@/utils/indexStatus";
import type { IndexStatusState } from "@/types";

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

const statusState = computed<IndexStatusState>(() => {
  if (isError.value) return "unavailable";
  if (isLoading.value) return "idle";
  return getIndexStatusState(data.value ?? null, {
    hasPath: !!props.path,
    isUnavailable: false,
  });
});

const statusLabel = computed<string>(() => {
  const d = data.value;
  if (!d) {
    switch (statusState.value) {
      case "disabled": return "Disabled";
      case "idle": return "Idle";
      case "unavailable": return "Unavailable";
      default: return "Idle";
    }
  }
  if ((d.failed ?? 0) > 0) return "Error";
  if ((d.running ?? 0) > 0 || (d.active_jobs ?? 0) > 0) return "Indexing";
  if ((d.queued ?? 0) > 0 || (d.runtime_queue_depth ?? 0) > 0) return "Queued";
  if ((d.stale ?? 0) > 0) return "Needs update";
  return "Idle";
});

const counts = computed(() => getIndexStatusCounts(data.value));
const progress = computed(() => getIndexStatusProgress(data.value));
const progressInfo = computed(() => getIndexStatusProgressInfo(data.value));
const statusPresentation = computed(() => getIndexStatusPresentation(data.value ?? null, {
  hasPath: !!props.path,
  isLoading: isLoading.value,
  isError: isError.value,
}));
const errorMessage = computed(() => (error.value as Error | null)?.message || "Failed to load status");

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
    } else {
      await scanDirectory(requestPath, { imageLimit: 1, imageCursor: 0 });
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.indexStatus(requestPath) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.scan(requestPath, IMAGE_PAGE_SIZE) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.scanInfinite(requestPath, IMAGE_PAGE_SIZE) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.folderChildren(requestPath) }),
      queryClient.invalidateQueries({ queryKey: ["library-inspector"] }),
      queryClient.invalidateQueries({ queryKey: ["library-inspector-metadata"] }),
      queryClient.invalidateQueries({ queryKey: ["search"] }),
      queryClient.invalidateQueries({ queryKey: ["facets"] }),
    ]);
    await queryClient.refetchQueries({ queryKey: ["library-inspector"], type: "active" });
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
        <Badge :variant="statusState === 'failed' || (data?.failed ?? 0) > 0 ? 'destructive' : statusState === 'active' ? 'secondary' : 'outline'" class="px-1.5 py-0 text-[10px] leading-none group-data-[collapsible=icon]:hidden">
          {{ statusLabel }}
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
          <Badge :variant="statusState === 'failed' || (data.failed ?? 0) > 0 ? 'destructive' : statusState === 'active' ? 'secondary' : 'outline'">{{ statusLabel }}</Badge>
        </div>

        <!-- Progress bar -->
        <div v-if="progress !== null && (data.running ?? 0) > 0" class="space-y-1">
          <div class="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full bg-primary transition-all duration-500"
              :style="{ width: progress + '%' }"
            />
          </div>
          <span class="text-[10px] text-muted-foreground">{{ progress }}% complete</span>
        </div>

        <!-- Summary metrics -->
        <div class="space-y-1 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">
              {{ (data.metadata_records ?? 0).toLocaleString() }} metadata records ·
              {{ (data.indexed_photos ?? 0).toLocaleString() }} indexed photos
            </span>
          </div>
          <div v-if="counts.done > 0" class="flex items-center justify-between">
            <span class="text-muted-foreground">{{ counts.done.toLocaleString() }} done jobs</span>
          </div>
          <div v-if="(data.failed ?? 0) > 0" class="flex items-center justify-between">
            <span class="text-destructive">{{ data.failed }} {{ data.failed === 1 ? 'failed job' : 'failed jobs' }}</span>
          </div>
          <div v-if="(data.queued ?? 0) > 0" class="flex items-center justify-between">
            <span class="text-muted-foreground">{{ data.queued }} queued</span>
          </div>
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
        <div v-if="showDetails" class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs border-t pt-2">
          <span class="text-muted-foreground">Processing</span>
          <span class="text-right font-medium">{{ counts.running }}</span>

          <span class="text-muted-foreground">Queued</span>
          <span class="text-right font-medium">{{ counts.queued }}</span>

          <span class="text-muted-foreground">Needs update</span>
          <span class="text-right font-medium">{{ counts.stale }}</span>

          <span class="text-muted-foreground">Workers</span>
          <span class="text-right font-medium">{{ data.worker_count }}</span>

          <span class="text-muted-foreground">Active jobs</span>
          <span class="text-right font-medium">{{ counts.activeJobs }}</span>

          <span class="text-muted-foreground">Queue depth</span>
          <span class="text-right font-medium">{{ counts.runtimeQueueDepth }}</span>
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
