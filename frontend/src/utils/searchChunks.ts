/**
 * Purpose: Load the search-only code (the results panel and the fuzzy-search engine with fuse.js) off the home route's
 * critical path, and have it ready before anyone searches.
 * Guarantees: Nothing here is imported statically by the home graph except this small module. The chunks are fetched
 * (a) when the first search results panel renders, (b) as soon as the URL carries a search, (c) the first time a text
 * field gets focus (the user is about to search), and (d) once the page has loaded and gone idle. Loads are shared
 * and memoised; a failed load is retried on the next request.
 * Run when: Adding another search-only module (route it through here) or changing when search code is warmed.
 */
import { preloadFuzzySearch } from "./fuzzySearch";
import { whenBrowserIdleAfterLoad } from "./idleAfterLoad";

let panelLoad: Promise<typeof import("@/components/search/SearchResultsPanelImpl.vue")> | null = null;

/** Loader for the results panel implementation (also the `defineAsyncComponent` loader of SearchResultsPanel). */
export function loadSearchResultsPanel() {
  panelLoad ??= import("@/components/search/SearchResultsPanelImpl.vue").catch((error: unknown) => {
    panelLoad = null; // allow a retry
    throw error;
  });
  return panelLoad;
}

/** Fetch every search-only chunk. Best effort: errors surface when the code is actually needed. */
export function warmSearchChunks(): Promise<void> {
  return Promise.all([loadSearchResultsPanel().catch(() => undefined), preloadFuzzySearch()]).then(() => undefined);
}

const SEARCH_URL_PARAMS = ["q", "wf"] as const;

function urlCarriesSearch(): boolean {
  const params = new URLSearchParams(window.location.search);
  return SEARCH_URL_PARAMS.some((key) => params.has(key));
}

function isTextField(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

/**
 * Warm the search chunks at the right moments (see the module comment). Call once when the gallery route mounts.
 * Returns a function that cancels everything that is still pending.
 */
export function startSearchChunkWarmup(): () => void {
  if (urlCarriesSearch()) void warmSearchChunks();

  const cancelIdle = whenBrowserIdleAfterLoad(() => void warmSearchChunks());
  const onFocus = (event: FocusEvent) => {
    if (!isTextField(event.target)) return;
    document.removeEventListener("focusin", onFocus, true);
    void warmSearchChunks();
  };
  document.addEventListener("focusin", onFocus, true);

  return () => {
    cancelIdle();
    document.removeEventListener("focusin", onFocus, true);
  };
}
