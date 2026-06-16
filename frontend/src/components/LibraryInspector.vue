<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useVueTable,
  type SortingState,
} from "@tanstack/vue-table";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { ArrowLeft, ArrowUpDown, Copy, ExternalLink, MoreHorizontal, Search } from "lucide-vue-next";
import Badge from "@/components/ui/Badge.vue";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Input from "@/components/ui/Input.vue";
import SortSelect from "@/components/SortSelect.vue";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useClipboard } from "@/composables/useClipboard";
import { useIndexStatusQuery } from "@/composables/useIndexStatusQuery";
import { useToast } from "@/composables/useToast";
import { useLibraryInspectorMetadataQuery } from "@/composables/useLibraryInspectorMetadataQuery";
import { useInfiniteLibraryInspectorQuery } from "@/composables/useInfiniteLibraryInspectorQuery";
import { useGalleryStore } from "@/stores/gallery";
import { useLightboxStore } from "@/stores/lightbox";
import { fetchLibraryInspectorMetadata, getThumbnailUrl } from "@/services/api";
import { queryClient } from "@/query";
import { queryKeys } from "@/query/keys";
import { clearScopeRebuildMarker, getScopeRebuildStartedAt } from "@/utils/indexMaintenance";
import { logIndexRebuildDebug } from "@/debug/indexRebuildDebug";
import { logLightboxNavDebug, summarizeLightboxItems } from "@/debug/lightboxNavDebug";
import { hasActiveIndexWork, hasQueuedIndexWork } from "@/utils/indexStatus";
import type {
  FileNode,
  LibraryInspectorMetadataResponse,
  LibraryInspectorResource,
  LibraryInspectorRow,
  SearchScope,
  SortValue,
} from "@/types";

const galleryStore = useGalleryStore();
const lightboxStore = useLightboxStore();
const { copyText } = useClipboard();
const toast = useToast();

const query = computed({
  get: () => galleryStore.metadataInspector.query,
  set: (value: string) => {
    galleryStore.metadataInspector.query = value;
  },
});
const scope = computed<SearchScope>({
  get: () => galleryStore.metadataInspector.scope,
  set: (value) => {
    galleryStore.metadataInspector.scope = value;
  },
});
const currentPath = computed(() => galleryStore.currentPath || "");
const limit = ref(200);
const inspectorSort = computed<SortValue>({
  get: () => galleryStore.metadataInspector.sort,
  set: (value) => {
    galleryStore.metadataInspector.sort = value;
  },
});
const sortValueToTableState = (value: SortValue): SortingState => {
  const [field, order] = value.split("_") as ["date" | "name", "asc" | "desc"];
  return [{ id: field === "name" ? "name" : "mtime", desc: order === "desc" }];
};
const tableStateToSortValue = (id: string, desc: boolean): SortValue | null => {
  if (id === "name") return desc ? "name_desc" : "name_asc";
  if (id === "mtime") return desc ? "date_desc" : "date_asc";
  return null;
};
const sorting = ref<SortingState>(sortValueToTableState(inspectorSort.value));
const modelFilter = computed({
  get: () => galleryStore.metadataInspector.modelFilter,
  set: (value: string) => {
    galleryStore.metadataInspector.modelFilter = value;
  },
});
const promptFilter = computed<"all" | "has_prompt" | "no_prompt">({
  get: () => galleryStore.metadataInspector.promptFilter,
  set: (value) => {
    galleryStore.metadataInspector.promptFilter = value;
  },
});
const selectedPath = computed({
  get: () => galleryStore.metadataInspector.selectedPath,
  set: (value: string) => {
    galleryStore.metadataInspector.selectedPath = value;
  },
});
const detailPath = ref("");
const detailEnabled = ref(false);
const rowMenuOpen = ref<Record<string, boolean>>({});
const tableShellRef = ref<HTMLElement | null>(null);
const hasRestoredScroll = ref(false);

const inspectorQuery = useInfiniteLibraryInspectorQuery(query, scope, currentPath, limit, inspectorSort);
const metadataQuery = useLibraryInspectorMetadataQuery(detailPath, detailEnabled);
const rebuildStartedAt = computed(() =>
  scope.value === "current" ? getScopeRebuildStartedAt(currentPath.value) : 0
);
const indexStatusEnabled = computed(() =>
  scope.value === "current" && Boolean(currentPath.value) && Boolean(rebuildStartedAt.value)
);
const indexStatusQuery = useIndexStatusQuery(currentPath, indexStatusEnabled);
const rebuildMarkerFirstSeenAtMs = ref(0);
const statusMetadataRecords = computed(() => indexStatusQuery.data.value?.metadata_records ?? null);
const indexStatusHasPendingWork = computed(() =>
  hasActiveIndexWork(indexStatusQuery.data.value) || hasQueuedIndexWork(indexStatusQuery.data.value)
);
const isInspectorPlaceholderData = computed(() => inspectorQuery.isPlaceholderData.value);
const inspectorSnapshotIsAfterRebuild = computed(() => {
  const startedAt = rebuildStartedAt.value;
  if (!startedAt || isInspectorPlaceholderData.value) return false;
  return (inspectorQuery.data.value.generated_at || 0) >= startedAt;
});
/**
 * True when the inspector snapshot in view is stale — its generated_at is before
 * the most recent rebuild_started_at for this scope. This means placeholder
 * (pre-rebuild) data is being shown while the inspector refetches.
 *
 * This does NOT reflect the actual index rebuild state. True rebuild progress
 * (active jobs, completion %) is shown in the sidebar Index Status panel.
 */
