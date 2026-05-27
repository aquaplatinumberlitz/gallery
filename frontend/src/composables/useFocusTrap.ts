/**
 * Focus Trap Composable for Modal Dialogs
 * Following Apple HIG & WCAG 2.1 Guidelines
 * 
 * Ensures keyboard focus stays within modal when open
 */

import { onMounted, onUnmounted, type Ref } from 'vue';

const FOCUSABLE_SELECTORS = [
  'button:not([disabled]):not([tabindex="-1"])',
  'a[href]:not([tabindex="-1"])',
  'input:not([disabled]):not([tabindex="-1"])',
  'select:not([disabled]):not([tabindex="-1"])',
  'textarea:not([disabled]):not([tabindex="-1"])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(', ');

export function useFocusTrap(containerRef: Ref<HTMLElement | null>, options?: {
  initialFocus?: Ref<HTMLElement | null>;
  returnFocus?: boolean;
}) {
  const { initialFocus, returnFocus = true } = options || {};
  
  let previouslyFocusedElement: HTMLElement | null = null;

  const getFocusableElements = (): HTMLElement[] => {
    if (!containerRef.value) return [];
    return Array.from(
      containerRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)
    ).filter(el => {
      // Additional visibility checks
      return el.offsetParent !== null && !el.hasAttribute('inert');
    });
  };

  const getFirstFocusable = (): HTMLElement | null => {
    const elements = getFocusableElements();
    return elements[0] || null;
  };

  const getLastFocusable = (): HTMLElement | null => {
    const elements = getFocusableElements();
    return elements[elements.length - 1] || null;
  };

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return;

    const focusableElements = getFocusableElements();
    if (focusableElements.length === 0) {
      event.preventDefault();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    const activeElement = document.activeElement as HTMLElement;

    // Shift + Tab: Going backwards
    if (event.shiftKey) {
      if (activeElement === firstElement || !containerRef.value?.contains(activeElement)) {
        event.preventDefault();
        lastElement.focus();
      }
    } 
    // Tab: Going forwards
    else {
      if (activeElement === lastElement || !containerRef.value?.contains(activeElement)) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  };

  const activate = () => {
    // Store current focus
    previouslyFocusedElement = document.activeElement as HTMLElement;

    // Add event listener
    document.addEventListener('keydown', handleKeyDown);

    // Set initial focus
    requestAnimationFrame(() => {
      if (initialFocus?.value) {
        initialFocus.value.focus();
      } else {
        const firstFocusable = getFirstFocusable();
        if (firstFocusable) {
          firstFocusable.focus();
        } else {
          // Fallback: focus container itself
          containerRef.value?.focus();
        }
      }
    });
  };

  const deactivate = () => {
    document.removeEventListener('keydown', handleKeyDown);

    // Return focus to previously focused element
    if (returnFocus && previouslyFocusedElement) {
      requestAnimationFrame(() => {
        previouslyFocusedElement?.focus();
      });
    }
  };

  return {
    activate,
    deactivate,
    getFocusableElements,
    getFirstFocusable,
    getLastFocusable,
  };
}

/**
 * Auto-activating focus trap (for use with v-if modals)
 */
export function useAutoFocusTrap(containerRef: Ref<HTMLElement | null>, options?: {
  initialFocus?: Ref<HTMLElement | null>;
  returnFocus?: boolean;
}) {
  const trap = useFocusTrap(containerRef, options);

  onMounted(() => {
    trap.activate();
  });

  onUnmounted(() => {
    trap.deactivate();
  });

  return trap;
}
