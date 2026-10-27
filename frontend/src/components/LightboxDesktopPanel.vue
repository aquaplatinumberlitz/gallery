<script setup lang="ts">
import { ref } from "vue";
import ExpandableText from "./ExpandableText.vue";
import type { MetadataResponse } from "../types";
import {
  Loader,
  Maximize,
  Calendar,
  Clock,
  MessageSquareText,
  MessageSquareOff,
  SlidersHorizontal,
  ChevronDown,
  Sprout,
  BrainCircuit,
  Box,
  Puzzle,
  Layers,
  TriangleAlert,
} from "lucide-vue-next";
import { EMPTY_SECTION_TEXT, shortModelHash } from "../composables/useMetadataSections";
import { useMetadataPanel } from "../composables/useMetadataPanel";
import CopyStateIcon from "@/components/ui/CopyStateIcon.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = defineProps<{
  meta: MetadataResponse | null;
  isLoading: boolean;
  imageName: string;
  sizeText: string;
  dateText: string;
  genTimeText: string;
  copyStatus: Record<string, boolean>;
  copyText: (text: string | undefined, id: string) => Promise<boolean>;
}>();

// Collapsible states (Advanced is owned by the shared panel state)
const showGenParams = ref(true);
const showResources = ref(false);

const {
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
} = useMetadataPanel(props);
</script>

