import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { VueQueryPlugin } from "@tanstack/vue-query";
import RawWorkflowSearch from "../RawWorkflowSearch.vue";
import { searchRawWorkflows } from "@/services/api";
import { createIsolatedQueryClient } from "@/test/queryClient";

vi.mock("@/services/api", () => ({ searchRawWorkflows: vi.fn() }));

const capability = {
  enabled: true,
  query_min_chars: 3,
  query_max_chars: 128,
  limit_max: 50,
  deadline_ms: 250,
  max_document_bytes: 1_048_576,
  index_budget_bytes: 536_870_912,
};

describe("RawWorkflowSearch", () => {
  beforeEach(() => vi.mocked(searchRawWorkflows).mockReset());

  it("never searches while typing and requires acknowledgement plus Apply", async () => {
    vi.mocked(searchRawWorkflows).mockResolvedValue({
      query: "model",
      items: [],
      next_cursor: null,
      has_more: false,
      returned: 0,
      warning: "bounded",
      capability: { deadline_ms: 250, max_query_chars: 128, max_limit: 50 },
    });
    const wrapper = mount(RawWorkflowSearch, {
      props: { capability, scope: { kind: "all" } },
      global: { plugins: [[VueQueryPlugin, { queryClient: createIsolatedQueryClient() }]] },
    });
    await wrapper.get('input[aria-label="Raw workflow search term"]').setValue("model");
    await flushPromises();
    expect(searchRawWorkflows).not.toHaveBeenCalled();
    await wrapper.get('input[type="checkbox"]').setValue(true);
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Apply"))!
      .trigger("click");
    await flushPromises();
    expect(searchRawWorkflows).toHaveBeenCalledOnce();
  });
});