const isInspectorDataStale = computed(() => {
  const startedAt = rebuildStartedAt.value;
  if (!startedAt) return false;
  if (isInspectorPlaceholderData.value) return true;
  return (inspectorQuery.data.value.generated_at || 0) < startedAt;
});
const inspectorSummary = computed(() => {
  if (isInspectorDataStale.value) return "Refreshing photo details\u2026";
  const returned = inspectorQuery.data.value.returned;
  const total = inspectorQuery.data.value.total_indexed;
  if (returned < total) {
    return `${returned.toLocaleString()} of ${total.toLocaleString()} indexed photos shown`;
  }
  return `${total.toLocaleString()} indexed photos`;
});
const pageSummary = computed(() => {
  const root = inspectorQuery.data.value.root || galleryStore.currentPath || "All indexed";
  return `${inspectorSummary.value} · ${root} · Including subfolders`;
});

const REBUILD_INSPECTOR_REFETCH_MS = 1_500;
const REBUILD_INSPECTOR_MAX_SETTLE_MS = 30_000;
const REBUILD_INSPECTOR_REFETCH_DEDUPE_MS = 350;
let rebuildInspectorPollTimer: number | undefined;
let lastRebuildInspectorRefetchAtMs = 0;

function canClearRebuildMarker() {
  const startedAt = rebuildStartedAt.value;
  if (!startedAt || !inspectorSnapshotIsAfterRebuild.value || indexStatusHasPendingWork.value) {
    return false;
  }

  const statusRecords = statusMetadataRecords.value;
  const inspectorRecords = inspectorQuery.data.value.total_indexed;
  const elapsedMs = rebuildMarkerFirstSeenAtMs.value
    ? Date.now() - rebuildMarkerFirstSeenAtMs.value
    : 0;

  if (statusRecords === null) {
    return elapsedMs >= REBUILD_INSPECTOR_MAX_SETTLE_MS;
  }
  if (statusRecords !== inspectorRecords) {
    return false;
  }

  return statusRecords > 0 || elapsedMs >= REBUILD_INSPECTOR_MAX_SETTLE_MS;
}

function maybeClearRebuildMarker() {
  if (!canClearRebuildMarker()) return;
  logIndexRebuildDebug("inspector-clear-rebuild-marker", {
    path: currentPath.value,
    generated_at: inspectorQuery.data.value.generated_at,
    rebuild_started_at: rebuildStartedAt.value,
    inspector_total_indexed: inspectorQuery.data.value.total_indexed,
    status_metadata_records: statusMetadataRecords.value,
    status_updated_at: indexStatusQuery.data.value?.updated_at ?? null,
  });
  clearScopeRebuildMarker(currentPath.value, inspectorQuery.data.value.generated_at);
}

function refetchInspectorAfterRebuild(reason: string) {
  if (!rebuildStartedAt.value || scope.value !== "current") return;
  const now = Date.now();
  if (now - lastRebuildInspectorRefetchAtMs < REBUILD_INSPECTOR_REFETCH_DEDUPE_MS) {
    return;
  }
  lastRebuildInspectorRefetchAtMs = now;
  logIndexRebuildDebug("inspector-refetch", {
    reason,
    path: currentPath.value,
    activeLibraryInspectorQueryKey: queryKeys.libraryInspector(
      inspectorQuery.debouncedQuery.value,
      scope.value,
      currentPath.value,
      limit.value,
      inspectorSort.value,
    ),
    rebuild_started_at: rebuildStartedAt.value,
    inspector_generated_at: inspectorQuery.data.value.generated_at,
    inspector_total_indexed: inspectorQuery.data.value.total_indexed,
    status_metadata_records: statusMetadataRecords.value,
  });
  void inspectorQuery.refetch();
}

function refetchRebuildState(reason: string) {
  if (!rebuildStartedAt.value || scope.value !== "current") return;
  void indexStatusQuery.refetch();
  refetchInspectorAfterRebuild(reason);
}

watch(
  rebuildStartedAt,
  (startedAt) => {
    if (startedAt) {
      rebuildMarkerFirstSeenAtMs.value = Date.now();
      refetchRebuildState("rebuild-marker");
      return;
    }
    rebuildMarkerFirstSeenAtMs.value = 0;
  },
  { immediate: true }
);

watch(
  () => statusMetadataRecords.value,
  () => {
    refetchInspectorAfterRebuild("status-count-change");
  }
);

