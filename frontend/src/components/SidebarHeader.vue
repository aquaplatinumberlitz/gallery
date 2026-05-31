<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useGalleryStore } from "../stores/gallery";
import { FolderOpen, RotateCcw, Info } from "lucide-vue-next";

const galleryStore = useGalleryStore();
const pathInput = ref(galleryStore.rootPath || "");
const inputRef = ref<HTMLInputElement | null>(null);

const onLoad = async () => {
  const cleaned = pathInput.value.trim().replace(/^["']|["']$/g, "");
  await galleryStore.setRootPath(cleaned);
  inputRef.value?.blur();
};

const onReset = () => {
  galleryStore.resetRootPath();
  pathInput.value = "";
};

onMounted(() => {
  if (galleryStore.rootPath) {
    pathInput.value = galleryStore.rootPath;
    galleryStore.setRootPath(galleryStore.rootPath);
  }
});

watch(
  () => galleryStore.rootPath,
  (val) => {
    if (val && val !== pathInput.value) {
      pathInput.value = val;
    }
  }
);
</script>

<template>
  <div class="sidebar-header">
    <label class="field-label" for="root-path">ROOT PATH</label>
    
    <div class="field-container">
      <FolderOpen class="field-icon" :size="16" />
      <input
        id="root-path"
        ref="inputRef"
        v-model="pathInput"
        type="text"
        placeholder="Enter folder path..."
        @keyup.enter="onLoad"
        autocomplete="off"
        :title="pathInput"
      />
      
      <button 
        v-if="pathInput"
        class="action-btn" 
        type="button" 
        @click="onReset" 
        title="Reset path"
      >
        <RotateCcw :size="14" />
      </button>
    </div>
    
    <p id="root-path-hint" class="field-hint">
      <Info :size="12" />
      Press Enter to load
    </p>
  </div>
</template>

<style scoped>
.sidebar-header {
  padding: 16px;
  background-color: var(--surface-color, #fff);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.field-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted-text, #65676b);
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

.field-container {
  background: var(--surface-color, #fff);
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  height: 40px;
  transition: border-color 0.2s, box-shadow 0.2s;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.field-container:hover {
  border-color: var(--primary-color, #ff6b35);
  box-shadow: var(--gallery-shadow-md, 0 4px 12px rgba(255, 107, 53, 0.25));
}

.field-container:focus-within {
  border-color: var(--primary-color, #ff6b35);
  box-shadow: var(--gallery-shadow-md, 0 4px 12px rgba(255, 107, 53, 0.25));
}

.field-icon {
  color: var(--primary-color);
  flex-shrink: 0;
}

.field-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted-text, #65676b);
}

input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0 8px;
  font-size: 14px;
  outline: none;
  color: var(--text-color, #050505);
  min-width: 0;
}

input::placeholder {
  color: var(--muted-text, #aaa);
}

.action-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--muted-text, #65676b);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-color, #000);
}

.action-btn:focus {
  outline: none;
}

.action-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.action-btn:active {
  transform: scale(0.95);
}

/* Responsive: iOS Safari zoom fix — font-size >= 16px prevents auto-zoom on input focus */
@media (max-width: 767px) {
  .sidebar-header {
    padding: 12px;
  }

  .field-container {
    height: 40px;
    padding: 0 10px;
  }

  input {
    font-size: 16px;
    min-width: 140px;
    touch-action: manipulation;
  }

  .action-btn {
    touch-action: manipulation;
  }
}

</style>
