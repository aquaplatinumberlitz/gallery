<script setup lang="ts">
import { ref } from "vue";
import { loraHighlighter } from "../utils/loraHighlighter";
import type { MetadataResponse } from "../types";
import {
  Loader, Maximize, Minimize, X,
  Calendar, Clock, MessageSquareText, Check, Copy, MessageSquareOff,
  SlidersHorizontal, ChevronDown, Sprout, BrainCircuit, Box, Puzzle, Layers,
  TriangleAlert,
} from "lucide-vue-next";

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

// Collapsible states — managed internally
const showGenParams = ref(true);
const showResources = ref(false);
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
          <span v-if="props.meta?.tool" class="meta-tag tool-tag">{{ props.meta.tool }}</span>
        </div>
      </header>

      <div class="scroll-content">
        <!-- Prompt -->
        <section class="prompt-box" v-if="props.meta?.prompt">
          <div class="section-top">
            <h4><MessageSquareText :size="14" :stroke-width="1.5" /> Prompt</h4>
            <button 
              type="button" 
              class="copy-btn"
              @click="props.copyText(props.meta?.prompt, 'prompt')"
            >
              <Check v-if="props.copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
              <Copy v-else :size="14" :stroke-width="1.5" />
            </button>
          </div>
          <div
            class="prompt-body"
            tabindex="-1"
            v-html="loraHighlighter(props.meta?.prompt || '')"
          ></div>
        </section>

        <!-- Negative Prompt -->
        <section class="prompt-box negative" v-if="props.meta?.negative_prompt">
          <div class="section-top">
            <h4><MessageSquareOff :size="14" :stroke-width="1.5" /> Negative</h4>
            <button 
              type="button" 
              class="copy-btn"
              @click="props.copyText(props.meta?.negative_prompt, 'neg')"
            >
              <Check v-if="props.copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
              <Copy v-else :size="14" :stroke-width="1.5" />
            </button>
          </div>
          <div
            class="prompt-body"
            tabindex="-1"
            v-html="loraHighlighter(props.meta?.negative_prompt || '')"
          ></div>
        </section>

        <!-- Generation Parameters -->
        <section class="meta-group">
          <div 
            class="group-header" 
            @click="showGenParams = !showGenParams"
            tabindex="0"
            @keydown.enter="showGenParams = !showGenParams"
            @keydown.space.prevent="showGenParams = !showGenParams"
          >
            <h4><SlidersHorizontal :size="14" :stroke-width="1.5" /> Generation Data</h4>
            <ChevronDown :size="12" :stroke-width="1.5" :class="{ rotate: !showGenParams }" />
          </div>
          <div class="group-content" v-show="showGenParams">
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
        </section>

        <!-- Models & Resources -->
        <section class="meta-group">
          <div 
            class="group-header" 
            @click="showResources = !showResources"
            tabindex="0"
            @keydown.enter="showResources = !showResources"
            @keydown.space.prevent="showResources = !showResources"
          >
            <h4><BrainCircuit :size="14" :stroke-width="1.5" /> Model & Resources</h4>
            <ChevronDown :size="12" :stroke-width="1.5" :class="{ rotate: !showResources }" />
          </div>
          <div class="group-content" v-show="showResources">
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
        </section>
      </div>
    </template>
  </aside>
</template>

<style scoped lang="scss">
@import '../styles/lightbox-shared';
@import '../styles/lightbox-desktop';
</style>
