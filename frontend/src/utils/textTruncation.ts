/**
 * Pixel-based middle truncation for identifiers (model names, filenames)
 * where the tail (version, extension) carries the distinguishing information
 * a user scans for. Tail-ellipsis hides exactly that part, so we keep the head
 * and the tail and collapse the middle into a single ellipsis.
 *
 * `text-overflow: middle-ellipsis` is not yet shipped by default in most
 * browsers (Chrome only behind flag, Firefox/Safari unsupported as of 2026),
 * so we measure with a canvas and truncate in JS for consistent cross-browser
 * behavior.
 */

let measureCanvas: HTMLCanvasElement | null = null;
let cachedFont: string | null = null;

function getCanvas(font: string): CanvasRenderingContext2D | null {
  if (typeof document === "undefined") return null;
  if (!measureCanvas) measureCanvas = document.createElement("canvas");
  const ctx = measureCanvas.getContext("2d");
  if (!ctx) return null;
  if (cachedFont !== font) {
    ctx.font = font;
    cachedFont = font;
  }
  return ctx;
}

function parseFontSize(font: string): number {
  const match = font.match(/(\d+(?:\.\d+)?)px/i);
  return match ? parseFloat(match[1]!) : 13;
}

function measureWidth(text: string, font: string): number {
  const ctx = getCanvas(font);
  if (!ctx) {
    // jsdom has no canvas 2d context; approximate with an average glyph width.
    const fontSize = parseFontSize(font);
    return text.length * 0.62 * fontSize;
  }
  return ctx.measureText(text).width;
}

const truncateCache = new Map<string, string>();

/**
 * Truncate `text` in the middle so the result fits within `maxWidthPx` at the
 * given CSS `font` string (e.g. "500 13px ui-sans-serif, system-ui"). The tail
 * is favored at `tailRatio` (default 0.6) because the trailing characters
 * (version, `_vae`, extension) are usually the part users compare.
 *
 * Results are cached by `${text}|${maxWidthPx}|${font}|${tailRatio}`.
 */
export function fitMiddleTruncate(
  text: string,
  maxWidthPx: number,
  font: string,
  tailRatio = 0.6,
  ellipsis = "\u2026",
): string {
  const cacheKey = `${text}|${maxWidthPx}|${font}|${tailRatio}`;
  const cached = truncateCache.get(cacheKey);
  if (cached !== undefined) return cached;

  const fullWidth = measureWidth(text, font);
  if (fullWidth <= maxWidthPx) {
    truncateCache.set(cacheKey, text);
    return text;
  }

  const ellipsisWidth = measureWidth(ellipsis, font);
  const available = maxWidthPx - ellipsisWidth;
  let result: string;
  if (available <= 0) {
    result = ellipsis;
  } else {
    const tailBudget = available * tailRatio;
    const headBudget = available - tailBudget;

    let tailChars = 0;
    let tailUsed = 0;
    for (let i = text.length - 1; i >= 0 && tailChars < text.length; i--) {
      const w = measureWidth(text[i]!, font);
      if (tailUsed + w > tailBudget) break;
      tailUsed += w;
      tailChars++;
    }

    let headChars = 0;
    let headUsed = 0;
    for (let i = 0; i < text.length - tailChars; i++) {
      const w = measureWidth(text[i]!, font);
      if (headUsed + w > headBudget) break;
      headUsed += w;
      headChars++;
    }

    if (headChars + tailChars >= text.length) {
      result = text;
    } else if (headChars === 0 && tailChars === 0) {
      result = ellipsis;
    } else {
      result = text.slice(0, headChars) + ellipsis + text.slice(text.length - tailChars);
    }
  }

  truncateCache.set(cacheKey, result);
  return result;
}

/**
 * Resolve the CSS font string for table cells. Reads the computed font of
 * `document.body` once and caches it, falling back to a sensible default when
 * the DOM is unavailable (e.g. jsdom in unit tests).
 */
let resolvedFont: string | null = null;

export function tableCellFont(fontWeight = 500, fontSize = 13): string {
  if (resolvedFont) return resolvedFont;
  const family = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  if (typeof document === "undefined" || !document.body) {
    resolvedFont = `${fontWeight} ${fontSize}px ${family}`;
    return resolvedFont;
  }
  const cs = getComputedStyle(document.body);
  const resolvedFamily = cs.fontFamily || family;
  resolvedFont = `${fontWeight} ${fontSize}px ${resolvedFamily}`;
  return resolvedFont;
}
