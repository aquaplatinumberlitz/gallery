<script setup lang="ts">
import { computed } from "vue";
import { File, FileChartColumn, HardDrive, ArrowDown, ArrowRight } from "lucide-vue-next";
import { Card, CardContent } from "@/components/ui/card";
import { useSearchIndexStatusQuery } from "@/composables/useSearchIndexStatusQuery";
import { summarizeDerivedSearchIndexes } from "@/utils/searchIndexSummary";

const catalogStage = {
  title: "File catalog",
  description: "Finds images and videos in your libraries",
  icon: File,
} as const;

// Steps 2 and 3 both start once files are cataloged and run side by side.
const parallelStages = [
  {
    step: 2,
    title: "Metadata extraction",
    description: "Reads prompts and settings from images",
    icon: FileChartColumn,
  },
  {
    step: 3,
    title: "Image cache",
    description: "Builds thumbnails and previews, ahead of time or on first view",
    icon: HardDrive,
  },
] as const;

// State of the derived prompt/workflow indexes, from the same data as Advanced Search > Search indexes.
const indexQuery = useSearchIndexStatusQuery(null, true);
const searchIndexNote = computed(() => summarizeDerivedSearchIndexes(indexQuery.statuses.data.value));
</script>

<template>
  <Card class="gap-0 overflow-hidden py-0" aria-labelledby="imported-data-flow-heading">
    <CardContent class="p-5 sm:p-6">
      <div class="max-w-2xl">
        <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Processing pipeline</p>
        <h3 id="imported-data-flow-heading" class="mt-1 font-semibold text-foreground">Imported data flow</h3>
      </div>

      <!-- 1 -> (2 || 3): step 1 feeds a group whose two steps run side by side -->
      <ol
        class="mt-4 grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] md:gap-8"
        aria-label="Imported data processing stages"
        data-testid="pipeline-stages"
      >
        <li class="relative md:self-center">
          <div class="flex min-h-20 items-center gap-3 rounded-md border border-border bg-muted/40 p-4">
            <span
              class="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground"
              aria-hidden="true"
            >
              <component :is="catalogStage.icon" class="size-4" />
            </span>
            <div class="min-w-0">
              <p class="text-sm font-semibold text-foreground">1. {{ catalogStage.title }}</p>
              <p class="mt-0.5 text-sm text-muted-foreground">{{ catalogStage.description }}</p>
            </div>
          </div>
          <span
            class="flex h-6 items-center justify-center text-muted-foreground md:absolute md:top-1/2 md:-right-[1.375rem] md:z-10 md:size-6 md:-translate-y-1/2 md:rounded-full md:border md:border-border md:bg-card"
            aria-hidden="true"
          >
            <ArrowDown class="size-4 md:hidden" />
            <ArrowRight class="hidden size-4 md:block" />
          </span>
        </li>
        <li>
          <ol
            class="flex flex-col gap-2 rounded-md border border-dashed border-border p-2"
            aria-label="Stages that run side by side"
            data-testid="pipeline-parallel-group"
          >
            <li
              v-for="stage in parallelStages"
              :key="stage.title"
              class="flex min-h-20 items-center gap-3 rounded-md border border-border bg-muted/40 p-4"
            >
              <span
                class="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground"
                aria-hidden="true"
              >
                <component :is="stage.icon" class="size-4" />
              </span>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-foreground">{{ stage.step }}. {{ stage.title }}</p>
                <p class="mt-0.5 text-sm text-muted-foreground">{{ stage.description }}</p>
              </div>
            </li>
          </ol>
        </li>
      </ol>

      <p class="mt-3 text-sm text-muted-foreground" data-testid="pipeline-parallel-note">
        Steps 2 and 3 start once files are cataloged and run side by side.
      </p>
      <p v-if="searchIndexNote" class="mt-1 text-sm text-muted-foreground" data-testid="pipeline-search-index-note">
        {{ searchIndexNote }}
      </p>
    </CardContent>
  </Card>
</template>
