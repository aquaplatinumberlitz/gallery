import { defineStore } from "pinia";
import { ref } from "vue";
import { toast as sonnerToast } from "vue-sonner";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastOptions {
  type?: ToastType;
  title: string;
  message?: string;
  duration?: number;
  html?: boolean;
  action?: {
    label: string;
    onClick: () => void;
  };
  dismissible?: boolean;
}

const DURATION = {
  SHORT: 4000,
  DEFAULT: 4000,
  MEDIUM: 4000,
  LONG: 4000,
} as const;

const DEFAULT_DURATION = DURATION.DEFAULT;

export const useToastStore = defineStore("toast", () => {
  const activeIds = ref<string[]>([]);

  const generateId = () => `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  const forgetToast = (id: string) => {
    const idx = activeIds.value.indexOf(id);
    if (idx !== -1) activeIds.value.splice(idx, 1);
  };

  const removeToast = (id: string) => {
    forgetToast(id);
    sonnerToast.dismiss(id);
  };

  const clearAll = () => {
    const ids = [...activeIds.value];
    activeIds.value = [];
    ids.forEach((id) => sonnerToast.dismiss(id));
  };

  const addToast = (options: ToastOptions): string => {
    const id = generateId();
    const type = options.type ?? "info";
    const duration = options.duration ?? DEFAULT_DURATION;

    const sonnerData: Record<string, unknown> = {
      id,
      duration: duration > 0 ? duration : Infinity,
      dismissible: options.dismissible ?? true,
      description: options.message,
      onDismiss: () => forgetToast(id),
      onAutoClose: () => forgetToast(id),
    };

    if (options.action) {
      sonnerData.action = {
        label: options.action.label,
        onClick: () => options.action!.onClick(),
      };
    }

    switch (type) {
      case "success":
        sonnerToast.success(options.title, sonnerData);
        break;
      case "error":
        sonnerToast.error(options.title, sonnerData);
        break;
      case "warning":
        sonnerToast.warning(options.title, sonnerData);
        break;
      default:
        sonnerToast.info(options.title, sonnerData);
    }

    activeIds.value.push(id);
    return id;
  };

  const success = (title: string, message?: string, options?: Partial<ToastOptions>) =>
    addToast({ type: "success", title, message, duration: DURATION.DEFAULT, ...options });

  const error = (title: string, message?: string, options?: Partial<ToastOptions>) =>
    addToast({ type: "error", title, message, duration: DURATION.LONG, ...options });

  const warning = (title: string, message?: string, options?: Partial<ToastOptions>) =>
    addToast({ type: "warning", title, message, duration: DURATION.MEDIUM, ...options });

  const info = (title: string, message?: string, options?: Partial<ToastOptions>) =>
    addToast({ type: "info", title, message, duration: DURATION.DEFAULT, ...options });

  return {
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
