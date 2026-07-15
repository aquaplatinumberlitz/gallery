<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { File, FileChartColumn, Info, RefreshCw, Trash2 } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { Card, CardContent } from "@/components/ui/card";
import { queryKeys } from "@/query/keys";
import { fetchLibraries, fetchGeneratedImagesStatus } from "@/services/api";
import { useGeneratedImagesGlobalMutations } from "@/composables/admin/useGeneratedImagesGlobalMutations";
import { useFileHealthQuery, useFileHealthMutation } from "@/composables/admin/useFileHealthQuery";
import { useJobsQuery } from "@/composables/admin/useJobsQuery";
import { useMaintenanceRuntimeQuery } from "@/composables/admin/useMaintenanceRuntimeQuery";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import JobList from "./JobList.vue";
import MaintenanceFileHealth from "./MaintenanceFileHealth.vue";
import MaintenanceImageCache from "./MaintenanceImageCache.vue";
import MaintenancePipelineFlow from "./MaintenancePipelineFlow.vue";
import GeneratedImagesClearDialog from "./dialogs/GeneratedImagesClearDialog.vue";
import GeneratedImagesRebuildDialog from "./dialogs/GeneratedImagesRebuildDialog.vue";

const RECENT_JOB_LIMIT = 8;
const rebuildOpen = shallowRef(false);
const clearOpen = shallowRef(false);
const { rebuildMutation, clearMutation } = useGeneratedImagesGlobalMutations();
const jobsQuery = useJobsQuery(RECENT_JOB_LIMIT);

const globalSummaryQuery = useQuery({
  queryKey: [...queryKeys.generatedImagesRoot(), "global-summary"],
  queryFn: async () => {
    const libraries = await fetchLibraries();
    const results = await Promise.all(libraries.map((lib) => fetchGeneratedImagesStatus(lib.id)));
    return results;
  },
  staleTime: 30_000,
});

const totalReady = computed(() => {
  const data = globalSummaryQuery.data.value;
  if (!data) return null;
  return data.reduce((s, r) => s + r.ready_derivatives, 0);
});

const totalExpected = computed(() => {
  const data = globalSummaryQuery.data.value;
  if (!data) return null;
  return data.reduce((s, r) => s + r.expected_derivatives, 0);
});

const fileHealthQuery = useFileHealthQuery();
const fileHealthMutation = useFileHealthMutation();

async function confirmClear() {
  try {
    await clearMutation.mutateAsync();
    clearOpen.value = false;
  } catch {
    // toast handled in mutation onError
  }
}

async function confirmRebuild() {
  try {
    await rebuildMutation.mutateAsync();
    rebuildOpen.value = false;
  } catch {
    // toast handled in mutation onError
  }
}

const runtimeQuery = useMaintenanceRuntimeQuery();

const needsRefreshCount = computed(() => {
  const lc = runtimeQuery.data.value?.metadata_lifecycle;
  if (!lc) return 0;
  return (lc.stale_metadata_jobs ?? 0) + (lc.assets_done_but_metadata_missing_or_stale ?? 0);
});
</script>

