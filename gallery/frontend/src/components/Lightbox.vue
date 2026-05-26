<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useClipboard } from "../composables/useClipboard";
import { loraHighlighter } from "../utils/loraHighlighter";
import { getImageUrl, getThumbnailUrl } from "../services/api";
import {
  Loader, Image, ChevronLeft, ChevronRight, Minimize, Maximize, X,
  Calendar, Clock, MessageSquareText, Check, Copy, MessageSquareOff,
  SlidersHorizontal, ChevronDown, Sprout, BrainCircuit, Box, Puzzle, Layers,
  TriangleAlert, Info, ArrowUp, ArrowDown, CheckCircle, Search,
  Settings, Folder, FolderOpen, RotateCcw
} from "lucide-vue-next";

// @ts-expect-error: used via :is dynamic component binding
const _icons = { Info, ArrowUp, ArrowDown, CheckCircle, Search, Settings, Folder, FolderOpen, RotateCcw }

const lightbox = useLightboxStore();
const { copyStatus, copyText } = useClipboard();

// Refs for focus management
const lightboxRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);

// Focus trap
const focusTrap = useFocusTrap(lightboxRef, {
  initialFocus: closeButtonRef,
  returnFocus: true,
});

const show = computed(() => lightbox.isOpen);
const isLoading = computed(() => lightbox.isLoading);
const meta = computed(() => lightbox.metadata);
const isFullscreen = ref(false);

// Collapsible states
const showGenParams = ref(true);
const showResources = ref(false);

const sizeText = computed(() => {
  if (lightbox.width && lightbox.height) return `${lightbox.width} x ${lightbox.height}`;
  return "";
});

const dateText = computed(() => {
  if (meta.value?.date) return meta.value.date;
  return "";
});

const genTimeText = computed(() => {
  if (meta.value?.generation_time) return meta.value.generation_time;
  return "";
});

const hasPrev = computed(() => lightbox.currentIndex > 0);
const hasNext = computed(() => lightbox.currentIndex < lightbox.galleryItems.length - 1);
const imageError = ref(false);
const manualOriginal = ref(false);
const fallbackOriginal = ref(false);
const useOriginal = computed(() => manualOriginal.value || fallbackOriginal.value);
const isAnimated = computed(() => {
  const name = lightbox.itemName || lightbox.metadata?.name || "";
  const ext = name.split(".").pop()?.toLowerCase();
  return ext === "gif" || ext === "webp";
});

// Mouse wheel navigation
let lastWheelTime = 0;
const handleWheel = (e: WheelEvent) => {
  const now = Date.now();
  if (now - lastWheelTime < 60) return; // Throttle
  lastWheelTime = now;

  if (e.deltaY > 0) {
    handleNext();
  } else if (e.deltaY < 0) {
    handlePrev();
  }
};

// Navigation with announcements
const handlePrev = () => {
  if (hasPrev.value) {
    lightbox.prev();
  }
};

const handleNext = () => {
  if (hasNext.value) {
    lightbox.next();
  }
};

const handleClose = () => {
  if (isFullscreen.value) {
    exitFullscreen();
  }
  lightbox.close();
};

// Keyboard navigation
const handleKeydown = (e: KeyboardEvent) => {
  if (!show.value) return;
  
  // Ignore if focus is on an input
  const target = e.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
  
  switch (e.key) {
    case "Escape":
      handleClose();
      break;
    case "ArrowLeft":
      handlePrev();
      break;
    case "ArrowRight":
      handleNext();
      break;
  }
};

// Activate focus trap when lightbox opens
watch(show, (isOpen) => {
  if (isOpen) {
    focusTrap.activate();
  } else {
    focusTrap.deactivate();
    if (document.fullscreenElement) {
      exitFullscreen();
    }
  }
});

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  // Reactive mobile detection
  mobileMql.value = window.matchMedia("(max-width: 640px)");
  handleMobileChange(mobileMql.value);
  mobileMql.value.addEventListener("change", handleMobileChange);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  mobileMql.value?.removeEventListener("change", handleMobileChange);
  focusTrap.deactivate();
});

