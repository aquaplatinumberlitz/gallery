import { ref } from "vue";
import { useToast } from "./useToast";

interface CopyTextOptions {
  fallbackRoot?: Element | null;
}

const INTERACTIVE_FALLBACK_ROOT_SELECTOR = [
  "button",
  "input",
  "select",
  "textarea",
  "a[href]",
  '[role="button"]',
  '[role="menuitem"]',
  '[role="option"]',
].join(", ");

const STABLE_FALLBACK_ROOT_SELECTOR = [
  '[data-slot="dropdown-menu-content"]',
  '[data-slot="popover-content"]',
  '[role="menu"]',
  '[role="dialog"]',
  ".pswp.pswp--open",
  ".lightbox-overlay",
].join(", ");

export function useClipboard() {
  const toast = useToast();
  const copyStatus = ref<Record<string, boolean>>({});

  function getCopyLabel(id: string): string {
    if (id.startsWith("seed:")) return "Seed";
    switch (id) {
      case "prompt":
        return "Prompt";
      case "neg":
        return "Negative prompt";
      case "seed":
        return "Seed";
      case "path":
        return "Path";
      case "loras":
        return "LoRA list";
      case "metadata":
        return "Metadata";
      default:
        return "Text";
    }
  }

  function getValidFallbackRoot(candidate?: Element | null) {
    if (!(candidate instanceof HTMLElement) || !candidate.isConnected) {
      return document.body;
    }

    if (!candidate.matches(INTERACTIVE_FALLBACK_ROOT_SELECTOR)) {
      return candidate;
    }

    const stableRoot = candidate.closest<HTMLElement>(STABLE_FALLBACK_ROOT_SELECTOR);
    if (stableRoot?.isConnected && !stableRoot.matches(INTERACTIVE_FALLBACK_ROOT_SELECTOR)) {
      return stableRoot;
    }

    return candidate.parentElement?.isConnected ? candidate.parentElement : document.body;
  }

  async function writeClipboardText(text: string, options: CopyTextOptions = {}) {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch {
        // Fall through to the DOM fallback. Some embedded/insecure contexts
        // expose the async Clipboard API but reject writes.
      }
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "-9999px";
    textarea.style.opacity = "0";
    const fallbackRoot = getValidFallbackRoot(options.fallbackRoot);
    fallbackRoot.appendChild(textarea);

    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousSelection = document.getSelection()?.rangeCount ? document.getSelection()?.getRangeAt(0) : null;
    textarea.focus();
    textarea.select();

    try {
      const hasTextareaSelection =
        document.activeElement === textarea &&
        textarea.selectionStart === 0 &&
        textarea.selectionEnd === textarea.value.length;
      if (!hasTextareaSelection) throw new Error("Clipboard fallback could not retain textarea selection");
      const copied = document.execCommand?.("copy") === true;
      if (!copied) throw new Error("Clipboard fallback returned false");
    } finally {
      if (previousActiveElement?.isConnected) {
        previousActiveElement.focus({ preventScroll: true });
      }
      textarea.remove();
      if (previousSelection) {
        const selection = document.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(previousSelection);
      }
    }
  }

  async function copyText(text: string | undefined, id: string, options: CopyTextOptions = {}): Promise<boolean> {
    if (!text) return false;
    try {
      await writeClipboardText(String(text), options);

      copyStatus.value[id] = true;
      const label = getCopyLabel(id);
      toast.success(`${label} copied`, "Copied to clipboard", { duration: 3000 });
      setTimeout(() => {
        copyStatus.value[id] = false;
      }, 1500);
      return true;
    } catch (e) {
      console.error("Copy failed", e);
      toast.error("Copy failed", "Unable to copy to clipboard");
      return false;
    }
  }

  return { copyStatus, copyText };
}
