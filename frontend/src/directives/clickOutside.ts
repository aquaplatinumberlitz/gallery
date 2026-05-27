import type { DirectiveBinding, ObjectDirective } from 'vue';

interface ClickOutsideElement extends HTMLElement {
  __clickOutsideHandler?: (event: MouseEvent) => void;
}

export const vClickOutside: ObjectDirective<ClickOutsideElement, () => void> = {
  mounted(el: ClickOutsideElement, binding: DirectiveBinding<() => void>) {
    el.__clickOutsideHandler = (event: MouseEvent) => {
      // Check if click was outside the element
      if (!(el === event.target || el.contains(event.target as Node))) {
        binding.value();
      }
    };
    
    // Use setTimeout to avoid immediate trigger on mount
    setTimeout(() => {
      document.addEventListener('click', el.__clickOutsideHandler!);
    }, 0);
  },
  
  unmounted(el: ClickOutsideElement) {
    if (el.__clickOutsideHandler) {
      document.removeEventListener('click', el.__clickOutsideHandler);
      delete el.__clickOutsideHandler;
    }
  },
};

export default vClickOutside;
