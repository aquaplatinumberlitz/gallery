<script setup lang="ts">
import { ref, computed } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import { useHaptic } from "../composables/useHaptic";
import {
  Loader, Check, Copy, TriangleAlert, ChevronDown,
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

const { light: hapticLight } = useHaptic();

const props = defineProps<{
  meta: MetadataResponse | null;
  isLoading: boolean;
  copyStatus: Record<string, boolean>;
  copyText: (text: string | undefined, id: string) => Promise<void>;
}>();

const emit = defineEmits<{
  close: [];
}>();

// Internal state
const sheetExpanded = ref(false);
const activeTab = ref('prompt');
const sheetStartY = ref(0);
const showAdvanced = ref(false);

function setTab(tab: string) {
  activeTab.value = tab;
  hapticLight();
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
  <div class="mobile-sheet" @click.self="closeSheet">
    <div class="sheet-backdrop" @click.self="closeSheet" />
    <div
      class="sheet-panel"
      :class="{ 'sheet-expanded': sheetExpanded }"
      @touchstart="onSheetTouchStart"
      @touchmove="onSheetTouchMove"
      @touchend="onSheetTouchEnd"
    >
      <div class="sheet-handle-wrapper" @click="closeSheet">
        <div class="sheet-handle" />
      </div>

      <div class="sheet-tabs" v-if="props.meta">
        <button class="sheet-tab" :class="{ active: activeTab === 'prompt' }" @click="setTab('prompt')">
          Prompt
        </button>
        <button class="sheet-tab" :class="{ active: activeTab === 'params' }" @click="setTab('params')">
          Params
        </button>
        <button class="sheet-tab" :class="{ active: activeTab === 'model' }" @click="setTab('model')">
          Model
        </button>
      </div>

      <div class="sheet-content" :class="{ 'sheet-content-enter': true }">
        <!-- Loading state -->
        <div v-if="props.isLoading && !props.meta" class="meta-loading">
          <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
          <span>Loading info...</span>
        </div>

        <!-- Error state -->
        <div v-else-if="!props.meta" class="meta-error">
          <TriangleAlert :size="24" :stroke-width="1.5" />
          <span>No metadata available</span>
        </div>

        <template v-else>
          <!-- ========== Tab: Prompt ========== -->
          <div v-show="activeTab === 'prompt'" class="sheet-tab-content">
            <div class="meta-section" :class="{ 'is-empty': !props.meta?.prompt }">
              <div class="section-top">
                <label class="sheet-label">Prompt</label>
                <button v-if="props.meta?.prompt" class="copy-btn" @click="props.copyText(props.meta?.prompt || '', 'prompt')">
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                v-if="props.meta?.prompt"
                class="sheet-text"
                v-html="loraHighlighter(props.meta.prompt)"
              ></div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.prompt }}</p>
            </div>
            <div class="meta-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <div class="section-top">
                <label class="sheet-label negative-label">Negative Prompt</label>
                <button v-if="props.meta?.negative_prompt" class="copy-btn" @click="props.copyText(props.meta?.negative_prompt || '', 'neg')">
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                v-if="props.meta?.negative_prompt"
                class="sheet-text"
                v-html="loraHighlighter(props.meta.negative_prompt)"
              ></div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.negative_prompt }}</p>
            </div>
          </div>

          <!-- ========== Tab: Params ========== -->
          <div v-show="activeTab === 'params'" class="sheet-tab-content">
            <!-- Tool label -->
            <div class="meta-section" v-if="props.meta?.tool">
              <div class="source-badge">
                <span class="source-label">SOURCE</span>
                <span class="source-chip">{{ props.meta.tool }}</span>
              </div>
            </div>

            <!-- Generation Data (core) -->
            <div class="meta-section" :class="{ 'is-empty': !hasGenData }">
              <label class="sheet-label">Generation Data</label>
              <div v-if="hasGenData" class="params-grid">
                <div class="param-pill seed-row" v-if="props.meta?.params?.Seed">
                  <span class="label">Seed</span>
                  <span class="value">{{ props.meta.params.Seed }}</span>
                  <button class="copy-btn-mini" @click="props.copyText(String(props.meta.params.Seed), 'seed')" title="Copy seed">
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
            <div class="meta-section" v-if="hasExtraSettings">
              <label class="sheet-label">Extra Settings</label>
              <div class="params-grid">
                <div class="param-pill" v-for="entry in extraEntries" :key="entry.key">
                  <span class="label">{{ entry.label }}</span>
                  <span class="value">{{ entry.value }}</span>
                </div>
              </div>
            </div>

            <!-- Advanced (debug) -->
            <div class="meta-section" v-if="hasAdv">
              <button
                type="button"
                class="accordion-header"
                @click="showAdvanced = !showAdvanced"
                :aria-expanded="showAdvanced"
                aria-controls="mobile-advanced-content"
              >
                <label class="sheet-label advanced-label">Advanced</label>
                <span class="count-pill">{{ extraParamKeys.length }}</span>
                <ChevronDown
                  :size="16"
                  :stroke-width="1.5"
                  class="chevron-icon"
                  :class="{ 'is-collapsed': !showAdvanced }"
                />
              </button>
              <div id="mobile-advanced-content" v-if="showAdvanced" class="params-grid">
                <div class="param-pill" v-for="k in extraParamKeys" :key="k">
                  <span class="label">{{ k }}</span>
                  <span class="value">{{ props.meta?.params?.[k] }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- ========== Tab: Model ========== -->
          <div v-show="activeTab === 'model'" class="sheet-tab-content">
            <div class="meta-section" :class="{ 'is-empty': !hasModels }">
              <label v-if="props.meta?.params?.Model" class="sheet-label">Checkpoint</label>
              <p v-if="props.meta?.params?.Model" class="sheet-text">{{ props.meta.params.Model }}</p>

              <label v-if="props.meta?.params?.Lora?.length" class="sheet-label" style="margin-top: 12px;">LoRAs</label>
              <p class="sheet-text" v-for="(lora, idx) in props.meta?.params?.Lora" :key="idx">{{ lora }}</p>

              <label v-if="props.meta?.models?.length" class="sheet-label" style="margin-top: 12px;">{{ props.meta.models.length === 1 ? 'Model' : 'Models' }}</label>
              <div v-for="m in props.meta?.models" :key="m.name">
                <p class="sheet-text">
                  {{ m.name }}
                  <span v-if="m.hash" class="res-hash">#{{ m.hash.substring(0, 8) }}</span>
                </p>
              </div>

              <p v-if="!hasModels" class="empty-text">{{ EMPTY_SECTION_TEXT.model_resources }}</p>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@import '../styles/lightbox-shared';
@import '../styles/lightbox-mobile';

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .copy-btn,
  .copy-btn-mini {
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
