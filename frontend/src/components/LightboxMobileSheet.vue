<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, shallowRef, useTemplateRef } from "vue";
import BottomSheet from "@douxcode/vue-spring-bottom-sheet";
import "@douxcode/vue-spring-bottom-sheet/dist/style.css";
import { loraHighlighter } from "../utils/loraHighlighter";
import ExpandableText from "./ExpandableText.vue";
import type { MetadataResponse } from "../types";
import { useHaptic } from "../composables/useHaptic";
import { Loader, TriangleAlert, ChevronDown, ChevronUp } from "lucide-vue-next";
import {
  hasCoreParams,
  hasSecondaryParams,
  hasModelData,
  hasAdvancedData,
  getSecondaryEntries,
  getExtraParamKeys,
  EMPTY_SECTION_TEXT,
} from "../composables/useMetadataSections";
import CopyStateIcon from "@/components/ui/CopyStateIcon.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const { light: hapticLight } = useHaptic();

const props = defineProps<{
  meta: MetadataResponse | null;
  isLoading: boolean;
  copyStatus: Record<string, boolean>;
  copyText: (text: string | undefined, id: string) => Promise<boolean>;
}>();

const emit = defineEmits<{
  close: [];
}>();

type MetadataTab = "prompt" | "params" | "model";

const bottomSheetRef = useTemplateRef<InstanceType<typeof BottomSheet>>("bottomSheet");
const sheetOpen = shallowRef(true);
const sheetExpanded = shallowRef(false);
const activeTab = shallowRef<MetadataTab>("prompt");
const showAdvanced = shallowRef(false);
const promptExpanded = shallowRef(false);
const negPromptExpanded = shallowRef(false);
const textResetKey = shallowRef(0);
const pendingOutsideTap = shallowRef<{
  pointerId: number;
  startX: number;
  startY: number;
  downOutside: boolean;
} | null>(null);
const anyTextExpanded = computed(() => promptExpanded.value || negPromptExpanded.value);
const isSheetVisuallyExpanded = computed(() => sheetExpanded.value || anyTextExpanded.value);
const snapPoints = ["44%", "80%"] as Array<`${number}%`>;
const tabOrder: MetadataTab[] = ["prompt", "params", "model"];
const TAP_THRESHOLD_PX = 10;
const documentPointerOptions = { capture: true, passive: true } as AddEventListenerOptions;

function setTab(tab: MetadataTab) {
  activeTab.value = tab;
  hapticLight();
}

async function focusTab(tab: MetadataTab) {
  setTab(tab);
  await nextTick();
  document.getElementById(`mobile-metadata-tab-${tab}`)?.focus({ preventScroll: true });
}

function onTabKeydown(event: KeyboardEvent, tab: MetadataTab) {
  const currentIndex = tabOrder.indexOf(tab);
  let nextIndex: number | null = null;

  if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabOrder.length;
  if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabOrder.length) % tabOrder.length;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = tabOrder.length - 1;
  if (nextIndex === null) return;

  event.preventDefault();
  event.stopPropagation();
  void focusTab(tabOrder[nextIndex]);
}

function syncSheetSemantics() {
  const sheet = bottomSheetRef.value?.$refs.sheet as HTMLElement | undefined;
  if (!sheet) return;
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-labelledby", "mobile-metadata-title");
  sheet.removeAttribute("aria-modal");
}

function onSheetClosed() {
  sheetOpen.value = false;
  sheetExpanded.value = false;
  pendingOutsideTap.value = null;
  emit("close");
}