watch(
  () => lightbox.itemPath,
  () => {
    imageError.value = false;
    manualOriginal.value = false;
    fallbackOriginal.value = false;
  },
);

const handleImageError = () => {
  // Nếu đang dùng ảnh display, thử fallback 1 lần sang ảnh gốc
  if (!useOriginal.value && lightbox.itemPath) {
    fallbackOriginal.value = true;
    return;
  }
  imageError.value = true;
};

const displayUrl = computed(() => {
  if (!lightbox.itemPath) return "";
  const forceOriginal = isAnimated.value || useOriginal.value;
  return forceOriginal
    ? getImageUrl(lightbox.itemPath)
    : getThumbnailUrl(lightbox.itemPath, 2048); // display size ~2K
});

// Fullscreen
const canFullscreen = computed(() => typeof document !== "undefined" && document.fullscreenEnabled !== false);

const handleFullscreenChange = () => {
  const active = !!document.fullscreenElement;
  isFullscreen.value = active;
  manualOriginal.value = active; // fullscreen ưu tiên ảnh gốc
};

const enterFullscreen = async () => {
  if (!canFullscreen.value || !lightboxRef.value || isFullscreen.value) return;
  try {
    await lightboxRef.value.requestFullscreen();
  } catch (e) {
    console.error("Failed to enter fullscreen", e);
  }
};

const exitFullscreen = async () => {
  if (!document.fullscreenElement) return;
  try {
    await document.exitFullscreen();
  } catch (e) {
    console.error("Failed to exit fullscreen", e);
  }
};

// Mobile bottom sheet — reactive via matchMedia
const isMobile = ref(false);
const mobileMql = ref<MediaQueryList | null>(null);

function handleMobileChange(e: MediaQueryListEvent | MediaQueryList) {
  isMobile.value = e.matches;
}
const showSheet = ref(false);
const sheetExpanded = ref(false);
const activeTab = ref('prompt');
const sheetStartY = ref(0);

function toggleSheet() {
  showSheet.value = !showSheet.value;
  if (!showSheet.value) sheetExpanded.value = false;
}

