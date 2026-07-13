import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import PromptUsagePanel from "../PromptUsagePanel.vue";

vi.mock("@/composables/usePromptUsageQuery", () => ({
  usePromptUsageQuery: () => ({
    isPending: ref(false),
    isError: ref(false),
    items: ref([
      {
        value_id: "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE",
        kind: "positive",
        text: "Masterpiece portrait",
        asset_count: 4,
        last_asset_mtime_ns: 10,
        sample_asset: { asset_id: 1, library_id: 2, path: "/photos/a.png" },
      },
    ]),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    fetchNextPage: vi.fn(),
  }),
}));

describe("PromptUsagePanel", () => {
  it("emits an exact kind and value id for Show assets", async () => {
    const wrapper = mount(PromptUsagePanel, { props: { scope: { kind: "library", library_id: 2 }, enabled: true } });
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Show assets"))!
      .trigger("click");
    expect(wrapper.emitted("showAssets")?.[0]).toEqual([
      { kind: "positive", value_id: "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE" },
    ]);
  });
});