watch(
  () => [
    inspectorQuery.data.value.generated_at,
    inspectorQuery.data.value.total_indexed,
    statusMetadataRecords.value,
    indexStatusHasPendingWork.value,
  ],
  maybeClearRebuildMarker
);

watch(
  () => Boolean(rebuildStartedAt.value && scope.value === "current"),
  (shouldPoll) => {
    if (rebuildInspectorPollTimer) {
      window.clearInterval(rebuildInspectorPollTimer);
      rebuildInspectorPollTimer = undefined;
    }
    if (!shouldPoll) return;
    rebuildInspectorPollTimer = window.setInterval(() => {
      refetchRebuildState("rebuild-poll");
      maybeClearRebuildMarker();
    }, REBUILD_INSPECTOR_REFETCH_MS);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  if (rebuildInspectorPollTimer) {
    window.clearInterval(rebuildInspectorPollTimer);
  }
});

const columnHelper = createColumnHelper<LibraryInspectorRow>();
const columns = [
  columnHelper.accessor("name", { id: "name", header: "File", enableSorting: true }),
  columnHelper.accessor("prompt_preview", { id: "prompt", header: "Prompt preview", enableSorting: false }),
  columnHelper.accessor((row) => row.model || row.tool, { id: "model", header: "Model", enableSorting: true }),
  columnHelper.accessor("seed", { id: "seed", header: "Seed", enableSorting: true }),
  columnHelper.accessor((row) => `${row.width || ""}x${row.height || ""}`, { id: "dimensions", header: "Size", enableSorting: true }),
  columnHelper.accessor("mtime", { id: "mtime", header: "Modified", enableSorting: true }),
  columnHelper.display({ id: "actions", header: "", enableSorting: false }),
];

const modelOptions = computed(() => {
  const options = new Set<string>();
  for (const row of inspectorQuery.rows.value) {
    const label = modelLabel(row);
    if (label && label !== "Unknown") options.add(label);
  }
  return Array.from(options).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
});

watch(modelOptions, (options) => {
  if (modelFilter.value !== "all" && !options.includes(modelFilter.value)) {
    modelFilter.value = "all";
  }
});

const filteredRows = computed(() =>
  inspectorQuery.rows.value.filter((row) => {
    if (modelFilter.value !== "all" && modelLabel(row) !== modelFilter.value) return false;
    if (promptFilter.value === "has_prompt" && !row.has_prompt) return false;
    if (promptFilter.value === "no_prompt" && row.has_prompt) return false;
    return true;
  })
);
watch(
  inspectorSort,
  (value) => {
    const next = sortValueToTableState(value);
    if (sorting.value[0]?.id !== next[0]?.id || sorting.value[0]?.desc !== next[0]?.desc) {
      sorting.value = next;
    }
  }
);

watch(
  sorting,
  () => {
    const active = sorting.value[0];
    const next = active ? tableStateToSortValue(active.id, active.desc) : null;
    if (next && inspectorSort.value !== next) {
      inspectorSort.value = next;
    }
  }
);

const table = useVueTable({
  get data() {
    return filteredRows.value;
  },
  columns,
  state: {
    get sorting() {
      return sorting.value;
    },
  },
  onSortingChange(updater) {
    const next = typeof updater === "function" ? updater(sorting.value) : updater;
    sorting.value = next;
  },
  enableSortingRemoval: false,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
});

const visibleTableRows = computed(() => table.getRowModel().rows);
const METADATA_ROW_HEIGHT = 64;
const virtualRowCount = computed(() => visibleTableRows.value.length);
const rowVirtualizer = useVirtualizer<HTMLElement, HTMLElement>(
  computed(() => ({
    count: virtualRowCount.value,
    getScrollElement: () => tableShellRef.value,
    estimateSize: () => METADATA_ROW_HEIGHT,
    overscan: 3,
    getItemKey: (index: number) => visibleTableRows.value[index]?.original.path ?? index,
  }))
);
const virtualRows = computed(() => rowVirtualizer.value.getVirtualItems());
const virtualPaddingTop = computed(() => virtualRows.value[0]?.start ?? 0);
const virtualPaddingBottom = computed(() => {
  const last = virtualRows.value[virtualRows.value.length - 1];
  if (!last) return 0;
  return Math.max(0, rowVirtualizer.value.getTotalSize() - last.end);
});
function saveInspectorScroll() {
  const scrollTop = tableShellRef.value?.scrollTop ?? 0;
  galleryStore.metadataInspector.scrollTop = scrollTop;
  galleryStore.metadataInspector.scrollPath = currentPath.value;
}

async function restoreInspectorScroll() {
  if (hasRestoredScroll.value) return;
  if (galleryStore.metadataInspector.scrollPath !== currentPath.value) {
    galleryStore.metadataInspector.scrollTop = 0;
    return;
  }
  const scrollTop = galleryStore.metadataInspector.scrollTop;
  if (!scrollTop || !tableShellRef.value || visibleTableRows.value.length === 0) {
    return;
  }
  hasRestoredScroll.value = true;
  await nextTick();
  rowVirtualizer.value.scrollToOffset(scrollTop);
}

