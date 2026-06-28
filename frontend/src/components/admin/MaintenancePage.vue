<script setup lang="ts">
import { ref, computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import {
  Activity,
  AlertTriangle,
  Bug,
  FileWarning,
  Info,
  Loader2,
  RefreshCw,
  ScanLine,
  Trash2,
  Wrench,
} from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { queryKeys } from "@/query/keys";
import { fetchJobs, fetchLibraries, fetchGeneratedImagesStatus } from "@/services/api";
import { useGeneratedImagesGlobalMutations } from "@/composables/admin/useGeneratedImagesGlobalMutations";
import { useFileHealthQuery, useFileHealthMutation } from "@/composables/admin/useFileHealthQuery";
import { useMaintenanceRuntimeQuery } from "@/composables/admin/useMaintenanceRuntimeQuery";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import GeneratedImagesClearDialog from "./dialogs/GeneratedImagesClearDialog.vue";
import GeneratedImagesRebuildDialog from "./dialogs/GeneratedImagesRebuildDialog.vue";

const rebuildOpen = ref(false);
const clearOpen = ref(false);
const { rebuildMutation, clearMutation } = useGeneratedImagesGlobalMutations();

const jobsQuery = useQuery({
  queryKey: queryKeys.jobs(),
  queryFn: fetchJobs,
});

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
  { key: "missing_source_files" as const, label: "Missing source files" },
  { key: "generated_image_missing" as const, label: "Generated image missing" },
  { key: "metadata_mismatch" as const, label: "Metadata mismatch" },
  { key: "orphaned_work_item" as const, label: "Orphaned work item" },
  { key: "generated_image_job_mismatch" as const, label: "Generated image job mismatch" },
] as const;

