<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useLightboxStore } from "../stores/lightbox";
import { useFocusTrap } from "../composables/useFocusTrap";
import { useToast } from "../composables/useToast";
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
const toast = useToast();

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

const escapeHtml = (unsafe: string) => {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

const loraHighlighter = (text: string) => {
  if (!text) return "";

  // Split string by <lora:...> tokens to avoid per-char replace on long prompts
  const regex = /<lora:([^:>]+)(?::([^>]+))?>/gi;
  let lastIndex = 0;
  let out = "";
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Add plain text before the token
    if (match.index > lastIndex) {
      out += escapeHtml(text.slice(lastIndex, match.index));
    }
    const name = escapeHtml(match[1]);
    const weight = match[2] ? escapeHtml(match[2]) : "";
    out += `<span class="lora-pill">${name}${weight ? `:${weight}` : ""}</span>`;
    lastIndex = regex.lastIndex;
  }

  // Remaining text (if any)
  if (lastIndex < text.length) {
    out += escapeHtml(text.slice(lastIndex));
  }

  return out;
};

// Copy feedback state
const copyStatus = ref<Record<string, boolean>>({});

// Get friendly name for copy toast
const getCopyLabel = (id: string): string => {
  switch (id) {
    case 'prompt': return 'Prompt';
    case 'neg': return 'Negative prompt';
    case 'seed': return 'Seed';
    default: return 'Text';
  }
};

const copyText = async (text: string | undefined, id: string) => {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    copyStatus.value[id] = true;
    const label = getCopyLabel(id);
    toast.success(`${label} copied`, 'Copied to clipboard', { duration: 3000 }); // Short duration for copy
    setTimeout(() => {
      copyStatus.value[id] = false;
    }, 1500);
  } catch (e) {
    console.error("Copy failed", e);
    toast.error('Copy failed', 'Unable to copy to clipboard');
  }
};

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
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
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
                        <button class="icon-btn" @click="copyText(meta.params.Seed, 'seed')" title="Copy Seed">
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
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
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
}

.lightbox-left:hover .nav-btn:not(:disabled) {
  opacity: 1;
}

/* Right Side: Metadata */
.lightbox-right {
  width: var(--lightbox-sidebar-width, 400px);
  min-width: 320px;
  max-width: 450px;
  height: 100%;
  background: rgba(20, 20, 20, 0.8);
  backdrop-filter: blur(20px);
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  color: #e0e0e0;
  font-family: 'Inter', sans-serif;

  @media (max-width: 1024px) {
    width: 350px;
  }

  @media (max-width: 640px) {
    position: fixed;
    inset: 0;
    width: 100%;
    max-width: 100%;
    z-index: 10;
  }
}

.meta-loading,
.meta-error {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #999;
  font-size: 14px;
}

.meta-header {
  padding: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.2);
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    word-break: break-all;
    line-height: 1.4;
  }
}

.header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.close-btn-mini {
  background: transparent;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 18px;
  padding: 4px;
  transition: color 0.2s;

  &:hover { color: #fff; }
}

.fullscreen-btn {
  font-size: 16px;
}

.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-tag {
  font-size: 12px;
  color: #999;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.05);
  padding: 4px 8px;
  border-radius: 4px;

  &.tool-tag {
    background: #3b82f6;
    color: #fff;
    font-weight: 600;
  }
}

.scroll-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;

  & > * {
    flex-shrink: 0;
  }

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 3px;
  }
}

/* Prompt Boxes */
.prompt-box {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(74, 222, 128, 0.35); /* green pastel accent */
  border-radius: 8px;

  &.negative {
    border-color: rgba(239, 68, 68, 0.3);
    .section-top h4 { color: #fca5a5; }
  }
}

.section-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px 8px 0 0;

  h4 {
    margin: 0;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #86efac;
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.copy-btn {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 14px;
  transition: color 0.2s;

  &:hover { color: #fff; }
}

.prompt-body {
  padding: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #d1d5db;
  white-space: pre-wrap;
  max-height: 200px;
  /* Prevent focus on scrollable text - only interactive elements should be focusable */
  &:focus {
    outline: none;
  }
  overflow-y: auto;
}

:deep(.lora-pill) {
  color: #c084fc;
  font-weight: 600;
}

/* Collapsible Groups */
.meta-group {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
}

.group-header {
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
  border-radius: 8px 8px 0 0;

  &:hover { background: rgba(255, 255, 255, 0.08); }

  h4 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: #e5e7eb;
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.group-content {
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

/* Params Grid */
.params-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.param-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;

  .label {
    color: #999;
    text-transform: uppercase;
    font-size: 10px;
    font-weight: 600;
  }

  .value {
    color: #fff;
    font-family: 'JetBrains Mono', monospace;
  }

  .icon-btn {
    background: transparent;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 0;
    display: flex;
    font-size: 12px;
    &:hover { color: #fff; }
  }
}

/* Resource List */
.resource-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;

  .res-info {
    display: flex;
    flex-direction: column;
  }

  .res-type {
    font-size: 10px;
    color: #666;
    text-transform: uppercase;
  }

  .res-name {
    font-size: 13px;
    color: #e5e7eb;
  }

  .res-hash {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: #999;
    background: rgba(255, 255, 255, 0.1);
    padding: 1px 4px;
    border-radius: 4px;
    margin-left: 6px;
  }
}

/* Screen reader only - visually hidden but accessible */
/* ==========================================
   FOCUS STYLES - WCAG 2.1 Compliant
   Using box-shadow for consistent full border
   ========================================== */

/* Base focus style mixin - orange border with dark inner ring */
.nav-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
  opacity: 1;
}

.close-btn-mini:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
  border-radius: 4px;
}

/* Copy buttons in prompt boxes */
.copy-btn {
  border-radius: 4px;
  padding: 4px 6px;
  
  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring-shadow);
  }
}

/* Icon buttons (seed copy, etc) */
.icon-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
  border-radius: 4px;
}

/* Collapsible group headers */
.group-header:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  .lightbox-overlay {
    background: #000;
  }
  
  .lightbox-right {
    background: #000;
    border-left: 2px solid #fff;
  }
  
  .nav-btn {
    border: 2px solid #fff;
  }
  
  .prompt-box {
    border: 2px solid #fff;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
  
  .hero-image {
    transition: none;
  }
}

/* =============================================
   RESPONSIVE — Lightbox Mobile
   ============================================= */

/* Tablet: narrow metadata panel */
@media (max-width: 1024px) {
  .lightbox-right {
    width: 320px;
    min-width: 280px;
  }
}

/* Phone: nav buttons always visible, metadata becomes bottom sheet */
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

  .lightbox-right {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    height: auto;
    max-height: 45vh;
    border-left: none;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    position: relative;
    flex-shrink: 0;
  }

  .meta-header {
    padding: 12px 16px;
  }

  .scroll-content {
    padding: 12px 16px;
    gap: 12px;
  }

  .header-top h3 {
    font-size: 14px;
  }

  .prompt-body {
    max-height: 120px;
    font-size: 12px;
  }
}

/* Small phone: compact metadata */
@media (max-width: 480px) {
  .nav-btn {
    width: 40px;
    height: 56px;
    font-size: 18px;
  }

  .lightbox-right {
    max-height: 40vh;
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

/* Auto-fullscreen on very small screens (<640px) */
@media (max-width: 640px) {
  .lightbox-right {
    display: none;
  }

  .lightbox-shell:fullscreen .lightbox-right,
  .lightbox-shell:-webkit-full-screen .lightbox-right {
    display: flex;
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