onMounted(() => {
  void restoreInspectorScroll();
});

onBeforeUnmount(() => {
  saveInspectorScroll();
});

watch(
  () => currentPath.value,
  () => {
    hasRestoredScroll.value = false;
    if (galleryStore.metadataInspector.scrollPath !== currentPath.value) {
      galleryStore.metadataInspector.scrollTop = 0;
      galleryStore.metadataInspector.selectedPath = "";
    }
  }
);

watch(
  () => visibleTableRows.value.length,
  () => {
    void restoreInspectorScroll();
  },
  { flush: "post" }
);

watch(
  [virtualRowCount, inspectorSort, query, scope, currentPath, modelFilter, promptFilter],
  () => {
    rowVirtualizer.value.measure();
  },
  { flush: "post" }
);

watch(virtualRows, (items) => {
  if (!items.length || !inspectorQuery.hasNextPage.value || inspectorQuery.isFetchingNextPage.value) return;
  const lastItem = items[items.length - 1];
  if (lastItem && lastItem.index >= visibleTableRows.value.length - 5) {
    void inspectorQuery.fetchNextPage();
  }
});
const visibleRows = computed(() => visibleTableRows.value.map((row) => row.original));
const visibleLightboxItems = computed<FileNode[]>(() =>
  visibleRows.value.map((row) => ({
    name: row.name,
    path: row.path,
    type: "image",
    has_children: false,
    mtime: row.mtime ?? undefined,
    width: row.width,
    height: row.height,
  })),
);

function openDetail(path: string, open: boolean) {
  if (!open) return;
  detailPath.value = path;
  detailEnabled.value = true;
}

function formatDate(value: number | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value * 1000));
}

function formatDimensions(row: LibraryInspectorRow) {
  if (!row.width || !row.height) return "-";
  return `${row.width} × ${row.height}`;
}

function modelLabel(row: LibraryInspectorRow) {
  return row.model || row.tool || "Unknown";
}

function folderLabel(row: LibraryInspectorRow) {
  return row.relative_path || row.folder || "Root";
}

function openImage(row: LibraryInspectorRow) {
  const items = visibleLightboxItems.value;
  const visibleIndex = items.findIndex((item) => item.path === row.path);
  logLightboxNavDebug("library-inspector-open-image", {
    clicked: { path: row.path, name: row.name },
    visibleIndex,
    visibleRows: visibleRows.value.length,
    tableRows: visibleTableRows.value.length,
    sorting: sorting.value,
    query: query.value,
    scope: scope.value,
    currentPath: currentPath.value,
    items: summarizeLightboxItems(items, visibleIndex),
  });
  lightboxStore.open({ path: row.path, name: row.name }, items, visibleIndex);
}

function composeMetadata(detail: LibraryInspectorMetadataResponse) {
  if (detail.raw_metadata) {
    return JSON.stringify(detail.raw_metadata, null, 2);
  }

  return [
    `Prompt: ${detail.prompt || ""}`,
    `Negative prompt: ${detail.negative_prompt || ""}`,
    `Model: ${detail.model || ""}`,
    `Tool: ${detail.tool || ""}`,
    `Sampler: ${detail.sampler || ""}`,
    `Seed: ${detail.seed || ""}`,
    `Dimensions: ${detail.width || ""}x${detail.height || ""}`,
    `Modified: ${detail.mtime ? formatDate(detail.mtime) : ""}`,
    `Path: ${detail.path}`,
  ].join("\n");
}

function formatResources(resources: LibraryInspectorResource[]) {
  return resources
    .map((item) => {
      const hash = item.resource_hash || item.hash;
      const weight = item.weight ?? item.strength;
      return [item.name, hash, weight !== null && weight !== undefined ? `weight ${weight}` : ""]
        .filter(Boolean)
        .join(" | ");
    })
    .filter(Boolean)
    .join("\n");
}

async function copyDetail(
  row: LibraryInspectorRow,
  kind: "prompt" | "negative" | "metadata" | "loras" | "hashes",
): Promise<boolean> {
  try {
    const detail = await queryClient.fetchQuery({
      queryKey: queryKeys.libraryInspectorMetadata(row.path),
      queryFn: () => fetchLibraryInspectorMetadata(row.path),
    });
    if (kind === "prompt") {
      await copyText(detail.prompt, "prompt");
      return true;
    }
    if (kind === "negative") {
      await copyText(detail.negative_prompt, "neg");
      return true;
    }
    if (kind === "loras") {
      await copyText(formatResources(detail.loras), "loras");
      return true;
    }
    if (kind === "hashes") {
      const hashes = [...detail.loras, ...detail.resources]
        .map((item) => item.resource_hash || item.hash)
        .filter(Boolean)
        .join("\n");
      await copyText(hashes, "hashes");
      return true;
    }
    await copyText(composeMetadata(detail), "metadata");
    return true;
  } catch {
    toast.error("Unable to load metadata", "The indexed metadata detail could not be fetched.");
    return false;
  }
}

