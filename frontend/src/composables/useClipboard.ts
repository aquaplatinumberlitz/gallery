import { ref } from 'vue'
import { useToast } from './useToast'

export function useClipboard() {
  const toast = useToast()
  const copyStatus = ref<Record<string, boolean>>({})

  function getCopyLabel(id: string): string {
    switch (id) {
      case 'prompt': return 'Prompt';
      case 'neg': return 'Negative prompt';
      case 'seed': return 'Seed';
      default: return 'Text';
    }
  }

  async function copyText(text: string | undefined, id: string) {
    if (!text) return;
    try {
      const str = String(text);

      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(str);
      } else {
        // Fallback cho HTTP — clipboard API không khả dụng
        const textarea = document.createElement('textarea');
        textarea.value = str;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }

      copyStatus.value[id] = true;
      const label = getCopyLabel(id);
      toast.success(`${label} copied`, 'Copied to clipboard', { duration: 3000 });
      setTimeout(() => {
        copyStatus.value[id] = false;
      }, 1500);
    } catch (e) {
      console.error("Copy failed", e);
      toast.error('Copy failed', 'Unable to copy to clipboard');
    }
  }

  return { copyStatus, copyText }
}
