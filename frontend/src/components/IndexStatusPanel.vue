<script setup lang="ts">
import { computed, ref } from "vue";
import { Database, Loader, AlertCircle } from "lucide-vue-next";
import { useIndexStatusQuery } from "@/composables/useIndexStatusQuery";
import Button from "@/components/ui/Button.vue";
import Badge from "@/components/ui/Badge.vue";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  getIndexStatusState,
  getIndexStatusCounts,
  getIndexStatusProgress,
} from "@/utils/indexStatus";
import type { IndexStatusState } from "@/types";

const props = withDefaults(defineProps<{
  path?: string;
}>(), {
  path: "",
});

const queryEnabled = ref(false);
const pathRef = computed(() => props.path || undefined);

const { data, isLoading, isError, error } = useIndexStatusQuery(pathRef, queryEnabled);

const statusState = computed<IndexStatusState>(() => {
  if (isError.value) return "unavailable";
  if (isLoading.value) return "idle";
  return getIndexStatusState(data.value ?? null, {
    hasPath: !!props.path,
    isUnavailable: false,
  });
});

const statusLabel = computed<string>(() => {
  switch (statusState.value) {
    case "failed": return "Failed";
    case "active": return "Indexing";
    case "queued": return "Queued";
    case "idle": return "Idle";
    case "unavailable": return "Unavailable";
    case "disabled": return "Disabled";
  }
});

const badgeVariantMap: Record<IndexStatusState, "default" | "secondary" | "destructive" | "outline"> = {
  failed: "destructive",
  active: "secondary",
  queued: "default",
  idle: "outline",
  unavailable: "destructive",
  disabled: "outline",
};

const statusBadgeVariant = computed(() => badgeVariantMap[statusState.value]);

const counts = computed(() => getIndexStatusCounts(data.value));
const progress = computed(() => getIndexStatusProgress(data.value));

function onOpenChange(open: boolean) {
  if (open && !queryEnabled.value) {
    queryEnabled.value = true;
  }
}
</script>

<template>
  <Popover @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        size="sm"
        class="h-8 gap-1.5 px-2.5 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center"
        aria-label="Index Status"
      >
        <Database class="size-3.5" />
        <Badge :variant="statusBadgeVariant" class="px-1.5 py-0 text-[10px] leading-none group-data-[collapsible=icon]:hidden">
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
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">Index Status</span>
          <Badge :variant="statusBadgeVariant">{{ statusLabel }}</Badge>
        </div>

        <!-- Progress bar -->
        <div v-if="progress !== null && statusState === 'active'" class="space-y-1">
          <div class="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full bg-primary transition-all duration-500"
              :style="{ width: progress + '%' }"
            />
          </div>
          <span class="text-[10px] text-muted-foreground">{{ progress }}% complete</span>
        </div>

        <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <span class="text-muted-foreground">Done</span>
          <span class="text-right font-medium">{{ counts.done.toLocaleString() }}</span>

          <span class="text-muted-foreground">Running</span>
          <span class="text-right font-medium">{{ counts.running }}</span>

          <span class="text-muted-foreground">Queued</span>
          <span class="text-right font-medium">{{ counts.queued }}</span>

          <span class="text-muted-foreground">Failed</span>
          <span class="text-right font-medium">{{ counts.failed }}</span>

          <span class="text-muted-foreground">Stale</span>
          <span class="text-right font-medium">{{ counts.stale }}</span>

          <span class="text-muted-foreground">Workers</span>
          <span class="text-right font-medium">{{ data.worker_count }}</span>

          <span class="text-muted-foreground">Active Jobs</span>
          <span class="text-right font-medium">{{ counts.activeJobs }}</span>

          <span class="text-muted-foreground">Queue Depth</span>
          <span class="text-right font-medium">{{ counts.runtimeQueueDepth }}</span>
        </div>

        <div v-if="data.last_error" class="rounded-md bg-destructive/10 p-2 text-xs">
          <span class="font-medium text-destructive">Last Error:</span>
          <p class="text-muted-foreground mt-0.5">{{ data.last_error.message }}</p>
          <p class="text-muted-foreground mt-0.5 text-[10px]">{{ new Date(data.last_error.updated_at * 1000).toLocaleString() }}</p>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
