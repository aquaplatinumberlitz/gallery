<script setup lang="ts">
import { computed } from "vue";
import { ArrowLeft, RefreshCw } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import Separator from "@/components/ui/Separator.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useJobsQuery } from "@/composables/admin/useJobsQuery";
import { useLibraryEvents } from "@/composables/admin/useLibraryEvents";
import JobList from "./JobList.vue";

const FULL_JOB_LIMIT = 500;
const jobsQuery = useJobsQuery(FULL_JOB_LIMIT);
const jobs = computed(() => jobsQuery.data.value ?? []);
useLibraryEvents();
</script>

<template>
  <main class="h-full overflow-y-auto rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="jobs-heading">
    <div class="mx-auto max-w-6xl space-y-6">
      <ButtonLink to="/admin/maintenance" variant="ghost" class="-ml-3"> <ArrowLeft /> Maintenance </ButtonLink>

      <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0">
          <p class="text-sm font-medium text-muted-foreground">Administration</p>
          <h2 id="jobs-heading" class="truncate text-2xl font-semibold tracking-tight">Job history</h2>
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
            Reload recent file catalog, metadata, and thumbnail jobs.
          </TooltipContent>
        </Tooltip>
      </header>

      <section class="rounded-md border bg-background p-5">
        <div v-if="jobsQuery.isPending.value" class="space-y-3">
          <Skeleton v-for="item in 8" :key="item" class="h-16 w-full" />
        </div>
        <JobList v-else :jobs="jobs" variant="full" show-library />

        <template v-if="jobs.length >= FULL_JOB_LIMIT">
          <Separator class="my-4" />
          <p class="text-sm text-muted-foreground">Only the latest {{ FULL_JOB_LIMIT }} jobs are shown.</p>
        </template>
      </section>
    </div>
  </main>
</template>