function handleCopyDetailSelect(
  event: Event,
  row: LibraryInspectorRow,
  kind: "prompt" | "negative" | "metadata" | "loras" | "hashes",
) {
  event.preventDefault();
  copyDetail(row, kind).then((ok) => {
    if (ok) rowMenuOpen.value[row.path] = false;
  });
}

function sortAriaLabel(columnId: string, header: unknown) {
  const label = typeof header === "string" ? header : "Column";
  const column = table.getColumn(columnId);
  const state = column?.getIsSorted();
  if (state === "asc") return `${label}, sorted ascending`;
  if (state === "desc") return `${label}, sorted descending`;
  return `${label}, not sorted`;
}

function onHeaderSort(columnId: string, event: MouseEvent) {
  table.getColumn(columnId)?.getToggleSortingHandler()?.(event);
}

</script>

<template>
  <section class="library-inspector" aria-labelledby="library-inspector-title">
    <div class="inspector-header">
      <div class="inspector-heading">
        <ButtonLink to="/" variant="outline" size="sm" class="h-8 shrink-0 gap-1.5">
          <ArrowLeft class="size-4" aria-hidden="true" />
          Gallery
        </ButtonLink>
        <div class="min-w-0">
          <h2 id="library-inspector-title" class="truncate text-xl font-semibold tracking-normal">
            Photo Details
          </h2>
          <p class="truncate text-sm text-muted-foreground">
            {{ pageSummary }}
          </p>
        </div>
      </div>
    </div>

    <div class="table-toolbar">
      <div class="inspector-search relative">
        <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="query"
          type="search"
          class="h-9 pl-9"
          placeholder="Search/filter metadata table... prompt:ancient door, model:sdxl, seed:123456"
          aria-label="Search metadata table"
        />
      </div>
      <Select v-model="modelFilter">
        <SelectTrigger class="toolbar-select">
          <SelectValue placeholder="Model" />
        </SelectTrigger>
        <SelectContent align="end">
          <SelectItem value="all">All models</SelectItem>
          <SelectItem v-for="model in modelOptions" :key="model" :value="model">
            {{ model }}
          </SelectItem>
        </SelectContent>
      </Select>
      <Select v-model="promptFilter">
        <SelectTrigger class="toolbar-select">
          <SelectValue placeholder="Has prompt" />
        </SelectTrigger>
        <SelectContent align="end">
          <SelectItem value="all">All prompts</SelectItem>
          <SelectItem value="has_prompt">Has prompt</SelectItem>
          <SelectItem value="no_prompt">No prompt</SelectItem>
        </SelectContent>
      </Select>
      <SortSelect v-model="inspectorSort" aria-label="Sort metadata table" />
    </div>

    <div v-if="inspectorQuery.isError.value" class="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
      Unable to load metadata rows.
    </div>

    <div v-if="isInspectorDataStale" class="rebuild-notice">
      Refreshing photo details. Previous results are shown until the latest snapshot arrives.
    </div>

    <div
      ref="tableShellRef"
      :class="['metadata-table-shell table-shell', isInspectorDataStale && 'table-shell--rebuilding']"
      @scroll.passive="saveInspectorScroll"
    >
      <Table class="inspector-table w-full table-fixed">
        <TableHeader class="table-header bg-muted">
          <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id" class="table-header-row bg-muted hover:bg-muted">
            <TableHead
              v-for="header in headerGroup.headers"
              :key="header.id"
              :class="['table-head sticky top-0 z-30 bg-muted', `col-${header.column.id}`]"
              :aria-sort="header.column.getIsSorted() === 'asc' ? 'ascending' : header.column.getIsSorted() === 'desc' ? 'descending' : undefined"
            >
              <button
                v-if="header.column.getCanSort()"
                type="button"
                class="metadata-header-control"
                :aria-label="sortAriaLabel(header.column.id, header.column.columnDef.header)"
                :title="sortAriaLabel(header.column.id, header.column.columnDef.header)"
                @click="onHeaderSort(header.column.id, $event)"
              >
                <span class="metadata-header-label">
                  {{ header.column.columnDef.header }}
                </span>
                <span
                  v-if="header.column.getIsSorted()"
                  class="metadata-header-sort-indicator"
                  aria-hidden="true"
                >
                  {{ header.column.getIsSorted() === 'asc' ? '↑' : '↓' }}
                </span>
                <ArrowUpDown v-else class="metadata-header-icon" aria-hidden="true" />
              </button>
              <span v-else class="metadata-header-control metadata-header-control--static">
                <span class="metadata-header-label">
                  {{ header.column.columnDef.header }}
                </span>
              </span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="inspectorQuery.isLoading.value">
            <TableCell colspan="7" class="p-4">
              <div class="space-y-2">
                <Skeleton v-for="idx in 8" :key="idx" class="h-10 w-full" />
              </div>
            </TableCell>
          </TableRow>
          <TableRow v-else-if="visibleTableRows.length === 0">
            <TableCell colspan="7" class="p-8 text-center text-sm text-muted-foreground">
              {{ isInspectorDataStale ? "Refreshing metadata rows…" : "No indexed metadata rows." }}
            </TableCell>
          </TableRow>
          <template v-else>
          <TableRow
            v-if="virtualPaddingTop > 0"
            aria-hidden="true"
            class="virtual-spacer-row"
            :style="{ height: `${virtualPaddingTop}px` }"
          >
            <TableCell colspan="7" class="p-0"></TableCell>
          </TableRow>
          <TableRow
            v-for="virtualRow in virtualRows"
            :key="String(virtualRow.key)"
            :data-state="selectedPath === visibleTableRows[virtualRow.index]?.original.path ? 'selected' : undefined"
            class="table-row"
            :style="{ height: `${virtualRow.size}px` }"
            @click="selectedPath = visibleTableRows[virtualRow.index]?.original.path || selectedPath"
          >
            <TableCell class="table-cell col-name">
              <div class="file-cell flex min-w-0 items-center gap-3">
                <button class="thumb-button" type="button" @click.stop="openImage(visibleTableRows[virtualRow.index].original)">
                  <img :src="getThumbnailUrl(visibleTableRows[virtualRow.index].original.path, 128)" :alt="visibleTableRows[virtualRow.index].original.name" loading="lazy" />
                </button>
                <div class="file-cell-content min-w-0">
                  <button class="long-text-trigger file-name-trigger" type="button" @click.stop="openImage(visibleTableRows[virtualRow.index].original)">
                    <span class="long-text-preview truncate">{{ visibleTableRows[virtualRow.index].original.name }}</span>
                  </button>
                  <Popover @update:open="(open) => open && (selectedPath = visibleTableRows[virtualRow.index].original.path)">
                    <PopoverTrigger as-child>
                      <button class="long-text-trigger folder-path-trigger" type="button" @click.stop>
                        <span class="long-text-preview truncate">{{ folderLabel(visibleTableRows[virtualRow.index].original) }}</span>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" class="w-96">
                      <div class="space-y-3">
                        <p class="break-all text-sm">{{ visibleTableRows[virtualRow.index].original.path }}</p>
                        <Button size="sm" variant="secondary" @click="copyText(visibleTableRows[virtualRow.index].original.path, 'path')">
                          <Copy class="size-4" /> Copy full path
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
            </TableCell>
            <TableCell class="table-cell col-prompt">
              <div class="prompt-cell min-w-0 overflow-hidden">
                <Popover v-if="visibleTableRows[virtualRow.index].original.has_prompt || visibleTableRows[virtualRow.index].original.has_negative" @update:open="(open) => openDetail(visibleTableRows[virtualRow.index].original.path, open)">
                  <PopoverTrigger as-child>
                    <button class="long-text-trigger prompt-trigger" type="button" @click.stop>
                      <span class="long-text-preview truncate whitespace-nowrap">{{ visibleTableRows[virtualRow.index].original.prompt_preview || 'No prompt metadata' }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" class="w-[32rem]">
                    <div v-if="metadataQuery.isLoading.value && detailPath === visibleTableRows[virtualRow.index].original.path" class="space-y-2">
                      <Skeleton class="h-4 w-2/3" />
                      <Skeleton class="h-24 w-full" />
                      <Skeleton class="h-16 w-full" />
                    </div>
                    <div v-else-if="metadataQuery.isError.value && detailPath === visibleTableRows[virtualRow.index].original.path" class="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                      <p class="font-medium">Unable to load metadata detail.</p>
                      <Button size="sm" variant="outline" @click="metadataQuery.refetch()">Retry</Button>
                    </div>
                    <div v-else class="space-y-4">
                      <div>
                        <p class="mb-1 text-sm font-medium">Prompt</p>
                        <p class="metadata-block">{{ metadataQuery.data.value?.prompt || 'No prompt metadata' }}</p>
                      </div>
                      <div v-if="metadataQuery.data.value?.negative_prompt">
                        <p class="mb-1 text-sm font-medium">Negative prompt</p>
                        <p class="metadata-block">{{ metadataQuery.data.value.negative_prompt }}</p>
                      </div>
                      <div class="flex flex-wrap gap-2">
                        <Button size="sm" variant="secondary" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'prompt')">Copy prompt</Button>
                        <Button size="sm" variant="secondary" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'negative')">Copy negative</Button>
                        <Button size="sm" variant="outline" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'metadata')">Copy full metadata</Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
                <span v-else class="block min-w-0 max-w-full truncate whitespace-nowrap text-muted-foreground">No prompt metadata</span>
              </div>
            </TableCell>
            <TableCell class="table-cell col-model">
              <div class="space-y-1">
                <span :class="['block truncate font-medium', modelLabel(visibleTableRows[virtualRow.index].original) === 'Unknown' && 'text-muted-foreground']">
                  {{ modelLabel(visibleTableRows[virtualRow.index].original) }}
                </span>
                <Popover v-if="visibleTableRows[virtualRow.index].original.has_lora" @update:open="(open) => openDetail(visibleTableRows[virtualRow.index].original.path, open)">
                  <PopoverTrigger as-child>
                    <button class="inline-flex" type="button" @click.stop>
                      <Badge variant="secondary">{{ visibleTableRows[virtualRow.index].original.lora_count > 1 ? `LoRA ${visibleTableRows[virtualRow.index].original.lora_count}` : 'LoRA' }}</Badge>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" class="w-[28rem]">
                    <div v-if="metadataQuery.isLoading.value && detailPath === visibleTableRows[virtualRow.index].original.path" class="space-y-2">
                      <Skeleton class="h-4 w-3/4" />
                      <Skeleton class="h-20 w-full" />
                    </div>
                    <div v-else-if="metadataQuery.isError.value && detailPath === visibleTableRows[virtualRow.index].original.path" class="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                      <p class="font-medium">Unable to load resource detail.</p>
                      <Button size="sm" variant="outline" @click="metadataQuery.refetch()">Retry</Button>
                    </div>
                    <div v-else class="space-y-3">
                      <p class="text-sm font-medium">LoRA resources</p>
                      <pre class="metadata-block">{{ formatResources(metadataQuery.data.value?.loras || []) || visibleTableRows[virtualRow.index].original.lora_preview }}</pre>
                      <div class="flex flex-wrap gap-2">
                        <Button size="sm" variant="secondary" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'loras')">Copy LoRA list</Button>
                        <Button size="sm" variant="secondary" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'hashes')">Copy resource hashes</Button>
                        <Button size="sm" variant="outline" @click="copyDetail(visibleTableRows[virtualRow.index].original, 'metadata')">Copy full metadata</Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </TableCell>
            <TableCell class="table-cell col-seed">
              <button
                v-if="visibleTableRows[virtualRow.index].original.seed"
                class="inline-flex cursor-copy items-center gap-1 rounded-sm font-mono text-xs hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                type="button"
                :aria-label="`Copy seed ${visibleTableRows[virtualRow.index].original.seed}`"
                title="Copy seed"
                @click.stop="copyText(visibleTableRows[virtualRow.index].original.seed, 'seed')"
              >
                <span>{{ visibleTableRows[virtualRow.index].original.seed }}</span>
                <Copy class="seed-copy-icon size-3" aria-hidden="true" />
              </button>
              <span v-else class="text-muted-foreground">-</span>
            </TableCell>
            <TableCell class="table-cell col-dimensions whitespace-nowrap">{{ formatDimensions(visibleTableRows[virtualRow.index].original) }}</TableCell>
            <TableCell class="table-cell col-mtime whitespace-nowrap">{{ formatDate(visibleTableRows[virtualRow.index].original.mtime) }}</TableCell>
            <TableCell class="table-cell col-actions">
              <DropdownMenu v-model:open="rowMenuOpen[visibleTableRows[virtualRow.index].original.path]">
                <DropdownMenuTrigger as-child>
                  <Button variant="ghost" size="icon-sm" aria-label="Row actions" @click.stop>
                    <MoreHorizontal class="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="openImage(visibleTableRows[virtualRow.index].original)">
                    <ExternalLink class="size-4" /> Open image
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="copyText(visibleTableRows[virtualRow.index].original.path, 'path')">
                    <Copy class="size-4" /> Copy path
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="visibleTableRows[virtualRow.index].original.seed" @click="copyText(visibleTableRows[virtualRow.index].original.seed, 'seed')">
                    <Copy class="size-4" /> Copy seed
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="visibleTableRows[virtualRow.index].original.has_prompt" @select="(event: Event) => handleCopyDetailSelect(event, visibleTableRows[virtualRow.index].original, 'prompt')">
                    <Copy class="size-4" /> Copy prompt
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="visibleTableRows[virtualRow.index].original.has_negative" @select="(event: Event) => handleCopyDetailSelect(event, visibleTableRows[virtualRow.index].original, 'negative')">
                    <Copy class="size-4" /> Copy negative
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="visibleTableRows[virtualRow.index].original.has_lora" @select="(event: Event) => handleCopyDetailSelect(event, visibleTableRows[virtualRow.index].original, 'loras')">
                    <Copy class="size-4" /> Copy LoRA list
                  </DropdownMenuItem>
                  <DropdownMenuItem @select="(event: Event) => handleCopyDetailSelect(event, visibleTableRows[virtualRow.index].original, 'metadata')">
                    <Copy class="size-4" /> Copy full metadata
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
          <TableRow
            v-if="virtualPaddingBottom > 0"
            aria-hidden="true"
            class="virtual-spacer-row"
            :style="{ height: `${virtualPaddingBottom}px` }"
          >
            <TableCell colspan="7" class="p-0"></TableCell>
          </TableRow>
          <TableRow v-if="inspectorQuery.isFetchingNextPage.value" class="load-more-row">
            <TableCell colspan="7" class="px-4 py-3 text-center text-xs text-muted-foreground">
              Loading more metadata rows...
            </TableCell>
          </TableRow>
          </template>
        </TableBody>
      </Table>
    </div>
  </section>
