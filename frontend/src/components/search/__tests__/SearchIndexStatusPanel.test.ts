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
          index_name: "generation_signatures",
          library_id: 2,
          library_name: "Gallery",
          state: "ready",
          usable: true,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 10,
          target_count: 10,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
          active_job_id: null,
        },
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
        {
          index_name: "visual_fingerprints",
          library_id: 2,
          library_name: "Gallery",
          state: "ready",
          usable: true,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 10,
          target_count: 10,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
          active_job_id: null,
        },
        {
          index_name: "workflow_properties",
          library_id: 2,
          library_name: "Gallery",
          state: "ready",
          usable: true,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 10,
          target_count: 10,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
          active_job_id: null,
        },
        {
          index_name: "workflow_raw",
          library_id: 2,
          library_name: "Gallery",
          state: "disabled",
          usable: false,
          enabled: false,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 0,
          target_count: 0,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
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
  const tooltipStubs = {
    Tooltip: { template: "<div><slot /></div>" },
    TooltipTrigger: { template: "<div><slot /></div>" },
    TooltipContent: { template: "<div><slot /></div>" },
  };

  it("distinguishes degraded usable state and confirms rebuild", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const wrapper = mount(SearchIndexStatusPanel, {
      props: { libraryId: 2, open: true },
      global: { stubs: tooltipStubs },
    });
    expect(wrapper.text()).toContain("degraded");
    expect(wrapper.text()).toContain("1 skipped");
    const promptRow = wrapper.findAll("li").find((row) => row.text().includes("prompt values"))!;
    await promptRow
      .findAll("button")
      .find((button) => button.text().includes("Rebuild"))!
      .trigger("click");
    expect(rebuild).toHaveBeenCalledWith({ indexName: "prompt_values", libraryId: 2, mode: "missing" });
  });

  it("explains why the raw workflow index is disabled", () => {
    const wrapper = mount(SearchIndexStatusPanel, {
      props: { libraryId: 2, open: true },
      global: { stubs: tooltipStubs },
    });

    expect(wrapper.find('[aria-label="Why workflow raw is disabled"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Raw workflow search is off in server configuration");
    expect(wrapper.text()).toContain("GALLERY_SEARCH_WORKFLOW_RAW_ENABLED");
  });

  it("explains what each enabled search index powers", () => {
    const wrapper = mount(SearchIndexStatusPanel, {
      props: { libraryId: 2, open: true },
      global: { stubs: tooltipStubs },
    });

    expect(wrapper.find('[aria-label="About generation signatures"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="About prompt values"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="About visual fingerprints"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="About workflow properties"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("metadata evidence to Related assets");
    expect(wrapper.text()).toContain("prompt discovery and exact prompt filters");
    expect(wrapper.text()).toContain("visual evidence to Related assets");
    expect(wrapper.text()).toContain("structured workflow filters in Advanced Search");
  });
});