<template>
  <main class="h-full overflow-y-auto p-4 text-foreground sm:p-6" aria-labelledby="maintenance-heading">
    <div class="maintenance-page-stack mx-auto max-w-6xl space-y-6">
      <header class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="min-w-0">
          <h2 id="maintenance-heading" class="text-xl font-semibold tracking-normal text-foreground">Maintenance</h2>
          <p class="mt-0.5 text-sm text-muted-foreground">
            File health checks, repair tracking, and imported-data diagnostics.
          </p>
        </div>
        <div class="flex flex-shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            size="lg"
            class="border-border bg-card px-4 text-sm text-foreground shadow-sm hover:bg-muted/70"
            :disabled="rebuildMutation.isPending.value"
            @click="rebuildOpen = true"
          >
            <RefreshCw data-icon="inline-start" /> Rebuild
          </Button>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="destructive"
                size="lg"
                class="px-4"
                :disabled="clearMutation.isPending.value"
                @click="clearOpen = true"
              >
                <Trash2 data-icon="inline-start" aria-hidden="true" /> Clear imported data
              </Button>
            </TooltipTrigger>
            <TooltipContent class="max-w-[320px] text-pretty">
              Clears the file catalog, extracted metadata, search indexes, job history, thumbnails, and previews.
              Library settings and source files are kept.
            </TooltipContent>
          </Tooltip>
        </div>
      </header>

      <MaintenancePipelineFlow />

      <MaintenanceFileHealth
        :run="fileHealthQuery.data.value?.run"
        :pending="fileHealthMutation.isPending.value"
        @run-checks="fileHealthMutation.mutateAsync()"
      />

      <div class="maintenance-status-grid grid gap-4 md:grid-cols-2">
        <Card class="maintenance-status-card gap-0 py-0">
          <CardContent class="maintenance-status-content p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <File class="size-5 text-foreground/70" aria-hidden="true" />
                <h3 class="font-semibold text-foreground">File catalog</h3>
              </div>
              <p class="text-sm text-muted-foreground">Tracks which source files exist in registered libraries.</p>
            </div>
            <div v-if="runtimeQuery.data.value" class="mt-4">
              <dl class="grid gap-3 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Watching for changes</dt>
                  <dd
                    class="font-medium"
                    :class="
                      !runtimeQuery.data.value.global_runtime.watcher_enabled
                        ? 'text-muted-foreground'
                        : runtimeQuery.data.value.global_runtime.watcher_healthy
                          ? 'text-success'
                          : 'text-destructive'
                    "
                  >
                    {{
                      runtimeQuery.data.value.global_runtime.watcher_enabled
                        ? runtimeQuery.data.value.global_runtime.watcher_healthy
                          ? "Healthy"
                          : "Unhealthy"
                        : "Off"
                    }}
                  </dd>
                </div>
                <div
                  v-if="runtimeQuery.data.value.global_runtime.watcher_issue"
                  class="flex items-center justify-between gap-3"
                >
                  <dt class="text-muted-foreground">Latest issue</dt>
                  <dd class="max-w-48 truncate text-right text-sm text-destructive">
                    {{ runtimeQuery.data.value.global_runtime.watcher_issue }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Scheduled refresh</dt>
                  <dd class="font-medium">
                    {{ runtimeQuery.data.value.global_runtime.scheduled_reconciliation_enabled ? "On" : "Off" }}
                  </dd>
                </div>
                <Separator />
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">File catalog workers</dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.catalog_worker_count }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">File catalog active jobs</dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.catalog_active_jobs }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    File catalog queue depth
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About File catalog queue depth"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start">
                        File catalog scan or rebuild jobs waiting to run.
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.catalog_queue_depth }}
                  </dd>
                </div>
              </dl>
            </div>
            <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-32 w-full" />
            <p v-else class="mt-4 text-sm text-muted-foreground">Runtime diagnostics unavailable.</p>
          </CardContent>
        </Card>

        <Card class="maintenance-status-card gap-0 py-0">
          <CardContent class="maintenance-status-content p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <FileChartColumn class="size-5 text-foreground/70" aria-hidden="true" />
                <h3 class="font-semibold text-foreground">Metadata extraction</h3>
              </div>
              <p class="text-sm text-muted-foreground">Reads file details after files are cataloged.</p>
            </div>
            <div v-if="runtimeQuery.data.value" class="mt-4 space-y-3">
              <dl class="grid gap-3 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Metadata workers</dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.metadata_worker_count }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Metadata active jobs</dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.metadata_active_jobs }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    Metadata queue depth
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About Metadata queue depth"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start">Metadata extraction jobs waiting to run.</TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.metadata_queue_depth }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    Metadata staged queue depth
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About Metadata staged queue depth"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start" class="max-w-[220px]">
                        Metadata paths staged before they become durable extraction jobs.
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.global_runtime.metadata_staged_queue_depth }}
                  </dd>
                </div>
                <Separator v-if="runtimeQuery.data.value.metadata_lifecycle" />
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Queued</dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ runtimeQuery.data.value.metadata_lifecycle?.queued_metadata_jobs ?? "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Running</dt>
                  <dd class="font-medium tabular-nums">
                    {{ runtimeQuery.data.value.metadata_lifecycle?.running_metadata_jobs ?? "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    Failed jobs
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About Failed jobs"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start">
                        Metadata extraction jobs that already failed.
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd
                    class="font-medium tabular-nums"
                    :class="
                      (runtimeQuery.data.value.metadata_lifecycle?.failed_metadata_jobs ?? 0) > 0
                        ? 'text-destructive'
                        : ''
                    "
                  >
                    {{ runtimeQuery.data.value.metadata_lifecycle?.failed_metadata_jobs ?? "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    Old or missing metadata
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About Old or missing metadata"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start">
                        Files whose extracted metadata is stale or missing.
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-medium tabular-nums" :class="needsRefreshCount > 0 ? 'text-warning' : ''">
                    {{ runtimeQuery.data.value.metadata_lifecycle ? needsRefreshCount : "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Can be repaired</dt>
                  <dd
                    class="font-medium tabular-nums"
                    :class="
                      (runtimeQuery.data.value.metadata_lifecycle?.repairable_metadata_assets ?? 0) > 0
                        ? 'text-warning'
                        : ''
                    "
                  >
                    {{ runtimeQuery.data.value.metadata_lifecycle?.repairable_metadata_assets ?? "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="flex items-center gap-1 text-muted-foreground">
                    Jobs without catalog item
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon-lg"
                          class="-my-2 text-muted-foreground hover:text-foreground"
                          aria-label="About Jobs without catalog item"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start">
                        Metadata index jobs with no matching catalog entry.
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-medium tabular-nums">
                    {{ runtimeQuery.data.value.metadata_lifecycle?.metadata_jobs_without_matching_assets ?? "\u2014" }}
                  </dd>
                </div>
              </dl>
            </div>
            <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-40 w-full" />
            <p v-else class="mt-4 text-sm text-muted-foreground">Metadata extraction diagnostics unavailable.</p>
          </CardContent>
        </Card>
      </div>

      <MaintenanceImageCache
        :runtime="runtimeQuery.data.value?.global_runtime"
        :runtime-pending="runtimeQuery.isPending.value"
        :total-ready="totalReady"
        :total-expected="totalExpected"
        :summary-available="Boolean(globalSummaryQuery.data.value)"
        :summary-pending="globalSummaryQuery.isPending.value"
        :summary-fetching="globalSummaryQuery.isFetching.value"
        @refresh="globalSummaryQuery.refetch()"
      />

      <Card class="gap-0 py-0">
        <CardContent class="p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="font-semibold text-foreground">Recent job history</h3>
              <p class="mt-1 text-sm text-muted-foreground">
                Latest {{ RECENT_JOB_LIMIT }} file catalog, metadata, and image cache jobs.
              </p>
            </div>
            <div class="flex items-center gap-2">
              <ButtonLink
                :to="{ name: 'admin-jobs' }"
                variant="outline"
                size="sm"
                class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
              >
                View all jobs
              </ButtonLink>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    class="-my-2 -me-2"
                    aria-label="Refresh recent jobs"
                    :disabled="jobsQuery.isFetching.value"
                    @click="jobsQuery.refetch()"
                  >
                    <RefreshCw :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" align="end" class="max-w-[220px]">
                  Reload recent file catalog, metadata, and image cache jobs.
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
          <JobList v-if="jobsQuery.data.value?.length" class="mt-4" :jobs="jobsQuery.data.value" show-library />
          <Skeleton v-else-if="jobsQuery.isPending.value" class="mt-4 h-24 w-full" />
          <p v-else class="mt-4 text-sm text-muted-foreground">No jobs recorded yet.</p>
        </CardContent>
      </Card>
    </div>

    <GeneratedImagesRebuildDialog
      v-model:open="rebuildOpen"
      :pending="rebuildMutation.isPending.value"
      @confirm="confirmRebuild"
    />
    <GeneratedImagesClearDialog
      v-model:open="clearOpen"
      :pending="clearMutation.isPending.value"
      @confirm="confirmClear"
    />
  </main>
</template>

<style scoped>
@media (max-width: 1023px) {
  .maintenance-page-stack {
    gap: 1.75rem;
  }

  .maintenance-status-grid {
    gap: 1rem;
  }

  .maintenance-status-content {
    padding: 1.25rem;
  }

  .maintenance-status-content dl {
    gap: 0.875rem;
  }

  .maintenance-status-content dl > div:not([role]) {
    min-height: 2rem;
  }
}
</style>
