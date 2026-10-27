/**
 * Purpose:
 * Decides whether the floating TanStack Query Devtools button is mounted.
 *
 * Guarantees:
 * * Devtools are opt-in: `VITE_DEVTOOLS=true`, `?devtools=1`, or the persisted
 *   `gallery-debug-query-devtools` flag. Plain Vite dev mode does not show them,
 *   because the shared VPS serves the Vite dev server to real phone/tablet users
 *   and the floating button covers the lightbox Info button and the mobile dock.
 * * `?devtools=0` clears the persisted opt-in.
 * * Storage failures (Safari Private Browsing) fall back to "off".
 *
 * Run when:
 * * changing how Query Devtools are enabled or where the button renders
 */

export const QUERY_DEVTOOLS_STORAGE_KEY = "gallery-debug-query-devtools";

export function shouldShowQueryDevtools(
  env: { VITE_DEVTOOLS?: unknown } = import.meta.env as { VITE_DEVTOOLS?: unknown },
  search: string = typeof window === "undefined" ? "" : window.location.search,
): boolean {
  if (env.VITE_DEVTOOLS === "true") return true;

  const param = new URLSearchParams(search).get("devtools");
  try {
    if (param === "1") {
      localStorage.setItem(QUERY_DEVTOOLS_STORAGE_KEY, "1");
      return true;
    }
    if (param === "0") {
      localStorage.removeItem(QUERY_DEVTOOLS_STORAGE_KEY);
      return false;
    }
    return localStorage.getItem(QUERY_DEVTOOLS_STORAGE_KEY) === "1";
  } catch {
    return param === "1";
  }
}
