/**
 * Run `callback` once the page has finished loading, a short settle delay has passed, and the
 * browser is idle.
 *
 * Used to warm non-critical UI (lazy chunks) after the first paint without competing with the
 * critical path: the `load` event can fire before the first thumbnails (the LCP element) have
 * arrived, so the settle delay keeps the warm-up from sharing bandwidth with them on slow links.
 * Falls back to a timeout where `requestIdleCallback` is missing (Safari).
 * Returns a function that cancels the pending callback.
 */
export function whenBrowserIdleAfterLoad(callback: () => void, settleMs = 1500, idleTimeoutMs = 2000): () => void {
  let cancelled = false;
  let idleHandle: number | null = null;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let settleHandle: ReturnType<typeof setTimeout> | null = null;

  const run = () => {
    if (!cancelled) callback();
  };
  const scheduleIdle = () => {
    if (cancelled) return;
    if (typeof window.requestIdleCallback === "function") {
      idleHandle = window.requestIdleCallback(run, { timeout: idleTimeoutMs });
    } else {
      timeoutHandle = setTimeout(run, 200);
    }
  };
  const settleThenIdle = () => {
    settleHandle = setTimeout(scheduleIdle, settleMs);
  };
  const onLoad = () => settleThenIdle();

  if (document.readyState === "complete") {
    settleThenIdle();
  } else {
    window.addEventListener("load", onLoad, { once: true });
  }

  return () => {
    cancelled = true;
    window.removeEventListener("load", onLoad);
    if (idleHandle !== null && typeof window.cancelIdleCallback === "function") window.cancelIdleCallback(idleHandle);
    if (timeoutHandle !== null) clearTimeout(timeoutHandle);
    if (settleHandle !== null) clearTimeout(settleHandle);
  };
}