</template>

<style scoped>
.library-inspector {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  gap: 10px;
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 2px;
}

.inspector-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}

.inspector-search {
  min-width: 280px;
  flex: 1 1 420px;
}

.table-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-select {
  height: 36px;
  width: 150px;
  flex: 0 0 auto;
}

.gallery-icon-sm {
  height: 16px;
  width: 16px;
}

.sort-dropdown-content {
  min-width: 150px;
}

.table-shell {
  position: relative;
  isolation: isolate;
  min-height: 0;
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--background);
}

.table-shell--rebuilding .inspector-table {
  opacity: 0.45;
}

.rebuild-notice {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--muted) 55%, transparent);
  padding: 10px 12px;
  color: var(--foreground);
  font-size: 13px;
}

.inspector-table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  min-width: 1280px;
  table-layout: fixed;
  font-size: 13px;
}

.table-header {
  position: relative;
  z-index: 30;
  background: var(--muted);
}

.table-header-row {
  position: relative;
  z-index: 30;
  background: var(--muted);
}

.table-head {
  position: sticky;
  top: 0;
  z-index: 30;
  height: 38px;
  border-bottom: 1px solid var(--border);
  background: var(--muted);
  background-clip: padding-box;
  box-shadow: inset 0 -1px 0 var(--border);
  color: var(--muted-foreground);
  text-align: left;
  vertical-align: middle;
}

