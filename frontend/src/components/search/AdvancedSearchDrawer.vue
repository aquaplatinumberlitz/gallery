<script setup lang="ts">
import { computed, ref, shallowRef, watch } from "vue";
import { useForm, useStore } from "@tanstack/vue-form";
import { Search, Trash2, X } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useFacetsQuery } from "@/composables/useFacetsQuery";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import { filterToDisplayString } from "@/utils/serializeAdvancedSearchToQuery";
import type { FacetEntry, FieldFilter } from "@/types";
import AdvancedSearchNumericField, { type NumericFilterValue } from "./AdvancedSearchNumericField.vue";

interface Props {
  isOpen: boolean;
  initialFilters: FieldFilter[];
}

const props = defineProps<Props>();

const emit = defineEmits<{
  close: [];
  apply: [filters: FieldFilter[]];
}>();

const { activeImportRootPath } = useActiveLibrarySelection();
const facetsQuery = useFacetsQuery(computed(() => activeImportRootPath.value));

const NUMERIC_OPS = [
  { label: "=", value: "=" },
  { label: ">", value: ">" },
  { label: ">=", value: ">=" },
  { label: "<", value: "<" },
  { label: "<=", value: "<=" },
] as const;

const aspectRatios = ["1:1", "4:3", "16:9", "3:2", "2:3", "9:16"] as const;

type NumericFieldName =
  | "seed"
  | "steps"
  | "cfg"
  | "width"
  | "height"
  | "clip_skip"
  | "denoising_strength"
  | "hires_upscale"
  | "hires_steps";

interface FormValues {
  prompt: string;
  negative: string;
  model: string;
  folder: string;
  name: string;
  date: string;
  sampler: string;
  scheduler: string;
  lora: string;
  vae: string;
  seed: NumericFilterValue;
  steps: NumericFilterValue;
  cfg: NumericFilterValue;
  clip_skip: NumericFilterValue;
  denoising_strength: NumericFilterValue;
  hires_upscale: NumericFilterValue;
  hires_steps: NumericFilterValue;
  width: NumericFilterValue;
  height: NumericFilterValue;
  size: string;
  ratio: string;
  param: string;
  advanced: string;
  raw: string;
}

type FormFieldName = keyof FormValues;

interface StagedToken {
  id: string;
  filter: FieldFilter;
  slot: FormFieldName | null;
  primary: boolean;
}

const fieldOrder: FormFieldName[] = [
  "prompt",
  "negative",
  "model",
  "folder",
  "name",
  "date",
  "sampler",
  "scheduler",
  "lora",
  "vae",
  "seed",
  "steps",
  "cfg",
  "clip_skip",
  "denoising_strength",
  "hires_upscale",
  "hires_steps",
  "width",
  "height",
  "size",
  "ratio",
  "param",
  "advanced",
  "raw",
];

const numericFields = new Set<FormFieldName>([
  "seed",
  "steps",
  "cfg",
  "clip_skip",
  "denoising_strength",
  "hires_upscale",
  "hires_steps",
  "width",
  "height",
]);

function defaultNumericValue(): NumericFilterValue {
  return { value: "", op: "=" };
}

function buildDefaultValues(): FormValues {
  return {
    prompt: "",
    negative: "",
    model: "",
    folder: "",
    name: "",
    date: "",
    sampler: "",
    scheduler: "",
    lora: "",
    vae: "",
    seed: defaultNumericValue(),
    steps: defaultNumericValue(),
    cfg: defaultNumericValue(),
    clip_skip: defaultNumericValue(),
    denoising_strength: defaultNumericValue(),
    hires_upscale: defaultNumericValue(),
    hires_steps: defaultNumericValue(),
    width: defaultNumericValue(),
    height: defaultNumericValue(),
    size: "",
    ratio: "",
    param: "",
    advanced: "",
    raw: "",
  };
}

