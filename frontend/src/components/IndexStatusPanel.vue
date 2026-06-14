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

const queryEnabled = ref(false);

const { data, isLoading, isError, error } = useIndexStatusQuery(queryEnabled);

type StatusState = "loading" | "idle" | "indexing" | "disabled" | "error";

const statusState = computed<StatusState>(() => {
  if (isLoading.value) return "loading";
  if (isError.value) return "error";
  if (data.value && !data.value.enabled) return "disabled";
  if (data.value && data.value.active_jobs > 0) return "indexing";
  return "idle";
});

const statusLabel = computed<string>(() => {
  switch (statusState.value) {
    case "loading": return "Loading...";
    case "idle": return "Idle";
    case "indexing": return "Indexing";
    case "disabled": return "Disabled";
    case "error": return "Error";
  }
});

const statusBadgeVariant = computed<"default" | "secondary" | "destructive" | "outline" | "loading" | "subtle">(() => {
  switch (statusState.value) {
    case "loading": return "loading";
    case "idle": return "default";
    case "indexing": return "secondary";
    case "disabled": return "outline";
    case "error": return "destructive";
  }
});

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
        class="h-8 gap-1.5 px-2.5"
        title="Index Status"
        aria-label="Index Status"
      >
        <Database class="size-3.5" />
        <Badge :variant="statusBadgeVariant" class="px-1.5 py-0 text-[10px] leading-none">
          {{ statusLabel }}
        </Badge>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-4" align="end" :side-offset="8">
      <div v-if="statusState === 'loading'" class="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader class="size-4 animate-spin" />
        Loading index status...
      </div>

      <div v-else-if="statusState === 'error'" class="flex items-start gap-2 text-sm">
        <AlertCircle class="size-4 text-destructive shrink-0 mt-0.5" />
        <span class="text-destructive">{{ (error as Error)?.message || "Failed to load status" }}</span>
      </div>

      <div v-else-if="data" class="space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">Index Status</span>
          <Badge :variant="statusBadgeVariant">{{ statusLabel }}</Badge>
        </div>

        <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <span class="text-muted-foreground">Index Type</span>
          <span class="text-right font-medium capitalize">{{ data.index_type }}</span>

          <span class="text-muted-foreground">Indexed Files</span>
          <span class="text-right font-medium">{{ data.indexed_files.toLocaleString() }}</span>

          <span class="text-muted-foreground">Total Files</span>
          <span class="text-right font-medium">{{ data.total_files.toLocaleString() }}</span>

          <span class="text-muted-foreground">Workers</span>
          <span class="text-right font-medium">{{ data.worker_count }}</span>

          <span class="text-muted-foreground">Active Jobs</span>
          <span class="text-right font-medium">{{ data.active_jobs }}</span>

          <span class="text-muted-foreground">Queue Depth</span>
          <span class="text-right font-medium">{{ data.runtime_queue_depth }}</span>

          <span class="text-muted-foreground">Coalesced</span>
          <span class="text-right font-medium">{{ data.coalesced_duplicates }}</span>

          <span class="text-muted-foreground">Staged</span>
          <span class="text-right font-medium">{{ data.staged_path_queue_depth }}</span>

          <span class="text-muted-foreground">Scan Requests</span>
          <span class="text-right font-medium">{{ data.active_scan_requests }}</span>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