function onSheetSnapped(index?: number) {
  sheetExpanded.value = index === 1;
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

function onDocumentPointerDown(e: PointerEvent) {
  if (!sheetOpen.value) return;
  if (!e.isPrimary) {
    pendingOutsideTap.value = null;
    return;
  }

  const sheet = document.querySelector("[data-vsbs-sheet]");
  const downOutside = sheet ? !sheet.contains(e.target as Node) : true;

  pendingOutsideTap.value = {
    pointerId: e.pointerId,
    startX: e.clientX,
    startY: e.clientY,
    downOutside,
  };
}

function onDocumentPointerUp(e: PointerEvent) {
  if (!sheetOpen.value) {
    pendingOutsideTap.value = null;
    return;
  }
  if (!e.isPrimary) {
    pendingOutsideTap.value = null;
    return;
  }
  if (!pendingOutsideTap.value) return;
  if (pendingOutsideTap.value.pointerId !== e.pointerId) return;
  if (!pendingOutsideTap.value.downOutside) {
    pendingOutsideTap.value = null;
    return;
  }

  const dx = e.clientX - pendingOutsideTap.value.startX;
  const dy = e.clientY - pendingOutsideTap.value.startY;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const wasOutside = pendingOutsideTap.value.downOutside;
  pendingOutsideTap.value = null;

  if (dist > TAP_THRESHOLD_PX) return;

  const sheet = document.querySelector("[data-vsbs-sheet]");
  const upOutside = sheet ? !sheet.contains(e.target as Node) : true;

  if (wasOutside && upOutside) {
    emit("close");
  }
}

function onDocumentPointerCancel() {
  pendingOutsideTap.value = null;
}

function onDocumentKeydown(event: KeyboardEvent) {
  const target = event.target instanceof HTMLElement ? event.target : null;
  const targetTab = target?.dataset.metadataTab as MetadataTab | undefined;
  if (targetTab && ["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
    onTabKeydown(event, targetTab);
    return;
  }
  if (!sheetOpen.value || event.key !== "Escape") return;
  event.preventDefault();
  event.stopPropagation();
  emit("close");
}

onMounted(async () => {
  document.addEventListener("pointerdown", onDocumentPointerDown, documentPointerOptions);
  document.addEventListener("pointerup", onDocumentPointerUp, documentPointerOptions);
  document.addEventListener("pointercancel", onDocumentPointerCancel, documentPointerOptions);
  document.addEventListener("keydown", onDocumentKeydown, true);
  await nextTick();
  syncSheetSemantics();
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown, documentPointerOptions);
  document.removeEventListener("pointerup", onDocumentPointerUp, documentPointerOptions);
  document.removeEventListener("pointercancel", onDocumentPointerCancel, documentPointerOptions);
  document.removeEventListener("keydown", onDocumentKeydown, true);
  pendingOutsideTap.value = null;
});

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
    ref="bottomSheet"
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
    @opened="syncSheetSemantics"
    @snapped="onSheetSnapped"
  >
    <template #header>
      <div class="sheet-header" v-if="props.meta" data-vsbs-no-drag>
        <div class="sheet-tabs" role="tablist" aria-label="Image metadata sections">
          <button
            id="mobile-metadata-tab-prompt"
            class="sheet-tab"
            :class="{ active: activeTab === 'prompt' }"
            role="tab"
            :aria-selected="activeTab === 'prompt'"
            aria-controls="mobile-metadata-panel-prompt"
            :tabindex="activeTab === 'prompt' ? 0 : -1"
            data-metadata-tab="prompt"
            data-testid="tab-prompt"
            @click="setTab('prompt')"
            @keydown="onTabKeydown($event, 'prompt')"
          >
            Prompt
          </button>
          <button
            id="mobile-metadata-tab-params"
            class="sheet-tab"
            :class="{ active: activeTab === 'params' }"
            role="tab"
            :aria-selected="activeTab === 'params'"
            aria-controls="mobile-metadata-panel-params"
            :tabindex="activeTab === 'params' ? 0 : -1"
            data-metadata-tab="params"
            data-testid="tab-params"
            @click="setTab('params')"
            @keydown="onTabKeydown($event, 'params')"
          >
            Params
          </button>
          <button
            id="mobile-metadata-tab-model"
            class="sheet-tab"
            :class="{ active: activeTab === 'model' }"
            role="tab"
            :aria-selected="activeTab === 'model'"
            aria-controls="mobile-metadata-panel-model"
            :tabindex="activeTab === 'model' ? 0 : -1"
            data-metadata-tab="model"
            data-testid="tab-model"
            @click="setTab('model')"
            @keydown="onTabKeydown($event, 'model')"
          >
            Model
          </button>
        </div>
        <button
          type="button"
          class="sheet-expand-toggle"
          :aria-label="isSheetVisuallyExpanded ? 'Collapse metadata sheet' : 'Expand metadata sheet'"
          :aria-expanded="isSheetVisuallyExpanded"
          @click="toggleSheetExpanded"
        >
          <ChevronDown v-if="isSheetVisuallyExpanded" :size="22" :stroke-width="2.25" />
          <ChevronUp v-else :size="22" :stroke-width="2.25" />
        </button>
      </div>
    </template>

    <div class="sheet-content-inner">
      <h2 id="mobile-metadata-title" class="sr-only">Image metadata</h2>
      <!-- Loading state -->
      <div v-if="props.isLoading && !props.meta" class="meta-loading">
        <Loader :stroke-width="1.5" class="lucide-spin gallery-icon-nav" />
        <span>Loading info...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="!props.meta" class="meta-error" data-testid="meta-error">
        <TriangleAlert :size="24" :stroke-width="1.5" />
        <span>No metadata available</span>
      </div>

      <template v-else>
        <!-- ========== Tab: Prompt ========== -->
        <div
          v-show="activeTab === 'prompt'"
          id="mobile-metadata-panel-prompt"
          class="sheet-tab-content"
          role="tabpanel"
          aria-labelledby="mobile-metadata-tab-prompt"
          tabindex="0"
        >
          <div class="meta-section" :class="{ 'is-empty': !props.meta?.prompt }">
            <div class="section-top" :class="{ 'metadata-copyable': props.meta?.prompt }">
              <label class="sheet-label">Prompt</label>
              <Tooltip v-if="props.meta?.prompt">
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="inline-copy-button"
                    aria-label="Copy prompt"
                    @click.stop.prevent="props.copyText(props.meta?.prompt, 'prompt')"
                  >
                    <CopyStateIcon
                      :copied="props.copyStatus['prompt']"
                      class="copy-icon-stack inline-copy-icon"
                      check-test-id="copy-prompt-check"
                    />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Copy prompt</TooltipContent>
              </Tooltip>
            </div>
            <div v-if="props.meta?.prompt" class="sheet-text">
              <ExpandableText
                :key="`prompt-${textResetKey}`"
                :collapsed-lines="5"
                :text="props.meta.prompt"
                :expanded="promptExpanded"
                @expanded-change="onPromptExpandedChange"
              >
                <span v-html="loraHighlighter(props.meta.prompt)" />
              </ExpandableText>
            </div>
            <p v-else class="empty-text">
              {{ EMPTY_SECTION_TEXT.prompt }}
            </p>
          </div>
          <div class="meta-section" :class="{ 'is-empty': !props.meta?.negative_prompt }">
            <div class="section-top" :class="{ 'metadata-copyable': props.meta?.negative_prompt }">
              <label class="sheet-label negative-label">Negative Prompt</label>
              <Tooltip v-if="props.meta?.negative_prompt">
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="inline-copy-button"
                    aria-label="Copy negative prompt"
                    @click.stop.prevent="props.copyText(props.meta?.negative_prompt, 'neg')"
                  >
                    <CopyStateIcon :copied="props.copyStatus['neg']" class="copy-icon-stack inline-copy-icon" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Copy negative prompt</TooltipContent>
              </Tooltip>
            </div>
            <div v-if="props.meta?.negative_prompt" class="sheet-text">
              <ExpandableText
                :key="`neg-prompt-${textResetKey}`"
                :collapsed-lines="5"
                :text="props.meta.negative_prompt"
                :expanded="negPromptExpanded"
                @expanded-change="onNegPromptExpandedChange"
              >
                <span v-html="loraHighlighter(props.meta.negative_prompt)" />
              </ExpandableText>
            </div>
            <p v-else class="empty-text">
              {{ EMPTY_SECTION_TEXT.negative_prompt }}
            </p>
          </div>
        </div>

        <!-- ========== Tab: Params ========== -->
        <div
          v-show="activeTab === 'params'"
          id="mobile-metadata-panel-params"
          class="sheet-tab-content"
          role="tabpanel"
          aria-labelledby="mobile-metadata-tab-params"
          tabindex="0"
        >
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
              <Tooltip v-if="props.meta?.params?.Seed">
                <TooltipTrigger as-child>
                  <div
                    class="param-pill seed-row metadata-copyable"
                    data-testid="seed-row"
                    role="button"
                    tabindex="0"
                    @click.stop.prevent="props.copyText(String(props.meta.params.Seed), 'seed')"
                    @keydown.enter.stop.prevent="props.copyText(String(props.meta.params.Seed), 'seed')"
                    @keydown.space.stop.prevent="props.copyText(String(props.meta.params.Seed), 'seed')"
                  >
                    <span class="label">Seed</span>
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
        <div
          v-show="activeTab === 'model'"
          id="mobile-metadata-panel-model"
          class="sheet-tab-content"
          role="tabpanel"
          aria-labelledby="mobile-metadata-tab-model"
          tabindex="0"
        >
          <div class="meta-section" :class="{ 'is-empty': !hasModels }">
            <label v-if="props.meta?.params?.Model" class="sheet-label">Checkpoint</label>
            <p v-if="props.meta?.params?.Model" class="sheet-text">
              {{ props.meta.params.Model }}
            </p>

            <label v-if="props.meta?.params?.Lora?.length" class="sheet-label" style="margin-top: 12px">LoRAs</label>
            <p class="sheet-text" v-for="(lora, idx) in props.meta?.params?.Lora" :key="idx">
              {{ lora }}
            </p>

            <label v-if="props.meta?.models?.length" class="sheet-label" style="margin-top: 12px">{{
              props.meta.models.length === 1 ? "Model" : "Models"
            }}</label>
            <div v-for="m in props.meta?.models" :key="m.name">
              <p class="sheet-text">
                {{ m.name }}
                <span v-if="m.hash" class="res-hash">#{{ m.hash.substring(0, 8) }}</span>
              </p>
            </div>

            <p v-if="!hasModels" class="empty-text">
              {{ EMPTY_SECTION_TEXT.model_resources }}
            </p>
          </div>
        </div>
      </template>
    </div>
  </BottomSheet>
</template>

<style lang="scss">
/* VSBS overrides must be global because BottomSheet teleports its DOM to body. */
[data-vsbs-sheet] {
  --vsbs-backdrop-bg: linear-gradient(
    to bottom,
    rgba(0, 0, 0, 0.04) 0%,
    rgba(0, 0, 0, 0.12) 50%,
    rgba(0, 0, 0, 0.28) 100%
  );
  --vsbs-background: var(--gallery-lightbox-bg, #1a1a1a);
  --vsbs-border-radius: 16px;
  --vsbs-border-color: var(--gallery-lightbox-border, rgba(255, 255, 255, 0.1));
  --vsbs-outer-border-color: transparent;
  --vsbs-padding-x: 0px;
  --vsbs-handle-background: rgba(255, 255, 255, 0.3);
  --vsbs-max-width: 100vw;
  width: 100vw;
  inline-size: 100vw;
  min-width: 0;
  max-width: 100vw;
  box-sizing: border-box;
  background: var(--gallery-lightbox-bg, #1a1a1a);
  color: #e5e7eb;
  z-index: var(--gallery-z-lightbox-panel, 100010);
}

[data-vsbs-backdrop] {
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.04) 0%, rgba(0, 0, 0, 0.12) 50%, rgba(0, 0, 0, 0.28) 100%);
  z-index: calc(var(--gallery-z-lightbox-panel, 100010) - 1);
}

[data-vsbs-header].mobile-sheet-header-slot {
  padding: 16px 0 0;
}

[data-vsbs-scroll] {
  --gallery-scrollbar-size: 4px;
  --gallery-scrollbar-thumb: var(--gallery-scrollbar-on-dark-thumb);
  --gallery-scrollbar-thumb-hover: var(--gallery-scrollbar-on-dark-thumb-hover);

  width: 100%;
  inline-size: 100%;
  min-width: 0;
  max-width: 100%;
  align-self: stretch;
  flex: 1 1 auto;
  box-sizing: border-box;
  background: transparent;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  touch-action: pan-y;
  -webkit-overflow-scrolling: touch;
}

[data-vsbs-content] {
  width: 100%;
  inline-size: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

[data-vsbs-content].sheet-content.sheet-content {
  display: block;
  width: 100%;
  inline-size: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  background: transparent;
  overflow-x: hidden;
  padding: 12px 16px max(24px, calc(env(safe-area-inset-bottom) + 16px));
  user-select: text;
  -webkit-user-select: text;
}

@media (max-width: 480px) {
  [data-vsbs-content].sheet-content.sheet-content {
    padding: 8px 12px max(20px, calc(env(safe-area-inset-bottom) + 12px));
  }
}
</style>

<style scoped lang="scss">
@import "../styles/lightbox-shared";
@import "../styles/lightbox-mobile";

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
