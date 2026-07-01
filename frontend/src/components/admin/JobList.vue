<script setup lang="ts">
import { computed } from "vue";
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import type { LibraryJob, LibraryJobState } from "@/types";

const props = withDefaults(
  defineProps<{
    jobs: LibraryJob[];
    variant?: "compact" | "full";
    showLibrary?: boolean;
    emptyText?: string;
    class?: HTMLAttributes["class"];
  }>(),
  {
    variant: "compact",
    showLibrary: false,
    emptyText: "No jobs recorded yet.",
    class: undefined,
  },
);

const gridClass = computed(() =>
  props.variant === "full"
    ? "grid gap-3 py-4 text-sm lg:grid-cols-[minmax(0,1fr)_auto_auto_auto]"
    : "grid gap-2 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto]",
);

const stateClasses: Record<LibraryJobState, string> = {
  queued: "border-muted-foreground/30 text-muted-foreground",
  running: "border-primary/40 bg-primary/10 text-primary",
  succeeded: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  failed: "border-destructive/40 bg-destructive/10 text-destructive",
  cancelled: "border-muted-foreground/30 text-muted-foreground",
};

function jobProgress(current: number, total: number | null): string {
  return total && total > 0 ? `${formatAssetCount(current)} / ${formatAssetCount(total)}` : formatAssetCount(current);
}

function stateClass(state: LibraryJobState): string {
  return stateClasses[state] ?? "border-muted-foreground/30 text-muted-foreground";
}
</script>

<template>
  <div :class="cn(props.class)">
    <div v-if="jobs.length" class="divide-y">
      <div v-for="job in jobs" :key="job.id" :class="gridClass">
        <div class="min-w-0">
          <p class="font-medium capitalize">
            {{ job.type.replaceAll("_", " ") }} <span class="text-muted-foreground">#{{ job.id }}</span>
            <span v-if="showLibrary && job.library_id" class="text-muted-foreground">
              · Library #{{ job.library_id }}</span
            >
          </p>
          <p v-if="job.message || job.error" :class="job.error ? 'text-destructive' : 'text-muted-foreground'">
            {{ job.error || job.message }}
          </p>
        </div>
        <span
          v-if="variant === 'full'"
          class="inline-flex h-6 items-center rounded-full border px-2 text-xs font-medium capitalize"
          :class="stateClass(job.state)"
        >
          {{ job.state }}
        </span>
        <span v-else class="capitalize" :class="job.state === 'failed' ? 'text-destructive' : 'text-muted-foreground'">
          {{ job.state }}
        </span>
        <span class="text-muted-foreground">
          {{ jobProgress(job.progress_current, job.progress_total) }} · {{ formatLibraryTimestamp(job.updated_at) }}
        </span>
      </div>
    </div>
    <p v-else class="text-sm text-muted-foreground">{{ emptyText }}</p>
  </div>
</template>
