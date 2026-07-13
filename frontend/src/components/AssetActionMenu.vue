<script setup lang="ts">
import { MoreHorizontal, ScanSearch } from "lucide-vue-next";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

withDefaults(defineProps<{ label?: string; dark?: boolean }>(), {
  label: "Image actions",
  dark: false,
});

const emit = defineEmits<{ findRelated: [] }>();

defineOptions({ inheritAttrs: false });
</script>

<template>
  <div class="asset-action-menu" v-bind="$attrs" @click.stop>
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <button
          type="button"
          class="asset-action-trigger"
          :class="{ 'asset-action-trigger-dark': dark }"
          :aria-label="label"
          :title="label"
          @click.stop
          @keydown.stop
        >
          <MoreHorizontal class="size-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" :class="['min-w-44', dark && 'z-[10050]']" @click.stop>
        <DropdownMenuItem @select="emit('findRelated')">
          <ScanSearch />
          Find related
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<style scoped>
.asset-action-menu {
  display: inline-flex;
}

.asset-action-trigger {
  display: inline-flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--background) 86%, transparent);
  color: var(--foreground);
  box-shadow: 0 8px 24px color-mix(in srgb, black 18%, transparent);
  backdrop-filter: blur(10px);
  cursor: pointer;
}

.asset-action-trigger:hover {
  background: var(--accent);
}

.asset-action-trigger:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.asset-action-trigger-dark {
  border-color: rgba(255, 255, 255, 0.22);
  background: rgba(0, 0, 0, 0.48);
  color: white;
}

.asset-action-trigger-dark:hover {
  background: rgba(255, 255, 255, 0.14);
}
</style>
