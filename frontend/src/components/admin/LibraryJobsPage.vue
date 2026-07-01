<script setup lang="ts">
import { computed } from "vue";
import { ArrowLeft, RefreshCw } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useLibraryJobsQuery } from "@/composables/admin/useLibraryJobsQuery";
import { useLibraryQuery } from "@/composables/admin/useLibraryQuery";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import type { LibraryJobState } from "@/types";

const props = defineProps<{ id: number }>();
const FULL_JOB_LIMIT = 200;

const libraryId = computed(() => (Number.isFinite(props.id) && props.id > 0 ? props.id : null));
const libraryQuery = useLibraryQuery(libraryId);
const jobsQuery = useLibraryJobsQuery(libraryId, FULL_JOB_LIMIT);
useLibraryEvents();

const library = computed(() => libraryQuery.data.value ?? null);
const jobs = computed(() => jobsQuery.data.value ?? []);

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
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="library-jobs-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <ButtonLink :to="{ name: 'admin-library-detail', params: { id } }" variant="ghost" class="-ml-3">
        <ArrowLeft /> Library details
      </ButtonLink>

      <div
        v-if="!libraryId || libraryQuery.isError.value"
        class="grid min-h-72 place-items-center rounded-md border border-dashed p-8 text-center"
      >
        <div class="space-y-3">
          <h2 class="text-xl font-semibold">Library not found</h2>
          <p class="text-sm text-muted-foreground">It may have been unregistered or the link is invalid.</p>
          <ButtonLink to="/admin/libraries" variant="outline">Back to libraries</ButtonLink>
        </div>
      </div>

      <template v-else>
        <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <p class="text-sm font-medium text-muted-foreground">Library administration</p>
            <h2 id="library-jobs-heading" class="truncate text-2xl font-semibold tracking-tight">
              {{ library?.name ?? "Library" }} job history
            </h2>
            <p class="mt-1 text-sm text-muted-foreground">Showing up to {{ FULL_JOB_LIMIT }} most recent jobs.</p>
          </div>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="outline"
                size="icon"
                aria-label="Refresh job history"
                :disabled="jobsQuery.isFetching.value"
                @click="jobsQuery.refetch()"
              >
                <RefreshCw :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" align="end" class="max-w-[220px]">
              Reload this library's scan, metadata, and generated-image jobs.
            </TooltipContent>
          </Tooltip>
        </header>

        <section class="rounded-md border bg-background p-5">
          <div v-if="libraryQuery.isPending.value || jobsQuery.isPending.value" class="space-y-3">
            <Skeleton v-for="item in 8" :key="item" class="h-16 w-full" />
          </div>

          <div v-else-if="jobs.length" class="divide-y">
            <div
              v-for="job in jobs"
              :key="job.id"
              class="grid gap-3 py-4 text-sm lg:grid-cols-[minmax(0,1fr)_auto_auto_auto]"
            >
              <div class="min-w-0">
                <p class="font-medium capitalize">
                  {{ job.type.replaceAll("_", " ") }} <span class="text-muted-foreground">#{{ job.id }}</span>
                </p>
                <p v-if="job.message || job.error" :class="job.error ? 'text-destructive' : 'text-muted-foreground'">
                  {{ job.error || job.message }}
                </p>
              </div>
              <span
                class="inline-flex h-6 items-center rounded-full border px-2 text-xs font-medium capitalize"
                :class="stateClass(job.state)"
              >
                {{ job.state }}
              </span>
              <span class="text-muted-foreground">{{ jobProgress(job.progress_current, job.progress_total) }}</span>
              <span class="text-muted-foreground">{{ formatLibraryTimestamp(job.updated_at) }}</span>
            </div>
          </div>

          <p v-else class="text-sm text-muted-foreground">No jobs recorded yet.</p>

          <template v-if="jobs.length >= FULL_JOB_LIMIT">
            <Separator class="my-4" />
            <p class="text-sm text-muted-foreground">Only the latest {{ FULL_JOB_LIMIT }} jobs are shown.</p>
          </template>
        </section>
      </template>
    </div>
  </main>
</template>
