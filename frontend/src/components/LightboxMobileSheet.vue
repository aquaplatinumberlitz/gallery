<script setup lang="ts">
import { ref, computed } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import ExpandableText from "./ExpandableText.vue";
import type { MetadataResponse } from "../types";
import { useHaptic } from "../composables/useHaptic";
import {
  Loader, Check, Copy, TriangleAlert, ChevronDown, ChevronUp,
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

const DRAG_THRESHOLD = 60;
const MAX_DRAG = 120;

const sheetExpanded = ref(false);
const activeTab = ref('prompt');
const showAdvanced = ref(false);
const promptExpanded = ref(false);
const negPromptExpanded = ref(false);
const textResetKey = ref(0);
const anyTextExpanded = computed(() => promptExpanded.value || negPromptExpanded.value);
const isSheetVisuallyExpanded = computed(() => sheetExpanded.value || anyTextExpanded.value);

const sheetDragState = ref<'idle' | 'dragging'>('idle');
const dragStartY = ref(0);
const dragDelta = ref(0);
const handleRef = ref<HTMLElement | null>(null);

function setTab(tab: string) {
  activeTab.value = tab;
  hapticLight();
}

function closeSheet() {
  sheetExpanded.value = false;
  emit('close');
}

function toggleSheetExpanded() {
  if (isSheetVisuallyExpanded.value) {
    sheetExpanded.value = false;
    promptExpanded.value = false;
    negPromptExpanded.value = false;
    textResetKey.value += 1;
  } else {
    sheetExpanded.value = true;
  }
  hapticLight();
}

function applyClamp(delta: number): number {
  return Math.max(-MAX_DRAG, Math.min(MAX_DRAG, delta));
}

function onHandlePointerDown(e: PointerEvent) {
  sheetDragState.value = 'dragging';
  dragStartY.value = e.clientY;
  dragDelta.value = 0;
  handleRef.value?.setPointerCapture(e.pointerId);
  e.preventDefault();
}

function onHandlePointerMove(e: PointerEvent) {
  if (sheetDragState.value !== 'dragging') return;
  dragDelta.value = applyClamp(e.clientY - dragStartY.value);
}

function onHandlePointerUp(e: PointerEvent) {
  if (sheetDragState.value !== 'dragging') return;
  const delta = dragDelta.value;
  const wasVisuallyExpanded = isSheetVisuallyExpanded.value;
  handleRef.value?.releasePointerCapture(e.pointerId);

  if (delta > DRAG_THRESHOLD) {
    dragDelta.value = 0;
    sheetDragState.value = 'idle';

    if (wasVisuallyExpanded) {
      sheetExpanded.value = false;
      promptExpanded.value = false;
      negPromptExpanded.value = false;
      textResetKey.value += 1;
    } else {
      closeSheet();
    }
    return;
  } else if (delta < -DRAG_THRESHOLD && !sheetExpanded.value) {
    sheetExpanded.value = true;
  }

  dragDelta.value = 0;
  requestAnimationFrame(() => {
    sheetDragState.value = 'idle';
  });
}

function onHandlePointerCancel() {
  if (sheetDragState.value !== 'dragging') return;
  sheetDragState.value = 'idle';
  dragDelta.value = 0;
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
  <div class="mobile-sheet" @click.self="closeSheet">
    <div class="sheet-backdrop" @click.self="closeSheet" />
    <div
      class="sheet-panel"
      :class="{
        'sheet-expanded': sheetExpanded,
        'is-expanded': anyTextExpanded,
        'no-transition': sheetDragState === 'dragging',
        'is-dragging': sheetDragState === 'dragging',
      }"
      :style="{ transform: `translateY(${dragDelta}px)` }"
    >
      <div
        ref="handleRef"
        class="sheet-handle-wrapper"
        @pointerdown="onHandlePointerDown"
        @pointermove="onHandlePointerMove"
        @pointerup="onHandlePointerUp"
        @pointercancel="onHandlePointerCancel"
      >
        <div class="sheet-handle" />
      </div>

      <div class="sheet-header" v-if="props.meta">
        <div class="sheet-tabs">
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
        <button
          type="button"
          class="sheet-expand-toggle"
          :aria-label="isSheetVisuallyExpanded ? 'Collapse metadata sheet' : 'Expand metadata sheet'"
          :aria-expanded="sheetExpanded"
          @click="toggleSheetExpanded"
        >
          <ChevronDown v-if="isSheetVisuallyExpanded" :size="22" :stroke-width="2.25" />
          <ChevronUp v-else :size="22" :stroke-width="2.25" />
        </button>
      </div>

      <div class="sheet-content" :class="{ 'sheet-content-enter': true }">
        <!-- Loading state -->
        <div v-if="props.isLoading && !props.meta" class="meta-loading">
          <Loader :stroke-width="1.5" class="lucide-spin gallery-icon-nav" />
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
              <div
                class="section-top"
                :class="{ 'metadata-copyable': props.meta?.prompt }"
                @click="props.meta?.prompt && props.copyText(props.meta?.prompt, 'prompt')"
                :title="props.meta?.prompt ? 'Copy prompt' : undefined"
              >
                <label class="sheet-label">Prompt</label>
                <template v-if="props.meta?.prompt">
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" class="inline-copy-icon" />
                  <Copy v-else :size="14" :stroke-width="1.5" class="inline-copy-icon" />
                </template>
              </div>
              <div v-if="props.meta?.prompt" class="sheet-text">
                <ExpandableText :key="`prompt-${textResetKey}`" :collapsed-lines="5" :text="props.meta.prompt" @expanded-change="(val: boolean) => promptExpanded = val">
                  <span v-html="loraHighlighter(props.meta.prompt)"></span>
                </ExpandableText>
              </div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.prompt }}</p>
            </div>
            <div class="meta-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <div
                class="section-top"
                :class="{ 'metadata-copyable': props.meta?.negative_prompt }"
                @click="props.meta?.negative_prompt && props.copyText(props.meta?.negative_prompt, 'neg')"
                :title="props.meta?.negative_prompt ? 'Copy negative prompt' : undefined"
              >
                <label class="sheet-label negative-label">Negative Prompt</label>
                <template v-if="props.meta?.negative_prompt">
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" class="inline-copy-icon" />
                  <Copy v-else :size="14" :stroke-width="1.5" class="inline-copy-icon" />
                </template>
              </div>
              <div v-if="props.meta?.negative_prompt" class="sheet-text">
                <ExpandableText :key="`neg-prompt-${textResetKey}`" :collapsed-lines="5" :text="props.meta.negative_prompt" @expanded-change="(val: boolean) => negPromptExpanded = val">
                  <span v-html="loraHighlighter(props.meta.negative_prompt)"></span>
                </ExpandableText>
              </div>
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
                <div
                  class="param-pill seed-row metadata-copyable"
                  v-if="props.meta?.params?.Seed"
                  @click="props.copyText(String(props.meta.params.Seed), 'seed')"
                  title="Copy seed"
                >
                  <span class="label">Seed</span>
                  <span class="value">{{ props.meta.params.Seed }}</span>
                  <Check v-if="props.copyStatus['seed']" :size="14" :stroke-width="1.5" style="color: #4ade80" class="inline-copy-icon" />
                  <Copy v-else :size="14" :stroke-width="1.5" class="inline-copy-icon" />
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

/* ── Token-based icon sizes ────────────────────────────────── */
.gallery-icon-nav {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
}
</style>
