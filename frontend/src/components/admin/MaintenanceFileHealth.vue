<script setup lang="ts">
import { computed } from "vue";
import { Bug, Info, Loader2, ShieldCheck } from "lucide-vue-next";
import type { FileHealthRun } from "@/services/api";
import Button from "@/components/ui/Button.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = defineProps<{
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
    key: "file_index_ownership_mismatch" as const,
    label: "Search ownership mismatch",
    description: "Indexed media rows that no longer map to one exact active asset in a registered library.",
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

/** True when zero issues were found in the last run */
const allClear = computed(() => {
  if (!props.run) return false;
  return fileIssueKeys.every((item) => props.run!.issues[item.key] === 0);
});

/** Issue items with count > 0 */
const activeIssues = computed(() => (props.run ? fileIssueKeys.filter((item) => props.run!.issues[item.key] > 0) : []));

/** Repair items with count > 0 */
const activeRepairs = computed(() => (props.run ? repairKeys.filter((item) => props.run!.repairs[item.key] > 0) : []));

/** Total issue count */
const totalIssues = computed(() =>
  props.run ? fileIssueKeys.reduce((sum, item) => sum + props.run!.issues[item.key], 0) : 0,
);

/** Format finished_at as "Today at HH:MM" or "DD MMM at HH:MM" */
function formatRunTime(ts: number | null | undefined): string {
  if (!ts) return "Check in progress";
  const d = new Date(ts * 1000);
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (isToday) return `Today at ${time}`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + ` at ${time}`;
}
</script>

<template>
  <div class="rounded-xl border border-border bg-card" aria-labelledby="file-health-heading">
    <!-- Header -->
    <div class="flex flex-col gap-4 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex min-w-0 items-center gap-2">
        <ShieldCheck class="size-4 shrink-0 text-foreground/60" aria-hidden="true" />
        <div>
          <h3 id="file-health-heading" class="text-sm font-semibold text-foreground">File health</h3>
          <p class="mt-0.5 text-xs text-muted-foreground">
            Check catalog, metadata, and image cache consistency across all libraries.
          </p>
        </div>
      </div>
      <Button
        variant="outline"
        class="shrink-0 border-border bg-card text-foreground shadow-sm hover:bg-muted/70"
        :disabled="pending"
        @click="$emit('runChecks')"
      >
        <Loader2 v-if="pending" class="animate-spin" aria-hidden="true" />
        <Bug v-else aria-hidden="true" />
        {{ pending ? "Checking…" : "Run checks" }}
      </Button>
    </div>

    <div class="px-5 py-4">
      <!-- No run yet -->
      <div v-if="!run">
        <p class="text-sm font-medium text-foreground">No file-health check has run yet.</p>
        <p class="mt-1 text-xs text-muted-foreground">
          Run a check to find consistency problems and see which records were repaired, requeued, or left unchanged.
        </p>
      </div>

      <!-- Run exists -->
      <template v-else>
        <!-- All clear (no issues) -->
        <div v-if="allClear" class="flex items-start gap-3">
          <span class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-success/15">
            <svg class="size-3 text-success" viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <path
                d="M2 6l3 3 5-5"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </span>
          <div class="min-w-0">
            <p class="text-sm font-medium text-foreground">No issues found</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Last checked: {{ formatRunTime(run.finished_at) }}
              <template v-if="activeRepairs.length > 0">
                · {{ activeRepairs.reduce((s, item) => s + run!.repairs[item.key], 0) }} item{{
                  activeRepairs.reduce((s, item) => s + run!.repairs[item.key], 0) !== 1 ? "s" : ""
                }}
                repaired
              </template>
              <template v-else> · No repairs needed </template>
            </p>
          </div>
        </div>

        <!-- Issues found -->
        <template v-else>
          <!-- Issue count banner -->
          <div
            class="mb-4 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5"
          >
            <span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-destructive/15">
              <svg class="size-3 text-destructive" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path d="M6 2v4M6 8.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              </svg>
            </span>
            <div class="min-w-0">
              <p class="text-xs font-medium text-destructive">
                {{ totalIssues }} issue{{ totalIssues !== 1 ? "s" : "" }} found
              </p>
              <p class="text-xs text-muted-foreground">Last checked: {{ formatRunTime(run.finished_at) }}</p>
            </div>
          </div>

          <div class="grid gap-6 lg:grid-cols-2">
            <!-- Issues section: only non-zero rows -->
            <section aria-labelledby="current-issues-heading">
              <h4
                id="current-issues-heading"
                class="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Issues
              </h4>
              <dl class="mt-2 divide-y divide-border text-sm">
                <div
                  v-for="item in activeIssues"
                  :key="item.key"
                  class="flex min-h-9 items-center justify-between gap-3"
                >
                  <dt class="flex min-w-0 items-center text-muted-foreground">
                    <span>{{ item.label }}</span>
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon"
                          class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground"
                          :aria-label="`About ${item.label}`"
                        >
                          <Info class="size-3" aria-hidden="true" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start" class="max-w-[260px]">
                        {{ item.description }}
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-destructive">{{ run.issues[item.key] }}</dd>
                </div>
              </dl>
            </section>

            <!-- Actions taken: only non-zero rows, hidden if nothing happened -->
            <section v-if="activeRepairs.length > 0" aria-labelledby="repair-results-heading">
              <h4
                id="repair-results-heading"
                class="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Actions taken
              </h4>
              <dl class="mt-2 divide-y divide-border text-sm">
                <div
                  v-for="item in activeRepairs"
                  :key="item.key"
                  class="flex min-h-9 items-center justify-between gap-3"
                >
                  <dt class="flex min-w-0 items-center text-muted-foreground">
                    <span>{{ item.label }}</span>
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <Button
                          variant="ghost"
                          size="icon"
                          class="-my-1 size-5 text-muted-foreground/60 hover:text-muted-foreground"
                          :aria-label="`About ${item.label}`"
                        >
                          <Info class="size-3" aria-hidden="true" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" align="start" class="max-w-[260px]">
                        {{ item.description }}
                      </TooltipContent>
                    </Tooltip>
                  </dt>
                  <dd class="font-semibold tabular-nums text-foreground">{{ run.repairs[item.key] }}</dd>
                </div>
              </dl>
            </section>
            <p v-else class="text-xs text-muted-foreground lg:pt-5">No repairs were made in this run.</p>
          </div>
        </template>
      </template>

      <!-- Footer note -->
      <p class="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
        Checks may repair confirmed mismatches, requeue stale work, or mark invalid jobs failed. They never delete
        registered libraries or source files.
      </p>
    </div>
  </div>
</template>
