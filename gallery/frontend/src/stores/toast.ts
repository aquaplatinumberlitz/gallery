import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number; // ms, 0 = persistent
  html?: boolean; // Allow HTML in message
  action?: {
    label: string;
    onClick: () => void;
  };
  dismissible?: boolean;
  createdAt: number;
}

export interface ToastOptions {
  type?: ToastType;
  title: string;
  message?: string;
  duration?: number;
  html?: boolean; // Allow HTML in message
  action?: {
    label: string;
    onClick: () => void;
  };
  dismissible?: boolean;
}

// Big Tech standard durations
const DURATION = {
  SHORT: 3000,    // Quick feedback (copy, simple success)
  DEFAULT: 4000,  // Standard success/info
  MEDIUM: 6000,   // Warnings
  LONG: 10000,    // Errors, toasts with actions
} as const;

const DEFAULT_DURATION = DURATION.DEFAULT;
const MAX_TOASTS = 3;

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([]);
  
  // Generate unique ID
  const generateId = () => `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  
  // Active toasts (limited)
  const activeToasts = computed(() => toasts.value.slice(0, MAX_TOASTS));
  
  // Add toast
  const addToast = (options: ToastOptions): string => {
    const id = generateId();
    
    const toast: Toast = {
      id,
      type: options.type ?? 'info',
      title: options.title,
      message: options.message,
      duration: options.duration ?? DEFAULT_DURATION,
      html: options.html ?? false,
      action: options.action,
      dismissible: options.dismissible ?? true,
      createdAt: Date.now(),
    };
    
    toasts.value.push(toast);
    
    // Auto-remove after duration (if not persistent)
    if (toast.duration && toast.duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, toast.duration);
    }
    
    return id;
  };
  
  // Remove toast by ID
  const removeToast = (id: string) => {
    const index = toasts.value.findIndex(t => t.id === id);
    if (index !== -1) {
      toasts.value.splice(index, 1);
    }
  };
  
  // Clear all toasts
  const clearAll = () => {
    toasts.value = [];
  };
  
  // Convenience methods
  const success = (title: string, message?: string, options?: Partial<ToastOptions>) => {
    return addToast({ 
      type: 'success', 
      title, 
      message, 
      duration: DURATION.DEFAULT,
      ...options 
    });
  };
  
  const error = (title: string, message?: string, options?: Partial<ToastOptions>) => {
    return addToast({ 
      type: 'error', 
      title, 
      message, 
      duration: DURATION.LONG, // Errors stay longer for user to read
      ...options 
    });
  };
  
  const warning = (title: string, message?: string, options?: Partial<ToastOptions>) => {
    return addToast({ 
      type: 'warning', 
      title, 
      message, 
      duration: DURATION.MEDIUM,
      ...options 
    });
  };
  
  const info = (title: string, message?: string, options?: Partial<ToastOptions>) => {
    return addToast({ 
      type: 'info', 
      title, 
      message, 
      duration: DURATION.DEFAULT,
      ...options 
    });
  };
  
  return {
    toasts,
    activeToasts,
    addToast,
    removeToast,
    clearAll,
    success,
    error,
    warning,
    info,
    DURATION,
  };
});
