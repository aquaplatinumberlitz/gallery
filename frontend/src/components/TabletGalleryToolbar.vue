<script setup lang="ts">
import type { SortValue } from "../types";
import SortSelect from "./SortSelect.vue";
import {
  ArrowLeft, ArrowRight, ChevronDown,
  LayoutGrid, Check,
} from "lucide-vue-next";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface DensityOption {
  level: number;
  label: string;
  columns: number;
}

interface Props {
  canGoBack: boolean;
  canGoForward: boolean;
  sortValue: SortValue;
  sliderLevel: number;
  columnCount: number;
  densityOptions: readonly DensityOption[];
  showDensityMenu: boolean;
}

defineProps<Props>();

const emit = defineEmits<{
  back: [];
  forward: [];
  "update:sortValue": [value: SortValue];
  toggleDensityMenu: [];
  selectDensity: [level: number];
}>();

const selectDensity = (level: number) => {
  emit("selectDensity", level);
};

// Density menu keyboard navigation
const handleDensityMenuKeydown = (e: KeyboardEvent) => {
  if (e.key === "Escape") {
    emit("toggleDensityMenu");
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const menu = e.currentTarget as HTMLElement;
    const buttons = menu.querySelectorAll("button");
    if (buttons.length) {
      const currentIndex = Array.from(buttons).findIndex(
        (b) => b === document.activeElement
      );
      const nextIndex =
        e.key === "ArrowDown"
          ? (currentIndex + 1) % buttons.length
          : (currentIndex - 1 + buttons.length) % buttons.length;
      (buttons[nextIndex] as HTMLElement).focus();
    }
  }
};
</script>

<template>
  <div class="tablet-gallery-toolbar">
    <!-- Nav group: back/forward -->
    <div class="tgt-nav-group">
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            class="tgt-btn"
            :disabled="!canGoBack"
            @click="emit('back')"
            aria-label="Go back"
          >
            <ArrowLeft class="tgt-nav-icon" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Back</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            class="tgt-btn"
            :disabled="!canGoForward"
            @click="emit('forward')"
            aria-label="Go forward"
          >
            <ArrowRight class="tgt-nav-icon" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Forward</TooltipContent>
      </Tooltip>
    </div>

    <div class="tgt-spacer"></div>

    <SortSelect
      :model-value="sortValue"
      aria-label="Sort gallery"
      @update:model-value="emit('update:sortValue', $event)"
    />

    <!-- Density dropdown -->
    <div class="density-dropdown" :class="{ open: showDensityMenu }">
      <button
        class="tgt-trigger"
        @click.stop="emit('toggleDensityMenu')"
        aria-haspopup="true"
        :aria-expanded="showDensityMenu"
      >
        <LayoutGrid class="tgt-trigger-icon" />
        <span class="tgt-trigger-label">{{ columnCount }} cols</span>
        <ChevronDown class="tgt-chevron" />
      </button>
      <Transition name="dropdown">
        <div
          v-if="showDensityMenu"
          class="density-menu"
          @keydown="handleDensityMenuKeydown"
        >
          <button
            v-for="option in densityOptions"
            :key="option.level"
            class="density-option"
            :class="{ active: sliderLevel === option.level }"
            @click="selectDensity(option.level)"
          >
            <LayoutGrid class="tgt-option-icon" />
            <span>{{ option.label }}</span>
            <span class="density-cols">{{ option.columns }} cols</span>
            <Check
              v-if="sliderLevel === option.level"
              class="density-check tgt-check-icon"
            />
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   Tablet Gallery Toolbar — follows TabletHeader design language
   ============================================================ */
.tablet-gallery-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--card) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
  border-radius: 12px;
  flex-shrink: 0;
}

/* Nav group */
.tgt-nav-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* Buttons — 44×44 touch targets */
.tgt-btn {
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease, transform 0.12s ease;
}

.tgt-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.tgt-btn:active:not(:disabled) {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
  transform: scale(0.96);
}

.tgt-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

/* Spacer to push right-side controls */
.tgt-spacer {
  flex: 1;
}

/* ============================================================
   Triggers (sort & density) — 44px min-height touch targets
   ============================================================ */
.tgt-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  min-height: 44px;
  background: color-mix(in srgb, var(--card) 95%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 10px;
  color: var(--foreground);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tgt-trigger:hover {
  border-color: var(--ring);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--ring) 25%, transparent);
}

.sort-dropdown.open .tgt-trigger,
.density-dropdown.open .tgt-trigger {
  border-color: var(--ring);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--ring) 25%, transparent);
}

.tgt-trigger-label {
  font-weight: 500;
}

.sort-dropdown.open .tgt-chevron,
.density-dropdown.open .tgt-chevron {
  transform: rotate(180deg);
}

/* ============================================================
   Sort & Density dropdowns (shared desktop-menu styles)
   ============================================================ */
.sort-dropdown {
  position: relative;
}

.density-dropdown {
  position: relative;
}

.sort-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 180px;
  background: var(--popover);
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 12px;
  box-shadow: var(--gallery-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.15));
  padding: 6px;
  z-index: 100;
  overflow: hidden;
}

.density-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 180px;
  background: var(--popover);
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 12px;
  box-shadow: var(--gallery-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.15));
  padding: 6px;
  z-index: 100;
  overflow: hidden;
}

.sort-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--foreground);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.sort-option:hover {
  background: rgba(0, 0, 0, 0.05);
}

.sort-option.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--primary);
  font-weight: 500;
}

.density-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--foreground);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  position: relative;
}

.density-option:hover {
  background: rgba(0, 0, 0, 0.05);
}

.density-option.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--primary);
  font-weight: 500;
}

.density-cols {
  opacity: 0.6;
  font-weight: 400;
}

.density-option.active .density-cols {
  opacity: 0.8;
}

/* Dropdown animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
  transform-origin: top right;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-4px);
}

/* Focus styles */
.tgt-btn:focus-visible,
.tgt-trigger:focus-visible,
.sort-option:focus-visible,
.density-option:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Dark mode support: surface adjustments */
:root[data-theme="dark"] .tablet-gallery-toolbar {
  border-color: color-mix(in srgb, var(--border) 50%, transparent);
}

/* ============================================================
   Icon size tokens
   ============================================================ */
:deep(.tgt-nav-icon) {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
  flex-shrink: 0;
}

.tgt-trigger-icon {
  width: var(--gallery-icon-tablet-toolbar);
  height: var(--gallery-icon-tablet-toolbar);
}

.tgt-chevron {
  opacity: 0.6;
  transition: transform 0.2s ease;
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

.tgt-option-icon {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}

.tgt-dir-icon {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
  margin-left: auto;
}

.tgt-check-icon {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
  margin-left: auto;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .tgt-btn {
    transition: none;
  }

  .tgt-btn:active:not(:disabled) {
    transform: none;
  }

  .tgt-chevron {
    transition: none;
  }

  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}
</style>
