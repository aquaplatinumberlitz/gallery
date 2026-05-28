<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { fetchLandingPages } from '../services/api';
import { useFocusTrap } from '../composables/useFocusTrap';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'preview', url: string): void;
}>();

const introMode = ref<'auto' | 'disabled' | 'manual'>('auto');
const selectedTheme = ref('');
const availableThemes = ref<string[]>([]);
const isLoadingThemes = ref(false);
const modalRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);

const { activate, deactivate } = useFocusTrap(modalRef, {
  initialFocus: closeButtonRef,
  returnFocus: true,
});

// Helper: /landpage/birthday/index.html -> Birthday
const formatThemeName = (path: string) => {
  const parts = path.split('/').filter(p => p && p !== 'landpage' && !p.endsWith('.html'));
  // parts[0] should be the folder name e.g. 'birthday'
  if (parts.length > 0) {
    const name = parts[0];
    return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  }
  return 'Unknown Theme';
};

const loadSettings = () => {
  const savedMode = localStorage.getItem('intro_mode');
  if (savedMode && ['auto', 'disabled', 'manual'].includes(savedMode)) {
    introMode.value = savedMode as any;
  }
  
  const savedTheme = localStorage.getItem('intro_theme');
  if (savedTheme) {
    selectedTheme.value = savedTheme;
  }
};

const saveSettings = () => {
  localStorage.setItem('intro_mode', introMode.value);
  if (selectedTheme.value) {
    localStorage.setItem('intro_theme', selectedTheme.value);
  }
};

onMounted(async () => {
  loadSettings();
  try {
    isLoadingThemes.value = true;
    const pages = await fetchLandingPages();
    availableThemes.value = pages;
    
    if (!selectedTheme.value && pages.length > 0) {
      selectedTheme.value = pages[0];
    }
  } catch (e) {
    console.error("Failed to load themes", e);
  } finally {
    isLoadingThemes.value = false;
  }
});

watch([introMode, selectedTheme], () => {
  saveSettings();
});

const handlePreview = () => {
  if (selectedTheme.value) {
    emit('preview', selectedTheme.value);
  }
};

const handleKeydown = (e: KeyboardEvent) => {
  if (!props.isOpen) return;
  if (e.key === 'Escape') {
    emit('close');
  }
};

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      activate();
      document.addEventListener('keydown', handleKeydown);
    } else {
      deactivate();
      document.removeEventListener('keydown', handleKeydown);
    }
  }
);

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
  deactivate();
});
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="modal-backdrop" @click="$emit('close')">
      <div ref="modalRef" class="modal-content" @click.stop>
        <header class="modal-header">
          <h2 class="modal-title">SETTINGS</h2>
          <button ref="closeButtonRef" class="close-text-btn" @click="$emit('close')">CLOSE</button>
        </header>

        <div class="modal-body">
          <section class="setting-section">
            <h3 class="section-title">Intro Screen</h3>
            
            <div class="options-list">
              <label class="option-item" :class="{ active: introMode === 'auto' }">
                <input type="radio" v-model="introMode" value="auto" class="sr-only">
                <div class="option-content">
                  <span class="option-label">Automatic</span>
                  <span class="option-desc">Random themes, prioritizing holidays</span>
                </div>
              </label>

              <label class="option-item" :class="{ active: introMode === 'disabled' }">
                <input type="radio" v-model="introMode" value="disabled" class="sr-only">
                <div class="option-content">
                  <span class="option-label">Disabled</span>
                  <span class="option-desc">Skip intro and enter gallery directly</span>
                </div>
              </label>

              <label class="option-item" :class="{ active: introMode === 'manual' }">
                <input type="radio" v-model="introMode" value="manual" class="sr-only">
                <div class="option-content">
                  <span class="option-label">Manual Selection</span>
                  <span class="option-desc">Always show a specific theme</span>
                </div>
              </label>
            </div>

            <div v-if="introMode === 'manual'" class="sub-settings">
              <div v-if="isLoadingThemes" class="loading-text">Loading themes...</div>
              <div v-else class="theme-selector-group">
                <select v-model="selectedTheme" class="theme-select">
                  <option v-for="theme in availableThemes" :key="theme" :value="theme">
                    {{ formatThemeName(theme) }}
                  </option>
                </select>
                <button class="preview-btn" @click="handlePreview">
                  PREVIEW
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.modal-content {
  background: var(--surface-color);
  width: 100%;
  max-width: 400px;
  border-radius: 16px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.08);
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

[data-theme="dark"] .modal-content {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: #1e293b;
}

.modal-header {
  padding: 20px 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

[data-theme="dark"] .modal-header {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

.modal-title {
  font-family: 'Cinzel', serif;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.05em;
  margin: 0;
  color: var(--title-color);
}

[data-theme="dark"] .modal-title {
  color: #f1f5f9;
}

.close-text-btn {
  background: none;
  border: none;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--muted-text);
  cursor: pointer;
  padding: 4px 8px;
  transition: color 0.2s;
  text-transform: uppercase;
}

.close-text-btn:hover {
  color: var(--text-color);
}

.modal-body {
  padding: 24px;
}

.section-title {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted-text);
  margin: 0 0 16px 0;
  font-weight: 600;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="dark"] .option-item {
  background: rgba(255, 255, 255, 0.03);
}

.option-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

[data-theme="dark"] .option-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.option-item.active {
  background: var(--surface-color);
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

[data-theme="dark"] .option-item.active {
  background: rgba(201, 169, 98, 0.1);
  border-color: var(--primary-color);
}

.option-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.option-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-color);
}

.option-item.active .option-label {
  color: var(--primary-color);
  font-weight: 600;
}

.option-desc {
  font-size: 12px;
  color: var(--muted-text);
}

.sub-settings {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  animation: fadeIn 0.3s ease;
}

[data-theme="dark"] .sub-settings {
  border-top-color: rgba(255, 255, 255, 0.06);
}

.theme-selector-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.theme-select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  background: var(--surface-color);
  color: var(--text-color);
  font-size: 14px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

[data-theme="dark"] .theme-select {
  background: #0f172a;
  border-color: rgba(255, 255, 255, 0.2);
  color: #f1f5f9;
  color-scheme: dark;
}

[data-theme="dark"] .theme-select option {
  background-color: #0f172a;
  color: #f1f5f9;
}

.theme-select:focus {
  border-color: var(--primary-color);
}

.preview-btn {
  width: 100%;
  padding: 10px;
  background: transparent;
  border: 1px solid var(--primary-color);
  color: var(--primary-color);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s;
  text-transform: uppercase;
}

.preview-btn:hover {
  background: var(--primary-color);
  color: #fff;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
</style>
