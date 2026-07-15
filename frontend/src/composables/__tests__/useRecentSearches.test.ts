import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SearchQueryRequestV1 } from "@/types";
import {
  LEGACY_SEARCH_LIBRARY_STORAGE_KEY,
  MAX_RECENT_SEARCHES,
  RECENT_SEARCHES_CHANGE_EVENT,
  RECENT_SEARCHES_STORAGE_KEY,
  recordRecentSearch,
  useRecentSearches,
} from "../useRecentSearches";

const request = (text: string, relativePath = "CaseSensitive/Portraits"): SearchQueryRequestV1 => ({
  schema_version: 1,
  mode: "lexical",
  text,
  scope: { kind: "folder", library_id: 2, import_path_id: 7, relative_path: relativePath },
  filters: { prompt_groups: [], workflow_groups: [] },
  cursor: "ignored-cursor",
  limit: 25,
});

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("useRecentSearches", () => {
  it("bounds, deduplicates, and preserves case-distinct canonical requests", () => {
    const dispatch = vi.spyOn(window, "dispatchEvent");
    for (let index = 0; index < MAX_RECENT_SEARCHES + 5; index += 1) {
      expect(recordRecentSearch(request(`query-${index}`), index)).toBe(true);
    }
    expect(recordRecentSearch(request("same", "Folder/A"), 100)).toBe(true);
    expect(recordRecentSearch(request("same", "folder/A"), 101)).toBe(true);
    expect(recordRecentSearch(request("same", "folder/A"), 102)).toBe(true);

    const history = useRecentSearches();
    expect(history.recent.value).toHaveLength(MAX_RECENT_SEARCHES);
    expect(history.recent.value.slice(0, 2).map((item) => item.request.scope)).toEqual([
      { kind: "folder", library_id: 2, import_path_id: 7, relative_path: "folder/A" },
      { kind: "folder", library_id: 2, import_path_id: 7, relative_path: "Folder/A" },
    ]);
    expect(dispatch.mock.calls.some(([event]) => event.type === RECENT_SEARCHES_CHANGE_EVENT)).toBe(true);
  });

  it("migrates recent searches from the previous browser document and ignores saved-search records", () => {
    localStorage.setItem(
      LEGACY_SEARCH_LIBRARY_STORAGE_KEY,
      JSON.stringify({
        schema_version: 1,
        saved: [{ id: "unused", name: "Old saved search" }],
        recent: [{ request: request("old"), used_at: 2 }],
      }),
    );

    const history = useRecentSearches();
    expect(history.recent.value).toEqual([
      expect.objectContaining({ request: expect.objectContaining({ text: "old" }) }),
    ]);
    expect(JSON.parse(localStorage.getItem(RECENT_SEARCHES_STORAGE_KEY) ?? "{}")).toEqual({
      schema_version: 1,
      recent: history.recent.value,
    });
  });

  it("clears history and falls back safely for corrupt or unavailable storage", () => {
    recordRecentSearch(request("rain"), 1);
    const history = useRecentSearches();
    expect(history.clear()).toBe(true);
    expect(history.recent.value).toEqual([]);

    localStorage.setItem(RECENT_SEARCHES_STORAGE_KEY, "{broken");
    expect(useRecentSearches().recent.value).toEqual([]);
    expect(localStorage.getItem(RECENT_SEARCHES_STORAGE_KEY)).toBeNull();

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });
    expect(recordRecentSearch(request("blocked"))).toBe(false);
  });
});
