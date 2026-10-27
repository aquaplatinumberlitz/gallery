/**
 * useMetadataPanel — derived state and actions shared by the desktop, tablet, and mobile
 * lightbox metadata panels.
 *
 * Each panel keeps its own layout and markup; this composable owns what they have in common:
 * which sections have data, section counts, the collapsible "Advanced" state, LoRA-highlighted
 * prompt HTML, and the copy actions wired to the lightbox clipboard helper.
 */

import { computed, shallowRef } from "vue";
import type { MetadataResponse } from "../types";
import { loraHighlighter } from "../utils/loraHighlighter";
import {
  countGenerationParams,
  countModelResources,
  getExtraParamKeys,
  getSecondaryEntries,
  hasAdvancedData,
  hasCoreParams,
  hasModelData,
  hasSecondaryParams,
} from "./useMetadataSections";

export interface MetadataPanelSource {
  readonly meta: MetadataResponse | null;
  readonly copyText: (text: string | undefined, id: string) => Promise<boolean>;
}

export function useMetadataPanel(source: MetadataPanelSource) {
  const showAdvanced = shallowRef(false);

  // Which sections have data
  const hasGenData = computed(() => hasCoreParams(source.meta?.params));
  const hasExtraSettings = computed(() => hasSecondaryParams(source.meta?.params));
  const hasModels = computed(() => hasModelData(source.meta));
  const hasAdv = computed(() => hasAdvancedData(source.meta));
  const extraEntries = computed(() => getSecondaryEntries(source.meta?.params));
  const extraParamKeys = computed(() => getExtraParamKeys(source.meta?.params));

  // Counts for accordion pills
  const genParamsCount = computed(() => countGenerationParams(source.meta));
  const modelCount = computed(() => countModelResources(source.meta));

  // `v-html` payloads (LoRA tags wrapped in `.lora-pill` spans)
  const promptHtml = computed(() => (source.meta?.prompt ? loraHighlighter(source.meta.prompt) : ""));
  const negativePromptHtml = computed(() =>
    source.meta?.negative_prompt ? loraHighlighter(source.meta.negative_prompt) : "",
  );

  // Copy actions (ids match the `copyStatus` keys read by the templates)
  const copyPrompt = () => source.copyText(source.meta?.prompt, "prompt");
  const copyNegativePrompt = () => source.copyText(source.meta?.negative_prompt, "neg");
  const copySeed = () => source.copyText(String(source.meta?.params?.Seed), "seed");

  return {
    showAdvanced,
    hasGenData,
    hasExtraSettings,
    hasModels,
    hasAdv,
    extraEntries,
    extraParamKeys,
    genParamsCount,
    modelCount,
    promptHtml,
    negativePromptHtml,
    copyPrompt,
    copyNegativePrompt,
    copySeed,
  };
}
