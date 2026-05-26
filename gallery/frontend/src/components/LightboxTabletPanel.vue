<script setup lang="ts">
import { ref } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import {
  Loader, X, Calendar, Clock, Maximize,
  Check, Copy, TriangleAlert,
} from "lucide-vue-next";

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
          <!-- Left column: Generation Params -->
          <div class="tablet-col">
            <div class="tablet-section" v-if="props.meta?.params && Object.keys(props.meta.params).length">
              <!-- Seed with copy -->
              <div class="tablet-section-top" v-if="props.meta?.params?.Seed">
                <label class="tablet-label">Seed</label>
                <button class="tablet-copy-btn" @click="props.copyText(String(props.meta.params.Seed), 'seed')" title="Copy seed">
                  <Check v-if="props.copyStatus['seed']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div class="tablet-pills">
                <div class="param-pill" v-if="props.meta?.params?.Seed">
                  <span class="value">{{ props.meta.params.Seed }}</span>
                </div>
                <div class="param-pill" v-if="props.meta?.params?.Steps"><span class="label">Steps</span><span class="value">{{ props.meta.params.Steps }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.CFG"><span class="label">CFG</span><span class="value">{{ props.meta.params.CFG }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.Sampler"><span class="label">Sampler</span><span class="value">{{ props.meta.params.Sampler }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.Scheduler"><span class="label">Scheduler</span><span class="value">{{ props.meta.params.Scheduler }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.AspectRatio"><span class="label">Ratio</span><span class="value">{{ props.meta.params.AspectRatio }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.clip_skip"><span class="label">Clip Skip</span><span class="value">{{ props.meta.params.clip_skip }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.hires_upscale"><span class="label">Hires</span><span class="value">{{ props.meta.params.hires_upscale }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.hires_steps"><span class="label">Hires Steps</span><span class="value">{{ props.meta.params.hires_steps }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.denoising_strength"><span class="label">Denoising</span><span class="value">{{ props.meta.params.denoising_strength }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.vae"><span class="label">VAE</span><span class="value">{{ props.meta.params.vae }}</span></div>
                <div class="param-pill" v-if="props.meta?.width && props.meta?.height"><span class="label">Size</span><span class="value">{{ props.meta.width }} × {{ props.meta.height }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.model_hash"><span class="label">Hash</span><span class="value">{{ props.meta.params.model_hash }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.ensd"><span class="label">ENSD</span><span class="value">{{ props.meta.params.ensd }}</span></div>
                <div class="param-pill" v-if="props.meta?.params?.aesthetic_score"><span class="label">Aesthetic</span><span class="value">{{ props.meta.params.aesthetic_score }}</span></div>
              </div>
            </div>

            <!-- Models section -->
            <div class="tablet-section" v-if="props.meta?.params?.Model || props.meta?.params?.Lora?.length || props.meta?.models?.length">
              <label class="tablet-label">Model & Resources</label>
              <div class="tablet-model-list">
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
            </div>

            <!-- Empty state -->
            <div class="tablet-section" v-if="!props.meta?.params || !Object.keys(props.meta.params).length">
              <p class="tablet-text">No generation parameters available</p>
            </div>
          </div>

          <!-- Right column: Prompts -->
          <div class="tablet-col">
            <div class="tablet-section" v-if="props.meta?.tool">
              <div class="tablet-tool-label">{{ props.meta.tool }}</div>
            </div>

            <div class="tablet-section" v-if="props.meta?.prompt">
              <div class="tablet-section-top">
                <label class="tablet-label">Prompt</label>
                <button class="tablet-copy-btn" @click="props.copyText(props.meta?.prompt, 'prompt')">
                  <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                class="tablet-text"
                v-html="loraHighlighter(props.meta?.prompt || 'No prompt available')"
              ></div>
            </div>

            <div class="tablet-section" v-if="props.meta?.negative_prompt">
              <div class="tablet-section-top">
                <label class="tablet-label negative-label">Negative Prompt</label>
                <button class="tablet-copy-btn" @click="props.copyText(props.meta?.negative_prompt, 'neg')">
                  <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                  <Copy v-else :size="14" :stroke-width="1.5" />
                </button>
              </div>
              <div
                class="tablet-text"
                v-html="loraHighlighter(props.meta.negative_prompt)"
              ></div>
            </div>

            <div class="tablet-section" v-if="!props.meta?.prompt && !props.meta?.negative_prompt">
              <p class="tablet-text">No prompt information available</p>
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
</style>
