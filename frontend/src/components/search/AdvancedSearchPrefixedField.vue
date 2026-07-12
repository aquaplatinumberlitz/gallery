<script setup lang="ts">
import Input from "@/components/ui/Input.vue";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";

interface Props {
  id: string;
  label: string;
  prefix: "param:" | "advanced:";
  modelValue: string;
  placeholder: string;
  exampleInput: string;
}

defineProps<Props>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();
</script>

<template>
  <Field class="gap-1.5">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <div
      class="advanced-search-prefixed-control flex h-9 overflow-hidden rounded-md border border-input bg-background shadow-xs transition-colors focus-within:border-ring"
    >
      <span
        class="inline-flex shrink-0 items-center border-r border-input bg-muted/60 px-2.5 font-mono text-xs font-medium text-muted-foreground"
        aria-hidden="true"
      >
        {{ prefix }}
      </span>
      <Input
        :id="id"
        :model-value="modelValue"
        variant="ghost"
        class="h-full rounded-none px-2 font-mono focus-visible:border-transparent focus-visible:ring-0"
        data-focus-ring="none"
        :placeholder="placeholder"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </div>
    <FieldDescription class="flex flex-col gap-0.5 text-xs">
      <span>Enter only <code>key:value</code>. The prefix shown on the left is added automatically.</span>
      <span>
        Example: <code>{{ exampleInput }}</code> <span aria-hidden="true">→</span>
        <code>{{ prefix }}{{ exampleInput }}</code>
      </span>
    </FieldDescription>
  </Field>
</template>

<style scoped>
.advanced-search-prefixed-control:focus-within {
  box-shadow: var(--focus-within-ring-shadow);
}
</style>
