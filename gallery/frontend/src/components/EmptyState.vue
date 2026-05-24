<script setup lang="ts">
import { computed } from 'vue';
import { 
  FolderOpen, Search, Images, TriangleAlert, Loader, Box, 
  Sprout, Cpu, Sparkle, X 
} from 'lucide-vue-next';

// @ts-expect-error: used via :is dynamic component binding
const _icons = { FolderOpen, Search, Images, TriangleAlert, Loader, Box, Sprout, Cpu, X }

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
        icon: 'Sprout',
        color: '#fb923c',
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

// Map actionIcon prop name to Lucide component
const actionIconComponent = computed(() => {
  if (!props.actionIcon) return null;
  const map: Record<string, string> = {
    'xmark': 'X',
    'arrow-left': 'ArrowLeft',
  };
  return map[props.actionIcon] || props.actionIcon;
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
          <component 
            :is="defaults.icon" 
            :size="32"
            :class="{ 'lucide-spin': type === 'loading' }"
          />
        </div>
      </div>
      
      <!-- Decorative elements -->
      <div class="floating-elements">
        <div class="float-dot dot-1"></div>
        <div class="float-dot dot-2"></div>
        <div class="float-dot dot-3"></div>
        <div class="sparkle sparkle-1">
          <Sparkle :size="12" />
        </div>
        <div class="sparkle sparkle-2">
          <Sparkle :size="10" />
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
        <component v-if="actionIcon" :is="actionIconComponent" :size="14" />
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
  background: linear-gradient(135deg, var(--surface-color) 0%, var(--bg-color) 100%);
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

.icon-ring i {
  font-size: 32px;
  color: var(--accent-color);
}

.compact .icon-ring i {
  font-size: 24px;
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
  gap: 8px;
  margin-top: 20px;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: var(--accent-color);
  color: #fff;
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
:root[data-theme="dark"] .icon-ring {
  background: linear-gradient(135deg, var(--surface-color) 0%, #1a1a1a 100%);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.3),
    0 0 0 8px rgba(255, 255, 255, 0.05);
}

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
  .sparkle,
  .icon-ring i {
    animation: none !important;
  }
}
</style>
