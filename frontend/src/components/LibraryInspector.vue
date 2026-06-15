<script setup lang="ts">
import { computed, ref } from "vue";
import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useVueTable,
  type SortingState,
} from "@tanstack/vue-table";
import { ArrowLeft, Copy, ExternalLink, MoreHorizontal, Search } from "lucide-vue-next";
import Badge from "@/components/ui/Badge.vue";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Input from "@/components/ui/Input.vue";
import { Skeleton } from "@/components/ui/skeleton";
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
import { useToast } from "@/composables/useToast";
import { useLibraryInspectorMetadataQuery } from "@/composables/useLibraryInspectorMetadataQuery";
import { useLibraryInspectorQuery } from "@/composables/useLibraryInspectorQuery";
import { useGalleryStore } from "@/stores/gallery";
import { useLightboxStore } from "@/stores/lightbox";
import { fetchLibraryInspectorMetadata, getThumbnailUrl } from "@/services/api";
import { queryClient } from "@/query";
import { queryKeys } from "@/query/keys";
import type {
  FileNode,
  LibraryInspectorMetadataResponse,
  LibraryInspectorResource,
  LibraryInspectorRow,
  SearchScope,
} from "@/types";

const galleryStore = useGalleryStore();
const lightboxStore = useLightboxStore();
const { copyText } = useClipboard();
const toast = useToast();

const query = ref("");
const scope = ref<SearchScope>("all");
const currentPath = computed(() => galleryStore.currentPath || "");
const limit = ref(200);
const sorting = ref<SortingState>([{ id: "mtime", desc: true }]);
const selectedPath = ref("");
const detailPath = ref("");
const detailEnabled = ref(false);
const rowMenuOpen = ref<Record<string, boolean>>({});

const inspectorQuery = useLibraryInspectorQuery(query, scope, currentPath, limit);
const metadataQuery = useLibraryInspectorMetadataQuery(detailPath, detailEnabled);

const columnHelper = createColumnHelper<LibraryInspectorRow>();
const columns = [
  columnHelper.display({ id: "thumbnail", header: "", enableSorting: false }),
  columnHelper.accessor("name", { id: "name", header: "File", enableSorting: true }),
  columnHelper.accessor("prompt_preview", { id: "prompt", header: "Prompt", enableSorting: false }),
  columnHelper.accessor((row) => row.model || row.tool, { id: "model", header: "Model", enableSorting: true }),
  columnHelper.accessor("seed", { id: "seed", header: "Seed", enableSorting: true }),
  columnHelper.accessor((row) => `${row.width || ""}x${row.height || ""}`, { id: "dimensions", header: "Size", enableSorting: true }),
  columnHelper.accessor("mtime", { id: "mtime", header: "Modified", enableSorting: true }),
  columnHelper.display({ id: "actions", header: "", enableSorting: false }),
];

const table = useVueTable({
  get data() {
    return inspectorQuery.rows.value;
  },
  columns,
  state: {
    get sorting() {
      return sorting.value;
    },
  },
  onSortingChange(updater) {
    sorting.value = typeof updater === "function" ? updater(sorting.value) : updater;
  },
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
});

const visibleTableRows = computed(() => table.getRowModel().rows);
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
  if (!row.width || !row.height) return "Unknown";
  return `${row.width} x ${row.height}`;
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

function sortLabel(columnId: string) {
  const column = table.getColumn(columnId);
  const state = column?.getIsSorted();
  return state === "asc" ? " ↑" : state === "desc" ? " ↓" : "";
}

