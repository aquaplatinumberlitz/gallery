<script setup lang="ts">
import { computed } from 'vue';
// ── FontAwesome Pro SVG strings ──
const FA_ICONS: Record<string, string> = {
  FolderOpen: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M64 356.2L64 96L288 96L352 144L544 144L544 224L106.8 224C103.2 235.2 88.9 279.2 64 356.2zM530.3 512L64 512L141.7 272L608 272L530.3 512z"/></svg>`,
  Search: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M480.3 272C480.3 317.9 465.4 360.3 440.3 394.7L566.9 521.4L589.5 544L544.3 589.3L521.6 566.6L395 440C360.6 465.2 318.2 480 272.3 480C157.4 480 64.3 386.9 64.3 272C64.3 157.1 157.4 64 272.3 64C387.2 64 480.3 157.1 480.3 272zM272.3 416C351.8 416 416.3 351.5 416.3 272C416.3 192.5 351.8 128 272.3 128C192.8 128 128.3 192.5 128.3 272C128.3 351.5 192.8 416 272.3 416z"/></svg>`,
  Images: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M128 96L576 96L576 480L128 480L128 96zM80 192L80 528L480 528L480 576L32 576L32 192L80 192zM224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160C206.3 160 192 174.3 192 192C192 209.7 206.3 224 224 224zM272 272L176 416L528 416L400 208L318.1 341.1L272 272z"/></svg>`,
  TriangleAlert: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M592 544L48 544L320 48L592 544zM292 420L292 476L348 476L348 420L292 420zM288 224L300.8 384L339.2 384L352 224L288 224z"/></svg>`,
  FolderTree: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M288 96L169.4 96L64 544L321.4 544C310.2 519.6 304 492.6 304 464C304 435.4 310.2 408.4 321.4 384L288 384L288 256L352 256L352 337C387.2 297.1 438.7 272 496 272C501.4 272 506.8 272.2 512.2 272.7L470.6 96L352 96L352 192L288 192L288 96zM496 608C575.5 608 640 543.5 640 464C640 384.5 575.5 320 496 320C416.5 320 352 384.5 352 464C352 543.5 416.5 608 496 608zM551.3 431.3L518.6 464C544 489.3 558.6 504 562.6 508L540 530.6C536 526.6 521.4 512 496 486.6C470.7 512 456 526.6 452 530.6L429.4 508C433.4 504 448 489.4 473.4 464C448 438.7 433.4 424 429.4 420L452 397.4C456 401.4 470.6 416 496 441.4C521.3 416 536 401.4 540 397.4L562.6 420L551.3 431.3z"/></svg>`,
  Loader: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M272 64L272 160L368 160L368 64L272 64zM64 272L64 368L160 368L160 272L64 272zM272 576L368 576L368 480L272 480L272 576zM576 272L480 272L480 368L576 368L576 272zM105 467.1L172.9 535L240.8 467.1L172.9 399.2L105 467.1zM467 535L534.9 467.1L467 399.2L399.1 467.1L467 535zM105 172.9L172.9 240.8L240.8 172.9L172.9 105L105 172.9z"/></svg>`,
  Box: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M64 320C64 178.6 178.6 64 320 64C461.4 64 576 178.6 576 320C576 461.4 461.4 576 320 576C178.6 576 64 461.4 64 320z"/></svg>`,
  X: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M182.9 137.4L160.3 114.7L115 160L137.6 182.6L275 320L137.6 457.4L115 480L160.3 525.3L182.9 502.6L320.3 365.3L457.6 502.6L480.3 525.3L525.5 480L502.9 457.4L365.5 320L502.9 182.6L525.5 160L480.3 114.7L457.6 137.4L320.3 274.7L182.9 137.4z"/></svg>`,
  ArrowLeft: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M73.6 297.4L51 320L73.6 342.6L233.6 502.6L256.2 525.2L301.5 479.9C300.2 478.6 257.5 435.9 173.5 351.9L576.2 351.9L576.2 287.9L173.5 287.9C257.5 203.9 300.2 161.2 301.5 159.9L256.2 114.6L233.6 137.2L73.6 297.2z"/></svg>`,
  Sparkle: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M480 96L512 24L544 96L616 128L544 160L512 232L480 160L408 128L480 96zM160 256L224 112L288 256L432 320L288 384L224 528L160 384L16 320L160 256zM480 408L512 480L584 512L512 544L480 616L448 544L376 512L448 480L480 408z"/></svg>`,
};