const repairKeys = [
  { key: "repaired" as const, label: "Repaired" },
  { key: "requeued" as const, label: "Requeued" },
  { key: "failed" as const, label: "Marked failed" },
  { key: "unchanged" as const, label: "Skipped / unchanged" },
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
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="maintenance-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium text-muted-foreground">Administration</p>
          <h2 id="maintenance-heading" class="text-2xl font-semibold tracking-tight">Maintenance</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            File health checks, repair tracking, and imported-data diagnostics.
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" :disabled="rebuildMutation.isPending.value" @click="rebuildOpen = true">
            <RefreshCw /> Rebuild
          </Button>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="destructive" :disabled="clearMutation.isPending.value" @click="clearOpen = true">
                <Trash2 /> Clear
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Clears imported catalog data, extracted metadata, jobs, and generated previews while keeping libraries and
              import paths.
            </TooltipContent>
          </Tooltip>
        </div>
      </header>

      <div class="grid gap-4 md:grid-cols-2">
        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center gap-3">
            <FileWarning class="size-5 text-muted-foreground" />
            <h3 class="font-semibold">File issues</h3>
          </div>
          <div class="mt-4 space-y-3">
            <dl class="grid gap-3 text-sm">
              <div v-for="item in fileIssueKeys" :key="item.key" class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">{{ item.label }}</dt>
                <dd class="font-medium">{{ fileHealthQuery.data.value?.run?.issues[item.key] ?? "—" }}</dd>
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
        </section>

        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center gap-3">
            <ScanLine class="size-5 text-muted-foreground" />
            <h3 class="font-semibold">Check files</h3>
          </div>
          <p class="mt-4 text-sm text-muted-foreground">
            Verify cross-table consistency and storage integrity across all registered libraries.
          </p>
          <div class="mt-4">
            <Button
              variant="outline"
              :disabled="fileHealthMutation.isPending.value"
              @click="fileHealthMutation.mutateAsync()"
            >
              <Loader2 v-if="fileHealthMutation.isPending.value" class="animate-spin" />
              <Bug v-else /> Run checks
            </Button>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">Checks verify cross-table consistency and storage integrity.</p>
        </section>
      </div>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center gap-3">
          <Wrench class="size-5 text-muted-foreground" />
          <h3 class="font-semibold">Repair results</h3>
        </div>
        <div class="mt-4 grid gap-4 text-sm sm:grid-cols-4">
          <div v-for="item in repairKeys" :key="item.key">
            <p class="text-xs text-muted-foreground">{{ item.label }}</p>
            <p class="text-xl font-semibold">{{ fileHealthQuery.data.value?.run?.repairs[item.key] ?? "—" }}</p>
          </div>
        </div>
      </section>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">Thumbnails &amp; previews</h3>
          <Button variant="ghost" size="icon" aria-label="Refresh summary" @click="globalSummaryQuery.refetch()">
            <RefreshCw />
          </Button>
        </div>
        <div v-if="globalSummaryQuery.data.value" class="mt-4">
          <dl class="grid gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Ready files</dt>
              <dd class="font-medium">{{ totalReady ?? "\u2014" }}</dd>
            </div>
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Expected files</dt>
              <dd class="font-medium">{{ totalExpected ?? "\u2014" }}</dd>
            </div>
          </dl>
        </div>
        <Skeleton v-else-if="globalSummaryQuery.isPending.value" class="mt-4 h-16 w-full" />
        <p v-else class="mt-4 text-sm text-muted-foreground">No data available.</p>
      </section>

      <div class="grid gap-4 md:grid-cols-2">
        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center gap-3">
            <Activity class="size-5 text-muted-foreground" />
            <h3 class="font-semibold">Catalogs</h3>
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
                <dt class="text-muted-foreground">Catalog workers</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.catalog_worker_count }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Catalog active jobs</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.catalog_active_jobs }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Catalog queue depth</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.catalog_queue_depth }}</dd>
              </div>
              <Separator />
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Metadata workers</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.metadata_worker_count }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Metadata active jobs</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.metadata_active_jobs }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Metadata queue depth</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.metadata_queue_depth }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Metadata staged queue depth</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.global_runtime.metadata_staged_queue_depth }}</dd>
              </div>
            </dl>
          </div>
          <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-48 w-full" />
          <p v-else class="mt-4 text-sm text-muted-foreground">Runtime diagnostics unavailable.</p>
        </section>

        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center gap-3">
            <AlertTriangle class="size-5 text-muted-foreground" />
            <h3 class="font-semibold">Metadata jobs</h3>
          </div>
          <div v-if="runtimeQuery.data.value?.metadata_lifecycle" class="mt-4 space-y-3">
            <dl class="grid gap-3 text-sm">
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Queued</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.metadata_lifecycle.queued_metadata_jobs }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Running</dt>
                <dd class="font-medium">{{ runtimeQuery.data.value.metadata_lifecycle.running_metadata_jobs }}</dd>
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
                    <TooltipContent side="top" align="start">Metadata jobs that already failed.</TooltipContent>
                  </Tooltip>
                </dt>
                <dd
                  class="font-medium"
                  :class="runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs > 0 ? 'text-destructive' : ''"
                >
                  {{ runtimeQuery.data.value.metadata_lifecycle.failed_metadata_jobs }}
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
                <dd class="font-medium" :class="needsRefreshCount > 0 ? 'text-amber-600' : ''">
                  {{ needsRefreshCount }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Can be repaired</dt>
                <dd
                  class="font-medium"
                  :class="
                    runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets > 0 ? 'text-amber-600' : ''
                  "
                >
                  {{ runtimeQuery.data.value.metadata_lifecycle.repairable_metadata_assets }}
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
                <dd class="font-medium">
                  {{ runtimeQuery.data.value.metadata_lifecycle.metadata_jobs_without_matching_assets }}
                </dd>
              </div>
            </dl>
          </div>
          <Skeleton v-else-if="runtimeQuery.isPending.value" class="mt-4 h-40 w-full" />
          <p v-else class="mt-4 text-sm text-muted-foreground">Metadata jobs diagnostics unavailable.</p>
        </section>
      </div>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">Active jobs</h3>
          <Button variant="ghost" size="icon" aria-label="Refresh jobs" @click="jobsQuery.refetch()">
            <RefreshCw />
          </Button>
        </div>
        <div v-if="jobsQuery.data.value?.length" class="mt-4 divide-y">
          <div
            v-for="job in jobsQuery.data.value"
            :key="job.id"
            class="grid gap-2 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto]"
          >
            <div>
              <p class="font-medium capitalize">
                {{ job.type.replaceAll("_", " ") }} <span class="text-muted-foreground">#{{ job.id }}</span>
              </p>
              <p v-if="job.message || job.error" :class="job.error ? 'text-destructive' : 'text-muted-foreground'">
                {{ job.error || job.message }}
              </p>
            </div>
            <span :class="job.state === 'failed' ? 'text-destructive' : 'text-muted-foreground'" class="capitalize">{{
              job.state
            }}</span>
          </div>
        </div>
        <Skeleton v-else-if="jobsQuery.isPending.value" class="mt-4 h-24 w-full" />
        <p v-else class="mt-4 text-sm text-muted-foreground">No active jobs.</p>
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
