/**
 * Purpose: Synchronous fuzzy filename search for the gallery grid, with fuse.js kept out of the home route's
 * static import graph (about 9 KB gzip that every cold load downloaded before it could mount).
 * Guarantees: `fuzzySearchFileNodes` keeps its synchronous signature. The engine (`fuzzySearchEngine.ts`, which imports
 * fuse.js) loads on first use or through `preloadFuzzySearch()`. Until it has loaded, a non-empty query returns the
 * list unfiltered, and the loading flips a reactive flag that this function reads, so every computed that called it
 * re-evaluates with real matches the moment the engine arrives. An empty query never touches the engine. A failed
 * load is retried on the next call.
 * Run when: Changing how or when the fuzzy engine loads; the matching rules live in fuzzySearchEngine.ts.
 */
import { shallowRef } from "vue";
import type { FileNode } from "../types";

type Engine = typeof import("./fuzzySearchEngine");
type FuzzySearchOptions = Parameters<Engine["fuzzySearchFileNodes"]>[2];

let engine: Engine | null = null;
let loading: Promise<void> | null = null;
// Read inside fuzzySearchFileNodes so Vue computeds that call it depend on the engine becoming available.
const engineReady = shallowRef(false);

/** Start (or join) the engine download. Resolves once it is usable; never rejects. */
export function preloadFuzzySearch(): Promise<void> {
  if (engine) return Promise.resolve();
  loading ??= import("./fuzzySearchEngine").then(
    (loaded) => {
      engine = loaded;
      engineReady.value = true;
    },
    () => {
      loading = null; // allow a retry on the next call
    },
  );
  return loading;
}

export function fuzzySearchFileNodes(items: FileNode[], query: string, options?: FuzzySearchOptions): FileNode[] {
  if (!query.trim()) return items;
  if (!engineReady.value || !engine) {
    void preloadFuzzySearch();
    return items;
  }
  return engine.fuzzySearchFileNodes(items, query, options);
}
