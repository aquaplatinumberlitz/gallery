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
    <CardContent class="p-5">
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

      <div class="mt-5 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section class="rounded-lg border border-border bg-muted/30 p-4" aria-labelledby="image-cache-coverage-heading">
          <h4 id="image-cache-coverage-heading" class="text-sm font-semibold text-foreground">Coverage</h4>
          <dl v-if="summaryAvailable" class="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div class="rounded-md border border-border bg-background p-3">
              <dt class="text-xs text-muted-foreground">Cached files</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">{{ totalReady ?? "—" }}</dd>
            </div>
            <div class="rounded-md border border-border bg-background p-3">
              <dt class="flex min-h-6 items-center text-xs text-muted-foreground">
                <span>Required files</span>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon-lg"
                      class="-my-2 -me-2 text-muted-foreground hover:text-foreground"
                      aria-label="About required files"
                    >
                      <Info class="size-3.5" aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="start" class="max-w-[240px]">
                    Total thumbnail and preview files required for cataloged photos.
                  </TooltipContent>
                </Tooltip>
              </dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">{{ totalExpected ?? "—" }}</dd>
            </div>
          </dl>
          <Skeleton v-else-if="summaryPending" class="mt-3 h-20 w-full" />
          <p v-else class="mt-3 text-sm text-muted-foreground">Image cache coverage is unavailable.</p>
        </section>

        <section class="rounded-lg border border-border bg-muted/30 p-4" aria-labelledby="image-cache-queue-heading">
          <h4 id="image-cache-queue-heading" class="text-sm font-semibold text-foreground">Queue health</h4>
          <dl v-if="runtime" class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
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
            <div class="rounded-md border border-border bg-background p-3">
              <dt class="text-xs text-muted-foreground">Active jobs</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                {{ runtime.derivative_active_jobs }}
              </dd>
            </div>
            <div class="rounded-md border border-border bg-background p-3">
              <dt class="text-xs text-muted-foreground">Queue depth</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums text-foreground">
                {{ runtime.derivative_queue_depth }}
              </dd>
            </div>
            <div class="rounded-md border border-border bg-background p-3">
              <dt class="text-xs text-muted-foreground">Failed jobs</dt>
              <dd
                class="mt-1 text-base font-semibold tabular-nums"
                :class="runtime.derivative_failed_jobs > 0 ? 'text-destructive' : 'text-foreground'"
              >
                {{ runtime.derivative_failed_jobs }}
              </dd>
            </div>
            <div class="col-span-2 rounded-md border border-border bg-background p-3">
              <dt class="text-xs text-muted-foreground">Stale running jobs</dt>
              <dd
                class="mt-1 text-base font-semibold tabular-nums"
                :class="runtime.derivative_stale_running_jobs > 0 ? 'text-destructive' : 'text-foreground'"
              >
                {{ runtime.derivative_stale_running_jobs }}
              </dd>
            </div>
          </dl>
          <Skeleton v-else-if="runtimePending" class="mt-3 h-36 w-full" />
          <p v-else class="mt-3 text-sm text-muted-foreground">Image cache queue health is unavailable.</p>
        </section>
      </div>
    </CardContent>
  </Card>
</template>
