<script setup lang="ts">
import { File, FileChartColumn, HardDrive, ArrowDown, ArrowRight } from "lucide-vue-next";
import { Card, CardContent } from "@/components/ui/card";

const stages = [
  {
    title: "File catalog",
    description: "Discovers source files",
    icon: File,
  },
  {
    title: "Metadata extraction",
    description: "Reads file details",
    icon: FileChartColumn,
  },
  {
    title: "Image cache",
    description: "Builds thumbnails and previews",
    icon: HardDrive,
  },
] as const;
</script>

<template>
  <Card class="gap-0 overflow-hidden py-0" aria-labelledby="imported-data-flow-heading">
    <CardContent class="p-5 sm:p-6">
      <div class="max-w-2xl">
        <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Processing pipeline</p>
        <h3 id="imported-data-flow-heading" class="mt-1 font-semibold text-foreground">Imported data flow</h3>
      </div>

      <ol class="mt-4 grid gap-2 md:grid-cols-3" aria-label="Imported data processing stages">
        <li v-for="(stage, index) in stages" :key="stage.title" class="relative">
          <div class="flex min-h-20 items-center gap-3 rounded-md border border-border bg-muted/40 p-4">
            <span
              class="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground"
              aria-hidden="true"
            >
              <component :is="stage.icon" class="size-4" />
            </span>
            <div class="min-w-0">
              <p class="text-sm font-semibold text-foreground">{{ index + 1 }}. {{ stage.title }}</p>
              <p class="mt-0.5 text-sm text-muted-foreground">{{ stage.description }}</p>
            </div>
          </div>
          <span
            v-if="index < stages.length - 1"
            class="flex h-6 items-center justify-center text-muted-foreground md:absolute md:top-1/2 md:-right-3 md:z-10 md:size-6 md:-translate-y-1/2 md:rounded-full md:border md:border-border md:bg-card"
            aria-hidden="true"
          >
            <ArrowDown class="size-4 md:hidden" />
            <ArrowRight class="hidden size-4 md:block" />
          </span>
        </li>
      </ol>
    </CardContent>
  </Card>
</template>
