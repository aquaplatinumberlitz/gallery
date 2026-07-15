import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { recordRecentSearch, useRecentSearches } from "@/composables/useRecentSearches";
import type { SearchFiltersV1, SearchQueryRequestV1 } from "@/types";
import RecentSearchesPanel from "../RecentSearchesPanel.vue";

function request(
  text: string,
  relativePath = "",
  filters: SearchFiltersV1 = { prompt_groups: [], workflow_groups: [] },
): SearchQueryRequestV1 {
  return {
    schema_version: 1,
    mode: "lexical",
    text,
    scope: relativePath
      ? { kind: "folder", library_id: 2, import_path_id: 7, relative_path: relativePath }
      : { kind: "all" },
    filters,
    cursor: null,
    limit: 60,
  };
}

describe("RecentSearchesPanel", () => {
  beforeEach(() => localStorage.clear());

  it("shows an automatic-history empty state without save controls", () => {
    const wrapper = mount(RecentSearchesPanel);

    expect(wrapper.text()).toContain("Your recent searches will appear here automatically.");
    expect(wrapper.find('input[aria-label="Saved search name"]').exists()).toBe(false);
    expect(wrapper.findAll("button").some((button) => button.text().includes("Save"))).toBe(false);
  });

  it("runs a recent search when the user clicks the whole row", async () => {
    recordRecentSearch(request("portrait", "People/Portraits"), 100);
    const wrapper = mount(RecentSearchesPanel);

    const row = wrapper.get('[aria-label="Run recent search: portrait. Folder · People/Portraits"]');
    expect(row.text()).toContain("Folder · People/Portraits");
    await row.trigger("click");

    expect(wrapper.emitted("apply")?.[0]?.[0]).toEqual(
      expect.objectContaining({
        text: "portrait",
        scope: expect.objectContaining({ relative_path: "People/Portraits" }),
      }),
    );
  });

  it("distinguishes a plain query from the same query narrowed to an exact prompt", () => {
    recordRecentSearch(request('prompt:"blue archive"'), 100);
    recordRecentSearch(
      request('prompt:"blue archive"', "", {
        prompt_groups: [{ kind: "positive", value_id: "p".repeat(43) }],
        workflow_groups: [],
      }),
      101,
    );
    const wrapper = mount(RecentSearchesPanel);

    const rows = wrapper
      .findAll("button")
      .filter((button) => button.attributes("aria-label")?.startsWith('Run recent search: prompt:"blue archive".'));
    expect(rows).toHaveLength(2);
    expect(rows[0]?.text()).toContain("Exact positive prompt");
    expect(rows[0]?.attributes("aria-label")).toContain("Exact positive prompt");
    expect(rows[0]?.text()).not.toContain("1 filter");
    expect(rows[1]?.text()).not.toContain("Exact positive prompt");
  });

  it("shows five searches first and progressively reveals the rest", async () => {
    for (let index = 0; index < 7; index += 1) recordRecentSearch(request(`query-${index}`), index);
    const wrapper = mount(RecentSearchesPanel);

    expect(wrapper.findAll('[aria-label^="Run recent search:"]')).toHaveLength(5);
    const showMore = wrapper.get('button[aria-controls="recent-search-list"]');
    expect(showMore.text()).toContain("Show 2 more");
    expect(showMore.attributes("aria-expanded")).toBe("false");

    await showMore.trigger("click");
    expect(wrapper.findAll('[aria-label^="Run recent search:"]')).toHaveLength(7);
    expect(showMore.text()).toContain("Show less");
    expect(showMore.attributes("aria-expanded")).toBe("true");
  });

  it("clears recent history without exposing saved-search management", async () => {
    recordRecentSearch(request("rain"), 100);
    const wrapper = mount(RecentSearchesPanel);

    const clearButton = wrapper.findAll("button").find((button) => button.text().includes("Clear history"));
    expect(clearButton).toBeDefined();
    await clearButton!.trigger("click");

    expect(wrapper.text()).toContain("Your recent searches will appear here automatically.");
    expect(useRecentSearches().recent.value).toEqual([]);
  });
});
