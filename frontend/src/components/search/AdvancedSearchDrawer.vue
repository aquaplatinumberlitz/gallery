<script setup lang="ts">
import { computed, watch } from 'vue'
import { useForm, useStore } from '@tanstack/vue-form'
import { X, Search, RotateCcw } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { useFacetsQuery } from '@/composables/useFacetsQuery'
import { useGalleryStore } from '@/stores/gallery'
import type { FieldFilter, FacetEntry } from '@/types'

interface Props {
  isOpen: boolean
  initialFilters: FieldFilter[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  apply: [filters: FieldFilter[]]
}>()

const galleryStore = useGalleryStore()
const facetsQueryPath = computed(() => galleryStore.rootPath || '')
const facetsQuery = useFacetsQuery(facetsQueryPath)

const NUMERIC_OPS = [
  { label: '=', value: '=' },
  { label: '>', value: '>' },
  { label: '>=', value: '>=' },
  { label: '<', value: '<' },
  { label: '<=', value: '<=' },
] as const

const aspectRatios = [
  { label: '1:1', value: '1:1' },
  { label: '4:3', value: '4:3' },
  { label: '16:9', value: '16:9' },
  { label: '3:2', value: '3:2' },
  { label: '2:3', value: '2:3' },
  { label: '9:16', value: '9:16' },
]

interface NumField { value: string; op: string }

function defaultNumField(): NumField {
  return { value: '', op: '=' }
}

interface FormValues {
  prompt: string
  negative: string
  model: string
  sampler: string
  scheduler: string
  lora: string
  vae: string
  folder: string
  name: string
  seed: NumField
  steps: NumField
  cfg: NumField
  width: NumField
  height: NumField
  clip_skip: NumField
  denoising_strength: NumField
  hires_upscale: NumField
  hires_steps: NumField
  ratio: string
  size: string
  date: string
  param: string
  advanced: string
  raw: string
}

function buildDefaultValues(): FormValues {
  return {
    prompt: '',
    negative: '',
    model: '',
    sampler: '',
    scheduler: '',
    lora: '',
    vae: '',
    folder: '',
    name: '',
    seed: defaultNumField(),
    steps: defaultNumField(),
    cfg: defaultNumField(),
    width: defaultNumField(),
    height: defaultNumField(),
    clip_skip: defaultNumField(),
    denoising_strength: defaultNumField(),
    hires_upscale: defaultNumField(),
    hires_steps: defaultNumField(),
    ratio: '',
    size: '',
    date: '',
    param: '',
    advanced: '',
    raw: '',
  }
}

function filtersToValues(filters: FieldFilter[]): FormValues {
  const values = buildDefaultValues()
  for (const f of filters) {
    switch (f.field) {
      case 'prompt':
      case 'positive':
        values.prompt = f.value; break
      case 'negative':
        values.negative = f.value; break
      case 'model':
        values.model = f.value; break
      case 'sampler':
        values.sampler = f.value; break
      case 'scheduler':
        values.scheduler = f.value; break
      case 'lora':
        values.lora = f.value; break
      case 'vae':
        values.vae = f.value; break
      case 'folder':
      case 'path':
        values.folder = f.value; break
      case 'name':
        values.name = f.value; break
      case 'seed':
        values.seed = { value: f.value, op: f.operator || '=' }; break
      case 'steps':
        values.steps = { value: f.value, op: f.operator || '=' }; break
      case 'cfg':
        values.cfg = { value: f.value, op: f.operator || '=' }; break
      case 'width':
        values.width = { value: f.value, op: f.operator || '=' }; break
      case 'height':
        values.height = { value: f.value, op: f.operator || '=' }; break
      case 'clip_skip':
        values.clip_skip = { value: f.value, op: f.operator || '=' }; break
      case 'denoising_strength':
      case 'denoising':
        values.denoising_strength = { value: f.value, op: f.operator || '=' }; break
      case 'hires_upscale':
        values.hires_upscale = { value: f.value, op: f.operator || '=' }; break
      case 'hires_steps':
        values.hires_steps = { value: f.value, op: f.operator || '=' }; break
      case 'ratio':
        values.ratio = f.value; break
      case 'size':
        values.size = f.value; break
      case 'date':
        values.date = f.value; break
      case 'param':
        values.param = f.value; break
      case 'advanced':
        values.advanced = f.value; break
      case 'raw':
        values.raw = f.value; break
      default:
        values.raw = values.raw ? `${values.raw} ${f.field}:${f.operator || ''}${f.value}` : `${f.field}:${f.operator || ''}${f.value}`
    }
  }
  return values
}

const form = useForm({
  defaultValues: buildDefaultValues(),
  validators: {
    onChange: ({ value }) => {
      const fields: Record<string, string | undefined> = {}

      const numericFields = ['seed', 'steps', 'cfg', 'width', 'height', 'clip_skip', 'denoising_strength', 'hires_upscale', 'hires_steps']
      for (const field of numericFields) {
        const v = (value as any)[field]?.value
        if (v && isNaN(Number(v))) {
          fields[field] = 'Must be a number'
        }
      }

      if (value.width?.value && Number(value.width.value) <= 0) {
        fields.width = 'Must be positive'
      }
      if (value.height?.value && Number(value.height.value) <= 0) {
        fields.height = 'Must be positive'
      }

      if (value.size && !/^\d+\s*x\s*\d+$/i.test(value.size)) {
        fields.size = 'Use format like 1024x768'
      }

      return { fields }
    },
  },
  onSubmit: ({ value }) => {
    const filters: FieldFilter[] = collectFilters(value)
    emit('apply', filters)
    emit('close')
  },
})

function collectFilters(values: FormValues): FieldFilter[] {
  const f: FieldFilter[] = []
  const add = (field: string, value: string, operator?: string) => {
    if (value) f.push({ field, operator, value })
  }
  add('prompt', values.prompt)
  add('negative', values.negative)
  add('model', values.model)
  add('sampler', values.sampler)
  add('scheduler', values.scheduler)
  add('lora', values.lora)
  add('vae', values.vae)
  add('folder', values.folder)
  add('name', values.name)
  if (values.seed.value) add('seed', values.seed.value, values.seed.op !== '=' ? values.seed.op : undefined)
  if (values.steps.value) add('steps', values.steps.value, values.steps.op !== '=' ? values.steps.op : undefined)
  if (values.cfg.value) add('cfg', values.cfg.value, values.cfg.op !== '=' ? values.cfg.op : undefined)
  if (values.width.value) add('width', values.width.value, values.width.op !== '=' ? values.width.op : undefined)
  if (values.height.value) add('height', values.height.value, values.height.op !== '=' ? values.height.op : undefined)
  if (values.clip_skip.value) add('clip_skip', values.clip_skip.value, values.clip_skip.op !== '=' ? values.clip_skip.op : undefined)
  if (values.denoising_strength.value) add('denoising_strength', values.denoising_strength.value, values.denoising_strength.op !== '=' ? values.denoising_strength.op : undefined)
  if (values.hires_upscale.value) add('hires_upscale', values.hires_upscale.value, values.hires_upscale.op !== '=' ? values.hires_upscale.op : undefined)
  if (values.hires_steps.value) add('hires_steps', values.hires_steps.value, values.hires_steps.op !== '=' ? values.hires_steps.op : undefined)
  add('ratio', values.ratio)
  add('size', values.size)
  add('date', values.date)
  add('param', values.param)
  add('advanced', values.advanced)
  add('raw', values.raw)
  return f
}

watch(() => props.isOpen, (open) => {
  if (open) {
    form.reset(filtersToValues(props.initialFilters))
  }
})

watch(() => props.initialFilters, (filters) => {
  if (filters) {
    form.reset(filtersToValues(filters))
  }
})

function handleReset() {
  emit('apply', [])
  emit('close')
}

function handleCancel() {
  form.reset(filtersToValues(props.initialFilters))
  emit('close')
}

const formState = useStore(form.store)
const isDirty = computed(() => formState.value.isDirty)

const facetData = computed(() => facetsQuery.data.value)
const facetModelOptions = computed(() => facetData.value?.model?.map((e: FacetEntry) => e.value) || [])
const facetSamplerOptions = computed(() => facetData.value?.sampler?.map((e: FacetEntry) => e.value) || [])
const facetSchedulerOptions = computed(() => facetData.value?.scheduler?.map((e: FacetEntry) => e.value) || [])

function applyAspectRatio(ratio: string) {
  form.setFieldValue('ratio', ratio)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="advanced-search-overlay" tabindex="-1" @click.self="handleCancel" @keydown.escape="handleCancel">
      <div class="advanced-search-drawer" role="dialog" aria-label="Advanced Search">
        <div class="advanced-search-header">
          <h2 class="text-base font-semibold">Advanced Search</h2>
          <Button variant="ghost" size="icon" type="button" aria-label="Close advanced search" @click="handleCancel">
            <X class="size-4" />
          </Button>
        </div>

        <div class="advanced-search-body">
          <form @submit.prevent="form.handleSubmit()">
            <!-- Text Fields -->
            <fieldset class="field-group">
              <legend class="field-group-label">Text Fields</legend>
              <div class="field-grid">
                <form.Field name="prompt" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-prompt">Prompt</label>
                  <Input id="advanced-search-prompt" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. blue archive" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="negative" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-negative">Negative Prompt</label>
                  <Input id="advanced-search-negative" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. blurry, watermark" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="model" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-model">Model</label>
                  <Input id="advanced-search-model" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. PonyXL" type="text" variant="default" class="field-input" :list="'model-datalist'" />
                  <datalist id="model-datalist">
                    <option v-for="opt in facetModelOptions" :key="opt" :value="opt" />
                  </datalist>
                </form.Field>
                <form.Field name="sampler" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-sampler">Sampler</label>
                  <Input id="advanced-search-sampler" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. Euler a" type="text" variant="default" class="field-input" :list="'sampler-datalist'" />
                  <datalist id="sampler-datalist">
                    <option v-for="opt in facetSamplerOptions" :key="opt" :value="opt" />
                  </datalist>
                </form.Field>
                <form.Field name="scheduler" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-scheduler">Scheduler</label>
                  <Input id="advanced-search-scheduler" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. Karras" type="text" variant="default" class="field-input" :list="'scheduler-datalist'" />
                  <datalist id="scheduler-datalist">
                    <option v-for="opt in facetSchedulerOptions" :key="opt" :value="opt" />
                  </datalist>
                </form.Field>
                <form.Field name="lora" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-lora">LoRA</label>
                  <Input id="advanced-search-lora" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="LoRA name" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="vae" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-vae">VAE</label>
                  <Input id="advanced-search-vae" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="VAE name" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="folder" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-folder">Folder</label>
                  <Input id="advanced-search-folder" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="Folder name" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="name" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-name">Name</label>
                  <Input id="advanced-search-name" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="File name" type="text" variant="default" class="field-input" />
                </form.Field>
              </div>
            </fieldset>

            <!-- Numeric Fields -->
            <fieldset class="field-group">
              <legend class="field-group-label">Numeric Fields</legend>
              <div class="field-grid">
                <form.Field name="seed" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-seed">Seed</label>
                  <div class="numeric-row">
                    <select id="advanced-search-seed-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Seed operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-seed" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="12345" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="steps" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-steps">Steps</label>
                  <div class="numeric-row">
                    <select id="advanced-search-steps-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Steps operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-steps" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="30" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="cfg" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-cfg">CFG Scale</label>
                  <div class="numeric-row">
                    <select id="advanced-search-cfg-op" class="numeric-op-select" :value="f.state.value.op" aria-label="CFG Scale operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-cfg" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="7.5" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="clip_skip" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-clip-skip">Clip Skip</label>
                  <div class="numeric-row">
                    <select id="advanced-search-clip-skip-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Clip Skip operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-clip-skip" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="2" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="denoising_strength" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-denoising-strength">Denoising Strength</label>
                  <div class="numeric-row">
                    <select id="advanced-search-denoising-strength-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Denoising Strength operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-denoising-strength" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="0.75" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="hires_upscale" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-hires-upscale">HiRes Upscale</label>
                  <div class="numeric-row">
                    <select id="advanced-search-hires-upscale-op" class="numeric-op-select" :value="f.state.value.op" aria-label="HiRes Upscale operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-hires-upscale" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="2" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="hires_steps" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-hires-steps">HiRes Steps</label>
                  <div class="numeric-row">
                    <select id="advanced-search-hires-steps-op" class="numeric-op-select" :value="f.state.value.op" aria-label="HiRes Steps operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-hires-steps" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="10" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
              </div>
            </fieldset>

            <!-- Dimensions -->
            <fieldset class="field-group">
              <legend class="field-group-label">Dimensions</legend>
              <div class="field-grid">
                <form.Field name="width" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-width">Width</label>
                  <div class="numeric-row">
                    <select id="advanced-search-width-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Width operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-width" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="1024" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="height" v-slot="{ field: f }">
                  <label class="field-label" for="advanced-search-height">Height</label>
                  <div class="numeric-row">
                    <select id="advanced-search-height-op" class="numeric-op-select" :value="f.state.value.op" aria-label="Height operator" @change="f.handleChange({ value: f.state.value.value, op: ($event.target as HTMLSelectElement).value })">
                      <option v-for="op in NUMERIC_OPS" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <Input id="advanced-search-height" :modelValue="f.state.value.value" @update:modelValue="(v: string) => f.handleChange({ value: v, op: f.state.value.op })" placeholder="768" type="text" variant="default" class="field-input numeric-input" />
                  </div>
                  <p v-if="f.state.meta.errors?.length" class="field-error">
                    {{ f.state.meta.errors[0] }}
                  </p>
                </form.Field>
                <form.Field name="size" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-size">Size</label>
                  <Input id="advanced-search-size" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. 1024x768" type="text" variant="default" class="field-input" />
                  <p v-if="field.state.meta.errors?.length" class="field-error">
                    {{ field.state.meta.errors[0] }}
                  </p>
                </form.Field>
              </div>
            </fieldset>

            <!-- Aspect Ratio -->
            <fieldset class="field-group">
              <legend class="field-group-label">Aspect Ratio</legend>
              <form.Field name="ratio" v-slot="{ field }">
                <label class="field-label" for="advanced-search-ratio">Ratio</label>
                <Input id="advanced-search-ratio" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. 16:9" type="text" variant="default" class="field-input" />
                <div class="aspect-ratio-row">
                  <button
                    v-for="ratio in aspectRatios"
                    :key="ratio.value"
                    type="button"
                    class="aspect-ratio-btn"
                    :aria-pressed="field.state.value === ratio.value"
                    @click="applyAspectRatio(ratio.value)"
                  >
                    {{ ratio.label }}
                  </button>
                </div>
              </form.Field>
            </fieldset>

            <!-- Date -->
            <fieldset class="field-group">
              <legend class="field-group-label">Date</legend>
              <div class="field-grid">
                <form.Field name="date" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-date">Date</label>
                  <Input id="advanced-search-date" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. 2024-01-15" type="text" variant="default" class="field-input" />
                </form.Field>
              </div>
            </fieldset>

            <!-- Generic / Power-user Fields -->
            <fieldset class="field-group">
              <legend class="field-group-label">Generic / Power-user</legend>
              <div class="field-grid">
                <form.Field name="param" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-param">Param</label>
                  <Input id="advanced-search-param" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="Custom parameter value" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="advanced" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-advanced">Advanced</label>
                  <Input id="advanced-search-advanced" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="Advanced field value" type="text" variant="default" class="field-input" />
                </form.Field>
                <form.Field name="raw" v-slot="{ field }">
                  <label class="field-label" for="advanced-search-raw">Raw Query</label>
                  <Input id="advanced-search-raw" :modelValue="field.state.value" @update:modelValue="(v: string) => field.handleChange(v)" placeholder="e.g. model:PonyXL sampler:Euler a" type="text" variant="default" class="field-input" />
                </form.Field>
              </div>
            </fieldset>

            <!-- Actions -->
            <div class="advanced-search-actions">
              <Button type="button" variant="outline" size="sm" @click="handleReset">
                <RotateCcw class="size-3.5 mr-1" />
                Reset
              </Button>
              <div class="flex gap-2">
                <Button type="button" variant="ghost" size="sm" @click="handleCancel">
                  Cancel
                </Button>
                <Button type="submit" variant="default" size="sm" :disabled="!(isDirty && formState.isValid)">
                  <Search class="size-3.5 mr-1" />
                  Apply
                </Button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.advanced-search-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: flex-end;
}

.advanced-search-drawer {
  width: 420px;
  max-width: 90vw;
  height: 100%;
  background: var(--background, hsl(0 0% 100%));
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  animation: slideInRight 200ms ease-out;
}

@keyframes slideInRight {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

.advanced-search-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, hsl(0 0% 89.8%));
  flex-shrink: 0;
}