function slotForFilter(filter: FieldFilter): FormFieldName | null {
  const field = filter.field.toLowerCase();
  const aliases: Record<string, FormFieldName> = {
    positive: "prompt",
    path: "folder",
    cfg_scale: "cfg",
    aspect_ratio: "ratio",
    denoising: "denoising_strength",
  };
  const normalized = aliases[field] ?? field;
  return fieldOrder.includes(normalized as FormFieldName) ? (normalized as FormFieldName) : null;
}

function setValueFromFilter(values: FormValues, slot: FormFieldName, filter: FieldFilter) {
  if (numericFields.has(slot)) {
    values[slot as NumericFieldName] = { value: filter.value, op: filter.operator || "=" };
    return;
  }
  values[slot as Exclude<FormFieldName, NumericFieldName>] = filter.value;
}

function stageFilters(filters: FieldFilter[]) {
  const values = buildDefaultValues();
  const seen = new Set<FormFieldName>();
  const tokens = filters.map((filter, index): StagedToken => {
    const slot = slotForFilter(filter);
    const primary = slot !== null && !seen.has(slot);
    if (slot && primary) {
      seen.add(slot);
      setValueFromFilter(values, slot, filter);
    }
    return { id: `filter-${index}`, filter: { ...filter }, slot, primary };
  });

  stagedTokens.value = tokens;
  openingValues.value = structuredClone(values);
  activeAccordionSections.value = computeOpenSections(filters);
  form.reset(values);
}

function fieldValue(values: FormValues, slot: FormFieldName): string | NumericFilterValue {
  return values[slot];
}

function fieldChanged(values: FormValues, slot: FormFieldName): boolean {
  const current = fieldValue(values, slot);
  const opening = fieldValue(openingValues.value, slot);
  if (typeof current === "string" && typeof opening === "string") return current !== opening;
  if (typeof current !== "string" && typeof opening !== "string") {
    return current.value !== opening.value || current.op !== opening.op;
  }
  return true;
}

function filterForSlot(slot: FormFieldName, values: FormValues): FieldFilter | null {
  const outputFields: Record<FormFieldName, string> = {
    prompt: "prompt",
    negative: "negative",
    model: "model",
    folder: "folder",
    name: "name",
    date: "date",
    sampler: "sampler",
    scheduler: "scheduler",
    lora: "lora",
    vae: "vae",
    seed: "seed",
    steps: "steps",
    cfg: "cfg",
    clip_skip: "clip_skip",
    denoising_strength: "denoising_strength",
    hires_upscale: "hires_upscale",
    hires_steps: "hires_steps",
    width: "width",
    height: "height",
    size: "size",
    ratio: "ratio",
    param: "param",
    advanced: "advanced",
    raw: "raw",
  };
  const value = fieldValue(values, slot);
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? { field: outputFields[slot], value: trimmed } : null;
  }
  const trimmed = value.value.trim();
  if (!trimmed) return null;
  return {
    field: outputFields[slot],
    value: trimmed,
    operator: value.op === "=" ? undefined : value.op,
  };
}

function collectStagedFilters(values: FormValues): FieldFilter[] {
  const result: FieldFilter[] = [];
  const primarySlots = new Set<FormFieldName>();

  for (const token of stagedTokens.value) {
    if (!token.primary || token.slot === null) {
      if (token.filter.value.trim()) result.push({ ...token.filter });
      continue;
    }
    primarySlots.add(token.slot);
    if (!fieldChanged(values, token.slot)) {
      if (token.filter.value.trim()) result.push({ ...token.filter });
      continue;
    }
    const replacement = filterForSlot(token.slot, values);
    if (replacement) result.push(replacement);
  }

  for (const slot of fieldOrder) {
    if (primarySlots.has(slot)) continue;
    const filter = filterForSlot(slot, values);
    if (filter) result.push(filter);
  }
  return result;
}

