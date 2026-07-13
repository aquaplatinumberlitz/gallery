import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SearchResultMetadata from "../SearchResultMetadata.vue";
import type { UnifiedSearchResult } from "@/types";

const result: UnifiedSearchResult = {
  asset_id: 1,
  library_id: 2,
  library_name: "Archive",
  name: "cat.png",
  path: "/cat.png",
  type: "image",
  parent_path: "/",
  relative_path: "cat.png",
  mtime: 1,
  width: 512,
  height: 512,
  match_type: "prompt",
  model: "PonyXL",
  sampler: "Euler a",
  seed: "42",
  prompt_snippet: '<img src=x onerror="alert(1)"> soft light',
};

describe("SearchResultMetadata", () => {
  it("renders match and generation context through text interpolation", () => {
    const wrapper = mount(SearchResultMetadata, { props: { result } });
    expect(wrapper.text()).toContain("Prompt");
    expect(wrapper.text()).toContain("Archive");
    expect(wrapper.text()).toContain("Model PonyXL · Sampler Euler a · Seed 42");
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.html()).toContain("&lt;img");
  });
});
