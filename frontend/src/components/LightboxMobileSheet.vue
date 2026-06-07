<script setup lang="ts">
import { ref, computed } from "vue";
import BottomSheet from "@douxcode/vue-spring-bottom-sheet";
import "@douxcode/vue-spring-bottom-sheet/dist/style.css";
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

const bottomSheetRef = ref<InstanceType<typeof BottomSheet>>();
const sheetOpen = ref(true);
const sheetExpanded = ref(false);
const activeTab = ref('prompt');
const showAdvanced = ref(false);
const promptExpanded = ref(false);
const negPromptExpanded = ref(false);
const textResetKey = ref(0);
const anyTextExpanded = computed(() => promptExpanded.value || negPromptExpanded.value);
const isSheetVisuallyExpanded = computed(() => sheetExpanded.value || anyTextExpanded.value);
const snapPoints = ['44%', '80%'] as Array<`${number}%`>;

function setTab(tab: string) {
  activeTab.value = tab;
  hapticLight();
}

function onSheetClosed() {
  sheetOpen.value = false;
  sheetExpanded.value = false;
  emit('close');
}

function snapToCompact() {
  sheetExpanded.value = false;
  bottomSheetRef.value?.snapToPoint(0);
}

function snapToExpanded() {
  sheetExpanded.value = true;
  bottomSheetRef.value?.snapToPoint(1);
}

function collapsePromptDetails() {
  promptExpanded.value = false;
  negPromptExpanded.value = false;
  textResetKey.value += 1;
  snapToCompact();
}

function expandPromptDetails() {
  promptExpanded.value = true;
  negPromptExpanded.value = true;
  textResetKey.value += 1;
  snapToExpanded();
}

function toggleSheetExpanded() {
  if (isSheetVisuallyExpanded.value) {
    collapsePromptDetails();
  } else {
    expandPromptDetails();
  }
  hapticLight();
}

function onPromptExpandedChange(val: boolean) {
  promptExpanded.value = val;
  if (val) {
    snapToExpanded();
  }
}

function onNegPromptExpandedChange(val: boolean) {
  negPromptExpanded.value = val;
  if (val) {
    snapToExpanded();
  }
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
  <BottomSheet
    ref="bottomSheetRef"
    v-model="sheetOpen"
    teleport-defer
    header-class="mobile-sheet-header-slot"
    content-class="sheet-content"
    :snap-points="snapPoints"
    :initial-snap-point="0"
    :blocking="false"
    :can-backdrop-close="false"
    :can-swipe-close="true"
    :expand-on-content-drag="true"
    swipe-close-threshold="35%"
    @closed="onSheetClosed"
    @snapped="(index) => { sheetExpanded = index === 1; }"
  >
    <template #header>
      <div class="sheet-header" v-if="props.meta" data-vsbs-no-drag>
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
    </template>

      <div class="sheet-content-inner">
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
              >
                <label class="sheet-label">Prompt</label>
                <button
                  v-if="props.meta?.prompt"
                  type="button"
                  class="inline-copy-button"
                  title="Copy prompt"
                  aria-label="Copy prompt"
                  @click.stop="props.copyText(props.meta?.prompt, 'prompt')"
                >
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" class="inline-copy-icon" />
                  <Copy v-else :size="14" :stroke-width="1.5" class="inline-copy-icon" />
                </button>
              </div>
              <div v-if="props.meta?.prompt" class="sheet-text">
                <ExpandableText :key="`prompt-${textResetKey}`" :collapsed-lines="5" :text="props.meta.prompt" :expanded="promptExpanded" @expanded-change="onPromptExpandedChange">
                  <span v-html="loraHighlighter(props.meta.prompt)"></span>
                </ExpandableText>
              </div>
              <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.prompt }}</p>
            </div>
            <div class="meta-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
              <div
                class="section-top"
                :class="{ 'metadata-copyable': props.meta?.negative_prompt }"
              >
                <label class="sheet-label negative-label">Negative Prompt</label>
                <button
                  v-if="props.meta?.negative_prompt"
                  type="button"
                  class="inline-copy-button"
                  title="Copy negative prompt"
                  aria-label="Copy negative prompt"
                  @click.stop="props.copyText(props.meta?.negative_prompt, 'neg')"
                >
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" class="inline-copy-icon" />
                  <Copy v-else :size="14" :stroke-width="1.5" class="inline-copy-icon" />
                </button>
              </div>
              <div v-if="props.meta?.negative_prompt" class="sheet-text">
                <ExpandableText :key="`neg-prompt-${textResetKey}`" :collapsed-lines="5" :text="props.meta.negative_prompt" :expanded="negPromptExpanded" @expanded-change="onNegPromptExpandedChange">
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
  </BottomSheet>
</template>

<style lang="scss">
/* VSBS overrides must be global because BottomSheet teleports these nodes to body. */
[data-vsbs-sheet] {
  --vsbs-backdrop-bg: linear-gradient(
    to bottom,
    rgba(0,0,0,0.04) 0%,
    rgba(0,0,0,0.12) 50%,
    rgba(0,0,0,0.28) 100%
  );
  --vsbs-background: var(--gallery-lightbox-bg, #1a1a1a);
  --vsbs-border-radius: 16px;
  --vsbs-border-color: var(--gallery-lightbox-border, rgba(255,255,255,0.1));
  --vsbs-outer-border-color: transparent;
  --vsbs-padding-x: 0px;
  --vsbs-handle-background: rgba(255, 255, 255, 0.3);
  width: 100vw !important;
  inline-size: 100vw !important;
  min-width: 0 !important;
  max-width: 100vw !important;
  left: 0 !important;
  right: 0 !important;
  box-sizing: border-box;
  background: var(--gallery-lightbox-bg, #1a1a1a);
  color: #e5e7eb;
  z-index: 100010;
}

[data-vsbs-backdrop] {
  background: linear-gradient(
    to bottom,
    rgba(0,0,0,0.04) 0%,
    rgba(0,0,0,0.12) 50%,
    rgba(0,0,0,0.28) 100%
  );
  z-index: 100009;
}

[data-vsbs-header].mobile-sheet-header-slot {
  padding: 16px 0 0;
}

[data-vsbs-scroll] {
  width: 100% !important;
  inline-size: 100% !important;
  min-width: 0 !important;
  max-width: 100% !important;
  align-self: stretch !important;
  flex: 1 1 auto !important;
  box-sizing: border-box;
  background: transparent !important;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  touch-action: pan-y;
  -webkit-overflow-scrolling: touch;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 2px;
  }
}

[data-vsbs-content-wrapper] {
  width: 100% !important;
  min-width: 0 !important;
  box-sizing: border-box;
}

[data-vsbs-content] {
  width: 100% !important;
  inline-size: 100% !important;
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box;
}

[data-vsbs-content].sheet-content {
  display: block;
  width: 100% !important;
  inline-size: 100% !important;
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box;
  background: transparent;
  overflow-x: hidden;
  padding: 12px 16px 24px;
  user-select: text;
  -webkit-user-select: text;
}

@media (max-width: 480px) {
  [data-vsbs-content].sheet-content {
    padding: 8px 12px 20px;
  }
}
</style>

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
