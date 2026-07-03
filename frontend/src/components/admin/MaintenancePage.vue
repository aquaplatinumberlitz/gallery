<script setup lang="ts">
import { ref, computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import {
  ArrowRight,
  Bug,
  File,
  FileChartColumn,
  FileWarning,
  HardDrive,
  Info,
  Loader2,
  RefreshCw,
  ScanLine,
  Trash2,
  Wrench,
} from "lucide-vue-next";
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
import GeneratedImagesClearDialog from "./dialogs/GeneratedImagesClearDialog.vue";
import GeneratedImagesRebuildDialog from "./dialogs/GeneratedImagesRebuildDialog.vue";

const RECENT_JOB_LIMIT = 8;
const rebuildOpen = ref(false);
const clearOpen = ref(false);
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

const fileIssueKeys = [
  {
    key: "missing_source_files" as const,
    label: "Missing source files",
    description: "Queued or running metadata jobs whose source file no longer exists on disk.",
  },
  {
    key: "generated_image_missing" as const,
    label: "Missing thumbnail file",
    description: "Thumbnail cache records marked ready while the cached file is missing.",
  },
  {
    key: "metadata_mismatch" as const,
    label: "Metadata mismatch",
    description: "Cataloged assets marked done but missing a matching extracted metadata row.",
  },
  {
    key: "orphaned_work_item" as const,
    label: "Orphaned work item",
    description: "Metadata jobs that no longer have a matching catalog asset.",
  },
  {
    key: "generated_image_job_mismatch" as const,
    label: "Thumbnail job mismatch",
    description: "Finished thumbnail jobs whose cache record is not ready.",
  },
] as const;

const repairKeys = [
  {
    key: "repaired" as const,
    label: "Repaired",
    description: "Rows corrected immediately because the expected catalog or cache state could be confirmed.",
  },
  {
    key: "requeued" as const,
    label: "Requeued",
    description: "Work sent back to metadata extraction or thumbnail building.",
  },
  {
    key: "failed" as const,
    label: "Marked failed",
    description: "Work items marked failed because the source asset or generated file could not be found.",
  },
  {
    key: "unchanged" as const,
    label: "Skipped / unchanged",
    description: "Problems that were counted but did not need a state change in this run.",
  },
] as const;

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
  <main
    class="h-full overflow-y-auto rounded-xl bg-card p-4 text-foreground shadow-sm ring-1 ring-border/70 sm:p-6"
    aria-labelledby="maintenance-heading"
  >
    <div class="mx-auto max-w-6xl space-y-6">
      <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Administration</p>
          <h2 id="maintenance-heading" class="mt-1 text-xl font-semibold tracking-normal text-foreground">
            Maintenance
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            File health checks, repair tracking, and imported-data diagnostics.
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            variant="outline"
            class="border-border/80 bg-card text-foreground shadow-sm hover:bg-muted/70"
            :disabled="rebuildMutation.isPending.value"
            @click="rebuildOpen = true"
          >
            <RefreshCw data-icon="inline-start" /> Rebuild
          </Button>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="destructive" :disabled="clearMutation.isPending.value" @click="clearOpen = true">
                <Trash2 /> Clear
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Clears imported catalog data, extracted metadata, jobs, and cached thumbnails while keeping libraries and
              folders.
            </TooltipContent>
          </Tooltip>
        </div>
      </header>

      <Card class="gap-0 py-0">
        <CardContent class="p-4">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="text-sm font-semibold text-foreground">Imported data flow</h3>
              <p class="mt-1 text-sm text-muted-foreground">
                Files are discovered first, then details are extracted, then thumbnails are cached.
              </p>
            </div>
            <ol class="flex flex-wrap items-center gap-2 text-sm" aria-label="Imported data flow">
              <li class="inline-flex items-center gap-1.5 font-medium">
                <File class="size-4 text-muted-foreground" />
                File catalog
              </li>
              <li class="text-muted-foreground" aria-hidden="true">
                <ArrowRight class="size-4" />
              </li>
              <li class="inline-flex items-center gap-1.5 font-medium">
                <FileChartColumn class="size-4 text-muted-foreground" />
                Metadata extraction
              </li>
              <li class="text-muted-foreground" aria-hidden="true">
                <ArrowRight class="size-4" />
              </li>
              <li class="inline-flex items-center gap-1.5 font-medium">
                <HardDrive class="size-4 text-muted-foreground" />
                Thumbnails cache
              </li>
            </ol>
          </div>
        </CardContent>
      </Card>

      <div class="grid gap-4 md:grid-cols-2">
        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <FileWarning class="size-5 text-foreground/70" />
                <h3 class="font-semibold text-foreground">File issues</h3>
              </div>
              <p class="text-sm text-muted-foreground">
                Counts consistency problems found in catalog, metadata, and thumbnail records.
              </p>
            </div>
            <div class="mt-4 space-y-3">
              <dl class="grid gap-3 text-sm">
                <div v-for="item in fileIssueKeys" :key="item.key" class="flex items-center justify-between gap-3">
                  <dt class="flex flex-wrap items-center gap-1 text-muted-foreground">
                    {{ item.label }}
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
                          :aria-label="`About ${item.label}`"
                        >
                          <Info class="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start" class="max-w-[240px]">
                        {{ item.description }}
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-foreground">
                    {{ fileHealthQuery.data.value?.run?.issues[item.key] ?? "—" }}
                  </dd>
                </div>
              </dl>
              <Separator />
              <div class="flex items-center justify-between text-xs text-muted-foreground">
                <span>Latest run</span>
                <span>{{
                  fileHealthQuery.data.value?.run?.finished_at
                    ? new Date(fileHealthQuery.data.value.run.finished_at * 1000).toLocaleString()
                    : "—"
                }}</span>
              </div>
            </div>
            <p v-if="!fileHealthQuery.data.value?.run" class="mt-4 text-sm text-muted-foreground">No run yet.</p>
          </CardContent>
        </Card>

        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <ScanLine class="size-5 text-foreground/70" />
                <h3 class="font-semibold text-foreground">Check files</h3>
              </div>
              <p class="text-sm text-muted-foreground">
                Runs the same backend integrity pass used by the scheduled checker.
              </p>
            </div>
            <p class="mt-4 text-sm text-muted-foreground">
              Verifies source files, extracted metadata, queued work, and thumbnail cache state across all registered
              libraries.
            </p>
            <div class="mt-4">
              <Button
                variant="outline"
                class="border-border/80 bg-card text-foreground shadow-sm hover:bg-muted/70"
                :disabled="fileHealthMutation.isPending.value"
                @click="fileHealthMutation.mutateAsync()"
              >
                <Loader2 v-if="fileHealthMutation.isPending.value" class="animate-spin" />
                <Bug v-else /> Run checks
              </Button>
            </div>
            <p class="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
              May repair confirmed mismatches, requeue stale work, or mark invalid jobs failed.
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="size-4 text-muted-foreground hover:text-foreground -my-1"
                    aria-label="About file checks"
                  >
                    <Info class="size-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" align="start" class="max-w-[260px]">
                  The check persists a summary run and updates repair counters shown below. It does not remove
                  registered libraries or source files.
                </TooltipContent>
              </Tooltip>
            </p>
          </CardContent>
        </Card>
      </div>

      <Card class="gap-0 py-0">
        <CardContent class="p-5">
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <Wrench class="size-5 text-foreground/70" />
              <h3 class="font-semibold text-foreground">Repair results</h3>
            </div>
            <p class="text-sm text-muted-foreground">
              Shows what the latest file-health run changed or left untouched.
            </p>
          </div>
          <div class="mt-4 grid gap-4 text-sm sm:grid-cols-4">
            <div v-for="item in repairKeys" :key="item.key" class="rounded-md bg-muted/40 p-3">
              <p class="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
                {{ item.label }}
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="size-4 text-muted-foreground hover:text-foreground -my-1"
                      :aria-label="`About ${item.label}`"
                    >
                      <Info class="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="start" class="max-w-[240px]">
                    {{ item.description }}
                  </TooltipContent>
                </Tooltip>
              </p>
              <p class="mt-1 text-sm font-semibold tabular-nums text-foreground">
                {{ fileHealthQuery.data.value?.run?.repairs[item.key] ?? "—" }}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card class="gap-0 py-0">
        <CardContent class="p-5">
          <div class="flex items-center justify-between">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <HardDrive class="size-5 text-foreground/70" />
                <h3 class="font-semibold text-foreground">Thumbnails cache</h3>
              </div>
              <p class="text-sm text-muted-foreground">Cached thumbnails and previews used for faster browsing.</p>
            </div>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Refresh thumbnails summary"
                  :disabled="globalSummaryQuery.isFetching.value"
                  @click="globalSummaryQuery.refetch()"
                >
                  <RefreshCw :class="globalSummaryQuery.isFetching.value ? 'animate-spin' : ''" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top" align="end" class="max-w-[220px]">
                Reload cached and required thumbnail cache counts.
              </TooltipContent>
            </Tooltip>
          </div>
          <div v-if="globalSummaryQuery.data.value" class="mt-4">
            <dl class="grid gap-3 text-sm sm:grid-cols-2">
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Cached files</dt>
                <dd class="font-semibold tabular-nums text-foreground">{{ totalReady ?? "\u2014" }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="flex items-center gap-1 text-muted-foreground">
                  Required files
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="size-4 text-muted-foreground hover:text-foreground -my-1"
                        aria-label="About required files"
                      >
                        <Info class="size-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" align="start" class="max-w-[220px]">
                      Total thumbnail and preview files required for cataloged photos.
                    </TooltipContent>
                  </Tooltip>
                </dt>
                <dd class="font-semibold tabular-nums text-foreground">{{ totalExpected ?? "\u2014" }}</dd>
              </div>
            </dl>
          </div>
          <Skeleton v-else-if="globalSummaryQuery.isPending.value" class="mt-4 h-16 w-full" />
          <p v-else class="mt-4 text-sm text-muted-foreground">No data available.</p>
        </CardContent>
      </Card>

      <div class="grid gap-4 md:grid-cols-2">
        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <File class="size-5 text-foreground/70" />
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
                      runtimeQuery.data.value.global_runtime.watcher_healthy ? 'text-green-600' : 'text-destructive'
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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

        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <FileChartColumn class="size-5 text-foreground/70" />
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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
                  <dd class="font-medium tabular-nums" :class="needsRefreshCount > 0 ? 'text-amber-600' : ''">
                    {{ runtimeQuery.data.value.metadata_lifecycle ? needsRefreshCount : "\u2014" }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Can be repaired</dt>
                  <dd
                    class="font-medium tabular-nums"
                    :class="
                      (runtimeQuery.data.value.metadata_lifecycle?.repairable_metadata_assets ?? 0) > 0
                        ? 'text-amber-600'
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
                          size="icon"
                          class="size-4 text-muted-foreground hover:text-foreground -my-1"
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

      <Card class="gap-0 py-0">
        <CardContent class="p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="font-semibold text-foreground">Recent job history</h3>
              <p class="mt-1 text-sm text-muted-foreground">
                Latest {{ RECENT_JOB_LIMIT }} file catalog, metadata, and thumbnail jobs.
              </p>
            </div>
            <div class="flex items-center gap-2">
              <ButtonLink
                :to="{ name: 'admin-jobs' }"
                variant="outline"
                size="sm"
                class="border-border/80 bg-card text-foreground shadow-sm hover:bg-muted/70"
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
                    <RefreshCw :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" align="end" class="max-w-[220px]">
                  Reload recent file catalog, metadata, and thumbnail jobs.
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
