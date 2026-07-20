<script setup lang="ts">
import { ScanSearch } from "lucide-vue-next";

withDefaults(defineProps<{ label?: string; dark?: boolean }>(), {
  label: "Image actions",
  dark: false,
});

const emit = defineEmits<{ findRelated: [] }>();

defineOptions({ inheritAttrs: false });
</script>

<template>
  <div class="asset-action-menu" v-bind="$attrs" @click.stop>
    <button
      type="button"
      class="asset-action-trigger"
      :class="{ 'asset-action-trigger-dark': dark }"
      :aria-label="`Find related images`"
      title="Find related"
      @click.stop="emit('findRelated')"
      @keydown.stop
    >
      <ScanSearch class="trigger-icon" />
      <span class="action-label">Find related</span>
    </button>
  </div>
</template>

<style scoped>
.asset-action-menu {
  display: inline-flex;
}

/* ── Shared base ── */
.asset-action-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
  background: color-mix(in srgb, var(--background) 82%, transparent);
  color: var(--foreground);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 140ms ease,
    box-shadow 140ms ease,
    transform 120ms ease,
    color 140ms ease;
}

.trigger-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* ── Desktop: pill with label, revealed on hover ── */
@media (hover: hover) {
  .asset-action-trigger {
    height: 30px;
    padding: 0 10px 0 8px;
    border-radius: 20px;
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: 0.01em;
    box-shadow:
      0 2px 8px color-mix(in srgb, black 14%, transparent),
      0 1px 2px color-mix(in srgb, black 10%, transparent);
  }

  .asset-action-trigger:hover {
    background: var(--accent);
    box-shadow:
      0 4px 16px color-mix(in srgb, black 20%, transparent),
      0 1px 3px color-mix(in srgb, black 12%, transparent);
    transform: translateY(-1px);
  }

  .asset-action-trigger:active {
    transform: translateY(0) scale(0.97);
    box-shadow: 0 1px 4px color-mix(in srgb, black 14%, transparent);
  }
}

/* ── Mobile: icon-only circle, 44×44 tap target ── */
@media (hover: none) {
  .asset-action-trigger {
    /* 44×44 meets Apple HIG / WCAG 2.5.5 tap target */
    width: 44px;
    height: 44px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    /* slightly darker glass so icon pops on any photo */
    background: rgba(0, 0, 0, 0.42);
    border-color: rgba(255, 255, 255, 0.18);
    color: #fff;
    box-shadow:
      0 1px 6px rgba(0, 0, 0, 0.28),
      inset 0 1px 0 rgba(255, 255, 255, 0.10);
    /* no transform animations — mobile prefers instant feedback via :active */
    transition: background 100ms ease;
    /* extend touch area without changing visual size */
    -webkit-tap-highlight-color: transparent;
  }

  /* Hide text label on mobile — icon only */
  .action-label {
    display: none;
  }

  .trigger-icon {
    width: 18px;
    height: 18px;
  }

  /* Tap feedback: brighten + slight scale */
  .asset-action-trigger:active {
    background: rgba(255, 255, 255, 0.22);
    transform: scale(0.92);
    transition:
      background 60ms ease,
      transform 60ms ease;
  }
}

/* ── Focus ring (keyboard / assistive tech) ── */
.asset-action-trigger:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* ── Dark variant (Lightbox overlay) ── */
.asset-action-trigger-dark {
  border-color: rgba(255, 255, 255, 0.22);
  background: rgba(0, 0, 0, 0.52);
  color: rgba(255, 255, 255, 0.92);
}

@media (hover: hover) {
  .asset-action-trigger-dark:hover {
    background: rgba(255, 255, 255, 0.16);
    color: #fff;
  }
}

.action-label {
  line-height: 1;
}
</style>