function isInteger(value: string) {
  return /^-?\d+$/.test(value.trim());
}

function isPositiveInteger(value: string) {
  return /^\d+$/.test(value.trim()) && Number(value) > 0;
}

function isPositiveNumber(value: string) {
  return Number.isFinite(Number(value)) && Number(value) > 0;
}

function validateValues(value: FormValues): Partial<Record<FormFieldName, string>> {
  const errors: Partial<Record<FormFieldName, string>> = {};
  if (value.seed.value && !isInteger(value.seed.value)) errors.seed = "Enter a whole number";
  for (const field of ["steps", "clip_skip", "hires_steps", "width", "height"] as const) {
    if (value[field].value && !isPositiveInteger(value[field].value)) errors[field] = "Enter a positive whole number";
  }
  for (const field of ["cfg", "denoising_strength", "hires_upscale"] as const) {
    if (value[field].value && !isPositiveNumber(value[field].value)) errors[field] = "Enter a positive number";
  }
  if (value.size) {
    const match = value.size.match(/^(\d+)\s*x\s*(\d+)$/i);
    if (!match || Number(match[1]) <= 0 || Number(match[2]) <= 0) errors.size = "Use a positive size such as 1024x768";
  }
  if (value.ratio) {
    const match = value.ratio.match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
    if (!match || Number(match[1]) <= 0 || Number(match[2]) <= 0) errors.ratio = "Use a ratio such as 16:9";
  }
  return errors;
}

const sectionFields: Record<string, FormFieldName[]> = {
  content: ["prompt", "negative", "model", "folder", "name", "date"],
  generation: [
    "sampler",
    "scheduler",
    "lora",
    "vae",
    "seed",
    "steps",
    "cfg",
    "clip_skip",
    "denoising_strength",
    "hires_upscale",
    "hires_steps",
  ],
  dimensions: ["width", "height", "size", "ratio"],
  syntax: ["param", "advanced", "raw"],
};

function sectionForField(field: FormFieldName): string | null {
  for (const [section, fields] of Object.entries(sectionFields)) {
    if (fields.includes(field)) return section;
  }
  return null;
}

function computeOpenSections(filters: FieldFilter[]): string[] {
  const sections = new Set<string>(["content"]);
  for (const filter of filters) {
    const slot = slotForFilter(filter);
    if (slot) {
      const section = sectionForField(slot);
      if (section) sections.add(section);
    }
  }
  return [...sections];
}

const stagedTokens = shallowRef<StagedToken[]>([]);
const openingValues = shallowRef<FormValues>(buildDefaultValues());
const activeAccordionSections = ref(["content"]);

const form = useForm({
  defaultValues: buildDefaultValues(),
  validators: {
    onChange: ({ value }) => {
      const fields = validateValues(value);
      return Object.keys(fields).length ? { fields } : undefined;
    },
  },
  onSubmit: ({ value }) => {
    emit("apply", collectStagedFilters(value));
    emit("close");
  },
});

const formState = useStore(form.store);
const validationErrors = computed(() => validateValues(formState.value.values));
const stagedFilters = computed(() => collectStagedFilters(formState.value.values));
const activeFilterCount = computed(() => stagedFilters.value.length);
const activeFilterSummary = computed(() =>
  activeFilterCount.value === 0
    ? "No filters selected"
    : `${activeFilterCount.value} filter${activeFilterCount.value === 1 ? "" : "s"} selected`,
);
const applyLabel = computed(() =>
  activeFilterCount.value > 0
    ? `Apply ${activeFilterCount.value} filter${activeFilterCount.value === 1 ? "" : "s"}`
    : "Apply filters",
);
const passThroughTokens = computed(() => stagedTokens.value.filter((token) => !token.primary || token.slot === null));

