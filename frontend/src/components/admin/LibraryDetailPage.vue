<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import {
  AlertTriangle,
  ArrowLeft,
  CircleCheck,
  CircleX,
  Images,
  Pencil,
  RefreshCw,
  Trash2,
  ImageIcon,
  Info,
} from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import CopyButton from "@/components/ui/CopyButton.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
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
import { useGalleryStore } from "@/stores/gallery";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import { formatBytes, formatPercent } from "@/utils/format";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
import { STATUS_CONTRACT_ERROR_MESSAGE } from "@/lib/catalog/contractGuard";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { MetadataState, ScanState, UnifiedStatus } from "@/lib/catalog/status";
import JobList from "./JobList.vue";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import LibraryStatusBadge from "./LibraryStatusBadge.vue";
import LibraryEditDialog from "./dialogs/LibraryEditDialog.vue";
import LibraryDeleteConfirmDialog from "./dialogs/LibraryDeleteConfirmDialog.vue";

const props = defineProps<{ id: number }>();
const RECENT_JOB_LIMIT = 8;
const router = useRouter();
const galleryStore = useGalleryStore();
const libraryId = computed(() => (Number.isFinite(props.id) && props.id > 0 ? props.id : null));
const libraryQuery = useLibraryQuery(libraryId);
const statusQuery = useCatalogStatusQuery(libraryId);
const statsQuery = useLibraryStatsQuery(libraryId);
const jobsQuery = useLibraryJobsQuery(libraryId, RECENT_JOB_LIMIT);
const librariesQuery = useLibrariesQuery();
const { scanMutation, unregisterMutation } = useLibraryMutations();
useLibraryEvents();
const generatedImagesQuery = useGeneratedImagesStatusQuery(libraryId);
const { warmMutation } = useGeneratedImagesMutations(libraryId);

const editOpen = ref(false);
const deleteOpen = ref(false);
const healthDetailsOpen = ref(false);
const library = computed(() => libraryQuery.data.value ?? null);
const status = computed<UnifiedStatus | null>(() => statusQuery.data.value?.status ?? null);
const busy = computed(() => scanMutation.isPending.value);
const statusContractError = computed(() => Boolean(statusQuery.contractError.value));
const statusPresentation = computed(() => getCatalogStatusPresentation(status.value?.summary_state ?? null));
const libraryFolderLabel = computed(() => {
  const count = library.value?.import_paths.length ?? 0;
  return count === 1 ? "Library folder" : "Library folders";
});

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

const metadataDisplayStateLabel = computed(() =>
  status.value?.metadata.state === "complete" ? "Ready" : metadataStateLabel.value,
);

const metadataReadyLabel = computed(() => {
  const metadata = status.value?.metadata;
  if (!metadata || metadata.total_assets === null) return metadataDisplayStateLabel.value;

  return `${metadataDisplayStateLabel.value} · ${formatAssetCount(metadata.ready_assets ?? 0)}/${formatAssetCount(
    metadata.total_assets,
  )}`;
});

