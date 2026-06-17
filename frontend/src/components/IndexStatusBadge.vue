<script setup lang="ts">
import type { IndexStatusPresentation } from "@/utils/indexStatus";

defineProps<{
  presentation: IndexStatusPresentation;
}>();
</script>

<template>
  <span class="index-status-badge" :class="`index-status-badge--${presentation.tone}`">
    <span
      class="index-status-badge__dot"
      :class="{ 'index-status-badge__dot--pulse': presentation.showPulse }"
      aria-hidden="true"
    />
    <span>{{ presentation.label }}</span>
  </span>
</template>

<style scoped>
.index-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  border: 1px solid transparent;
  border-radius: var(--gallery-radius-full);
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.index-status-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  flex: 0 0 auto;
}

.index-status-badge--green {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(34, 197, 94, 0.1);
  color: #15803d;
}

.index-status-badge--green .index-status-badge__dot {
  background: #16a34a;
}

.index-status-badge--yellow {
  border-color: rgba(245, 158, 11, 0.2);
  background: rgba(245, 158, 11, 0.12);
  color: #a16207;
}

.index-status-badge--yellow .index-status-badge__dot {
  background: #d97706;
}

.index-status-badge--red {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
}

.index-status-badge--red .index-status-badge__dot {
  background: #dc2626;
}

.index-status-badge--gray {
  border-color: rgba(107, 114, 128, 0.18);
  background: rgba(107, 114, 128, 0.1);
  color: #4b5563;
}

.index-status-badge--gray .index-status-badge__dot {
  background: #6b7280;
}

.index-status-badge__dot--pulse {
  animation: index-status-dot-pulse 1.8s ease-in-out infinite;
}

@keyframes index-status-dot-pulse {
  0%,
  100% {
    opacity: 1;
    box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.28);
  }
  50% {
    opacity: 0.72;
    box-shadow: 0 0 0 4px rgba(217, 119, 6, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .index-status-badge__dot--pulse {
    animation: none;
  }
}

:global(:root[data-theme="dark"]) .index-status-badge--green {
  color: #86efac;
}

:global(:root[data-theme="dark"]) .index-status-badge--yellow {
  color: #fde68a;
}

:global(:root[data-theme="dark"]) .index-status-badge--red {
  color: #fca5a5;
}

:global(:root[data-theme="dark"]) .index-status-badge--gray {
  color: #d1d5db;
}
</style>
