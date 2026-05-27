import { useToastStore } from '../stores/toast';
import type { ToastOptions } from '../stores/toast';

/**
 * Composable for easy toast notifications
 * Usage:
 *   const toast = useToast();
 *   toast.success('Title', 'Message');
 *   toast.error('Error', 'Something went wrong', { action: { label: 'Retry', onClick: () => {} } });
 */
export function useToast() {
  const store = useToastStore();

  return {
    /**
     * Show a success toast
     */
    success: (title: string, message?: string, options?: Partial<ToastOptions>) => {
      return store.success(title, message, options);
    },

    /**
     * Show an error toast (stays longer by default)
     */
    error: (title: string, message?: string, options?: Partial<ToastOptions>) => {
      return store.error(title, message, options);
    },

    /**
     * Show a warning toast
     */
    warning: (title: string, message?: string, options?: Partial<ToastOptions>) => {
      return store.warning(title, message, options);
    },

    /**
     * Show an info toast
     */
    info: (title: string, message?: string, options?: Partial<ToastOptions>) => {
      return store.info(title, message, options);
    },

    /**
     * Show a custom toast
     */
    show: (options: ToastOptions) => {
      return store.addToast(options);
    },

    /**
     * Dismiss a specific toast by ID
     */
    dismiss: (id: string) => {
      store.removeToast(id);
    },

    /**
     * Clear all toasts
     */
    clear: () => {
      store.clearAll();
    },

    /**
     * Promise-based toast: shows loading, then success/error based on promise result
     */
    promise: async <T>(
      promise: Promise<T>,
      options: {
        loading: string;
        success: string | ((data: T) => string);
        error: string | ((err: unknown) => string);
      }
    ): Promise<T> => {
      const loadingId = store.info(options.loading, undefined, { duration: 0, dismissible: false });
      
      try {
        const result = await promise;
        store.removeToast(loadingId);
        const successMessage = typeof options.success === 'function' 
          ? options.success(result) 
          : options.success;
        store.success(successMessage);
        return result;
      } catch (err) {
        store.removeToast(loadingId);
        const errorMessage = typeof options.error === 'function' 
          ? options.error(err) 
          : options.error;
        store.error(errorMessage);
        throw err;
      }
    },
  };
}

export default useToast;
