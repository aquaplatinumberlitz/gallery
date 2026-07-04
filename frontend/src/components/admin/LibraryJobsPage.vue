<script setup lang="ts">
import { computed } from "vue";
import { ArrowLeft, RefreshCw } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import { useLibraryJobsQuery } from "@/composables/admin/useLibraryJobsQuery";
import { useLibraryQuery } from "@/composables/admin/useLibraryQuery";
import JobList from "./JobList.vue";

const props = defineProps<{ id: number }>();
const FULL_JOB_LIMIT = 200;

const libraryId = computed(() => (Number.isFinite(props.id) && props.id > 0 ? props.id : null));
const libraryQuery = useLibraryQuery(libraryId);
const jobsQuery = useLibraryJobsQuery(libraryId, FULL_JOB_LIMIT);
useLibraryEvents();

const library = computed(() => libraryQuery.data.value ?? null);
const jobs = computed(() => jobsQuery.data.value ?? []);
</script>

<template>
  <main
    class="h-full overflow-y-auto rounded-xl border border-border bg-card p-4 sm:p-6"
    aria-labelledby="library-jobs-heading"
  >
    <div class="mx-auto max-w-6xl space-y-6">
      <ButtonLink :to="{ name: 'admin-library-detail', params: { id } }" variant="ghost" class="-ml-3">
        <ArrowLeft /> Library details
      </ButtonLink>

      <div
        v-if="!libraryId || libraryQuery.isError.value"
        class="grid min-h-72 place-items-center rounded-md border border-dashed border-border p-8 text-center"
      >
        <div class="space-y-3">
          <h2 class="text-xl font-semibold">Library not found</h2>
          <p class="text-sm text-muted-foreground">It may have been unregistered or the link is invalid.</p>
          <ButtonLink to="/admin/libraries" variant="outline">Back to libraries</ButtonLink>
        </div>
      </div>

      <template v-else>
        <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <p class="text-sm font-medium text-muted-foreground">Library administration</p>
            <h2 id="library-jobs-heading" class="truncate text-2xl font-semibold tracking-tight">
              {{ library?.name ?? "Library" }} job history
            </h2>
            <p class="mt-1 text-sm text-muted-foreground">Showing up to {{ FULL_JOB_LIMIT }} most recent jobs.</p>
          </div>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="outline"
                size="icon"
                aria-label="Refresh job history"
                :disabled="jobsQuery.isFetching.value"
                @click="jobsQuery.refetch()"
              >
                <RefreshCw :class="jobsQuery.isFetching.value ? 'animate-spin' : ''" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" align="end" class="max-w-[220px]">
              Reload this library's scan, metadata, and generated-image jobs.
            </TooltipContent>
          </Tooltip>
        </header>

        <section class="rounded-md border border-border bg-background p-5">
          <div v-if="libraryQuery.isPending.value || jobsQuery.isPending.value" class="space-y-3">
            <Skeleton v-for="item in 8" :key="item" class="h-16 w-full" />
          </div>

          <JobList v-else :jobs="jobs" variant="full" />

          <template v-if="jobs.length >= FULL_JOB_LIMIT">
            <Separator class="my-4" />
            <p class="text-sm text-muted-foreground">Only the latest {{ FULL_JOB_LIMIT }} jobs are shown.</p>
          </template>
        </section>
      </template>
    </div>
  </main>
</template>
