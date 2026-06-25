<script setup lang="ts">
import { ref, computed } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { FileWarning, ScanLine, Wrench, RefreshCw, Trash2, Bug } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { fetchJobs, clearGeneratedImages, refreshStaleGeneratedImages } from "@/services/api";
import GeneratedImagesClearDialog from "./dialogs/GeneratedImagesClearDialog.vue";
import GeneratedImagesRebuildDialog from "./dialogs/GeneratedImagesRebuildDialog.vue";

const queryClient = useQueryClient();
const toast = useToast();
const rebuildOpen = ref(false);
const clearGeneratedOpen = ref(false);

const rebuildPending = ref(false);
const clearPending = ref(false);
const checkRunning = ref(false);

const jobsQuery = useQuery({
  queryKey: queryKeys.jobs(),
  queryFn: fetchJobs,
});

const generatedStatusesQuery = useQuery({
  queryKey: ["generated-images", "global-summary"],
  queryFn: async () => {
    const libraries = await (await fetch("/api/libraries")).json();
    const statuses = await Promise.all(
      (libraries as Array<{ id: number }>).map((lib) =>
        fetch(`/api/derivatives/status?library_id=${lib.id}`).then((r) => r.json()),
      ),
    );
    return statuses as Array<{
      library_id: number;
      total_assets: number;
      ready_derivatives: number;
      expected_derivatives: number;
    }>;
  },
  enabled: false,
});

const totalReady = computed(() =>
  generatedStatusesQuery.data.value?.reduce((s, r) => s + r.ready_derivatives, 0) ?? null,
);
const totalExpected = computed(() =>
  generatedStatusesQuery.data.value?.reduce((s, r) => s + r.expected_derivatives, 0) ?? null,
);

async function confirmRebuild() {
  rebuildOpen.value = false;
  rebuildPending.value = true;
  try {
    const result = await refreshStaleGeneratedImages();
    toast.success(`Refresh queued for ${result.stale_derivatives} stale items across all libraries`);
    await invalidateDerivativeQueries();
  } catch {
    toast.error("Could not refresh generated images");
  } finally {
    rebuildPending.value = false;
  }
}

async function confirmClearGenerated() {
  clearGeneratedOpen.value = false;
  clearPending.value = true;
  try {
    await clearGeneratedImages();
    toast.success("Generated files cleared across all libraries. Source images are not affected.");
    await invalidateDerivativeQueries();
  } catch {
    toast.error("Could not clear generated images");
  } finally {
    clearPending.value = false;
  }
}

async function invalidateDerivativeQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.statusRoot() }),
    queryClient.invalidateQueries({ queryKey: ["generated-images"] }),
  ]);
}

async function refreshStatuses() {
  checkRunning.value = true;
  try {
    await invalidateDerivativeQueries();
    toast.success("Status refreshed");
  } catch {
    toast.error("Could not refresh status");
  } finally {
    checkRunning.value = false;
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
          <p class="mt-4 text-sm text-muted-foreground">No report history available — backend health report API not available yet.</p>
        </section>

        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center gap-3">
            <ScanLine class="size-5 text-muted-foreground" />
            <h3 class="font-semibold">Check files</h3>
          </div>
          <p class="mt-4 text-sm text-muted-foreground">
            Verify cross-table consistency and storage integrity across all registered libraries.
          </p>
          <div class="mt-4 flex flex-wrap gap-2">
            <Button variant="outline" :disabled="true" title="Backend check API not available">
              <Bug /> Run checks
            </Button>
            <Button variant="outline" :disabled="checkRunning" @click="refreshStatuses">
              <RefreshCw v-if="checkRunning" class="animate-spin" />
              <RefreshCw v-else />
              {{ checkRunning ? "Refreshing\u2026" : "Refresh status" }}
            </Button>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">Automated file checks require a backend health API endpoint.</p>
        </section>
      </div>

      <section class="rounded-md border bg-background p-5">
        <div class="flex items-center gap-3">
          <Wrench class="size-5 text-muted-foreground" />
          <h3 class="font-semibold">Generated files (all libraries)</h3>
        </div>
        <div class="mt-4">
          <dl class="grid gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Ready</dt>
              <dd class="font-medium">{{ totalReady != null ? totalReady : "\u2014" }}</dd>
            </div>
            <div class="flex items-center justify-between gap-3">
              <dt class="text-muted-foreground">Expected</dt>
              <dd class="font-medium">{{ totalExpected != null ? totalExpected : "\u2014" }}</dd>
            </div>
          </dl>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" size="sm" :disabled="rebuildPending" @click="rebuildOpen = true">
            <RefreshCw /> Refresh stale (all libraries)
          </Button>
          <Button variant="destructive" size="sm" :disabled="clearPending" @click="clearGeneratedOpen = true">
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
      :pending="rebuildPending"
      @confirm="confirmRebuild"
    />
    <GeneratedImagesClearDialog
      v-model:open="clearGeneratedOpen"
      :pending="clearPending"
      @confirm="confirmClearGenerated"
    />
  </main>
</template>
