<script setup lang="ts">
import { computed, ref } from "vue";
import { FolderOpen, Library, Settings2 } from "lucide-vue-next";
import LibrarySelectorSheet from "@/components/LibrarySelectorSheet.vue";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import IconTooltipButton from "@/components/ui/IconTooltipButton.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import { useDevice } from "@/composables/useDevice";
import { useGalleryStore } from "@/stores/gallery";

const galleryStore = useGalleryStore();
const { isMobile } = useDevice();
const { setOpen } = useSidebar();
const { librariesQuery, libraries, activeLibrary, activeImportPath } = useActiveLibrarySelection();
const sheetOpen = ref(false);
const eligibleLibraries = computed(() => libraries.value.filter((library) => library.import_paths.length > 0));
const libraryValue = computed(() => (galleryStore.activeLibraryId ? String(galleryStore.activeLibraryId) : undefined));
const importPathValue = computed(() =>
  galleryStore.activeImportPathId ? String(galleryStore.activeImportPathId) : undefined,
);

function selectLibrary(value: unknown) {
  const library = eligibleLibraries.value.find((item) => item.id === Number(value));
  if (library) galleryStore.setActiveLibrary(library);
}

function selectImportPath(value: unknown) {
  const library = activeLibrary.value;
  const importPath = library?.import_paths.find((item) => item.id === Number(value));
  if (library && importPath) galleryStore.setActiveImportPath(importPath, library);
}
</script>

<template>
  <div class="relative bg-sidebar p-4 pb-3 group-data-[collapsible=icon]:p-1">
    <SidebarTrigger
      class="absolute right-2 top-2 z-20 size-7 group-data-[collapsible=icon]:static group-data-[collapsible=icon]:mx-auto"
    />
    <IconTooltipButton
      variant="ghost"
      size="icon"
      class="hidden size-8 group-data-[collapsible=icon]:flex"
      label="Select library"
      side="right"
      @click="setOpen(true)"
    >
      <Library class="size-4" />
    </IconTooltipButton>

    <div class="space-y-3 group-data-[collapsible=icon]:hidden">
      <p class="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Active library</p>
      <Skeleton v-if="librariesQuery.isPending.value" class="h-9 w-full" />
      <div v-else-if="librariesQuery.isError.value" class="space-y-2">
        <p class="text-xs text-destructive">Could not load libraries.</p>
        <Button size="sm" variant="outline" @click="librariesQuery.refetch()">Retry</Button>
      </div>
      <div
        v-else-if="!eligibleLibraries.length"
        class="space-y-3 rounded-lg border border-dashed border-sidebar-border/70 bg-sidebar-accent/35 p-3 text-center"
      >
        <p class="text-sm font-medium">No libraries registered</p>
        <ButtonLink to="/admin/libraries" size="sm">Add Library</ButtonLink>
      </div>
      <template v-else-if="isMobile">
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-lg bg-sidebar-accent/45 p-3 text-left shadow-sm ring-1 ring-sidebar-border/55 transition-colors hover:bg-sidebar-accent/70"
          @click="sheetOpen = true"
        >
          <FolderOpen class="size-4 shrink-0 text-primary" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{{ activeLibrary?.name ?? "Select a library" }}</span>
            <span class="block truncate font-mono text-[11px] text-muted-foreground">{{ activeImportPath?.path }}</span>
          </span>
        </button>
      </template>
      <template v-else>
        <Select :model-value="libraryValue" @update:model-value="selectLibrary">
          <SelectTrigger aria-label="Active library"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="library in eligibleLibraries" :key="library.id" :value="String(library.id)">
              {{ library.name }}
            </SelectItem>
          </SelectContent>
        </Select>
        <Select
          v-if="activeLibrary && activeLibrary.import_paths.length > 1"
          :model-value="importPathValue"
          @update:model-value="selectImportPath"
        >
          <SelectTrigger aria-label="Active import path">
            <SelectValue placeholder="Select an import path" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="path in activeLibrary.import_paths" :key="path.id" :value="String(path.id)">
              {{ path.path }}
            </SelectItem>
          </SelectContent>
        </Select>
        <OverflowTooltip
          v-else-if="activeImportPath"
          as="p"
          :text="activeImportPath.path"
          class="font-mono text-[11px] text-muted-foreground"
          align="start"
        >
          {{ activeImportPath.path }}
        </OverflowTooltip>
      </template>
      <ButtonLink
        v-if="eligibleLibraries.length"
        to="/admin/libraries"
        variant="outline"
        size="sm"
        class="w-full border-sidebar-border bg-sidebar hover:bg-sidebar-accent/70"
      >
        <Settings2 class="size-4" /> Manage Libraries
      </ButtonLink>
    </div>
    <LibrarySelectorSheet v-model="sheetOpen" />
  </div>
</template>
