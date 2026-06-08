import Fuse, { type IFuseOptions } from "fuse.js";
import type { FileNode } from "../types";

interface FuzzySearchOptions {
  includePath?: boolean;
}

type FuseCacheEntry = {
  nameOnly?: Fuse<FileNode>;
  withPath?: Fuse<FileNode>;
};

const fuseCache = new WeakMap<FileNode[], FuseCacheEntry>();

const getFuse = (items: FileNode[], includePath: boolean): Fuse<FileNode> => {
  const cacheEntry = fuseCache.get(items) ?? {};
  const cacheKey = includePath ? "withPath" : "nameOnly";
  const cached = cacheEntry[cacheKey];
  if (cached) return cached;

  const fuseOptions: IFuseOptions<FileNode> = {
    keys: includePath
      ? [
          { name: "name", weight: 0.85 },
          { name: "path", weight: 0.15 },
        ]
      : [{ name: "name", weight: 1 }],
    threshold: 0.4,
    ignoreLocation: true,
    shouldSort: true,
    minMatchCharLength: 1,
  };

  const fuse = new Fuse(items, fuseOptions);
  cacheEntry[cacheKey] = fuse;
  fuseCache.set(items, cacheEntry);
  return fuse;
};

export function fuzzySearchFileNodes(
  items: FileNode[],
  query: string,
  options: FuzzySearchOptions = {}
): FileNode[] {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) return items;

  return getFuse(items, options.includePath ?? false)
    .search(trimmedQuery)
    .map((result) => result.item);
}
