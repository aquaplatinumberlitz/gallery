<script setup lang="ts">
import { computed } from "vue";
import Input from "@/components/ui/Input.vue";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AcceptableValue } from "reka-ui";
import {
  BETWEEN_SEPARATOR,
  isBetweenOp,
  joinBetweenValue,
  splitBetweenValue,
  type NumericFilterValue,
} from "./advancedSearchModel";

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
const isBetween = computed(() => isBetweenOp(props.modelValue.op));
const betweenParts = computed(() => splitBetweenValue(props.modelValue.value));

function updateOperator(op: AcceptableValue) {
  const opStr = op == null ? "=" : String(op);
  if (isBetweenOp(opStr) && !BETWEEN_SEPARATOR.includes(props.modelValue.value)) {
    emit("update:modelValue", { value: joinBetweenValue(props.modelValue.value, ""), op: opStr });
  } else {
    emit("update:modelValue", { value: props.modelValue.value, op: opStr });
  }
}

function updateValue(value: string) {
  emit("update:modelValue", { value, op: props.modelValue.op });
}

function updateBetweenLow(low: string) {
  emit("update:modelValue", {
    value: joinBetweenValue(low, betweenParts.value[1]),
    op: props.modelValue.op,
  });
}

function updateBetweenHigh(high: string) {
  emit("update:modelValue", {
    value: joinBetweenValue(betweenParts.value[0], high),
    op: props.modelValue.op,
  });
}
</script>

<template>
  <Field :data-invalid="Boolean(error)" class="min-w-0 gap-1.5">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <div
      class="advanced-search-numeric-control flex items-stretch rounded-md border border-input bg-background shadow-xs transition-colors"
    >
      <Select :model-value="modelValue.op" @update:model-value="updateOperator">
        <SelectTrigger
          class="advanced-search-operator h-auto min-h-9 w-20 shrink-0 rounded-l-md rounded-r-none border-r border-input bg-transparent px-2 text-sm font-medium text-foreground data-[placeholder]:text-muted-foreground"
          :aria-label="`${label} operator`"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="start" class="z-[calc(var(--gallery-z-modal)+1)] min-w-20">
          <SelectItem v-for="operator in operators" :key="operator.value" :value="operator.value">
            {{ operator.label }}
          </SelectItem>
        </SelectContent>
      </Select>
      <template v-if="isBetween">
        <Input
          :id="id"
          :model-value="betweenParts[0]"
          :inputmode="inputmode"
          :aria-label="`${label} lower bound`"
          :aria-invalid="Boolean(error)"
          :aria-describedby="error ? errorId : undefined"
          variant="ghost"
          data-focus-ring="none"
          class="advanced-search-numeric-input h-full min-w-0 flex-1 rounded-none px-2 focus-visible:border-transparent focus-visible:ring-0"
          :placeholder="placeholder"
          @update:model-value="updateBetweenLow"
        />
        <span
          class="inline-flex shrink-0 items-center border-x border-input bg-muted/60 px-1.5 text-xs font-medium text-muted-foreground"
          aria-hidden="true"
        >
          –
        </span>
        <Input
          :id="`${id}-high`"
          :model-value="betweenParts[1]"
          :inputmode="inputmode"
          :aria-label="`${label} upper bound`"
          :aria-invalid="Boolean(error)"
          :aria-describedby="error ? errorId : undefined"
          variant="ghost"
          data-focus-ring="none"
          class="advanced-search-numeric-input h-full min-w-0 flex-1 rounded-r-md px-2 focus-visible:border-transparent focus-visible:ring-0"
          :placeholder="placeholder"
          @update:model-value="updateBetweenHigh"
        />
      </template>
      <Input
        v-else
        :id="id"
        :model-value="modelValue.value"
        :placeholder="placeholder"
        :inputmode="inputmode"
        :aria-invalid="Boolean(error)"
        :aria-describedby="error ? errorId : undefined"
        variant="ghost"
        data-focus-ring="none"
        class="advanced-search-numeric-input h-full min-w-0 flex-1 rounded-r-md rounded-l-none px-2 focus-visible:border-transparent focus-visible:ring-0"
        @update:model-value="updateValue"
      />
    </div>
    <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
  </Field>
</template>

<style scoped>
.advanced-search-numeric-control:has(input:focus-visible) {
  border-color: var(--ring);
  box-shadow: var(--focus-within-ring-shadow);
}

@media (max-width: 1023px) {
  .advanced-search-operator,
  .advanced-search-numeric-input {
    min-height: 44px;
    padding-block: 0.625rem;
  }
}
</style>
