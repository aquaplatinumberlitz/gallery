import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import PromptUsagePanel from "../PromptUsagePanel.vue";

const clipboardMocks = vi.hoisted(() => ({
  copyText: vi.fn(),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyText: clipboardMocks.copyText }),
}));

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
  beforeEach(() => {
    clipboardMocks.copyText.mockReset();
    clipboardMocks.copyText.mockResolvedValue(true);
  });

  it("copies prompt text through the shared clipboard fallback", async () => {
    const wrapper = mount(PromptUsagePanel, { props: { scope: { kind: "library", library_id: 2 }, enabled: true } });
    const copyButton = wrapper.get('[aria-label="Copy"]');

    await copyButton.trigger("click");

    expect(clipboardMocks.copyText).toHaveBeenCalledWith("Masterpiece portrait", "prompt", {
      fallbackRoot: copyButton.element,
    });
    const copiedButton = wrapper.get('[aria-label="Prompt copied"]');
    expect(copiedButton.text()).toContain("Copied");
    expect(copiedButton.attributes("data-copied")).toBe("true");
  });

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
