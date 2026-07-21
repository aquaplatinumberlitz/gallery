<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { File, FileChartColumn, Info, RefreshCw, Trash2, Wrench } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
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
  <main class="mp-main h-full overflow-y-auto text-foreground" aria-labelledby="maintenance-heading">
    <div class="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6 sm:py-8">
      <!-- ═══════════════════════════════════════════
           PAGE HEADER
      ════════════════════════════════════════════ -->
      <header class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex min-w-0 items-center gap-3.5">
          <div class="flex size-11 shrink-0 items-center justify-center rounded-lg border border-border bg-muted">
            <Wrench class="size-5 text-foreground/60" />
          </div>
          <div>
            <h1 id="maintenance-heading" class="text-2xl font-semibold tracking-tight text-foreground">Maintenance</h1>
            <p class="mt-0.5 text-xs text-muted-foreground">
              File health checks, repair tracking, and imported-data diagnostics.
            </p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
            :disabled="rebuildMutation.isPending.value"
            @click="rebuildOpen = true"
          >
            <RefreshCw class="mr-1.5 size-4" /> Rebuild
          </Button>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="destructive" :disabled="clearMutation.isPending.value" @click="clearOpen = true">
                <Trash2 class="mr-1.5 size-4" aria-hidden="true" /> Clear imported data
              </Button>
            </TooltipTrigger>
            <TooltipContent class="max-w-[320px] text-pretty">
              Clears the file catalog, extracted metadata, search indexes, job history, thumbnails, and previews.
              Library settings and source files are kept.
            </TooltipContent>
          </Tooltip>
        </div>
      </header>

      <!-- Pipeline flow -->
      <MaintenancePipelineFlow />

      <!-- File health -->
      <MaintenanceFileHealth
        :run="fileHealthQuery.data.value?.run"
        :pending="fileHealthMutation.isPending.value"
        @run-checks="fileHealthMutation.mutateAsync()"
      />

      <!-- ═══════════════════════════════════════════
           RUNTIME STATUS CARDS
      ════════════════════════════════════════════ -->
      <section aria-labelledby="runtime-heading">
        <h2 id="runtime-heading" class="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Runtime diagnostics
        </h2>
        <div class="grid gap-4 md:grid-cols-2">
          <!-- File catalog card -->
          <div class="rounded-xl border border-border bg-card">
            <div class="flex items-center gap-2 border-b border-border px-5 py-4">
              <File class="size-4 text-foreground/60" aria-hidden="true" />
              <h3 class="text-sm font-semibold text-foreground">File catalog</h3>
            </div>
            <div class="px-5 py-4">
              <p class="text-xs text-muted-foreground">Tracks which source files exist in registered libraries.</p>
              <template v-if="runtimeQuery.data.value">
                <!-- Idle: watcher ok, no active/queued jobs, no issues -->
                <div
                  v-if="
                    !runtimeQuery.data.value.global_runtime.watcher_issue &&
                    (!runtimeQuery.data.value.global_runtime.watcher_enabled || runtimeQuery.data.value.global_runtime.watcher_healthy) &&
                    runtimeQuery.data.value.global_runtime.catalog_active_jobs === 0 &&
                    runtimeQuery.data.value.global_runtime.catalog_queue_depth === 0
                  "
                  class="mt-4 flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5"
                >
                  <span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-success/15">
                    <svg class="size-3 text-success" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                      <path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </span>
                  <div class="min-w-0">
                    <p class="text-xs font-medium text-foreground">Healthy</p>
                    <p class="text-xs text-muted-foreground">
                      <span v-if="runtimeQuery.data.value.global_runtime.watcher_enabled">Watching for changes · </span>
                      <span v-if="runtimeQuery.data.value.global_runtime.scheduled_reconciliation_enabled">Scheduled refresh on · </span>
                      {{ runtimeQuery.data.value.global_runtime.catalog_worker_count }} worker{{ runtimeQuery.data.value.global_runtime.catalog_worker_count !== 1 ? 's' : '' }} ready · no active jobs
                    </p>
                  </div>
                </div>

                <!-- Active or error state -->
                <template v-else>
                  <!-- Watcher issue alert -->
                  <div
                    v-if="runtimeQuery.data.value.global_runtime.watcher_issue"
                    class="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
                    role="alert"
                  >
                    Watcher issue: {{ runtimeQuery.data.value.global_runtime.watcher_issue }}
                  </div>

                  <dl class="mt-4 divide-y divide-border text-sm">
                    <div class="flex items-center justify-between gap-3 py-2">
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
                    <div class="flex items-center justify-between gap-3 py-2">
                      <dt class="text-muted-foreground">Scheduled refresh</dt>
                      <dd class="font-medium">
                        {{ runtimeQuery.data.value.global_runtime.scheduled_reconciliation_enabled ? "On" : "Off" }}
                      </dd>
                    </div>
                    <div class="flex items-center justify-between gap-3 py-2">
                      <dt class="text-muted-foreground">Workers</dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.catalog_worker_count }}
                      </dd>
                    </div>
                    <div class="flex items-center justify-between gap-3 py-2">
                      <dt class="text-muted-foreground">Active jobs</dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.catalog_active_jobs }}
                      </dd>
                    </div>
                    <div class="flex items-center justify-between gap-3 py-2">
                      <dt class="flex items-center gap-1 text-muted-foreground">
                        Queue depth
                        <Tooltip>
                          <TooltipTrigger as-child>
                            <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About File catalog queue depth">
                              <Info class="size-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="top" align="start">File catalog scan or rebuild jobs waiting to run.</TooltipContent>
                        </Tooltip>
                      </dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.catalog_queue_depth }}
                      </dd>
                    </div>
                  </dl>
                </template>
              </template>

              <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-32 w-full rounded-lg" />
              <p v-else class="mt-4 text-sm text-muted-foreground">Runtime diagnostics unavailable.</p>
            </div>
          </div>

          <!-- Metadata extraction card -->
          <div class="rounded-xl border border-border bg-card">
            <div class="flex items-center gap-2 border-b border-border px-5 py-4">
              <FileChartColumn class="size-4 text-foreground/60" aria-hidden="true" />
              <h3 class="text-sm font-semibold text-foreground">Metadata extraction</h3>
            </div>
            <div class="px-5 py-4">
              <p class="text-xs text-muted-foreground">Reads file details after files are cataloged.</p>
              <template v-if="runtimeQuery.data.value">
                <!-- Idle: all counters zero, no failures -->
                <div
                  v-if="
                    runtimeQuery.data.value.global_runtime.metadata_active_jobs === 0 &&
                    runtimeQuery.data.value.global_runtime.metadata_queue_depth === 0 &&
                    runtimeQuery.data.value.global_runtime.metadata_staged_queue_depth === 0 &&
                    (!runtimeQuery.data.value.metadata_lifecycle || (
                      runtimeQuery.data.value.metadata_lifecycle.running_metadata_jobs === 0 &&
                      (runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs ?? 0) === 0 &&
                      needsRefreshCount === 0 &&
                      (runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets ?? 0) === 0 &&
                      runtimeQuery.data.value.metadata_lifecycle.metadata_jobs_without_matching_assets === 0
                    ))
                  "
                  class="mt-4 flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5"
                >
                  <span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-success/15">
                    <svg class="size-3 text-success" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                      <path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </span>
                  <div class="min-w-0">
                    <p class="text-xs font-medium text-foreground">Healthy</p>
                    <p class="text-xs text-muted-foreground">
                      {{ runtimeQuery.data.value.global_runtime.metadata_worker_count }} worker{{ runtimeQuery.data.value.global_runtime.metadata_worker_count !== 1 ? 's' : '' }} ready · no active or queued jobs · metadata up to date
                    </p>
                  </div>
                </div>

                <!-- Active or error state -->
                <template v-else>
                  <!-- Error/warning alert -->
                  <div
                    v-if="
                      runtimeQuery.data.value.metadata_lifecycle && (
                        (runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs ?? 0) > 0 ||
                        needsRefreshCount > 0 ||
                        (runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets ?? 0) > 0
                      )
                    "
                    class="mt-4 space-y-1 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-xs"
                    role="alert"
                  >
                    <p v-if="(runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs ?? 0) > 0" class="text-destructive">
                      {{ runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs }} failed extraction job{{ runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs !== 1 ? 's' : '' }}.
                    </p>
                    <p v-if="needsRefreshCount > 0" class="text-warning">
                      {{ needsRefreshCount }} file{{ needsRefreshCount !== 1 ? 's' : '' }} with old or missing metadata.
                    </p>
                    <p v-if="(runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets ?? 0) > 0" class="text-warning">
                      {{ runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets }} asset{{ (runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets ?? 0) !== 1 ? 's' : '' }} can be repaired.
                    </p>
                  </div>

                  <dl class="mt-4 divide-y divide-border text-sm">
                    <!-- Workers (always shown in active state) -->
                    <div class="flex items-center justify-between gap-3 py-2">
                      <dt class="text-muted-foreground">Workers</dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.metadata_worker_count }}
                      </dd>
                    </div>
                    <!-- Active jobs (show when > 0) -->
                    <div v-if="runtimeQuery.data.value.global_runtime.metadata_active_jobs > 0" class="flex items-center justify-between gap-3 py-2">
                      <dt class="text-muted-foreground">Active jobs</dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.metadata_active_jobs }}
                      </dd>
                    </div>
                    <!-- Queue depth (show when > 0) -->
                    <div v-if="runtimeQuery.data.value.global_runtime.metadata_queue_depth > 0" class="flex items-center justify-between gap-3 py-2">
                      <dt class="flex items-center gap-1 text-muted-foreground">
                        Queue depth
                        <Tooltip>
                          <TooltipTrigger as-child>
                            <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About Metadata queue depth">
                              <Info class="size-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="top" align="start">Metadata extraction jobs waiting to run.</TooltipContent>
                        </Tooltip>
                      </dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.metadata_queue_depth }}
                      </dd>
                    </div>
                    <!-- Staged queue depth (show when > 0) -->
                    <div v-if="runtimeQuery.data.value.global_runtime.metadata_staged_queue_depth > 0" class="flex items-center justify-between gap-3 py-2">
                      <dt class="flex items-center gap-1 text-muted-foreground">
                        Staged queue depth
                        <Tooltip>
                          <TooltipTrigger as-child>
                            <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About Metadata staged queue depth">
                              <Info class="size-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="top" align="start" class="max-w-[220px]">Metadata paths staged before they become durable extraction jobs.</TooltipContent>
                        </Tooltip>
                      </dt>
                      <dd class="font-semibold tabular-nums text-foreground">
                        {{ runtimeQuery.data.value.global_runtime.metadata_staged_queue_depth }}
                      </dd>
                    </div>
                    <template v-if="runtimeQuery.data.value.metadata_lifecycle">
                      <!-- Running (show when > 0) -->
                      <div v-if="runtimeQuery.data.value.metadata_lifecycle.running_metadata_jobs > 0" class="flex items-center justify-between gap-3 py-2">
                        <dt class="text-muted-foreground">Running</dt>
                        <dd class="font-medium tabular-nums text-foreground">{{ runtimeQuery.data.value.metadata_lifecycle.running_metadata_jobs }}</dd>
                      </div>
                      <!-- Failed (show when > 0) -->
                      <div v-if="(runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs ?? 0) > 0" class="flex items-center justify-between gap-3 py-2">
                        <dt class="flex items-center gap-1 text-muted-foreground">
                          Failed jobs
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About Failed jobs">
                                <Info class="size-3" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" align="start">Metadata extraction jobs that already failed.</TooltipContent>
                          </Tooltip>
                        </dt>
                        <dd class="font-medium tabular-nums text-destructive">{{ runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs }}</dd>
                      </div>
                      <!-- Old or missing (show when > 0) -->
                      <div v-if="needsRefreshCount > 0" class="flex items-center justify-between gap-3 py-2">
                        <dt class="flex items-center gap-1 text-muted-foreground">
                          Old or missing metadata
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About Old or missing metadata">
                                <Info class="size-3" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" align="start">Files whose extracted metadata is stale or missing.</TooltipContent>
                          </Tooltip>
                        </dt>
                        <dd class="font-medium tabular-nums text-warning">{{ needsRefreshCount }}</dd>
                      </div>
                      <!-- Can be repaired (show when > 0) -->
                      <div v-if="(runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets ?? 0) > 0" class="flex items-center justify-between gap-3 py-2">
                        <dt class="text-muted-foreground">Can be repaired</dt>
                        <dd class="font-medium tabular-nums text-warning">{{ runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets }}</dd>
                      </div>
                      <!-- Orphan jobs (show when > 0) -->
                      <div v-if="runtimeQuery.data.value.metadata_lifecycle.metadata_jobs_without_matching_assets > 0" class="flex items-center justify-between gap-3 py-2">
                        <dt class="flex items-center gap-1 text-muted-foreground">
                          Jobs without catalog item
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <Button variant="ghost" size="icon" class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground" aria-label="About Jobs without catalog item">
                                <Info class="size-3" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" align="start">Metadata index jobs with no matching catalog entry.</TooltipContent>
                          </Tooltip>
                        </dt>
                        <dd class="font-medium tabular-nums text-foreground">{{ runtimeQuery.data.value.metadata_lifecycle.metadata_jobs_without_matching_assets }}</dd>
                      </div>
                    </template>
                    <div v-else class="py-2">
                      <dt class="text-xs text-muted-foreground">Lifecycle data unavailable</dt>
                    </div>
                  </dl>
                </template>
              </template>
              <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-40 w-full rounded-lg" />
              <p v-else class="mt-4 text-sm text-muted-foreground">Metadata extraction diagnostics unavailable.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Image cache -->
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

      <!-- ═══════════════════════════════════════════
           RECENT JOBS
      ════════════════════════════════════════════ -->
      <section aria-labelledby="jobs-heading">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 id="jobs-heading" class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Recent jobs
            </h2>
            <p class="mt-0.5 text-sm text-foreground">
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
                  size="icon"
                  aria-label="Refresh recent jobs"
                  :disabled="jobsQuery.isFetching.value"
                  @click="jobsQuery.refetch()"
                >
                  <RefreshCw class="size-3.5" :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top" align="end" class="max-w-[220px]">
                Reload recent file catalog, metadata, and image cache jobs.
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
        <div class="rounded-xl border border-border bg-card px-5">
          <JobList v-if="jobsQuery.data.value?.length" :jobs="jobsQuery.data.value" show-library />
          <Skeleton v-else-if="jobsQuery.isPending.value" class="my-5 h-24 w-full rounded-lg" />
          <p v-else class="py-5 text-sm text-muted-foreground">No jobs recorded yet.</p>
        </div>
      </section>
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
.mp-main {
  background-color: var(--background);
}
</style>