const facetData = computed(() => facetsQuery.data.value);
const facetModelOptions = computed(() => facetData.value?.model?.map((entry: FacetEntry) => entry.value) ?? []);
const facetSamplerOptions = computed(() => facetData.value?.sampler?.map((entry: FacetEntry) => entry.value) ?? []);
const facetSchedulerOptions = computed(() => facetData.value?.scheduler?.map((entry: FacetEntry) => entry.value) ?? []);
const facetsLoading = computed(() => facetsQuery.isLoading.value);
const facetsFailed = computed(() => facetsQuery.isError?.value ?? false);

function facetStatus(options: string[]) {
  if (facetsLoading.value) return "Loading suggestions";
  if (facetsFailed.value) return "Suggestions unavailable";
  if (options.length === 0) return "No suggestions available";
  return "";
}

function handleClearAll() {
  stagedTokens.value = [];
  form.reset(buildDefaultValues());
}

function handleResetChanges() {
  stageFilters(props.initialFilters);
}

function handleCancel() {
  stageFilters(props.initialFilters);
  emit("close");
}

function handleOpenChange(open: boolean) {
  if (!open) handleCancel();
}

function removeStagedToken(id: string) {
  stagedTokens.value = stagedTokens.value.filter((token) => token.id !== id);
}

function handleShortcut(event: KeyboardEvent) {
  if (event.key !== "Enter" || (!event.ctrlKey && !event.metaKey)) return;
  event.preventDefault();
  if (formState.value.isValid) void form.handleSubmit();
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) stageFilters(props.initialFilters);
  },
  { immediate: true },
);
</script>