const showStatusProgress = computed(() => {
  const currentStatus = status.value;
  if (!currentStatus) return false;
  if (currentStatus.scan.state === "queued" || currentStatus.scan.state === "scanning") return true;
  if (currentStatus.metadata.state === "queued" || currentStatus.metadata.state === "indexing") return true;
  return currentStatus.metadata.state !== "complete" && currentStatus.metadata.progress_percent !== 100;
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
const hasHealthIssues = computed(() => (status.value?.issue_count ?? 0) > 0);
const healthSeverity = computed<"healthy" | "warning" | "error">(() => {
  const currentStatus = status.value;
  if (!currentStatus || currentStatus.availability.state === "unavailable" || currentStatus.summary_state === "error") {
    return "error";
  }
  return hasHealthIssues.value ? "warning" : "healthy";
});
const healthIssueLabel = computed(() => {
  const count = status.value?.issue_count ?? 0;
  return `${formatAssetCount(count)} ${count === 1 ? "issue needs" : "issues need"} attention`;
});
const healthTitle = computed(() => {
  if (healthSeverity.value === "healthy") return "Healthy";
  if (healthSeverity.value === "warning") return "Warning";
  return "Error";
});
const healthMessage = computed(() => {
  if (healthSeverity.value === "healthy") return "No issues found";
  if (healthSeverity.value === "error") return "Library unavailable";
  return healthIssueLabel.value;
});

const thumbnails = computed(() => generatedImagesQuery.data.value ?? null);
const thumbnailReady = computed(() => thumbnails.value?.ready_derivatives ?? 0);
const thumbnailExpected = computed(() => thumbnails.value?.expected_derivatives ?? 0);
const thumbnailMissing = computed(() => Math.max(0, thumbnailExpected.value - thumbnailReady.value));
const thumbnailCoverageRatio = computed(() => {
  if (!thumbnailExpected.value) return 0;
  return thumbnailReady.value / thumbnailExpected.value;
});
const thumbnailCoverageLabel = computed(() => formatPercent(thumbnailCoverageRatio.value));
const thumbnailSummaryLabel = computed(
  () => `${formatAssetCount(thumbnailReady.value)}/${formatAssetCount(thumbnailExpected.value)} cached`,
);
const hasUnavailableFiles = computed(() => (statsQuery.data.value?.offline_assets ?? 0) > 0);

async function useInGallery() {
  if (library.value && galleryStore.setActiveLibrary(library.value)) await router.push("/");
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
            <OverflowTooltip
              as="p"
              :text="library.import_paths[0]?.path ?? library.root_path"
              class="mt-1 font-mono text-xs text-muted-foreground"
              align="start"
            >
              {{ library.import_paths[0]?.path ?? library.root_path }}
            </OverflowTooltip>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" @click="useInGallery"> <Images /> Open gallery </Button>
            <Button variant="outline" :disabled="busy" @click="scanMutation.mutate({ id: library.id })">
              <RefreshCw /> Update library
            </Button>
            <Button variant="outline" @click="editOpen = true"> <Pencil /> Edit </Button>
          </div>
        </header>

        <div
          v-if="statusContractError"
          class="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
          role="status"
        >
          {{ STATUS_CONTRACT_ERROR_MESSAGE }}
        </div>

        <Separator />

        <section class="space-y-4">
          <h3 class="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Overview</h3>
          <dl v-if="statsQuery.data.value" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt class="text-sm text-muted-foreground">Photos</dt>
              <dd class="mt-1 text-2xl font-semibold">{{ formatAssetCount(statsQuery.data.value.photos) }}</dd>
            </div>
            <div>
              <dt class="text-sm text-muted-foreground">Videos</dt>
              <dd class="mt-1 text-2xl font-semibold">{{ formatAssetCount(statsQuery.data.value.videos) }}</dd>
            </div>
            <div>
              <dt class="text-sm text-muted-foreground">Storage</dt>
              <dd class="mt-1 text-2xl font-semibold">{{ formatBytes(statsQuery.data.value.usage_bytes) }}</dd>
            </div>
            <div>
              <dt class="flex items-center gap-1 text-sm text-muted-foreground">
                Files
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="-my-1 size-5 text-muted-foreground hover:text-foreground"
                      aria-label="About file availability"
                    >
                      <Info class="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="start" class="max-w-[260px]">
                    <p>Available: indexed images/videos currently available on disk.</p>
                    <p class="mt-1">
                      Unavailable: cataloged files not available in the latest scan or under unavailable import paths.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </dt>
              <dd class="mt-1 text-lg font-semibold">
                {{ formatAssetCount(statsQuery.data.value.active_assets) }} available
                <span v-if="hasUnavailableFiles">
                  · {{ formatAssetCount(statsQuery.data.value.offline_assets) }} unavailable
                </span>
              </dd>
            </div>
          </dl>
          <Skeleton v-else class="h-24 w-full" />
        </section>

        <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
          <section class="rounded-md border bg-background p-5">
            <div class="space-y-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Status</h3>
                  <p class="mt-1 text-sm text-muted-foreground">
                    Availability, update progress, and metadata readiness.
                  </p>
                </div>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Refresh status"
                      :disabled="statusQuery.isFetching.value"
                      @click="statusQuery.refetch()"
                    >
                      <RefreshCw :class="statusQuery.isFetching.value ? 'animate-spin' : ''" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="end" class="max-w-[220px]">
                    Reload this library's availability, update progress, and metadata state.
                  </TooltipContent>
                </Tooltip>
              </div>

              <p class="text-lg font-semibold">{{ statusPresentation.label }}</p>
              <div
                v-if="status"
                class="rounded-md border p-3"
                :class="{
                  'border-success/20 bg-success-bg': healthSeverity === 'healthy',
                  'border-warning/30 bg-warning-bg': healthSeverity === 'warning',
                  'border-destructive/30 bg-destructive/10': healthSeverity === 'error',
                }"
              >
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="flex min-w-0 gap-3">
                    <CircleCheck
                      v-if="healthSeverity === 'healthy'"
                      class="mt-0.5 size-5 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <AlertTriangle
                      v-else-if="healthSeverity === 'warning'"
                      class="mt-0.5 size-5 shrink-0 text-warning"
                      aria-hidden="true"
                    />
                    <CircleX v-else class="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />
                    <div class="min-w-0">
                      <p class="font-medium">{{ healthTitle }}</p>
                      <p class="text-sm text-muted-foreground">{{ healthMessage }}</p>
                    </div>
                  </div>
                  <Button
                    v-if="healthSeverity === 'warning'"
                    variant="outline"
                    size="sm"
                    class="shrink-0"
                    @click="healthDetailsOpen = !healthDetailsOpen"
                  >
                    {{ healthDetailsOpen ? "Hide details" : "Review" }}
                  </Button>
                  <Button
                    v-else-if="healthSeverity === 'error'"
                    variant="outline"
                    size="sm"
                    class="shrink-0"
                    :disabled="busy"
                    @click="scanMutation.mutate({ id: library.id })"
                  >
                    Fix now
                  </Button>
                </div>

                <div v-if="healthSeverity === 'warning' && healthDetailsOpen" class="mt-3 border-t pt-3">
                  <div class="grid gap-3 text-sm sm:grid-cols-3">
                    <div v-for="issue in issueBreakdown" :key="issue.label">
                      <p class="text-xs text-muted-foreground">{{ issue.label }}</p>
                      <p class="text-lg font-semibold" :class="issue.count > 0 ? 'text-destructive' : ''">
                        {{ issue.count }}
                      </p>
                    </div>
                  </div>
                  <div v-if="latestIssue" class="mt-3 rounded-md bg-background/70 p-3 text-sm">
                    <p class="font-medium">{{ latestIssue.message }}</p>
                    <p v-if="latestIssue.path" class="mt-1 truncate font-mono text-xs text-muted-foreground">
                      {{ latestIssue.path }}
                    </p>
                  </div>
                </div>
              </div>
              <dl class="grid gap-3 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Availability</dt>
                  <dd class="text-right font-medium">
                    {{ availabilityLabel }}
                    <span v-if="status" class="text-muted-foreground">
                      · {{ status.availability.available_paths }}/{{ status.availability.total_paths }} folders
                    </span>
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">File update</dt>
                  <dd class="text-right font-medium">
                    {{ scanStateLabel }}
                    <span v-if="scanProgressLabel" class="text-muted-foreground"> · {{ scanProgressLabel }}</span>
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-muted-foreground">Metadata</dt>
                  <dd class="text-right font-medium">{{ metadataReadyLabel }}</dd>
                </div>
              </dl>
              <LibraryProgressBar v-if="showStatusProgress" :status="status" />
            </div>
          </section>

          <section class="rounded-md border bg-background p-5">
            <div class="space-y-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Thumbnails</h3>
                  <p class="mt-1 text-sm text-muted-foreground">Cached previews used for faster browsing.</p>
                </div>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Refresh thumbnails cache"
                      :disabled="generatedImagesQuery.isFetching.value"
                      @click="generatedImagesQuery.refetch()"
                    >
                      <RefreshCw :class="generatedImagesQuery.isFetching.value ? 'animate-spin' : ''" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="end" class="max-w-[220px]">
                    Reload cached, required, coverage, and cache usage counts.
                  </TooltipContent>
                </Tooltip>
              </div>

              <template v-if="thumbnails">
                <p class="text-lg font-semibold">{{ thumbnailSummaryLabel }} · {{ thumbnailCoverageLabel }}</p>
                <p class="mt-1 text-sm text-muted-foreground">
                  {{ formatAssetCount(thumbnailMissing) }} thumbnails missing
                </p>
                <div
                  class="h-2 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  :aria-valuenow="Math.round(thumbnailCoverageRatio * 100)"
                >
                  <div class="h-full rounded-full bg-primary" :style="{ width: thumbnailCoverageLabel }" />
                </div>
                <dl class="grid gap-3 text-sm">
                  <div class="flex items-center justify-between gap-3">
                    <dt class="text-muted-foreground">Cache size</dt>
                    <dd class="font-medium">{{ formatBytes(thumbnails.quota_used_bytes) }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-3">
                    <dt class="text-muted-foreground">Limit</dt>
                    <dd class="font-medium">{{ formatBytes(thumbnails.quota_bytes) }}</dd>
                  </div>
                </dl>
                <Button
                  v-if="thumbnailMissing > 0"
                  variant="outline"
                  size="sm"
                  :disabled="warmMutation.isPending.value"
                  @click="warmMutation.mutate()"
                >
                  <ImageIcon data-icon="inline-start" /> Build missing thumbnails
                </Button>
              </template>
              <Skeleton v-else class="h-32 w-full" />
            </div>
          </section>
        </div>

        <Separator />

        <section class="space-y-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Configuration</h3>
              <p class="mt-1 text-sm text-muted-foreground">Read-only summary of this library's source paths.</p>
            </div>
            <Button variant="outline" size="sm" @click="editOpen = true">
              <Pencil data-icon="inline-start" />
              Edit configuration
            </Button>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <section class="rounded-md border bg-background p-4">
              <div class="flex items-center justify-between gap-3">
                <h4 class="text-sm font-semibold">{{ libraryFolderLabel }}</h4>
                <span class="text-xs text-muted-foreground">{{ library.import_paths.length }}</span>
              </div>
              <div class="mt-3 grid gap-2">
                <div
                  v-for="path in library.import_paths"
                  :key="path.id"
                  class="flex min-w-0 items-center gap-2 rounded-md bg-muted/50 px-3 py-2"
                >
                  <OverflowTooltip :text="path.path" class="min-w-0 flex-1 font-mono text-xs" align="start">
                    {{ path.path }}
                  </OverflowTooltip>
                  <CopyButton
                    :text="path.path"
                    copy-id="path"
                    label="Copy path"
                    copied-label="Path copied"
                    variant="ghost"
                    size="icon-sm"
                    class="-mr-1 shrink-0 text-muted-foreground hover:text-foreground"
                  />
                </div>
              </div>
            </section>

            <section class="rounded-md border bg-background p-4">
              <div class="flex items-center justify-between gap-3">
                <h4 class="text-sm font-semibold">Excluded paths</h4>
                <span class="text-xs text-muted-foreground">{{ library.exclusion_patterns.length }}</span>
              </div>
              <div v-if="library.exclusion_patterns.length" class="mt-3 flex flex-wrap gap-2">
                <code
                  v-for="pattern in library.exclusion_patterns"
                  :key="pattern"
                  class="rounded bg-muted px-2 py-1 text-xs"
                >
                  {{ pattern }}
                </code>
              </div>
              <div v-else class="mt-3 rounded-md border border-dashed bg-muted/30 p-3">
                <p class="text-sm text-muted-foreground">None configured</p>
                <Button variant="ghost" size="sm" class="mt-2 h-8 px-2" @click="editOpen = true">Add pattern</Button>
              </div>
            </section>
          </div>
        </section>

        <section class="rounded-md border bg-background p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="font-semibold">Recent job history</h3>
              <p class="mt-1 text-sm text-muted-foreground">Latest {{ RECENT_JOB_LIMIT }} jobs for this library.</p>
            </div>
            <div class="flex items-center gap-2">
              <ButtonLink :to="{ name: 'admin-library-jobs', params: { id: library.id } }" variant="outline" size="sm">
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
                  Reload this library's recent scan, metadata, and generated-image jobs.
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
          <JobList class="mt-4" :jobs="jobsQuery.data.value ?? []" />
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
              <dt class="text-muted-foreground">Catalog updated</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(status?.last_scan_at ?? library.last_scan_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Metadata updated</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(status?.last_index_at ?? null) }}</dd>
            </div>
          </dl>
        </section>

        <section class="space-y-3 rounded-md border border-destructive/30 bg-background p-5">
          <h3 class="text-sm font-semibold uppercase tracking-wide text-destructive">Danger zone</h3>
          <p class="text-sm text-muted-foreground">
            Unregistering removes this library from the catalog. Files are not deleted.
          </p>
          <Button variant="destructive" @click="deleteOpen = true"><Trash2 /> Unregister library</Button>
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