function closeSheet() {
  showSheet.value = false;
  sheetExpanded.value = false;
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
  <Teleport to="body">
    <Transition name="fade">
      <div 
        v-if="show" 
        ref="lightboxRef"
        class="lightbox-overlay"
        @click.self="handleClose"
      >
        <div class="lightbox-shell">
          <!-- Left: Image Area -->
          <div 
            class="lightbox-left"
            @click.self="handleClose"
            @wheel.prevent="handleWheel"
          >
            <div v-if="isLoading" class="image-loading">
              <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
            </div>
            
            <img 
              v-if="lightbox.itemPath && !imageError" 
              :src="displayUrl" 
              class="hero-image" 
              :class="{ loading: isLoading }"
              @error="handleImageError"
              :alt="lightbox.itemName || 'Gallery image'"
            />
            <div v-else class="hero-placeholder">
              <Image :size="24" :stroke-width="1.5" />
              <p>Unable to display this image.</p>
            </div>

            <!-- Navigation Buttons -->
            <button 
              class="nav-btn prev" 
              :disabled="!hasPrev"
              @click.stop="handlePrev" 
              :title="hasPrev ? 'Previous (Left Arrow)' : 'No previous image'"
            >
              <ChevronLeft :size="24" :stroke-width="1.5" />
            </button>
            <button 
              class="nav-btn next" 
              :disabled="!hasNext"
              @click.stop="handleNext" 
              :title="hasNext ? 'Next (Right Arrow)' : 'No next image'"
            >
              <ChevronRight :size="24" :stroke-width="1.5" />
            </button>
            
            <!-- Image counter for screen readers -->
            <div class="sr-only">
              Image {{ lightbox.currentIndex + 1 }} of {{ lightbox.galleryItems.length }}
            </div>

            <!-- Mobile info button -->
            <button class="mobile-info-btn" v-if="isMobile" @click.stop="toggleSheet" title="Image Info">
              <Info :size="20" :stroke-width="1.5" />
            </button>
          </div>

          <!-- Right: Metadata Panel -->
          <aside v-if="!isFullscreen" class="lightbox-right">
            <div v-if="isLoading && !meta" class="meta-loading">
              <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
              <span>Loading info...</span>
            </div>
            
            <div v-else-if="!meta" class="meta-error">
              <TriangleAlert :size="24" :stroke-width="1.5" />
              <span>No metadata available</span>
            </div>

            <template v-else>
              <header class="meta-header">
                <div class="header-top">
                  <h3 id="lightbox-image-name" :title="lightbox.itemName">{{ lightbox.itemName }}</h3>
                  <div class="header-actions">
                    <button 
                      v-if="canFullscreen"
                      class="close-btn-mini fullscreen-btn" 
                      @click="isFullscreen ? exitFullscreen() : enterFullscreen()"
                      :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
                    >
                      <Minimize v-if="isFullscreen" :size="18" :stroke-width="1.5" />
                      <Maximize v-else :size="18" :stroke-width="1.5" />
                    </button>
                    <button 
                      ref="closeButtonRef"
                      class="close-btn-mini" 
                      @click="handleClose"
                      title="Close (Escape)"
                    >
                      <X :size="18" :stroke-width="1.5" />
                    </button>
                  </div>
                </div>
                <div class="header-meta">
                  <span v-if="sizeText" class="meta-tag"><Maximize :size="12" :stroke-width="1.5" /> {{ sizeText }}</span>
                  <span v-if="dateText" class="meta-tag"><Calendar :size="12" :stroke-width="1.5" /> {{ dateText }}</span>
                  <span v-if="genTimeText" class="meta-tag"><Clock :size="12" :stroke-width="1.5" /> {{ genTimeText }}</span>
                  <span v-if="meta?.tool" class="meta-tag tool-tag">{{ meta.tool }}</span>
                </div>
              </header>

              <div class="scroll-content">
                <!-- Prompt -->
                <section class="prompt-box" v-if="meta?.prompt">
                  <div class="section-top">
                    <h4><MessageSquareText :size="14" :stroke-width="1.5" /> Prompt</h4>
                    <button 
                      type="button" 
                      class="copy-btn"
                      @click="copyText(meta?.prompt, 'prompt')"
                    >
                      <Check v-if="copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                      <Copy v-else :size="14" :stroke-width="1.5" />
                    </button>
                  </div>
                  <div
                    class="prompt-body"
                    tabindex="-1"
                    v-html="loraHighlighter(meta?.prompt || '')"
                  ></div>
                </section>

                <!-- Negative Prompt -->
                <section class="prompt-box negative" v-if="meta?.negative_prompt">
                  <div class="section-top">
                    <h4><MessageSquareOff :size="14" :stroke-width="1.5" /> Negative</h4>
                    <button 
                      type="button" 
                      class="copy-btn"
                      @click="copyText(meta?.negative_prompt, 'neg')"
                    >
                      <Check v-if="copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                      <Copy v-else :size="14" :stroke-width="1.5" />
                    </button>
                  </div>
                  <div
                    class="prompt-body"
                    tabindex="-1"
                    v-html="loraHighlighter(meta?.negative_prompt || '')"
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
                      <div class="param-pill" v-if="meta?.params?.Seed">
                        <span class="label">Seed</span>
                        <span class="value">{{ meta.params.Seed }}</span>
                        <button class="icon-btn" @click="copyText(String(meta.params.Seed), 'seed')" title="Copy Seed">
                          <Check v-if="copyStatus['seed']" :size="12" :stroke-width="1.5" style="color: #4ade80" />
                          <Sprout v-else :size="12" :stroke-width="1.5" />
                        </button>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.Steps">
                        <span class="label">Steps</span>
                        <span class="value">{{ meta.params.Steps }}</span>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.CFG">
                        <span class="label">CFG</span>
                        <span class="value">{{ meta.params.CFG }}</span>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.Sampler">
                        <span class="label">Sampler</span>
                        <span class="value">{{ meta.params.Sampler }}</span>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.Scheduler">
                        <span class="label">Scheduler</span>
                        <span class="value">{{ meta.params.Scheduler }}</span>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.AspectRatio">
                        <span class="label">Ratio</span>
                        <span class="value">{{ meta.params.AspectRatio }}</span>
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
                      <div class="resource-item" v-if="meta?.params?.Model">
                        <Box :size="14" :stroke-width="1.5" />
                        <div class="res-info">
                          <span class="res-type">Checkpoint</span>
                          <span class="res-name">{{ meta.params.Model }}</span>
                        </div>
                      </div>
                      
                      <div class="resource-item" v-for="lora in meta?.params?.Lora" :key="lora">
                        <Puzzle :size="14" :stroke-width="1.5" />
                        <div class="res-info">
                          <span class="res-type">LoRA</span>
                          <span class="res-name">{{ lora }}</span>
                        </div>
                      </div>

                      <!-- Swarm Specific Models List -->
                      <div class="resource-item" v-for="m in meta?.models" :key="m.name">
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

          <!-- Fullscreen overlay controls -->
          <div v-else class="fs-controls">
            <button 
              class="fs-btn" 
              @click="exitFullscreen"
              title="Exit fullscreen"
            >
              <Minimize :size="20" :stroke-width="1.5" />
            </button>
            <button 
              class="fs-btn" 
              @click="handleClose"
              title="Close"
            >
              <X :size="20" :stroke-width="1.5" />
            </button>
          </div>
        </div>

        <!-- Mobile bottom sheet for metadata -->
        <div class="mobile-sheet" v-if="isMobile && showSheet && !isFullscreen" @click.self="closeSheet">
          <div class="sheet-backdrop" @click.self="closeSheet" />
          <div 
            class="sheet-panel"
            :class="{ 'sheet-expanded': sheetExpanded }"
            @touchstart="onSheetTouchStart"
            @touchmove="onSheetTouchMove"
            @touchend="onSheetTouchEnd"
          >
            <div class="sheet-handle-wrapper">
              <div class="sheet-handle" />
            </div>
            
            <div class="sheet-tabs" v-if="meta">
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
              <div v-if="isLoading && !meta" class="meta-loading">
                <Loader :size="24" :stroke-width="1.5" class="lucide-spin" />
                <span>Loading info...</span>
              </div>
              
              <!-- Error state -->
              <div v-else-if="!meta" class="meta-error">
                <TriangleAlert :size="24" :stroke-width="1.5" />
                <span>No metadata available</span>
              </div>
              
              <template v-else>
                <!-- Tab: Prompt -->
                <div v-show="activeTab === 'prompt'" class="sheet-tab-content">
                  <div class="meta-section">
                    <div class="section-top">
                      <label class="sheet-label">Prompt</label>
                      <button class="copy-btn" @click="copyText(meta?.prompt || '', 'prompt')">
                        <Check v-if="copyStatus['prompt']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                        <Copy v-else :size="14" :stroke-width="1.5" />
                      </button>
                    </div>
                    <div
                      class="sheet-text"
                      v-html="loraHighlighter(meta?.prompt || 'No prompt available')"
                    ></div>
                  </div>
                  <div class="meta-section" v-if="meta?.negative_prompt">
                    <div class="section-top">
                      <label class="sheet-label negative-label">Negative Prompt</label>
                      <button class="copy-btn" @click="copyText(meta?.negative_prompt || '', 'neg')">
                        <Check v-if="copyStatus['neg']" :size="14" :stroke-width="1.5" style="color: #4ade80" />
                        <Copy v-else :size="14" :stroke-width="1.5" />
                      </button>
                    </div>
                    <div
                      class="sheet-text"
                      v-html="loraHighlighter(meta.negative_prompt)"
                    ></div>
                  </div>
                </div>
                
                <!-- Tab: Params -->
                <div v-show="activeTab === 'params'" class="sheet-tab-content">
                  <!-- Tool label -->
                  <div class="meta-section" v-if="meta?.tool">
                    <div class="tool-label">{{ meta.tool }}</div>
                  </div>

                  <!-- Generation params grid -->
                  <div class="meta-section" v-if="meta?.params && Object.keys(meta.params).length">
                    <div class="params-grid">
                      <!-- Seed first with copy button -->
                      <div class="param-pill seed-row" v-if="meta?.params?.Seed">
                        <span class="label">Seed</span>
                        <span class="value">{{ meta.params.Seed }}</span>
                        <button class="copy-btn-mini" @click="copyText(String(meta.params.Seed), 'seed')" title="Copy seed">
                          <Check v-if="copyStatus['seed']" :size="12" :stroke-width="1.5" style="color: #4ade80" />
                          <Copy v-else :size="12" :stroke-width="1.5" />
                        </button>
                      </div>
                      <div class="param-pill" v-if="meta?.params?.Steps"><span class="label">Steps</span><span class="value">{{ meta.params.Steps }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.CFG"><span class="label">CFG</span><span class="value">{{ meta.params.CFG }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.Sampler"><span class="label">Sampler</span><span class="value">{{ meta.params.Sampler }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.Scheduler"><span class="label">Scheduler</span><span class="value">{{ meta.params.Scheduler }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.Model"><span class="label">Model</span><span class="value">{{ meta.params.Model }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.model_hash"><span class="label">Hash</span><span class="value">{{ meta.params.model_hash }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.clip_skip"><span class="label">Clip Skip</span><span class="value">{{ meta.params.clip_skip }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.hires_upscale"><span class="label">Hires</span><span class="value">{{ meta.params.hires_upscale }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.hires_steps"><span class="label">Hires Steps</span><span class="value">{{ meta.params.hires_steps }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.denoising_strength"><span class="label">Denoising</span><span class="value">{{ meta.params.denoising_strength }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.vae"><span class="label">VAE</span><span class="value">{{ meta.params.vae }}</span></div>
                      <div class="param-pill" v-if="meta?.width && meta?.height"><span class="label">Size</span><span class="value">{{ meta.width }} × {{ meta.height }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.ensd"><span class="label">ENSD</span><span class="value">{{ meta.params.ensd }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.aesthetic_score"><span class="label">Aesthetic</span><span class="value">{{ meta.params.aesthetic_score }}</span></div>
                      <div class="param-pill" v-if="meta?.params?.AspectRatio"><span class="label">Ratio</span><span class="value">{{ meta.params.AspectRatio }}</span></div>
                    </div>
                  </div>
                  <div class="meta-section" v-else>
                    <p class="sheet-text">No generation parameters available</p>
                  </div>
                </div>
                
                <!-- Tab: Model -->
                <div v-show="activeTab === 'model'" class="sheet-tab-content">
                  <div class="meta-section" v-if="meta?.params?.Model">
                    <label class="sheet-label">Checkpoint</label>
                    <p class="sheet-text">{{ meta.params.Model }}</p>
                  </div>
                  <div class="meta-section" v-if="meta?.params?.Lora?.length">
                    <label class="sheet-label">LoRAs</label>
                    <p class="sheet-text" v-for="(lora, idx) in meta.params.Lora" :key="idx">{{ lora }}</p>
                  </div>
                  <div class="meta-section" v-if="meta?.models?.length">
                    <label class="sheet-label">{{ meta.models.length === 1 ? 'Model' : 'Models' }}</label>
                    <div v-for="m in meta.models" :key="m.name">
                      <p class="sheet-text">
                        {{ m.name }}
                        <span v-if="m.hash" class="res-hash">#{{ m.hash.substring(0, 8) }}</span>
                      </p>
                    </div>
                  </div>
                  <div class="meta-section" v-if="!meta?.params?.Model && !meta?.models?.length">
                    <p class="sheet-text">No model information available</p>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
// ============================================
// Lightbox SCSS — modular partials
// Shared/Desktop/Mobile extracted to _lightbox-*.scss
// ============================================
@import '../styles/lightbox-shared';
@import '../styles/lightbox-desktop';
@import '../styles/lightbox-mobile';

// === Component-unique styles (image viewer, navigation, fullscreen) ===

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.lightbox-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.95);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-shell {
  width: 100%;
  height: 100%;
  display: flex;
  overflow: hidden;
}

.fs-controls {
  position: absolute;
  top: 20px;
  right: 20px;
  display: inline-flex;
  gap: 8px;
  z-index: 10;
}

.fs-btn {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.fs-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.5);
}

.fs-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Left Side: Image & Nav */
.lightbox-left {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%);
  user-select: none;
}

.hero-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: opacity 0.2s;
  
  &.loading {
    opacity: 0.5;
  }
}

.hero-placeholder {
  display: grid;
  place-items: center;
  gap: 10px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 24px;
  text-align: center;
}

.hero-placeholder p {
  margin: 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.image-loading {
  position: absolute;
  font-size: 48px;
  color: rgba(255, 255, 255, 0.2);
}

.nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #f5f7fb;
  width: 48px;
  height: 80px;
  font-size: 24px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  backdrop-filter: blur(6px);
  opacity: 0; /* Hidden by default */

  &:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.35);
    color: #ff6b35; /* pastel orange từ palette */
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    transform: translateY(-50%) scale(1.02);
  }

  &.prev { left: 20px; }
  &.next { right: 20px; }

  &:disabled {
    opacity: 0;
    pointer-events: none;
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
    opacity: 1;
  }
}

.lightbox-left:hover .nav-btn:not(:disabled) {
  opacity: 1;
}

// =============================================
// RESPONSIVE BREAKPOINTS
// =============================================

/* Tablet: narrow metadata panel */
@media (max-width: 1024px) {
  .lightbox-right {
    width: clamp(280px, 34vw, 380px);
    min-width: 280px;
  }
}

/* Phone: bottom sheet replaces sidebar */
@media (max-width: 640px) {
  .lightbox-shell {
    flex-direction: column;
  }

  .lightbox-left {
    flex: 1;
    min-height: 0;
  }

  .nav-btn {
    opacity: 0.8 !important;
  }

  .nav-btn.prev { left: 8px; }
  .nav-btn.next { right: 8px; }

  .nav-btn:disabled {
    opacity: 0.2 !important;
    pointer-events: none;
  }

  /* Hide desktop sidebar on mobile — replaced by bottom sheet */
  .lightbox-right {
    display: none;
  }

  /* Show mobile info button */
  .mobile-info-btn {
    display: flex;
  }

  /* Fullscreen: show sidebar instead of bottom sheet */
  .lightbox-shell:fullscreen .lightbox-right,
  .lightbox-shell:-webkit-full-screen .lightbox-right {
    display: flex;
  }
}

/* Small phone: compact metadata */
@media (max-width: 480px) {
  .nav-btn {
    width: 40px;
    height: 56px;
    font-size: 18px;
  }

  .meta-header {
    padding: 8px 12px;
  }

  .scroll-content {
    padding: 8px 12px;
    gap: 8px;
  }

  .params-grid {
    gap: 4px;
  }

  .param-pill {
    padding: 3px 6px;
    font-size: 11px;
  }
}

/* Touch devices: bigger nav tap targets */
@media (pointer: coarse) {
  .nav-btn {
    min-width: 44px;
    min-height: 44px;
  }

  .nav-btn.prev { left: 4px; }
  .nav-btn.next { right: 4px; }
}
</style>
