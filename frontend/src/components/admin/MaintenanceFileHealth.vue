<script setup lang="ts">
import { Bug, Info, Loader2, ShieldCheck } from "lucide-vue-next";
import type { FileHealthRun } from "@/services/api";
import Button from "@/components/ui/Button.vue";
import Separator from "@/components/ui/Separator.vue";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

defineProps<{
  run?: FileHealthRun | null;
  pending?: boolean;
}>();

defineEmits<{
  runChecks: [];
}>();

const fileIssueKeys = [
  {
    key: "missing_source_files" as const,
    label: "Missing source files",
    description: "Queued or running metadata jobs whose source file no longer exists on disk.",
  },
  {
    key: "generated_image_missing" as const,
    label: "Missing image cache file",
    description: "Thumbnail or preview cache records marked ready while the cached file is missing.",
  },
  {
    key: "generated_image_abandoned" as const,
    label: "Abandoned image cache jobs",
    description: "Running thumbnail or preview cache jobs whose worker claim expired.",
  },
  {
    key: "metadata_mismatch" as const,
    label: "Metadata mismatch",
    description: "Cataloged assets marked done but missing a matching extracted metadata row.",
  },
  {
    key: "orphaned_work_item" as const,
    label: "Orphaned work item",
    description: "Metadata jobs that no longer have a matching catalog asset.",
  },
  {
    key: "generated_image_job_mismatch" as const,
    label: "Image cache job mismatch",
    description: "Finished thumbnail or preview jobs whose cache record is not ready.",
  },
] as const;

const repairKeys = [
  {
    key: "repaired" as const,
    label: "Repaired",
    description: "Rows corrected because the expected catalog or image cache state could be confirmed.",
  },
  {
    key: "requeued" as const,
    label: "Requeued",
    description: "Work sent back to metadata extraction or image cache preparation.",
  },
  {
    key: "failed" as const,
    label: "Marked failed",
    description: "Work marked failed because its source asset or image cache file could not be found.",
  },
  {
    key: "skipped" as const,
    label: "Marked skipped",
    description: "Image cache work made inapplicable by an offline, missing, or changed source.",
  },
  {
    key: "recovered" as const,
    label: "Recovered claims",
    description: "Expired image cache claims returned to a durable queued, skipped, or failed state.",
  },
  {
    key: "unchanged" as const,
    label: "Unchanged",
    description: "Problems counted in this run that did not need a state change.",
  },
] as const;
</script>

<template>
  <Card class="gap-0 py-0" aria-labelledby="file-health-heading">
    <CardContent class="p-5">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0 space-y-1">
          <div class="flex items-center gap-2">
            <ShieldCheck class="size-5 text-foreground/70" aria-hidden="true" />
            <h3 id="file-health-heading" class="font-semibold text-foreground">File health</h3>
          </div>
          <p class="max-w-2xl text-sm text-muted-foreground">
            Check catalog, metadata, and image cache consistency across all libraries.
          </p>
        </div>
        <Button variant="outline" size="lg" class="shrink-0 px-4" :disabled="pending" @click="$emit('runChecks')">
          <Loader2 v-if="pending" class="animate-spin" aria-hidden="true" />
          <Bug v-else aria-hidden="true" />
          {{ pending ? "Checking…" : "Run checks" }}
        </Button>
      </div>

      <div v-if="run" class="mt-5 grid gap-6 lg:grid-cols-2 lg:gap-8">
        <section aria-labelledby="current-issues-heading">
          <div class="flex items-baseline justify-between gap-3">
            <h4 id="current-issues-heading" class="text-sm font-semibold text-foreground">Issues found</h4>
            <p class="text-xs text-muted-foreground">
              {{ run.finished_at ? new Date(run.finished_at * 1000).toLocaleString() : "Check in progress" }}
            </p>
          </div>
          <dl class="mt-3 grid gap-1 text-sm">
            <div v-for="item in fileIssueKeys" :key="item.key" class="flex min-h-10 items-center justify-between gap-3">
              <dt class="flex min-w-0 items-center text-muted-foreground">
                <span>{{ item.label }}</span>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon-lg"
                      class="-my-2 shrink-0 text-muted-foreground hover:text-foreground"
                      :aria-label="`About ${item.label}`"
                    >
                      <Info class="size-3.5" aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="start" class="max-w-[260px]">{{ item.description }}</TooltipContent>
                </Tooltip>
              </dt>
              <dd class="font-semibold tabular-nums text-foreground">{{ run.issues[item.key] }}</dd>
            </div>
          </dl>
        </section>

        <section aria-labelledby="repair-results-heading">
          <h4 id="repair-results-heading" class="text-sm font-semibold text-foreground">Actions taken</h4>
          <dl class="mt-3 grid gap-1 text-sm sm:grid-cols-2 sm:gap-x-6">
            <div v-for="item in repairKeys" :key="item.key" class="flex min-h-10 items-center justify-between gap-3">
              <dt class="flex min-w-0 items-center text-muted-foreground">
                <span>{{ item.label }}</span>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon-lg"
                      class="-my-2 shrink-0 text-muted-foreground hover:text-foreground"
                      :aria-label="`About ${item.label}`"
                    >
                      <Info class="size-3.5" aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="start" class="max-w-[260px]">{{ item.description }}</TooltipContent>
                </Tooltip>
              </dt>
              <dd class="font-semibold tabular-nums text-foreground">{{ run.repairs[item.key] }}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div v-else class="mt-5 border-t border-border pt-5">
        <p class="text-sm font-medium text-foreground">No file-health check has run yet.</p>
        <p class="mt-1 max-w-2xl text-sm text-muted-foreground">
          Run a check to find consistency problems and see which records were repaired, requeued, or left unchanged.
        </p>
      </div>

      <Separator class="mt-5" />
      <p class="mt-3 text-xs text-muted-foreground">
        Checks may repair confirmed mismatches, requeue stale work, or mark invalid jobs failed. They never delete
        registered libraries or source files.
      </p>
    </CardContent>
  </Card>
</template>
