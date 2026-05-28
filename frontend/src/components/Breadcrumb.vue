<script setup lang="ts">
import { computed, ref } from "vue";
import { vClickOutside } from "../directives/clickOutside";
import { ChevronRight, Ellipsis, Folder, ArrowsUpFromLine, Minimize, Home } from "lucide-vue-next";

const props = defineProps<{
  path?: string;
  /** Maximum visible segments before collapsing (default: 4) */
  maxVisible?: number;
}>();

const emit = defineEmits<{
  (e: "navigate", path: string): void;
}>();

// State for expanded/collapsed ellipsis menu
const isExpanded = ref(false);
const ellipsisMenuOpen = ref(false);

const separator = computed(() => (props.path?.includes("\\") ? "\\" : "/"));

// Maximum segments to show before collapsing
const maxSegments = computed(() => props.maxVisible ?? 4);

const allSegments = computed(() => {
  const raw = props.path || "";
  const sep = separator.value;
  const prefix =
    raw.startsWith("\\\\") ? "\\\\" : raw.startsWith(sep) ? sep : "";
  const parts = raw.split(/[\\/]+/).filter(Boolean);

  const result: { name: string; fullPath: string; isLast: boolean; index: number }[] = [];
  let current = prefix;

  parts.forEach((part, idx) => {
    if (current && !current.endsWith(sep)) {
      current += sep + part;
    } else {
      current += part;
    }
    result.push({
      name: part,
      fullPath: current,
      isLast: idx === parts.length - 1,
      index: idx,
    });
  });

  return result;
});

// Determine if we need to collapse
const shouldCollapse = computed(() => 
  !isExpanded.value && allSegments.value.length > maxSegments.value
);

// Visible segments with ellipsis logic
const visibleSegments = computed(() => {
  const all = allSegments.value;
  
  if (!shouldCollapse.value) {
    return all;
  }

  // Show: first segment + "..." + last (maxSegments - 2) segments
  // Example with maxSegments=4: [first] [...] [second-to-last] [last]
  const firstCount = 1;
  const lastCount = maxSegments.value - 1; // Keep more items at the end for context
  
  const firstPart = all.slice(0, firstCount);
  const lastPart = all.slice(-lastCount);
  
  return [...firstPart, ...lastPart];
});

// Hidden segments (for dropdown menu)
const hiddenSegments = computed(() => {
  if (!shouldCollapse.value) return [];
  
  const all = allSegments.value;
  const firstCount = 1;
  const lastCount = maxSegments.value - 1;
  
  return all.slice(firstCount, all.length - lastCount);
});

// Check if ellipsis should be shown after a segment
const showEllipsisAfter = (segmentIndex: number) => {
  return shouldCollapse.value && segmentIndex === 0 && hiddenSegments.value.length > 0;
};

const onNavigate = (segment: { fullPath: string; isLast: boolean }) => {
  if (segment.isLast) return;
  ellipsisMenuOpen.value = false;
  emit("navigate", segment.fullPath);
};

const toggleEllipsisMenu = () => {
  ellipsisMenuOpen.value = !ellipsisMenuOpen.value;
};

const expandAll = () => {
  isExpanded.value = true;
  ellipsisMenuOpen.value = false;
};

// Close menu on outside click
const closeMenu = () => {
  ellipsisMenuOpen.value = false;
};
</script>

<template>
  <nav class="breadcrumb" v-click-outside="closeMenu">
    <ol class="breadcrumb-list">
      <li class="breadcrumb-item home-item">
        <Home :size="14" class="home-icon" />
      </li>
      <template v-if="allSegments.length">
        <template v-for="seg in visibleSegments" :key="seg.fullPath">
          <!-- Regular breadcrumb item -->
          <li class="breadcrumb-item">
            <button
              class="crumb"
              :class="{ active: seg.isLast }"
              type="button"
              @click="onNavigate(seg)"
              :disabled="seg.isLast"
              :title="seg.name"
            >
              <span class="crumb-text">{{ seg.name }}</span>
            </button>
          </li>

          <!-- Ellipsis dropdown after first segment -->
          <li v-if="showEllipsisAfter(seg.index)" class="breadcrumb-item ellipsis-item">
            <span class="separator">
              <ChevronRight :size="12" />
            </span>
            
            <div class="ellipsis-container">
              <button
                class="ellipsis-btn"
                type="button"
                @click="toggleEllipsisMenu"
                :title="`${hiddenSegments.length} more folders`"
              >
                <Ellipsis :size="16" />
              </button>
              
              <!-- Dropdown menu for hidden segments -->
              <Transition name="dropdown">
                <div 
                  v-if="ellipsisMenuOpen" 
                  class="ellipsis-menu"
                >
                  <button
                    v-for="hidden in hiddenSegments"
                    :key="hidden.fullPath"
                    class="ellipsis-menu-item"
                    @click="onNavigate(hidden)"
                    :title="hidden.fullPath"
                  >
                    <Folder :size="14" />
                    <span>{{ hidden.name }}</span>
                  </button>
                  
                  <div class="ellipsis-menu-divider"></div>
                  
                  <button
                    class="ellipsis-menu-item expand-btn"
                    @click="expandAll"
                  >
                    <ArrowsUpFromLine :size="14" />
                    <span>Show full path</span>
                  </button>
                </div>
              </Transition>
            </div>
          </li>

          <!-- Separator (not after ellipsis, not after last) -->
          <li 
            v-if="!seg.isLast && !showEllipsisAfter(seg.index)" 
            class="breadcrumb-separator"
          >
            <span class="separator">
              <ChevronRight :size="12" />
            </span>
          </li>
        </template>
      </template>
      <li v-else class="breadcrumb-item">
        <span class="empty-breadcrumb">No path</span>
      </li>
    </ol>
    
    <!-- Collapse button when expanded -->
    <button
      v-if="isExpanded && allSegments.length > maxSegments"
      class="collapse-btn"
      type="button"
      @click="isExpanded = false"
      title="Collapse path"
    >
      <Minimize :size="14" />
    </button>
  </nav>
