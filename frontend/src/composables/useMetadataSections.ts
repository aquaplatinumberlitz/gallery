/**
 * useMetadataSections — shared section config & helpers for metadata panels.
 *
 * Categories:
 *   Core      – always visible; shows muted empty-state text when data is absent
 *   Secondary – rendered only when at least one matching param exists
 *   Advanced  – collapsed by default; shown only when extra data exists
 */

import type { MetadataResponse } from '../types';

/* ─── Param field sets ───────────────────────────────────────────── */

/** Core params shown in the "Generation Data" section */
export const CORE_PARAMS = new Set([
  'Seed', 'Steps', 'CFG', 'Sampler', 'Scheduler', 'AspectRatio',
]);

/** Secondary params placed in an "Extra Settings" block (hidden when empty) */
export const SECONDARY_PARAMS_MAP: Record<string, string> = {
  clip_skip: 'Clip Skip',
  hires_upscale: 'Hires Upscale',
  hires_steps: 'Hires Steps',
  denoising_strength: 'Denoising',
  vae: 'VAE',
  model_hash: 'Model Hash',
  ensd: 'ENSD',
  aesthetic_score: 'Aesthetic',
};

export const SECONDARY_PARAM_KEYS = Object.keys(SECONDARY_PARAMS_MAP);

/* ─── Empty-state text per core section ─────────────────────────── */

export const EMPTY_SECTION_TEXT: Record<string, string> = {
  prompt: 'No prompt metadata',
  negative_prompt: 'No negative prompt',
  generation_data: 'No generation parameters',
  model_resources: 'No model/resource metadata found',
};

/* ─── Helpers ────────────────────────────────────────────────────── */

/** At least one core param has a truthy value */
export function hasCoreParams(
  params: Record<string, unknown> | null | undefined,
): boolean {
  if (!params) return false;
  return [...CORE_PARAMS].some((k) => {
    const v = params[k];
    return v !== undefined && v !== null && v !== '';
  });
}

/** At least one secondary param key has a truthy value */
export function hasSecondaryParams(
  params: Record<string, unknown> | null | undefined,
): boolean {
  if (!params) return false;
  return SECONDARY_PARAM_KEYS.some((k) => {
    const v = params[k];
    return v !== undefined && v !== null && v !== '' &&
      !(Array.isArray(v) && v.length === 0);
  });
}

/** Model name, LoRAs, or models[] array is present */
export function hasModelData(
  meta: MetadataResponse | null | undefined,
): boolean {
  if (!meta) return false;
  return !!(
    meta.params?.Model ||
    (meta.params?.Lora && meta.params.Lora.length > 0) ||
    (meta.models && meta.models.length > 0)
  );
}

/** Param keys that belong to neither core, secondary, Model, Lora, Width, Height, SwarmVersion */
export function getExtraParamKeys(
  params: Record<string, unknown> | null | undefined,
): string[] {
  if (!params) return [];
  const known = new Set([
    ...CORE_PARAMS,
    ...SECONDARY_PARAM_KEYS,
    'Model',
    'Lora',
    'Width',
    'Height',
    'SwarmVersion',
  ]);
  return Object.keys(params).filter((k) => !known.has(k));
}

export function hasAdvancedData(
  meta: MetadataResponse | null | undefined,
): boolean {
  if (!meta) return false;
  return getExtraParamKeys(meta.params).length > 0;
}

/** Build secondary param entries for rendering */
export function getSecondaryEntries(
  params: Record<string, unknown> | null | undefined,
): Array<{ key: string; label: string; value: unknown }> {
  if (!params) return [];
  const out: Array<{ key: string; label: string; value: unknown }> = [];
  for (const k of SECONDARY_PARAM_KEYS) {
    const v = params[k];
    if (v !== undefined && v !== null && v !== '' &&
      !(Array.isArray(v) && v.length === 0)) {
      out.push({ key: k, label: SECONDARY_PARAMS_MAP[k] || k, value: v });
    }
  }
  return out;
}