.table-head::before {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: var(--muted);
  content: "";
}

.metadata-header-control {
  position: relative;
  z-index: 10;
  display: inline-flex;
  height: 2rem;
  align-items: center;
  gap: 0.25rem;
  border: 0;
  border-radius: 0.375rem;
  background: transparent;
  padding: 0 0.5rem;
  color: var(--foreground);
  cursor: pointer;
  font-family: inherit;
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.25rem;
}

.metadata-header-control--static {
  cursor: default;
}

button.metadata-header-control:hover {
  background: var(--accent);
}

button.metadata-header-control:focus-visible {
  outline: none;
  box-shadow: 0 0 0 1px var(--ring);
}

.metadata-header-label {
  min-width: 0;
}

.metadata-header-icon {
  width: 0.75rem;
  height: 0.75rem;
  flex: 0 0 auto;
  opacity: 0.45;
}

.metadata-header-sort-indicator {
  display: inline-flex;
  width: 0.75rem;
  flex: 0 0 0.75rem;
  justify-content: center;
  color: var(--foreground);
  font-size: 0.875rem;
  line-height: 1;
}

.table-row {
  position: relative;
  z-index: 0;
  height: 64px;
}

.virtual-spacer-row {
  pointer-events: none;
}

.virtual-spacer-row > td {
  height: inherit;
  border: 0;
}

