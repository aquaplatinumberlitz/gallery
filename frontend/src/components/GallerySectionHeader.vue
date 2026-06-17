<script setup lang="ts">
import type { Component } from "vue";
import { ChevronDown } from "lucide-vue-next";

defineProps<{
  title: string;
  count?: number;
  badgeIcon?: Component;
  clickable?: boolean;
  collapsed?: boolean;
}>();
</script>

<template>
  <div
    class="gallery-section-header"
    :class="{ 'is-clickable': clickable }"
  >
    <h3>{{ title }}</h3>
    <span
      v-if="count !== undefined"
      class="section-count-badge"
    >
      <component
        :is="badgeIcon"
        v-if="badgeIcon"
        class="gallery-icon-md"
      />
      {{ count }}
      <ChevronDown
        v-if="clickable"
        class="toggle-chevron gallery-icon-md"
        :class="{ collapsed }"
      />
    </span>
  </div>
</template>

<style scoped>
.gallery-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.gallery-section-header h3 {
  margin: 0;
  font-family: "Cinzel", serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--brand-section-label);
  position: relative;
  display: inline-block;
}

.gallery-section-header h3::after {
  content: "";
  position: absolute;
  bottom: -4px;
  left: 0;
  width: 100%;
  height: 1.5px;
  background: linear-gradient(90deg, var(--brand-section-label) 0%, transparent 100%);
  border-radius: 1px;
}

.section-count-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--brand-section-label) 12%, transparent);
  font-size: 12px;
  font-family: var(--font-code);
  color: var(--brand-section-label);
}

.toggle-chevron {
  margin-left: 4px;
  vertical-align: middle;
  transition: transform 0.3s ease;
  opacity: 0.6;
  flex-shrink: 0;
}

.toggle-chevron.collapsed {
  transform: rotate(-90deg);
}

.is-clickable:hover .toggle-chevron {
  opacity: 1;
}

/* ── Token-based icon sizes ────────────────────────────────── */
.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

/* ── Tablet (768px–1199px) ── */
@media (min-width: 768px) and (max-width: 1199px) {
  .gallery-section-header {
    margin-bottom: 8px;
  }

  .section-count-badge {
    font-size: 13px;
  }
}

/* ── Mobile (≤767px) ── */
@media (max-width: 767px) {
  .gallery-section-header {
    margin-bottom: 12px;
  }

  .gallery-section-header h3 {
    font-size: 16px;
  }

  .section-count-badge {
    font-size: 12px;
  }
}
</style>
