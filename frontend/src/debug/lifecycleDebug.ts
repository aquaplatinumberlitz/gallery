/**
 * Purpose:
 * Provides DEV-only page lifecycle logging for browser navigation and visibility events.
 *
 * Guarantees:
 * * lifecycle logs install only in DEV builds through the caller in main.ts
 * * no beforeunload or unload listeners are added, preserving bfcache behavior
 *
 * Run when:
 * * debugging mobile tab switches, pagehide/pageshow behavior, or unexpected reloads
 * * changing app boot diagnostics or lifecycle debug logging
 */

export function installLifecycleDebug(): void {
  window.addEventListener("pageshow", (event) => {
    console.log("[LIFECYCLE] pageshow", {
      persisted: event.persisted,
      timestamp: Date.now(),
      navType: (performance as any)?.getEntriesByType?.("navigation")?.[0]?.type,
    });
  });

  window.addEventListener("pagehide", (event) => {
    console.log("[LIFECYCLE] pagehide", {
      persisted: event.persisted,
      timestamp: Date.now(),
    });
  });

  document.addEventListener("visibilitychange", () => {
    console.log("[LIFECYCLE] visibilitychange", {
      state: document.visibilityState,
      timestamp: Date.now(),
    });
  });

  window.addEventListener("freeze", () => {
    console.log("[LIFECYCLE] freeze", { timestamp: Date.now() });
  });

  window.addEventListener("resume", () => {
    console.log("[LIFECYCLE] resume", { timestamp: Date.now() });
  });
}