.table-cell {
  position: relative;
  z-index: 0;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  padding: 7px 12px;
  vertical-align: middle;
}

.col-name {
  width: 360px;
  max-width: 360px;
}

.col-prompt {
  width: 390px;
  max-width: 390px;
}

.col-model {
  width: 150px;
  max-width: 150px;
}

.col-seed {
  width: 110px;
  max-width: 110px;
}

.col-dimensions {
  width: 96px;
  max-width: 96px;
}

.col-mtime {
  width: 160px;
  max-width: 160px;
}

.col-actions {
  width: 56px;
  text-align: right;
}

.thumb-button {
  display: block;
  height: 44px;
  width: 44px;
  flex: 0 0 44px;
  overflow: hidden;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--muted);
}

.thumb-button img {
  height: 100%;
  width: 100%;
  object-fit: cover;
}

.long-text-trigger {
  display: block;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-align: left;
}

.file-cell-content,
.prompt-cell {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.col-model > div,
.col-seed > button,
.col-dimensions,
.col-mtime {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-name-trigger {
  color: var(--foreground);
  font-weight: 500;
}

.folder-path-trigger {
  color: var(--muted-foreground);
  font-size: 12px;
}

.folder-path-trigger:hover,
.prompt-trigger:hover {
  color: var(--foreground);
}

.prompt-trigger {
  color: var(--foreground);
}

.long-text-preview {
  display: block;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.seed-copy-icon {
  opacity: 0;
  transition: opacity 120ms ease;
}

.col-seed button:hover .seed-copy-icon,
.col-seed button:focus-visible .seed-copy-icon {
  opacity: 0.55;
}

.metadata-block {
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 6px;
  background: var(--muted);
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--foreground);
}

@media (max-width: 900px) {
  .inspector-header,
  .table-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .inspector-heading {
    align-items: flex-start;
  }

  .inspector-search,
  .toolbar-select {
    width: 100%;
  }
}
</style>