function sortAriaLabel(columnId: string, header: unknown) {
  const label = typeof header === "string" ? header : "Column";
  const column = table.getColumn(columnId);
  const state = column?.getIsSorted();
  if (state === "asc") return `${label}, sorted ascending`;
  if (state === "desc") return `${label}, sorted descending`;
  return `${label}, not sorted`;
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
            Library Inspector
          </h2>
          <p class="truncate text-sm text-muted-foreground">
            {{ inspectorQuery.data.value.returned }} returned from {{ inspectorQuery.data.value.total_indexed }} indexed
            <span v-if="inspectorQuery.data.value.truncated">(showing first {{ inspectorQuery.data.value.limit }})</span>
          </p>
        </div>
      </div>
      <div class="inspector-search relative">
        <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="query"
          type="search"
          class="pl-9"
          placeholder="Search metadata, prompt:ancient door, model:sdxl, seed:123456"
          aria-label="Search metadata"
        />
      </div>
    </div>

    <div v-if="inspectorQuery.isError.value" class="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
      Unable to load metadata rows.
    </div>

    <div class="table-shell">
      <table class="inspector-table">
        <thead>
          <tr v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
            <th
              v-for="header in headerGroup.headers"
              :key="header.id"
              :class="['table-head', `col-${header.column.id}`]"
              :aria-sort="header.column.getIsSorted() === 'asc' ? 'ascending' : header.column.getIsSorted() === 'desc' ? 'descending' : undefined"
            >
              <Button
                v-if="header.column.getCanSort()"
                variant="ghost"
                size="sm"
                class="h-8 px-2 text-xs font-medium"
                :aria-label="sortAriaLabel(header.column.id, header.column.columnDef.header)"
                :title="sortAriaLabel(header.column.id, header.column.columnDef.header)"
                @click="header.column.getToggleSortingHandler()?.($event)"
              >
                {{ header.column.columnDef.header }}{{ sortLabel(header.column.id) }}
              </Button>
              <span v-else class="px-2 text-xs font-medium">
                {{ header.column.columnDef.header }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="inspectorQuery.isLoading.value">
            <td colspan="8" class="p-4">
              <div class="space-y-2">
                <Skeleton v-for="idx in 8" :key="idx" class="h-10 w-full" />
              </div>
            </td>
          </tr>
          <tr v-else-if="table.getRowModel().rows.length === 0">
            <td colspan="8" class="p-8 text-center text-sm text-muted-foreground">
              No indexed metadata rows.
            </td>
          </tr>
          <tr
            v-for="row in table.getRowModel().rows"
            v-else
            :key="row.original.path"
            :class="['table-row', selectedPath === row.original.path && 'selected']"
            @click="selectedPath = row.original.path"
          >
            <td class="table-cell col-thumbnail">
              <button class="thumb-button" type="button" @click.stop="openImage(row.original)">
                <img :src="getThumbnailUrl(row.original.path, 128)" :alt="row.original.name" loading="lazy" />
              </button>
            </td>
            <td class="table-cell col-name">
              <div class="file-cell-content">
                <button class="long-text-trigger file-name-trigger" type="button" @click.stop="openImage(row.original)">
                  <span class="long-text-preview">{{ row.original.name }}</span>
                </button>
                <Popover @update:open="(open) => open && (selectedPath = row.original.path)">
                  <PopoverTrigger as-child>
                    <button class="long-text-trigger folder-path-trigger" type="button" @click.stop>
                      <span class="long-text-preview">{{ folderLabel(row.original) }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" class="w-96">
                    <div class="space-y-3">
                      <p class="break-all text-sm">{{ row.original.path }}</p>
                      <Button size="sm" variant="secondary" @click="copyText(row.original.path, 'path')">
                        <Copy class="size-4" /> Copy full path
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </td>
            <td class="table-cell col-prompt">
              <div class="prompt-cell">
                <Popover v-if="row.original.has_prompt || row.original.has_negative" @update:open="(open) => openDetail(row.original.path, open)">
                  <PopoverTrigger as-child>
                    <button class="long-text-trigger prompt-trigger" type="button" @click.stop>
                      <span class="long-text-preview">{{ row.original.prompt_preview || 'No prompt metadata' }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" class="w-[32rem]">
                    <div v-if="metadataQuery.isLoading.value && detailPath === row.original.path" class="space-y-2">
                      <Skeleton class="h-4 w-2/3" />
                      <Skeleton class="h-24 w-full" />
                      <Skeleton class="h-16 w-full" />
                    </div>
                    <div v-else-if="metadataQuery.isError.value && detailPath === row.original.path" class="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
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
                        <Button size="sm" variant="secondary" @click="copyDetail(row.original, 'prompt')">Copy prompt</Button>
                        <Button size="sm" variant="secondary" @click="copyDetail(row.original, 'negative')">Copy negative</Button>
                        <Button size="sm" variant="outline" @click="copyDetail(row.original, 'metadata')">Copy full metadata</Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
                <span v-else class="block min-w-0 max-w-full truncate text-muted-foreground">No prompt metadata</span>
              </div>
            </td>
            <td class="table-cell col-model">
              <div class="space-y-1">
                <span class="block truncate font-medium">{{ modelLabel(row.original) }}</span>
                <Popover v-if="row.original.has_lora" @update:open="(open) => openDetail(row.original.path, open)">
                  <PopoverTrigger as-child>
                    <button class="inline-flex" type="button" @click.stop>
                      <Badge variant="secondary">{{ row.original.lora_count > 1 ? `LoRA ${row.original.lora_count}` : 'LoRA' }}</Badge>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" class="w-[28rem]">
                    <div v-if="metadataQuery.isLoading.value && detailPath === row.original.path" class="space-y-2">
                      <Skeleton class="h-4 w-3/4" />
                      <Skeleton class="h-20 w-full" />
                    </div>
                    <div v-else-if="metadataQuery.isError.value && detailPath === row.original.path" class="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                      <p class="font-medium">Unable to load resource detail.</p>
                      <Button size="sm" variant="outline" @click="metadataQuery.refetch()">Retry</Button>
                    </div>
                    <div v-else class="space-y-3">
                      <p class="text-sm font-medium">LoRA resources</p>
                      <pre class="metadata-block">{{ formatResources(metadataQuery.data.value?.loras || []) || row.original.lora_preview }}</pre>
                      <div class="flex flex-wrap gap-2">
                        <Button size="sm" variant="secondary" @click="copyDetail(row.original, 'loras')">Copy LoRA list</Button>
                        <Button size="sm" variant="secondary" @click="copyDetail(row.original, 'hashes')">Copy resource hashes</Button>
                        <Button size="sm" variant="outline" @click="copyDetail(row.original, 'metadata')">Copy full metadata</Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </td>
            <td class="table-cell col-seed">
              <button
                v-if="row.original.seed"
                class="inline-flex cursor-copy items-center gap-1 rounded-sm font-mono text-xs hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                type="button"
                :aria-label="`Copy seed ${row.original.seed}`"
                title="Copy seed"
                @click.stop="copyText(row.original.seed, 'seed')"
              >
                <span>{{ row.original.seed }}</span>
                <Copy class="seed-copy-icon size-3" aria-hidden="true" />
              </button>
              <span v-else class="text-muted-foreground">-</span>
            </td>
            <td class="table-cell col-dimensions">{{ formatDimensions(row.original) }}</td>
            <td class="table-cell col-mtime">{{ formatDate(row.original.mtime) }}</td>
            <td class="table-cell col-actions">
              <DropdownMenu v-model:open="rowMenuOpen[row.original.path]">
                <DropdownMenuTrigger as-child>
                  <Button variant="ghost" size="icon-sm" aria-label="Row actions" @click.stop>
                    <MoreHorizontal class="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="openImage(row.original)">
                    <ExternalLink class="size-4" /> Open image
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="copyText(row.original.path, 'path')">
                    <Copy class="size-4" /> Copy path
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="row.original.seed" @click="copyText(row.original.seed, 'seed')">
                    <Copy class="size-4" /> Copy seed
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="row.original.has_prompt" @select="(event: Event) => handleCopyDetailSelect(event, row.original, 'prompt')">
                    <Copy class="size-4" /> Copy prompt
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="row.original.has_negative" @select="(event: Event) => handleCopyDetailSelect(event, row.original, 'negative')">
                    <Copy class="size-4" /> Copy negative
                  </DropdownMenuItem>
                  <DropdownMenuItem v-if="row.original.has_lora" @select="(event: Event) => handleCopyDetailSelect(event, row.original, 'loras')">
                    <Copy class="size-4" /> Copy LoRA list
                  </DropdownMenuItem>
                  <DropdownMenuItem @select="(event: Event) => handleCopyDetailSelect(event, row.original, 'metadata')">
                    <Copy class="size-4" /> Copy full metadata
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </td>
          </tr>
        </tbody>
      </table>
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
  gap: 12px;
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.inspector-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}

.inspector-search {
  width: min(100%, 520px);
  min-width: 280px;
}

.table-shell {
  min-height: 0;
  flex: 1;
  overflow: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--background));
}

.inspector-table {
  width: 100%;
  min-width: 1100px;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 13px;
}

.table-head {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 40px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--muted) / 0.72);
  color: hsl(var(--muted-foreground));
  text-align: left;
  vertical-align: middle;
}

.table-row {
  border-bottom: 1px solid hsl(var(--border));
}

.table-row:hover,
.table-row.selected {
  background: hsl(var(--accent) / 0.42);
}

.table-cell {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  padding: 8px;
  vertical-align: middle;
}

.col-thumbnail {
  width: 64px;
}

.col-name {
  width: 250px;
}

.col-model {
  width: 145px;
}

.col-seed {
  width: 110px;
}

.col-dimensions {
  width: 96px;
}

.col-mtime {
  width: 150px;
}

.col-prompt {
  width: 330px;
}

.col-actions {
  width: 56px;
  text-align: right;
}

.thumb-button {
  display: block;
  height: 44px;
  width: 44px;
  overflow: hidden;
  border-radius: 6px;
  border: 1px solid hsl(var(--border));
  background: hsl(var(--muted));
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
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.file-name-trigger {
  color: hsl(var(--foreground));
  font-weight: 500;
}

.folder-path-trigger {
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.folder-path-trigger:hover,
.prompt-trigger:hover {
  color: hsl(var(--foreground));
}

.prompt-trigger {
  color: hsl(var(--foreground));
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
  background: hsl(var(--muted));
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--foreground));
}
</style>
