<script setup lang="ts">
import { ref, computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { FileWarning, ScanLine, Wrench, RefreshCw, Trash2, Bug } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { queryKeys } from "@/query/keys";
import { fetchJobs, fetchLibraries, fetchGeneratedImagesStatus } from "@/services/api";
import { useGeneratedImagesGlobalMutations } from "@/composables/admin/useGeneratedImagesGlobalMutations";
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
    const results = await Promise.all(
      libraries.map((lib) => fetchGeneratedImagesStatus(lib.id)),
    );
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
</script>

<template>
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="maintenance-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium text-muted-foreground">Administration</p>
          <h2 id="maintenance-heading" class="text-2xl font-semibold tracking-tight">Maintenance</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            File health checks, repair tracking, and storage consistency reports.
          </p>
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
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Missing source files</dt>
                <dd class="font-medium">\u2014</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Generated image missing</dt>
                <dd class="font-medium">\u2014</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Metadata mismatch</dt>
                <dd class="font-medium">\u2014</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Orphaned work item</dt>
                <dd class="font-medium">\u2014</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-muted-foreground">Generated image job mismatch</dt>
                <dd class="font-medium">\u2014</dd>
              </div>
            </dl>
            <Separator />
            <div class="flex items-center justify-between text-xs text-muted-foreground">
              <span>Latest run</span>
              <span>\u2014</span>
            </div>
          </div>
          <p class="mt-4 text-sm text-muted-foreground">
            No report history available \u2014 backend health report API not available yet.
          </p>
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
            <Button variant="outline" disabled title="Backend check API not available">
              <Bug /> Run checks
            </Button>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">Automated file checks require a backend health API endpoint.</p>
        </section>
      </div>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center gap-3">
          <Wrench class="size-5 text-muted-foreground" />
          <h3 class="font-semibold">Repair results</h3>
        </div>
        <div class="mt-4 grid gap-4 text-sm sm:grid-cols-4">
          <div>
            <p class="text-xs text-muted-foreground">Repaired</p>
            <p class="text-xl font-semibold">\u2014</p>
          </div>
          <div>
            <p class="text-xs text-muted-foreground">Requeued</p>
            <p class="text-xl font-semibold">\u2014</p>
          </div>
          <div>
            <p class="text-xs text-muted-foreground">Marked failed</p>
            <p class="text-xl font-semibold">\u2014</p>
          </div>
          <div>
            <p class="text-xs text-muted-foreground">Skipped / unchanged</p>
            <p class="text-xl font-semibold">\u2014</p>
          </div>
        </div>
        <p class="mt-4 text-sm text-muted-foreground">No repair history available.</p>
      </section>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">Generated files (all libraries)</h3>
          <Button variant="ghost" size="icon" aria-label="Refresh summary" @click="globalSummaryQuery.refetch()">
            <RefreshCw />
          </Button>
        </div>
        <div v-if="globalSummaryQuery.data.value" class="mt-4">
          <dl class="grid gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Ready</dt>
              <dd class="font-medium">{{ totalReady ?? "\u2014" }}</dd>
            </div>
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Expected</dt>
              <dd class="font-medium">{{ totalExpected ?? "\u2014" }}</dd>
            </div>
          </dl>
        </div>
        <Skeleton v-else-if="globalSummaryQuery.isPending.value" class="mt-4 h-16 w-full" />
        <p v-else class="mt-4 text-sm text-muted-foreground">No data available.</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" size="sm" :disabled="rebuildMutation.isPending.value" @click="rebuildOpen = true">
            <RefreshCw /> Refresh stale (all libraries)
          </Button>
          <Button variant="destructive" size="sm" :disabled="clearMutation.isPending.value" @click="clearOpen = true">
            <Trash2 /> Clear generated files (all libraries)
          </Button>
        </div>
      </section>

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
      scope-label=" across all libraries"
      @confirm="confirmRebuild"
    />
    <GeneratedImagesClearDialog
      v-model:open="clearOpen"
      :pending="clearMutation.isPending.value"
      scope-label=" across all libraries"
      @confirm="confirmClear"
    />
  </main>
</template>
