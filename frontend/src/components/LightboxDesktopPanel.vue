<script setup lang="ts">
import { ref, computed } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import {
  Loader, Maximize, Minimize, X,
  Calendar, Clock, MessageSquareText, Check, Copy, MessageSquareOff,
  SlidersHorizontal, ChevronDown, Sprout, BrainCircuit, Box, Puzzle, Layers,
  TriangleAlert,
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
  canFullscreen: boolean;
  isFullscreen: boolean;
  copyStatus: Record<string, boolean>;
  copyText: (text: string | undefined, id: string) => Promise<void>;
}>();

const emit = defineEmits<{
  close: [];
  'toggle-fullscreen': [];
}>();

// Collapsible states
const showGenParams = ref(true);
const showResources = ref(false);
const showAdvanced = ref(false);

// Derived flags
const hasGenData = computed(() => hasCoreParams(props.meta?.params));
const hasExtraSettings = computed(() => hasSecondaryParams(props.meta?.params));
const hasModels = computed(() => hasModelData(props.meta));
const hasAdv = computed(() => hasAdvancedData(props.meta));
const extraEntries = computed(() => getSecondaryEntries(props.meta?.params));
const extraParamKeys = computed(() => getExtraParamKeys(props.meta?.params));
</script>

<template>
  <aside v-if="!props.isFullscreen" class="lightbox-right">
    <div v-if="props.isLoading && !props.meta" class="meta-loading">
      <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
      <span>Loading info...</span>
    </div>

    <div v-else-if="!props.meta" class="meta-error">
      <TriangleAlert :size="24" :stroke-width="1.5" />
      <span>No metadata available</span>
    </div>

    <template v-else>
      <header class="meta-header">
        <div class="header-top">
          <h3 id="lightbox-image-name" :title="props.imageName">{{ props.imageName }}</h3>
          <div class="header-actions">
            <button
              v-if="props.canFullscreen"
              class="close-btn-mini fullscreen-btn"
              @click="emit('toggle-fullscreen')"
              :title="props.isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
            >
              <Minimize v-if="props.isFullscreen" :size="18" :stroke-width="1.5" />
              <Maximize v-else :size="18" :stroke-width="1.5" />
            </button>
            <button
              class="close-btn-mini"
              @click="emit('close')"
              title="Close (Escape)"
            >
              <X :size="18" :stroke-width="1.5" />
            </button>
          </div>
        </div>
        <div class="header-meta">
          <span v-if="props.sizeText" class="meta-tag"><Maximize :size="12" :stroke-width="1.5" /> {{ props.sizeText }}</span>
          <span v-if="props.dateText" class="meta-tag"><Calendar :size="12" :stroke-width="1.5" /> {{ props.dateText }}</span>
          <span v-if="props.genTimeText" class="meta-tag"><Clock :size="12" :stroke-width="1.5" /> {{ props.genTimeText }}</span>
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
            <h4><MessageSquareText :size="14" :stroke-width="1.5" /> Prompt</h4>
            <button
              v-if="props.meta?.prompt"
              type="button"
              class="copy-btn"
              @click="props.copyText(props.meta?.prompt, 'prompt')"
            >
              <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
              <Copy v-else :size="14" :stroke-width="1.5" />
            </button>
          </div>
          <div
            v-if="props.meta?.prompt"
            class="prompt-body"
            tabindex="-1"
            v-html="loraHighlighter(props.meta.prompt)"
          ></div>
          <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.prompt }}</p>
        </section>

        <!-- ========== Negative Prompt (core) ========== -->
        <section class="prompt-box negative" :class="{ 'is-empty': !props.meta?.negative_prompt }">
          <div class="section-top">
            <h4><MessageSquareOff :size="14" :stroke-width="1.5" /> Negative</h4>
            <button
              v-if="props.meta?.negative_prompt"
              type="button"
              class="copy-btn"
              @click="props.copyText(props.meta?.negative_prompt, 'neg')"
            >
              <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
              <Copy v-else :size="14" :stroke-width="1.5" />
            </button>
          </div>
          <div
            v-if="props.meta?.negative_prompt"
            class="prompt-body"
            tabindex="-1"
            v-html="loraHighlighter(props.meta.negative_prompt)"
          ></div>
          <p v-else class="empty-text">{{ EMPTY_SECTION_TEXT.negative_prompt }}</p>
        </section>

        <!-- ========== Generation Data (core) ========== -->
        <section class="meta-group" :class="{ 'is-empty': !hasGenData }">
          <div
            class="group-header"
            :class="{ 'is-disabled': !hasGenData }"
            @click="hasGenData && (showGenParams = !showGenParams)"
            tabindex="0"
            role="button"
            :aria-expanded="hasGenData ? showGenParams : undefined"
            aria-controls="gen-data-content"
            @keydown.enter="hasGenData && (showGenParams = !showGenParams)"
            @keydown.space.prevent="hasGenData && (showGenParams = !showGenParams)"
          >
            <h4><SlidersHorizontal :size="14" :stroke-width="1.5" /> Generation Data</h4>
            <ChevronDown
              v-if="hasGenData"
              :size="12"
              :stroke-width="1.5"
              :class="{ rotate: !showGenParams }"
            />
          </div>
          <div id="gen-data-content" v-if="hasGenData" class="group-content" v-show="showGenParams">
            <div class="params-grid">
              <div class="param-pill" v-if="props.meta?.params?.Seed">
                <span class="label">Seed</span>
                <span class="value">{{ props.meta.params.Seed }}</span>
                <button class="icon-btn" @click="props.copyText(String(props.meta.params.Seed), 'seed')" title="Copy Seed">
                  <Check v-if="props.copyStatus['seed']" :size="12" :stroke-width="1.5" style="color: #4ade80" />
                  <Sprout v-else :size="12" :stroke-width="1.5" />
                </button>
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
          <p v-else class="empty-text" style="padding: 12px;">{{ EMPTY_SECTION_TEXT.generation_data }}</p>
        </section>

        <!-- ========== Extra Settings (secondary) ========== -->
        <section v-if="hasExtraSettings" class="meta-group">
          <div class="group-header static">
            <h4><SlidersHorizontal :size="14" :stroke-width="1.5" /> Extra Settings</h4>
          </div>
          <div class="group-content">
            <div class="params-grid">
              <div
                v-for="entry in extraEntries"
                :key="entry.key"
                class="param-pill"
              >
                <span class="label">{{ entry.label }}</span>
                <span class="value">{{ entry.value }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ========== Model & Resources (core) ========== -->
        <section class="meta-group" :class="{ 'is-empty': !hasModels }">
          <div
            class="group-header"
            :class="{ 'is-disabled': !hasModels }"
            @click="hasModels && (showResources = !showResources)"
            tabindex="0"
            role="button"
            :aria-expanded="hasModels ? showResources : undefined"
            aria-controls="model-resources-content"
            @keydown.enter="hasModels && (showResources = !showResources)"
            @keydown.space.prevent="hasModels && (showResources = !showResources)"
          >
            <h4><BrainCircuit :size="14" :stroke-width="1.5" /> Model & Resources</h4>
            <ChevronDown
              v-if="hasModels"
              :size="12"
              :stroke-width="1.5"
              :class="{ rotate: !showResources }"
            />
          </div>
          <div id="model-resources-content" v-if="hasModels" class="group-content" v-show="showResources">
            <div class="resource-list">
              <div class="resource-item" v-if="props.meta?.params?.Model">
                <Box :size="14" :stroke-width="1.5" />
                <div class="res-info">
                  <span class="res-type">Checkpoint</span>
                  <span class="res-name">{{ props.meta.params.Model }}</span>
                </div>
              </div>

              <div class="resource-item" v-for="lora in props.meta?.params?.Lora" :key="lora">
                <Puzzle :size="14" :stroke-width="1.5" />
                <div class="res-info">
                  <span class="res-type">LoRA</span>
                  <span class="res-name">{{ lora }}</span>
                </div>
              </div>

              <!-- Swarm Specific Models List -->
              <div class="resource-item" v-for="m in props.meta?.models" :key="m.name">
                <Layers :size="14" :stroke-width="1.5" />
                <div class="res-info">
                  <span class="res-type">{{ m.param || 'Model' }}</span>
                  <span class="res-name">
                    {{ m.name }}
                    <span v-if="m.hash" class="res-hash" :title="'Hash: ' + m.hash">#{{ m.hash.substring(0, 8) }}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="empty-text" style="padding: 12px;">{{ EMPTY_SECTION_TEXT.model_resources }}</p>
        </section>

        <!-- ========== Advanced (debug) ========== -->
        <section v-if="hasAdv" class="meta-group advanced">
          <div
            class="group-header"
            @click="showAdvanced = !showAdvanced"
            tabindex="0"
            role="button"
            :aria-expanded="showAdvanced"
            aria-controls="advanced-content"
            @keydown.enter="showAdvanced = !showAdvanced"
            @keydown.space.prevent="showAdvanced = !showAdvanced"
          >
            <h4>
              Advanced
              <span class="count-badge">{{ extraParamKeys.length }}</span>
            </h4>
            <ChevronDown
              :size="14"
              :stroke-width="1.5"
              :class="{ rotate: !showAdvanced }"
            />
          </div>
          <div id="advanced-content" class="group-content" v-show="showAdvanced">
            <div class="params-grid">
              <div
                v-for="k in extraParamKeys"
                :key="k"
                class="param-pill"
              >
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
@import '../styles/lightbox-shared';
@import '../styles/lightbox-desktop';

// ── Empty state overrides ─────────────────────────────────────────
.is-empty {
  opacity: 0.55;

  .group-header.is-disabled {
    cursor: default;
    pointer-events: none;

    .chevron,
    :deep(.lucide-chevron-down) {
      display: none;
    }
  }

  .copy-btn {
    display: none;
  }
}

.empty-text {
  color: #888;
  font-size: 13px;
  font-style: italic;
  margin: 0;
  padding: 0 4px;
}

// ── Advanced section ──────────────────────────────────────────────
.meta-group.advanced {
  .count-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 18px;
    padding: 0 6px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.1);
    color: #aaa;
    line-height: 1;
  }
}
</style>
