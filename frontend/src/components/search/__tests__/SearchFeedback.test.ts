import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SearchFeedback from "../SearchFeedback.vue";

describe("SearchFeedback", () => {
  it.each([
    ["blocking-error", "Search unavailable"],
    ["stale-warning", "Showing the last successful results"],
    ["pagination-error", "Earlier results are still available"],
    ["empty", "No results"],
  ] as const)("renders the %s state distinctly", (state, expected) => {
    const wrapper = mount(SearchFeedback, { props: { state, message: "Network error" } });
    expect(wrapper.text()).toContain(expected);
  });

  it("renders pending skeletons without an empty-state message", () => {
    const wrapper = mount(SearchFeedback, { props: { state: "pending", columnCount: 3 } });
    expect(wrapper.attributes("aria-label")).toBe("Loading search results");
    expect(wrapper.text()).not.toContain("No results");
  });

  it("emits retry without changing presentation state", async () => {
    const wrapper = mount(SearchFeedback, { props: { state: "pagination-error" } });
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
    expect(wrapper.text()).toContain("Earlier results are still available");
  });
});
