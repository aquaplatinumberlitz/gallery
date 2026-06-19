<script setup lang="ts">
import { ref, computed } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import ExpandableText from "./ExpandableText.vue";
import type { MetadataResponse } from "../types";
import { Loader, X, Calendar, Clock, Maximize, Check, Copy, TriangleAlert, ChevronDown } from "lucide-vue-next";
import {
  hasCoreParams,
  hasSecondaryParams,
  hasModelData,
  hasAdvancedData,
  getSecondaryEntries,
  getExtraParamKeys,
  EMPTY_SECTION_TEXT,
} from "../composables/useMetadataSections";

const props = defineProps<{
  meta: MetadataResponse | null;
  isLoading: boolean;
  imageName: string;
  sizeText: string;
  dateText: string;
  genTimeText: string;
  copyStatus: Record<string, boolean>;
  copyText: (text: string | undefined, id: string) => Promise<void>;
}>();

const emit = defineEmits<{
  close: [];
}>();

// Internal state
const sheetExpanded = ref(false);
const sheetStartY = ref(0);
const showAdvanced = ref(false);

function toggleExpanded() {
  sheetExpanded.value = !sheetExpanded.value;
}

function closeSheet() {
  sheetExpanded.value = false;
  emit("close");
}

function onSheetTouchStart(e: TouchEvent) {
  sheetStartY.value = e.touches[0].clientY;
}

function onSheetTouchMove(e: TouchEvent) {
  const delta = e.touches[0].clientY - sheetStartY.value;
  if (delta > 50) closeSheet();
  if (delta < -50) sheetExpanded.value = true;
}

function onSheetTouchEnd() {
  /* no-op */
}

// Derived
const hasGenData = computed(() => hasCoreParams(props.meta?.params));
const hasExtraSettings = computed(() => hasSecondaryParams(props.meta?.params));
const hasModels = computed(() => hasModelData(props.meta));
const hasAdv = computed(() => hasAdvancedData(props.meta));
const extraEntries = computed(() => getSecondaryEntries(props.meta?.params));
const extraParamKeys = computed(() => getExtraParamKeys(props.meta?.params));
</script>

<template>
  <div class="tablet-sheet" @click.self="closeSheet">
    <div class="tablet-backdrop" @click.self="closeSheet" />
    <div
      class="tablet-panel"
      :class="{ 'tablet-expanded': sheetExpanded }"
      @touchstart="onSheetTouchStart"
      @touchmove="onSheetTouchMove"
      @touchend="onSheetTouchEnd"
    >
      <div class="tablet-handle-wrapper" @click="toggleExpanded">
        <div class="tablet-handle" />
      </div>

      <!-- Loading state -->
      <div v-if="props.isLoading && !props.meta" class="meta-loading" style="flex: 1; min-height: 120px">
        <Loader :stroke-width="1.5" class="lucide-spin icon-nav" />
        <span>Loading info...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="!props.meta" class="meta-error" style="flex: 1; min-height: 120px">
        <TriangleAlert :stroke-width="1.5" class="icon-nav" />
        <span>No metadata available</span>
      </div>

      <template v-else>
        <!-- Header -->
        <header class="tablet-header">
          <div class="header-row">
            <h3 :title="props.imageName">
              {{ props.imageName }}
            </h3>
            <button class="tablet-close-btn" @click="closeSheet" title="Close">
              <X :stroke-width="1.5" class="icon-lg" />
            </button>
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
        <div class="tablet-grid">
          <!-- Left column: Generation Params + Model -->
          <div class="tablet-col">
            <!-- Generation Data (core) -->
            <div class="tablet-section" :class="{ 'is-empty': !hasGenData }">
              <label class="tablet-label">Generation Data</label>
              <div v-if="hasGenData" class="tablet-pills">
                <div
                  class="param-pill metadata-copyable"
                  v-if="props.meta?.params?.Seed"
                  @click="props.copyText(String(props.meta.params.Seed), 'seed')"
                  title="Copy seed"
                >
                  <span class="value">{{ props.meta.params.Seed }}</span>
                  <Check
                    v-if="props.copyStatus['seed']"
                    :stroke-width="1.5"
                    :size="14"
                    style="color: #4ade80"
                    class="inline-copy-icon"
                  />
                  <Copy v-else :stroke-width="1.5" :size="14" class="inline-copy-icon" />
                </div>
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
                    <span v-if="m.hash" class="tablet-hash" :title="'Hash: ' + m.hash"
                      >#{{ m.hash.substring(0, 8) }}</span
                    >
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
              <div
                class="tablet-section-top"
                :class="{ 'metadata-copyable': props.meta?.prompt }"
                @click="props.meta?.prompt && props.copyText(props.meta?.prompt, 'prompt')"
                :title="props.meta?.prompt ? 'Copy prompt' : undefined"
              >
                <label class="tablet-label">Prompt</label>
                <template v-if="props.meta?.prompt">
                  <Check
                    v-if="props.copyStatus['prompt']"
                    :stroke-width="1.5"
                    :size="14"
                    style="color: #4ade80"
                    class="inline-copy-icon"
                  />
                  <Copy v-else :stroke-width="1.5" :size="14" class="inline-copy-icon" />
                </template>
              </div>
              <div v-if="props.meta?.prompt" class="tablet-text">
                <ExpandableText :collapsed-lines="6" :text="props.meta.prompt">
                  <span v-html="loraHighlighter(props.meta.prompt)" />
                </ExpandableText>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.prompt }}
              </p>
            </div>

            <div class="tablet-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <div
                class="tablet-section-top"
                :class="{ 'metadata-copyable': props.meta?.negative_prompt }"
                @click="props.meta?.negative_prompt && props.copyText(props.meta?.negative_prompt, 'neg')"
                :title="props.meta?.negative_prompt ? 'Copy negative prompt' : undefined"
              >
                <label class="tablet-label negative-label">Negative Prompt</label>
                <template v-if="props.meta?.negative_prompt">
                  <Check
                    v-if="props.copyStatus['neg']"
                    :stroke-width="1.5"
                    :size="14"
                    style="color: #4ade80"
                    class="inline-copy-icon"
                  />
                  <Copy v-else :stroke-width="1.5" :size="14" class="inline-copy-icon" />
                </template>
              </div>
              <div v-if="props.meta?.negative_prompt" class="tablet-text">
                <ExpandableText :collapsed-lines="6" :text="props.meta.negative_prompt">
                  <span v-html="loraHighlighter(props.meta.negative_prompt)" />
                </ExpandableText>
              </div>
              <p v-else class="empty-text">
                {{ EMPTY_SECTION_TEXT.negative_prompt }}
              </p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
@import "../styles/lightbox-shared";
@import "../styles/lightbox-tablet";

/* LoRA highlighter — penetrate v-html injected spans */
:deep(.lora-pill) {
  color: #c084fc;
  font-weight: 600;
}

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .inline-copy-icon {
    display: none;
  }
}

.empty-text {
  color: #888;
  font-size: 13px;
  font-style: italic;
  margin: 0;
  padding: 4px 0;
}

/* Icon sizing tokens */
.icon-nav {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
}

.icon-lg {
  width: var(--gallery-icon-lg);
  height: var(--gallery-icon-lg);
}

.icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

.icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}

.icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}

.icon-meta {
  width: var(--gallery-icon-meta);
  height: var(--gallery-icon-meta);
}
</style>
