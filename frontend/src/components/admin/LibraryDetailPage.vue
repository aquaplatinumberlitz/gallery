<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { AlertTriangle, ArrowLeft, Copy, Images, Pencil, RefreshCw, Trash2, ImageIcon } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Separator from "@/components/ui/Separator.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import { useLibrariesQuery } from "@/composables/admin/useLibrariesQuery";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useLibraryJobsQuery } from "@/composables/admin/useLibraryJobsQuery";
import { useLibraryMutations } from "@/composables/admin/useLibraryMutations";
import { useCatalogStatusQuery } from "@/composables/useCatalogStatusQuery";
import { useLibraryQuery } from "@/composables/admin/useLibraryQuery";
import { useLibraryStatsQuery } from "@/composables/admin/useLibraryStatsQuery";
import { useGeneratedImagesStatusQuery } from "@/composables/admin/useGeneratedImagesStatusQuery";
import { useGeneratedImagesMutations } from "@/composables/admin/useGeneratedImagesMutations";
import { useClipboard } from "@/composables/useClipboard";
import { useGalleryStore } from "@/stores/gallery";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import { formatBytes, formatPercent } from "@/utils/format";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
import { STATUS_CONTRACT_ERROR_MESSAGE } from "@/lib/catalog/contractGuard";
import type { MetadataState, ScanState, UnifiedStatus } from "@/lib/catalog/status";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import LibraryStatusBadge from "./LibraryStatusBadge.vue";
import LibraryEditDialog from "./dialogs/LibraryEditDialog.vue";
import LibraryDeleteConfirmDialog from "./dialogs/LibraryDeleteConfirmDialog.vue";

const props = defineProps<{ id: number }>();
const router = useRouter();
const galleryStore = useGalleryStore();
const { copyText } = useClipboard();
const libraryId = computed(() => (Number.isFinite(props.id) && props.id > 0 ? props.id : null));
const libraryQuery = useLibraryQuery(libraryId);
const statusQuery = useCatalogStatusQuery(libraryId);
const statsQuery = useLibraryStatsQuery(libraryId);
const jobsQuery = useLibraryJobsQuery(libraryId);
const librariesQuery = useLibrariesQuery();
const { scanMutation, unregisterMutation } = useLibraryMutations();
useLibraryEvents();
const generatedImagesQuery = useGeneratedImagesStatusQuery(libraryId);
const { warmMutation } = useGeneratedImagesMutations(libraryId);

const editOpen = ref(false);
const deleteOpen = ref(false);
const library = computed(() => libraryQuery.data.value ?? null);
const status = computed<UnifiedStatus | null>(() => statusQuery.data.value?.status ?? null);
const busy = computed(() => scanMutation.isPending.value);
const statusContractError = computed(() => Boolean(statusQuery.contractError.value));

const scanStateLabels: Record<ScanState, string> = {
  never: "Never updated",
  queued: "Queued",
  scanning: "Updating",
  complete: "Complete",
  failed: "Failed",
};

const metadataStateLabels: Record<MetadataState, string> = {
  disabled: "Disabled",
  queued: "Queued",
  indexing: "Updating metadata",
  needs_update: "Needs update",
  complete: "Complete",
  failed: "Failed",
};

const availabilityLabel = computed(() => {
  const state = status.value?.availability.state;
  if (!state) return "Unknown";
  return state.charAt(0).toUpperCase() + state.slice(1);
});

const scanStateLabel = computed(() => {
  const state = status.value?.scan.state;
  if (!state) return "Unknown";
  return scanStateLabels[state];
});

const metadataStateLabel = computed(() => {
  const state = status.value?.metadata.state;
  if (!state) return "Unknown";
  return metadataStateLabels[state];
});

const scanProgressLabel = computed(() => {
  const scan = status.value?.scan;
  if (!scan) return "";
  if (scan.state === "queued" || scan.state === "scanning") {
    const completed = scan.completed_units ?? 0;
    if (scan.total_units !== null) {
      return `${formatAssetCount(completed)} / ${formatAssetCount(scan.total_units)} units`;
    }
    return `${formatAssetCount(completed)} units`;
  }
  return "";
});

