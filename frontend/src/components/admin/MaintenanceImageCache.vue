<script setup lang="ts">
import { HardDrive, Info, RefreshCw } from "lucide-vue-next";
import type { GlobalRuntime } from "@/lib/catalog/status";
import Button from "@/components/ui/Button.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

defineProps<{
  runtime?: GlobalRuntime | null;
  runtimePending?: boolean;
  totalReady?: number | null;
  totalExpected?: number | null;
  summaryAvailable?: boolean;
  summaryPending?: boolean;
  summaryFetching?: boolean;
}>();

defineEmits<{
  refresh: [];
}>();
</script>

<template>
  <Card class="gap-0 py-0" aria-labelledby="image-cache-heading">
    <CardContent class="image-cache-content p-5">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 space-y-1">
          <div class="flex items-center gap-2">
            <HardDrive class="size-5 text-foreground/70" aria-hidden="true" />
            <h3 id="image-cache-heading" class="font-semibold text-foreground">Image cache</h3>
          </div>
          <p class="text-sm text-muted-foreground">Coverage and queue health for cached thumbnails and previews.</p>
        </div>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              variant="ghost"
              size="icon-lg"
              class="-my-2 -me-2 shrink-0"
              aria-label="Refresh image cache diagnostics"
              :disabled="summaryFetching"
              @click="$emit('refresh')"
            >
              <RefreshCw :class="summaryFetching ? 'animate-spin' : ''" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" align="end" class="max-w-[240px]">
            Reload image cache coverage. Queue health refreshes automatically while work is active.
          </TooltipContent>
        </Tooltip>
      </div>

      <div class="image-cache-sections mt-5 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section
          class="image-cache-section rounded-lg border border-border bg-muted/30 p-4"
          aria-labelledby="image-cache-coverage-heading"
        >
          <h4 id="image-cache-coverage-heading" class="text-sm font-semibold text-foreground">Coverage</h4>
          <div v-if="summaryAvailable" class="mt-3 space-y-3">
            <!-- Coverage % hero -->
            <div class="flex items-end justify-between gap-2">
              <div>
                <p
                  class="text-2xl font-semibold tabular-nums leading-none"
                  :class="
                    totalReady != null && totalExpected != null && totalExpected > 0
                      ? totalReady >= totalExpected
                        ? 'text-success'
                        : totalReady / totalExpected >= 0.9
                          ? 'text-warning'
                          : 'text-destructive'
                      : 'text-foreground'
                  "
                >
                  {{
                    totalReady != null && totalExpected != null && totalExpected > 0
                      ? Math.min(100, Math.round((totalReady / totalExpected) * 100)) + "%"
                      : "—"
                  }}
                </p>
                <p class="mt-1 text-xs text-muted-foreground tabular-nums">
                  {{ totalReady ?? "—" }} / {{ totalExpected ?? "—" }} files cached
                </p>
              </div>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="-my-1 mb-0.5 size-5 text-muted-foreground/60 hover:text-muted-foreground"
                    aria-label="About coverage"
                  >
                    <Info class="size-3" aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" align="end" class="max-w-[240px]">
                  Percentage of required thumbnail and preview files that are already cached. Required = total files
                  needed for all cataloged photos.
                </TooltipContent>
              </Tooltip>
            </div>
            <!-- Progress bar -->
            <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="
                  totalReady != null && totalExpected != null && totalExpected > 0
                    ? totalReady >= totalExpected
                      ? 'bg-success'
                      : totalReady / totalExpected >= 0.9
                        ? 'bg-warning'
                        : 'bg-destructive'
                    : 'bg-muted-foreground/30'
                "
                :style="{
                  width:
                    totalReady != null && totalExpected != null && totalExpected > 0
                      ? Math.min(100, (totalReady / totalExpected) * 100) + '%'
                      : '0%',
                }"
                role="progressbar"
                :aria-valuenow="
                  totalReady != null && totalExpected != null && totalExpected > 0
                    ? Math.min(100, Math.round((totalReady / totalExpected) * 100))
                    : 0
                "
                aria-valuemin="0"
                aria-valuemax="100"
              />
            </div>
          </div>
          <Skeleton v-else-if="summaryPending" class="mt-3 h-20 w-full" />
          <p v-else class="mt-3 text-sm text-muted-foreground">Image cache coverage is unavailable.</p>
        </section>

        <section
          class="image-cache-section rounded-lg border border-border bg-muted/30 p-4"
          aria-labelledby="image-cache-queue-heading"
        >
          <h4 id="image-cache-queue-heading" class="text-sm font-semibold text-foreground">Queue health</h4>
          <template v-if="runtime">
            <!-- Idle state: workers full, nothing running, no failures -->
            <div
              v-if="
                runtime.derivative_worker_count >= runtime.derivative_configured_worker_count &&
                runtime.derivative_active_jobs === 0 &&
                runtime.derivative_queue_depth === 0 &&
                runtime.derivative_failed_jobs === 0 &&
                runtime.derivative_stale_running_jobs === 0
              "
              class="mt-3 flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2.5"
            >
              <span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-success/15">
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
                <p class="text-xs font-medium text-foreground">Idle</p>
                <p class="text-xs text-muted-foreground">
                  {{ runtime.derivative_worker_count }}/{{ runtime.derivative_configured_worker_count }} workers ready ·
                  no active or queued jobs
                </p>
              </div>
            </div>

            <!-- Active or warning/error state -->
            <template v-else>
              <!-- Error/warning alert (failed or stale jobs) -->
              <div
                v-if="runtime.derivative_failed_jobs > 0 || runtime.derivative_stale_running_jobs > 0"
                class="mt-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
                role="alert"
              >
                <span v-if="runtime.derivative_failed_jobs > 0"
                  >{{ runtime.derivative_failed_jobs }} failed job{{
                    runtime.derivative_failed_jobs !== 1 ? "s" : ""
                  }}.</span
                >
                <span v-if="runtime.derivative_stale_running_jobs > 0">
                  {{ runtime.derivative_stale_running_jobs }} stale running job{{
                    runtime.derivative_stale_running_jobs !== 1 ? "s" : ""
                  }}.</span
                >
              </div>

              <!-- Metrics grid -->
              <dl class="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                <!-- Workers -->
                <div class="rounded-md border border-border bg-background p-3">
                  <dt class="text-xs text-muted-foreground">Workers</dt>
                  <dd
                    class="mt-1 text-base font-semibold tabular-nums"
                    :class="
                      runtime.derivative_worker_count < runtime.derivative_configured_worker_count
                        ? 'text-warning'
                        : 'text-success'
                    "
                  >
                    {{ runtime.derivative_worker_count }}/{{ runtime.derivative_configured_worker_count }}
                  </dd>
                </div>

                <!-- Active jobs -->
                <div class="rounded-md border border-border bg-background p-3">
                  <dt class="text-xs text-muted-foreground">Active jobs</dt>
                  <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                    {{ runtime.derivative_active_jobs }}
                  </dd>
                </div>

                <!-- Queue depth -->
                <div class="rounded-md border border-border bg-background p-3">
                  <dt class="text-xs text-muted-foreground">Queue depth</dt>
                  <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                    {{ runtime.derivative_queue_depth }}
                  </dd>
                </div>

                <!-- Failed jobs — only show when non-zero or in error state -->
                <div
                  v-if="runtime.derivative_failed_jobs > 0 || runtime.derivative_stale_running_jobs > 0"
                  class="rounded-md border border-border bg-background p-3"
                >
                  <dt class="text-xs text-muted-foreground">Failed jobs</dt>
                  <dd
                    class="mt-1 text-base font-semibold tabular-nums"
                    :class="runtime.derivative_failed_jobs > 0 ? 'text-destructive' : 'text-foreground'"
                  >
                    {{ runtime.derivative_failed_jobs }}
                  </dd>
                </div>

                <!-- Stale running jobs — only show when non-zero -->
                <div
                  v-if="runtime.derivative_stale_running_jobs > 0"
                  class="rounded-md border border-border bg-background p-3"
                >
                  <dt class="text-xs text-muted-foreground">Stale running</dt>
                  <dd class="mt-1 text-base font-semibold tabular-nums text-destructive">
                    {{ runtime.derivative_stale_running_jobs }}
                  </dd>
                </div>
              </dl>
            </template>
          </template>
          <Skeleton v-else-if="runtimePending" class="mt-3 h-24 w-full rounded-lg" />
          <p v-else class="mt-3 text-sm text-muted-foreground">Image cache queue health is unavailable.</p>
        </section>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped>
@media (max-width: 1023px) {
  .image-cache-content {
    padding: 1.25rem;
  }

  .image-cache-sections {
    gap: 1rem;
    margin-top: 1.25rem;
  }

  .image-cache-section {
    padding: 1rem;
  }

  .image-cache-metric {
    min-height: 82px;
    padding: 0.875rem;
  }

  .image-cache-metric dt {
    font-weight: 600;
  }

  .image-cache-metric dd {
    margin-top: 0.375rem;
    font-size: 1.125rem;
    line-height: 1.25;
  }
}
</style>