<template>
  <Sheet :open="isOpen" @update:open="handleOpenChange">
    <SheetContent
      side="right"
      class="advanced-search-drawer w-[560px] max-w-[560px] gap-0 p-0 sm:max-w-[560px]"
      data-testid="advanced-search-drawer"
    >
      <form class="flex h-full min-h-0 flex-col" @submit.prevent="form.handleSubmit()" @keydown="handleShortcut">
        <SheetHeader class="shrink-0 gap-1 border-b px-6 py-5 pr-14 text-left">
          <SheetTitle class="text-lg">Advanced Search</SheetTitle>
          <SheetDescription>Build precise metadata and file filters.</SheetDescription>
        </SheetHeader>

        <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5" data-testid="advanced-search-scroll-body">
          <div class="mb-4 flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
            <p class="text-sm font-medium" aria-live="polite">{{ activeFilterSummary }}</p>
            <Button type="button" variant="ghost" size="sm" :disabled="activeFilterCount === 0" @click="handleClearAll">
              <Trash2 data-icon="inline-start" />
              Clear all
            </Button>
          </div>

          <Accordion
            type="multiple"
            :model-value="activeAccordionSections"
            @update:model-value="activeAccordionSections = $event as string[]"
            class="w-full"
            data-testid="advanced-search-groups"
          >
            <AccordionItem value="content">
              <AccordionTrigger class="text-left no-underline hover:no-underline">
                <span class="flex flex-col gap-0.5">
                  <span>Content and files</span>
                  <span class="text-xs font-normal text-muted-foreground">Words, models, locations, and dates</span>
                </span>
              </AccordionTrigger>
              <AccordionContent class="pt-1">
                <FieldGroup class="gap-4">
                  <form.Field name="prompt" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-prompt">Prompt</FieldLabel>
                      <Input
                        id="advanced-search-prompt"
                        :model-value="field.state.value"
                        placeholder="blue archive"
                        @update:model-value="field.handleChange"
                      />
                    </Field>
                  </form.Field>
                  <form.Field name="negative" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-negative">Negative prompt</FieldLabel>
                      <Input
                        id="advanced-search-negative"
                        :model-value="field.state.value"
                        placeholder="blurry, watermark"
                        @update:model-value="field.handleChange"
                      />
                    </Field>
                  </form.Field>
                  <div class="grid grid-cols-2 gap-4">
                    <form.Field name="model" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-model">Model</FieldLabel>
                        <Input
                          id="advanced-search-model"
                          :model-value="field.state.value"
                          list="model-datalist"
                          placeholder="PonyXL"
                          @update:model-value="field.handleChange"
                        />
                        <datalist id="model-datalist">
                          <option v-for="option in facetModelOptions" :key="option" :value="option" />
                        </datalist>
                        <FieldDescription v-if="facetStatus(facetModelOptions)" class="text-xs" aria-live="polite">
                          {{ facetStatus(facetModelOptions) }}
                        </FieldDescription>
                      </Field>
                    </form.Field>
                    <form.Field name="folder" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-folder">Folder</FieldLabel>
                        <Input
                          id="advanced-search-folder"
                          :model-value="field.state.value"
                          placeholder="portraits"
                          @update:model-value="field.handleChange"
                        />
                      </Field>
                    </form.Field>
                    <form.Field name="name" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-name">File name</FieldLabel>
                        <Input
                          id="advanced-search-name"
                          :model-value="field.state.value"
                          placeholder="image_001"
                          @update:model-value="field.handleChange"
                        />
                      </Field>
                    </form.Field>
                    <form.Field name="date" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-date">Date</FieldLabel>
                        <Input
                          id="advanced-search-date"
                          :model-value="field.state.value"
                          placeholder="2026-06-10"
                          @update:model-value="field.handleChange"
                        />
                        <FieldDescription class="text-xs">Matches indexed date text.</FieldDescription>
                      </Field>
                    </form.Field>
                  </div>
                </FieldGroup>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="generation">
              <AccordionTrigger class="text-left no-underline hover:no-underline">
                <span class="flex flex-col gap-0.5">
                  <span>Generation settings</span>
                  <span class="text-xs font-normal text-muted-foreground"
                    >Sampler, resources, and generation values</span
                  >
                </span>
              </AccordionTrigger>
              <AccordionContent class="pt-1">
                <FieldGroup class="gap-4">
                  <div class="grid grid-cols-2 gap-4">
                    <form.Field name="sampler" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-sampler">Sampler</FieldLabel>
                        <Input
                          id="advanced-search-sampler"
                          :model-value="field.state.value"
                          list="sampler-datalist"
                          placeholder="Euler a"
                          @update:model-value="field.handleChange"
                        />
                        <datalist id="sampler-datalist">
                          <option v-for="option in facetSamplerOptions" :key="option" :value="option" />
                        </datalist>
                        <FieldDescription v-if="facetStatus(facetSamplerOptions)" class="text-xs" aria-live="polite">
                          {{ facetStatus(facetSamplerOptions) }}
                        </FieldDescription>
                      </Field>
                    </form.Field>
                    <form.Field name="scheduler" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-scheduler">Scheduler</FieldLabel>
                        <Input
                          id="advanced-search-scheduler"
                          :model-value="field.state.value"
                          list="scheduler-datalist"
                          placeholder="Karras"
                          @update:model-value="field.handleChange"
                        />
                        <datalist id="scheduler-datalist">
                          <option v-for="option in facetSchedulerOptions" :key="option" :value="option" />
                        </datalist>
                        <FieldDescription v-if="facetStatus(facetSchedulerOptions)" class="text-xs" aria-live="polite">
                          {{ facetStatus(facetSchedulerOptions) }}
                        </FieldDescription>
                      </Field>
                    </form.Field>
                    <form.Field name="lora" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-lora">LoRA</FieldLabel
                        ><Input
                          id="advanced-search-lora"
                          :model-value="field.state.value"
                          placeholder="detail-slider"
                          @update:model-value="field.handleChange"
                        />
                      </Field>
                    </form.Field>
                    <form.Field name="vae" v-slot="{ field }">
                      <Field class="gap-1.5">
                        <FieldLabel for="advanced-search-vae">VAE</FieldLabel
                        ><Input
                          id="advanced-search-vae"
                          :model-value="field.state.value"
                          placeholder="vae-ft-mse"
                          @update:model-value="field.handleChange"
                        />
                      </Field>
                    </form.Field>
                    <form.Field name="seed" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-seed"
                        label="Seed"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="12345"
                        :error="validationErrors.seed"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="steps" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-steps"
                        label="Steps"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="30"
                        :error="validationErrors.steps"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="cfg" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-cfg"
                        label="CFG scale"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        placeholder="7.5"
                        :error="validationErrors.cfg"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="clip_skip" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-clip-skip"
                        label="Clip skip"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="2"
                        :error="validationErrors.clip_skip"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="denoising_strength" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-denoising-strength"
                        label="Denoising strength"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        placeholder="0.75"
                        :error="validationErrors.denoising_strength"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="hires_upscale" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-hires-upscale"
                        label="HiRes upscale"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        placeholder="2"
                        :error="validationErrors.hires_upscale"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="hires_steps" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-hires-steps"
                        label="HiRes steps"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="10"
                        :error="validationErrors.hires_steps"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                  </div>
                </FieldGroup>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="dimensions">
              <AccordionTrigger class="text-left no-underline hover:no-underline">
                <span class="flex flex-col gap-0.5"
                  ><span>Dimensions</span
                  ><span class="text-xs font-normal text-muted-foreground">Pixel size and proportions</span></span
                >
              </AccordionTrigger>
              <AccordionContent class="pt-1">
                <FieldDescription class="mb-4 text-xs">
                  Dimension filters combine with AND. Add more than one only when every condition should match.
                </FieldDescription>
                <FieldGroup class="gap-4">
                  <div class="grid grid-cols-2 gap-4">
                    <form.Field name="width" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-width"
                        label="Width"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="1024"
                        :error="validationErrors.width"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                    <form.Field name="height" v-slot="{ field }">
                      <AdvancedSearchNumericField
                        id="advanced-search-height"
                        label="Height"
                        :model-value="field.state.value"
                        :operators="NUMERIC_OPS"
                        inputmode="numeric"
                        placeholder="768"
                        :error="validationErrors.height"
                        @update:model-value="field.handleChange"
                      />
                    </form.Field>
                  </div>
                  <form.Field name="size" v-slot="{ field }">
                    <Field :data-invalid="Boolean(validationErrors.size)" class="gap-1.5">
                      <FieldLabel for="advanced-search-size">Size</FieldLabel>
                      <Input
                        id="advanced-search-size"
                        :model-value="field.state.value"
                        inputmode="numeric"
                        placeholder="1024x768"
                        :aria-invalid="Boolean(validationErrors.size)"
                        :aria-describedby="validationErrors.size ? 'advanced-search-size-error' : undefined"
                        @update:model-value="field.handleChange"
                      />
                      <FieldError v-if="validationErrors.size" id="advanced-search-size-error">
                        {{ validationErrors.size }}
                      </FieldError>
                    </Field>
                  </form.Field>
                  <form.Field name="ratio" v-slot="{ field }">
                    <Field :data-invalid="Boolean(validationErrors.ratio)" class="gap-2">
                      <FieldLabel for="advanced-search-ratio">Aspect ratio</FieldLabel>
                      <Input
                        id="advanced-search-ratio"
                        :model-value="field.state.value"
                        inputmode="decimal"
                        placeholder="16:9"
                        :aria-invalid="Boolean(validationErrors.ratio)"
                        :aria-describedby="validationErrors.ratio ? 'advanced-search-ratio-error' : undefined"
                        @update:model-value="field.handleChange"
                      />
                      <FieldError v-if="validationErrors.ratio" id="advanced-search-ratio-error">
                        {{ validationErrors.ratio }}
                      </FieldError>
                      <ToggleGroup
                        type="single"
                        variant="outline"
                        size="sm"
                        :model-value="field.state.value || undefined"
                        class="grid grid-cols-6"
                        aria-label="Aspect ratio presets"
                        @update:model-value="
                          (value) => field.handleChange(Array.isArray(value) ? (value[0] ?? '') : (value ?? ''))
                        "
                      >
                        <ToggleGroupItem
                          v-for="ratio in aspectRatios"
                          :key="ratio"
                          :value="ratio"
                          :aria-label="ratio"
                          class="min-h-9 min-w-0 border data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                        >
                          {{ ratio }}
                        </ToggleGroupItem>
                      </ToggleGroup>
                    </Field>
                  </form.Field>
                </FieldGroup>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="syntax">
              <AccordionTrigger class="text-left no-underline hover:no-underline">
                <span class="flex flex-col gap-0.5"
                  ><span>Query syntax</span
                  ><span class="text-xs font-normal text-muted-foreground"
                    >Metadata keys and raw metadata text</span
                  ></span
                >
              </AccordionTrigger>
              <AccordionContent class="pt-1">
                <FieldGroup class="gap-4">
                  <form.Field name="param" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-param">Metadata key</FieldLabel
                      ><Input
                        id="advanced-search-param"
                        :model-value="field.state.value"
                        class="font-mono"
                        placeholder="some_key:value"
                        @update:model-value="field.handleChange"
                      /><FieldDescription class="text-xs">
                        Serialized as <code>param:some_key:value</code>.
                      </FieldDescription>
                    </Field>
                  </form.Field>
                  <form.Field name="advanced" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-advanced">Workflow key</FieldLabel
                      ><Input
                        id="advanced-search-advanced"
                        :model-value="field.state.value"
                        class="font-mono"
                        placeholder="some_key:value"
                        @update:model-value="field.handleChange"
                      /><FieldDescription class="text-xs">
                        Serialized as <code>advanced:some_key:value</code>.
                      </FieldDescription>
                    </Field>
                  </form.Field>
                  <form.Field name="raw" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-raw">Raw metadata text</FieldLabel
                      ><Textarea
                        id="advanced-search-raw"
                        :model-value="field.state.value"
                        class="min-h-24 resize-y font-mono"
                        placeholder="model:PonyXL"
                        @update:model-value="(value) => field.handleChange(String(value))"
                      /><FieldDescription class="text-xs">Searches embedded raw metadata text.</FieldDescription>
                    </Field>
                  </form.Field>

                  <Field v-if="passThroughTokens.length" class="gap-2">
                    <FieldLabel>Additional preserved filters</FieldLabel>
                    <FieldDescription class="text-xs">
                      Repeated and unsupported filters stay unchanged unless removed.
                    </FieldDescription>
                    <ul class="flex flex-col gap-2">
                      <li
                        v-for="token in passThroughTokens"
                        :key="token.id"
                        class="flex items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2"
                      >
                        <code class="min-w-0 truncate text-xs">{{ filterToDisplayString(token.filter) }}</code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          :aria-label="`Remove ${filterToDisplayString(token.filter)}`"
                          @click="removeStagedToken(token.id)"
                        >
                          <X />
                        </Button>
                      </li>
                    </ul>
                  </Field>
                </FieldGroup>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>

        <footer
          class="flex shrink-0 items-center justify-between gap-4 border-t bg-background px-6 py-4"
          data-testid="advanced-search-footer"
        >
          <Button type="button" variant="outline" size="sm" @click="handleResetChanges">Reset changes</Button>
          <div class="flex items-center gap-3">
            <span class="text-xs text-muted-foreground"><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd></span>
            <Button type="button" variant="ghost" size="sm" @click="handleCancel">Cancel</Button>
            <Button type="submit" size="sm" :disabled="!formState.isValid">
              <Search data-icon="inline-start" />{{ applyLabel }}
            </Button>
          </div>
        </footer>
      </form>
    </SheetContent>
  </Sheet>
</template>