export type EmptyStateType = 
  | 'empty-folder' 
  | 'no-results' 
  | 'no-images' 
  | 'error' 
  | 'no-path'
  | 'loading';

const props = withDefaults(defineProps<{
  type?: EmptyStateType;
  title?: string;
  description?: string;
  actionLabel?: string;
  actionIcon?: string;
  compact?: boolean;
}>(), {
  type: 'empty-folder',
  compact: false,
});

const emit = defineEmits<{
  (e: 'action'): void;
}>();

// Default content for each type
const defaults = computed(() => {
  switch (props.type) {
    case 'empty-folder':
      return {
        title: 'This folder is empty',
        description: 'No images or subfolders found here',
        icon: 'FolderOpen',
        color: '#a78bfa',
      };
    case 'no-results':
      return {
        title: 'No results found',
        description: 'Try adjusting your search or filters',
        icon: 'Search',
        color: '#60a5fa',
      };
    case 'no-images':
      return {
        title: 'No images here',
        description: 'This folder only contains subfolders',
        icon: 'Images',
        color: '#f472b6',
      };
    case 'error':
      return {
        title: 'Something went wrong',
        description: 'Unable to load content. Please try again.',
        icon: 'TriangleAlert',
        color: '#f87171',
      };
    case 'no-path':
      return {
        title: 'Welcome to Gallery',
        description: 'Enter a folder path to start browsing your images',
        icon: 'FolderTree',
        color: '#f2a007',
      };
    case 'loading':
      return {
        title: 'Loading...',
        description: 'Please wait while we fetch your content',
        icon: 'Loader',
        color: '#a78bfa',
      };
    default:
      return {
        title: 'Nothing here',
        description: '',
        icon: 'Box',
        color: '#94a3b8',
      };
  }
});

const displayTitle = computed(() => props.title || defaults.value.title);
const displayDescription = computed(() => props.description || defaults.value.description);

// Returns SVG HTML string for the icon
const currentIconSvg = computed(() => FA_ICONS[defaults.value.icon]);

// Map actionIcon prop name to SVG
const actionIconComponent = computed(() => {
  if (!props.actionIcon) return null;
  const name = props.actionIcon === 'xmark' ? 'X' : props.actionIcon === 'arrow-left' ? 'ArrowLeft' : props.actionIcon;
  return FA_ICONS[name];
});
</script>

<template>
  <div 
    class="empty-state" 
    :class="{ compact }"
    :style="{ '--accent-color': defaults.color }"
  >
    <!-- Illustration -->
    <div class="illustration">
      <!-- Background decoration circles -->
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
      
      <!-- Main icon container -->
      <div class="icon-container">
        <div class="icon-ring">
          <span class="fa-icon-wrap" :class="{ 'icon-spin': type === 'loading' }" v-html="currentIconSvg"></span>
        </div>
      </div>
      
      <!-- Decorative elements -->
      <div class="floating-elements">
        <div class="float-dot dot-1"></div>
        <div class="float-dot dot-2"></div>
        <div class="float-dot dot-3"></div>
        <div class="sparkle sparkle-1">
          <span class="fa-sparkle" v-html="FA_ICONS['Sparkle']"></span>
        </div>
        <div class="sparkle sparkle-2">
          <span class="fa-sparkle" v-html="FA_ICONS['Sparkle']"></span>
        </div>
      </div>
    </div>
    
    <!-- Text content -->
    <div class="content">
      <h3 class="title">{{ displayTitle }}</h3>
      <p v-if="displayDescription" class="description">{{ displayDescription }}</p>
      
      <!-- Action button -->
      <button 
        v-if="actionLabel"
        class="action-btn"
        type="button"
        @click="emit('action')"
      >
        <span class="fa-icon-wrap action-icon-fa" v-html="actionIconComponent"></span>
        <span>{{ actionLabel }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  min-height: 300px;
}

.empty-state.compact {
  padding: 32px 16px;
  min-height: 200px;
}

/* Illustration */
.illustration {
  position: relative;
  width: 160px;
  height: 160px;
  margin-bottom: 24px;
}

.compact .illustration {
  width: 120px;
  height: 120px;
  margin-bottom: 16px;
}

