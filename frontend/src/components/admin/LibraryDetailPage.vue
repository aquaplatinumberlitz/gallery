<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeft, Copy, Images, Pencil, Play, RefreshCw, Trash2, Wrench, AlertTriangle } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Separator from "@/components/ui/Separator.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import { useLibrariesQuery } from "@/composables/admin/useLibrariesQuery";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useLibraryJobsQuery } from "@/composables/admin/useLibraryJobsQuery";
import { useLibraryMutations } from "@/composables/admin/useLibraryMutations";
import { useLibraryProgressQuery } from "@/composables/admin/useLibraryProgressQuery";
import { useLibraryQuery } from "@/composables/admin/useLibraryQuery";
import { useLibraryStatsQuery } from "@/composables/admin/useLibraryStatsQuery";
import { useToast } from "@/composables/useToast";
import { useGalleryStore } from "@/stores/gallery";
import { formatAssetCount, formatLibraryTimestamp } from "@/utils/libraryStatus";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import LibraryStatusBadge from "./LibraryStatusBadge.vue";
import LibraryEditDialog from "./dialogs/LibraryEditDialog.vue";
import LibraryDeleteConfirmDialog from "./dialogs/LibraryDeleteConfirmDialog.vue";

const props = defineProps<{ id: number }>();
const router = useRouter();
const toast = useToast();
const galleryStore = useGalleryStore();
const libraryId = computed(() => (Number.isFinite(props.id) && props.id > 0 ? props.id : null));
const libraryQuery = useLibraryQuery(libraryId);
const progressQuery = useLibraryProgressQuery(libraryId);
const statsQuery = useLibraryStatsQuery(libraryId);
const jobsQuery = useLibraryJobsQuery(libraryId);
const librariesQuery = useLibrariesQuery();
const { scanMutation, repairMutation, unregisterMutation } = useLibraryMutations();
useLibraryEvents();

const editOpen = ref(false);
const deleteOpen = ref(false);
const library = computed(() => libraryQuery.data.value ?? null);
const busy = computed(() => scanMutation.isPending.value || repairMutation.isPending.value);

function formatBytes(bytes?: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function useInGallery() {
  const path = library.value?.import_paths[0]?.path;
  if (!path) return;
  if (await galleryStore.setRootPath(path)) await router.push("/");
}

async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path);
    toast.success("Path copied");
  } catch {
    toast.error("Could not copy path");
  }
}

async function confirmUnregister() {
  if (!library.value) return;
  await unregisterMutation.mutateAsync(library.value.id);
  deleteOpen.value = false;
  await router.push("/admin/libraries");
}

function jobProgress(current: number, total: number | null): string {
  return total && total > 0 ? `${formatAssetCount(current)} / ${formatAssetCount(total)}` : formatAssetCount(current);
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
              <LibraryStatusBadge :library="library" :progress="progressQuery.data.value" />
            </div>
            <p class="mt-1 truncate font-mono text-xs text-muted-foreground" :title="library.root_path">
              {{ library.root_path }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" @click="useInGallery"><Images /> Use in gallery</Button
            ><Button variant="outline" @click="editOpen = true"><Pencil /> Edit</Button
            ><Button variant="outline" :disabled="busy" @click="scanMutation.mutate(library.id)"><Play /> Scan</Button
            ><Button variant="outline" :disabled="busy" @click="repairMutation.mutate(library.id)"
              >
<Wrench /> Repair
</Button
            ><Button variant="destructive" @click="deleteOpen = true"><Trash2 /> Unregister</Button>
          </div>
        </header>

        <section v-if="library.last_error" class="rounded-md border border-destructive/40 bg-destructive/10 p-4">
          <div class="flex gap-3">
            <AlertTriangle class="mt-0.5 size-5 text-destructive" />
            <div>
              <h3 class="font-medium text-destructive">Last error</h3>
              <p class="mt-1 whitespace-pre-wrap text-sm">{{ library.last_error }}</p>
            </div>
          </div>
        </section>

        <div class="grid gap-4 md:grid-cols-2">
          <section class="rounded-md border bg-background p-5">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold">Status and progress</h3>
              <Button variant="ghost" size="icon" aria-label="Refresh progress" @click="progressQuery.refetch()"
                >
<RefreshCw
              />
</Button>
            </div>
            <div class="mt-5"><LibraryProgressBar :progress="progressQuery.data.value" /></div>
            <p v-if="progressQuery.data.value" class="mt-3 text-xs text-muted-foreground">
              {{ progressQuery.data.value.discovery_complete ? "Discovery complete" : "Discovery in progress"
              }}<span v-if="progressQuery.data.value.active_job_id">
                · Job #{{ progressQuery.data.value.active_job_id }}</span
              >
            </p>
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
                ><Button variant="ghost" size="icon" aria-label="Copy import path" @click="copyPath(path.path)"
                  >
<Copy
                />
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
            <Button variant="ghost" size="icon" aria-label="Refresh jobs" @click="jobsQuery.refetch()"
              >
<RefreshCw
            />
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
          <dl class="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt class="text-muted-foreground">Created</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(library.created_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Updated</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(library.updated_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">Last scan</dt>
              <dd class="mt-1">{{ formatLibraryTimestamp(library.last_scan_at) }}</dd>
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
      :estimated-assets="progressQuery.data.value?.estimated_assets"
      :pending="unregisterMutation.isPending.value"
      @confirm="confirmUnregister"
    />
  </main>
</template>
