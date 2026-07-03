<script setup lang="ts">
import { Toaster } from "vue-sonner";
import { useGalleryTheme } from "@/composables/useGalleryTheme";
import "vue-sonner/style.css";

const { resolvedTheme } = useGalleryTheme();
</script>

<template>
  <Toaster
    position="bottom-right"
    :theme="resolvedTheme"
    :visible-toasts="3"
    :gap="12"
    :offset="{ right: 24, bottom: 24 }"
    :mobile-offset="{ right: 16, bottom: 16, left: 16 }"
    close-button
    class="gallery-toaster"
    :toast-options="{
      classes: {
        toast: 'gallery-toast',
        title: 'gallery-toast__title',
        description: 'gallery-toast__description',
        closeButton: 'gallery-toast__close',
        actionButton: 'gallery-toast__action',
        icon: 'gallery-toast__icon',
        content: 'gallery-toast__content',
        success: 'gallery-toast--success',
        error: 'gallery-toast--error',
        warning: 'gallery-toast--warning',
        info: 'gallery-toast--info',
      },
    }"
  />
</template>

<style>
.gallery-toaster {
  --width: 420px;
  z-index: 10000 !important;
}

@media (max-width: 480px) {
  .gallery-toaster {
    --width: 100%;
  }
}

.gallery-toast {
  padding: 14px 16px !important;
  border-radius: 12px !important;
  border: none !important;
  border-left: 4px solid var(--toast-accent, var(--gallery-info, #3b82f6)) !important;
  background: var(--gallery-toast-bg, #fff) !important;
  box-shadow:
    0 4px 12px rgba(0, 0, 0, 0.15),
    0 0 1px rgba(0, 0, 0, 0.1) !important;
  gap: 12px !important;
  width: var(--width) !important;
  font-family: inherit !important;
}

.gallery-toast__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.gallery-toast__title {
  font-size: 14px !important;
  font-weight: 600 !important;
  line-height: 1.4 !important;
  color: var(--gallery-toast-title, #1f2937) !important;
}

.gallery-toast__description {
  font-size: 13px !important;
  font-weight: 400 !important;
  line-height: 1.4 !important;
  color: var(--gallery-toast-message, #6b7280) !important;
  margin-top: 2px !important;
}

.gallery-toast__icon {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 32px !important;
  height: 32px !important;
  border-radius: 8px !important;
  background: var(--toast-icon-bg, rgba(59, 130, 246, 0.1)) !important;
  color: var(--toast-icon-color, #3b82f6) !important;
  flex-shrink: 0 !important;
}

[data-sonner-toast][data-styled="true"] .gallery-toast__close[data-close-button] {
  position: static;
  inset: auto;
  order: 10;
  align-self: flex-start;
  margin-left: auto;
  height: 28px;
  width: 28px;
  flex-shrink: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--gallery-toast-dismiss, #9ca3af);
  transform: none;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

[data-sonner-toast][data-styled="true"]:hover .gallery-toast__close[data-close-button]:hover {
  background: color-mix(in srgb, var(--foreground, #111827) 7%, transparent);
  color: var(--gallery-toast-title, #1f2937);
}

[data-sonner-toast][data-styled="true"] .gallery-toast__close[data-close-button]:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring, #3b82f6) 50%, transparent);
}

.gallery-toast__action {
  display: inline-flex !important;
  align-items: center !important;
  margin-top: 8px !important;
  padding: 4px 0 !important;
  border: none !important;
  background: transparent !important;
  color: var(--toast-accent, var(--gallery-info, #3b82f6)) !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  cursor: pointer !important;
  transition: opacity 0.15s ease !important;
  height: auto !important;
  border-radius: 0 !important;
}

.gallery-toast__action:hover {
  opacity: 0.8 !important;
}

/* Variant colors */
.gallery-toast--success {
  --toast-accent: var(--gallery-success, #22c55e);
  --toast-icon-color: var(--gallery-success, #22c55e);
  --toast-icon-bg: var(--gallery-success-bg, rgba(34, 197, 94, 0.1));
}

.gallery-toast--error {
  --toast-accent: var(--gallery-error, #ef4444);
  --toast-icon-color: var(--gallery-error, #ef4444);
  --toast-icon-bg: var(--gallery-error-bg, rgba(239, 68, 68, 0.1));
}

.gallery-toast--warning {
  --toast-accent: var(--gallery-warning, #f59e0b);
  --toast-icon-color: var(--gallery-warning, #f59e0b);
  --toast-icon-bg: var(--gallery-warning-bg, rgba(245, 158, 11, 0.1));
}

.gallery-toast--info {
  --toast-accent: var(--gallery-info, #3b82f6);
  --toast-icon-color: var(--gallery-info, #3b82f6);
  --toast-icon-bg: var(--gallery-info-bg, rgba(59, 130, 246, 0.1));
}

/* Dark mode */
[data-sonner-toaster][data-sonner-theme="dark"] .gallery-toast {
  --gallery-toast-bg: var(--popover, #1f2937);
  --gallery-toast-title: var(--foreground, #f9fafb);
  --gallery-toast-message: var(--muted-foreground, #9ca3af);
  --gallery-toast-dismiss: var(--muted-foreground, #9ca3af);
  box-shadow:
    0 4px 12px rgba(0, 0, 0, 0.4),
    0 0 1px rgba(0, 0, 0, 0.2) !important;
}

[data-sonner-toaster][data-sonner-theme="dark"]
  [data-sonner-toast][data-styled="true"]:hover
  .gallery-toast__close[data-close-button]:hover {
  background: color-mix(in srgb, var(--foreground, #f9fafb) 10%, transparent);
  color: var(--foreground, #f9fafb);
}

/* High contrast mode */
@media (prefers-contrast: high) {
  .gallery-toast {
    border-left-width: 4px !important;
    border-left-style: solid !important;
    border-top: 2px solid var(--toast-accent);
    border-right: 2px solid var(--toast-accent);
    border-bottom: 2px solid var(--toast-accent);
  }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  [data-sonner-toast] {
    transition: opacity 150ms ease !important;
  }
}
</style>