/* Background circles */
.bg-circle {
  position: absolute;
  border-radius: 50%;
  background: var(--accent-color);
  opacity: 0.08;
}

.bg-circle-1 {
  width: 100%;
  height: 100%;
  top: 0;
  left: 0;
  animation: pulse-slow 4s ease-in-out infinite;
}

.bg-circle-2 {
  width: 75%;
  height: 75%;
  top: 12.5%;
  left: 12.5%;
  opacity: 0.12;
  animation: pulse-slow 4s ease-in-out infinite 0.5s;
}

.bg-circle-3 {
  width: 50%;
  height: 50%;
  top: 25%;
  left: 25%;
  opacity: 0.15;
  animation: pulse-slow 4s ease-in-out infinite 1s;
}

/* Icon container */
.icon-container {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}

.icon-ring {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--gallery-surface-default, rgba(255,255,255,0.1));
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  border: 2px solid var(--accent-color);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.08),
    0 0 0 8px color-mix(in srgb, var(--accent-color) 15%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
}

.compact .icon-ring {
  width: 64px;
  height: 64px;
}

/* FA SVG icon styles */
.fa-icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-color);
}

.fa-icon-wrap :deep(svg) {
  width: 32px;
  height: 32px;
  display: block;
}

.compact .fa-icon-wrap :deep(svg) {
  width: 24px;
  height: 24px;
}

.icon-ring :deep(svg) {
  color: var(--accent-color);
}

.compact .icon-ring :deep(svg) {
  width: 24px;
  height: 24px;
}

/* Spin animation for loading */
.icon-spin :deep(svg) {
  animation: icon-spin 1.5s linear infinite;
}

@keyframes icon-spin {
  to { transform: rotate(360deg); }
}

/* Floating elements */
.floating-elements {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.float-dot {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-color);
  opacity: 0.4;
}

.dot-1 {
  top: 15%;
  right: 10%;
  animation: float 3s ease-in-out infinite;
}

.dot-2 {
  bottom: 20%;
  left: 8%;
  width: 6px;
  height: 6px;
  animation: float 3.5s ease-in-out infinite 0.5s;
}

.dot-3 {
  top: 40%;
  left: 5%;
  width: 5px;
  height: 5px;
  animation: float 4s ease-in-out infinite 1s;
}

.sparkle {
  position: absolute;
  color: var(--accent-color);
  opacity: 0.6;
  font-size: 12px;
}

.fa-sparkle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-color);
  opacity: 0.6;
}
.fa-sparkle :deep(svg) {
  width: 12px;
  height: 12px;
  display: block;
}

.sparkle-1 {
  top: 10%;
  left: 20%;
  animation: twinkle 2s ease-in-out infinite;
}

.sparkle-2 {
  bottom: 15%;
  right: 15%;
  font-size: 10px;
  animation: twinkle 2.5s ease-in-out infinite 0.5s;
}

/* Content */
.content {
  max-width: 320px;
}

.title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--title-color);
}

.compact .title {
  font-size: 16px;
}

.description {
  margin: 0;
  font-size: 14px;
  color: var(--muted-text);
  line-height: 1.5;
}

.compact .description {
  font-size: 13px;
}

/* Action button */
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 20px;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: var(--primary-color);
  color: var(--gallery-text-inverse, #fff);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15), 0 1px 3px rgba(0, 0, 0, 0.1);
}

.action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2), 0 2px 6px rgba(0, 0, 0, 0.12);
  filter: brightness(1.1);
}

.action-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.action-btn:active {
  transform: translateY(0);
}

/* Action icon FA styling */
.action-icon-fa :deep(svg) {
  width: 14px;
  height: 14px;
  display: block;
}

.action-btn .action-icon-fa {
  color: var(--gallery-text-inverse, #fff);
}

/* Animations */
@keyframes pulse-slow {
  0%, 100% {
    transform: scale(1);
    opacity: 0.08;
  }
  50% {
    transform: scale(1.05);
    opacity: 0.12;
  }
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes twinkle {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

/* Dark mode adjustments */
:root[data-theme="dark"] .bg-circle {
  opacity: 0.15;
}

:root[data-theme="dark"] .float-dot {
  opacity: 0.5;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .bg-circle,
  .float-dot,
  .sparkle {
    animation: none !important;
  }
}
</style>
