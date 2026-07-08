import { ref } from "vue";
import { useToast } from "./useToast";

export function useClipboard() {
  const toast = useToast();
  const copyStatus = ref<Record<string, boolean>>({});

  function getCopyLabel(id: string): string {
    switch (id) {
      case "prompt":
        return "Prompt";
      case "neg":
        return "Negative prompt";
      case "seed":
        return "Seed";
      case "path":
        return "Path";
      default:
        return "Text";
    }
  }

  async function writeClipboardText(text: string) {
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
    document.body.appendChild(textarea);

    const previousSelection = document.getSelection()?.rangeCount ? document.getSelection()?.getRangeAt(0) : null;
    textarea.focus();
    textarea.select();

    try {
      const copied = document.execCommand?.("copy") === true;
      if (!copied) throw new Error("Clipboard fallback returned false");
    } finally {
      textarea.remove();
      if (previousSelection) {
        const selection = document.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(previousSelection);
      }
    }
  }

  async function copyText(text: string | undefined, id: string) {
    if (!text) return;
    try {
      await writeClipboardText(String(text));

      copyStatus.value[id] = true;
      const label = getCopyLabel(id);
      toast.success(`${label} copied`, "Copied to clipboard", { duration: 3000 });
      setTimeout(() => {
        copyStatus.value[id] = false;
      }, 1500);
    } catch (e) {
      console.error("Copy failed", e);
      toast.error("Copy failed", "Unable to copy to clipboard");
    }
  }

  return { copyStatus, copyText };
}
