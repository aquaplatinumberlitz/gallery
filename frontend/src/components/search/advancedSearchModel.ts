import type { FieldFilter } from "@/types";

export interface NumericFilterValue {
  value: string;
  op: string;
}

export type NumericFieldName =
  | "seed"
  | "steps"
  | "cfg"
  | "width"
  | "height"
  | "clip_skip"
  | "denoising_strength"
  | "hires_upscale"
  | "hires_steps";

export interface FormValues {
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

export type FormFieldName = keyof FormValues;

export interface StagedToken {
  id: string;
  filter: FieldFilter;
  slot: FormFieldName | null;
  primary: boolean;
}

export const NUMERIC_OPS = [
  { label: "=", value: "=" },
  { label: ">", value: ">" },
  { label: ">=", value: ">=" },
  { label: "<", value: "<" },
  { label: "<=", value: "<=" },
] as const;

export const aspectRatios = ["1:1", "4:3", "16:9", "3:2", "2:3", "9:16"] as const;

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

function defaultNumericValue(): NumericFilterValue {
  return { value: "", op: "=" };
}

export function buildDefaultValues(): FormValues {
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

export function slotForFilter(filter: FieldFilter): FormFieldName | null {
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

export function sectionForField(field: FormFieldName): string | null {
  for (const [section, fields] of Object.entries(sectionFields)) {
    if (fields.includes(field)) return section;
  }
  return null;
}

export function computeOpenSections(filters: FieldFilter[]): string[] {
  const sections = new Set<string>(["content"]);
  const seen = new Set<FormFieldName>();
  for (const filter of filters) {
    const slot = slotForFilter(filter);
    if (!slot || seen.has(slot)) {
      sections.add("syntax");
    } else {
      seen.add(slot);
      const section = sectionForField(slot);
      if (section) sections.add(section);
    }
  }
  return [...sections];
}

export function buildStagedState(filters: FieldFilter[]) {
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
  return { values, tokens, openSections: computeOpenSections(filters) };
}

function fieldValue(values: FormValues, slot: FormFieldName): string | NumericFilterValue {
  return values[slot];
}

function fieldChanged(values: FormValues, openingValues: FormValues, slot: FormFieldName): boolean {
  const current = fieldValue(values, slot);
  const opening = fieldValue(openingValues, slot);
  if (typeof current === "string" && typeof opening === "string") return current !== opening;
  if (typeof current !== "string" && typeof opening !== "string") {
    return current.value !== opening.value || current.op !== opening.op;
  }
  return true;
}

function filterForSlot(slot: FormFieldName, values: FormValues): FieldFilter | null {
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

export function collectStagedFilters(
  values: FormValues,
  stagedTokens: StagedToken[],
  openingValues: FormValues,
): FieldFilter[] {
  const result: FieldFilter[] = [];
  const primarySlots = new Set<FormFieldName>();

  for (const token of stagedTokens) {
    if (!token.primary || token.slot === null) {
      if (token.filter.value.trim()) result.push({ ...token.filter });
      continue;
    }
    primarySlots.add(token.slot);
    if (!fieldChanged(values, openingValues, token.slot)) {
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

export function validateValues(value: FormValues): Partial<Record<FormFieldName, string>> {
  const errors: Partial<Record<FormFieldName, string>> = {};
  const isInteger = (input: string) => /^-?\d+$/.test(input.trim());
  const isPositiveInteger = (input: string) => /^\d+$/.test(input.trim()) && Number(input) > 0;
  const isPositiveNumber = (input: string) => Number.isFinite(Number(input)) && Number(input) > 0;

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

export const filterSignature = (filters: FieldFilter[]) =>
  JSON.stringify(filters.map((filter) => [filter.field, filter.operator ?? "", filter.value]));