<template>
  <aside class="lightbox-right">
    <div v-if="props.isLoading && !props.meta" class="meta-loading">
      <Loader :stroke-width="1.5" class="lucide-spin icon-nav" />
      <span>Loading info...</span>
    </div>

    <div v-else-if="!props.meta" class="meta-error" data-testid="meta-error">
      <TriangleAlert :stroke-width="1.5" class="icon-nav" />
      <span>No metadata available</span>
    </div>

    <template v-else>
      <header class="meta-header">
        <div class="header-top">
          <OverflowTooltip as="h3" id="lightbox-image-name" :text="props.imageName" align="start">
            {{ props.imageName }}
          </OverflowTooltip>
        </div>
        <div class="header-meta">
          <span v-if="props.sizeText" class="meta-tag"
            ><Maximize :stroke-width="1.5" class="icon-xs" /> {{ props.sizeText }}</span
          >
          <span v-if="props.dateText" class="meta-tag"
            ><Calendar :stroke-width="1.5" class="icon-xs" /> {{ props.dateText }}</span
          >
          <span v-if="props.genTimeText" class="meta-tag"
            ><Clock :stroke-width="1.5" class="icon-xs" /> {{ props.genTimeText }}</span
          >
          <span v-if="props.meta?.tool" class="source-badge">
            <span class="source-label">SOURCE</span>
            <span class="source-chip">{{ props.meta.tool }}</span>
          </span>
        </div>
      </header>

      <div class="scroll-content">
        <!-- ========== Prompt (core) ========== -->
        <section class="prompt-box" :class="{ 'is-empty': !props.meta?.prompt }">
          <div class="section-top">
            <h4><MessageSquareText :stroke-width="1.5" class="icon-sm" /> Prompt</h4>
            <Tooltip v-if="props.meta?.prompt">
              <TooltipTrigger as-child>
                <button type="button" class="copy-btn" aria-label="Copy prompt" @click.stop.prevent="copyPrompt">
                  <CopyStateIcon :copied="props.copyStatus['prompt']" class="copy-icon-stack" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Copy prompt</TooltipContent>
            </Tooltip>
          </div>
          <div v-if="props.meta?.prompt" class="prompt-body">
            <ExpandableText :collapsed-lines="8" :text="props.meta.prompt">
              <span v-html="promptHtml" />
            </ExpandableText>
          </div>
          <p v-else class="empty-text">
            {{ EMPTY_SECTION_TEXT.prompt }}
          </p>
        </section>

        <!-- ========== Negative Prompt (core) ========== -->
        <section class="prompt-box negative" :class="{ 'is-empty': !props.meta?.negative_prompt }">
          <div class="section-top">
            <h4><MessageSquareOff :stroke-width="1.5" class="icon-sm" /> Negative</h4>
            <Tooltip v-if="props.meta?.negative_prompt">
              <TooltipTrigger as-child>
                <button
                  type="button"
                  class="copy-btn"
                  aria-label="Copy negative prompt"
                  @click.stop.prevent="copyNegativePrompt"
                >
                  <CopyStateIcon :copied="props.copyStatus['neg']" class="copy-icon-stack" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Copy negative prompt</TooltipContent>
            </Tooltip>
          </div>
          <div v-if="props.meta?.negative_prompt" class="prompt-body">
            <ExpandableText :collapsed-lines="8" :text="props.meta.negative_prompt">
              <span v-html="negativePromptHtml" />
            </ExpandableText>
          </div>
          <p v-else class="empty-text">
            {{ EMPTY_SECTION_TEXT.negative_prompt }}
          </p>
        </section>

        <!-- ========== Generation Data (core) ========== -->
        <section class="meta-group" :class="{ 'is-empty': !hasGenData }">
          <button
            type="button"
            class="accordion-header"
            :disabled="!hasGenData"
            @click="showGenParams = !showGenParams"
            :aria-expanded="hasGenData ? showGenParams : undefined"
            aria-controls="gen-data-content"
          >
            <h4><SlidersHorizontal :stroke-width="1.5" class="icon-sm" /> Generation Data</h4>
            <span v-if="hasGenData" class="count-pill">{{ genParamsCount }}</span>
            <ChevronDown
              v-if="hasGenData"
              :stroke-width="1.5"
              class="chevron-icon icon-md"
              :class="{ 'is-collapsed': !showGenParams }"
            />
          </button>
          <div id="gen-data-content" v-if="hasGenData" class="group-content" v-show="showGenParams">
            <div class="params-grid">
              <div class="param-pill" v-if="props.meta?.params?.Seed">
                <span class="label">Seed</span>
                <span class="value">{{ props.meta.params.Seed }}</span>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <button class="icon-btn" aria-label="Copy seed" @click.stop.prevent="copySeed">
                      <CopyStateIcon
                        :copied="props.copyStatus['seed']"
                        :default-icon="Sprout"
                        class="copy-icon-stack"
                        style="--copy-icon-stack-size: var(--gallery-icon-xs)"
                      />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>Copy seed</TooltipContent>
                </Tooltip>
              </div>
              <div class="param-pill" v-if="props.meta?.params?.Steps">
                <span class="label">Steps</span>
                <span class="value">{{ props.meta.params.Steps }}</span>
              </div>
              <div class="param-pill" v-if="props.meta?.params?.CFG">
                <span class="label">CFG</span>
                <span class="value">{{ props.meta.params.CFG }}</span>
              </div>
              <div class="param-pill" v-if="props.meta?.params?.Sampler">
                <span class="label">Sampler</span>
                <span class="value">{{ props.meta.params.Sampler }}</span>
              </div>
              <div class="param-pill" v-if="props.meta?.params?.Scheduler">
                <span class="label">Scheduler</span>
                <span class="value">{{ props.meta.params.Scheduler }}</span>
              </div>
              <div class="param-pill" v-if="props.meta?.params?.AspectRatio">
                <span class="label">Ratio</span>
                <span class="value">{{ props.meta.params.AspectRatio }}</span>
              </div>
            </div>
          </div>
          <p v-else class="empty-text" style="padding: 12px">
            {{ EMPTY_SECTION_TEXT.generation_data }}
          </p>
        </section>

        <!-- ========== Extra Settings (secondary) ========== -->
        <section v-if="hasExtraSettings" class="meta-group">
          <div class="group-header static">
            <h4><SlidersHorizontal :stroke-width="1.5" class="icon-sm" /> Extra Settings</h4>
          </div>
          <div class="group-content">
            <div class="params-grid">
              <div v-for="entry in extraEntries" :key="entry.key" class="param-pill">
                <span class="label">{{ entry.label }}</span>
                <span class="value">{{ entry.value }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ========== Model & Resources (core) ========== -->
        <section class="meta-group" :class="{ 'is-empty': !hasModels }">
          <button
            type="button"
            class="accordion-header"
            :disabled="!hasModels"
            @click="showResources = !showResources"
            :aria-expanded="hasModels ? showResources : undefined"
            aria-controls="model-resources-content"
          >
            <h4><BrainCircuit :stroke-width="1.5" class="icon-sm" /> Model & Resources</h4>
            <span v-if="hasModels" class="count-pill">{{ modelCount }}</span>
            <ChevronDown
              v-if="hasModels"
              :stroke-width="1.5"
              class="chevron-icon icon-md"
              :class="{ 'is-collapsed': !showResources }"
            />
          </button>
          <div id="model-resources-content" v-if="hasModels" class="group-content" v-show="showResources">
            <div class="resource-list">
              <div class="resource-item" v-if="props.meta?.params?.Model">
                <Box :stroke-width="1.5" class="icon-sm" />
                <div class="res-info">
                  <span class="res-type">Checkpoint</span>
                  <span class="res-name">{{ props.meta.params.Model }}</span>
                </div>
              </div>

              <div class="resource-item" v-for="lora in props.meta?.params?.Lora" :key="lora">
                <Puzzle :stroke-width="1.5" class="icon-sm" />
                <div class="res-info">
                  <span class="res-type">LoRA</span>
                  <span class="res-name">{{ lora }}</span>
                </div>
              </div>

              <!-- Swarm Specific Models List -->
              <div class="resource-item" v-for="m in props.meta?.models" :key="m.name">
                <Layers :stroke-width="1.5" class="icon-sm" />
                <div class="res-info">
                  <span class="res-type">{{ m.param || "Model" }}</span>
                  <span class="res-name">
                    {{ m.name }}
                    <Tooltip v-if="m.hash">
                      <TooltipTrigger as-child>
                        <span class="res-hash">#{{ shortModelHash(m.hash) }}</span>
                      </TooltipTrigger>
                      <TooltipContent class="max-w-[260px] break-all">Hash: {{ m.hash }}</TooltipContent>
                    </Tooltip>
                  </span>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="empty-text" style="padding: 12px">
            {{ EMPTY_SECTION_TEXT.model_resources }}
          </p>
        </section>

        <!-- ========== Advanced (debug) ========== -->
        <section v-if="hasAdv" class="meta-group advanced">
          <button
            type="button"
            class="accordion-header"
            @click="showAdvanced = !showAdvanced"
            :aria-expanded="showAdvanced"
            aria-controls="advanced-content"
          >
            <h4>Advanced</h4>
            <span class="count-pill">{{ extraParamKeys.length }}</span>
            <ChevronDown :stroke-width="1.5" class="chevron-icon icon-md" :class="{ 'is-collapsed': !showAdvanced }" />
          </button>
          <div id="advanced-content" class="group-content" v-show="showAdvanced">
            <div class="params-grid">
              <div v-for="k in extraParamKeys" :key="k" class="param-pill">
                <span class="label">{{ k }}</span>
                <span class="value">{{ props.meta?.params?.[k] }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>
  </aside>
</template>

<style scoped lang="scss">
@import "../styles/lightbox-shared";
@import "../styles/lightbox-desktop";
@import "../styles/lightbox-panel-common";
@import "../styles/lightbox-panel-icons";

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .copy-btn {
    display: none;
  }
}

.empty-text {
  padding: 0 4px;
}
</style>
