/**
 * Purpose: Protect the lazy loading of the fuzzy-search engine (fuse.js stays out of the home route's static graph).
 * Guarantees: Importing the facade does not load the engine; an empty query never loads it; a non-empty query before it
 * has loaded returns the list unfiltered, starts the load, and re-evaluates dependent computeds with real matches when
 * it arrives; after loading the facade matches exactly like the engine; a failed load is retried; and fuse.js is imported
 * by the engine module only.
 * Run when: Changing utils/fuzzySearch.ts, utils/fuzzySearchEngine.ts, or the places that import fuse.js.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { computed, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FileNode } from "@/types";

const node = (name: string): FileNode => ({ name, path: `/root/${name}`, type: "image" });
const nodes = [node("apple.png"), node("banana.png"), node("cherry.png")];

const engineLoads = vi.fn();
let failNextLoad = false;

async function freshFacade() {
  vi.resetModules();
  engineLoads.mockClear();
  vi.doMock("../fuzzySearchEngine", async () => {
    engineLoads();
    if (failNextLoad) {
      failNextLoad = false;
      throw new Error("chunk load failed");
    }
    return await vi.importActual<typeof import("../fuzzySearchEngine")>("../fuzzySearchEngine");
  });
  return import("../fuzzySearch");
}

describe("fuzzySearch facade", () => {
  beforeEach(() => {
    failNextLoad = false;
  });
  afterEach(() => {
    vi.doUnmock("../fuzzySearchEngine");
  });

  it("does not load the engine on import or for an empty query", async () => {
    const { fuzzySearchFileNodes } = await freshFacade();

    expect(fuzzySearchFileNodes(nodes, "")).toBe(nodes);
    expect(fuzzySearchFileNodes(nodes, "   ")).toBe(nodes);

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(engineLoads).not.toHaveBeenCalled();
  });

  it("returns the list unfiltered and starts one load when the engine is not ready", async () => {
    const { fuzzySearchFileNodes, preloadFuzzySearch } = await freshFacade();

    expect(fuzzySearchFileNodes(nodes, "apple")).toBe(nodes);
    expect(fuzzySearchFileNodes(nodes, "apple")).toBe(nodes);
    await preloadFuzzySearch();

    expect(engineLoads).toHaveBeenCalledTimes(1);
  });

  it("matches like the engine once loaded, and re-evaluates computeds that called it before", async () => {
    const { fuzzySearchFileNodes, preloadFuzzySearch } = await freshFacade();
    const names = computed(() => fuzzySearchFileNodes(nodes, "apple").map((n) => n.name));

    expect(names.value).toEqual(["apple.png", "banana.png", "cherry.png"]);
    await preloadFuzzySearch();
    await nextTick();

    expect(names.value).toEqual(["apple.png"]);
    expect(fuzzySearchFileNodes(nodes, "zzzzzzz")).toEqual([]);
  });

  it("retries after a failed load", async () => {
    const { fuzzySearchFileNodes, preloadFuzzySearch } = await freshFacade();
    failNextLoad = true;

    await preloadFuzzySearch();
    expect(fuzzySearchFileNodes(nodes, "apple")).toBe(nodes);
    await preloadFuzzySearch();

    // The unfiltered call in between already restarted the load, and the second preload joined it.
    expect(engineLoads).toHaveBeenCalledTimes(2);
    expect(fuzzySearchFileNodes(nodes, "apple").map((n) => n.name)).toEqual(["apple.png"]);
  });
});

describe("fuse.js import graph", () => {
  const srcRoot = join(process.cwd(), "src");
  const sourceFiles = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sourceFiles(path);
      return /\.(vue|ts)$/.test(name) ? [path] : [];
    });

  it("is imported by the engine module only, and the engine only through a dynamic import()", () => {
    const files = sourceFiles(srcRoot);
    const importsFuse = files.filter((file) => /from\s+["']fuse\.js["']/.test(readFileSync(file, "utf8")));
    expect(importsFuse.map((file) => file.slice(srcRoot.length + 1))).toEqual(["utils/fuzzySearchEngine.ts"]);

    const staticEngineImports = files.filter((file) =>
      /^\s*import\s[^;]*from\s+["'][^"']*fuzzySearchEngine["']/m.test(readFileSync(file, "utf8")),
    );
    expect(staticEngineImports).toEqual([]);
  });
});
