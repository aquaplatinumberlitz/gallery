<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { Library, Plus, RefreshCw, ScanLine, AlertTriangle } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLibrariesQuery } from "@/composables/admin/useLibrariesQuery";
import { useGalleryStatsQuery } from "@/composables/admin/useGalleryStatsQuery";
import { useJobsQuery } from "@/composables/admin/useJobsQuery";
import { useLibraryMutations } from "@/composables/admin/useLibraryMutations";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useGalleryStore } from "@/stores/gallery";
import type { RegisteredLibrary } from "@/types";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import LibraryActionMenu from "./LibraryActionMenu.vue";
import LibraryStatusBadge from "./LibraryStatusBadge.vue";
import LibrarySummaryPanel from "./LibrarySummaryPanel.vue";
import LibraryCreateDialog from "./dialogs/LibraryCreateDialog.vue";
import LibraryEditDialog from "./dialogs/LibraryEditDialog.vue";
import LibraryDeleteConfirmDialog from "./dialogs/LibraryDeleteConfirmDialog.vue";

const router = useRouter();
const galleryStore = useGalleryStore();
const librariesQuery = useLibrariesQuery();
const statsQuery = useGalleryStatsQuery();
const jobsQuery = useJobsQuery();
const { scanMutation, scanAllMutation, repairMutation, unregisterMutation } = useLibraryMutations();
useLibraryEvents();

const createOpen = ref(false);
const editLibrary = ref<RegisteredLibrary | null>(null);
const deleteLibrary = ref<RegisteredLibrary | null>(null);
const libraries = computed(() => librariesQuery.data.value ?? []);
const activeJobs = computed(
  () => jobsQuery.data.value?.filter((job) => job.state === "queued" || job.state === "running").length ?? 0,
);
const actionPending = computed(
  () => scanMutation.isPending.value || repairMutation.isPending.value || unregisterMutation.isPending.value,
);

