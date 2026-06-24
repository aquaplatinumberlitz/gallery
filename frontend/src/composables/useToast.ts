import { useToastStore } from "../stores/toast";
import type { ToastOptions } from "../stores/toast";

export function useToast() {
  const store = useToastStore();

  return {
    success: (title: string, message?: string, options?: Partial<ToastOptions>) =>
      store.success(title, message, options),

    error: (title: string, message?: string, options?: Partial<ToastOptions>) => store.error(title, message, options),

    warning: (title: string, message?: string, options?: Partial<ToastOptions>) =>
      store.warning(title, message, options),

    info: (title: string, message?: string, options?: Partial<ToastOptions>) => store.info(title, message, options),

    show: (options: ToastOptions) => store.addToast(options),

    dismiss: (id: string) => store.removeToast(id),

    clear: () => store.clearAll(),

    promise: async <T>(
      promise: Promise<T>,
      options: {
        loading: string;
        success: string | ((data: T) => string);
        error: string | ((err: unknown) => string);
      },
    ): Promise<T> => {
      const loadingId = store.info(options.loading, undefined, { duration: 0, dismissible: false });

      try {
        const result = await promise;
        store.removeToast(loadingId);
        const successMessage = typeof options.success === "function" ? options.success(result) : options.success;
        store.success(successMessage);
        return result;
      } catch (err) {
        store.removeToast(loadingId);
        const errorMessage = typeof options.error === "function" ? options.error(err) : options.error;
        store.error(errorMessage);
        throw err;
      }
    },
  };
}
