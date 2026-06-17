/**
 * Purpose:
 * Provides gated debug logging for lightbox navigation index/path synchronization.
 *
 * Guarantees:
 * * navigation logs are off unless debug-lightbox-nav or window flag enables them
 * * logs include enough item/index context to identify double navigation or data reordering
 *
 * Run when:
 * * debugging Library Inspector lightbox swipes that skip images or desync counters
 * * changing lightbox store navigation, PhotoSwipe events, or inspector lightbox item mapping
 */

type LightboxNavDebugItem = {
  path: string;
  name?: string;
  type?: string;
};

declare global {
  interface Window {
    __GALLERY_DEBUG_LIGHTBOX_NAV?: boolean;
  }
}

let sequence = 0;
let startedAt = 0;

export function isLightboxNavDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return window.__GALLERY_DEBUG_LIGHTBOX_NAV === true || window.localStorage.getItem("debug-lightbox-nav") === "true";
}

function itemLabel(item: LightboxNavDebugItem | undefined) {
  if (!item) return null;
  return {
    name: item.name || item.path.split("/").pop() || "",
    path: item.path,
  };
}

export function summarizeLightboxItems(items: LightboxNavDebugItem[], focusIndex = -1, radius = 3) {
  const imageItems = items.filter((item) => item.type === undefined || item.type === "image");
  const pathCounts = new Map<string, number>();
  for (const item of imageItems) {
    pathCounts.set(item.path, (pathCounts.get(item.path) ?? 0) + 1);
  }
  const duplicatePaths = Array.from(pathCounts.entries())
    .filter(([, count]) => count > 1)
    .map(([path, count]) => ({ path, count }));

  const start = focusIndex >= 0 ? Math.max(0, focusIndex - radius) : 0;
  const end =
    focusIndex >= 0
      ? Math.min(imageItems.length, focusIndex + radius + 1)
      : Math.min(imageItems.length, radius * 2 + 1);

  return {
    totalItems: items.length,
    imageItems: imageItems.length,
    focusIndex,
    focusItem: itemLabel(imageItems[focusIndex]),
    window: imageItems.slice(start, end).map((item, offset) => ({
      index: start + offset,
      ...itemLabel(item),
    })),
    duplicatePaths,
  };
}

export function lightboxItemAt(items: LightboxNavDebugItem[], index: number) {
  const imageItems = items.filter((item) => item.type === "image");
  return itemLabel(imageItems[index]);
}

export function logLightboxNavDebug(event: string, payload: Record<string, unknown> = {}): void {
  if (!isLightboxNavDebugEnabled()) return;
  const now = Date.now();
  if (!startedAt) startedAt = now;
  sequence += 1;
  console.info(
    "[lightbox-nav-debug]",
    JSON.stringify({
      seq: sequence,
      at_ms: now,
      rel_ms: now - startedAt,
      event,
      ...payload,
    }),
  );
}
