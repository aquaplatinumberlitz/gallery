<script setup lang="ts">
import { nextTick, onMounted, shallowRef, useTemplateRef } from "vue";
import ExpandableText from "./ExpandableText.vue";
import type { MetadataResponse } from "../types";
import { Loader, X, Calendar, Clock, Maximize, TriangleAlert, ChevronDown } from "lucide-vue-next";
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

const emit = defineEmits<{
  close: [];
}>();

// Internal state
const sheetExpanded = shallowRef(false);
const sheetHandleRef = useTemplateRef<HTMLButtonElement>("sheetHandle");

function toggleExpanded() {
  sheetExpanded.value = !sheetExpanded.value;
}

function closeSheet() {
  sheetExpanded.value = false;
  emit("close");
}

onMounted(async () => {
  await nextTick();
  sheetHandleRef.value?.focus({ preventScroll: true });
});

// Derived and shared with the other metadata panels
const {
  showAdvanced,
  hasGenData,
  hasExtraSettings,
  hasModels,
  hasAdv,
  extraEntries,
  extraParamKeys,
  promptHtml,
  negativePromptHtml,
  copyPrompt,
  copyNegativePrompt,
  copySeed,
} = useMetadataPanel(props);
</script>

<template>
  <div class="tablet-sheet" @click.self="closeSheet">
    <div class="tablet-backdrop" @click.self="closeSheet" />
    <section
      class="tablet-panel"
      :class="{ 'tablet-expanded': sheetExpanded }"
      role="dialog"
      aria-labelledby="tablet-metadata-title"
      @keydown.esc.stop.prevent="closeSheet"
    >
      <h2 id="tablet-metadata-title" class="sr-only">Image information for {{ props.imageName }}</h2>
      <button
        ref="sheetHandle"
        type="button"
        class="tablet-handle-wrapper"
        :aria-label="sheetExpanded ? 'Collapse image information' : 'Expand image information'"
        :aria-expanded="sheetExpanded"
        aria-controls="tablet-metadata-content"
        @click="toggleExpanded"
      >
        <span class="tablet-handle" aria-hidden="true" />
      </button>

      <!-- Loading state -->
      <div v-if="props.isLoading && !props.meta" class="meta-loading" style="flex: 1; min-height: 120px">
        <Loader :stroke-width="1.5" class="lucide-spin icon-nav" />
        <span>Loading info...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="!props.meta" class="meta-error" style="flex: 1; min-height: 120px" data-testid="meta-error">
        <TriangleAlert :stroke-width="1.5" class="icon-nav" />
        <span>No metadata available</span>
      </div>

      <template v-else>
        <!-- Header -->
        <header class="tablet-header">
          <div class="header-row">
            <OverflowTooltip as="h3" :text="props.imageName" align="start">
              {{ props.imageName }}
            </OverflowTooltip>
            <Tooltip>
              <TooltipTrigger as-child>
                <button class="tablet-close-btn" aria-label="Close" @click="closeSheet">
                  <X :stroke-width="1.5" class="icon-lg" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Close</TooltipContent>
            </Tooltip>
          </div>
          <div class="header-meta">
            <span v-if="props.sizeText" class="meta-tag"
              ><Maximize :stroke-width="1.5" class="icon-meta" /> {{ props.sizeText }}</span
            >
            <span v-if="props.dateText" class="meta-tag"
              ><Calendar :stroke-width="1.5" class="icon-meta" /> {{ props.dateText }}</span
            >
            <span v-if="props.genTimeText" class="meta-tag"
              ><Clock :stroke-width="1.5" class="icon-meta" /> {{ props.genTimeText }}</span
            >
            <span v-if="props.meta?.tool" class="source-badge">
              <span class="source-label">SOURCE</span>
              <span class="source-chip">{{ props.meta.tool }}</span>
            </span>
          </div>
        </header>

        <!-- 2-column content -->
        <div id="tablet-metadata-content" class="tablet-grid">
          <!-- Left column: Generation Params + Model -->
          <div class="tablet-col">
            <!-- Generation Data (core) -->
            <div class="tablet-section" :class="{ 'is-empty': !hasGenData }">
              <label class="tablet-label">Generation Data</label>
              <div v-if="hasGenData" class="tablet-pills">
                <Tooltip v-if="props.meta?.params?.Seed">
                  <TooltipTrigger as-child>
                    <div
                      class="param-pill metadata-copyable"
                      role="button"
                      tabindex="0"
                      @click.stop.prevent="copySeed"
                      @keydown.enter.stop.prevent="copySeed"
                      @keydown.space.stop.prevent="copySeed"
                    >
                      <span class="value">{{ props.meta.params.Seed }}</span>
                      <CopyStateIcon :copied="props.copyStatus['seed']" class="copy-icon-stack inline-copy-icon" />
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>Copy seed</TooltipContent>
                </Tooltip>
                <div class="param-pill" v-if="props.meta?.params?.Steps">
                  <span class="label">Steps</span><span class="value">{{ props.meta.params.Steps }}</span>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.CFG">
                  <span class="label">CFG</span><span class="value">{{ props.meta.params.CFG }}</span>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.Sampler">
                  <span class="label">Sampler</span><span class="value">{{ props.meta.params.Sampler }}</span>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.Scheduler">
                  <span class="label">Scheduler</span><span class="value">{{ props.meta.params.Scheduler }}</span>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.AspectRatio">
                  <span class="label">Ratio</span><span class="value">{{ props.meta.params.AspectRatio }}</span>
                </div>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.generation_data }}
              </p>
            </div>

            <!-- Extra Settings (secondary) -->
            <div class="tablet-section" v-if="hasExtraSettings">
              <label class="tablet-label">Extra Settings</label>
              <div class="tablet-pills">
                <div class="param-pill" v-for="entry in extraEntries" :key="entry.key">
                  <span class="label">{{ entry.label }}</span>
                  <span class="value">{{ entry.value }}</span>
                </div>
              </div>
            </div>

            <!-- Model & Resources (core) -->
            <div class="tablet-section" :class="{ 'is-empty': !hasModels }">
              <label class="tablet-label">Model & Resources</label>
              <div v-if="hasModels" class="tablet-model-list">
                <div class="tablet-model-item" v-if="props.meta?.params?.Model">
                  <span class="tablet-model-type">Checkpoint</span>
                  <span class="tablet-model-name">{{ props.meta.params.Model }}</span>
                </div>
                <div class="tablet-model-item" v-for="lora in props.meta?.params?.Lora" :key="lora">
                  <span class="tablet-model-type">LoRA</span>
                  <span class="tablet-model-name">{{ lora }}</span>
                </div>
                <div class="tablet-model-item" v-for="m in props.meta?.models" :key="m.name">
                  <span class="tablet-model-type">{{ m.param || "Model" }}</span>
                  <span class="tablet-model-name">
                    {{ m.name }}
                    <Tooltip v-if="m.hash">
                      <TooltipTrigger as-child>
                        <span class="tablet-hash">#{{ shortModelHash(m.hash) }}</span>
                      </TooltipTrigger>
                      <TooltipContent class="max-w-[260px] break-all">Hash: {{ m.hash }}</TooltipContent>
                    </Tooltip>
                  </span>
                </div>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.model_resources }}
              </p>
            </div>

            <!-- Advanced (debug) -->
            <div class="tablet-section" v-if="hasAdv">
              <button
                type="button"
                class="accordion-header"
                @click="showAdvanced = !showAdvanced"
                :aria-expanded="showAdvanced"
                aria-controls="tablet-advanced-content"
              >
                <label class="tablet-label advanced-label">Advanced</label>
                <span class="count-pill">{{ extraParamKeys.length }}</span>
                <ChevronDown
                  :stroke-width="1.5"
                  class="chevron-icon icon-md"
                  :class="{ 'is-collapsed': !showAdvanced }"
                />
              </button>
              <div id="tablet-advanced-content" v-if="showAdvanced" class="tablet-pills">
                <div class="param-pill" v-for="k in extraParamKeys" :key="k">
                  <span class="label">{{ k }}</span>
                  <span class="value">{{ props.meta?.params?.[k] }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Right column: Prompts -->
          <div class="tablet-col">
            <div class="tablet-section" :class="{ 'is-empty': !props.meta?.prompt }">
              <Tooltip v-if="props.meta?.prompt">
                <TooltipTrigger as-child>
                  <div
                    class="tablet-section-top metadata-copyable"
                    role="button"
                    tabindex="0"
                    @click.stop.prevent="copyPrompt"
                    @keydown.enter.stop.prevent="copyPrompt"
                    @keydown.space.stop.prevent="copyPrompt"
                  >
                    <label class="tablet-label">Prompt</label>
                    <CopyStateIcon :copied="props.copyStatus['prompt']" class="copy-icon-stack inline-copy-icon" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>Copy prompt</TooltipContent>
              </Tooltip>
              <div v-else class="tablet-section-top">
                <label class="tablet-label">Prompt</label>
              </div>
              <div v-if="props.meta?.prompt" class="tablet-text">
                <ExpandableText :collapsed-lines="6" :text="props.meta.prompt">
                  <span v-html="promptHtml" />
                </ExpandableText>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.prompt }}
              </p>
            </div>

            <div class="tablet-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <Tooltip v-if="props.meta?.negative_prompt">
                <TooltipTrigger as-child>
                  <div
                    class="tablet-section-top metadata-copyable"
                    role="button"
                    tabindex="0"
                    @click.stop.prevent="copyNegativePrompt"
                    @keydown.enter.stop.prevent="copyNegativePrompt"
                    @keydown.space.stop.prevent="copyNegativePrompt"
                  >
                    <label class="tablet-label negative-label">Negative Prompt</label>
                    <CopyStateIcon :copied="props.copyStatus['neg']" class="copy-icon-stack inline-copy-icon" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>Copy negative prompt</TooltipContent>
              </Tooltip>
              <div v-else class="tablet-section-top">
                <label class="tablet-label negative-label">Negative Prompt</label>
              </div>
              <div v-if="props.meta?.negative_prompt" class="tablet-text">
                <ExpandableText :collapsed-lines="6" :text="props.meta.negative_prompt">
                  <span v-html="negativePromptHtml" />
                </ExpandableText>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.negative_prompt }}
              </p>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped lang="scss">
@import "../styles/lightbox-shared";
@import "../styles/lightbox-tablet";
@import "../styles/lightbox-panel-common";
@import "../styles/lightbox-panel-icons";

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .inline-copy-icon {
    display: none;
  }
}

.empty-text {
  padding: 4px 0;
}

.icon-meta {
  width: var(--gallery-icon-meta);
  height: var(--gallery-icon-meta);
}
</style>
