<script setup lang="ts">
import Input from "@/components/ui/Input.vue";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import type { NumericFilterValue } from "./advancedSearchModel";

export type { NumericFilterValue } from "./advancedSearchModel";

interface Props {
  id: string;
  label: string;
  modelValue: NumericFilterValue;
  operators: ReadonlyArray<{ label: string; value: string }>;
  placeholder?: string;
  inputmode?: "numeric" | "decimal";
  error?: string;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: undefined,
  inputmode: "decimal",
  error: undefined,
});

const emit = defineEmits<{
  "update:modelValue": [value: NumericFilterValue];
}>();

const errorId = `${props.id}-error`;

function updateOperator(event: Event) {
  emit("update:modelValue", {
    value: props.modelValue.value,
    op: (event.target as HTMLSelectElement).value,
  });
}

function updateValue(value: string) {
  emit("update:modelValue", { value, op: props.modelValue.op });
}
</script>

<template>
  <Field :data-invalid="Boolean(error)" class="min-w-0 gap-1.5">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <div class="flex min-w-0 gap-2">
      <select
        :id="`${id}-operator`"
        :value="modelValue.op"
        :aria-label="`${label} operator`"
        :aria-invalid="Boolean(error)"
        :aria-describedby="error ? errorId : undefined"
        class="h-9 w-16 shrink-0 cursor-pointer rounded-md border border-input bg-background px-2 text-sm font-medium text-foreground shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        @change="updateOperator"
      >
        <option v-for="operator in operators" :key="operator.value" :value="operator.value">
          {{ operator.label }}
        </option>
      </select>
      <Input
        :id="id"
        :model-value="modelValue.value"
        :placeholder="placeholder"
        :inputmode="inputmode"
        :aria-invalid="Boolean(error)"
        :aria-describedby="error ? errorId : undefined"
        class="min-w-0"
        @update:model-value="updateValue"
      />
    </div>
    <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
  </Field>
</template>
