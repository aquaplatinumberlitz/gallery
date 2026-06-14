<script setup lang="ts">
import { onMounted, ref, watch, inject } from "vue";
import { useGalleryStore } from "../stores/gallery";
import { FolderOpen, RotateCcw, Info, Edit3 } from "lucide-vue-next";
import { useDevice } from "../composables/useDevice";
import RootPathSheet from "./RootPathSheet.vue";
import { closeSidebarKey } from "../injectionKeys";
import { useSidebar, SidebarTrigger } from "@/components/ui/sidebar";
import Input from "@/components/ui/Input.vue";
import Button from "@/components/ui/Button.vue";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const { isMobile } = useDevice();
const closeSidebar = inject(closeSidebarKey, () => {});
const { setOpen } = useSidebar();
const galleryStore = useGalleryStore();
const pathInput = ref(galleryStore.rootPath || "");
const inputRef = ref<HTMLInputElement | null>(null);
const showSheet = ref(false);

const onLoad = async () => {
  const cleaned = pathInput.value.trim().replace(/^["']|["']$/g, "");
  const success = await galleryStore.setRootPath(cleaned);
  if (success) {
    closeSidebar();
  }
  inputRef.value?.blur();
};

const onReset = () => {
  galleryStore.resetRootPath();
  pathInput.value = "";
};

const editOnMobile = () => {
  showSheet.value = true;
};

onMounted(() => {
  if (galleryStore.rootPath) {
    pathInput.value = galleryStore.rootPath;
  }
});

watch(
  () => galleryStore.rootPath,
  (val) => {
    if (val && val !== pathInput.value) {
      pathInput.value = val;
    }
  }
);
</script>

<template>
  <div class="sidebar-header p-4 group-data-[collapsible=icon]:p-1 bg-surface border-b border-black/5 dark:border-white/5 group-data-[collapsible=icon]:border-b-0">
    <SidebarTrigger
      class="absolute top-3 right-3 z-20 h-8 w-8 [&>button]:h-8 [&>button]:w-8 group-data-[collapsible=icon]:static group-data-[collapsible=icon]:mb-1"
    />
    <!-- MOBILE: Compact display with tappable edit -->
    <template v-if="isMobile">
      <label class="field-label block text-[11px] font-semibold text-muted-foreground mb-2 tracking-[0.5px]">ROOT PATH</label>
      <div class="mobile-root-display" @click="editOnMobile" role="button" tabindex="0" @keydown.enter="editOnMobile">
        <FolderOpen class="field-icon gallery-icon-md" />
        <span class="mobile-path-text">
          {{ pathInput || "Not set" }}
        </span>
        <Tooltip>
          <TooltipTrigger as-child>
            <button class="mobile-edit-btn" type="button" @click.stop="editOnMobile" aria-label="Edit root path">
              <Edit3 class="gallery-icon-sm" />
            </button>
          </TooltipTrigger>
          <TooltipContent>Edit root path</TooltipContent>
        </Tooltip>
      </div>
      <p class="field-hint">
        <Info class="gallery-icon-xs" />
        Tap to edit
      </p>

      <RootPathSheet
        v-model="showSheet"
        :current-path="pathInput"
      />
    </template>

    <!-- DESKTOP: Full input with controls (unchanged) -->
    <template v-else>
      <!-- Icon-only view for collapsed icon mode -->
      <Tooltip>
        <TooltipTrigger as-child>
          <Button
            variant="ghost"
            size="icon"
            class="hidden group-data-[collapsible=icon]:flex size-8"
            aria-label="Edit Root Path"
            @click="setOpen(true)"
          >
            <FolderOpen class="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">Edit Root Path</TooltipContent>
      </Tooltip>

      <!-- Full desktop view, hidden in collapsed icon mode -->
      <div class="group-data-[collapsible=icon]:hidden">
        <label class="field-label" for="root-path">ROOT PATH</label>

        <div class="field-container">
          <FolderOpen class="field-icon gallery-icon-md" />
          <Input
            id="root-path"
            ref="inputRef"
            v-model.trim="pathInput"
            variant="ghost"
            type="text"
            placeholder="Enter folder path..."
            autocomplete="off"
            aria-label="Root path"
            @keyup.enter="onLoad"
          />

          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                v-if="pathInput"
                variant="ghost"
                size="icon-sm"
                class="action-btn"
                type="button"
                aria-label="Reset path"
                @click="onReset"
              >
                <RotateCcw class="gallery-icon-sm" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Reset path</TooltipContent>
          </Tooltip>
        </div>

        <p class="field-hint">
          <Info class="gallery-icon-xs" />
          Press Enter to load
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* sidebar-header and field-label layout handled by Tailwind utilities */
/* Keep container shells, icons, hints, and responsive rules */

.sidebar-header {
  /* Class preserved for responsive overrides */
}

.field-label {
  /* Layout handled by Tailwind utilities */
}

/* field-container and input styling handled by shadcn Input variant="ghost" */
/* and shadcn Button variant="ghost" size="icon-sm" */
/* Only container shell and responsive rules remain */

.field-container {
  background: var(--surface-color, #fff);
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  height: 40px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.field-icon {
  color: var(--primary-color);
  flex-shrink: 0;
}

.field-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted-text, #65676b);
}

/* Responsive: iOS Safari zoom fix — font-size >= 16px prevents auto-zoom on input focus */
@media (max-width: 767px) {
  .sidebar-header {
    padding: 12px;
  }

  .field-container {
    height: 40px;
    padding: 0 10px;
  }

  input {
    font-size: 16px;
    min-width: 140px;
    touch-action: manipulation;
  }

  .action-btn {
    touch-action: manipulation;
  }

  /* Compact root path display for mobile */
  .mobile-root-display {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px;
    height: 40px;
    border-radius: 10px;
    border: 1px solid rgba(0, 0, 0, 0.1);
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s;
    touch-action: manipulation;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
  }

  [data-theme="dark"] .mobile-root-display {
    border-color: rgba(255, 255, 255, 0.12);
  }

  .mobile-root-display:active {
    border-color: var(--primary-color, #ff6b35);
    box-shadow: 0 0 0 2px rgba(255, 107, 53, 0.15);
  }

  .mobile-root-display .field-icon {
    flex-shrink: 0;
  }

  .mobile-path-text {
    flex: 1;
    min-width: 0;
    font-size: 14px;
    color: var(--text-color, #050505);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mobile-edit-btn {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: var(--muted-text, #65676b);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    touch-action: manipulation;
  }

  .mobile-edit-btn:active {
    background: rgba(0, 0, 0, 0.05);
    color: var(--primary-color, #ff6b35);
  }
}

/* Icon sizes using design tokens */
.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
.gallery-icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}
.gallery-icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}
</style>
