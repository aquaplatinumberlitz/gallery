export const LIGHTBOX_PERF_MARKS = {
  openStart: "gallery:lightbox-open-start",
  overlayPainted: "gallery:lightbox-overlay-painted",
  transitionStart: "gallery:lightbox-transition-start",
} as const;

function replacePerformanceMark(name: string): void {
  if (typeof performance === "undefined" || typeof performance.mark !== "function") return;
  performance.clearMarks(name);
  performance.mark(name);
}

export function markLightboxOverlayPainted(): void {
  replacePerformanceMark(LIGHTBOX_PERF_MARKS.overlayPainted);
}

export function markLightboxTransitionStart(): void {
  replacePerformanceMark(LIGHTBOX_PERF_MARKS.transitionStart);
}
