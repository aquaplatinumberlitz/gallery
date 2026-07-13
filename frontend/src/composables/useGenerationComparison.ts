import { computed, toValue, type MaybeRefOrGetter } from "vue";
import type { MetadataResponse } from "@/types";

export interface GenerationComparisonItem {
  key: string;
  label: string;
  reference: string;
  candidate: string;
  changed: boolean;
}

const asText = (value: unknown): string => {
  if (Array.isArray(value)) return value.map(String).filter(Boolean).join(", ");
  if (value === null || value === undefined) return "";
  return String(value).trim();
};

const firstParam = (metadata: MetadataResponse | null, names: string[]): string => {
  for (const name of names) {
    const value = asText(metadata?.params?.[name]);
    if (value) return value;
  }
  return "";
};

const modelText = (metadata: MetadataResponse | null): string =>
  firstParam(metadata, ["Model", "model"]) ||
  (metadata?.models ?? [])
    .map((model) => model.name || model.param || model.hash || "")
    .filter(Boolean)
    .join(", ");

const dimensionsText = (metadata: MetadataResponse | null): string => {
  const width = firstParam(metadata, ["Width", "width"]) || asText(metadata?.width);
  const height = firstParam(metadata, ["Height", "height"]) || asText(metadata?.height);
  return width && height ? `${width} × ${height}` : "";
};

const fields = [
  { key: "seed", label: "Seed", read: (meta: MetadataResponse | null) => firstParam(meta, ["Seed", "seed"]) },
  {
    key: "sampler",
    label: "Sampler",
    read: (meta: MetadataResponse | null) => firstParam(meta, ["Sampler", "sampler"]),
  },
  {
    key: "scheduler",
    label: "Scheduler",
    read: (meta: MetadataResponse | null) => firstParam(meta, ["Scheduler", "scheduler"]),
  },
  { key: "steps", label: "Steps", read: (meta: MetadataResponse | null) => firstParam(meta, ["Steps", "steps"]) },
  {
    key: "cfg",
    label: "CFG",
    read: (meta: MetadataResponse | null) => firstParam(meta, ["CFG", "CFG scale", "cfg_scale", "cfg"]),
  },
  { key: "dimensions", label: "Dimensions", read: dimensionsText },
  { key: "model", label: "Model", read: modelText },
  {
    key: "resources",
    label: "LoRA / resources",
    read: (meta: MetadataResponse | null) => firstParam(meta, ["Lora", "LoRA", "loras", "Resources"]),
  },
  {
    key: "denoising",
    label: "Denoising",
    read: (meta: MetadataResponse | null) =>
      firstParam(meta, ["Denoising strength", "Denoising", "denoising_strength", "denoise"]),
  },
  {
    key: "hires",
    label: "Hires",
    read: (meta: MetadataResponse | null) => {
      const upscale = firstParam(meta, ["Hires upscale", "hires_upscale"]);
      const steps = firstParam(meta, ["Hires steps", "hires_steps"]);
      return [upscale && `${upscale}×`, steps && `${steps} steps`].filter(Boolean).join(" · ");
    },
  },
  { key: "vae", label: "VAE", read: (meta: MetadataResponse | null) => firstParam(meta, ["VAE", "vae"]) },
] as const;

export function useGenerationComparison(
  reference: MaybeRefOrGetter<MetadataResponse | null>,
  candidate: MaybeRefOrGetter<MetadataResponse | null>,
) {
  const comparisons = computed<GenerationComparisonItem[]>(() => {
    const referenceValue = toValue(reference);
    const candidateValue = toValue(candidate);
    return fields
      .map((field) => {
        const referenceText = field.read(referenceValue);
        const candidateText = field.read(candidateValue);
        return {
          key: field.key,
          label: field.label,
          reference: referenceText,
          candidate: candidateText,
          changed: Boolean(referenceText && candidateText && referenceText !== candidateText),
        };
      })
      .filter((item) => item.reference || item.candidate);
  });

  const changed = computed(() => comparisons.value.filter((item) => item.changed));
  return { comparisons, changed };
}
