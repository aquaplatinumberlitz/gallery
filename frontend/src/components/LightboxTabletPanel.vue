<script setup lang="ts">
import { ref, computed } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import {
  Loader, X, Calendar, Clock, Maximize,
  Check, Copy, TriangleAlert,
} from "lucide-vue-next";
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
  emit('close');
}

function onSheetTouchStart(e: TouchEvent) {
  sheetStartY.value = e.touches[0].clientY;
}

function onSheetTouchMove(e: TouchEvent) {
  const delta = e.touches[0].clientY - sheetStartY.value;
  if (delta > 50) closeSheet();
  if (delta < -50) sheetExpanded.value = true;
}

function onSheetTouchEnd() { /* no-op */ }

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
      <div v-if="props.isLoading && !props.meta" class="meta-loading" style="flex: 1; min-height: 120px;">
        <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
        <span>Loading info...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="!props.meta" class="meta-error" style="flex: 1; min-height: 120px;">
        <TriangleAlert :size="24" :stroke-width="1.5" />
        <span>No metadata available</span>
      </div>

      <template v-else>
        <!-- Header -->
        <header class="tablet-header">
          <div class="header-row">
            <h3 :title="props.imageName">{{ props.imageName }}</h3>
            <button
              class="tablet-close-btn"
              @click="closeSheet"
              title="Close"
            >
              <X :size="18" :stroke-width="1.5" />
            </button>
          </div>
          <div class="header-meta">
            <span v-if="props.sizeText" class="meta-tag"><Maximize :size="11" :stroke-width="1.5" /> {{ props.sizeText }}</span>
            <span v-if="props.dateText" class="meta-tag"><Calendar :size="11" :stroke-width="1.5" /> {{ props.dateText }}</span>
            <span v-if="props.genTimeText" class="meta-tag"><Clock :size="11" :stroke-width="1.5" /> {{ props.genTimeText }}</span>
            <span v-if="props.meta?.tool" class="meta-tag tool-tag">{{ props.meta.tool }}</span>
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
                <div class="param-pill" v-if="props.meta?.params?.Seed">
                  <span class="value">{{ props.meta.params.Seed }}</span>
                  <button class="icon-btn" @click="props.copyText(String(props.meta.params.Seed), 'seed')" title="Copy seed">
                    <Check v-if="props.copyStatus['seed']" :size="12" :stroke-width="1.5" style="color: #4ade80" />
                    <Copy v-else :size="12" :stroke-width="1.5" />
                  </button>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.Steps"><span class="label">Steps</span><span class="value">{{ props.meta.params.Steps }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.CFG"><span class="label">CFG</span><span class="value">{{ props.meta.params.CFG }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.Sampler"><span class="label">Sampler</span><span class="value">{{ props.meta.params.Sampler }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.Scheduler"><span class="label">Scheduler</span><span class="value">{{ props.meta.params.Scheduler }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.AspectRatio"><span class="label">Ratio</span><span class="value">{{ props.meta.params.AspectRatio }}</span></div>
              </div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.generation_data }}</p>
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
                  <span class="tablet-model-type">{{ m.param || 'Model' }}</span>
                  <span class="tablet-model-name">
                    {{ m.name }}
                    <span v-if="m.hash" class="tablet-hash" :title="'Hash: ' + m.hash">#{{ m.hash.substring(0, 8) }}</span>
                  </span>
                </div>
              </div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.model_resources }}</p>
            </div>

            <!-- Advanced (debug) -->
            <div class="tablet-section" v-if="hasAdv">
              <div class="tablet-section-top" @click="showAdvanced = !showAdvanced" style="cursor: pointer;">
                <label class="tablet-label advanced-label">Advanced</label>
              </div>
              <div v-if="showAdvanced" class="tablet-pills">
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
              <div class="tablet-section-top">
                <label class="tablet-label">Prompt</label>
                <button v-if="props.meta?.prompt" class="tablet-copy-btn" @click="props.copyText(props.meta?.prompt, 'prompt')">
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                v-if="props.meta?.prompt"
                class="tablet-text"
                v-html="loraHighlighter(props.meta.prompt)"
              ></div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.prompt }}</p>
            </div>

            <div class="tablet-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <div class="tablet-section-top">
                <label class="tablet-label negative-label">Negative Prompt</label>
                <button v-if="props.meta?.negative_prompt" class="tablet-copy-btn" @click="props.copyText(props.meta?.negative_prompt, 'neg')">
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                v-if="props.meta?.negative_prompt"
                class="tablet-text"
                v-html="loraHighlighter(props.meta.negative_prompt)"
              ></div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.negative_prompt }}</p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
@import '../styles/lightbox-shared';
@import '../styles/lightbox-tablet';

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .copy-btn,
  .tablet-copy-btn,
  .icon-btn {
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
</style>
