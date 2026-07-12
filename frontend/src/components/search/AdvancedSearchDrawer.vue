<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from "vue";
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
import AdvancedSearchNumericField from "./AdvancedSearchNumericField.vue";
import AdvancedSearchPrefixedField from "./AdvancedSearchPrefixedField.vue";
import {
  NUMERIC_OPS,
  aspectRatios,
  buildDefaultValues,
  buildStagedState,
  collectStagedFilters,
  filterSignature,
  sectionForField,
  slotForFilter,
  validateValues,
  type FormFieldName,
  type FormValues,
  type StagedToken,
} from "./advancedSearchModel";

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
const facetsQuery = useFacetsQuery(
  computed(() => activeImportRootPath.value),
  computed(() => props.isOpen),
);

function stageFilters(filters: FieldFilter[]) {
  const { values, tokens, openSections } = buildStagedState(filters);
  stagedTokens.value = tokens;
  openingValues.value = structuredClone(values);
  activeAccordionSections.value = openSections;
  form.reset(values);
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
    emit("apply", collectStagedFilters(value, stagedTokens.value, openingValues.value));
    emit("close");
  },
});

const formState = useStore(form.store);
const validationErrors = computed(() => validateValues(formState.value.values));
const stagedFilters = computed(() =>
  collectStagedFilters(formState.value.values, stagedTokens.value, openingValues.value),
);
const isDirty = computed(() => filterSignature(stagedFilters.value) !== filterSignature(props.initialFilters));
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
const validationErrorEntries = computed(() => Object.entries(validationErrors.value) as Array<[FormFieldName, string]>);
const validationErrorCount = computed(() => validationErrorEntries.value.length);
const sectionErrorCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const [field] of validationErrorEntries.value) {
    const section = sectionForField(field);
    if (section) counts[section] = (counts[section] ?? 0) + 1;
  }
  return counts;
});
const sectionFilterCounts = computed(() => {
  const counts: Record<string, number> = {};
  const seen = new Set<FormFieldName>();
  for (const filter of stagedFilters.value) {
    const slot = slotForFilter(filter);
    const section = !slot || seen.has(slot) ? "syntax" : sectionForField(slot);
    if (slot) seen.add(slot);
    if (section) counts[section] = (counts[section] ?? 0) + 1;
  }
  return counts;
});

const fieldIds: Record<FormFieldName, string> = {
  prompt: "advanced-search-prompt",
  negative: "advanced-search-negative",
  model: "advanced-search-model",
  folder: "advanced-search-folder",
  name: "advanced-search-name",
  date: "advanced-search-date",
  sampler: "advanced-search-sampler",
  scheduler: "advanced-search-scheduler",
  lora: "advanced-search-lora",
  vae: "advanced-search-vae",
  seed: "advanced-search-seed",
  steps: "advanced-search-steps",
  cfg: "advanced-search-cfg",
  clip_skip: "advanced-search-clip-skip",
  denoising_strength: "advanced-search-denoising-strength",
  hires_upscale: "advanced-search-hires-upscale",
  hires_steps: "advanced-search-hires-steps",
  width: "advanced-search-width",
  height: "advanced-search-height",
  size: "advanced-search-size",
  ratio: "advanced-search-ratio",
  param: "advanced-search-param",
  advanced: "advanced-search-advanced",
  raw: "advanced-search-raw",
};

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

function handleInteractOutside(event: Event) {
  if (isDirty.value) event.preventDefault();
}

function removeStagedToken(id: string) {
  stagedTokens.value = stagedTokens.value.filter((token) => token.id !== id);
}

async function focusFirstInvalidField() {
  const firstInvalidField = validationErrorEntries.value[0]?.[0];
  if (!firstInvalidField) return;
  const section = sectionForField(firstInvalidField);
  if (section && !activeAccordionSections.value.includes(section)) {
    activeAccordionSections.value = [...activeAccordionSections.value, section];
  }
  await nextTick();
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  const target = document.getElementById(fieldIds[firstInvalidField]);
  target?.focus();
  target?.scrollIntoView({ block: "nearest" });
}