</template>

<style scoped>
.breadcrumb {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  gap: 6px;
}

.breadcrumb-list {
  display: flex;
  align-items: center;
  gap: 4px;
  list-style: none;
  margin: 0;
  padding: 0;
  min-width: 0;
  flex-wrap: nowrap;
  /* Allow dropdown to overflow beyond the list container */
  overflow: visible;
}

.breadcrumb-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex-shrink: 0;
}

/* Allow last item to shrink and show ellipsis */
.breadcrumb-item:last-child {
  flex-shrink: 1;
  min-width: 60px;
}

.breadcrumb-separator {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.crumb {
  border: none;
  background: transparent;
  padding: 4px 8px;
  margin: 0;
  font-size: 14px;
  color: var(--muted-text);
  cursor: pointer;
  white-space: nowrap;
  border-radius: 4px;
  transition: color 0.15s ease, background-color 0.15s ease;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.crumb-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

.crumb:hover:not(:disabled) {
  color: var(--title-color);
  background-color: var(--gallery-surface-hover, rgba(0, 0, 0, 0.05));
}

.crumb:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.crumb.active {
  color: var(--title-color);
  font-weight: 600;
  cursor: default;
  max-width: 200px;
}

.crumb:disabled {
  cursor: default;
}

.separator {
  color: var(--muted-text);
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  opacity: 0.6;
  flex-shrink: 0;
}

.empty-breadcrumb {
  color: var(--muted-text);
  font-size: 13px;
}

/* Ellipsis Button & Dropdown */
.ellipsis-item {
  position: relative;
}

.ellipsis-container {
  position: relative;
}

.ellipsis-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 24px;
  border: none;
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.05));
  color: var(--muted-text);
  cursor: pointer;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.15s ease;
}

.ellipsis-btn:hover {
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.1));
  color: var(--title-color);
}

.ellipsis-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Dropdown Menu */
.ellipsis-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 200px;
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 8px;
  box-shadow: var(--gallery-shadow-lg, 0 4px 20px rgba(0, 0, 0, 0.15));
  z-index: 1000;
  padding: 4px;
}

.ellipsis-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--text-color, #333);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.15s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ellipsis-menu-item span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.ellipsis-menu-item:hover {
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.05));
}

.ellipsis-menu-item:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.ellipsis-menu-divider {
  height: 1px;
  background: var(--border-color, rgba(0, 0, 0, 0.1));
  margin: 4px 8px;
}

.expand-btn {
  color: var(--primary-color);
}

/* Collapse Button */
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.05));
  color: var(--muted-text);
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.1));
  color: var(--title-color);
}

.collapse-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Dropdown Animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Dark mode support */
:root[data-theme="dark"] .ellipsis-btn {
  background: var(--gallery-surface-hover, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .ellipsis-btn:hover {
  background: var(--gallery-surface-elevated, rgba(255, 255, 255, 0.15));
}

:root[data-theme="dark"] .ellipsis-menu {
  background: var(--bg-secondary, #1e1e1e);
  border-color: var(--gallery-border-default, rgba(255, 255, 255, 0.1));
  box-shadow: var(--gallery-shadow-lg, 0 4px 20px rgba(0, 0, 0, 0.4));
}

:root[data-theme="dark"] .ellipsis-menu-item:hover {
  background: var(--gallery-surface-hover, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .collapse-btn {
  background: var(--gallery-surface-hover, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .collapse-btn:hover {
  background: var(--gallery-surface-elevated, rgba(255, 255, 255, 0.15));
}

:root[data-theme="dark"] .crumb:hover:not(:disabled) {
  background-color: var(--gallery-surface-hover, rgba(255, 255, 255, 0.08));
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}

/* Home icon */
.home-item {
  display: inline-flex;
  align-items: center;
}

.home-icon {
  color: var(--primary-color);
  opacity: 0.5;
  flex-shrink: 0;
  transition: opacity 0.15s ease;
}

.home-icon:hover {
  opacity: 0.8;
}

/* Responsive: reduce breadcrumb text max-width on phones */
@media (max-width: 480px) {
  .crumb {
    max-width: 100px;
    padding: 3px 6px;
    font-size: 13px;
  }

  .crumb.active {
    max-width: 120px;
  }

  .breadcrumb {
    gap: 4px;
  }

  .breadcrumb-list {
    gap: 2px;
  }

  .ellipsis-btn {
    width: 24px;
    height: 20px;
  }
}
</style>
