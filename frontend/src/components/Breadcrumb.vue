<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from "vue";
import { vClickOutside } from "../directives/clickOutside";
import { Ellipsis, Folder, ArrowsUpFromLine, Minimize, Home } from "lucide-vue-next";
import BreadcrumbRoot from "./ui/Breadcrumb.vue";
import BreadcrumbList from "./ui/BreadcrumbList.vue";
import BreadcrumbItem from "./ui/BreadcrumbItem.vue";
import BreadcrumbLink from "./ui/BreadcrumbLink.vue";
import BreadcrumbPage from "./ui/BreadcrumbPage.vue";
import BreadcrumbSeparator from "./ui/BreadcrumbSeparator.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = defineProps<{
  path?: string;
  maxVisible?: number;
}>();

const emit = defineEmits<{
  (e: "navigate", path: string): void;
}>();

const isExpanded = ref(false);
const ellipsisMenuOpen = ref(false);
const ellipsisBtnRef = ref<HTMLElement | HTMLElement[] | null>(null);
const menuPosition = ref({ top: 0, left: 0 });

function getEllipsisButtonElement() {
  const value = ellipsisBtnRef.value;
  if (Array.isArray(value)) {
    return value.find((item): item is HTMLElement => item instanceof HTMLElement) ?? null;
  }
  return value instanceof HTMLElement ? value : null;
}

function updateMenuPosition() {
  const button = getEllipsisButtonElement();
  if (!button) return;
  const rect = button.getBoundingClientRect();
  menuPosition.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 320),
    left: Math.min(rect.left, window.innerWidth - 310),
  };
}

watch(ellipsisMenuOpen, async (open) => {
  if (open) {
    await nextTick();
    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, { passive: true, capture: true });
  } else {
    window.removeEventListener("resize", updateMenuPosition);
    window.removeEventListener("scroll", updateMenuPosition, { capture: true } as EventListenerOptions);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateMenuPosition);
  window.removeEventListener("scroll", updateMenuPosition, { capture: true } as EventListenerOptions);
});

const separator = computed(() => (props.path?.includes("\\") ? "\\" : "/"));
const maxSegments = computed(() => props.maxVisible ?? 4);

const allSegments = computed(() => {
  const raw = props.path || "";
  const sep = separator.value;
  const prefix = raw.startsWith("\\\\") ? "\\\\" : raw.startsWith(sep) ? sep : "";
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

const shouldCollapse = computed(() => !isExpanded.value && allSegments.value.length > maxSegments.value);

const visibleSegments = computed(() => {
  const all = allSegments.value;
  if (!shouldCollapse.value) return all;

  const firstCount = 1;
  const lastCount = maxSegments.value - 1;
  const firstPart = all.slice(0, firstCount);
  const lastPart = all.slice(-lastCount);
  return [...firstPart, ...lastPart];
});

const hiddenSegments = computed(() => {
  if (!shouldCollapse.value) return [];
  const all = allSegments.value;
  const firstCount = 1;
  const lastCount = maxSegments.value - 1;
  return all.slice(firstCount, all.length - lastCount);
});

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

const closeMenu = () => {
  ellipsisMenuOpen.value = false;
};
</script>

<template>
  <BreadcrumbRoot v-click-outside="closeMenu" class="breadcrumb">
    <BreadcrumbList>
      <BreadcrumbItem>
        <Home class="size-3.5 text-primary opacity-50 shrink-0" />
      </BreadcrumbItem>
      <template v-if="allSegments.length">
        <template v-for="seg in visibleSegments" :key="seg.fullPath">
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink
              v-if="!seg.isLast"
              :disabled="seg.isLast"
              as="button"
              type="button"
              @click="onNavigate(seg)"
            >
              {{ seg.name }}
            </BreadcrumbLink>
            <BreadcrumbPage v-else>
              {{ seg.name }}
            </BreadcrumbPage>
          </BreadcrumbItem>

          <template v-if="showEllipsisAfter(seg.index)">
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <div class="relative">
                <Tooltip>
                  <TooltipTrigger as-child>
                    <button
                      ref="ellipsisBtnRef"
                      class="ellipsis-btn"
                      type="button"
                      @click="toggleEllipsisMenu"
                      :aria-label="`${hiddenSegments.length} more folders`"
                    >
                      <Ellipsis class="size-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>{{ hiddenSegments.length }} more folders</TooltipContent>
                </Tooltip>

                <Transition name="dropdown">
                  <div
                    v-if="ellipsisMenuOpen"
                    class="ellipsis-menu"
                    :style="{ top: menuPosition.top + 'px', left: menuPosition.left + 'px' }"
                  >
                    <button
                      v-for="hidden in hiddenSegments"
                      :key="hidden.fullPath"
                      class="ellipsis-menu-item"
                      @click="onNavigate(hidden)"
                    >
                      <Folder class="size-3.5" />
                      <span>{{ hidden.name }}</span>
                    </button>

                    <div class="ellipsis-menu-divider"></div>

                    <button class="ellipsis-menu-item expand-btn" @click="expandAll">
                      <ArrowsUpFromLine class="size-3.5" />
                      <span>Show full path</span>
                    </button>
                  </div>
                </Transition>
              </div>
            </BreadcrumbItem>
          </template>
        </template>
      </template>
      <template v-else>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <span class="text-sm text-muted-foreground">No path</span>
        </BreadcrumbItem>
      </template>
    </BreadcrumbList>

    <Tooltip v-if="isExpanded && allSegments.length > maxSegments">
      <TooltipTrigger as-child>
        <button class="collapse-btn" type="button" aria-label="Collapse path" @click="isExpanded = false">
          <Minimize class="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Collapse path</TooltipContent>
    </Tooltip>
  </BreadcrumbRoot>
</template>

<style scoped>
/* Breadcrumb wrapper */
.breadcrumb {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  gap: 1.5rem;
}

/* Ellipsis button */
.ellipsis-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  min-height: 40px;
  padding: 4px 8px;
  border: none;
  background: var(--accent, rgba(0, 0, 0, 0.05));
  color: var(--muted-foreground);
  cursor: pointer;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.15s ease;
}

.ellipsis-btn:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}

.ellipsis-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--ring);
}

:root[data-theme="dark"] .ellipsis-btn {
  background: var(--accent, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .ellipsis-btn:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}

/* Collapse button */
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: var(--accent, rgba(0, 0, 0, 0.05));
  color: var(--muted-foreground);
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}

.collapse-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--ring);
}

:root[data-theme="dark"] .collapse-btn {
  background: var(--accent, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .collapse-btn:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}

/* Dropdown Menu */
.ellipsis-menu {
  position: fixed;
  min-width: 200px;
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  padding: 4px;
}

.ellipsis-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 40px;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--foreground);
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
  background: var(--accent, rgba(0, 0, 0, 0.05));
}

.ellipsis-menu-item:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--ring);
}

.ellipsis-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 8px;
}

.expand-btn {
  color: var(--foreground);
}

/* Dropdown Animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Dark mode dropdown */
:root[data-theme="dark"] .ellipsis-menu {
  background: var(--popover);
  border-color: var(--border, rgba(255, 255, 255, 0.1));
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .ellipsis-menu-item:hover {
  background: var(--accent, rgba(255, 255, 255, 0.08));
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}

/* Responsive */
@media (max-width: 480px) {
  .breadcrumb {
    gap: 4px;
  }

  .ellipsis-btn {
    min-width: 36px;
    min-height: 36px;
    padding: 2px 6px;
  }
}
</style>