async function submitForm() {
  if (validationErrorCount.value > 0) {
    await focusFirstInvalidField();
    return;
  }
  if (isDirty.value) await form.handleSubmit();
}

function handleShortcut(event: KeyboardEvent) {
  if (event.key !== "Enter" || (!event.ctrlKey && !event.metaKey)) return;
  event.preventDefault();
  void submitForm();
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
      class="advanced-search-drawer w-full max-w-none gap-0 p-0 sm:w-[560px] sm:max-w-[560px]"
      data-testid="advanced-search-drawer"
      @interact-outside="handleInteractOutside"
    >
      <form class="flex h-full min-h-0 flex-col" @submit.prevent="submitForm" @keydown="handleShortcut">
        <SheetHeader class="shrink-0 gap-1 border-b px-4 py-4 pr-14 text-left sm:px-6 sm:py-5">
          <SheetTitle class="text-lg">Advanced Search</SheetTitle>
          <SheetDescription>Build precise metadata and file filters.</SheetDescription>
        </SheetHeader>

        <div
          class="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-4 sm:px-6 sm:py-5"
          data-testid="advanced-search-scroll-body"
        >
          <div class="mb-4 rounded-md border bg-muted/40 px-3 py-2.5">
            <div class="flex items-center justify-between gap-3">
              <p class="text-sm font-medium" aria-live="polite">{{ activeFilterSummary }}</p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                class="min-h-9 shrink-0"
                :disabled="activeFilterCount === 0"
                @click="handleClearAll"
              >
                <Trash2 data-icon="inline-start" />
                Clear all
              </Button>
            </div>
            <ul
              v-if="stagedFilters.length"
              class="mt-2 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto"
              aria-label="Selected filters"
            >
              <li
                v-for="(filter, index) in stagedFilters"
                :key="`${filter.field}-${filter.operator ?? ''}-${filter.value}-${index}`"
                class="max-w-full rounded-md border bg-background px-2 py-1"
              >
                <code class="block max-w-full truncate text-xs">{{ filterToDisplayString(filter) }}</code>
              </li>
            </ul>
          </div>

          <Accordion
            type="multiple"
            :model-value="activeAccordionSections"
            @update:model-value="activeAccordionSections = $event as string[]"
            class="min-w-0 max-w-full"
            data-testid="advanced-search-groups"
          >
            <AccordionItem value="content">
              <AccordionTrigger class="text-left no-underline hover:no-underline">
                <span class="flex min-w-0 flex-1 items-center justify-between gap-3 pr-2">
                  <span class="flex flex-col gap-0.5">
                    <span>Content and files</span>
                    <span class="text-xs font-normal text-muted-foreground">Words, models, locations, and dates</span>
                  </span>
                  <span
                    v-if="sectionFilterCounts.content"
                    class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium"
                  >
                    {{ sectionFilterCounts.content }}
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent class="px-1 pt-1">
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
                  <div class="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 [&>*]:min-w-0">
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
                <span class="flex min-w-0 flex-1 items-center justify-between gap-3 pr-2">
                  <span class="flex flex-col gap-0.5">
                    <span>Generation settings</span>
                    <span class="text-xs font-normal text-muted-foreground"
                      >Sampler, resources, and generation values</span
                    >
                  </span>
                  <span class="flex items-center gap-1.5">
                    <span
                      v-if="sectionErrorCounts.generation"
                      class="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
                    >
                      {{ sectionErrorCounts.generation }} error{{ sectionErrorCounts.generation === 1 ? "" : "s" }}
                    </span>
                    <span
                      v-if="sectionFilterCounts.generation"
                      class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium"
                    >
                      {{ sectionFilterCounts.generation }}
                    </span>
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent class="px-1 pt-1">
                <FieldGroup class="gap-4">
                  <div class="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 [&>*]:min-w-0">
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
                <span class="flex min-w-0 flex-1 items-center justify-between gap-3 pr-2">
                  <span class="flex flex-col gap-0.5">
                    <span>Dimensions</span>
                    <span class="text-xs font-normal text-muted-foreground">Pixel size and proportions</span>
                  </span>
                  <span class="flex items-center gap-1.5">
                    <span
                      v-if="sectionErrorCounts.dimensions"
                      class="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
                    >
                      {{ sectionErrorCounts.dimensions }} error{{ sectionErrorCounts.dimensions === 1 ? "" : "s" }}
                    </span>
                    <span
                      v-if="sectionFilterCounts.dimensions"
                      class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium"
                    >
                      {{ sectionFilterCounts.dimensions }}
                    </span>
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent class="px-1 pt-1">
                <FieldDescription class="mb-4 text-xs">
                  Dimension filters combine with AND. Add more than one only when every condition should match.
                </FieldDescription>
                <FieldGroup class="gap-4">
                  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                        class="grid grid-cols-3 sm:grid-cols-6"
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
                          class="min-h-9 min-w-0 border focus-visible:relative focus-visible:z-10 data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
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
                <span class="flex min-w-0 flex-1 items-center justify-between gap-3 pr-2">
                  <span class="flex flex-col gap-0.5">
                    <span>Custom metadata</span>
                    <span class="text-xs font-normal text-muted-foreground"
                      >Uncommon keys and embedded metadata text</span
                    >
                  </span>
                  <span v-if="sectionFilterCounts.syntax" class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
                    {{ sectionFilterCounts.syntax }}
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent class="px-1 pt-1">
                <FieldGroup class="gap-4">
                  <FieldDescription class="rounded-md bg-muted/50 px-3 py-2.5 text-sm">
                    Use these options only when the standard fields above do not cover the metadata you need.
                  </FieldDescription>
                  <form.Field name="param" v-slot="{ field }">
                    <AdvancedSearchPrefixedField
                      id="advanced-search-param"
                      label="Custom metadata field"
                      prefix="param:"
                      :model-value="field.state.value"
                      placeholder="camera_model:ILCE-7M4"
                      example-input="camera_model:ILCE-7M4"
                      @update:model-value="field.handleChange"
                    />
                  </form.Field>
                  <form.Field name="advanced" v-slot="{ field }">
                    <AdvancedSearchPrefixedField
                      id="advanced-search-advanced"
                      label="Workflow metadata field"
                      prefix="advanced:"
                      :model-value="field.state.value"
                      placeholder="sampler_name:euler"
                      example-input="sampler_name:euler"
                      @update:model-value="field.handleChange"
                    />
                  </form.Field>
                  <form.Field name="raw" v-slot="{ field }">
                    <Field class="gap-1.5">
                      <FieldLabel for="advanced-search-raw">Raw metadata contains</FieldLabel
                      ><Textarea
                        id="advanced-search-raw"
                        :model-value="field.state.value"
                        class="min-h-24 resize-y font-mono"
                        placeholder="model:PonyXL"
                        @update:model-value="(value) => field.handleChange(String(value))"
                      /><FieldDescription class="text-xs">
                        Matches this text anywhere in embedded metadata. Use it when you know the text but not its key.
                      </FieldDescription>
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
          class="flex shrink-0 flex-col gap-3 border-t bg-background px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-4"
          data-testid="advanced-search-footer"
        >
          <div class="flex min-w-0 items-center justify-between gap-3 sm:justify-start">
            <Button type="button" variant="outline" size="sm" :disabled="!isDirty" @click="handleResetChanges">
              Revert edits
            </Button>
            <span v-if="validationErrorCount" class="text-xs font-medium text-destructive" role="alert">
              {{ validationErrorCount }} field{{ validationErrorCount === 1 ? "" : "s" }} need attention
            </span>
            <span v-else-if="isDirty" class="text-xs text-muted-foreground">Unsaved changes</span>
          </div>
          <div class="flex items-center justify-end gap-2 sm:gap-3">
            <span class="hidden text-xs text-muted-foreground md:inline"
              ><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd></span
            >
            <Button type="button" variant="ghost" size="sm" @click="handleCancel">Cancel</Button>
            <Button type="submit" size="sm" :disabled="!isDirty">
              <Search data-icon="inline-start" />{{ applyLabel }}
            </Button>
          </div>
        </footer>
      </form>
    </SheetContent>
  </Sheet>
</template>
