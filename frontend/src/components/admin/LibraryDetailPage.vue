<script setup lang="ts">
import { computed, shallowRef } from "vue";
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
import Badge from "@/components/ui/Badge.vue";
import CopyButton from "@/components/ui/CopyButton.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import Separator from "@/components/ui/Separator.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
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
import IndexStatusBadge from "@/components/IndexStatusBadge.vue";
import JobList from "./JobList.vue";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import LibraryStatusBadge from "./LibraryStatusBadge.vue";
import LibraryEditDialog from "./dialogs/LibraryEditDialog.vue";
import LibraryDeleteConfirmDialog from "./dialogs/LibraryDeleteConfirmDialog.vue";
import OfflineFilesDialog from "./dialogs/OfflineFilesDialog.vue";

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

const editOpen = shallowRef(false);
const deleteOpen = shallowRef(false);
const offlineFilesOpen = shallowRef(false);
const healthDetailsOpen = shallowRef(false);
const library = computed(() => libraryQuery.data.value ?? null);
const status = computed<UnifiedStatus | null>(() => statusQuery.data.value?.status ?? null);
const busy = computed(() => scanMutation.isPending.value);
const statusContractError = computed(() => Boolean(statusQuery.contractError.value));
const statusLoadError = computed(() => Boolean(statusQuery.isError?.value));
const sourceFolderCountLabel = computed(() => {
  const count = library.value?.import_paths.length ?? 0;
  return `${formatAssetCount(count)} ${count === 1 ? "folder" : "folders"}`;
});
const exclusionPatternCountLabel = computed(() => {
  const count = library.value?.exclusion_patterns.length ?? 0;
  return `${formatAssetCount(count)} ${count === 1 ? "pattern" : "patterns"}`;
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
const availabilityDisplayLabel = computed(() =>
  status.value?.availability.state === "available" ? "Available" : availabilityLabel.value,
);
const availabilityDetailLabel = computed(() => {
  const availability = status.value?.availability;
  if (!availability) return "—";
  return `${availability.available_paths}/${availability.total_paths} folders`;
});

const scanStateLabel = computed(() => {
  const state = status.value?.scan.state;
  if (!state) return "Unknown";
  return scanStateLabels[state];
});
const scanDisplayStateLabel = computed(() =>
  status.value?.scan.state === "complete" ? "Ready" : scanStateLabel.value,
);
const scanDetailLabel = computed(() => {
  const scan = status.value?.scan;
  if (!scan) return "—";
  if (scanProgressLabel.value) return scanProgressLabel.value;
  if (scan.state === "never") return "Run update to scan files";
  if (scan.state === "complete") return "File catalog is current";
  return scanStateLabel.value;
});

const metadataStateLabel = computed(() => {
  const state = status.value?.metadata.state;
  if (!state) return "Unknown";
  return metadataStateLabels[state];
});

const metadataDisplayStateLabel = computed(() =>
  status.value?.scan.state === "never"
    ? "Not measured"
    : status.value?.metadata.state === "complete"
      ? "Ready"
      : metadataStateLabel.value,
);

const metadataDetailLabel = computed(() => {
  if (status.value?.scan.state === "never") return "Run update to discover assets";
  const metadata = status.value?.metadata;
  if (!metadata || metadata.total_assets === null) return metadataStateLabel.value;
  return `${formatAssetCount(metadata.ready_assets ?? 0)}/${formatAssetCount(metadata.total_assets)} assets`;
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
const hasUnavailableFiles = computed(() => (statsQuery.data.value?.offline_assets ?? 0) > 0);
const hasCatalogIssues = computed(() => (status.value?.issue_count ?? 0) > 0);
const hasHealthIssues = computed(() => hasCatalogIssues.value || hasUnavailableFiles.value);
const statusPresentation = computed(() => getCatalogStatusPresentation(status.value?.summary_state ?? null));
const healthSeverity = computed<"healthy" | "warning" | "error">(() => {
  const currentStatus = status.value;
  if (!currentStatus || currentStatus.availability.state === "unavailable" || currentStatus.summary_state === "error") {
    return "error";
  }
  if (currentStatus.summary_state !== "ready") return "warning";
  return hasHealthIssues.value ? "warning" : "healthy";
});
const healthIssueLabel = computed(() => {
  const count = status.value?.issue_count ?? 0;
  return `${formatAssetCount(count)} ${count === 1 ? "issue needs" : "issues need"} attention`;
});
const healthMessage = computed(() => {
  if (healthSeverity.value === "healthy") return "All systems available";
  if (healthSeverity.value === "error") return "Library unavailable";
  if (hasCatalogIssues.value) return healthIssueLabel.value;
  if (hasUnavailableFiles.value) {
    return `${formatAssetCount(statsQuery.data.value?.offline_assets ?? 0)} cataloged files unavailable`;
  }
  if (!hasHealthIssues.value) return statusPresentation.value.meaning;
  return healthIssueLabel.value;
});
const canUpdateFromStatus = computed(() => {
  const summary = status.value?.summary_state;
  return summary === "needs_scan" || summary === "needs_update";
});
type StatusTileTone = "healthy" | "warning" | "error";
const statusTileTone: Record<StatusTileTone, string> = {
  healthy: "text-success",
  warning: "text-warning",
  error: "text-destructive",
};
const statusTiles = computed<
  Array<{ key: string; label: string; value: string; detail: string; tone: StatusTileTone; help?: string }>
>(() => {
  const currentStatus = status.value;
  const availabilityTone: StatusTileTone =
    !currentStatus || currentStatus.availability.state === "unavailable"
      ? "error"
      : hasUnavailableFiles.value
        ? "warning"
        : "healthy";
  const scanTone: StatusTileTone =
    !currentStatus || currentStatus.scan.state === "failed"
      ? "error"
      : currentStatus.scan.state === "complete"
        ? "healthy"
        : "warning";
  const metadataTone: StatusTileTone =
    !currentStatus || currentStatus.metadata.state === "failed"
      ? "error"
      : currentStatus.scan.state === "never" || currentStatus.metadata.state !== "complete"
        ? "warning"
        : "healthy";

  return [
    {
      key: "availability",
      label: "Source folders",
      value: hasUnavailableFiles.value ? "Available with issues" : availabilityDisplayLabel.value,
      detail: hasUnavailableFiles.value
        ? `${availabilityDetailLabel.value} · ${formatAssetCount(statsQuery.data.value?.offline_assets ?? 0)} files unavailable`
        : availabilityDetailLabel.value,
      tone: availabilityTone,
      help: hasUnavailableFiles.value
        ? `${formatAssetCount(statsQuery.data.value?.offline_assets ?? 0)} previously cataloged files are unavailable. They may have been moved, deleted, excluded by the library configuration, or located under an unavailable path. Restore the files or adjust the configuration, then choose Check again.`
        : undefined,
    },
    {
      key: "scan",
      label: "File update",
      value: scanDisplayStateLabel.value,
      detail: scanDetailLabel.value,
      tone: scanTone,
    },
    {
      key: "metadata",
      label: "Metadata",
      value: metadataDisplayStateLabel.value,
      detail: metadataDetailLabel.value,
      tone: metadataTone,
    },
  ];
});

const thumbnails = computed(() => generatedImagesQuery.data.value ?? null);

function variantLabel(kind: "thumbnail" | "preview", maxLongEdge: number): string {
  return `${kind === "thumbnail" ? "Thumbnail" : "Preview"} · ${maxLongEdge}px`;
}

function variantHelp(kind: "thumbnail" | "preview", maxLongEdge: number): string {
  if (kind === "thumbnail" && maxLongEdge === 128) {
    return "Small thumbnail used in prompt results and metadata tables.";
  }
  if (kind === "thumbnail" && maxLongEdge === 512) {
    return "Gallery thumbnail used in grids and as the preferred visual fingerprint source.";
  }
  if (kind === "preview" && maxLongEdge === 1440) {
    return "Previews are larger cached images used when opening an image in the lightbox or detail view.";
  }
  return `${kind === "thumbnail" ? "Thumbnail" : "Preview"} cache generated at ${maxLongEdge}px.`;
}

const derivativeCoverageRows = computed(() => {
  const currentStatus = thumbnails.value;
  if (!currentStatus) return [];

  if (currentStatus.variants?.length) {
    return currentStatus.variants.map((status) => ({
      key: `${status.kind}:${status.variant}`,
      kind: status.kind,
      label: variantLabel(status.kind, status.max_long_edge),
      help: variantHelp(status.kind, status.max_long_edge),
      ready: status.ready_derivatives,
      expected: status.expected_derivatives,
      ratio: status.expected_derivatives > 0 ? status.ready_derivatives / status.expected_derivatives : 0,
      queued: status.queued_derivatives,
      running: status.running_derivatives,
      failed: status.failed_derivatives,
      deferred: status.deferred_derivatives,
      countUnit: "images",
    }));
  }

  if (!currentStatus.by_kind) return [];

  return (["thumbnail", "preview"] as const)
    .map((kind) => {
      const status = currentStatus.by_kind?.[kind];
      if (!status) return null;
      const ratio = status.expected_derivatives > 0 ? status.ready_derivatives / status.expected_derivatives : 0;
      return {
        key: kind,
        kind,
        label: kind === "thumbnail" ? "Thumbnails" : "Previews",
        help:
          kind === "thumbnail"
            ? "Thumbnails are small cached images used in gallery grids and lists."
            : "Previews are larger cached images used when opening an image in the lightbox or detail view.",
        ready: status.ready_derivatives,
        expected: status.expected_derivatives,
        ratio,
        queued: status.queued_derivatives,
        running: status.running_derivatives,
        failed: status.failed_derivatives,
        deferred: status.deferred_derivatives,
        countUnit: "files",
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);
});
const thumbnailReady = computed(() => thumbnails.value?.ready_derivatives ?? 0);
const thumbnailExpected = computed(() => thumbnails.value?.expected_derivatives ?? 0);
const thumbnailMissing = computed(() => thumbnails.value?.actionable_missing_derivatives ?? 0);
const informationalGap = computed(() => {
  if (!thumbnails.value) return 0;
  return Math.max(0, (thumbnails.value.expected_derivatives ?? 0) - (thumbnails.value.ready_derivatives ?? 0));
});
const showGenerateMissing = computed(() => {
  if (!thumbnails.value) return false;
  if (thumbnails.value.policy === "on_demand") return informationalGap.value > 0;
  return thumbnailMissing.value > 0;
});
const generateMissingLabel = computed(() => {
  const count = thumbnailMissing.value || informationalGap.value;
  return count > 0 ? `Prepare ${formatAssetCount(count)} image cache files now` : "Prepare image cache";
});
const derivativeWorkerUnavailable = computed(
  () =>
    thumbnails.value !== null &&
    thumbnails.value.policy === "warm" &&
    (thumbnailMissing.value > 0 || thumbnails.value.queued_jobs > 0 || thumbnails.value.running_jobs > 0) &&
    !thumbnails.value.worker_healthy,
);
const hasDerivativeExpectation = computed(() => thumbnailExpected.value > 0);
const derivativeCoverageRatio = computed(() => {
  if (!thumbnailExpected.value) return 0;
  return thumbnailReady.value / thumbnailExpected.value;
});
const derivativeCoverageLabel = computed(() =>
  hasDerivativeExpectation.value ? formatPercent(derivativeCoverageRatio.value) : "Not measured",
);
const derivativeCacheState = computed(() => {
  const currentStatus = thumbnails.value;
  if (!currentStatus || !hasDerivativeExpectation.value) {
    return {
      label: "Cache status",
      value: "Unknown",
      detail: "Run a scan to measure image cache coverage",
      tone: "text-muted-foreground",
    };
  }
  if (currentStatus.deferred_derivatives > 0) {
    return {
      label: "Cache status",
      value: "Storage limited",
      detail: `${formatAssetCount(currentStatus.deferred_derivatives)} waiting for capacity`,
      tone: "text-warning",
    };
  }
  if (currentStatus.terminal_failed_derivatives > 0 || derivativeWorkerUnavailable.value) {
    return {
      label: "Cache status",
      value: "Needs attention",
      detail: "Some image cache jobs cannot progress",
      tone: "text-destructive",
    };
  }
  if (currentStatus.queued_jobs > 0 || currentStatus.running_jobs > 0) {
    return {
      label: "Cache status",
      value: "Preparing",
      detail: "Image cache is being prepared",
      tone: "text-warning",
    };
  }
  if (informationalGap.value === 0 && thumbnailReady.value >= thumbnailExpected.value) {
    return {
      label: "Cache status",
      value: "Ready",
      detail: "All thumbnails and previews are cached",
      tone: "text-success",
    };
  }
  if (currentStatus.policy === "on_demand") {
    return {
      label: "Cache status",
      value: "On demand",
      detail: `${formatAssetCount(informationalGap.value)} image cache files will be created on first view`,
      tone: "text-muted-foreground",
    };
  }
  return {
    label: "Cache status",
    value: `${formatAssetCount(thumbnailMissing.value)} missing`,
    detail: "Image cache preparation is needed",
    tone: "text-warning",
  };
});
const statsLoadError = computed(() => Boolean(statsQuery.isError?.value));
const generatedImagesLoadError = computed(() => Boolean(generatedImagesQuery.isError?.value));

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
  <main class="h-full overflow-y-auto p-4 text-foreground sm:p-6" aria-labelledby="library-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <ButtonLink to="/admin/libraries" variant="ghost" class="-ml-3"><ArrowLeft /> Libraries</ButtonLink>

      <div
        v-if="!libraryId || libraryQuery.isError.value"
        class="grid min-h-72 place-items-center rounded-lg border border-dashed border-border bg-card p-8 text-center shadow-sm"
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
              <h2 id="library-heading" class="truncate text-xl font-semibold tracking-normal text-foreground">
                {{ library.name }}
              </h2>
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
            <Button
              variant="outline"
              class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
              @click="useInGallery"
            >
              <Images data-icon="inline-start" /> Open gallery
            </Button>
            <Button
              variant="outline"
              class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
              :disabled="busy"
              @click="scanMutation.mutate({ id: library.id })"
            >
              <RefreshCw data-icon="inline-start" /> Update library
            </Button>
            <Button
              variant="outline"
              class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
              @click="editOpen = true"
            >
              <Pencil data-icon="inline-start" /> Edit
            </Button>
          </div>
        </header>

        <div
          v-if="statusContractError"
          class="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm"
          role="status"
        >
          {{ STATUS_CONTRACT_ERROR_MESSAGE }}
        </div>

        <Separator />

        <section class="space-y-4">
          <h3 class="text-sm font-semibold text-foreground">Overview</h3>
          <dl
            v-if="statsQuery.data.value"
            class="grid divide-y divide-border rounded-md border border-border bg-card sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4"
          >
            <div class="p-4">
              <dt class="text-sm text-muted-foreground">Images</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                {{ formatAssetCount(statsQuery.data.value.photos) }}
              </dd>
            </div>
            <div class="p-4">
              <dt class="text-sm text-muted-foreground">Videos</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                {{ formatAssetCount(statsQuery.data.value.videos) }}
              </dd>
            </div>
            <div class="p-4">
              <dt class="text-sm text-muted-foreground">Source storage</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                {{ formatBytes(statsQuery.data.value.usage_bytes) }}
              </dd>
            </div>
            <div class="p-4">
              <dt class="flex items-center gap-1 text-sm text-muted-foreground">
                Files
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="-my-1 size-8 text-muted-foreground hover:text-foreground"
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
              <dd
                class="mt-1 text-base font-semibold tabular-nums"
                :class="hasUnavailableFiles ? 'text-warning' : 'text-foreground'"
              >
                {{ formatAssetCount(statsQuery.data.value.active_assets) }} available
                <span v-if="hasUnavailableFiles">
                  · {{ formatAssetCount(statsQuery.data.value.offline_assets) }} unavailable
                </span>
              </dd>
            </div>
          </dl>
          <div
            v-else-if="statsLoadError"
            class="rounded-md border border-destructive/30 bg-destructive/5 p-4"
            role="alert"
          >
            <p class="text-sm font-medium">Overview data could not be loaded.</p>
            <Button variant="outline" size="sm" class="mt-3" @click="statsQuery.refetch?.()">Try again</Button>
          </div>
          <Skeleton v-else class="h-24 w-full" />
        </section>

        <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
          <Card class="gap-0 py-0">
            <CardContent class="p-5">
              <div class="space-y-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="flex flex-wrap items-center gap-2">
                      <h3 class="text-sm font-semibold text-foreground">Status</h3>
                      <IndexStatusBadge v-if="status" :presentation="statusPresentation" />
                    </div>
                    <p class="mt-1 text-sm text-muted-foreground">
                      Availability, update progress, and metadata readiness.
                    </p>
                  </div>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        class="size-11"
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

                <div
                  v-if="statusLoadError"
                  class="rounded-md border border-destructive/30 bg-destructive/5 p-4"
                  role="alert"
                >
                  <p class="text-sm font-medium">Status could not be loaded.</p>
                  <Button variant="outline" size="sm" class="mt-3" @click="statusQuery.refetch?.()">Try again</Button>
                </div>
                <div
                  v-else-if="status"
                  class="rounded-md border border-border p-3"
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
                      <div class="flex min-w-0 flex-wrap items-center gap-2">
                        <p class="font-medium">{{ healthMessage }}</p>
                        <Button
                          v-if="canUpdateFromStatus"
                          variant="outline"
                          size="sm"
                          class="h-7 px-2 text-xs"
                          :disabled="busy"
                          @click="scanMutation.mutate({ id: library.id })"
                        >
                          <RefreshCw data-icon="inline-start" /> Update
                        </Button>
                      </div>
                    </div>
                    <Button
                      v-if="healthSeverity === 'warning' && hasCatalogIssues"
                      variant="outline"
                      size="sm"
                      class="shrink-0"
                      @click="healthDetailsOpen = !healthDetailsOpen"
                    >
                      {{ healthDetailsOpen ? "Hide details" : "Review" }}
                    </Button>
                    <div v-else-if="hasUnavailableFiles" class="flex shrink-0 flex-wrap gap-2">
                      <Button variant="outline" size="sm" @click="offlineFilesOpen = true">View files</Button>
                      <Button
                        variant="outline"
                        size="sm"
                        :disabled="busy"
                        @click="scanMutation.mutate({ id: library.id })"
                      >
                        <RefreshCw :class="busy ? 'animate-spin' : ''" data-icon="inline-start" />
                        {{ busy ? "Checking..." : "Check again" }}
                      </Button>
                    </div>
                    <Button
                      v-else-if="healthSeverity === 'error'"
                      variant="outline"
                      size="sm"
                      class="shrink-0"
                      :disabled="busy"
                      @click="scanMutation.mutate({ id: library.id })"
                    >
                      <RefreshCw :class="busy ? 'animate-spin' : ''" data-icon="inline-start" />
                      {{ busy ? "Checking..." : "Check again" }}
                    </Button>
                  </div>

                  <div
                    v-if="healthSeverity === 'warning' && hasCatalogIssues && healthDetailsOpen"
                    class="mt-3 border-t pt-3"
                  >
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
                <div v-if="status" class="grid gap-3 text-sm sm:grid-cols-3">
                  <div
                    v-for="tile in statusTiles"
                    :key="tile.key"
                    class="rounded-md border border-border bg-muted/60 p-3"
                  >
                    <p class="text-xs font-medium text-muted-foreground">{{ tile.label }}</p>
                    <p class="mt-1 flex items-center gap-1.5 font-semibold" :class="statusTileTone[tile.tone]">
                      <CircleCheck v-if="tile.tone === 'healthy'" class="size-4 shrink-0" aria-hidden="true" />
                      <AlertTriangle v-else-if="tile.tone === 'warning'" class="size-4 shrink-0" aria-hidden="true" />
                      <CircleX v-else class="size-4 shrink-0" aria-hidden="true" />
                      <span>{{ tile.value }}</span>
                      <Tooltip v-if="tile.help">
                        <TooltipTrigger as-child>
                          <Button
                            variant="ghost"
                            size="icon"
                            class="-my-1 size-6 text-muted-foreground hover:text-foreground"
                            aria-label="About available with issues"
                          >
                            <Info class="size-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top" align="start" class="max-w-[320px] font-normal">
                          {{ tile.help }}
                        </TooltipContent>
                      </Tooltip>
                    </p>
                    <p class="mt-1 text-xs text-muted-foreground">{{ tile.detail }}</p>
                  </div>
                </div>
                <LibraryProgressBar v-if="showStatusProgress" :status="status" />
              </div>
            </CardContent>
          </Card>

          <Card class="gap-0 py-0">
            <CardContent class="p-5">
              <div class="space-y-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="flex flex-wrap items-center gap-2">
                      <h3 class="text-sm font-semibold text-foreground">Generated image cache</h3>
                      <Badge
                        v-if="thumbnails?.policy === 'on_demand'"
                        variant="outline"
                        class="text-[11px] font-medium text-muted-foreground"
                      >
                        On demand
                      </Badge>
                    </div>
                    <p class="mt-1 text-sm text-muted-foreground">
                      Cached thumbnails and previews used while browsing.
                    </p>
                    <p v-if="thumbnails" class="mt-1 text-xs text-muted-foreground">
                      {{ formatAssetCount(thumbnails.total_assets) }} images ·
                      {{ formatAssetCount(thumbnails.expected_derivatives) }} generated cache files
                    </p>
                  </div>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        class="size-11"
                        aria-label="Refresh image cache"
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
                  <div
                    v-if="derivativeCoverageRows.length"
                    class="divide-y divide-border rounded-md border border-border bg-muted/60"
                  >
                    <div v-for="row in derivativeCoverageRows" :key="row.key" class="space-y-2 p-3">
                      <div class="flex items-center justify-between gap-3">
                        <div class="flex min-w-0 items-center gap-2.5">
                          <ImageIcon class="size-4 shrink-0 text-foreground/70" aria-hidden="true" />
                          <p class="font-medium text-foreground">{{ row.label }}</p>
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <Button
                                variant="ghost"
                                size="icon"
                                class="-my-1 size-6 text-muted-foreground hover:text-foreground"
                                :aria-label="`About ${row.label.toLowerCase()}`"
                              >
                                <Info class="size-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" align="start" class="max-w-[280px] font-normal">
                              {{ row.help }}
                            </TooltipContent>
                          </Tooltip>
                        </div>
                        <p class="shrink-0 text-sm font-semibold tabular-nums text-foreground">
                          {{ formatAssetCount(row.ready) }}/{{ formatAssetCount(row.expected) }} {{ row.countUnit }}
                          cached
                        </p>
                      </div>
                      <Progress
                        :model-value="Math.round(row.ratio * 100)"
                        class="h-2 bg-muted"
                        :indicator-class="row.ratio >= 1 ? 'bg-success' : 'bg-warning'"
                      />
                      <dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                        <div v-if="row.queued > 0" class="flex items-center justify-between gap-2 sm:block">
                          <dt class="text-muted-foreground">Queued</dt>
                          <dd class="font-medium tabular-nums text-foreground">{{ formatAssetCount(row.queued) }}</dd>
                        </div>
                        <div v-if="row.running > 0" class="flex items-center justify-between gap-2 sm:block">
                          <dt class="text-muted-foreground">Running</dt>
                          <dd class="font-medium tabular-nums text-foreground">{{ formatAssetCount(row.running) }}</dd>
                        </div>
                        <div v-if="row.failed > 0" class="flex items-center justify-between gap-2 sm:block">
                          <dt class="text-muted-foreground">Failed</dt>
                          <dd class="font-medium tabular-nums text-foreground">{{ formatAssetCount(row.failed) }}</dd>
                        </div>
                        <div v-if="row.deferred > 0" class="flex items-center justify-between gap-2 sm:block">
                          <dt class="text-muted-foreground">Deferred</dt>
                          <dd class="font-medium tabular-nums text-foreground">{{ formatAssetCount(row.deferred) }}</dd>
                        </div>
                      </dl>
                    </div>
                  </div>
                  <div v-else class="rounded-md border border-border bg-muted/60 p-3">
                    <p class="font-semibold text-foreground">
                      {{ formatAssetCount(thumbnailReady) }}/{{ formatAssetCount(thumbnailExpected) }} cached
                    </p>
                    <p class="mt-1 text-sm text-muted-foreground">{{ derivativeCoverageLabel }}</p>
                  </div>
                  <p v-if="showGenerateMissing" class="text-sm text-muted-foreground">
                    {{ formatAssetCount(thumbnailMissing || informationalGap) }} image cache files missing
                  </p>
                  <dl class="grid gap-3 text-sm sm:grid-cols-3">
                    <div class="rounded-md border border-border bg-muted/60 p-3">
                      <dt class="text-xs font-medium text-muted-foreground">This library</dt>
                      <dd class="mt-1 font-semibold text-foreground">
                        {{ formatBytes(thumbnails.library_used_bytes) }}
                      </dd>
                    </div>
                    <div class="rounded-md border border-border bg-muted/60 p-3">
                      <dt class="text-xs font-medium text-muted-foreground">All libraries</dt>
                      <dd class="mt-1 font-semibold text-foreground">
                        {{ formatBytes(thumbnails.quota_used_bytes) }} / {{ formatBytes(thumbnails.quota_bytes) }}
                      </dd>
                    </div>
                    <div class="rounded-md border border-border bg-muted/60 p-3">
                      <dt class="text-xs font-medium text-muted-foreground">{{ derivativeCacheState.label }}</dt>
                      <dd class="mt-1 font-semibold" :class="derivativeCacheState.tone">
                        {{ derivativeCacheState.value }}
                      </dd>
                      <p class="mt-1 text-xs text-muted-foreground">{{ derivativeCacheState.detail }}</p>
                    </div>
                  </dl>
                  <div
                    v-if="derivativeWorkerUnavailable"
                    class="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
                    role="alert"
                  >
                    <AlertTriangle class="mt-0.5 size-4 shrink-0" />
                    <div class="space-y-2">
                      <p>No image cache worker is available. New image cache jobs cannot progress.</p>
                      <ButtonLink to="/admin/maintenance" variant="outline" size="sm">Open maintenance</ButtonLink>
                    </div>
                  </div>
                  <p
                    v-if="thumbnails.queued_jobs || thumbnails.running_jobs || thumbnails.failed_jobs"
                    class="text-sm text-muted-foreground"
                  >
                    {{ thumbnails.queued_jobs }} queued · {{ thumbnails.running_jobs }} running ·
                    {{ thumbnails.failed_jobs }} failed
                  </p>
                  <Button
                    v-if="showGenerateMissing"
                    variant="outline"
                    size="sm"
                    :disabled="warmMutation.isPending.value"
                    @click="warmMutation.mutate()"
                  >
                    <RefreshCw v-if="warmMutation.isPending.value" class="animate-spin" data-icon="inline-start" />
                    <ImageIcon v-else data-icon="inline-start" />
                    {{ warmMutation.isPending.value ? "Preparing image cache..." : generateMissingLabel }}
                  </Button>
                </template>
                <div
                  v-else-if="generatedImagesLoadError"
                  class="rounded-md border border-destructive/30 bg-destructive/5 p-4"
                  role="alert"
                >
                  <p class="text-sm font-medium">Image cache coverage could not be loaded.</p>
                  <Button variant="outline" size="sm" class="mt-3" @click="generatedImagesQuery.refetch?.()">
                    Try again
                  </Button>
                </div>
                <Skeleton v-else-if="generatedImagesQuery.isPending.value" class="h-32 w-full" />
                <div v-else class="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                  Image cache coverage has not been measured yet.
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Separator />

        <section class="space-y-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="text-sm font-semibold text-foreground">Configuration</h3>
              <p class="mt-1 text-sm text-muted-foreground">
                Source folders and exclusion patterns used when updating this library.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
              @click="editOpen = true"
            >
              <Pencil data-icon="inline-start" />
              Edit configuration
            </Button>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <Card class="gap-0 py-0">
              <CardContent class="p-4">
                <div class="flex items-center justify-between gap-3">
                  <h4 class="text-sm font-semibold">Source folders</h4>
                  <span class="text-xs text-muted-foreground">{{ sourceFolderCountLabel }}</span>
                </div>
                <div class="mt-3 grid gap-2">
                  <div
                    v-for="path in library.import_paths"
                    :key="path.id"
                    class="flex min-w-0 items-center gap-2 rounded-md border border-border bg-muted/60 px-3 py-2"
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
                      size="icon-lg"
                      class="-mr-1 shrink-0 text-muted-foreground hover:text-foreground"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card class="gap-0 py-0">
              <CardContent class="p-4">
                <div class="flex items-center justify-between gap-3">
                  <h4 class="text-sm font-semibold">Exclusion patterns</h4>
                  <span class="text-xs text-muted-foreground">{{ exclusionPatternCountLabel }}</span>
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
                <div v-else class="mt-3 space-y-3">
                  <div>
                    <p class="text-sm font-medium text-foreground">No exclusion patterns</p>
                    <p class="mt-1 text-sm text-muted-foreground">
                      All files under the source folders are included during library updates.
                    </p>
                  </div>
                  <Button variant="outline" size="sm" class="border-border bg-card" @click="editOpen = true">
                    Add exclusion pattern
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 class="font-semibold text-foreground">Recent job history</h3>
                <p class="mt-1 text-sm text-muted-foreground">Latest {{ RECENT_JOB_LIMIT }} jobs for this library.</p>
              </div>
              <div class="flex items-center gap-2">
                <ButtonLink
                  :to="{ name: 'admin-library-jobs', params: { id: library.id } }"
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
                      <RefreshCw :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="end" class="max-w-[220px]">
                    Reload this library's recent scan, metadata, and image cache jobs.
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>
            <JobList class="mt-4" :jobs="jobsQuery.data.value ?? []" />
          </CardContent>
        </Card>

        <Card class="gap-0 py-0">
          <CardContent class="p-5">
            <h3 class="font-semibold text-foreground">File catalog lifecycle</h3>
            <Separator class="my-4" />
            <dl class="grid gap-4 text-sm sm:grid-cols-4">
              <div>
                <dt class="text-muted-foreground">Created</dt>
                <dd class="mt-1 font-medium text-foreground">{{ formatLibraryTimestamp(library.created_at) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">Updated</dt>
                <dd class="mt-1 font-medium text-foreground">{{ formatLibraryTimestamp(library.updated_at) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">File catalog updated</dt>
                <dd class="mt-1 font-medium text-foreground">
                  {{ formatLibraryTimestamp(status?.last_scan_at ?? library.last_scan_at) }}
                </dd>
              </div>
              <div>
                <dt class="text-muted-foreground">Metadata updated</dt>
                <dd class="mt-1 font-medium text-foreground">
                  {{ formatLibraryTimestamp(status?.last_index_at ?? null) }}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card class="gap-0 border-destructive/30 py-0">
          <CardContent class="flex flex-col items-start gap-3 p-5">
            <h3 class="text-sm font-semibold uppercase tracking-wide text-destructive">Danger zone</h3>
            <p class="text-sm text-muted-foreground">
              Unregistering removes this library from the catalog. Files are not deleted.
            </p>
            <Button variant="destructive" @click="deleteOpen = true"><Trash2 /> Unregister library</Button>
          </CardContent>
        </Card>
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
    <OfflineFilesDialog
      v-if="library"
      v-model:open="offlineFilesOpen"
      :library-id="library.id"
      :expected-count="statsQuery.data.value?.offline_assets ?? 0"
    />
  </main>
</template>
