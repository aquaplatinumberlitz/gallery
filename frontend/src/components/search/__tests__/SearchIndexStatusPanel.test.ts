import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import SearchIndexStatusPanel from "../SearchIndexStatusPanel.vue";

const rebuild = vi.fn();
const cancel = vi.fn();
vi.mock("@/composables/useSearchIndexStatusQuery", () => ({
  useSearchIndexStatusQuery: () => ({
    statuses: {
      data: ref([
        {
          index_name: "prompt_values",
          library_id: 2,
          library_name: "Gallery",
          state: "degraded",
          usable: true,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 8,
          target_count: 10,
          failed_count: 1,
          skipped_count: 1,
          skip_reasons: { too_large: 1 },
          active_job_id: null,
        },
      ]),
      isPending: ref(false),
      isError: ref(false),
    },
    rebuild: { mutate: rebuild, isPending: ref(false) },
    cancel: { mutate: cancel, isPending: ref(false) },
  }),
}));

describe("SearchIndexStatusPanel", () => {
  it("distinguishes degraded usable state and confirms rebuild", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const wrapper = mount(SearchIndexStatusPanel, { props: { libraryId: 2, open: true } });
    expect(wrapper.text()).toContain("degraded");
    expect(wrapper.text()).toContain("1 skipped");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Rebuild"))!
      .trigger("click");
    expect(rebuild).toHaveBeenCalledWith({ indexName: "prompt_values", libraryId: 2, mode: "missing" });
  });
});
