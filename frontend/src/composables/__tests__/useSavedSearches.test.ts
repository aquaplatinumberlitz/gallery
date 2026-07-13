import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SearchQueryRequestV1 } from "@/types";
import {
  MAX_RECENT_SEARCHES,
  MAX_SAVED_SEARCHES,
  recordRecentSearch,
  SEARCH_LIBRARY_CHANGE_EVENT,
  SEARCH_LIBRARY_STORAGE_KEY,
  useSavedSearches,
} from "../useSavedSearches";

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

describe("useSavedSearches", () => {
  it("bounds, deduplicates, renames, deletes, and preserves path casing", () => {
    const library = useSavedSearches();
    const first = library.save("Portraits", request("cat"), 100);
    expect(first).not.toBeNull();
    const duplicate = library.save("Updated portraits", request("cat"), 200);
    expect(duplicate?.id).toBe(first?.id);
    expect(library.saved.value).toHaveLength(1);
    expect(library.saved.value[0].request.scope).toEqual({
      kind: "folder",
      library_id: 2,
      import_path_id: 7,
      relative_path: "CaseSensitive/Portraits",
    });

    for (let index = 0; index < MAX_SAVED_SEARCHES + 5; index += 1) {
      library.save(`Search ${index}`, request(`query-${index}`), 300 + index);
    }
    expect(library.saved.value).toHaveLength(MAX_SAVED_SEARCHES);
    const newest = library.saved.value[0];
    expect(library.rename(newest.id, "Renamed", 999)).toBe(true);
    expect(library.saved.value[0].name).toBe("Renamed");
    expect(library.remove(newest.id)).toBe(true);
    expect(library.saved.value.some((item) => item.id === newest.id)).toBe(false);
  });

  it("bounds recent searches and keeps case-distinct canonical requests", () => {
    const dispatch = vi.spyOn(window, "dispatchEvent");
    for (let index = 0; index < MAX_RECENT_SEARCHES + 5; index += 1) {
      expect(recordRecentSearch(request(`query-${index}`), index)).toBe(true);
    }
    expect(recordRecentSearch(request("same", "Folder/A"), 100)).toBe(true);
    expect(recordRecentSearch(request("same", "folder/A"), 101)).toBe(true);

    const library = useSavedSearches();
    expect(library.recent.value).toHaveLength(MAX_RECENT_SEARCHES);
    expect(library.recent.value.slice(0, 2).map((item) => item.request.scope)).toEqual([
      { kind: "folder", library_id: 2, import_path_id: 7, relative_path: "folder/A" },
      { kind: "folder", library_id: 2, import_path_id: 7, relative_path: "Folder/A" },
    ]);
    expect(library.clearRecent()).toBe(true);
    expect(library.recent.value).toEqual([]);
    expect(dispatch.mock.calls.some(([event]) => event.type === SEARCH_LIBRARY_CHANGE_EVENT)).toBe(true);
  });

  it("migrates the previous browser document shape", () => {
    localStorage.setItem(
      SEARCH_LIBRARY_STORAGE_KEY,
      JSON.stringify({
        schema_version: 0,
        savedSearches: [
          {
            id: "old",
            name: "Old search",
            request: {
              schema_version: 1,
              mode: "lexical",
              text: "old",
              scope: { kind: "all" },
              filters: { prompt_groups: [], workflow_groups: [] },
            },
            created_at: 1,
            updated_at: 2,
          },
        ],
        recentSearches: [],
      }),
    );
    const library = useSavedSearches();
    expect(library.saved.value).toEqual([
      expect.objectContaining({ id: "old", name: "Old search", request: expect.objectContaining({ text: "old" }) }),
    ]);
  });

  it("falls back safely for corrupt or unavailable storage", () => {
    localStorage.setItem(SEARCH_LIBRARY_STORAGE_KEY, "{broken");
    expect(useSavedSearches().saved.value).toEqual([]);
    expect(localStorage.getItem(SEARCH_LIBRARY_STORAGE_KEY)).toBeNull();

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });
    expect(useSavedSearches().save("Blocked", request("blocked"))).toBeNull();
  });
});