.advanced-search-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.advanced-search-body form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.advanced-search-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border, hsl(0 0% 89.8%));
  flex-shrink: 0;
  margin: 0 -20px;
  padding-top: 16px;
}

.field-group {
  border: none;
  padding: 0;
  margin: 0;
}

.field-group-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted-foreground, hsl(0 0% 45.1%));
  margin-bottom: 8px;
  display: block;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--foreground, hsl(0 0% 3.9%));
  margin-bottom: 2px;
}

.field-input {
  width: 100%;
}

.field-select {
  width: 100%;
  height: 36px;
  border-radius: 6px;
  border: 1px solid var(--border, hsl(0 0% 89.8%));
  background: transparent;
  padding: 0 8px;
  font-size: 14px;
  color: var(--foreground, hsl(0 0% 3.9%));
  outline: none;
}

.field-select:focus {
  border-color: var(--ring, hsl(0 0% 3.9%));
  box-shadow: 0 0 0 1px var(--ring, hsl(0 0% 3.9%));
}

.numeric-row {
  display: flex;
  gap: 4px;
}

.numeric-op-select {
  width: 52px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 6px;
  border: 1px solid var(--border, hsl(0 0% 89.8%));
  background: transparent;
  padding: 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, hsl(0 0% 3.9%));
  outline: none;
  cursor: pointer;
}

.numeric-op-select:focus {
  border-color: var(--ring, hsl(0 0% 3.9%));
}

.numeric-input {
  flex: 1;
  min-width: 0;
}

.aspect-ratio-row {
  display: flex;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
  gap: 4px;
}

.aspect-ratio-btn {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border, hsl(0 0% 89.8%));
  background: transparent;
  color: var(--foreground, hsl(0 0% 3.9%));
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.aspect-ratio-btn:hover {
  background: var(--accent, hsl(0 0% 96.1%));
  border-color: var(--ring, hsl(0 0% 3.9%));
}

.field-error {
  font-size: 11px;
  color: var(--destructive, hsl(0 84.2% 60.2%));
  margin-top: 2px;
}
</style>
