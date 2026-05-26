<script setup lang="ts">
import { ref } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import {
  Loader, Check, Copy, TriangleAlert,
} from "lucide-vue-next";

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
  if (delta > 50) closeSheet();     // swipe down >50px = close
  if (delta < -50) sheetExpanded.value = true; // swipe up >50px = expand
}

function onSheetTouchEnd() { /* no-op */ }
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
      <div class="sheet-handle-wrapper" @click="toggleExpanded">
        <div class="sheet-handle" />
      </div>
      
      <div class="sheet-tabs" v-if="props.meta">
        <button class="sheet-tab" :class="{ active: activeTab === 'prompt' }" @click="activeTab='prompt'">
          Prompt
        </button>
        <button class="sheet-tab" :class="{ active: activeTab === 'params' }" @click="activeTab='params'">
          Params
        </button>
        <button class="sheet-tab" :class="{ active: activeTab === 'model' }" @click="activeTab='model'">
          Model
        </button>
      </div>
      
      <div class="sheet-content">
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
          <!-- Tab: Prompt -->
          <div v-show="activeTab === 'prompt'" class="sheet-tab-content">
            <div class="meta-section">
              <div class="section-top">
                <label class="sheet-label">Prompt</label>
                <button class="copy-btn" @click="props.copyText(props.meta?.prompt || '', 'prompt')">
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                class="sheet-text"
                v-html="loraHighlighter(props.meta?.prompt || 'No prompt available')"
              ></div>
            </div>
            <div class="meta-section" v-if="props.meta?.negative_prompt">
              <div class="section-top">
                <label class="sheet-label negative-label">Negative Prompt</label>
                <button class="copy-btn" @click="props.copyText(props.meta?.negative_prompt || '', 'neg')">
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                class="sheet-text"
                v-html="loraHighlighter(props.meta.negative_prompt)"
              ></div>
            </div>
          </div>
          
          <!-- Tab: Params -->
          <div v-show="activeTab === 'params'" class="sheet-tab-content">
            <!-- Tool label -->
            <div class="meta-section" v-if="props.meta?.tool">
              <div class="tool-label">{{ props.meta.tool }}</div>
            </div>

            <!-- Generation params grid -->
            <div class="meta-section" v-if="props.meta?.params && Object.keys(props.meta.params).length">
              <div class="params-grid">
                <!-- Seed first with copy button -->
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
                <div class="param-pill" v-if="props.meta?.params?.Model"><span class="label">Model</span><span class="value">{{ props.meta.params.Model }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.model_hash"><span class="label">Hash</span><span class="value">{{ props.meta.params.model_hash }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.clip_skip"><span class="label">Clip Skip</span><span class="value">{{ props.meta.params.clip_skip }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.hires_upscale"><span class="label">Hires</span><span class="value">{{ props.meta.params.hires_upscale }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.hires_steps"><span class="label">Hires Steps</span><span class="value">{{ props.meta.params.hires_steps }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.denoising_strength"><span class="label">Denoising</span><span class="value">{{ props.meta.params.denoising_strength }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.vae"><span class="label">VAE</span><span class="value">{{ props.meta.params.vae }}</span></div>
                <div class="param-pill" v-if="props.meta?.width && props.meta?.height"><span class="label">Size</span><span class="value">{{ props.meta.width }} × {{ props.meta.height }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.ensd"><span class="label">ENSD</span><span class="value">{{ props.meta.params.ensd }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.aesthetic_score"><span class="label">Aesthetic</span><span class="value">{{ props.meta.params.aesthetic_score }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.AspectRatio"><span class="label">Ratio</span><span class="value">{{ props.meta.params.AspectRatio }}</span></div>
              </div>
            </div>
            <div class="meta-section" v-else>
              <p class="sheet-text">No generation parameters available</p>
            </div>
          </div>
          
          <!-- Tab: Model -->
          <div v-show="activeTab === 'model'" class="sheet-tab-content">
            <div class="meta-section" v-if="props.meta?.params?.Model">
              <label class="sheet-label">Checkpoint</label>
              <p class="sheet-text">{{ props.meta.params.Model }}</p>
            </div>
            <div class="meta-section" v-if="props.meta?.params?.Lora?.length">
              <label class="sheet-label">LoRAs</label>
              <p class="sheet-text" v-for="(lora, idx) in props.meta.params.Lora" :key="idx">{{ lora }}</p>
            </div>
            <div class="meta-section" v-if="props.meta?.models?.length">
              <label class="sheet-label">{{ props.meta.models.length === 1 ? 'Model' : 'Models' }}</label>
              <div v-for="m in props.meta.models" :key="m.name">
                <p class="sheet-text">
                  {{ m.name }}
                  <span v-if="m.hash" class="res-hash">#{{ m.hash.substring(0, 8) }}</span>
                </p>
              </div>
            </div>
            <div class="meta-section" v-if="!props.meta?.params?.Model && !props.meta?.models?.length">
              <p class="sheet-text">No model information available</p>
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
</style>
