<script setup lang="ts">
import { computed, ref } from "vue";
import { Folders, Minimize, Home } from "lucide-vue-next";
import BreadcrumbRoot from "./ui/Breadcrumb.vue";
import BreadcrumbList from "./ui/BreadcrumbList.vue";
import BreadcrumbItem from "./ui/BreadcrumbItem.vue";
import BreadcrumbLink from "./ui/BreadcrumbLink.vue";
import BreadcrumbPage from "./ui/BreadcrumbPage.vue";
import BreadcrumbSeparator from "./ui/BreadcrumbSeparator.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { pathContains } from "../stores/gallery";

const props = defineProps<{
  path?: string;
  rootPath?: string;
  maxVisible?: number;
}>();

const emit = defineEmits<{
  (e: "navigate", path: string): void;
}>();

const isExpanded = ref(false);
const ellipsisMenuOpen = ref(false);

const separator = computed(() => (props.path?.includes("\\") ? "\\" : "/"));
const maxSegments = computed(() => props.maxVisible ?? 4);
const rootPath = computed(() => props.rootPath?.trim() ?? "");

type Segment = { name: string; fullPath: string; isLast: boolean; index: number };

const allSegments = computed(() => {
  const raw = props.path || "";
  const sep = separator.value;
  const prefix = raw.startsWith("\\\\") ? "\\\\" : raw.startsWith(sep) ? sep : "";
  const parts = raw.split(/[\\/]+/).filter(Boolean);

  const result: Segment[] = [];
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

const canNavigateToSegment = (segment: Segment) => !rootPath.value || pathContains(rootPath.value, segment.fullPath);

const onNavigate = (segment: Segment) => {
  if (segment.isLast || !canNavigateToSegment(segment)) return;
  ellipsisMenuOpen.value = false;
  emit("navigate", segment.fullPath);
};

const expandAll = () => {
  isExpanded.value = true;
  ellipsisMenuOpen.value = false;
};
</script>

<template>
  <BreadcrumbRoot class="breadcrumb">
    <BreadcrumbList class="breadcrumb-list">
      <BreadcrumbItem>
        <Home class="size-3.5 text-primary opacity-50 shrink-0" data-testid="home-icon" />
      </BreadcrumbItem>
      <template v-if="allSegments.length">
        <template v-for="seg in visibleSegments" :key="seg.fullPath">
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink
              v-if="!seg.isLast && canNavigateToSegment(seg)"
              :disabled="false"
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
              <DropdownMenu v-model:open="ellipsisMenuOpen">
                <DropdownMenuTrigger
                  class="hover:text-foreground"
                  :aria-label="`${hiddenSegments.length} more folders`"
                >
                  <span role="presentation" aria-hidden="true" class="flex size-5 items-center justify-center">
                    <Folders class="size-4" />
                  </span>
                  <span class="sr-only">Toggle hidden folders</span>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    v-for="hidden in hiddenSegments"
                    :key="hidden.fullPath"
                    :disabled="!canNavigateToSegment(hidden)"
                    @select="onNavigate(hidden)"
                  >
                    {{ hidden.name }}
                  </DropdownMenuItem>

                  <DropdownMenuItem @select="expandAll"> Show full path </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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

    <div v-if="$slots.actions || (isExpanded && allSegments.length > maxSegments)" class="breadcrumb-actions">
      <slot name="actions" />

      <Tooltip v-if="isExpanded && allSegments.length > maxSegments">
        <TooltipTrigger as-child>
          <button class="collapse-btn" type="button" aria-label="Collapse path" @click="isExpanded = false">
            <Minimize class="size-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Collapse path</TooltipContent>
      </Tooltip>
    </div>
  </BreadcrumbRoot>
</template>

<style scoped>
/* Breadcrumb wrapper */
.breadcrumb {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  gap: 0.5rem;
}

.breadcrumb-list {
  min-width: 0;
  width: fit-content;
  max-width: 100%;
  flex: 0 1 auto;
  flex-wrap: nowrap;
  overflow: hidden;
}

.breadcrumb-actions {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 4px;
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
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 50%, transparent);
}

:root[data-theme="dark"] .collapse-btn {
  background: var(--accent, rgba(255, 255, 255, 0.08));
}

:root[data-theme="dark"] .collapse-btn:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}

/* Responsive */
@media (max-width: 480px) {
  .breadcrumb {
    gap: 4px;
  }
}
</style>
