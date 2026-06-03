<script setup lang="ts">
import { type SortField } from "../types";
import {
  ArrowLeft, ArrowRight, ArrowUpDown, ChevronDown,
  ArrowUp, ArrowDown, LayoutGrid, Check,
  Type, Clock
} from "lucide-vue-next";

const icons: Record<string, any> = { Type, Clock };

interface SortOption {
  field: SortField;
  label: string;
  icon: string;
}

interface DensityOption {
  level: number;
  label: string;
  columns: number;
}

interface Props {
  canGoBack: boolean;
  canGoForward: boolean;
  currentSort: SortField;
  sortOptions: SortOption[];
  showSortMenu: boolean;
  currentSortLabel: string;
  sortOrder: "asc" | "desc";
  sliderLevel: number;
  columnCount: number;
  densityOptions: readonly DensityOption[];
  showDensityMenu: boolean;
}

defineProps<Props>();

const emit = defineEmits<{
  back: [];
  forward: [];
  toggleSortMenu: [];
  selectSort: [field: SortField];
  toggleDensityMenu: [];
  selectDensity: [level: number];
}>();

const selectSort = (field: SortField) => {
  emit("selectSort", field);
};

const selectDensity = (level: number) => {
  emit("selectDensity", level);
};

// Sort menu keyboard navigation
const handleSortMenuKeydown = (e: KeyboardEvent) => {
  if (e.key === "Escape") {
    emit("toggleSortMenu");
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
      <button
        class="tgt-btn"
        :disabled="!canGoBack"
        @click="emit('back')"
        title="Back"
        aria-label="Go back"
      >
        <ArrowLeft :size="22" />
      </button>
      <button
        class="tgt-btn"
        :disabled="!canGoForward"
        @click="emit('forward')"
        title="Forward"
        aria-label="Go forward"
      >
        <ArrowRight :size="22" />
      </button>
    </div>

    <div class="tgt-spacer"></div>

    <!-- Sort dropdown -->
    <div class="sort-dropdown" :class="{ open: showSortMenu }">
      <button
        class="tgt-trigger"
        @click.stop="emit('toggleSortMenu')"
        title="Sort by"
        aria-haspopup="true"
        :aria-expanded="showSortMenu"
      >
        <ArrowUpDown :size="20" />
        <span class="tgt-trigger-label">{{ currentSortLabel }}</span>
        <ChevronDown :size="16" class="tgt-chevron" />
      </button>
      <Transition name="dropdown">
        <div
          v-if="showSortMenu"
          class="sort-menu"
          @keydown="handleSortMenuKeydown"
        >
          <button
            v-for="option in sortOptions"
            :key="option.field"
            class="sort-option"
            :class="{ active: currentSort === option.field }"
            @click="selectSort(option.field)"
          >
            <component :is="icons[option.icon]" :size="14" />
            <span>{{ option.label }}</span>
            <component
              v-if="currentSort === option.field"
              :is="sortOrder === 'asc' ? ArrowUp : ArrowDown"
              class="sort-direction"
              :size="12"
            />
          </button>
        </div>
      </Transition>
    </div>

    <!-- Density dropdown -->
    <div class="density-dropdown" :class="{ open: showDensityMenu }">
      <button
        class="tgt-trigger"
        @click.stop="emit('toggleDensityMenu')"
        aria-haspopup="true"
        :aria-expanded="showDensityMenu"
        title="Thumbnail size"
      >
        <LayoutGrid :size="20" />
        <span class="tgt-trigger-label">{{ columnCount }} cols</span>
        <ChevronDown :size="16" class="tgt-chevron" />
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
            <LayoutGrid :size="14" />
            <span>{{ option.label }}</span>
            <span class="density-cols">{{ option.columns }} cols</span>
            <Check
              v-if="sliderLevel === option.level"
              class="density-check"
              :size="12"
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
  background: color-mix(in srgb, var(--surface-color) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.08)) 50%, transparent);
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
  color: var(--text-color);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease, transform 0.12s ease;
}

.tgt-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.tgt-btn:active:not(:disabled) {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
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
  background: color-mix(in srgb, var(--surface-color) 95%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.1)) 70%, transparent);
  border-radius: 10px;
  color: var(--text-color);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tgt-trigger:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.sort-dropdown.open .tgt-trigger,
.density-dropdown.open .tgt-trigger {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.tgt-trigger-label {
  font-weight: 500;
}

.tgt-chevron {
  opacity: 0.6;
  transition: transform 0.2s ease;
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
  background: var(--surface-color);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.1)) 70%, transparent);
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
  background: var(--surface-color);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.1)) 70%, transparent);
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
  color: var(--text-color);
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
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-weight: 500;
}

.sort-direction {
  margin-left: auto;
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
  color: var(--text-color);
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
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-weight: 500;
}

.density-cols {
  opacity: 0.6;
  font-weight: 400;
}

.density-option.active .density-cols {
  opacity: 0.8;
}

.density-check {
  margin-left: auto;
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
  border-color: color-mix(in srgb, var(--border-color, rgba(255, 255, 255, 0.08)) 50%, transparent);
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
