<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { Library, Plus, RefreshCw, AlertTriangle, FolderOpen, Folder, Images, ImageIcon, Film, HardDrive, Briefcase } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLibrariesQuery } from "@/composables/admin/useLibrariesQuery";
import { useGalleryStatsQuery } from "@/composables/admin/useGalleryStatsQuery";
import { useJobsQuery } from "@/composables/admin/useJobsQuery";
import { useLibraryMutations } from "@/composables/admin/useLibraryMutations";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useLibraryStatusBatchQuery } from "@/composables/admin/useLibraryStatusBatchQuery";
import { useGalleryStore } from "@/stores/gallery";
import type { RegisteredLibrary } from "@/types";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import { formatBytes } from "@/utils/format";
import { STATUS_CONTRACT_ERROR_MESSAGE } from "@/lib/catalog/contractGuard";
import type { UnifiedStatus } from "@/lib/catalog/status";
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
const statusBatchQuery = useLibraryStatusBatchQuery();
const { scanMutation, scanAllMutation, unregisterMutation } = useLibraryMutations();
useLibraryEvents();

const createOpen = ref(false);
const editLibrary = ref<RegisteredLibrary | null>(null);
const deleteLibrary = ref<RegisteredLibrary | null>(null);
const libraries = computed(() => librariesQuery.data.value ?? []);
const statusByLibrary = computed(() => statusBatchQuery.statusByLibrary.value);
const totalMediaFiles = computed(() => {
  const stats = statsQuery.data.value;
  return stats ? stats.photos + stats.videos : undefined;
});
const activeJobs = computed(
  () => jobsQuery.data.value?.filter((job) => job.state === "queued" || job.state === "running").length ?? 0,
);
const actionPending = computed(() => scanMutation.isPending.value || unregisterMutation.isPending.value);
const statusContractError = computed(() => Boolean(statusBatchQuery.contractError.value));

function statusFor(library: RegisteredLibrary): UnifiedStatus | null {
  return statusByLibrary.value.get(library.id) ?? null;
}

function lastScanAt(library: RegisteredLibrary): number | null {
  return statusFor(library)?.last_scan_at ?? library.last_scan_at;
}

function lastIndexAt(library: RegisteredLibrary): number | null {
  return statusFor(library)?.last_index_at ?? null;
}

function scanErrorMessage(library: RegisteredLibrary): string | null {
  const status = statusFor(library);
  if (status?.latest_issue && status.latest_issue.source === "scan") {
    return status.latest_issue.message;
  }
  return library.last_error;
}

async function useInGallery(library: RegisteredLibrary) {
  if (galleryStore.setActiveLibrary(library)) await router.push("/");
}

async function confirmUnregister() {
  if (!deleteLibrary.value) return;
  try {
    await unregisterMutation.mutateAsync(deleteLibrary.value.id);
    deleteLibrary.value = null;
  } catch {
    // Error is already handled by the mutation's onError handler (toast)
  }
}

function created(library: RegisteredLibrary) {
  createOpen.value = false;
  galleryStore.setActiveLibrary(library);
  void router.push({ name: "admin-library-detail", params: { id: library.id } });
}
</script>

