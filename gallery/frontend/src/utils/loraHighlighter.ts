function escapeHtml(unsafe: string) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function loraHighlighter(text: string) {
  if (!text) return "";

  // Split string by <lora:...> tokens to avoid per-char replace on long prompts
  const regex = /<lora:([^:>]+)(?::([^>]+))?>/gi;
  let lastIndex = 0;
  let out = "";
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Add plain text before the token
    if (match.index > lastIndex) {
      out += escapeHtml(text.slice(lastIndex, match.index));
    }
    const name = escapeHtml(match[1]);
    const weight = match[2] ? escapeHtml(match[2]) : "";
    out += `<span class="lora-pill">${name}${weight ? `:${weight}` : ""}</span>`;
    lastIndex = regex.lastIndex;
  }

  // Remaining text (if any)
  if (lastIndex < text.length) {
    out += escapeHtml(text.slice(lastIndex));
  }

  return out;
}