function formatBytes(bytes?: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function useInGallery(library: RegisteredLibrary) {
  const path = library.import_paths[0]?.path;
  if (!path) return;
  if (await galleryStore.setRootPath(path)) await router.push("/");
}

async function confirmUnregister() {
  if (!deleteLibrary.value) return;
  await unregisterMutation.mutateAsync(deleteLibrary.value.id);
  deleteLibrary.value = null;
}

function created(library: RegisteredLibrary) {
  createOpen.value = false;
  void router.push({ name: "admin-library-detail", params: { id: library.id } });
}
</script>

<template>
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="libraries-heading">
    <div class="mx-auto max-w-7xl space-y-6">
      <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium text-muted-foreground">Administration</p>
          <h2 id="libraries-heading" class="text-2xl font-semibold tracking-tight">Libraries</h2>
          <p class="mt-1 text-sm text-muted-foreground">Register folders, monitor imports, and maintain the catalog.</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            variant="outline"
            :disabled="scanAllMutation.isPending.value || libraries.length === 0"
            @click="scanAllMutation.mutate()"
          >
            <ScanLine /> {{ scanAllMutation.isPending.value ? "Queueing…" : "Scan all" }}
          </Button>
          <Button @click="createOpen = true"><Plus /> Add library</Button>
        </div>
      </header>

      <section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Gallery statistics">
        <div class="rounded-md border bg-background p-4">
          <p class="text-xs text-muted-foreground">Libraries</p>
          <p class="mt-1 text-2xl font-semibold">{{ statsQuery.data.value?.library_count ?? libraries.length }}</p>
        </div>
        <div class="rounded-md border bg-background p-4">
          <p class="text-xs text-muted-foreground">Photos</p>
          <p class="mt-1 text-2xl font-semibold">{{ formatAssetCount(statsQuery.data.value?.photos) }}</p>
        </div>
        <div class="rounded-md border bg-background p-4">
          <p class="text-xs text-muted-foreground">Videos / Usage</p>
          <p class="mt-1 text-lg font-semibold">
            {{ formatAssetCount(statsQuery.data.value?.videos) }} ·
            {{ formatBytes(statsQuery.data.value?.usage_bytes) }}
          </p>
        </div>
        <div class="rounded-md border bg-background p-4">
          <p class="text-xs text-muted-foreground">Active queue</p>
          <p class="mt-1 text-2xl font-semibold">{{ activeJobs }}</p>
        </div>
      </section>

      <div v-if="librariesQuery.isError.value" class="rounded-md border border-destructive/40 bg-destructive/10 p-5">
        <div class="flex items-start gap-3">
          <AlertTriangle class="mt-0.5 size-5 text-destructive" />
          <div class="flex-1">
            <h3 class="font-medium">Could not load libraries</h3>
            <p class="text-sm text-muted-foreground">Check the backend connection and try again.</p>
          </div>
          <Button variant="outline" size="sm" @click="librariesQuery.refetch()"><RefreshCw /> Retry</Button>
        </div>
      </div>

      <div v-else-if="librariesQuery.isPending.value" class="space-y-3">
        <Skeleton v-for="row in 4" :key="row" class="h-24 w-full" />
      </div>

      <section
        v-else-if="libraries.length === 0"
        class="grid min-h-72 place-items-center rounded-md border border-dashed p-8 text-center"
      >
        <div class="max-w-md space-y-3">
          <Library class="mx-auto size-10 text-muted-foreground" />
          <h3 class="text-lg font-semibold">No libraries registered</h3>
          <p class="text-sm text-muted-foreground">Register a library before browsing or indexing local assets.</p>
          <Button @click="createOpen = true"><Plus /> Add library</Button>
        </div>
      </section>

      <template v-else>
        <div class="hidden overflow-hidden rounded-md border lg:block">
          <Table>
            <TableHeader
              >
<TableRow
                >
<TableHead>Library</TableHead><TableHead>Import paths</TableHead><TableHead>Status</TableHead
                ><TableHead>Assets / Stats</TableHead><TableHead>Last scan</TableHead><TableHead>Updated</TableHead
                ><TableHead class="w-14"><span class="sr-only">Actions</span></TableHead>
</TableRow
              >
</TableHeader
            >
            <TableBody>
              <TableRow v-for="library in libraries" :key="library.id">
                <TableCell
                  >
<button
                    class="text-left font-medium hover:underline"
                    @click="router.push(`/admin/libraries/${library.id}`)"
                  >
                    {{ library.name }}
                  </button>
                  <div
                    v-if="library.last_error"
                    class="mt-1 flex items-center gap-1 text-xs text-destructive"
                    :title="library.last_error"
                  >
                    <AlertTriangle class="size-3" /> Last scan failed
                  </div>
</TableCell
                >
                <TableCell
                  >
<div class="max-w-72 space-y-1">
                    <p
                      v-for="path in library.import_paths.slice(0, 2)"
                      :key="path.id"
                      class="truncate font-mono text-xs"
                      :title="path.path"
                    >
                      {{ path.path }}
                    </p>
                    <p v-if="library.import_paths.length > 2" class="text-xs text-muted-foreground">
                      +{{ library.import_paths.length - 2 }} paths
                    </p>
                  </div>
</TableCell
                >
                <TableCell><LibraryStatusBadge :library="library" /></TableCell>
                <TableCell><LibrarySummaryPanel :library-id="library.id" /></TableCell>
                <TableCell class="text-sm">{{ formatLibraryTimestamp(library.last_scan_at) }}</TableCell>
                <TableCell class="text-sm">{{ formatLibraryTimestamp(library.updated_at) }}</TableCell>
                <TableCell
                  >
<LibraryActionMenu
                    :disabled="actionPending"
                    @view="router.push(`/admin/libraries/${library.id}`)"
                    @use="useInGallery(library)"
                    @edit="editLibrary = library"
                    @scan="scanMutation.mutate(library.id)"
                    @repair="repairMutation.mutate(library.id)"
                    @unregister="deleteLibrary = library"
                />
</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <div class="grid gap-3 lg:hidden">
          <article v-for="library in libraries" :key="library.id" class="rounded-md border bg-background p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <button
                  class="truncate text-left font-semibold hover:underline"
                  @click="router.push(`/admin/libraries/${library.id}`)"
                >
                  {{ library.name }}
                </button>
                <p class="mt-1 truncate font-mono text-xs text-muted-foreground" :title="library.import_paths[0]?.path">
                  {{ library.import_paths[0]?.path }}
                </p>
                <p v-if="library.import_paths.length > 1" class="text-xs text-muted-foreground">
                  +{{ library.import_paths.length - 1 }} paths
                </p>
              </div>
              <LibraryActionMenu
                :disabled="actionPending"
                @view="router.push(`/admin/libraries/${library.id}`)"
                @use="useInGallery(library)"
                @edit="editLibrary = library"
                @scan="scanMutation.mutate(library.id)"
                @repair="repairMutation.mutate(library.id)"
                @unregister="deleteLibrary = library"
              />
            </div>
            <div class="mt-4 flex items-center justify-between gap-3">
              <LibraryStatusBadge :library="library" /><span class="text-xs text-muted-foreground"
                >Scanned {{ formatLibraryTimestamp(library.last_scan_at) }}</span
              >
            </div>
            <div class="mt-4"><LibrarySummaryPanel :library-id="library.id" /></div>
            <p v-if="library.last_error" class="mt-3 line-clamp-2 text-xs text-destructive">{{ library.last_error }}</p>
          </article>
        </div>
      </template>
    </div>

    <LibraryCreateDialog v-model:open="createOpen" :libraries="libraries" @created="created" />
    <LibraryEditDialog
      :open="Boolean(editLibrary)"
      :library="editLibrary"
      :libraries="libraries"
      @update:open="!$event && (editLibrary = null)"
      @updated="editLibrary = null"
    />
    <LibraryDeleteConfirmDialog
      :open="Boolean(deleteLibrary)"
      :library="deleteLibrary"
      :estimated-assets="deleteLibrary?.asset_count"
      :pending="unregisterMutation.isPending.value"
      @update:open="!$event && (deleteLibrary = null)"
      @confirm="confirmUnregister"
    />
  </main>
</template>