<template>
  <main class="llp-main h-full overflow-y-auto text-foreground" aria-labelledby="libraries-heading">
    <div class="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 space-y-8">
      <!-- ═══════════════════════════════════════════
           PAGE HEADER
      ════════════════════════════════════════════ -->
      <header class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex min-w-0 items-center gap-3.5">
          <div class="flex size-11 shrink-0 items-center justify-center rounded-lg border border-border bg-muted">
            <Library class="size-5 text-foreground/60" />
          </div>
          <div>
            <h1 id="libraries-heading" class="text-2xl font-semibold tracking-tight text-foreground">Libraries</h1>
            <p class="mt-0.5 text-xs text-muted-foreground">Register folders, monitor imports, and maintain the file catalog.</p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            class="border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
            :disabled="scanAllMutation.isPending.value || libraries.length === 0"
            @click="scanAllMutation.mutate()"
          >
            <RefreshCw class="mr-1.5 size-4" :class="scanAllMutation.isPending.value ? 'animate-spin' : ''" />
            {{ scanAllMutation.isPending.value ? "Queueing…" : "Update all" }}
          </Button>
          <Button @click="createOpen = true">
            <Plus class="mr-1.5 size-4" /> Add library
          </Button>
        </div>
      </header>

      <!-- ═══════════════════════════════════════════
           STATS BAR
      ════════════════════════════════════════════ -->
      <section aria-label="Gallery statistics">
        <dl class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="llp-stat-card rounded-xl border border-border bg-card p-4">
            <dt class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Library class="size-3.5 shrink-0" aria-hidden="true" /> Libraries
            </dt>
            <dd class="mt-2 text-2xl font-semibold tabular-nums text-foreground">
              {{ statsQuery.data.value?.library_count ?? libraries.length }}
            </dd>
          </div>
          <div class="llp-stat-card rounded-xl border border-border bg-card p-4">
            <dt class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Images class="size-3.5 shrink-0" aria-hidden="true" /> Media files
            </dt>
            <dd class="mt-2 text-2xl font-semibold tabular-nums text-foreground">
              {{ formatAssetCount(totalMediaFiles) }}
            </dd>
            <p class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs tabular-nums text-muted-foreground">
              <span class="inline-flex items-center gap-1">
                <ImageIcon class="size-3 shrink-0" aria-hidden="true" />
                {{ formatAssetCount(statsQuery.data.value?.photos) }} photos
              </span>
              <span class="inline-flex items-center gap-1">
                <Film class="size-3 shrink-0" aria-hidden="true" />
                {{ formatAssetCount(statsQuery.data.value?.videos) }} videos
              </span>
            </p>
          </div>

          <div class="llp-stat-card rounded-xl border border-border bg-card p-4">
            <dt class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <HardDrive class="size-3.5 shrink-0" aria-hidden="true" /> Storage used
            </dt>
            <dd class="mt-2 text-2xl font-semibold tabular-nums text-foreground">
              {{ formatBytes(statsQuery.data.value?.usage_bytes) }}
            </dd>
          </div>
          <div class="llp-stat-card rounded-xl border border-border bg-card p-4">
            <dt class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Briefcase class="size-3.5 shrink-0" aria-hidden="true" /> Active jobs
            </dt>
            <dd
              class="mt-2 text-2xl font-semibold tabular-nums"
              :class="activeJobs > 0 ? 'text-warning' : 'text-foreground'"
            >
              {{ activeJobs }}
            </dd>
          </div>
        </dl>
      </section>

      <!-- Contract error -->
      <div
        v-if="statusContractError"
        class="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"
        role="status"
      >
        {{ STATUS_CONTRACT_ERROR_MESSAGE }}
      </div>

      <!-- ═══════════════════════════════════════════
           LIBRARY LIST
      ════════════════════════════════════════════ -->

      <!-- Load error -->
      <div v-if="librariesQuery.isError.value" class="rounded-lg border border-destructive/40 bg-destructive/5 p-5">
        <div class="flex items-start gap-3">
          <AlertTriangle class="mt-0.5 size-5 shrink-0 text-destructive" />
          <div class="flex-1">
            <h3 class="font-medium">Could not load libraries</h3>
            <p class="mt-0.5 text-sm text-muted-foreground">Check the backend connection and try again.</p>
          </div>
          <Button variant="outline" size="sm" @click="librariesQuery.refetch()">
            <RefreshCw class="mr-1.5 size-3.5" /> Retry
          </Button>
        </div>
      </div>

      <!-- Skeleton -->
      <div v-else-if="librariesQuery.isPending.value" class="space-y-2">
        <Skeleton v-for="row in 4" :key="row" class="h-16 w-full rounded-xl" />
      </div>

      <!-- Empty state -->
      <section
        v-else-if="libraries.length === 0"
        class="grid min-h-64 place-items-center rounded-xl border border-dashed border-border bg-card p-8 text-center"
      >
        <div class="max-w-sm space-y-3">
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-muted">
            <FolderOpen class="size-6 text-muted-foreground" />
          </div>
          <h3 class="text-base font-semibold">No libraries registered</h3>
          <p class="text-sm text-muted-foreground">Register a library before browsing or indexing local media.</p>
          <Button @click="createOpen = true"><Plus class="mr-1.5 size-4" /> Add library</Button>
        </div>
      </section>

      <!-- Desktop table -->
      <template v-else>
        <div class="hidden overflow-hidden rounded-xl border border-border bg-card lg:block">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border bg-muted/40">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Library</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Folder</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">File catalog</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Catalog updated</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Metadata updated</th>
                <th class="w-12 px-4 py-3"><span class="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr
                v-for="library in libraries"
                :key="library.id"
                class="group transition-colors hover:bg-muted/30"
              >
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2.5">
                    <div class="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                      <Folder class="size-3.5 text-foreground/60" aria-hidden="true" />
                    </div>
                    <div>
                      <button
                        class="font-semibold text-foreground hover:underline"
                        @click="router.push(`/admin/libraries/${library.id}`)"
                      >
                        {{ library.name }}
                      </button>
                      <Tooltip v-if="scanErrorMessage(library)">
                        <TooltipTrigger as-child>
                          <div class="mt-0.5 flex items-center gap-1 text-xs text-destructive">
                            <AlertTriangle class="size-3" /> Update failed
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="top" align="start" class="max-w-[260px]">
                          {{ scanErrorMessage(library) }}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <div class="max-w-64 space-y-0.5">
                    <OverflowTooltip
                      v-for="path in library.import_paths.slice(0, 2)"
                      :key="path.id"
                      as="p"
                      :text="path.path"
                      class="font-mono text-xs text-muted-foreground"
                      align="start"
                    >
                      {{ path.path }}
                    </OverflowTooltip>
                    <p v-if="library.import_paths.length > 2" class="text-xs text-muted-foreground">
                      +{{ library.import_paths.length - 2 }} paths
                    </p>
                  </div>
                </td>
                <td class="px-4 py-3"><LibraryStatusBadge :status="statusFor(library)" /></td>
                <td class="px-4 py-3"><LibrarySummaryPanel :status="statusFor(library)" /></td>
                <td class="px-4 py-3 text-xs text-muted-foreground">{{ formatLibraryTimestamp(lastScanAt(library)) }}</td>
                <td class="px-4 py-3 text-xs text-muted-foreground">{{ formatLibraryTimestamp(lastIndexAt(library)) }}</td>
                <td class="px-4 py-3">
                  <LibraryActionMenu
                    :disabled="actionPending"
                    @view="router.push(`/admin/libraries/${library.id}`)"
                    @use="useInGallery(library)"
                    @edit="editLibrary = library"
                    @scan="scanMutation.mutate({ id: library.id })"
                    @unregister="deleteLibrary = library"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Mobile cards -->
        <div class="grid gap-3 lg:hidden">
          <div
            v-for="library in libraries"
            :key="library.id"
            class="rounded-xl border border-border bg-card p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-3">
                <div class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-muted">
                  <Folder class="size-4 text-foreground/60" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <button
                    class="truncate text-left font-semibold text-foreground hover:underline"
                    @click="router.push(`/admin/libraries/${library.id}`)"
                  >
                    {{ library.name }}
                  </button>
                  <OverflowTooltip
                    as="p"
                    :text="library.import_paths[0]?.path"
                    class="mt-0.5 font-mono text-xs text-muted-foreground"
                    align="start"
                  >
                    {{ library.import_paths[0]?.path }}
                  </OverflowTooltip>
                  <p v-if="library.import_paths.length > 1" class="text-xs text-muted-foreground">
                    +{{ library.import_paths.length - 1 }} paths
                  </p>
                </div>
              </div>
              <LibraryActionMenu
                :disabled="actionPending"
                @view="router.push(`/admin/libraries/${library.id}`)"
                @use="useInGallery(library)"
                @edit="editLibrary = library"
                @scan="scanMutation.mutate({ id: library.id })"
                @unregister="deleteLibrary = library"
              />
            </div>
            <div class="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
              <LibraryStatusBadge :status="statusFor(library)" />
              <span class="text-xs text-muted-foreground">
                Updated {{ formatLibraryTimestamp(lastScanAt(library)) }}
              </span>
            </div>
            <div class="mt-3"><LibrarySummaryPanel :status="statusFor(library)" /></div>
            <p v-if="scanErrorMessage(library)" class="mt-2 flex items-center gap-1 text-xs text-destructive">
              <AlertTriangle class="size-3 shrink-0" /> {{ scanErrorMessage(library) }}
            </p>
          </div>
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

<style scoped>
.llp-main {
  background-color: var(--background);
}

/* Stat card subtle hover lift — same as detail page */
.llp-stat-card {
  transition: box-shadow 150ms ease, transform 150ms ease;
}
.llp-stat-card:hover {
  box-shadow: var(--gallery-shadow-sm);
  transform: translateY(-1px);
}
@media (prefers-reduced-motion: reduce) {
  .llp-stat-card { transition: none; transform: none !important; }
}
</style>
