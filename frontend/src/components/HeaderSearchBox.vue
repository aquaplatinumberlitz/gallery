<script setup lang="ts">
import { computed } from "vue";
import { Loader2, Search, X } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = withDefaults(
  defineProps<{
    id: string;
    modelValue: string;
    loading?: boolean;
    placeholder?: string;
    compact?: boolean;
  }>(),
  {
    loading: false,
    placeholder: "Search",
    compact: false,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  clear: [];
}>();

const hasQuery = computed(() => props.modelValue.length > 0);
</script>

<template>
  <div class="search-box" :class="{ 'is-compact': compact }">
    <Loader2 v-if="loading" class="search-leading-icon search-leading-loading" aria-hidden="true" />
    <Search v-else class="search-leading-icon" aria-hidden="true" />
    <Input
      :id="id"
      :model-value="modelValue"
      @update:model-value="emit('update:modelValue', $event)"
      @keydown.enter="emit('submit')"
      type="search"
      variant="ghost"
      :placeholder="placeholder"
      autocomplete="off"
      class="search-input"
      data-focus-ring="none"
    />
    <Tooltip v-if="hasQuery">
      <TooltipTrigger as-child>
        <Button
          variant="ghost"
          size="icon"
          class="clear-btn search-action-btn"
          type="button"
          aria-label="Clear search"
          @click="emit('clear')"
        >
          <X class="gallery-icon-xs" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Clear search</TooltipContent>
    </Tooltip>
    <slot name="actions" />
  </div>
</template>

<style scoped lang="scss">
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 360px;
  width: min(520px, 52vw);
  height: 40px;
  padding: 0 6px 0 12px;
  border: 1px solid var(--input);
  border-radius: 12px;
  background: var(--background);
  box-shadow: 0 1px 2px color-mix(in srgb, black 6%, transparent);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.search-box:focus-within {
  border-color: var(--ring);
  box-shadow: var(--focus-within-ring-shadow);
}

.search-box.is-compact {
  min-width: 0;
  width: 100%;
  height: 34px;
  padding-right: 10px;
  border-radius: 9px;
}

.search-input {
  flex: 1;
  min-width: 0;
}

.search-input::-webkit-search-decoration,
.search-input::-webkit-search-cancel-button,
.search-input::-webkit-search-results-button,
.search-input::-webkit-search-results-decoration {
  -webkit-appearance: none;
  appearance: none;
  display: none;
}

.search-input:focus-visible {
  box-shadow: none;
}

.search-leading-icon {
  flex-shrink: 0;
  width: var(--gallery-icon-toolbar);
  height: var(--gallery-icon-toolbar);
  color: var(--muted-foreground);
}

.search-leading-loading {
  animation: searchLeadingSpin 1s linear infinite;
}

@keyframes searchLeadingSpin {
  to {
    transform: rotate(360deg);
  }
}

.search-action-btn,
:slotted(.search-action-btn) {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: var(--muted-foreground);
  background: transparent;
  box-shadow: none;
}

.search-box .search-action-btn:hover,
.search-box :slotted(.search-action-btn:hover) {
  background: color-mix(in srgb, var(--foreground) 7%, transparent);
  color: var(--foreground);
}

.search-box .search-action-btn:focus-visible,
.search-box :slotted(.search-action-btn:focus-visible) {
  border-color: var(--ring);
  box-shadow: var(--focus-ring-shadow);
}

.search-box .search-action-btn:active,
.search-box :slotted(.search-action-btn:active) {
  background: color-mix(in srgb, var(--foreground) 10%, transparent);
}

.gallery-icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}

@media (max-width: 1199px) {
  .search-box {
    min-width: 180px;
  }

  .search-box.is-compact {
    min-width: 0;
    width: 100%;
  }
}

@media (max-width: 767px) {
  .search-box {
    flex: 1;
    min-width: 0;
    height: 36px;
    padding: 0 10px;
    gap: 6px;
    border: 1px solid var(--input);
    border-radius: 10px;
    background: var(--card);
    transition:
      border-color 0.2s,
      box-shadow 0.2s;
  }

  .search-box:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--ring) 25%, transparent);
  }

  .search-box:focus-within {
    border-color: var(--primary);
    box-shadow: var(--focus-within-ring-shadow);
  }
}

@media (max-width: 480px) {
  .search-box {
    width: 30px;
    height: 30px;
  }

  .search-box.is-compact {
    width: 100%;
    min-width: 0;
  }
}
</style>
