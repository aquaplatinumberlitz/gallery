/**
 * Purpose: Protect when the search-only chunks (results panel, fuzzy engine) are fetched.
 * Guarantees: Nothing loads on import; the warm-up loads both once the page is loaded and idle, immediately for a URL
 * that carries a search, and on the first text-field focus (once); loads are shared and a failed panel load is retried;
 * cancelling the warm-up stops all of it.
 * Run when: Changing utils/searchChunks.ts or utils/idleAfterLoad.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const panelLoads = vi.fn();
const enginePreloads = vi.fn();
let failPanel = false;

type SearchChunks = typeof import("../searchChunks");

const stops: Array<() => void> = [];

async function freshModule(): Promise<SearchChunks> {
  vi.resetModules();
  panelLoads.mockClear();
  enginePreloads.mockClear();
  vi.doMock("@/components/search/SearchResultsPanelImpl.vue", () => {
    panelLoads();
    if (failPanel) {
      failPanel = false;
      throw new Error("chunk load failed");
    }
    return { default: { name: "SearchResultsPanelImpl", render: () => null } };
  });
  vi.doMock("../fuzzySearch", () => ({
    preloadFuzzySearch: () => {
      enginePreloads();
      return Promise.resolve();
    },
  }));
  const mod = await import("../searchChunks");
  // Remember every warm-up so afterEach can remove the document listeners it adds.
  return {
    ...mod,
    startSearchChunkWarmup: () => {
      const stop = mod.startSearchChunkWarmup();
      stops.push(stop);
      return stop;
    },
  };
}

// Dynamic imports resolve on a later tick than microtasks; wait for the calls instead of guessing a tick count.
const flush = async () => {
  await vi.advanceTimersByTimeAsync(0);
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
};

describe("search chunk warm-up", () => {
  let readyState: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    failPanel = false;
    readyState = Object.getOwnPropertyDescriptor(document, "readyState");
    Object.defineProperty(document, "readyState", { configurable: true, get: () => "complete" });
    window.history.replaceState({}, "", "/");
    window.requestIdleCallback = ((cb: IdleRequestCallback) => setTimeout(() => cb({} as IdleDeadline), 0)) as never;
  });

  afterEach(() => {
    for (const stop of stops.splice(0)) stop();
    vi.useRealTimers();
    if (readyState) Object.defineProperty(document, "readyState", readyState);
    else delete (document as unknown as Record<string, unknown>).readyState;
    window.history.replaceState({}, "", "/");
  });

  it("loads nothing when the module is imported", async () => {
    await freshModule();
    expect(panelLoads).not.toHaveBeenCalled();
    expect(enginePreloads).not.toHaveBeenCalled();
  });

  it("loads the panel and the engine after load + idle, not before", async () => {
    const { startSearchChunkWarmup } = await freshModule();
    startSearchChunkWarmup();

    await vi.advanceTimersByTimeAsync(1000);
    expect(panelLoads).not.toHaveBeenCalled();
    expect(enginePreloads).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(2000);
    await flush();
    expect(panelLoads).toHaveBeenCalledTimes(1);
    expect(enginePreloads).toHaveBeenCalledTimes(1);
  });

  it("loads immediately when the URL carries a search", async () => {
    window.history.replaceState({}, "", "/?q=sunset");
    const { startSearchChunkWarmup } = await freshModule();

    startSearchChunkWarmup();
    await flush();

    expect(panelLoads).toHaveBeenCalledTimes(1);
    expect(enginePreloads).toHaveBeenCalledTimes(1);
  });

  it("loads on the first text-field focus, once, and ignores other elements", async () => {
    const { startSearchChunkWarmup } = await freshModule();
    startSearchChunkWarmup();
    const button = document.createElement("button");
    const input = document.createElement("input");
    document.body.append(button, input);

    button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    await flush();
    expect(panelLoads).not.toHaveBeenCalled();

    input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    await flush();
    expect(panelLoads).toHaveBeenCalledTimes(1);
    expect(enginePreloads).toHaveBeenCalledTimes(1);
    button.remove();
    input.remove();
  });

  it("stops everything when cancelled", async () => {
    const { startSearchChunkWarmup } = await freshModule();
    const stop = startSearchChunkWarmup();
    const input = document.createElement("input");
    document.body.append(input);

    stop();
    input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(10_000);
    await flush();

    expect(panelLoads).not.toHaveBeenCalled();
    expect(enginePreloads).not.toHaveBeenCalled();
    input.remove();
  });

  it("shares one panel load", async () => {
    const { loadSearchResultsPanel } = await freshModule();

    const first = loadSearchResultsPanel();
    expect(loadSearchResultsPanel()).toBe(first);
    await first;

    expect(panelLoads).toHaveBeenCalledTimes(1);
  });

  it("retries the panel load after a failure", async () => {
    const { loadSearchResultsPanel } = await freshModule();
    failPanel = true;

    await expect(loadSearchResultsPanel()).rejects.toThrow();
    await expect(loadSearchResultsPanel()).resolves.toBeDefined();
  });
});
