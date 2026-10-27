<script setup lang="ts">
import { computed, inject } from "vue";
import LibrarySidebarHeader from "@/components/LibrarySidebarHeader.vue";
import FolderTree from "@/components/FolderTree.vue";
import { Loader, Settings, Wrench } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import { openSettingsKey } from "@/injectionKeys";
import {
  SidebarHeader as ShadSidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  useSidebar,
} from "@/components/ui/sidebar";
import IndexStatusPanel from "@/components/IndexStatusPanel.vue";
import type { FolderTreeNode } from "@/types";

defineProps<{
  tree: FolderTreeNode[];
  isLoading: boolean;
  hasActiveLibrary: boolean;
  currentPath: string;
}>();

const { isMobile, state, setOpenMobile } = useSidebar();
const isCollapsed = computed(() => state.value === "collapsed");
const openSettings = inject(openSettingsKey, null);

// Mobile/tablet chrome has no desktop header nav, so the sheet footer carries those entries.
function handleOpenSettings() {
  setOpenMobile(false);
  openSettings?.();
}
const indexStatusVariant = computed(() => (isMobile.value || isCollapsed.value ? "button" : "card"));
</script>

<template>
  <ShadSidebarHeader class="p-0">
    <LibrarySidebarHeader />
  </ShadSidebarHeader>

  <SidebarContent class="sidebar-content-area group-data-[collapsible=icon]:border-t-0">
    <SidebarGroup class="min-h-0 px-3 pb-3 pt-2 group-data-[collapsible=icon]:px-2">
      <SidebarGroupLabel as="div" class="sidebar-title" id="folder-tree-label">
        <span class="sidebar-title-text">Folder Tree</span>
        <span v-if="isLoading" class="loading-pill">
          <Loader class="gallery-icon-md lucide-spin" />
          <span>Loading</span>
        </span>
      </SidebarGroupLabel>

      <SidebarGroupContent>
        <div class="tree-container">
          <div v-if="!hasActiveLibrary" class="empty-state group-data-[collapsible=icon]:hidden">
            <p class="empty-state-text">Select a registered library to start browsing.</p>
          </div>
          <div v-else-if="!isLoading && !tree.length" class="empty-state group-data-[collapsible=icon]:hidden">
            <p class="empty-state-text">No folders available for this library.</p>
          </div>
          <FolderTree :tree="tree" :active-path="currentPath" />
        </div>
      </SidebarGroupContent>
    </SidebarGroup>
  </SidebarContent>

  <SidebarFooter
    class="sidebar-footer-area overflow-hidden group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-1"
  >
    <div v-if="isMobile" class="sidebar-footer-row">
      <IndexStatusPanel :path="currentPath" :variant="indexStatusVariant" />
      <nav class="sidebar-footer-nav" aria-label="App sections">
        <ButtonLink
          to="/admin/maintenance"
          variant="ghost"
          size="icon"
          class="sidebar-footer-action"
          aria-label="Maintenance"
        >
          <Wrench />
        </ButtonLink>
        <Button
          v-if="openSettings"
          variant="ghost"
          size="icon"
          class="sidebar-footer-action"
          aria-label="Settings"
          @click="handleOpenSettings"
        >
          <Settings />
        </Button>
      </nav>
    </div>
    <IndexStatusPanel v-else :path="currentPath" :variant="indexStatusVariant" />
  </SidebarFooter>
</template>

<style scoped>
.sidebar-footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.sidebar-footer-nav {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}

.sidebar-footer-action {
  width: 44px;
  height: 44px;
}

.sidebar-footer-action :deep(svg) {
  width: var(--gallery-icon-toolbar, 20px);
  height: var(--gallery-icon-toolbar, 20px);
  flex-shrink: 0;
}

.sidebar-content-area {
  border-top: 1px solid color-mix(in srgb, var(--sidebar-border) 45%, transparent);
  padding-top: 4px;
  position: relative;
}

/* Subtle accent line at the top of the content area */
.sidebar-content-area::before {
  content: "";
  position: absolute;
  top: 0;
  left: 12px;
  right: 12px;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--primary) 20%, transparent) 30%,
    color-mix(in srgb, var(--primary) 20%, transparent) 70%,
    transparent
  );
}

.sidebar-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: var(--sidebar-foreground);
  flex-shrink: 0;
  padding-bottom: 4px;
}

.sidebar-title-text {
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  opacity: 0.7;
}

.loading-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--primary) 8%, transparent);
  font-size: 11px;
  font-weight: 500;
  color: var(--sidebar-foreground);
  letter-spacing: 0.01em;
}

.tree-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  padding-right: 2px;
}

.empty-state {
  margin: 0;
  padding: 16px 12px;
  border-radius: var(--gallery-radius-lg);
  background: color-mix(in srgb, var(--sidebar-accent) 40%, transparent);
  border: 1px dashed color-mix(in srgb, var(--sidebar-border) 60%, transparent);
  text-align: center;
}

.empty-state-text {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 13px;
  line-height: 1.5;
}

.sidebar-footer-area {
  border-top: 1px solid color-mix(in srgb, var(--sidebar-border) 45%, transparent);
  padding: 10px 12px;
  padding-bottom: calc(10px + env(safe-area-inset-bottom));
  background: color-mix(in srgb, var(--foreground) 2%, var(--sidebar));
}

/* Override scoped CSS padding in collapsed (icon) mode.
   :global is needed because the data-collapsible attribute lives on an ancestor
   outside this component's scope, so group-data-* Tailwind utilities lose to scoped CSS. */
:global([data-collapsible="icon"]) .sidebar-footer-area {
  padding: 4px;
  padding-bottom: calc(4px + env(safe-area-inset-bottom));
}

.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
</style>
