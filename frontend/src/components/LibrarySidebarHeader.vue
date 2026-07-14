<script setup lang="ts">
import { computed, ref } from "vue";
import { FolderOpen, Library, Settings2, ChevronRight } from "lucide-vue-next";
import ResponsiveLibrarySelector from "@/components/ResponsiveLibrarySelector.vue";
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
const { isMobile: isSidebarSheet, setOpen } = useSidebar();
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

// Open the library selector modal. Blur the current focus first so reka-ui's
// hideOthers (which sets aria-hidden on the rest of the page) does not leave a
// focused descendant inside the now-hidden sidebar — that triggers a Chrome
// "Blocked aria-hidden" a11y warning.
function openLibrarySelector() {
  (document.activeElement as HTMLElement | null)?.blur();
  sheetOpen.value = true;
}
</script>

<template>
  <div class="sidebar-header-root relative bg-sidebar group-data-[collapsible=icon]:p-1">
    <!-- Mobile drag handle indicator -->
    <div v-if="isSidebarSheet" class="drag-handle-bar" aria-hidden="true">
      <span class="drag-handle" />
    </div>

    <SidebarTrigger
      v-if="!isSidebarSheet"
      class="sidebar-close-trigger absolute right-2 top-2 z-20 size-7 group-data-[collapsible=icon]:static group-data-[collapsible=icon]:mx-auto"
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

    <div class="sidebar-header-content space-y-3 group-data-[collapsible=icon]:hidden">
      <p class="sidebar-section-label">Active library</p>
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
          class="library-selector-btn"
          @click="openLibrarySelector"
        >
          <span class="library-icon-badge">
            <FolderOpen class="size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="library-name">{{ activeLibrary?.name ?? "Select a library" }}</span>
            <span class="library-path">{{ activeImportPath?.path }}</span>
          </span>
          <ChevronRight class="library-chevron" />
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
        class="manage-libraries-btn w-full"
      >
        <Settings2 class="size-4" /> Manage Libraries
      </ButtonLink>
    </div>
    <ResponsiveLibrarySelector v-model="sheetOpen" />
  </div>
</template>

<style scoped>
.sidebar-header-root {
  padding: 16px 16px 14px;
}

.drag-handle-bar {
  display: flex;
  justify-content: center;
  padding-bottom: 12px;
}

.drag-handle {
  width: 36px;
  height: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--sidebar-foreground) 15%, transparent);
  transition: background 200ms ease;
}

.sidebar-section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
  margin: 0;
}

.sidebar-header-content {
  /* inherits space-y-3 from class */
}

.library-selector-btn {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: var(--gallery-radius-lg);
  background: color-mix(in srgb, var(--sidebar-accent) 50%, transparent);
  text-align: left;
  border: 1px solid color-mix(in srgb, var(--sidebar-border) 50%, transparent);
  transition: background 180ms ease, border-color 180ms ease, transform 120ms ease;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.library-selector-btn:active {
  transform: scale(0.98);
  background: color-mix(in srgb, var(--sidebar-accent) 80%, transparent);
}

.library-icon-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--gallery-radius-md);
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--primary);
  flex-shrink: 0;
}

.library-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--sidebar-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-path {
  display: block;
  font-family: var(--gallery-font-mono);
  font-size: 11px;
  line-height: 1.4;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 1px;
}

.library-chevron {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--muted-foreground);
  opacity: 0.5;
}

.manage-libraries-btn {
  border-color: color-mix(in srgb, var(--sidebar-border) 60%, transparent);
  background: var(--sidebar);
  transition: background 150ms ease, border-color 150ms ease;
}

.manage-libraries-btn:hover {
  background: color-mix(in srgb, var(--sidebar-accent) 70%, transparent);
}

@media (max-width: 1023px) {
  .sidebar-close-trigger {
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
  }

  .library-selector-btn {
    min-height: 56px;
  }
}
</style>