const issueBreakdown = computed(() => {
  const issues = status.value?.issues;
  if (!issues) return [];
  return [
    { label: "Availability", count: issues.availability },
    { label: "File update", count: issues.scan },
    { label: "Metadata", count: issues.metadata },
  ];
});

const latestIssue = computed(() => status.value?.latest_issue ?? null);

async function useInGallery() {
  if (library.value && galleryStore.setActiveLibrary(library.value)) await router.push("/");
}

async function copyPath(path: string) {
  await copyText(path, "path");
}

async function confirmUnregister() {
  if (!library.value) return;
  try {
    await unregisterMutation.mutateAsync(library.value.id);
    deleteOpen.value = false;
    await router.push("/admin/libraries");
  } catch {
    // Error is already handled by the mutation's onError handler (toast)
  }
}

function jobProgress(current: number, total: number | null): string {
  return total && total > 0 ? `${formatAssetCount(current)} / ${formatAssetCount(total)}` : formatAssetCount(current);
}

function estimatedAssets(): number | undefined {
  return status.value?.metadata.total_assets ?? library.value?.asset_count;
}
</script>

<template>
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="library-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <ButtonLink to="/admin/libraries" variant="ghost" class="-ml-3"><ArrowLeft /> Libraries</ButtonLink>

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

      <div v-else-if="libraryQuery.isPending.value" class="space-y-4">
        <Skeleton class="h-16 w-full" />
        <div class="grid gap-4 md:grid-cols-2"><Skeleton v-for="item in 6" :key="item" class="h-40 w-full" /></div>
      </div>

      <template v-else-if="library">
        <header class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-3">
              <h2 id="library-heading" class="truncate text-2xl font-semibold tracking-tight">{{ library.name }}</h2>
              <LibraryStatusBadge :status="status" />
            </div>
            <p class="mt-1 truncate font-mono text-xs text-muted-foreground" :title="library.import_paths[0]?.path">
              {{ library.import_paths[0]?.path ?? library.root_path }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" @click="useInGallery"> <Images /> Use in gallery </Button>
            <Button variant="outline" @click="editOpen = true"> <Pencil /> Edit </Button>
            <Button variant="outline" :disabled="busy" @click="scanMutation.mutate({ id: library.id })">
              <RefreshCw /> Update library
            </Button>
            <Button variant="destructive" @click="deleteOpen = true"> <Trash2 /> Unregister </Button>
          </div>
        </header>

        <div
          v-if="statusContractError"
          class="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
          role="status"
        >
          {{ STATUS_CONTRACT_ERROR_MESSAGE }}
        </div>

        <section
          v-if="latestIssue && !statusContractError"
          class="rounded-md border border-destructive/40 bg-destructive/10 p-4"
        >
          <div class="flex gap-3">
            <AlertTriangle class="mt-0.5 size-5 text-destructive" />
            <div>
              <h3 class="font-medium text-destructive">{{ latestIssue.source }} issue</h3>
              <p class="mt-1 whitespace-pre-wrap text-sm">{{ latestIssue.message }}</p>
              <p v-if="latestIssue.path" class="mt-1 truncate font-mono text-xs text-muted-foreground">
                {{ latestIssue.path }}
              </p>
            </div>
          </div>
        </section>

        <div class="grid gap-4 md:grid-cols-2">
          <section class="rounded-md border bg-background p-5">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold">Status and progress</h3>
              <Button variant="ghost" size="icon" aria-label="Refresh status" @click="statusQuery.refetch()">
                <RefreshCw />
              </Button>
            </div>
            <div class="mt-5 space-y-4">
              <dl class="grid gap-3 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Summary</dt>
                  <dd class="font-medium">{{ getCatalogStatusPresentation(status?.summary_state ?? null).label }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Availability</dt>
                  <dd class="font-medium">
                    {{ availabilityLabel }}
                    <span v-if="status" class="text-muted-foreground">
                      ({{ status.availability.available_paths }}/{{ status.availability.total_paths }} paths)
                    </span>
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">File update</dt>
                  <dd class="font-medium">
                    {{ scanStateLabel }}
                    <span v-if="scanProgressLabel" class="text-muted-foreground"> · {{ scanProgressLabel }}</span>
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Metadata</dt>
                  <dd class="font-medium">
                    {{ metadataStateLabel }}
                    <span v-if="status && status.metadata.total_assets !== null" class="text-muted-foreground">
                      · {{ formatAssetCount(status.metadata.ready_assets ?? 0) }} /
                      {{ formatAssetCount(status.metadata.total_assets) }} ready
                    </span>
                  </dd>
                </div>
              </dl>
              <LibraryProgressBar :status="status" />
            </div>
          </section>

          <section class="rounded-md border bg-background p-5">
            <h3 class="font-semibold">Issues</h3>
            <div v-if="status" class="mt-4 space-y-3">
              <div class="grid grid-cols-3 gap-4 text-sm">
                <div v-for="issue in issueBreakdown" :key="issue.label">
                  <p class="text-xs text-muted-foreground">{{ issue.label }}</p>
                  <p class="text-xl font-semibold" :class="issue.count > 0 ? 'text-destructive' : ''">
                    {{ issue.count }}
                  </p>
                </div>
              </div>
              <p class="text-xs text-muted-foreground">
                Total issues: <span class="font-medium text-foreground">{{ status.issue_count }}</span>
              </p>
            </div>
            <Skeleton v-else class="mt-4 h-24 w-full" />
          </section>

          <section class="rounded-md border bg-background p-5">
            <h3 class="font-semibold">Statistics</h3>
            <div v-if="statsQuery.data.value" class="mt-4 grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-muted-foreground">Photos</p>
                <p class="text-xl font-semibold">{{ formatAssetCount(statsQuery.data.value.photos) }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Videos</p>
                <p class="text-xl font-semibold">{{ formatAssetCount(statsQuery.data.value.videos) }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Active / Offline</p>
                <p class="text-lg font-semibold">
                  {{ formatAssetCount(statsQuery.data.value.active_assets) }} /
                  {{ formatAssetCount(statsQuery.data.value.offline_assets) }}
                </p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Usage</p>
                <p class="text-lg font-semibold">{{ formatBytes(statsQuery.data.value.usage_bytes) }}</p>
              </div>
            </div>
            <Skeleton v-else class="mt-4 h-24 w-full" />
          </section>

          <section class="rounded-md border bg-background p-5">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">Generated images</h3>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Refresh generated images"
                @click="generatedImagesQuery.refetch()"
              >
                <RefreshCw />
              </Button>
            </div>
            <div v-if="generatedImagesQuery.data.value" class="mt-4 space-y-4">
              <dl class="grid gap-3 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Ready</dt>
                  <dd class="font-medium">{{ formatAssetCount(generatedImagesQuery.data.value.ready_derivatives) }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Expected</dt>
                  <dd class="font-medium">
                    {{ formatAssetCount(generatedImagesQuery.data.value.expected_derivatives) }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Progress</dt>
                  <dd class="font-medium">
                    {{
                      formatPercent(
                        generatedImagesQuery.data.value.expected_derivatives > 0
                          ? generatedImagesQuery.data.value.ready_derivatives /
                              generatedImagesQuery.data.value.expected_derivatives
                          : 0,
                      )
                    }}
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Cache usage</dt>
                  <dd class="font-medium">{{ formatBytes(generatedImagesQuery.data.value.quota_used_bytes) }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Cache limit</dt>
                  <dd class="font-medium">{{ formatBytes(generatedImagesQuery.data.value.quota_bytes) }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Cache used</dt>
                  <dd class="font-medium">{{ formatPercent(generatedImagesQuery.data.value.quota_utilization) }}</dd>
                </div>
              </dl>
              <Separator />
              <div class="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  :disabled="warmMutation.isPending.value"
                  @click="warmMutation.mutate()"
                >
                  <ImageIcon /> Generate missing
                </Button>
              </div>
            </div>
            <Skeleton v-else class="mt-4 h-24 w-full" />
          </section>

          <section class="rounded-md border bg-background p-5">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">Import paths</h3>
              <Button variant="ghost" size="sm" @click="editOpen = true">Edit</Button>
            </div>
            <div class="mt-4 space-y-3">
              <div
                v-for="path in library.import_paths"
                :key="path.id"
                class="flex items-center gap-2 rounded-md border p-3"
              >
                <span class="min-w-0 flex-1 truncate font-mono text-xs" :title="path.path">{{ path.path }}</span
                ><Button variant="ghost" size="icon" aria-label="Copy import path" @click="copyPath(path.path)">
                  <Copy />
                </Button>
              </div>
            </div>
          </section>

          <section class="rounded-md border bg-background p-5">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">Exclusion patterns</h3>
              <Button variant="ghost" size="sm" @click="editOpen = true">Edit</Button>
            </div>
            <div v-if="library.exclusion_patterns.length" class="mt-4 flex flex-wrap gap-2">
              <code
                v-for="pattern in library.exclusion_patterns"
                :key="pattern"
                class="rounded bg-muted px-2 py-1 text-xs"
                >{{ pattern }}</code
              >
            </div>
            <p v-else class="mt-4 text-sm text-muted-foreground">No exclusion patterns.</p>
          </section>
        </div>

        <section class="rounded-md border bg-background p-5">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold">Recent job history</h3>
            <Button variant="ghost" size="icon" aria-label="Refresh jobs" @click="jobsQuery.refetch()">
              <RefreshCw />
            </Button>
          </div>
          <div v-if="jobsQuery.data.value?.length" class="mt-4 divide-y">
            <div
              v-for="job in jobsQuery.data.value"
              :key="job.id"
              class="grid gap-2 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto]"
            >
              <div>
                <p class="font-medium capitalize">
                  {{ job.type.replaceAll("_", " ") }} <span class="text-muted-foreground">#{{ job.id }}</span>
                </p>
                <p v-if="job.message || job.error" :class="job.error ? 'text-destructive' : 'text-muted-foreground'">
                  {{ job.error || job.message }}
                </p>
              </div>
              <span class="capitalize" :class="job.state === 'failed' ? 'text-destructive' : 'text-muted-foreground'">{{
                job.state
              }}</span
              ><span class="text-muted-foreground"
                >{{ jobProgress(job.progress_current, job.progress_total) }} ·
                {{ formatLibraryTimestamp(job.updated_at) }}</span
              >
            </div>
          </div>
          <p v-else class="mt-4 text-sm text-muted-foreground">No jobs recorded yet.</p>
        </section>

        <section class="rounded-md border bg-background p-5">
          <h3 class="font-semibold">Catalog lifecycle</h3>
          <Separator class="my-4" />
          <dl class="grid gap-4 text-sm sm:grid-cols-4">
            <div>
              <dt class="text-muted-foreground">Created</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(library.created_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Updated</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(library.updated_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Last update</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(status?.last_scan_at ?? library.last_scan_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Last index</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(status?.last_index_at ?? null) }}</dd>
            </div>
          </dl>
        </section>
      </template>
    </div>

    <LibraryEditDialog
      v-model:open="editOpen"
      :library="library"
      :libraries="librariesQuery.data.value ?? []"
      @updated="editOpen = false"
    />
    <LibraryDeleteConfirmDialog
      v-model:open="deleteOpen"
      :library="library"
      :estimated-assets="estimatedAssets()"
      :pending="unregisterMutation.isPending.value"
      @confirm="confirmUnregister"
    />
  </main>
</template>
