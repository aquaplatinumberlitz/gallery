<script setup lang="ts">
import { ref, watch } from "vue";
import { FolderOpen, ClipboardPaste, X } from "lucide-vue-next";

const props = defineProps<{
  modelValue: boolean;
  currentPath: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void;
  (e: "load", path: string): void;
}>();

const localPath = ref("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);

const handleOpen = () => {
  localPath.value = props.currentPath;
};

const handlePaste = async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      localPath.value = text;
    }
  } catch (e) {
    console.warn("Clipboard read not available or denied");
  }
};

const handleClear = async () => {
  localPath.value = "";
};

const handleCancel = () => {
  emit("update:modelValue", false);
};

const handleLoad = () => {
  const cleaned = localPath.value.trim().replace(/^["']|["']$/g, "");
  emit("load", cleaned);
  textareaRef.value?.blur();
  emit("update:modelValue", false);
};

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === "Escape") {
    handleCancel();
  }
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
    handleLoad();
  }
};

// Sync localPath and focus textarea when sheet opens
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      handleOpen();
    }
  }
);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="root-path-sheet-backdrop"
      @click.self="handleCancel"
      @keydown="handleKeydown"
    >
      <div
        class="root-path-sheet"
        @click.stop
      >
        <!-- Handle -->
        <div class="sheet-handle-wrapper">
          <div class="sheet-handle" />
        </div>

        <!-- Title -->
        <div class="sheet-title">
          <FolderOpen :size="18" class="title-icon" />
          <span>Edit Root Path</span>
        </div>

        <!-- Textarea -->
        <textarea
          ref="textareaRef"
          v-model="localPath"
          class="root-path-textarea"
          placeholder="Enter folder path..."
          inputmode="text"
          autocapitalize="off"
          autocorrect="off"
          spellcheck="false"
          enterkeyhint="go"
          @keydown="handleKeydown"
        ></textarea>

        <!-- Action buttons -->
        <div class="sheet-actions">
          <button class="action-btn" type="button" @click="handlePaste" title="Paste from clipboard">
            <ClipboardPaste :size="16" />
            <span>Paste</span>
          </button>
          <button class="action-btn clear-btn" type="button" @click="handleClear" title="Clear path">
            <X :size="16" />
            <span>Clear</span>
          </button>
          <button class="action-btn cancel-btn" type="button" @click="handleCancel" title="Cancel">
            <span>Cancel</span>
          </button>
          <button class="action-btn load-btn" type="button" @click="handleLoad" title="Load path">
            <span>Load</span>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.root-path-sheet-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  z-index: 10000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.root-path-sheet {
  background: var(--surface-color, #fff);
  width: 100%;
  max-width: 100%;
  border-radius: 16px 16px 0 0;
  padding: 0 16px 24px;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  max-height: 85vh;
  overflow-y: auto;
}

[data-theme="dark"] .root-path-sheet {
  background: var(--surface-color, #1c1c1e);
}

.sheet-handle-wrapper {
  display: flex;
  justify-content: center;
  padding: 8px 0 4px;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.15);
}

[data-theme="dark"] .sheet-handle {
  background: rgba(255, 255, 255, 0.2);
}

.sheet-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color, #050505);
}

.title-icon {
  color: var(--primary-color, #ff6b35);
  flex-shrink: 0;
}

.root-path-textarea {
  display: block;
  width: 100%;
  min-height: 72px;
  max-height: 120px;
  padding: 12px;
  font-size: 16px;
  font-family: inherit;
  line-height: 1.4;
  color: var(--text-color, #050505);
  background: var(--bg-color, #f5f5f5);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  outline: none;
  resize: vertical;
  overflow-wrap: break-word;
  word-break: break-all;
  white-space: pre-wrap;
  box-sizing: border-box;
  transition: border-color 0.2s, box-shadow 0.2s;
}

[data-theme="dark"] .root-path-textarea {
  background: var(--bg-color, #2c2c2e);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--text-color, #f0f0f0);
}

.root-path-textarea:focus {
  border-color: var(--primary-color, #ff6b35);
  box-shadow: 0 0 0 2px rgba(255, 107, 53, 0.15);
}

.root-path-textarea::placeholder {
  color: var(--muted-text, #aaa);
}

.sheet-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.action-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  padding: 0 12px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  touch-action: manipulation;
  color: var(--text-color, #050505);
  background: rgba(0, 0, 0, 0.05);
}

[data-theme="dark"] .action-btn {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-color, #f0f0f0);
}

.action-btn:active {
  transform: scale(0.95);
}

.clear-btn {
  color: #e74c3c;
}

.cancel-btn {
  color: var(--muted-text, #65676b);
}

.load-btn {
  background: var(--primary-color, #ff6b35);
  color: #fff;
}

.load-btn:active {
  background: color-mix(in srgb, var(--primary-color, #ff6b35) 85%, black);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
</style>
